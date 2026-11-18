"""Estados financieros: contabilidad por tipo de reporte, ejercicio y mes, dentro de su subcarpeta.

Metadata only. It organizes what is filed (balanza, auxiliares, libro diario, balance general, estado de resultados,
flujo, razones, variaciones, analíticas, estados en Excel) and never reads or validates the numbers.
"""

import re
from pathlib import PurePosixPath

from .folder_groups import fold

# Order matters: «ANALITICAS DE BALANCE» is an analítica, not the balance general.
TYPES = (
    ('analiticas', 'Analíticas', r'ANALITICAS'),
    ('balanza', 'Balanza de comprobación', r'BALANZA'),
    ('auxiliar', 'Auxiliares', r'AUXILIAR|AUXULIAR'),
    ('diario', 'Libro diario', r'LIBRO DIARIO'),
    ('balance', 'Balance general', r'BALANCE GENERAL'),
    ('resultados', 'Estado de resultados', r'ESTADO DE RESULTADOS'),
    ('flujo', 'Flujo de efectivo', r'FLUJO DE EFECTIVO'),
    ('razones', 'Razones financieras', r'RAZONES FINANCIERAS'),
    ('variaciones', 'Variaciones en capital', r'VARIACIONES EN CAPITAL'),
    ('detalle', 'Detalle mensual', r'DETALLEMENSUAL'),
    ('movimientos', 'Ingresos y gastos', r'^(INGRESOS|GASTOS)\b'),
    ('estados', 'Estados financieros', r'ESTADOS? FINANCIEROS?'),
    ('anual', 'Archivo anual (.36)', r'\.36\.'),
    ('mensual', 'Archivo mensual (.38)', r'\.38\.'),
    ('nomina', 'Visor de nómina', r'VISOR DE NOMINA'),
)
LABELS = {key: label for key, label, _ in TYPES} | {'otro': 'Otro'}
MAX_ROWS = 800


def report_type(name):
    folded = fold(name)
    for key, _, pattern in TYPES:
        if re.search(pattern, folded):
            return key
    return 'otro'


def year_and_month(name):
    """(year, month) from names such as 'CNA…38.2026-7.pdf', 'BALANCE GENERAL 24.pdf' or '….36.2023.xlsx'."""
    stem = PurePosixPath(name).stem
    four = re.search(r'(20\d{2})(?:-(\d{1,2}))?(?!\d)', stem)
    if four:
        month = int(four.group(2)) if four.group(2) and 1 <= int(four.group(2)) <= 12 else None
        return int(four.group(1)), month
    two = re.search(r'(?<![\d.])(\d{2})$', stem.strip())
    return (2000 + int(two.group(1)), None) if two else (None, None)


class FinanceIndex:
    def __init__(self):
        self.items = []

    def add(self, path):
        norm = path.replace('\\', '/')
        parts = norm.split('/')
        name = parts[-1]
        year, month = year_and_month(name)
        folders = parts[:-1]
        # The folders below «ESTADOS FINANCIEROS» are scopes (FIANZAS, MUNICIPIO OAXACA…).
        scope = ''
        for n, folder in enumerate(folders):
            if re.search(r'ESTADOS? FINANCIEROS?', fold(folder)):
                scope = '/'.join(folders[n + 1 :])
                break
        self.items.append({'p': path, 't': report_type(name), 'y': year, 'n': month, 'o': scope})

    def result(self):
        return {'rows': self.items[:MAX_ROWS], 'total': len(self.items), 'dropped': max(0, len(self.items) - MAX_ROWS)}
