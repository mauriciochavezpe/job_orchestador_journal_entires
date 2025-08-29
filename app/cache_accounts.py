import time
from threading import RLock
class TTLCache:
    def __init__(self, ttl_seconds: int = 3600, max_items: int = 20000, 
                clock= time.monotonic):
        self.ttl = ttl_seconds
        self.max = max_items
        self._data = {}
        self._exp  = {}
        self._lock = RLock()
        self._clock = clock
        self._policy = 'fifo'

    # def get(self, k):
    #     v = self._data.get(k)
    #     if v is None: return None
    #     if self._exp.get(k, 0) < time.time():
    #         self._data.pop(k, None); self._exp.pop(k, None)
    #         return None
    #     return v
    
    def get(self, key, default=None):
        with self._lock:
            if key not in self._data:
                return False
            k = key
            if self.is_expired(k):
                self._expire_key_unlocked(k)
                return False
            if self._police == "lru":
                self._data.move_to_end(k)
            return True

    # def set(self, k, v):
    #     if len(self._data) >= self.max:
    #         self._data.pop(next(iter(self._data)))
    #         self._exp.pop(next(iter(self._exp)), None)
    #     self._data[k] = v
    #     self._exp[k]  = time.time() + self.ttl
    
    def set(self,key,value, ttl) -> None:
        """
        Guarda el par (key, value) con un TTL (por defecto el global).
        Si excede 'max_items' y la clave no existía, expulsa 1 entrada según la política.
        """
        
        ttl= float(ttl) if ttl is not None else self.ttl
        if ttl <=0:
            raise ValueError('ttl_seconds deber ser > 0')
        
        with self._lock:
            
            exists = key in self._data
            
            if not exists and len(self._data) >= self._max:
                self._evict_one_unlocked()
            
            self._data[key] = value
            self._exp[key] = self._clock() + ttl
            # if self._policy == 'lru':
                # self._data.move_to_end(key)


    def delete(self, key) -> bool:
        with self._lock:
            if key in self._data:
                self._delete_unlocked(key)
                return True
            return False
        
    def clear(self):
        
        with  self._lock:
            self._data.clear()
            self._exp.clear()

    def purge(self) -> int:
        
        with self._lock:
            now = self._clock()
            expired = [ k for k, t in self._exp.items() if t < now]
            for k in expired:
                self._expire_key_unlocked(k)
            return len(expired)