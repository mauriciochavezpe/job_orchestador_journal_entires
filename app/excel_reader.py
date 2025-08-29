from __future__ import annotations
from typing import Iterable, Iterator, List, Dict, Any
from openpyxl import load_workbook
from datetime import date, datetime


def _normalize_header(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    # quitar acentos
    import unicodedata
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = '_'.join(s.split())
    out = ''.join(ch for ch in s if (ch.isalnum() or ch == '_'))
    return out or None


def _clean_single_line(val: Any) -> str | None:
    if val is None:
        return None
    return (str(val).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').strip() or None)


def _normalize_scalar(v: Any) -> Any:
    if isinstance(v, (datetime, date, int, float)):
        return v
    return _clean_single_line(v)


def read_sheet_in_chunks(
    file_path: str | os.PathLike,
    *,
    sheet_name: str | None = None,
    chunk_size: int = 1000,
    skip_rows: int = 2,
    header_row: int = 1,
    ignore_empty_rows: bool = True,
    required_headers: list[str] | None = None,
) -> Iterator[list[dict]]:
    """
    Lee una hoja XLSX en modo read_only y emite tramos (chunks) de dicts con claves de header normalizadas.
    Cada elemento del chunk tiene forma: { 'rowNumber': int, 'data': {col: val} }
    """
    from pathlib import Path
    # import os
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Archivo no existe: {p}")
    if p.stat().st_size == 0:
        raise ValueError(f"Archivo vacío: {p}")

    wb = load_workbook(p, read_only=True, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.worksheets[0]

    # iter_rows con values_only=True para obtener ya tipos nativos (openpyxl resuelve sharedStrings)
    rows = ws.iter_rows(values_only=True)

    # saltar filas decorativas previas
    for _ in range(skip_rows):
        try:
            next(rows)
        except StopIteration:
            break

    # leer encabezados relativos
    headers: List[str | None] = []
    for _ in range(header_row):
        header_tuple = next(rows)  # puede lanzar StopIteration si archivo está mal
        headers = [_normalize_header(h) for h in header_tuple]

    # print(f"headers {headers}")
    if not any(headers):
        raise ValueError(f"No se encontró encabezado en hoja '{ws.title}'")

    # validar required_headers si se provee
    if required_headers:
        missing = [h for h in required_headers if h and h not in headers]
        if missing:
            raise ValueError(f"Faltan columnas requeridas en '{ws.title}': {', '.join(missing)}")

    batch: List[dict] = []
    row_number = skip_rows + header_row

    for row in rows:
        # print(f" vlaores {len(row)}")
        row_number += 1
        data: Dict[str, Any] = {}
        for idx, key in enumerate(headers):
            if not key:
                continue
            # proteger por si hay más celdas que headers
            if idx >= len(row):
                continue
            v = row[idx]
            data[key] = _normalize_scalar(v)
            # print(f"valor item {data[key]}")

        if ignore_empty_rows and all(v in (None, '') for v in data.values()):
            continue

        batch.append({"rowNumber": row_number, "data": data})
        if len(batch) >= chunk_size:
            yield batch
            batch = []
    if batch:
        yield batch