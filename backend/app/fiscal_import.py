"""Pure preview contract for the Excel «Control de obligaciones». No database writes or file access.

The reader (`fiscal_xlsx.read_workbook`) supplies visible sheets/rows with their cells in memory; this module turns
them into PROPOSALS using the versioned dictionary `fiscal_dictionary.json`. The original value of every cell is
always kept literal. Nothing here is a final import: no fiscal record is written.
"""

import json
import re
import unicodedata
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

DICTIONARY_PATH = Path(__file__).with_name('fiscal_dictionary.json')

MONTHS = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
]


@lru_cache(maxsize=1)
def dictionary():
    with DICTIONARY_PATH.open(encoding='utf-8') as handle:
        return json.load(handle)


def normalize(value):
    return ' '.join(
        ''.join(c for c in unicodedata.normalize('NFKD', str(value)) if not unicodedata.combining(c)).lower().split()
    )


def normalize_header(value):
    """Header text without accents, case, extra spaces; `/` counts as a space («IMSS  /  PAGADO» -> «imss pagado»)."""
    return normalize(str(value or '').replace('/', ' '))


def sheet_period(name):
    """`OCT 26` -> 2026-10, `OCT20` -> 2020-10, `Noviembre 2026` -> 2026-11, `2026-11` -> 2026-11; None if unclear."""
    text = normalize(name)
    numeric = re.fullmatch(r'(20\d{2})[-/](0?[1-9]|1[0-2])', text)
    if numeric:
        return f'{int(numeric[1])}-{int(numeric[2]):02d}'
    months = dictionary()['months']
    match = re.fullmatch(r'([a-z]+)\s*[-/ ]?\s*(?:20)?(\d{2})', text)
    if match and match[1] in months:
        return f'20{match[2]}-{months[match[1]]:02d}'
    year = re.search(r'\b(20\d{2})\b', text)
    found = [months[w] for w in re.findall(r'[a-z]+', text) if w in months]
    return f'{year[1]}-{found[0]:02d}' if year and len(set(found)) == 1 else None


def resolve_header(header):
    """What a column header means: obligation (with optional fixed year), special column or unknown."""
    dic = dictionary()
    key = normalize_header(header)
    if not key or key.startswith('(sin encabezado'):
        return dict(role='unknown', reason='blank_header')
    special = dic['special_columns'].get(key)
    if special == 'not_added':
        return dict(role='unknown', reason='not_added')
    if special:
        return dict(role=special)
    annual = re.fullmatch(dic['annual_header_pattern'], key)
    if annual:
        return dict(role='obligation', label=dic['annual_label'], year=int(annual[1]))
    label = dic['headers'].get(key)
    if label:
        return dict(role='obligation', label=label)
    return dict(role='unknown', reason='unknown_header')


def _date_value(value):
    return isinstance(value, (date, datetime))


def _iso(value):
    return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()


