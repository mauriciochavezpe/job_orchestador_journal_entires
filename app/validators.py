from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

# ---------- Strings ----------

def normalize_string(val: Any, *, to_upper=False, to_lower=False, single_line=True, remove_diacritics=True):
    if val is None:
        return None
    s = str(val)
    if single_line:
        s = s.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    s = s.strip()
    if remove_diacritics:
        import unicodedata
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    if to_upper:
        s = s.upper()
    if to_lower:
        s = s.lower()
    return s or None


def validate_string(value: Any, options: Dict) -> Tuple[bool, Any, List[str]]:
    opts = {
        'required': False, 'minLength': None, 'maxLength': None,
        'toUpper': False, 'toLower': False, 'regex': None,
        'enumSet': None, 'disallow': []
    }
    opts.update(options or {})

    if (value in (None, '')) and not opts['required']:
        return True, None, []

    s = normalize_string(value, to_upper=opts['toUpper'], to_lower=opts['toLower'])
    if not s and opts['required']:
        return False, value, ['requerido']
    if not s:
        return True, None, []

    errs: List[str] = []
    if opts['minLength'] is not None and len(s) < opts['minLength']:
        errs.append(f"min {opts['minLength']}")
    if opts['maxLength'] is not None and len(s) > opts['maxLength']:
        errs.append(f"max {opts['maxLength']}")
    if opts['regex'] and not re.compile(opts['regex']).match(s):
        errs.append('formato inválido')
    if opts['enumSet'] and s not in set(opts['enumSet']):
        errs.append('valor no permitido')
    for pat in opts['disallow'] or []:
        if re.compile(pat).search(s):
            errs.append('caracteres prohibidos')
    return (len(errs) == 0), s, errs

# ---------- Dates ----------

def _pad2(n: int) -> str:
    return f"{n:02d}"


def _days_in_month(y: int, m: int) -> int:
    import calendar
    return calendar.monthrange(y, m)[1]


def _parse_any_date(value: Any, *, format_in: str | None, allow_excel_serial=True) -> Tuple[bool, str | None, str | None]:
    if value in (None, ''):
        return False, None, 'vacía'

    if isinstance(value, int):
        value = str(value)

    # strings tipo YYYYMMDD
    if isinstance(value, str) and format_in == 'YYYYMMDD' and re.fullmatch(r"\d{8}", value):
        y, m, d = int(value[0:4]), int(value[4:6]), int(value[6:8])
        try:
            dt = datetime(y, m, d)
            return True, f"{y}-{_pad2(m)}-{_pad2(d)}", None
        except ValueError:
            return False, None, 'fecha inválida'

    # datetime nativo
    if isinstance(value, datetime):
        return True, value.strftime('%Y-%m-%d'), None

    # excel serial (openpyxl suele traer datetime ya, pero por si acaso)
    if allow_excel_serial:
        try:
            num = Decimal(str(value))
            if Decimal(59) < num < Decimal(60000):
                # base 1899-12-30
                base = datetime(1899, 12, 30)
                dt = base + timedelta(days=float(num))
                return True, dt.strftime('%Y-%m-%d'), None
        except Exception:
            pass

    # otras cadenas comunes
    s = normalize_string(value, remove_diacritics=False)
    if not s:
        return False, None, 'vacía'

    # yyyy-mm-dd
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d)
            return True, dt.strftime('%Y-%m-%d'), None
        except ValueError:
            return False, None, 'fecha inválida (yyyy-mm-dd)'

    # dd/mm/yyyy o dd-mm-yyyy
    m = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d)
            return True, dt.strftime('%Y-%m-%d'), None
        except ValueError:
            return False, None, 'fecha inválida (dd/mm/yyyy)'

    # mm/dd/yyyy
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d)
            return True, dt.strftime('%Y-%m-%d'), None
        except ValueError:
            return False, None, 'fecha inválida (mm/dd/yyyy)'

    return False, None, 'formato no reconocido'
def validate_date2(value):
    
    if(type(value) ==str and len(value)==8):
        y, m, d = int(value[0:4]), int(value[4:6]), int(value[6:8])
        try:
            dt = datetime(y, m, d)
            return True, f"{y}-{_pad2(m)}-{_pad2(d)}", None
        except ValueError:
            return False, None, 'fecha inválida'
    else:
        return False,''

