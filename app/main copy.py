# from __future__ import annotations
# import argparse
# from dotenv import load_dotenv
# from .config import Config
# from pathlib import Path
# from .pipeline import process_file
# import os

# # Reglas de ejemplo (ajusta a tus columnas/headers reales)
# rule_CAB = {
#     'jdtnum':       {'name': 'JdtNum',        'type': 'number', 'options': {'required': True}},
#     'memo':         {'name': 'Memo',          'type': 'string', 'options': {'required': True}},
#     'taxdate':      {'name': 'TaxDate',       'type': 'date',   'options': {'required': True, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'referencedate':{'name': 'ReferenceDate', 'type': 'date',   'options': {'required': True, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'duedate':      {'name': 'DueDate',       'type': 'date',   'options': {'required': True, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'projectcode':  {'name': 'ProjectCode',   'type': 'string', 'options': {'required': False}},
#     'reference2':   {'name': 'Reference2',    'type': 'string', 'options': {'required': False}},
#     'reference':    {'name': 'Reference',     'type': 'string', 'options': {'required': False}},
#     'transactioncode': {'name': 'TransactionCode', 'type': 'string', 'options': {'required': False}},
# }

# rule_DET = {
#     'parentkey':    {'name': 'ParentKey',     'type': 'number', 'options': {'required': True}},
#     'linenum':      {'name': 'LineNum',       'type': 'number', 'options': {'required': False}},
#     'accountcode':  {'name': 'AccountCode',   'type': 'string', 'options': {'required': True}},
#     'shortname':    {'name': 'ShortName',     'type': 'string', 'options': {'required': False}},
#     'linememo':     {'name': 'LineMemo',      'type': 'string', 'options': {'required': False}},
#     'duedate':      {'name': 'DueDate',       'type': 'date',   'options': {'required': True, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'taxdate':      {'name': 'TaxDate',       'type': 'date',   'options': {'required': True, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'vatdate':      {'name': 'VatDate',       'type': 'date',   'options': {'required': True, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'u_infope01':   {'name': 'U_INFOPE01',    'type': 'string', 'options': {'required': False}},
#     'u_infope02':   {'name': 'U_INFOPE02',    'type': 'string', 'options': {'required': False}},
#     'referencedate2':{'name': 'ReferenceDate2','type': 'date',  'options': {'required': False, 'formatIn': 'YYYYMMDD', 'formatOut': 'YYYY-MM-DD'}},
#     'fccurrency':   {'name': 'FCCurrency',    'type': 'string', 'options': {'required': False}},
#     'debit':        {'name': 'Debit',         'type': 'number', 'options': {'required': False}},
#     'credit':       {'name': 'Credit',        'type': 'number', 'options': {'required': False}},
#     'reference2':   {'name': 'Reference2',    'type': 'string', 'options': {'required': False}},
#     'costingcode':  {'name': 'CostingCode',   'type': 'string', 'options': {'required': False}},
#     'projectcode':  {'name': 'ProjectCode',   'type': 'string', 'options': {'required': False}},
#     'reference1':   {'name': 'Reference1',    'type': 'string', 'options': {'required': False}},
# }


# def main():
#     project_root = Path(__file__).resolve().parent.parent
#     # dotenv_path = project_root / '.env'
#     load_dotenv()
#     cfg = Config()
#     t = Path(__file__).resolve().parent.parent
#     path_cab= f"{project_root}/{cfg.assets_dir}/{os.getenv("FILE_CABECERA")}"
#     path_det= f"{project_root}/{cfg.assets_dir}/{os.getenv("FILE_DETALLE")}"
#     sheet_cab = os.getenv("SHEET_NAME_CABECERA")
#     sheet_det = os.getenv("SHEET_NAME_DETALLE")
#     chunk_size = int(os.getenv("CHUNK_SIZE"))
#     skip_rows = int(os.getenv("SKIP_ROWS"))
    

#     # print({'cab': path_cab, 'det': path_det, 'sheet_cab': sheet_cab, 'sheet_det': sheet_det, 'chunk':chunk_size, 'skip': skip_rows})

#     # CAB: validación general
#     cab_res = process_file(path_cab, sheet=sheet_cab, label='CAB', rules=rule_CAB, chunk_size=chunk_size, skip_rows=skip_rows, required_headers=list(rule_CAB.keys()))
#     print('[summary CAB]', cab_res)

#     # # # DET: validación + balance
#     det_res = process_file(path_det, sheet=sheet_det, label='DET', rules=rule_DET, chunk_size=chunk_size, skip_rows=skip_rows, required_headers=list(rule_DET.keys()), use_agg=True)
#     print('[summary DET]', det_res)

# if __name__ == '__main__':
#     main()
