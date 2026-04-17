import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
from dotenv import load_dotenv
from app.modules.SL_B1.sl_client import ServiceLayerClient
from app.batch_builder import build_batch_request

load_dotenv()
sl = ServiceLayerClient(
    base_url=os.getenv("SL_BASE_URL"),
    company_db=os.getenv("CompanyDB"),
    user_name=os.getenv("user_name"),
    password=os.getenv("Password"),
    timeout=30_000,
)

sl.login()

payload = {
    "ReferenceDate": "20251231",
    "Memo": "Test batch format",
    "JournalEntryLines": [
        {"Debit": 10, "Credit": 0, "AccountCode": "91291101"},
        {"Debit": 0, "Credit": 10, "AccountCode": "91291101"}
    ]
}

# test 1: path "/b1s/v1/JournalEntries"
requests = [{
    "method": "POST",
    "path": "/b1s/v1/JournalEntries",
    "body": payload,
    "content_id": "1"
}]

batch_body, headers, cids = build_batch_request(requests)
resp1 = sl.request("POST", "/$batch", data=batch_body, headers=headers)
print("TEST 1 (/b1s/v1/JournalEntries):")
print(resp1.status_code)
print(resp1.headers.get("Content-Type"))
try:
    print(resp1.text)
except Exception:
    pass

# test 2: path "JournalEntries"
requests2 = [{
    "method": "POST",
    "path": "JournalEntries",
    "body": payload,
    "content_id": "1"
}]

batch_body2, headers2, cids2 = build_batch_request(requests2)
resp2 = sl.request("POST", "/$batch", data=batch_body2, headers=headers2)
print("TEST 2 (JournalEntries):")
print(resp2.status_code)
print(resp2.headers.get("Content-Type"))
try:
    print(resp2.text)
except Exception:
    pass

