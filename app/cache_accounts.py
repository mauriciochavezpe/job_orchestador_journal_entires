import time

class TTLCache:
    def __init__(self, ttl_seconds: int = 3600, max_items: int = 20000):
        self.ttl = ttl_seconds
        self.max = max_items
        self._data = {}
        self._exp  = {}

    def get(self, k):
        v = self._data.get(k)
        if v is None: return None
        if self._exp.get(k, 0) < time.time():
            self._data.pop(k, None); self._exp.pop(k, None)
            return None
        return v

    def set(self, k, v):
        if len(self._data) >= self.max:
            self._data.pop(next(iter(self._data)))
            self._exp.pop(next(iter(self._exp)), None)
        self._data[k] = v
        self._exp[k]  = time.time() + self.ttl
