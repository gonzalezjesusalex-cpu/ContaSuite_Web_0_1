"""Plan v1.1, Cambio 2: catalog of fiscal obligations as printed on the Constancia de Situación Fiscal.

Pure functions (no database): the initial catalog loaded by migration cs_0018, name normalization to compare the
CSF wording with the catalog, the due rule read from the CSF («A más tardar el día 17 del mes inmediato
posterior…») and the due date of a period. Due dates are a calculation for the office's control; weekends and
holidays are not moved, and the office confirms or corrects the rules. Nothing here is an SAT validation.
"""

import calendar
import re
import unicodedata
from datetime import date

GROUPS = ['IVA', 'ISR', 'Retenciones', 'Informativas', 'Anuales']
CADENCES = ('monthly', 'bimonthly', 'quarterly', 'annual')
# Months in which each cadence closes a period: obligations are shown in the last month of their period.
CLOSING = {
    'monthly': set(range(1, 13)),
    'bimonthly': {2, 4, 6, 8, 10, 12},
    'quarterly': {3, 6, 9, 12},
    'annual': {12},
}

DAY17 = {'kind': 'day_next_month', 'day': 17}
LAST_DAY = {'kind': 'last_day_next_month'}
THREE_MONTHS = {'kind': 'months_after_year_end', 'months': 3}
APRIL_30 = {'kind': 'fixed_next_year', 'month': 4, 'day': 30}
FEBRUARY_15 = {'kind': 'fixed_next_year', 'month': 2, 'day': 15}
T17 = 'A más tardar el día 17 del mes inmediato posterior al periodo que corresponda.'
TLAST = 'A más tardar el último día del mes inmediato posterior al periodo que corresponda.'
T3M = 'Dentro de los tres meses siguientes al cierre del ejercicio.'
TAPR = 'A más tardar el día 30 del mes de abril del ejercicio siguiente.'

