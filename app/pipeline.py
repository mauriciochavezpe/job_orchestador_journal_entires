from __future__ import annotations
from typing import Dict, Any
from .excel_reader import read_sheet_in_chunks
from .validators import validate_row_generic
from .agg import BalanceAgg


def process_file(file_path: str, *, sheet: str | None, label: str, rules: Dict[str, Dict], chunk_size: int, skip_rows: int, required_headers: list[str] | None = None, use_agg: bool = False):
    total = ok_count = bad_count = 0
    agg = BalanceAgg() if use_agg else None
    sample_errors: list[dict] = []

    for batch in read_sheet_in_chunks(file_path, sheet_name=sheet, chunk_size=chunk_size, skip_rows=skip_rows, header_row=1, required_headers=required_headers):
        total += len(batch)
        for item in batch:
            res = validate_row_generic(item['data'], label, rules)
            if res['ok']:
                ok_count += 1
            else:
                bad_count += 1
                if len(sample_errors) < 5:
                    sample_errors.append({'rowNumber': item['rowNumber'], 'errors': res['errors']})

            if agg and label == 'DET':
                # clave típica en tu layout: parentkey
                k = item['data'].get('parentkey')
                d = float(item['data'].get('debit') or 0)
                c = float(item['data'].get('credit') or 0)
                agg.add(str(k), d, c)

        print(f"[{label}] +{len(batch)} -> OK:{ok_count} ERR:{bad_count} TOT:{total}")

    result = {'total': total, 'ok': ok_count, 'invalid': bad_count, 'samples': sample_errors}

    if agg:
        bal = agg.finalize()
        result['balanced_docs'] = len(bal['balanced'])
        result['unbalanced_docs'] = len(bal['unbalanced'])
        result['unbalanced_examples'] = bal['unbalanced'][:10]
    return result