def _person_like(text):
    return bool(re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ.'\- ]+", text.strip())) and len(text.strip()) >= 2


def classify(value):
    """Generic classification (company diagnostics use it): no fiscal meaning is inferred."""
    if value is None or value == '':
        return dict(kind='blank', status='unreviewed', original=value)
    if isinstance(value, (date, datetime)):
        return dict(kind='date', status='unreviewed', original=value.isoformat(), authority_validated=False)
    if normalize(value) in {'na', 'n/a', 'no aplica'}:
        return dict(kind='not_applicable', status='not_applicable', original=value)
    return dict(kind='text', status='unreviewed', original=value, requires_review=True)


def propose(value, role='obligation'):
    """Proposal for one cell by the dictionary. `role` is `obligation`, `payment`, `regime` or `responsible`."""
    dic = dictionary()
    base = dict(original=value, requires_review=False, warnings=[], authority_validated=False)
    if value is None or (isinstance(value, str) and not value.strip()):
        return dict(base, kind='blank', status='pending' if role == 'obligation' else 'unreviewed', original=value)
    if _date_value(value) and role == 'payment':
        return dict(
            base,
            kind='date',
            status='unreviewed',
            original=_iso(value),
            payment='pending',
            requires_review=True,
            warnings=['una fecha en PAGO no acredita el pago federal'],
        )
    if _date_value(value):
        return dict(
            base,
            kind='date',
            status='fulfilled' if role == 'obligation' else 'unreviewed',
            original=_iso(value),
            submitted_at=_iso(value),
            original_type='date',
        )
    text = str(value).strip()
    token = dic['values'].get(normalize(text))
    if role == 'regime':
        key = normalize(text)
        if key in dic['regimes']:
            return dict(base, kind='regime', status='unreviewed', interpreted=dic['regime_aliases'].get(key, key))
        return dict(base, kind='text', status='unreviewed', requires_review=True)
    if role == 'responsible':
        return dict(base, kind='person', status='unreviewed', responsible_name=text, requires_confirmation=True)
    if token == 'not_applicable':
        extra = dict(payment='not_applicable') if role == 'payment' else {}
        return dict(base, kind='not_applicable', status='not_applicable', **extra)
    if role == 'payment':
        if token == 'without_payment':
            return dict(base, kind='without_payment', status='unreviewed', payment='not_applicable')
        if token == 'with_payment':
            return dict(base, kind='with_payment', status='unreviewed', payment='pending')
        if token == 'zeros':
            return dict(base, kind='zeros', status='unreviewed', payment='not_applicable')
        return dict(base, kind='text', status='unreviewed', requires_review=True, payment='unknown')
    if token == 'ok':
        return dict(base, kind='ok', status='fulfilled', requires_review=True, warnings=['ok_without_date'])
    if token == 'zeros':
        return dict(base, kind='zeros', status='fulfilled', payment='not_applicable')
    if token == 'no_fiel':
        return dict(base, kind='no_fiel', status='pending', warnings=['sin FIEL para acceder al portal'])
    if token == 'not_carried':
        return dict(
            base,
            kind='not_carried',
            status='not_applicable',
            propose_company_not_applicable=True,
            requires_confirmation=True,
        )
    if token == 'trust':
        return dict(base, kind='trust', status='unreviewed', requires_review=True, warnings=['nota: CONFIANZA'])
    if token in ('with_payment', 'without_payment'):
        return dict(base, kind='text', status='unreviewed', requires_review=True)
    if normalize(text) in dic['known_other'] or not _person_like(text):
        return dict(base, kind='text', status='unreviewed', requires_review=True)
    return dict(base, kind='person', status='pending', responsible_name=text, requires_confirmation=True)


def _company_match(row, companies, equivalences):
    """(company or None, how, candidates). Never decided by name alone: a name is only a proposal."""
    rfc = str(row.get('rfc', '') or '').strip().upper()
    if rfc:
        found = [c for c in companies if c.get('rfc', '').upper() == rfc]
        return (found[0] if len(found) == 1 else None, 'rfc' if len(found) == 1 else 'none', found)
    name = normalize(row.get('name', ''))
    if not name:
        return None, 'none', []
    confirmed = (equivalences or {}).get(name)
    if confirmed:
        found = [c for c in companies if c['id'] == confirmed]
        if len(found) == 1:
            return found[0], 'confirmed', found
    proposed = [c for c in companies if normalize(c['name']) == name]
    if len(proposed) == 1:
        return None, 'proposed', proposed
    return None, 'ambiguous' if proposed else 'none', proposed


def preview(sheets, companies, catalog, equivalences=None):
    """Proposals per sheet/row/cell. `equivalences` maps normalized Excel name -> confirmed company id."""
    dic = dictionary()
    by_label = {normalize(c['label']): c['id'] for c in catalog}
    result = []
    seen = set()
    for sheet in sheets:
        period = sheet_period(sheet['name'])
        for row in sheet['rows']:
            company, how, candidates = _company_match(row, companies, equivalences)
            conflicts = []
            if how not in ('rfc', 'confirmed'):
                conflicts.append('company_not_unique' if how == 'ambiguous' else 'company_not_confirmed')
            if not period:
                conflicts.append('period_ambiguous')
            cells = []
            if how in ('rfc', 'confirmed'):
                resolved = [(h, v, resolve_header(h)) for h, v in row['cells'].items()]
                payment_value = next((v for h, v, r in resolved if r['role'] == 'payment'), None)
                payment_cell = next(((h, v) for h, v, r in resolved if r['role'] == 'payment'), None)
                federal = next(
                    (v for h, v, r in resolved if r.get('label') == dic['payment_date_source']),
                    None,
                )
                pay = propose(payment_value, 'payment') if payment_cell else None
                for header, value, meaning in resolved:
                    role = meaning['role']
                    issues = []
                    entry = dict(header=header, role=role, obligation_id=None, conflicts=issues)
                    if role in ('company', 'ignore'):
                        continue
                    if role == 'regime':
                        proposal = propose(value, 'regime')
                        mine = [normalize(x) for x in company.get('regimes', [])]
                        if proposal.get('interpreted') and mine:
                            proposal['matches_company_regime'] = any(proposal['interpreted'] in m for m in mine)
                        entry['value'] = proposal
                    elif role == 'responsible':
                        entry['value'] = propose(value, 'responsible')
                    elif role == 'payment':
                        entry['value'] = pay
                        entry['targets'] = dic['payment_targets']
                    elif role == 'unknown':
                        issues.append(meaning.get('reason', 'unknown_header'))
                        entry['value'] = dict(original=value if not _date_value(value) else _iso(value))
                    else:
                        proposal = propose(value)
                        ident = by_label.get(normalize(meaning['label']))
                        entry.update(obligation_id=ident, obligation=meaning['label'])
                        if not ident:
                            issues.append('obligation_not_in_catalog')
                        if meaning.get('year'):
                            entry['period'] = f"{meaning['year']}-A"
                        if pay and meaning['label'] in dic['payment_targets'] and 'payment' not in proposal:
                            payment = pay.get('payment')
                            if payment == 'pending' and _date_value(federal):
                                payment = 'paid'
                            if payment:
                                proposal['payment'] = payment
                                proposal['payment_source'] = 'PAGO' + (
                                    ' + fecha de pago federal' if payment == 'paid' else ''
                                )
                        entry['value'] = proposal
                        key = (company['id'], ident, entry.get('period') or period)
                        if ident and (entry.get('period') or period):
                            if key in seen:
                                issues.append('duplicate_cell')
                            seen.add(key)
                    cells.append(entry)
            result.append(
                dict(
                    sheet=sheet['name'],
                    row_number=row['number'],
                    period=period,
                    company_id=company['id'] if company else None,
                    company_match=how,
                    candidate_company_ids=[c['id'] for c in candidates] if not company else [],
                    excel_name=row.get('name', ''),
                    cells=cells,
                    conflicts=conflicts,
                    original=row,
                )
            )
    return result
