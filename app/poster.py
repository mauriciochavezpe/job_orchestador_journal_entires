from __future__ import annotations
from .rate_limit import RateLimiter, with_retry
from .journal_builder import build_journal_entry
from .batch_builder import build_batch_request, parse_batch_response
import time
import re
from typing import Any, Dict, List, Optional
import json

class CircuitBreaker:
    """
    Controla el estado de la comunicación con SAP. Si el número de errores
    seguidos supera el umbral, el circuito se "abre" y bloquea cualquier envío
    posterior durante un periodo de enfriamiento (cool_down).
    """
    def __init__(self, *, enabled: bool = True, fail_threshold: int = 8, cool_down_sec: int = 30):
        self.enabled = enabled
        self.fail_threshold = fail_threshold
        self.cool_down_sec = cool_down_sec
        self._fails = 0
        self._open_until = 0.0

    def check(self) -> bool:
        """Indica si el circuito está abierto (bloqueando peticiones)."""
        return self.enabled and time.time() < self._open_until

    def on_success(self):
        """Reinicia el contador de errores tras un éxito."""
        self._fails = 0

    def on_fail(self) -> bool:
        """Registra un fallo y abre el circuito si se alcanza el límite."""
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
            # formateamos desde los valores del lines
            
            payload = (build_fn or build_journal_entry)(it["cab"], it["lines"], local_currency=self.local_currency)
            # misses = self._validate_accounts(it["lines"])
            
            # if misses:
            #     err_msg = f"Cuentas invalidas: {', '.join(map(str, misses[:10]))}{'...' if len(misses)>10 else ''}"
            #     results.append({"key": it["key"], "ok": False, "err": err_msg, "payload": payload})
            #     continue
            
            valid_requests.append({
                "method": "POST",
                "path": "/JournalVouchersService_Add",
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
    
    

    def post_all(self, items: list[dict], build_fn=None, chunk_size: int = 20):
        """
        Orquesta el envío de todos los asientos contables, dividiéndolos en
        sub-lotes (chunks) para evitar saturar el Service Layer o exceder
        el límite de tiempo de respuesta.

        Args:
            items: Lista de diccionarios con la data de cada asiento.
            build_fn: Función constructora de JSON opcional.
            chunk_size: Tamaño de cada lote (default 20).
        """
        if self.breaker.check():
            raise RuntimeError("Circuit breaker abierto; en enfriamiento.")

        total_results = {"ok": 0, "fail": 0, "results": []}
        
        # Segmentación de la carga total
        for i in range(0, len(items), chunk_size):
            chunk = items[i : i + chunk_size]
            print(f"-> Procesando lote {i//chunk_size + 1} ({len(chunk)} registros de {len(items)})...")
            
            chunk_res = self._post_batch_chunk(chunk, build_fn)
            
            # Acumulación de métricas
            total_results["ok"] += chunk_res["ok"]
            total_results["fail"] += chunk_res["fail"]
            total_results["results"].extend(chunk_res["results"])
            
            # Verificación del breaker después de cada lote
            if self.breaker.check():
                print(f"[ERROR] Circuit Breaker activado. Abortando el resto de lotes.")
                break
                
        return total_results

    def _post_batch_chunk(self, items: list[dict], build_fn=None):
        """
        Realiza el envío físico de un paquete $batch a SAP.
        Construye la petición multipart, la envía y parsea la respuesta.
        """
        results: list[dict] = []
        valid_requests: list[dict] = []
        items_by_cid: dict[str, dict] = {}

        # 1) Preparar solicitudes
        for i, it in enumerate(items):
            payload = (build_fn or build_journal_entry)(it["cab"], it["lines"], local_currency=self.local_currency)
            content_id = str(it.get("key") or i)
            valid_requests.append({
                "method": "POST",
                "path": "JournalVouchersService_Add",
                "body": payload,
                "content_id": content_id,
            })
            items_by_cid[content_id] = {"item": it, "payload": payload}

        if not valid_requests:
            return {"ok": 0, "fail": 0, "results": results}
        
        # 2) Dry-run
        if self.dry_run:
            for cid, info in items_by_cid.items():
                it = info["item"]
                payload = info["payload"]
                results.append({
                    "key": it["key"], "ok": True,
                    "res": {"dry_run": True}, "payload": payload
                })
            return {"ok": len(results), "fail": 0, "results": results}

        # 3) Construir y enviar el $batch real
        batch_body, batch_headers, ordered_cids = build_batch_request(valid_requests)
        
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
                results.append({
                    "key": it["key"],
                    "ok": False, "err": f"Fallo en lote completo: {e}",
                    "payload": items_by_cid[cid]["payload"]
                })
            return {"ok": 0, "fail": len(ordered_cids), "results": results}

        # 4) Interpretar respuesta batch
        ct = raw_res.headers.get("Content-Type", "")
        m = re.search(r'boundary="?([^";]+)"?', ct, flags=re.I)
        boundary = m.group(1) if m else None
        
        if not boundary:
            for cid in ordered_cids:
                it = items_by_cid[cid]["item"]
                results.append({
                    "key": it["key"], "ok": False, 
                    "err": "No se pudo encontrar el boundary en la respuesta del lote", 
                    "payload": items_by_cid[cid]["payload"]
                })
            return {"ok": 0, "fail": len(ordered_cids), "results": results}

        parts = parse_batch_response(raw_res.text, boundary)

        # ---------------------------------------------------------------------
        # 1) Indexar por Content-ID
        # ---------------------------------------------------------------------
        by_cid: Dict[Optional[str], Dict[str, Any]] = {
            p.get("content_id"): p for p in parts if p.get("content_id")
        }
        
        seq_parts: List[Dict[str, Any]] = [p for p in parts if not p.get("content_id")]
        seq_idx = 0

        def _extract_err_msg(part: Dict[str, Any]) -> str:
            body = part.get("body")
            raw = part.get("raw_body")
            try:
                if isinstance(body, dict):
                    msg = ((body.get("error") or {}).get("message") or {}).get("value")
                    if msg: return str(msg)
                    return json.dumps(body, ensure_ascii=False)
                if raw:
                    obj = json.loads(raw)
                    msg = ((obj.get("error") or {}).get("message") or {}).get("value")
                    return str(msg or raw)
            except Exception: pass
            return raw or "Error desconocido"
        
        def _build_per_item_response(part: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "status_code": int(part.get("status_code") or 0),
                "status_text": part.get("status_text") or "",
                "body": part.get("body"),
                "raw": part.get("raw_body"),
                "http_headers": part.get("http_headers"),
                "content_id": part.get("content_id"),
            }
        
        # ---------------------------------------------------------------------
        # 2) Recorrer los content_ids originales
        # ---------------------------------------------------------------------
        for cid in ordered_cids:
            item_info = items_by_cid[cid]
            it = item_info["item"]
            payload = item_info["payload"]

            part = by_cid.get(cid)
            if part is None and seq_idx < len(seq_parts):
                part = seq_parts[seq_idx]
                seq_idx += 1

            if part is None:
                results.append({
                    "key": it["key"],
                    "ok": False,
                    "err": "No se encontró respuesta para este Content-ID",
                    "payload": payload,
                    "response": {"raw_batch": raw_res.text},
                })
                self.breaker.on_fail()
                continue

            sc = int(part.get("status_code") or 0)
            per_item_resp = _build_per_item_response(part)
            is_ok = 200 <= sc < 300

            if is_ok:
                results.append({
                    "key": it["key"],
                    "ok": True,
                    "res": per_item_resp,
                    "payload": payload,
                })
            else:
                err_msg = _extract_err_msg(part)
                results.append({
                    "key": it["key"],
                    "ok": False,
                    "err": f"{per_item_resp['status_code']} {per_item_resp['status_text']}: {err_msg}",
                    "payload": payload,
                    "response": per_item_resp,
                })
                self.breaker.on_fail()

        ok_count = sum(1 for r in results if r["ok"])
        fail_count = sum(1 for r in results if not r["ok"])
        return {"ok": ok_count, "fail": fail_count, "results": results}