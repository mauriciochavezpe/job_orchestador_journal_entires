import os
import logging
from dotenv import load_dotenv
from app.modules.SL_B1.sl_client import ServiceLayerClient

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_connections():
    # 1. Cargar variables de entorno
    load_dotenv()
    print("--- Probando Conexiones ---")
    
    # Datos de SL
    sl_url = os.getenv("SL_BASE_URL")
    sl_db = os.getenv("CompanyDB")
    sl_user = os.getenv("user_name")
    sl_pass = os.getenv("Password")
    
    # Datos de DB
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_database = os.getenv("DB_HANA")
    db_schema = os.getenv("DB_SCHEMA")

    # 2. Probar SAP Service Layer
    print(f"\n[1] Probando Service Layer en: {sl_url}")
    try:
        sl = ServiceLayerClient(sl_url, sl_db, sl_user, sl_pass)
        sl.login()
        print("✅ Login exitoso en Service Layer.")
    except Exception as e:
        print(f"❌ Error en Service Layer: {e}")

    # 3. Probar Conexión Directa SQL (HANA)
    print(f"\n[2] Probando Conexión SQL Directa en: {db_host}:{db_port}")
    try:
        from hdbcli import dbapi
        conn = dbapi.connect(
            address=db_host,
            port=int(db_port or 30015),
            user=db_user,
            password=db_pass,
            databaseName=db_database,
            currentSchema=db_schema,
            encrypt='true',
            sslValidateCertificate='false'
        )
        if conn.isconnected():
            print("✅ Conexión exitosa a SAP HANA.")
            
            # Probar una query simple
            cursor = conn.cursor()
            cursor.execute("SELECT dummy FROM DUMMY")
            res = cursor.fetchone()
            print(f"✅ Query de prueba exitosa (DUMMY): {res}")
            cursor.close()
            conn.close()
        else:
            print("❌ El driver no reportó conexión activa.")
    except ImportError:
        print("❌ Error: hdbcli no está instalado.")
    except Exception as e:
        print(f"❌ Error de autenticación/conexión SQL: {e}")

if __name__ == "__main__":
    test_connections()
