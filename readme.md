# SAP Business One Journal Entries Orchestrator (Jobs_JE)

Este proyecto es un orquestador automatizado diseñado para procesar y cargar asientos contables (**Journal Entries**) de manera masiva en **SAP Business One** a través del **Service Layer** (OData API). 

Está optimizado para manejar grandes volúmenes de datos (más de 10k registros) sin comprometer la estabilidad del sistema ni la integridad de la base de datos contable.

## 🚀 Características Principales

*   **Carga Fragmentada (Chunked Batching)**: Divide automáticamente miles de registros en mini-lotes manejables (ej. 20 asientos por petición) para evitar errores de timeout o desbordamiento de memoria.
*   **Validación de Balanceo (D=C)**: No permite el envío de asientos cuyas sumas de Débito y Crédito no cuadren perfectamente (tolerancia ajustable).
*   **Integración Robusta**: Implementa patrones de **Circuit Breaker** (para detener el proceso ante errores críticos) y **Rate Limiting** (para respetar los límites de carga del servidor).
*   **Procesamiento de Excel Eficiente**: Utiliza lectura por trozos para manejar archivos `.xlsx` pesados.
*   **Caché de Cuentas**: Sistema inteligente de caché para reducir las consultas de validación de cuentas contables a SAP.
*   **Trazabilidad Total**: Genera registros detallados en formato JSON sobre el éxito o fracaso de cada operación.

## 📂 Estructura del Proyecto

```text
Jobs_JE/
├── app/
│   ├── main.py             # Entrada principal de la lógica de procesamiento.
│   ├── poster.py           # Orquestador de envíos a SAP (Maneja Batch y Chunks).
│   ├── excel_reader.py     # Lector optimizado de archivos Excel.
│   ├── batch_builder.py    # Constructor de peticiones multipart/mixed.
│   ├── validators.py       # Limpieza y validación de tipos de datos.
│   ├── accounts_repo.py    # Gestión de Plan de Cuentas y Caché.
│   └── config.py           # Gestión centralizada de variables de entorno.
├── assets/                 # Depósito de los archivos Excel a procesar.
├── out/                    # Resultados de ejecución y reportes en JSON.
├── scheduler.py            # Script encargado de programar las tareas diarias.
└── requirements.txt        # Dependencias de Python necesarias.
```

## ⚙️ Configuración (.env)

El proyecto requiere un archivo `.env` en la raíz con los siguientes campos:

### Conexión a SAP Service Layer
*   `SL_BASE_URL`: URL del Service Layer (ej: `https://servidor:50000/b1s/v2/`).
*   `CompanyDB`: Base de datos de la compañía.
*   `user_name`: Usuario de SAP (con permisos de Journal Entries).
*   `Password`: Contraseña del usuario.

### Configuración de Archivos Excel
*   `ASSETS_DIR`: Directorio donde están los archivos (default: `assets`).
*   `FILE_CABECERA`: Nombre del archivo Excel con las cabeceras.
*   `FILE_DETALLE`: Nombre del archivo Excel con las líneas de detalle.
*   `SHEET_NAME_CABECERA`: Nombre de la hoja de cabeceras.
*   `SHEET_NAME_DETALLE`: Nombre de la hoja de detalles.

### Rendimiento y Límites
*   `SL_RPS`: Peticiones por segundo máximas permitidas (default: 3).
*   `SL_CONCURRENCY`: Número de hilos simultáneos (default: 1).
*   `CHUNK_SIZE`: Tamaño de los sub-lotes del batch (default: 20).

## 🛠️ Instalación y Uso

### 1. Preparar el entorno
```bash
python -m venv venv
venv\Scripts\activate  # En Windows
pip install -r requirements.txt
```

### 2. Ejecución Manual
Para realizar un proceso de carga inmediato:
```bash
python -m app.main
```

### 3. Ejecución Programada (Modo Service)
Para mantener el orquestador corriendo y que procese los archivos cada cierto tiempo (ej: cada 5 horas):
```bash
python scheduler.py
```

## 🛡️ Notas de Seguridad
*   **Dry Run**: En `app/main.py`, se recomienda configurar `dry_run=True` en las primeras pruebas para visualizar qué se enviaría sin afectar la contabilidad real.
*   **Circuit Breaker**: Si fallan más de 8 peticiones consecutivas, el sistema se detendrá temporalmente por seguridad.