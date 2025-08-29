# app/main.py (fragmento)
from pathlib import Path
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
from datetime import datetime
from app.config import Config
from app.excel_reader import read_sheet_in_chunks
from app.accounts_repo import AccountsRepo
from app.poster import JournalPoster, CircuitBreaker
from decimal import Decimal
from app.modules.SL_B1.sl_client import ServiceLayerClient
from app.response_json import _dump_json_result
cfg = Config()

# 1) armar items balanceados
def collect_items_for_post():
    # indexa CAB por JdtNum (ajusta si tu llave es otra)
    cab_by_key = {}
    for batch in read_sheet_in_chunks(cfg.cab_path, sheet_name=cfg.sheet_cab, chunk_size=1000, skip_rows=cfg.skip_rows, header_row=1):
        for it in batch:
            c = it["data"]
            key = str(c.get("jdtnum") or c.get("JdtNum") or "")
            if not key: continue
            cab_by_key[key] = {
                "JdtNum":        c.get("JdtNum") or c.get("jdtnum"),
                "Memo":          c.get("Memo") or c.get("memo"),
                "TaxDate":       c.get("TaxDate") or c.get("taxdate"),
                "ReferenceDate": c.get("ReferenceDate") or c.get("referencedate"),
                "DueDate":       c.get("DueDate") or c.get("duedate"),
                "ProjectCode":   c.get("ProjectCode") or c.get("projectcode") or '',
                "TransactionCode": c.get("TransactionCode") or c.get("transactioncode") or "",
                "Reference2":    c.get("Reference2") or c.get("reference2") or ''
            }

    groups = {}
    sums = {}
    index2= 0
    # retorna lote de informacion de {chunk_size}
    for batch in read_sheet_in_chunks(cfg.det_path, sheet_name=cfg.sheet_det, chunk_size=100, skip_rows=cfg.skip_rows, header_row=1):
        for it in batch:
            index2 +=1
            print(f" datos del btch {it}")
            d = it["data"]
            key = str(d.get("parentkey") or d.get("ParentKey") or "")
            if not key: continue

            line = {
                "AccountCode": d.get("AccountCode") or d.get("accountcode"),
                "LineMemo": d.get("LineMemo") or d.get("linememo") or "",
                "DueDate": d.get("DueDate") or d.get("duedate") or '',
                "TaxDate": d.get("TaxDate") or d.get("taxdate") or '',
                "VatDate": d.get("VatDate") or d.get("vatdate") or '',
                "U_INFOPE01": d.get("U_INFOPE01") or d.get("u_infope01") or '',
                "U_INFOPE02": d.get("U_INFOPE02") or d.get("u_infope02") or '',
                "ReferenceDate2": d.get("ReferenceDate2") or d.get("referencedate2") or '',
                "FCCurrency": d.get("FCCurrency") or d.get("fccurrency") or '',
                "Debit":  float(d.get("Debit")  or d.get("debit")  or 0.0) ,
                "Credit": float(d.get("Credit") or d.get("credit") or 0.0) ,
                "Reference2": d.get("Reference2") or d.get("reference2") or '',
                "CostingCode": d.get("CostingCode") or d.get("costingcode") or '',
                "ProjectCode": d.get("ProjectCode") or d.get("projectcode") or '',
                "Reference1": d.get("Reference1") or d.get("reference1") or '',
            } 
            line["ShortName"] = d.get("ShortName") or d.get("shortname") or line["AccountCode"]
            # print(f"listDetl {line}")
            groups.setdefault(key, []).append(line)
            s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
            s["d"] += Decimal(str(line["Debit"]))
            s["c"] += Decimal(str(line["Credit"]))
            sums[key] = s
    # print(f"total {len(batch)}")

    # print(f"total {cab_by_key}")
    # filtrar balanceados
    TOL = Decimal("0.000001")
    items = []
    for key, lines in groups.items():
        s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
        print(f"d: {s['d']} | c: {s['c']}")
        if abs(s["d"] - s["c"]) <= TOL:
            cab = cab_by_key.get(key)
            if cab:
                items.append({"key": key, "cab": cab, "lines": lines})
            else:
                print(f"[WARN] sin CAB para {key}, se omite")
        else:
            print(f"[SKIP] {key} no balanceado d={s['d']} c={s['c']}")
    # print(f"items {cab_by_key}")
    return items

# 2) postear (empieza en dry_run=True)
def post_to_sl():
    import os, time
    sl = ServiceLayerClient(
        base_url=os.getenv("SL_BASE_URL"),
        company_db=os.getenv("CompanyDB"),
        user_name=os.getenv("user_name"),
        password=os.getenv("Password"),
        timeout=30_000,
    )
    repo = AccountsRepo(sl, ttl_seconds=3600, max_items=20000)
    repo.cache.clear() # <--- Limpiar cache al iniciar
    # repo.preload_all()  # opcional

    rps = float(os.getenv("SL_RPS", "3"))
    conc = int(os.getenv("SL_CONCURRENCY", "1"))

    poster = JournalPoster(
        sl, repo,
        rps=rps, concurrency=conc,
        local_currency="PEN",
        dry_run=True,  # ← prueba primero SIN postear
        breaker=CircuitBreaker(enabled=True, fail_threshold=8, cool_down_sec=30)
    )

 # ▶ Construye asientos listos para postear
    started = time.time()
    started_iso = datetime.now().isoformat(timespec="seconds")
    items = collect_items_for_post()  # [{ key, cab, lines }, ...]
    print(f"items {items}")
    res = poster.post_all(items)
    finished = time.time()
    finished_iso = datetime.now().isoformat(timespec="seconds")
    result_doc = {
        "job": {
            "started_at": started_iso,
            "finished_at": finished_iso,
            "duration_sec": round(finished - started, 3),
            "rps": rps,
            "concurrency": conc,
            "dry_run": poster.dry_run,
            # "local_currency": "PEN",
        },
        "sources": {
            "cab_path": str(cfg.cab_path),
            "det_path": str(cfg.det_path),
            "sheet_cab": cfg.sheet_cab,
            "sheet_det": cfg.sheet_det,
        },
        "counts": {
            "items": len(items),
            "ok": res["ok"],
            "fail": res["fail"],
        },
        "results": res["results"],  # [{key, ok, res|err, payload}, ...]
    }
    
    project_root = Path(__file__).resolve().parent.parent
    out_path =    _dump_json_result(result_doc, out_dir=project_root / "out")
    # print("file",out_path)
# def generate_json(payload):
    
if __name__ == "__main__":
    # primero haz un dry-run
    post_to_sl()
    # cuando veas que el payload está bien, cambia a dry_run=False:
