import threading, time, random

class RateLimiter:
    """RPS + concurrencia (bloqueante, thread-safe)."""
    def __init__(self, rate_per_sec: float = 3.0, max_concurrent: int = 1):
        self.interval = 1.0 / float(max(0.001, rate_per_sec))
        self._next = 0.0
        self._lock = threading.Lock()
        self._sema = threading.Semaphore(max_concurrent)

    def acquire(self):
        self._sema.acquire()
        with self._lock:
            now = time.monotonic()
            if self._next < now:
                self._next = now
            wait = self._next - now
            self._next += self.interval
        if wait > 0:
            time.sleep(wait)

    def release(self):
        self._sema.release()

def with_retry(fn, *, retries=5, base_ms=500, max_ms=30_000,
               retriable_status=(429, 500, 502, 503, 504),
               no_retry_on_timeout: bool = False):
    """
    Backoff exponencial con jitter para 429/5xx y timeouts.

    Args:
        no_retry_on_timeout: Si True, NO reintenta en caso de timeout.
                             Usar True para operaciones NO idempotentes (ej: crear asientos en SAP),
                             donde un timeout puede significar que SAP YA procesó la solicitud
                             y reintentar crearía duplicados.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as e:
            attempt += 1
            status = getattr(e, 'status', None)
            msg = str(e)
            timeouty = 'timeout' in msg.lower()

            # Si es timeout y no_retry_on_timeout está activo → propagar sin reintentar
            if timeouty and no_retry_on_timeout:
                raise

            retriable = (status in retriable_status) or timeouty
            if (not retriable) or attempt > retries:
                raise
            delay = min(max_ms/1000.0, (2 ** (attempt - 1)) * (base_ms/1000.0) + random.uniform(0, 0.2))
            time.sleep(delay)
