from __future__ import annotations
from .rate_limit import RateLimiter, with_retry
from .journal_builder import build_journal_entry
from .batch_builder import build_batch_request, parse_batch_response
import time
import re

class CircuitBreaker:
    def __init__(self, *, enabled=True, fail_threshold=8, cool_down_sec=30):
        self.enabled = enabled
        self.fail_threshold = fail_threshold
        self.cool_down_sec = cool_down_sec
        self._fails = 0
        self._open_until = 0.0

    def check(self): ## is open ?
        return self.enabled and time.time() < self._open_until

    def on_success(self):
        self._fails = 0

    def on_fail(self):
        if not self.enabled: return False
        self._fails += 1
        if self._fails >= self.fail_threshold:
            self._open_until = time.time() + self.cool_down_sec
            self._fails = 0
            return True
        return False

class JournalPoster:
    def __init__(self, sl_client, accounts_repo, *, rps=3, concurrency=1, local_currency="PEN", dry_run=False, breaker: CircuitBreaker | None = None):
        self.sl = sl_client
        self.repo = accounts_repo
        self.limiter = RateLimiter(rate_per_sec=rps, max_concurrent=concurrency)
        self.local_currency = local_currency
        self.dry_run = dry_run
        self.breaker = breaker or CircuitBreaker()

    def _validate_accounts(self, lines):
        missing = set()
        for l in lines:
            code = l.get("AccountCode")
            if not self.repo.exists(code):
                missing.add(code or "")
        return list(missing)

    def post_all2(self, items: list[dict], build_fn=None):
        
        if self.breaker.check():
            raise RuntimeError("Circuit breaker abierto; en enfriamiento.")

        results = []
        valid_requests = []
        valid_items_map = []
        # 1. Validar y preparar todas las solicitudes
        for i, it in enumerate(items):
            payload = (build_fn or build_journal_entry)(it["cab"], it["lines"], local_currency=self.local_currency)
            # misses = self._validate_accounts(it["lines"])
            
            # if misses:
            #     err_msg = f"Cuentas invalidas: {', '.join(map(str, misses[:10]))}{'...' if len(misses)>10 else ''}"
            #     results.append({"key": it["key"], "ok": False, "err": err_msg, "payload": payload})
            #     continue
            
            valid_requests.append({
                "method": "POST",
                "path": "/JournalEntries",
                "body": payload
            })
            valid_items_map.append(it)
        if not valid_requests:
            return {"ok": 0, "fail": len(results), "results": results}
        # print(f"valid {self.dry_run}")

        # 2. Construir y ejecutar la solicitud batch
        if not self.dry_run:
            for it in valid_items_map:
                results.append({"key": it["key"], "ok": True, "res": {"dry": True}, "payload": it["cab"]})
            return {"ok": len(valid_items_map), "fail": len(items) - len(valid_items_map), "results": results}

        batch_body, batch_headers = build_batch_request(valid_requests)
        
        try:
            # La logica de reintento y rate limiting se aplica a todo el lote
            def call():
                self.limiter.acquire()
                try:
                    return self.sl.request("POST", "/$batch", json=None, headers=batch_headers, data=batch_body)
                finally:
                    self.limiter.release()
            
            raw_res = with_retry(call, retries=5, base_ms=500, max_ms=30_000)
            self.breaker.on_success()

        except Exception as e:
            self.breaker.on_fail()
            # Si todo el lote falla, marcamos todos los asientos de ese lote como fallidos
            for it in valid_items_map:
                results.append({"key": it["key"], "ok": False, "err": f"Fallo en lote completo: {e}", "payload": it["cab"]})
            return {"ok": 0, "fail": len(items), "results": results}

        # 3. Interpretar la respuesta del lote
        content_type = raw_res.headers.get("Content-Type", "")
        # boundary_match = raw_res.search(r'boundary=(batchresponse_.*)', content_type)
        ct = raw_res.headers.get('Content-Type', '')
        m = re.search(r'boundary="?([^";]+)"?', ct, flags=re.I)
        boundary_match = m.group(1) if m else None
        if not boundary_match:
            # Fallo si no podemos interpretar la respuesta
            for it in valid_items_map:
                results.append({"key": it["key"], "ok": False, "err": "No se pudo encontrar el boundary en la respuesta del lote", "payload": it["cab"]})
            return {"ok": 0, "fail": len(items), "results": results}

        batch_responses = parse_batch_response(raw_res.text, boundary_match)
        # print(f"test {batch_responses}")
        for i, res_part in enumerate(batch_responses):
            item = valid_items_map[i]
            payload = valid_requests[i]['body']
            if res_part["status_code"] >= 200 and res_part["status_code"] < 300:
                results.append({"key": item["key"], "ok": True, "res": res_part["body"], "payload": payload})
            else:
                results.append({"key": item["key"], "ok": False, "err": res_part["body"], "payload": payload})
                self.breaker.on_fail()

        ok_count = sum(1 for r in results if r["ok"])
        fail_count = sum(1 for r in results if not r["ok"])
        
        return {"ok": ok_count, "fail": fail_count, "results": results}
    
    

    def post_all(self, items: list[dict], build_fn=None):
        if self.breaker.check():
            raise RuntimeError("Circuit breaker abierto; en enfriamiento.")

        results: list[dict] = []
        valid_requests: list[dict] = []
        items_by_cid: dict[str, dict] = {}
        ordered_cids: list[str] = []

        # 1) Preparar solicitudes (1 doc = 1 subrequest)
        for i, it in enumerate(items):
            payload = (build_fn or build_journal_entry)(it["cab"], it["lines"], local_currency=self.local_currency)
            content_id = str(it.get("key") or i)  # usa tu key si es única
            valid_requests.append({
                "method": "POST",
                "path": "/JournalEntries",
                "body": payload,
                "content_id": content_id,  # <-- que build_batch_request ponga este Content-ID
            })
            items_by_cid[content_id] = {"item": it, "payload": payload}
            ordered_cids.append(content_id)

        if not valid_requests:
            return {"ok": 0, "fail": 0, "results": results}

        # 2) Dry-run: sólo vista previa
        if self.dry_run:
            for cid in ordered_cids:
                it = items_by_cid[cid]["item"]
                payload = items_by_cid[cid]["payload"]
                results.append({"key": it["key"], "ok": True, "res": {"dry_run": True}, "payload": payload})
            return {"ok": len(results), "fail": 0, "results": results}

        # 3) Construir y enviar el $batch real
        batch_body, batch_headers = build_batch_request(valid_requests)

        try:
            def call():
                self.limiter.acquire()
                try:
                    return self.sl.request("POST", "/$batch", json=None, headers=batch_headers, data=batch_body)
                finally:
                    self.limiter.release()

            raw_res = with_retry(call, retries=5, base_ms=500, max_ms=30_000)
            self.breaker.on_success()
        except Exception as e:
            self.breaker.on_fail()
            for cid in ordered_cids:
                it = items_by_cid[cid]["item"]
                results.append({"key": it["key"], "ok": False, "err": f"Fallo en lote completo: {e}", "payload": items_by_cid[cid]["payload"]})
            return {"ok": 0, "fail": len(ordered_cids), "results": results}

        # 4) Interpretar respuesta batch
        ct = raw_res.headers.get("Content-Type", "")
        m = re.search(r'boundary="?([^";]+)"?', ct, flags=re.I)
        boundary = m.group(1) if m else None
        if not boundary:
            for cid in ordered_cids:
                it = items_by_cid[cid]["item"]
                results.append({"key": it["key"], "ok": False, "err": "No se pudo encontrar el boundary en la respuesta del lote", "payload": items_by_cid[cid]["payload"]})
            return {"ok": 0, "fail": len(ordered_cids), "results": results}

        parts = parse_batch_response(raw_res.text, boundary)

        # Indexar por Content-ID; fallback secuencial si alguna parte no trae content_id
        by_cid = {p.get("content_id"): p for p in parts if p.get("content_id")}
        seq_parts = [p for p in parts if not p.get("content_id")]
        seq_idx = 0

        def _extract_err(p) -> str:
            body = p.get("body")
            raw = p.get("raw_body")
            try:
                if isinstance(body, dict):
                    msg = ((body.get("error") or {}).get("message") or {}).get("value")
                    if msg:
                        return msg
                    return json.dumps(body, ensure_ascii=False)
                if raw:
                    obj = json.loads(raw)
                    msg = ((obj.get("error") or {}).get("message") or {}).get("value")
                    return msg or raw
            except Exception:
                pass
            return raw or "Error desconocido"

        for cid in ordered_cids:
            it = items_by_cid[cid]["item"]
            payload = items_by_cid[cid]["payload"]

            p = by_cid.get(cid)
            if p is None and seq_idx < len(seq_parts):
                p = seq_parts[seq_idx]
                seq_idx += 1

            if p is None:
                results.append({
                    "key": it["key"], "ok": False,
                    "err": "No se encontró respuesta para este Content-ID",
                    "payload": payload,
                    "response": {"raw_batch": raw_res.text}
                })
                self.breaker.on_fail()
                continue

            sc = int(p.get("status_code") or 0)
            st = p.get("status_text") or ""
            per_item_resp = {
                "status_code": sc,
                "status_text": st,
                "body": p.get("body"),
                "raw": p.get("raw_body"),
                "http_headers": p.get("http_headers"),
            }

            if 200 <= sc < 300:
                results.append({
                    "key": it["key"], "ok": True,
                    "res": per_item_resp,
                    "payload": payload
                })
            else:
                err_msg = _extract_err(p)
                results.append({
                    "key": it["key"], "ok": False,
                    "err": f"{sc} {st}: {err_msg}",
                    "payload": payload,
                    "response": per_item_resp
                })
                self.breaker.on_fail()

        ok_count = sum(1 for r in results if r["ok"])
        fail_count = sum(1 for r in results if not r["ok"])

        return {"ok": ok_count, "fail": fail_count, "results": results}