def validate_date(value: Any, options: Dict) -> Tuple[bool, Any, List[str]]:
    opts = {
        'required': False,
        'allowExcelSerial': True,
        'formatIn': None,
        'formatOut': 'YYYY-MM-DD',
    }
    opts.update(options or {})

    if (value in (None, '')) and not opts['required']:
        return True, None, []

    ok, iso, err = _parse_any_date(value, format_in=opts['formatIn'], allow_excel_serial=opts['allowExcelSerial'])
    if not ok:
        return False, value, [err]

    # salida
    if opts['formatOut'] == 'YYYYMMDD' and iso:
        return True, iso.replace('-', ''), []
    return True, iso, []

# ---------- Numbers ----------

def validate_number(value: Any, options: Dict) -> Tuple[bool, Any, List[str]]:
    opts = {'required': False, 'min': None, 'max': None, 'decimals': 2}
    opts.update(options or {})

    if (value in (None, '')) and not opts['required']:
        return True, None, []

    # normaliza separadores
    s = str(value).strip()
    s = re.sub(r"[^\d.,\-]", "", s)
    # separador decimal probable = último . o ,
    last_dot = s.rfind('.')
    last_com = s.rfind(',')
    dec_pos = max(last_dot, last_com)
    if dec_pos >= 0:
        int_part = re.sub(r"[.,]", "", s[:dec_pos]) or '0'
        dec_part = re.sub(r"[.,]", "", s[dec_pos+1:])
    else:
        int_part = re.sub(r"[.,]", "", s) or '0'
        dec_part = ''

    sign = 1
    if int_part.startswith('-'):
        sign = -1
        int_part = int_part[1:]
    if int_part == '':
        int_part = '0'

    try:
        d = Decimal(int_part or '0') + (Decimal(dec_part or '0') / (Decimal(10) ** len(dec_part)))
        d = d.copy_negate() if sign < 0 else d
        if opts['decimals'] is not None:
            q = Decimal(10) ** (-opts['decimals'])
            d = d.quantize(q, rounding=ROUND_HALF_UP)
        if opts['min'] is not None and d < Decimal(str(opts['min'])):
            return False, value, [f"min {opts['min']}"]
        if opts['max'] is not None and d > Decimal(str(opts['max'])):
            return False, value, [f"max {opts['max']}"]
        return True, float(d), []
    except (InvalidOperation, ValueError):
        return False, value, ['formato numérico inválido']

def validate_journal_entry_lines(lines: list[dict]):
    errors = []
    for i, l in enumerate(lines):
        if not l.get("ShortName"):
            errors.append(f"Línea {i+1}: ShortName es requerido")
    if errors:
        raise ValueError(", ".join(errors))

# ---------- Row engine ----------

def validate_row_generic(row: Dict[str, Any], label: str, rules: Dict[str, Dict]) -> Dict:
    out: Dict[str, Any] = {}
    errs: Dict[str, List[str]] = {}

    for field, rule in (rules or {}).items():
        src_val = row.get(field, '')
        t = rule.get('type')
        name = rule.get('name', field)
        options = rule.get('options', {})

        if t == 'string':
            ok, val, e = validate_string(src_val, options)
        elif t == 'date':
            ok, val, e = validate_date(src_val, options)
        elif t == 'number':
            ok, val, e = validate_number(src_val, options)
        else:
            ok, val, e = True, src_val, []

        if ok:
            out[name] = val if val is not None else ''
        else:
            errs[field] = e or ['inválido']
            out[name] = src_val

    # Regla mínima DET: uno de Debit/Credit > 0 si existen ambos
    if label == 'DET' and ('debit' in row or 'credit' in row):
        d = float(row.get('debit') or 0)
        c = float(row.get('credit') or 0)
        if (d == 0 and c == 0) or (d != 0 and c != 0):
            errs['debit_credit'] = ['Debe existir solo un valor en Débito o Crédito']

    return {
        'ok': len(errs) == 0,
        'data': out,
        'errors': errs
    }