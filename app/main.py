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
from app.validators import validate_date2

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
                "Memo":          c.get("Reference1") or c.get("Reference1"),
                "TaxDate":       c.get("TaxDate") or c.get("TaxDate"),
                "ReferenceDate": c.get("ReferenceDate") or c.get("ReferenceDate"),
                "DueDate":       c.get("DueDate") or c.get("DueDate"),
                "ProjectCode":   c.get("ProjectCode") or c.get("projectcode") or '',
                "TransactionCode": c.get("TransactionCode") or c.get("transactioncode") or ""
                # "Reference2":    c.get("Reference2") or c.get("reference2") or ''
            }

    # 2) Agrupar DETALLES por ParentKey
    groups = {}
    sums = {}
    first_detail_row = None
    for batch in read_sheet_in_chunks(cfg.det_path, sheet_name=cfg.sheet_det, chunk_size=100, skip_rows=cfg.skip_rows, header_row=1):
        for it in batch:
            d = it["data"]
            if first_detail_row is None:
                first_detail_row = d
                # print(f"[DEBUG] Primera fila del DETALLE:\n{list(d.keys())}")
                # print(f"[DEBUG] Valores: {d}\n")
            key = str(d.get("parentkey") or d.get("ParentKey") or "")
            if not key: continue

            line = {
                "AccountCode": str(d.get("AccountCode") or d.get("accountcode")),
                "LineMemo": d.get("LineMemo") or d.get("linememo") or "",
                "DueDate": d.get("DueDate") or d.get("duedate") or '',
                "TaxDate": d.get("TaxDate") or d.get("taxdate") or '',
                "VatDate": d.get("VatDate") or d.get("vatdate") or '',
                "U_INFOPE01": d.get("U_INFOPE01") or d.get("u_infope01") or '',
                "U_INFOPE02": d.get("U_INFOPE02") or d.get("u_infope02") or '',
                "ReferenceDate2": d.get("ReferenceDate2") or d.get("referencedate2") or '',
                "FCCurrency": d.get("FCCurrency") or d.get("fccurrency") or 'PEN',
                "Debit":  float(d.get("Debit")  or d.get("debit")  or 0.0) ,
                "Credit": float(d.get("Credit") or d.get("credit") or 0.0) ,
                "Reference2": d.get("Reference2") or d.get("reference2") or '',
                "OcrCode1":  d.get("OcrCode1") or '',
                "OcrCode2":  d.get("OcrCode2") or '',
                "OcrCode3":  d.get("OcrCode3") or '',
                "OcrCode4":  d.get("OcrCode4") or '',
                "OcrCode5":  d.get("OcrCode5") or '',
                "ProjectCode": d.get("ProjectCode") or d.get("projectcode") or '',
                "Reference1": d.get("Reference1") or d.get("reference1") or '',
                "ShortName": d.get("ShortName") or d.get("shortname") or '',
                # Datos de cabecera desde línea
                "JdtNum": d.get("JdtNum") or d.get("jdtnum") or '',
                "Memo": d.get("Memo") or d.get("memo") or '',
                #"CabTaxDate": validate_date2(d.get("CabTaxDate") or d.get("cabtaxdate") or d.get("TaxDate") or '')[1],
                #"CabReferenceDate": validate_date2(d.get("CabReferenceDate") or d.get("cabreferencedate") or d.get("ReferenceDate") or '')[1],
                #"CabDueDate": validate_date2(d.get("CabDueDate") or d.get("cabduedate") or d.get("DueDate") or '')[1],
                #"TransactionCode": d.get("TransactionCode") or d.get("transactioncode") or '',
            }
            
            groups.setdefault(key, []).append(line)
            s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
            s["d"] += Decimal(str(line["Debit"]))
            s["c"] += Decimal(str(line["Credit"]))
            sums[key] = s

    # 3) Filtrar solo asientos balanceados y extraer cabecera de primera línea
    TOL = Decimal("0.000001")
    items = []
    for key, lines in groups.items():
        s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
        if abs(s["d"] - s["c"]) <= TOL:
            # Extraer cabecera de la primera línea
            first_line = lines[0]
            cab = {
                "JdtNum": first_line.get("JdtNum") or key,
                "Memo": first_line.get("Memo") or f"Asiento {key}",
                "TaxDate": first_line.get("CabTaxDate") or '',
                "ReferenceDate": first_line.get("CabReferenceDate") or '',
                "DueDate": first_line.get("CabDueDate") or '',
                "ProjectCode": first_line.get("ProjectCode") or '',
                "TransactionCode": first_line.get("TransactionCode") or '',
                "Reference2": first_line.get("Reference2") or ''
            }
            if not items:  # Print solo del primer asiento
                # print(f"[DEBUG] Cabecera extraída para asiento {key}:\n{cab}\n")
                
                items.append({"key": key, "cab": cab, "lines": lines})
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
    # print(f"-> Proceso terminado. Exitosos: {res['ok']}, Fallidos: {res['fail']}")


