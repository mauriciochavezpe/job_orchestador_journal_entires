
import openpyxl
from pathlib import Path

# --- Configuración ---
FILE_NAME = "ASIENTOS_CONTABLES_DETALLE.xlsx"
SHEET_NAME = "DetalleSaldosBancosFinal"
ASSETS_DIR = "assets"
# -------------------

project_root = Path(__file__).resolve().parent
file_path = project_root / ASSETS_DIR / FILE_NAME

# print(f"Leyendo archivo: {file_path}")
# print(f"Leyendo hoja: {SHEET_NAME}")

try:
    workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheet = workbook[SHEET_NAME]

    for row_num, row in enumerate(sheet.iter_rows(values_only=True), 1):
        print(f"--- Fila {row_num} ---")
        # print(row)
        if any(cell is None for cell in row):
            print(f"¡ADVERTENCIA! La fila {row_num} contiene celdas vacías (None).")
        if(row_num > 10): break

except FileNotFoundError:
    print(f"Error: No se encontró el archivo en la ruta: {file_path}")
except KeyError:
    print(f"Error: No se encontró la hoja '{SHEET_NAME}' en el archivo.")
except Exception as e:
    print(f"Ocurrió un error inesperado: {e}")

