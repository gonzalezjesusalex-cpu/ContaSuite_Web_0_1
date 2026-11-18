"""Conciliación contra el SAT y pagos de facturas PPD, a partir de los reportes mensuales y de los XML.

Two read-only checks over data the user already keeps in the folder:
- Reporte SAT contra XML: for each month and direction (emitidos / recibidos), which UUIDs the SAT report lists that
  have no XML in the folder, and which XML are not in the report.
- Pagos PPD: for each PPD invoice, which payment complements (CFDI tipo P) point at it and what balance remains.
Nothing is validated with the SAT and nothing changes a file; results are proposals for the accountant to review.
"""

import re
from collections import defaultdict

from .folder_groups import fold

UUID = re.compile(r'[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}', re.I)
DOCUMENT = re.compile(r'<(?:\w+:)?DoctoRelacionado\b([^>]*)>', re.S)
MAX_ITEMS = 40
MAX_INVOICES = 800
REASONS = {
    'sin_xml': 'El SAT lo lista y no hay XML en la carpeta.',
    'sin_reporte': 'Hay XML, pero el reporte del SAT de ese mes no lo incluye.',
    'sin_pago': 'Factura PPD sin complemento de pago.',
    'parcial': 'Factura PPD con pagos y saldo pendiente.',
    'liquidada': 'Factura PPD liquidada por sus complementos de pago.',
}


def uuid_in(text):
    found = UUID.search(text)
    return found.group(0).upper() if found else None


def parse_report(rows):
    """Rows of a SAT monthly report as dicts; the header row is found by its «UUID» cell. [] if there is none."""
    head = next((n for n, r in enumerate(rows) if any(str(c).strip().upper() == 'UUID' for c in r if c)), None)
    if head is None:
        return []
    names = [fold(str(c)).strip() if c else '' for c in rows[head]]

    def col(*options):
        return next((names.index(o) for o in options if o in names), None)

    cols = {
        'u': col('UUID'),
        'tipo': col('TIPO'),
        'fecha': col('FECHA'),
        'total': col('TOTAL'),
        'metodo': col('METODO DE PAGO'),
        'emisor': col('RFC EMISOR'),
        'receptor': col('RFC RECEPTOR'),
        'estatus': col('ESTATUS'),
    }

    def cell(row, key):
        index = cols[key]
        return row[index] if index is not None and index < len(row) else None

    out = []
    for row in rows[head + 1 :]:
        uuid = str(cell(row, 'u') or '').strip().upper()
        if not UUID.fullmatch(uuid):
            continue
        total = cell(row, 'total')
        out.append(
            {
                'u': uuid,
                'tipo': str(cell(row, 'tipo') or '')[:12],
                'fecha': str(cell(row, 'fecha') or '')[:10],
                'total': round(total, 2) if isinstance(total, (int, float)) else None,
                'emisor': str(cell(row, 'emisor') or '')[:13],
                'receptor': str(cell(row, 'receptor') or '')[:13],
                'cancelado': 'CANCEL' in fold(str(cell(row, 'estatus') or '')),
            }
        )
    return out


def _attr(attrs, name):
    found = re.search(r'\b' + name + r'\s*=\s*"([^"]*)"', attrs)
    return found.group(1) if found else ''


def _number(attrs, name):
    try:
        return float(_attr(attrs, name))
    except ValueError:
        return None


def parse_payment(text):
    """(uuid, pagado, saldo, parcialidad) of every document a payment complement settles."""
    out = []
    for attrs in DOCUMENT.findall(text):
        uuid = _attr(attrs, 'IdDocumento').upper()
        if not UUID.fullmatch(uuid):
            continue
        parcialidad = int(_attr(attrs, 'NumParcialidad') or 0)
        out.append((uuid, _number(attrs, 'ImpPagado'), _number(attrs, 'ImpSaldoInsoluto'), parcialidad))
    return out


