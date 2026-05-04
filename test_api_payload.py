import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import json
from dotenv import load_dotenv

load_dotenv()
from app.main import post_payload_to_sl

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

print("Procesando payload directamente...")
response = post_payload_to_sl(payload)

print(json.dumps(response, indent=2))