# (key, official name as printed on the CSF, short name, group, cadence, regime / subject, due rule, due text).
# Names marked «seen» were read on real constancias (23/11/2026); the rest follow the office's list and are
# corrected by an administrator when a constancia shows the exact wording (aliases keep the older spellings).
INITIAL = [
    ('v11-iva-mensual', 'Pago definitivo mensual de IVA.', 'IVA mensual', 'IVA', 'monthly', 'General', DAY17, T17),
    (
        'v11-iva-proveedores',
        'Declaración de proveedores de IVA',
        'Proveedores IVA (DIOT)',
        'IVA',
        'monthly',
        'General',
        LAST_DAY,
        TLAST,
    ),
    (
        'v11-iva-informativa-anual',
        'Declaración informativa de IVA con el anual de ISR',
        'Informativa IVA anual',
        'IVA',
        'annual',
        'Según CSF',
        THREE_MONTHS,
        T3M,
    ),
    (
        'v11-iva-resico',
        'Pago definitivo mensual de IVA. Régimen Simplificado de Confianza.',
        'IVA RESICO',
        'IVA',
        'monthly',
        'RESICO',
        DAY17,
        T17,
    ),
    (
        'v11-ret-sueldos',
        'Entero de retenciones mensuales de ISR por sueldos y salarios',
        'Ret. sueldos',
        'Retenciones',
        'monthly',
        'Patrones',
        DAY17,
        T17,
    ),
    (
        'v11-ret-asimilados',
        'Entero de retenciones mensuales de ISR por ingresos asimilados a salarios',
        'Ret. asimilados',
        'Retenciones',
        'monthly',
        'Quien paga asimilados',
        DAY17,
        T17,
    ),
    (
        'v11-isr-pm-general',
        'Pago provisional mensual de ISR personas morales régimen general',
        'ISR PM mensual',
        'ISR',
        'monthly',
        'PM general',
        DAY17,
        T17,
    ),
    (
        'v11-isr-pm-trimestral',
        'Pago provisional trimestral de ISR de personas morales por inicio de segundo ejercicio. Régimen General.',
        'ISR PM trimestral',
        'ISR',
        'quarterly',
        'PM',
        DAY17,
        T17,
    ),
    ('v11-isr-mensual', 'Pago provisional mensual de ISR', 'ISR mensual', 'ISR', 'monthly', 'Según CSF', DAY17, T17),
    (
        'v11-isr-empresariales',
        'Pago provisional mensual de ISR por actividades empresariales',
        'ISR act. empresariales',
        'ISR',
        'monthly',
        'PF actividades empresariales y profesionales',
        DAY17,
        T17,
    ),
    (
        'v11-isr-resico-pf',
        'Pago provisional mensual de ISR. Régimen Simplificado de Confianza.',
        'ISR RESICO PF',
        'ISR',
        'monthly',
        'PF RESICO',
        DAY17,
        T17,
    ),
    (
        'v11-isr-resico-pm',
        'Pago provisional mensual de ISR personas morales. Régimen Simplificado de Confianza.',
        'ISR RESICO PM',
        'ISR',
        'monthly',
        'PM RESICO',
        DAY17,
        T17,
    ),
    (
        'v11-isr-arrendamiento',
        'Pago provisional mensual de ISR por arrendamiento de inmuebles',
        'ISR arrendamiento',
        'ISR',
        'monthly',
        'PF arrendamiento',
        DAY17,
        T17,
    ),
    (
        'v11-isr-rif',
        'Pago definitivo bimestral de ISR. Régimen de Incorporación Fiscal.',
        'RIF bimestral',
        'ISR',
        'bimonthly',
        'RIF',
        DAY17,
        'A más tardar el día 17 del mes inmediato posterior al bimestre que corresponda.',
    ),
    (
        'v11-anual-pm-general',
        'Declaración anual de ISR del ejercicio Personas morales.',
        'Anual PM',
        'Anuales',
        'annual',
        'PM general',
        THREE_MONTHS,
        T3M,
    ),
    (
        'v11-anual-pm-resico',
        'Declaración anual de ISR del ejercicio personas morales. Régimen Simplificado de Confianza.',
        'Anual PM RESICO',
        'Anuales',
        'annual',
        'PM RESICO',
        THREE_MONTHS,
        T3M,
    ),
    (
        'v11-anual-pf',
        'Declaración anual de ISR. Personas Físicas.',
        'Anual PF',
        'Anuales',
        'annual',
        'PF',
        APRIL_30,
        TAPR,
    ),
    (
        'v11-anual-resico',
        'Declaración anual de ISR. Régimen Simplificado de Confianza.',
        'Anual RESICO',
        'Anuales',
        'annual',
        'PF RESICO',
        APRIL_30,
        TAPR,
    ),
    (
        'v11-ajuste-resico',
        'Ajuste anual de ISR correspondiente a la declaración anual. Régimen Simplificado de Confianza.',
        'Ajuste anual RESICO',
        'Anuales',
        'annual',
        'RESICO',
        APRIL_30,
        TAPR,
    ),
    (
        'v11-informativa-clientes',
        'Declaración informativa anual de clientes y proveedores de bienes y servicios. Impuesto Sobre la Renta.',
        'Informativa clientes y proveedores',
        'Informativas',
        'annual',
        'Según CSF',
        FEBRUARY_15,
        'A más tardar el 15 de febrero del ejercicio siguiente.',
    ),
]
# Older or partial spellings that must land on the same entry (normalized on comparison).
ALIASES = {
    'v11-isr-pm-trimestral': ['Pago provisional trimestral de ISR personas morales (por inicio de operaciones)'],
    'v11-anual-pm-general': ['Declaración anual de ISR del ejercicio personas morales. Régimen General.'],
    'v11-informativa-clientes': ['Declaración informativa anual de clientes y proveedores de bienes y servicios'],
}


