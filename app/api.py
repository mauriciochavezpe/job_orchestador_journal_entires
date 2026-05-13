from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
import uvicorn
from app.main import post_payload_to_sl
from fastapi.middleware.cors import CORSMiddleware

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

@app.post("/api/asientos")
async def process_journal_entries(payload: List[Dict[str, Any]]):
    """
    Recibe una lista plana de diccionarios, donde cada diccionario representa una línea
    con datos tanto de la cabecera como del detalle del asiento contable.
    """
    
    if not payload:
        raise HTTPException(status_code=400, detail="El payload está vacío")
    
    try:
        # Llama a la lógica principal pasándole el JSON del frontend
        resultado = post_payload_to_sl(payload)
        return {
            "status": "success",
            "message": "Proceso completado",
            "data": resultado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el procesamiento: {str(e)}")

# Si se ejecuta este archivo directamente, levanta el servidor localmente en el puerto 8000
if __name__ == "__main__":
    uvicorn.run("app.api:app", host="0.0.0.0", port=3018, reload=True, timeout_keep_alive=300)
