"""
app/main.py
Módulo principal para la ejecución del orquestador de Asientos Contables.
Este script se encarga de leer los archivos Excel, agrupar las cabeceras con sus
detalles, validar el balanceo contable y enviar los datos a SAP Business One.
"""

from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal
import os
import time

# Configuración de rutas y variables de entorno
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from app.config import Config
from app.excel_reader import read_sheet_in_chunks
from app.accounts_repo import AccountsRepo
from app.poster import JournalPoster, CircuitBreaker
from app.modules.SL_B1.sl_client import ServiceLayerClient
from app.response_json import _dump_json_result
from .validators import validate_date2

cfg = Config()

def collect_items_for_post():
    """
    Lee los archivos Excel de Cabecera y Detalle, los correlaciona mediante una llave
    común (jdtnum) y filtra solo aquellos asientos que están contablemente balanceados 
    (Suma Débito = Suma Crédito).
    
    Returns:
        list: Una lista de diccionarios, cada uno con los datos de un asiento completo.
    """
    # 1) Indexar CABECERAS por JdtNum para búsqueda rápida
    cab_by_key = {}
    for batch in read_sheet_in_chunks(cfg.cab_path, sheet_name=cfg.sheet_cab, chunk_size=1000, skip_rows=cfg.skip_rows, header_row=1):
        for it in batch:
            c = it["data"]
            key = str(c.get("jdtnum") or c.get("JdtNum") or "")
            if not key: continue
            cab_by_key[key] = {
                "JdtNum":        c.get("JdtNum") or c.get("jdtnum"),
                "Memo":          c.get("Memo") or c.get("memo"),
                "TaxDate":       validate_date2(c.get("TaxDate") or c.get("taxdate"))[1],
                "ReferenceDate": validate_date2(c.get("ReferenceDate") or c.get("referencedate"))[1],
                "DueDate":       validate_date2(c.get("DueDate") or c.get("duedate"))[1],
                "ProjectCode":   c.get("ProjectCode") or c.get("projectcode") or '',
                "TransactionCode": c.get("TransactionCode") or c.get("transactioncode") or "",
                "Reference2":    c.get("Reference2") or c.get("reference2") or ''
            }

    # 2) Agrupar DETALLES por ParentKey
    groups = {}
    sums = {}
    for batch in read_sheet_in_chunks(cfg.det_path, sheet_name=cfg.sheet_det, chunk_size=100, skip_rows=cfg.skip_rows, header_row=1):
        for it in batch:
            d = it["data"]
            key = str(d.get("parentkey") or d.get("ParentKey") or "")
            if not key: continue

            line = {
                "AccountCode": str(d.get("AccountCode") or d.get("accountcode")),
                "LineMemo": d.get("LineMemo") or d.get("linememo") or "",
                "DueDate": validate_date2(d.get("DueDate") or d.get("duedate") or '')[1],
                "TaxDate": validate_date2(d.get("TaxDate") or d.get("taxdate") or '')[1],
                "VatDate": validate_date2(d.get("VatDate") or d.get("vatdate") or '')[1],
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
                "ShortName": d.get("ShortName") or d.get("shortname") or ''
            } 
            
            groups.setdefault(key, []).append(line)
            s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
            s["d"] += Decimal(str(line["Debit"]))
            s["c"] += Decimal(str(line["Credit"]))
            sums[key] = s

    # 3) Filtrar solo asientos balanceados y con cabecera existente
    TOL = Decimal("0.000001")
    items = []
    for key, lines in groups.items():
        s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
        if abs(s["d"] - s["c"]) <= TOL:
            cab = cab_by_key.get(key)
            if cab:
                items.append({"key": key, "cab": cab, "lines": lines})
            else:
                print(f"[WARN] Sin cabecera (CAB) para la llave {key}, se omite.")
        else:
            print(f"[SKIP] Asiento {key} no balanceado (D={s['d']}, C={s['c']}).")
            
    return items

def post_to_sl():
    """
    Función principal que orquestra la conexión a SAP Service Layer,
    inicializa el poster y ejecuta la carga de datos.
    """
    # Inicialización del cliente SAP Service Layer
    sl = ServiceLayerClient(
        base_url=os.getenv("SL_BASE_URL"),
        company_db=os.getenv("CompanyDB"),
        user_name=os.getenv("user_name"),
        password=os.getenv("Password"),
        timeout=30_000,
    )
    
    # Repositorio de cuentas con caché
    repo = AccountsRepo(sl, ttl_seconds=3600, max_items=20000)
    repo.cache.clear() 

    rps = float(os.getenv("SL_RPS", "3"))
    conc = int(os.getenv("SL_CONCURRENCY", "1"))
    chunk_size = int(os.getenv("CHUNK_SIZE", "20"))

    # Configuración del póster con Circuit Breaker
    poster = JournalPoster(
        sl, repo,
        rps=rps, concurrency=conc,
        local_currency="PEN",
        dry_run=False,
        breaker=CircuitBreaker(enabled=True, fail_threshold=8, cool_down_sec=30)
    )

    started = time.time()
    started_iso = datetime.now().isoformat(timespec="seconds")
    
    # Recolección y envío
    items = collect_items_for_post()
    res = poster.post_all(items, chunk_size=chunk_size)
    
    finished = time.time()
    finished_iso = datetime.now().isoformat(timespec="seconds")
    
    # Generación de reporte final
    result_doc = {
        "job": {
            "started_at": started_iso,
            "finished_at": finished_iso,
            "duration_sec": round(finished - started, 3),
            "rps": rps,
            "concurrency": conc,
            "dry_run": poster.dry_run,
            "chunk_size": chunk_size
        },
        "sources": {
            "cab_path": str(cfg.cab_path),
            "det_path": str(cfg.det_path),
            "sheet_cab": cfg.sheet_cab,
            "sheet_det": cfg.sheet_det,
        },
        "counts": {
            "items_procesados": len(items),
            "exitosos": res["ok"],
            "fallidos": res["fail"],
        },
        "results": res["results"],
    }
    
    _dump_json_result(result_doc, out_dir=PROJECT_ROOT / "out")
    print(f"-> Proceso terminado. Exitosos: {res['ok']}, Fallidos: {res['fail']}")

if __name__ == "__main__":
    post_to_sl()