def normalize(text):
    """Upper case, no accents, single spaces, no punctuation. The regime after a period is kept as words, so
    «Pago provisional mensual de ISR. Régimen Simplificado de Confianza.» never equals the general one."""
    text = unicodedata.normalize('NFD', text or '')
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn').upper()
    text = re.sub(r'[^A-Z0-9Ñ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def match(description, entries):
    """Catalog id whose official name or alias equals the CSF wording once normalized; None otherwise.

    entries: iterable of dicts with id, official_name and aliases (list or None).
    """
    wanted = normalize(description)
    if not wanted:
        return None
    for entry in entries:
        names = [entry.get('official_name') or ''] + list(entry.get('aliases') or [])
        if any(normalize(n) == wanted for n in names if n):
            return entry['id']
    return None


def parse_due_rule(text):
    """Calculable rule from the CSF «Descripción vencimiento»; None when the wording is not recognized."""
    t = normalize(text)
    if not t:
        return None
    if 'ULTIMO DIA DEL MES INMEDIATO POSTERIOR' in t:
        return dict(LAST_DAY)
    m = re.search(r'DIA (\d{1,2}) DEL MES INMEDIATO POSTERIOR', t)
    if m:
        return {'kind': 'day_next_month', 'day': int(m.group(1))}
    m = re.search(r'DIA (\d{1,2}) DEL MES DE ([A-Z]+) DEL EJERCICIO SIGUIENTE', t)
    if m and m.group(2) in MONTHS:
        return {'kind': 'fixed_next_year', 'month': MONTHS[m.group(2)], 'day': int(m.group(1))}
    m = re.search(r'(\d{1,2}) DE ([A-Z]+) DEL EJERCICIO SIGUIENTE', t)
    if m and m.group(2) in MONTHS:
        return {'kind': 'fixed_next_year', 'month': MONTHS[m.group(2)], 'day': int(m.group(1))}
    m = re.search(r'DENTRO DE LOS (\w+) MESES SIGUIENTES AL CIERRE DEL EJERCICIO', t)
    if m:
        months = NUMBERS.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else None)
        if months:
            return {'kind': 'months_after_year_end', 'months': months}
    return None


MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            'ENERO',
            'FEBRERO',
            'MARZO',
            'ABRIL',
            'MAYO',
            'JUNIO',
            'JULIO',
            'AGOSTO',
            'SEPTIEMBRE',
            'OCTUBRE',
            'NOVIEMBRE',
            'DICIEMBRE',
        ]
    )
}
NUMBERS = {'UN': 1, 'DOS': 2, 'TRES': 3, 'CUATRO': 4, 'CINCO': 5, 'SEIS': 6}


def period_key(cadence, year, month):
    """Record key of the period that contains (year, month): 2026-11, 2026-B6, 2026-Q4, 2026-A."""
    if cadence == 'annual':
        return f'{year}-A'
    if cadence == 'quarterly':
        return f'{year}-Q{(month - 1) // 3 + 1}'
    if cadence == 'bimonthly':
        return f'{year}-B{(month - 1) // 2 + 1}'
    return f'{year}-{month:02d}'


def period_bounds(cadence, year, month):
    """First and last day of the period that contains (year, month)."""
    if cadence == 'annual':
        first, last = 1, 12
    elif cadence == 'quarterly':
        first = (month - 1) // 3 * 3 + 1
        last = first + 2
    elif cadence == 'bimonthly':
        first = (month - 1) // 2 * 2 + 1
        last = first + 1
    else:
        first = last = month
    return date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1])


def shown_in(cadence, month):
    """Obligations appear in the month that closes their period (bimonthly, quarterly and annual too)."""
    return month in CLOSING.get(cadence or 'monthly', CLOSING['monthly'])


def _month_after(day, months=1):
    index = day.year * 12 + day.month - 1 + months
    return index // 12, index % 12 + 1


def due_date(rule, period_end):
    """Due date of the period ending on `period_end` under `rule`; None without a calculable rule."""
    if not rule:
        return None
    kind = rule.get('kind')
    try:
        if kind == 'day_next_month':
            y, m = _month_after(period_end)
            return date(y, m, min(int(rule['day']), calendar.monthrange(y, m)[1]))
        if kind == 'last_day_next_month':
            y, m = _month_after(period_end)
            return date(y, m, calendar.monthrange(y, m)[1])
        if kind == 'months_after_year_end':
            y, m = period_end.year + 1, int(rule['months'])
            return date(y, m, calendar.monthrange(y, m)[1])
        if kind == 'fixed_next_year':
            y, m = period_end.year + 1, int(rule['month'])
            return date(y, m, min(int(rule['day']), calendar.monthrange(y, m)[1]))
    except (KeyError, TypeError, ValueError):
        return None
    return None


def active_in(start, end, period_start, period_end):
    """The company's obligation (CSF start/end dates) overlaps the period."""
    return (not start or start <= period_end) and (not end or end >= period_start)


def label_cadence(cadence):
    return {'monthly': 'Mensual', 'bimonthly': 'Bimestral', 'quarterly': 'Trimestral', 'annual': 'Anual'}.get(
        cadence or 'monthly', 'Mensual'
    )
