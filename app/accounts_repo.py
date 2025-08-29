from app.modules.SL_B1.sl_client import ServiceLayerClient, SLRequestError
from .cache_accounts import TTLCache

class AccountsRepo:
    def __init__(self, sl: ServiceLayerClient, ttl_seconds=3600, max_items=20000):
        self.sl = sl
        self.cache = TTLCache(ttl_seconds, max_items)

    def exists(self, code: str) -> bool:
        if not code: return False
        k = f"acct:{code}"
        hit = self.cache.get(k)
        if hit is not None: return bool(hit)
        try:
            acc = self.sl.get_account(code)
            ok = acc is not None
            self.cache.set(k, ok)
            return ok
        except SLRequestError as e:
            if e.status == 404:
                self.cache.set(k, False)
                return False
            raise

    def preload_all(self, top=1000):
        for it in self.sl.iter_accounts(top=top):
            code = it.get("Code")
            if code:
                self.cache.set(f"acct:{code}", True)
