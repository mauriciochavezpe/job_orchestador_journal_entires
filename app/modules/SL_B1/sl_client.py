import requests
import urllib3
import os
import logging
try:
    from hdbcli import dbapi
    HDB_AVAILABLE = True
except ImportError:
    HDB_AVAILABLE = False

# Deshabilitar advertencias de SSL inseguro (necesario cuando verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from typing import Any, Optional

class SLAuthError(Exception): ...
class SLRequestError(Exception):
    def __init__(self, status: int, payload: Any):
        self.status = status
        self.payload = payload
        msg = f"SL error {status}: {payload}"
        try:
            val = payload.get("error", {}).get("message", {}).get("value")
            if val: msg = f"SL error {status}: {val}"
        except Exception:
            pass
        super().__init__(msg)

class ServiceLayerClient:
    def __init__(self, base_url: str, company_db: str, user_name: str, password: str, timeout: int = 30_000):
        self.base_url = base_url.rstrip("/")
        self.company_db = company_db
        self.user_name = user_name
        self.password = password
        self.timeout = timeout / 1000.0  # seconds
        self.s = requests.Session()
        self.s.verify = False  # Ignorar validación de certificados SSL
        self.cookie: Optional[str] = None
        
        # Datos para conexión directa a DB (opcional)
        self.db_conn = None
        self.db_host = os.getenv("DB_HOST")
        self.db_port = os.getenv("DB_PORT")
        self.db_user = os.getenv("DB_USER")
        self.db_pass = os.getenv("DB_PASS")
        self.db_schema = os.getenv("DB_SCHEMA")
        self.db_database = os.getenv("DB_HANA")

    def _url(self, path: str) -> str:
        # print(f"{self.base_url}{path}")
        return f"{self.base_url}{path}"

    def login(self):
        # print(f" CompanyDB: {self.company_db},            UserName: {self.user_name},            Password: {self.password}")
        
        r = self.s.post(self._url("/Login"), json={
            "CompanyDB": self.company_db,
            "UserName": self.user_name,
            "Password": self.password
        }, timeout=self.timeout, verify=False)
        if r.status_code != 200:
            raise SLAuthError(f"Login failed: {r.status_code} {r.text}")
        ck = r.headers.get("Set-Cookie")
        if ck: self.cookie = ck

    def request(self, method: str, path: str, *, json=None, data=None, params=None, headers=None):
        if not self.cookie:
            self.login()
        
        # Default headers. If sending raw data, Content-Type should be in headers.
        hdrs = {}
        if json is not None:
            hdrs["Content-Type"] = "application/json"

        if self.cookie: hdrs["Cookie"] = self.cookie
        if headers: hdrs.update(headers)

        r = self.s.request(method, self._url(path), json=json, data=data, params=params, headers=hdrs, timeout=self.timeout, verify=False)
        if r.status_code == 401:  # sesión vencida → relogin y reintenta 1 vez
            self.login()
            hdrs["Cookie"] = self.cookie or ""
            r = self.s.request(method, self._url(path), json=json, data=data, params=params, headers=hdrs, timeout=self.timeout, verify=False)

        if r.status_code >= 400:
            try:
                raise SLRequestError(r.status_code, r.json())
            except ValueError:
                raise SLRequestError(r.status_code, r.text)

        # For batch responses, we need the raw text and headers
        if 'multipart/mixed' in r.headers.get('Content-Type', ''):
            return r

        try:
            return r.json()
        except ValueError:
            return r.text

    # Endpoints usados
    def get_account(self, code: str):
        return self.request("GET", f"/ChartOfAccounts('{code}')")

    def iter_accounts(self, top: int = 1000):
        skip = 0
        while True:
            data = self.request("GET", "/ChartOfAccounts", params={"$select":"Code,Name","$top":top,"$skip":skip})
            items = data.get("value", []) if isinstance(data, dict) else []
            if not items: break
            for it in items: yield it
            skip += top

    def post_journal_entries(self, payload: dict):
        # print(payload)
        return self.request("POST", "/JournalEntries", json=payload)

    def post_batch(self, payload: str, headers: dict):
        """POST a batch request. Content-Type must be handled by caller."""
        # print(f"batch: {payload}")
        return self.request("POST", "/$batch", json=payload, headers=headers)

    def _get_db_conn(self):
        """Inicializa o retorna la conexión actual a la base de datos."""
        if not HDB_AVAILABLE:
            logging.error("Librería hdbcli no está instalada.")
            return None
        
        if self.db_conn is None or not self.is_db_connected():
            try:
                if not (self.db_host and self.db_user and self.db_pass):
                    logging.warning("Faltan credenciales de DB en el archivo .env")
                    return None
                
                self.db_conn = dbapi.connect(
                    address=self.db_host,
                    port=int(self.db_port or 30015),
                    user=self.db_user,
                    password=self.db_pass,
                    databaseName=self.db_database,
                    currentSchema=self.db_schema,
                    encrypt='true',
                    sslValidateCertificate='false'
                )
                logging.info(f"Conexión exitosa a SAP HANA: {self.db_host}")
            except Exception as e:
                logging.error(f"Error conectando a la DB: {e}")
                self.db_conn = None
        return self.db_conn

    def is_db_connected(self) -> bool:
        if self.db_conn is None: return False
        try:
            return self.db_conn.isconnected()
        except:
            return False

    def query_sql(self, sql: str) -> list[dict]:
        """
        Ejecuta una query SQL directa via HANA (hdbcli).
        """
        conn = self._get_db_conn()
        if not conn:
            logging.error("No hay conexión a la base de datos disponible.")
            return []

        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            cols = [desc[0] for desc in cursor.description]
            results = [dict(zip(cols, row)) for row in cursor.fetchall()]
            cursor.close()
            return results
        except Exception as e:
            logging.error(f"Error en query SQL nativa: {e}")
            return []

