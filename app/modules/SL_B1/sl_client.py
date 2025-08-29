from __future__ import annotations
import requests
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
        self.cookie: Optional[str] = None

    def _url(self, path: str) -> str:
        # print(f"{self.base_url}{path}")
        return f"{self.base_url}{path}"

    def login(self):
        # print(f" CompanyDB: {self.company_db},            UserName: {self.user_name},            Password: {self.password}")
        
        r = self.s.post(self._url("/Login"), json={
            "CompanyDB": self.company_db,
            "UserName": self.user_name,
            "Password": self.password
        }, timeout=self.timeout)
        if r.status_code != 200:
            raise SLAuthError(f"Login failed: {r.status_code} {r.text}")
        ck = r.headers.get("Set-Cookie")
        if ck: self.cookie = ck

    def request(self, method: str, path: str, *, json=None, params=None, headers=None):
        if not self.cookie:
            self.login()
        hdrs = {"Content-Type": "application/json"}
        if self.cookie: hdrs["Cookie"] = self.cookie
        if headers: hdrs.update(headers)

        r = self.s.request(method, self._url(path), json=json, params=params, headers=hdrs, timeout=self.timeout)
        if r.status_code == 401:  # sesión vencida → relogin y reintenta 1 vez
            self.login()
            hdrs["Cookie"] = self.cookie or ""
            r = self.s.request(method, self._url(path), json=json, params=params, headers=hdrs, timeout=self.timeout)

        if r.status_code >= 400:
            try:
                raise SLRequestError(r.status_code, r.json())
            except ValueError:
                raise SLRequestError(r.status_code, r.text)

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
        print(payload)
        return self.request("POST", "/JournalEntries", json=payload)
