# Walkthrough: Conversión a Servicio REST

He completado la migración del orquestador de asientos contables a un servicio REST utilizando **FastAPI**. El sistema ahora permite recibir tramas de datos JSON directamente desde un frontend, procesarlas, validarlas y enviarlas a SAP Business One.

## Cambios Realizados

### 1. Nueva API REST ([app/api.py](file:///c:/Users/user29/Documents/GitHub/job_orchestador_journal_entires/app/api.py))
Se ha implementado un servidor web que expone el endpoint:
- `POST /api/v1/journal-entries/process`
- Soporta **CORS** para peticiones desde el navegador.
- Documentación automática en `/docs` (Swagger).

### 2. Procesamiento de Payloads Masivos ([app/main.py](file:///c:/Users/user29/Documents/GitHub/job_orchestador_journal_entires/app/main.py))
Se añadieron funciones para:
- Recibir un array plano de objetos JSON.
- Agrupar automáticamente por `JdtNum` (Número de asiento).
- Validar que cada asiento esté balanceado (Debe = Haber) antes de intentar enviarlo.
- Retornar un JSON de respuesta con el conteo de éxitos y errores.

### 3. Documentación y Despliegue
- Se creó [API_DOCUMENTATION.md](file:///c:/Users/user29/Documents/GitHub/job_orchestador_journal_entires/API_DOCUMENTATION.md) con la lógica de negocio y los pasos para poner el servidor en producción (usando Uvicorn, PM2 o como Servicio de Windows).
- Se actualizó [requirements.txt](file:///c:/Users/user29/Documents/GitHub/job_orchestador_journal_entires/requirements.txt) con las nuevas dependencias.

## Verificación

1. **Estructura de Datos:** El sistema separa correctamente cabecera y detalle de una lista plana.
2. **Seguridad:** Se incluyó middleware de CORS para evitar bloqueos del navegador.
3. **Resiliencia:** Mantiene el uso de Circuit Breaker y Rate Limiting para no saturar SAP.

Para iniciar el servicio, ejecuta:
```bash
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```
