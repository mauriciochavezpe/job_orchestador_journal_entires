from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

class BalanceAgg:
    """Agrupa por clave (p.ej. ParentKey) y valida Débito=Crédito con tolerancia"""
    def __init__(self, *, tolerance: str = '0.000001'):
        self.tol = Decimal(tolerance)
        self.map: Dict[str, Dict] = {}

    def add(self, key: str, debit: float | int | None, credit: float | int | None):
        if key is None:
            return
        g = self.map.get(key) or {'debit': Decimal('0'), 'credit': Decimal('0'), 'lines': 0}
        g['debit'] += Decimal(str(debit or 0))
        g['credit'] += Decimal(str(credit or 0))
        g['lines'] += 1
        self.map[key] = g

    def finalize(self):
        ok, bad = [], []
        for key, g in self.map.items():
            diff = g['debit'] - g['credit']
            item = {
                'key': key,
                'lines': g['lines'],
                'debit': float(g['debit']),
                'credit': float(g['credit']),
                'diff': float(diff)
            }
            (ok if abs(diff) <= self.tol else bad).append(item)
        return {'balanced': ok, 'unbalanced': bad}