import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import json
from dotenv import load_dotenv
from app.api import app
from fastapi.testclient import TestClient

load_dotenv()
client = TestClient(app)

with open("app.http", "r", encoding="utf-8") as f:
    lines = f.readlines()

payload_str = ""
capture = False
for line in lines:
    if line.strip().startswith("[{"):
        capture = True
    if capture:
        payload_str += line

payload = json.loads(payload_str)

print("Enviando request a FastAPI...")
response = client.post("/api/asientos", json=payload)

print(f"Status Code FastAPI: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
