from __future__ import annotations
from .rate_limit import RateLimiter, with_retry
from .journal_builder import build_journal_entry
from .validators import validate_journal_entry_lines
import time

class CircuitBreaker:
    def __init__(self, *, enabled=True, fail_threshold=8, cool_down_sec=30):
        self.enabled = enabled
        self.fail_threshold = fail_threshold
        self.cool_down_sec = cool_down_sec
        self._fails = 0
        self._open_until = 0.0

    def check(self):
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

    def post_one(self, *, key: str, cab: dict, lines: list[dict], payload: dict, build_fn=None):
        if self.breaker.check():
            raise RuntimeError("Circuit breaker abierto; en enfriamiento.")

        validate_journal_entry_lines(lines)

        misses = self._validate_accounts(lines)
        if misses:
            raise RuntimeError(f"Cuentas inválidas: {', '.join(map(str, misses[:10]))}{'...' if len(misses)>10 else ''}")

        print(f"payload: {payload}")
        def call():
            self.limiter.acquire()
            try:
                if self.dry_run:
                    return {"dry": True}
                return self.sl.post_journal_entries(payload)
            finally:
                self.limiter.release()

        res = with_retry(call, retries=5, base_ms=500, max_ms=30_000)
        self.breaker.on_success()
        return res,payload

    def post_all(self, items: list[dict], build_fn=None):
        ok = fail = 0
        results = []
        payloads=[]
        print("lis ",items)
        for it in items:
            try:
                p = (build_fn or build_journal_entry)(it["cab"], it["lines"], local_currency=self.local_currency)
                r, _ = self.post_one(key=it["key"], cab=it["cab"], lines=it["lines"], payload=p, build_fn=build_fn)
                ok += 1
                results.append({"key": it["key"], "ok": True, "res": r, "payload": p})
                print(f"[OK] {it['key']} -> {r}")
            except Exception as e:
                fail += 1
                p = (build_fn or build_journal_entry)(it["cab"], it["lines"], local_currency=self.local_currency)
                results.append({"key": it["key"], "ok": False, "err": str(e), "payload": p})
                print(f"[FAIL] {it['key']} -> {e}")
                if self.breaker.on_fail():
                    print(f"[breaker] abierto {self.breaker.cool_down_sec}s...")
                    time.sleep(self.breaker.cool_down_sec)
        return {"ok": ok, "fail": fail, "results": results}