class SatReconcile:
    def __init__(self):
        self.reports = {}  # (kind, year, month) -> {uuid: row}
        self.xml = defaultdict(dict)  # (kind, year, month) -> {uuid: path}

    def add_report(self, kind, year, month, rows):
        self.reports.setdefault((kind, year, month), {}).update({r['u']: r for r in parse_report(rows)})

    def add_xml(self, uuid, path, place):
        if uuid and place.get('k') and place.get('y') and place.get('m'):
            self.xml[(place['k'], place['y'], place['m'])][uuid] = path

    def result(self):
        periods = []
        for key in sorted(set(self.reports) | set(self.xml), key=lambda k: (k[1], k[2], k[0])):
            kind, year, month = key
            report, xml = self.reports.get(key), self.xml.get(key, {})
            entry = {'k': kind, 'y': year, 'm': month, 'xml': len(xml), 'reporte': len(report) if report else None}
            if report is None:
                entry.update(s='sin_reporte_mes', ok=0, faltan=[], sobran=[], cancelados=0)
            else:
                missing = [r for u, r in report.items() if u not in xml]
                extra = [p for u, p in xml.items() if u not in report]
                canceled = [u for u, r in report.items() if r['cancelado'] and u in xml]
                entry.update(
                    ok=len(set(report) & set(xml)),
                    faltan=missing[:MAX_ITEMS],
                    n_faltan=len(missing),
                    sobran=extra[:MAX_ITEMS],
                    n_sobran=len(extra),
                    cancelados=len(canceled),
                    s='revisar' if missing or extra or canceled else 'ok',
                )
            periods.append(entry)
        return {
            'periodos': periods,
            'con_reporte': sum(1 for p in periods if p['reporte'] is not None),
            'ok': sum(1 for p in periods if p['s'] == 'ok'),
            'revisar': sum(1 for p in periods if p['s'] == 'revisar'),
            'sin_reporte': sum(1 for p in periods if p['s'] == 'sin_reporte_mes'),
            'faltan_xml': sum(p.get('n_faltan', 0) for p in periods),
            'sin_reporte_xml': sum(p.get('n_sobran', 0) for p in periods),
        }


class PpdIndex:
    """PPD invoices and the payment complements that settle them (matched by UUID, never by name)."""

    def __init__(self):
        self.invoices = {}  # uuid -> {...}
        self.payments = defaultdict(list)  # invoice uuid -> [(pagado, saldo, parcialidad, path)]

    def add_invoice(self, uuid, path, info, place):
        if uuid and info and info.get('metodo') == 'PPD' and info.get('tipo') == 'I':
            self.invoices[uuid] = {
                'u': uuid,
                'p': path,
                'k': place.get('k'),
                'y': place.get('y'),
                'm': place.get('m'),
                'tot': info.get('total'),
            }

    def add_payment(self, path, text):
        for uuid, paid, balance, number in parse_payment(text):
            self.payments[uuid].append((paid, balance, number, path))

    def result(self):
        rows = []
        for uuid, inv in self.invoices.items():
            pays = self.payments.get(uuid, [])
            paid = round(sum(p[0] or 0 for p in pays), 2)
            last = max(pays, key=lambda p: p[2], default=None)
            balance = last[1] if last else inv['tot']
            if not pays:
                state = 'sin_pago'
            elif balance is not None and balance <= 0.01:
                state = 'liquidada'
            else:
                state = 'parcial'
            rows.append({**inv, 'pagos': len(pays), 'pagado': paid, 'saldo': balance, 's': state})
        order = {'parcial': 0, 'sin_pago': 1, 'liquidada': 2}
        rows.sort(key=lambda r: (order[r['s']], r['y'] or 0, r['m'] or 0))
        known = set(self.invoices)
        orphans = [{'u': u, 'p': pays[0][3]} for u, pays in self.payments.items() if u not in known]
        return {
            'rows': rows[:MAX_INVOICES],
            'total': len(rows),
            'sin_pago': sum(1 for r in rows if r['s'] == 'sin_pago'),
            'parcial': sum(1 for r in rows if r['s'] == 'parcial'),
            'liquidadas': sum(1 for r in rows if r['s'] == 'liquidada'),
            'pagos_ajenos': len(orphans),
            'ajenos': orphans[:MAX_ITEMS],
        }
