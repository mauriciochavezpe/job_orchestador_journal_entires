import time
from threading import RLock
from collections import OrderedDict

class TTLCache:
    """
    Cache en memoria con TTL por entrada y capacidad máxima.
    - Expulsión FIFO por defecto (puedes pasar policy='lru' si quieres LRU).
    - Thread-safe con RLock.
    - Reloj monotónico para evitar problemas si cambia la hora del SO.
    """

    def __init__(self, ttl_seconds: float = 3600, max_items: int = 20000,
                 clock=time.monotonic, policy: str = 'fifo'):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser > 0")
        if max_items <= 0:
            raise ValueError("max_items debe ser > 0")
        if policy not in ('fifo', 'lru'):
            raise ValueError("policy debe ser 'fifo' o 'lru'")

        self.ttl = float(ttl_seconds)
        self.max = int(max_items)
        self._clock = clock
        self._policy = policy

        self._data = OrderedDict()  # mantiene orden de inserción/uso
        self._exp  = {}             # key -> timestamp de expiración
        self._lock = RLock()

    # -------------- helpers internos --------------

    def _is_expired(self, key) -> bool:
        return self._exp.get(key, -1.0) < self._clock()

    def _delete_unlocked(self, key) -> None:
        self._data.pop(key, None)
        self._exp.pop(key, None)

    def _expire_key_unlocked(self, key) -> None:
        # se usa cuando detectamos expiración
        self._delete_unlocked(key)

    def _evict_one_unlocked(self) -> None:
        # expulsa el más antiguo:
        # - FIFO: más antiguo por inserción
        # - LRU : menos usado recientemente (si movemos al final en accesos)
        if not self._data:
            return
        k, _ = self._data.popitem(last=False)
        self._exp.pop(k, None)

    # -------------- API pública mínima --------------

    def get(self, key, default=None):
        """Devuelve el valor si existe y no expiró; si no, 'default'."""
        with self._lock:
            if key not in self._data:
                return default
            if self._is_expired(key):
                self._expire_key_unlocked(key)
                return default
            # acceso válido
            if self._policy == 'lru':
                self._data.move_to_end(key)
            return self._data[key]

    def set(self, key, value, ttl_seconds: float | None = None) -> None:
        """Guarda (key, value) con TTL (por defecto el global)."""
        ttl = float(ttl_seconds) if ttl_seconds is not None else self.ttl
        if ttl <= 0:
            raise ValueError("ttl_seconds debe ser > 0")

        with self._lock:
            exists = key in self._data

            # libera espacio solo si es una nueva clave y ya alcanzaste el máximo
            if not exists and len(self._data) >= self.max:
                self._evict_one_unlocked()

            self._data[key] = value
            self._exp[key] = self._clock() + ttl
            if self._policy == 'lru':
                self._data.move_to_end(key)

    def delete(self, key) -> bool:
        """Elimina la clave si existe. Retorna True si la borró."""
        with self._lock:
            if key in self._data:
                self._delete_unlocked(key)
                return True
            return False

    def clear(self) -> None:
        """Vacía todo el caché."""
        with self._lock:
            self._data.clear()
            self._exp.clear()

    def purge(self) -> int:
        """Elimina todas las claves expiradas ahora mismo. Devuelve cuántas purgó."""
        with self._lock:
            now = self._clock()
            expired = [k for k, t in self._exp.items() if t < now]
            for k in expired:
                self._expire_key_unlocked(k)
            return len(expired)

    def __contains__(self, key) -> bool:
        """Permite usar: `if key in cache:` (solo si no expiró)."""
        with self._lock:
            if key not in self._data:
                return False
            if self._is_expired(key):
                self._expire_key_unlocked(key)
                return False
            if self._policy == 'lru':
                self._data.move_to_end(key)
            return True
