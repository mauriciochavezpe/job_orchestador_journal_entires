# Documentación Técnica: API de Orquestador de Asientos Contables

### Esta guía detalla la configuración técnica, arquitectura y despliegue del servicio para procesar asientos contables en SAP Business One.

---

## 1. Arquitectura del Servicio

El sistema está diseñado para recibir datos masivos desde un frontend y procesarlos de forma segura hacia SAP Service Layer.

*   **Backend:** Python con FastAPI.
*   **Gestor de Procesos:** PM2.
*   **Servidor Web / Reverse Proxy:** Caddy.
*   **Puerto Interno:** 3018.

### Flujo de Datos
1.  **Recepción:** El API recibe un JSON con múltiples líneas (cabecera + detalle).
2.  **Validación:** Agrupa por `JdtNum` y valida que cada asiento esté balanceado (`Debe - Haber = 0`).
3.  **Envío ($batch):** Los asientos válidos se envían a SAP en paquetes de 20 (configurable en `.env`) usando el método `$batch` de Service Layer.

---

## 2. Configuración de Endpoints e Interfaz

Debido a la configuración del Reverse Proxy, todos los recursos están bajo el prefijo `/api/asientos`:

*   **Endpoint Principal (POST):** `https://apiconsultas.llamagas.nubeprivada.biz/api/asientos`
*   **Documentación Interactiva (Swagger):** `https://apiconsultas.llamagas.nubeprivada.biz/api/asientos/docs`
*   **Documentación Alternativa (Redoc):** `https://apiconsultas.llamagas.nubeprivada.biz/api/asientos/redoc`

---

## 3. Guía de Administración (PM2)

El servicio corre bajo el nombre **`sap-journal-api`**.

*   **Iniciar:** `pm2 start ecosystem.config.js`
*   **Reiniciar:** `pm2 restart sap-journal-api`
*   **Ver Logs:** `pm2 logs sap-journal-api`
*   **Estado:** `pm2 status`

El archivo `ecosystem.config.js` está configurado para usar el puerto **3018** y el comando `python -m uvicorn`.

---

## 4. Configuración del Reverse Proxy (Caddy)

Para que el dominio sea accesible desde internet, se utiliza la siguiente regla en el archivo Caddyfile:

```caddy
route /api/asientos* {
    reverse_proxy localhost:3018
}
```

---

## 5. Reglas de Uso para el Frontend

Para que el servidor procese correctamente la información, el frontend debe seguir estas normas:

### Estructura del JSON
Se debe enviar un **Array plano de objetos**. Cada objeto debe contener:
- Identificador de asiento (ej: `JdtNum` o `ParentKey`).
- Datos de Cabecera (ej: `MemoCab`, `TaxDateCab`).
- Datos de Detalle (ej: `AccountCode`, `Debit`, `Credit`).

> [!IMPORTANT]
> **No fraccionar asientos:** Todas las líneas de un mismo asiento contable (con el mismo `JdtNum`) deben viajar en la **misma petición HTTP**. Si se envían por separado en diferentes peticiones, el sistema marcará el asiento como desbalanceado y lo rechazará por seguridad.

---

## 6. Mantenimiento y Seguridad

1.  **CORS:** La API tiene habilitado CORS para aceptar peticiones desde cualquier origen (`*`). Se recomienda restringirlo a dominios específicos en producción si es necesario.
2.  **Variables de Entorno:** Todas las credenciales de SAP (URL, DB, User, Pass) se gestionan desde el archivo `.env` en la raíz del proyecto.
3.  **Firewall:** El puerto **3018** debe estar abierto en el servidor para permitir la comunicación interna entre el Reverse Proxy y la aplicación.
