# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException, Header
from typing import List, Dict, Any, Optional
import uvicorn
from app.main import post_payload_to_sl
from fastapi.middleware.cors import CORSMiddleware
import time

app = FastAPI(
    title="Journal Entries Orchestrator API",
    docs_url="/api/asientos/docs",
    redoc_url="/api/asientos/redoc",
    openapi_url="/api/asientos/openapi.json"
)

# Configurar CORS para permitir que tu frontend se comunique con la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar a dominios específicos en producción por seguridad
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Registro en memoria de claves de idempotencia ya procesadas.
# { idempotency_key: {"result": ..., "expires_at": timestamp} }
# TTL de 24 horas: protege contra reintentos del sistema externo.
# ─────────────────────────────────────────────────────────────
_processed_keys: Dict[str, Dict] = {}
_IDEMPOTENCY_TTL_SEC = 86_400  # 24 horas

def _cleanup_expired_keys():
    """Elimina claves expiradas del registro en memoria."""
    now = time.time()
    expired = [k for k, v in _processed_keys.items() if v["expires_at"] < now]
    for k in expired:
        del _processed_keys[k]

@app.post("/api/qas/asientos")
async def process_journal_entries(
    payload: List[Dict[str, Any]],
    x_idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key")
):
    """
    Recibe una lista plana de diccionarios, donde cada diccionario representa una línea
    con datos tanto de la cabecera como del detalle del asiento contable.

    **Idempotencia**: Envía el header `X-Idempotency-Key` con un UUID único por operación.
    Si el mismo key se recibe de nuevo (reintento por timeout de red), se devuelve el
    resultado original sin re-procesar ni crear duplicados en SAP.

    Ejemplo de header: `X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000`
    """
    if not payload:
        raise HTTPException(status_code=400, detail="El payload está vacío")

    # ── Chequeo de idempotencia ───────────────────────────────────────────────
    if x_idempotency_key:
        _cleanup_expired_keys()
        if x_idempotency_key in _processed_keys:
            cached = _processed_keys[x_idempotency_key]
            print(f"[IDEMPOTENCY] Key '{x_idempotency_key}' ya fue procesada. Devolviendo resultado cacheado.")
            return {
                "status": "success",
                "message": "Proceso completado (resultado cacheado — reintento detectado)",
                "idempotency_key": x_idempotency_key,
                "data": cached["result"]
            }
    # ─────────────────────────────────────────────────────────────────────────

    try:
        resultado = post_payload_to_sl(payload)

        # Guardar resultado si se usó idempotency key
        if x_idempotency_key:
            _processed_keys[x_idempotency_key] = {
                "result": resultado,
                "expires_at": time.time() + _IDEMPOTENCY_TTL_SEC
            }

        return {
            "status": "success",
            "message": "Proceso completado",
            "idempotency_key": x_idempotency_key,
            "data": resultado
        }
    except Exception as e:
        # IMPORTANTE: NO guardar la key si hubo error — así el reintento puede re-ejecutar.
        # Si el error fue timeout de SAP (ya creó los asientos), el sistema externo
        # no debería reintentar sin verificar en SAP primero.
        raise HTTPException(status_code=500, detail=f"Error en el procesamiento: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("app.api:app", host="0.0.0.0", port=3018, reload=True, timeout_keep_alive=300)