def process_payload_for_post(payload: list, sl=None) -> list:
    """
    Procesa un payload JSON (lista de diccionarios planos) enviado desde el frontend.
    Cada diccionario contiene información de Cabecera y Detalle.
    Si se pasa `sl` (ServiceLayerClient), se consulta OHEM para enriquecer
    cada línea con U_RML_CECO1-4 y EmployeeID desde el empleado asociado al CardCode.
    """
    cab_by_key = {}
    groups = {}
    sums = {}
    # Caché de OHEM por CardCode para no repetir el SELECT
    ohem_cache: dict = {}

    for row in payload:
        # ── Enriquecer con datos OHEM (solo si ShortName existe) ──────────────
        if sl is not None:
            card_code = row.get("ShortName") or ""
            if card_code:  # ShortName no es obligatorio; si no hay, se omite el lookup
                if card_code not in ohem_cache:
                    try:
                        # Usar el schema de la configuración o el hardcoded como fallback
                        db_schema = getattr(sl, 'db_schema', None) or "LLAMA_GAS_0326"
                        
                        sql = (
                            f"SELECT H1.\"U_CE_PVAS\", H1.\"U_RML_CECO1\", H1.\"U_RML_CECO2\","
                            f" H1.\"U_RML_CECO3\", H1.\"U_RML_CECO4\", H1.\"CostCenter\", H1.\"Code\""
                            f" FROM \"{db_schema}\".\"OCRD\" O"
                            f" INNER JOIN \"{db_schema}\".\"OHEM\" H1"
                            f" ON O.\"CardCode\"=H1.\"U_CE_PVAS\""
                            f" WHERE O.\"CardCode\"='{card_code}'"
                        )
                        print(f"[DEBUG SQL] Consultando OHEM para: {card_code} en schema: {db_schema}")
                        
                        rows_ohem = sl.query_sql(sql)
                        ohem_cache[card_code] = rows_ohem[0] if rows_ohem else {}
                        if not rows_ohem:
                            print(f"[OHEM] No hay data para CardCode={card_code}")
                        else:
                            print(f"[OHEM] CardCode={card_code} -> {ohem_cache[card_code]}")
                    except Exception as e:
                        print(f"[WARN] OHEM lookup falló para {card_code}: {e}")
                        ohem_cache[card_code] = {}
                # Inyectar OcrCode* solo si OHEM retornó valor y el row no los trae
                ohem = ohem_cache.get(card_code, {})
                # VALIDAMOS SI EXISTE un CostCenter válido en OHEM
                if ohem and ohem.get("CostCenter"):
                    # canal / ProfitCode
                    row["ProfitCode"] = ohem.get("U_RML_CECO1") or ""
                    # OcrCode (centros de costo y dimensiones)
                    row["OcrCode1"] = ohem.get("U_RML_CECO1") or ""
                    row["OcrCode2"] = ohem.get("U_RML_CECO2") or ""
                    row["OcrCode3"] = ohem.get("U_RML_CECO3") or ""
                    row["OcrCode4"] = ohem.get("U_RML_CECO4") or ""
                    row["OcrCode5"] = ohem.get("CostCenter") or ""
                # empleado
        # ─────────────────────────────────────────────────────────────────────────

        # Extraer llave común
        key = str(row.get("jdtnum") or row.get("JdtNum") or row.get("parentkey") or row.get("ParentKey") or "")
        if not key: continue

        # Extraer cabecera asumiendo que viene en cada fila o en la primera
        if key not in cab_by_key:
            cab_by_key[key] = {
                "JdtNum": row.get("JdtNum") or row.get("jdtnum") or key,
                "Memo": row.get("MemoCab") or row.get("Reference1") or row.get("Reference1") or "",
                "DueDate": row.get("DueDate") or row.get("DueDate") or row.get("DueDate") or getattr(row, 'DueDate', ''),
                "VatDate": row.get("VatDate") or row.get("VatDate") or row.get("VatDate") or getattr(row, 'VatDate', ''),
                "TaxDate": row.get("TaxDate") or row.get("taxdate") or row.get("VatDate") or getattr(row, 'taxdate', ''),
                "ReferenceDate": row.get("ReferenceDate") or row.get("referencedate") or row.get("VatDate") or getattr(row, 'referencedate', ''),
                #"ProjectCode": row.get("ProjectCodeCab") or row.get("projectcodecab") or row.get("ProjectCode") or row.get("projectcode") or '',
                "TransactionCode": row.get("TransactionCode") or row.get("transactioncode") or "",
                #"Reference2": row.get("Reference2Cab") or row.get("reference2cab") or row.get("Reference2") or row.get("reference2") or ''
            }
        # print(f"[DEBUG] Procesando línea con key={key}: {row}")
        # Extraer línea de detalle
        acc = str(row.get("AccountCode") or row.get("accountcode") or "")
        if acc:
            line = {
                "AccountCode": acc,
                #"LineNum": row.get("LineNum") or row.get("linenum") or '',
                "LineMemo": row.get("LineMemo") or row.get("linememo") or "",
                "DueDate":  row.get("TaxDate") or row.get("TaxDate") or getattr(row, 'TaxDate', ''),
                "TaxDate":  row.get("TaxDate") or row.get("TaxDate") or getattr(row, 'TaxDate', ''),
                "VatDate":  row.get("TaxDate") or row.get("TaxDate") or getattr(row, 'TaxDate', ''),
                "U_INFOPE01": row.get("U_INFOPE01") or row.get("u_infope01") or '',
                "U_INFOPE02": row.get("U_INFOPE02") or row.get("u_infope02") or '',
                "ReferenceDate": row.get("ReferenceDate") or row.get("referencedate") or '',
                "FCCurrency": row.get("FCCurrency") or row.get("fccurrency") or 'PEN',
                "Debit": float(row.get("Debit") or row.get("debit") or 0.0),
                "Credit": float(row.get("Credit") or row.get("credit") or 0.0),
                "Reference2": row.get("Reference2Line") or row.get("reference2line") or row.get("Reference2") or row.get("reference2") or '',
                "CostingCode" : row.get("ProfitCode") or "",
                "CostingCode2" : row.get("OcrCode2") or "",
                "CostingCode3" : row.get("OcrCode3") or "",
                "CostingCode4" : row.get("OcrCode4") or "",
                "CostingCode5" : row.get("OcrCode5") or ""
            }

            # Campos opcionales: solo se agregan si tienen valor
            for i in range(1, 6):
                val = row.get(f"OcrCode{i}")
                if val: line[f"OcrCode{i}"] = val
            # ProfitCode (viene de OHEM U_RML_CECO1 o del payload)
            if row.get("ProfitCode"):
                line["ProfitCode"] = row["ProfitCode"]
            if row.get("ShortName") or row.get("shortname"):
                line["ShortName"] = row.get("ShortName") or row.get("shortname")
            if row.get("ProjectCode") or row.get("projectcode"):
                line["ProjectCode"] = row.get("ProjectCode") or row.get("projectcode")
            if row.get("Reference1") or row.get("reference1"):
                line["Reference1"] = row.get("Reference1") or row.get("reference1")
            if row.get("EmployeeID") or row.get("employeeid"):
                line["EmployeeID"] = row.get("EmployeeID") or row.get("employeeid")
            if key not in groups:
                groups[key] = []
            groups[key].append(line)
            s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
            s["d"] += Decimal(str(line["Debit"]))
            s["c"] += Decimal(str(line["Credit"]))
            sums[key] = s

            # print(f"[DEBUG] Línea procesada para key={key}: {line}")
    # Filtrar solo balanceados
    TOL = Decimal("0.000001")
    items = []
    for key, lines in groups.items():
        s = sums.get(key) or {"d": Decimal(0), "c": Decimal(0)}
        if abs(s["d"] - s["c"]) <= TOL:
            cab = cab_by_key.get(key)
            items.append({"key": key, "cab": cab, "lines": lines})
        else:
            print(f"[SKIP] Asiento {key} no balanceado (D={s['d']}, C={s['c']}).")

    return items


