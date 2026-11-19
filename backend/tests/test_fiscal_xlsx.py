"""Reader of the Excel «Control de obligaciones» with a synthetic workbook built by the test itself (cambio 3A.7)."""

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.company_xlsx import InvalidWorkbook
from app.fiscal_import import preview
from app.fiscal_xlsx import read_workbook

CATALOG = [
    dict(id=f'o{i}', label=label)
    for i, label in enumerate(
        [
            'Contabilidad',
            'ISR',
            'IVA',
            'Retenciones',
            'DIOT',
            'REPSE',
            'Impuesto sobre Nómina',
            'Nómina 1',
            'IMSS',
            'Declaración anual',
            'Pago impuestos federales',
            'Expediente físico',
        ]
    )
]
COMPANIES = [
    dict(id='c1', rfc='AAA010101AA1', name='Alfa Servicios SA', regimes=['General de Ley']),
    dict(id='c2', rfc='BBB010101BB1', name='Beta Comercial SA', regimes=['Resico']),
]
HEADERS = [
    'No.',
    'EMPRESA',
    'REGIMEN',
    'EJECUTA',
    'CONTABILIDAD',
    'ISR ',
    'IVA',
    'RETENCIONES',
    'PAGO',
    'ANUAL 2024',
    None,
    'REPSE',
    'IMPUESTO SOBRE NOMINA ',
    'IMSS  /  PAGADO',
    'PAGO IMPUESTOS FED',
    'EXPEDIENTE ',
    'BIMESTRAL RIF',
    'COLUMNA NUEVA',
]


def workbook_bytes():
    book = Workbook()
    ws = book.active
    ws.title = 'OCT 26'
    ws.append(HEADERS)
    ws.append(
        [
            '=ROW()-1',
            'ALFA SERVICIOS SA',
            'GENERAL',
            'Laura Gómez',
            datetime(2026, 11, 5),
            datetime(2026, 11, 17),
            'OK OK OK',
            'CEROS',
            'CON PAGO',
            date(2025, 4, 30),
            'dato suelto',
            'SIN FIEL',
            'NO SE LLEVARAN',
            'NEGATIVO',
            datetime(2026, 11, 18),
            'CONFIANZA',
            'OK',
            'x',
        ]
    )
    ws.append(
        [
            '=ROW()-1',
            'BETA COMERCIAL SA',
            'CONFIANZA',
            None,
            'NA',
            None,
            datetime(2026, 11, 20),
            None,
            'SIN PAGO',
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
    )
    ws.append([None] * len(HEADERS))  # a blank row is skipped
    old = book.create_sheet('ENE 22')
    old.append(['EMPRESA', 'ISR'])
    old.append(['ALFA SERVICIOS SA', 'OK'])
    hidden = book.create_sheet('OCT20')
    hidden.append(['EMPRESA', 'ISR'])
    hidden.append(['SECRETA SA', 'OK'])
    hidden.sheet_state = 'hidden'
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def test_hidden_sheets_are_ignored_and_formulas_never_evaluated():
    data = read_workbook(workbook_bytes())
    assert [s['name'] for s in data['sheets']] == ['OCT 26', 'ENE 22']
    assert data['ignored'] == [dict(name='OCT20', reason='hidden')]
    assert data['formula_cells_omitted'] == 2
    first = data['sheets'][0]
    assert first['period'] == '2026-10' and data['sheets'][1]['period'] == '2022-01'
    assert [r['name'] for r in first['rows']] == ['ALFA SERVICIOS SA', 'BETA COMERCIAL SA']
    assert 'ISR' in first['rows'][0]['cells'] and 'IMSS / PAGADO' in first['rows'][0]['cells']
    names = {u['header']: u['reason'] for u in data['unknown_columns']}
    assert names['COLUMNA NUEVA'] == 'unknown_header'
    assert names['BIMESTRAL RIF'] == 'not_added'
    assert names['(sin encabezado K)'] == 'blank_header'


def test_full_preview_with_every_special_value():
    data = read_workbook(workbook_bytes())
    result = preview(data['sheets'], COMPANIES, CATALOG, equivalences={'alfa servicios sa': 'c1'})
    alfa = next(r for r in result if r['sheet'] == 'OCT 26' and r['row_number'] == 2)
    beta = next(r for r in result if r['sheet'] == 'OCT 26' and r['row_number'] == 3)
    assert alfa['company_id'] == 'c1' and alfa['period'] == '2026-10'
    # Beta has no confirmed equivalence: its name only proposes, nothing enters the proposal.
    assert beta['company_id'] is None and beta['company_match'] == 'proposed' and beta['cells'] == []

    def get(header):
        return next(c for c in alfa['cells'] if c['header'] == header)

    assert get('ISR')['value']['status'] == 'fulfilled' and get('ISR')['value']['payment'] == 'paid'
    assert get('IVA')['value']['requires_review'] and get('IVA')['value']['original'] == 'OK OK OK'
    assert get('RETENCIONES')['value']['payment'] == 'not_applicable'  # CEROS beats CON PAGO
    assert get('ANUAL 2024')['period'] == '2024-A'
    assert get('REPSE')['value']['status'] == 'pending' and get('REPSE')['value']['warnings']
    assert get('IMPUESTO SOBRE NOMINA')['value']['propose_company_not_applicable']
    assert get('IMSS / PAGADO')['value']['status'] == 'unreviewed'  # NEGATIVO
    assert get('EJECUTA')['value']['responsible_name'] == 'Laura Gómez'
    assert get('REGIMEN')['value']['matches_company_regime'] is True
    assert get('EXPEDIENTE')['value']['requires_review']  # CONFIANZA as an obligation is only a note
    assert get('(sin encabezado K)')['conflicts'] == ['blank_header']
    assert get('COLUMNA NUEVA')['conflicts'] == ['unknown_header']
    assert get('BIMESTRAL RIF')['conflicts'] == ['not_added']


def test_invalid_workbooks_are_rejected():
    with pytest.raises(InvalidWorkbook):
        read_workbook(b'esto no es un xlsx')
    with pytest.raises(InvalidWorkbook):
        read_workbook(b'')