def post_payload_to_sl(payload: list) -> dict:
    """
    Procesa un payload JSON plano enviado por REST API y lo envía al Service Layer.
    """
    sl = ServiceLayerClient(
        base_url=os.getenv("SL_BASE_URL"),
        company_db=os.getenv("CompanyDB"),
        user_name=os.getenv("user_name"),
        password=os.getenv("Password"),
        timeout=30_000,
    )
    
    repo = AccountsRepo(sl, ttl_seconds=3600, max_items=20000)
    repo.cache.clear() 

    rps = float(os.getenv("SL_RPS", "3"))
    conc = int(os.getenv("SL_CONCURRENCY", "1"))
    chunk_size = int(os.getenv("CHUNK_SIZE", "20"))

    poster = JournalPoster(
        sl, repo,
        rps=rps, concurrency=conc,
        local_currency="PEN",
        dry_run=False,
        breaker=CircuitBreaker(enabled=True, fail_threshold=8, cool_down_sec=30)
    )

    started = time.time()
    started_iso = datetime.now().isoformat(timespec="seconds")
    
    items = process_payload_for_post(payload, sl=sl)
    res = poster.post_all(items, chunk_size=chunk_size)
    
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
            "chunk_size": chunk_size
        },
        "counts": {
            "items_procesados": len(items),
            "exitosos": res["ok"],
            "fallidos": res["fail"],
        },
        "results": res["results"],
    }
    
    _dump_json_result(result_doc, out_dir=PROJECT_ROOT / "out")
    # print(f"-> API Proceso terminado. Exitosos: {res['ok']}, Fallidos: {res['fail']}")
    
    return result_doc

if __name__ == "__main__":
    post_to_sl()