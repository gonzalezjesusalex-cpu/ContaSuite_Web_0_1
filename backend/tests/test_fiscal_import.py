"""Excel «Control de obligaciones»: sheet periods, headers, dictionary and PAGO proposals (cambios 3A.1-3A.3)."""

from datetime import date

from app.fiscal_import import classify, normalize_header, preview, propose, resolve_header, sheet_period

CATALOG = [
    dict(id='isr', label='ISR'),
    dict(id='iva', label='IVA'),
    dict(id='ret', label='Retenciones'),
    dict(id='imss', label='IMSS'),
    dict(id='anual', label='Declaración anual'),
    dict(id='fed', label='Pago impuestos federales'),
    dict(id='repse', label='REPSE'),
]
COMPANY = dict(id='c1', rfc='AAA010101AA1', name='Empresa Uno SA', regimes=['Régimen General de Ley'])


def test_sheet_period_abbreviations_and_two_digit_years():
    assert sheet_period('OCT 26') == '2026-10'
    assert sheet_period('OCT20') == '2020-10'
    assert sheet_period('ABRIL 26') == '2026-04'
    assert sheet_period('SEP 26') == '2026-09'
    assert sheet_period('SEPT 26') == '2026-09'
    assert sheet_period('ENE 22') == '2022-01'
    assert sheet_period('Noviembre 2026') == '2026-11'
    assert sheet_period('2026-11') == '2026-11'
    assert sheet_period('Resumen') is None
    assert sheet_period('Noviembre') is None


def test_header_normalization_and_aliases():
    assert normalize_header(' IMSS  /  PAGADO ') == 'imss pagado'
    assert resolve_header('IMSS/ENVIADO')['label'] == 'IMSS'
    assert resolve_header('ISR ')['label'] == 'ISR'
    assert resolve_header('IMPUESTO SOBRE NOMINA ')['label'] == 'Impuesto sobre Nómina'
    assert resolve_header('OPINION BUZON')['label'].startswith('Buzón')
    annual = resolve_header('ANUAL 2024')
    assert annual['label'] == 'Declaración anual' and annual['year'] == 2024
    assert resolve_header('DECLARACION ANUAL')['label'] == 'Declaración anual'
    assert resolve_header('BIMESTRAL RIF') == dict(role='unknown', reason='not_added')
    assert resolve_header('')['role'] == 'unknown'
    assert resolve_header('COLUMNA RARA')['reason'] == 'unknown_header'
    assert resolve_header('EJECUTA')['role'] == 'responsible'


def test_value_dictionary_keeps_original_literal():
    assert propose(date(2026, 10, 17))['status'] == 'fulfilled'
    assert propose(date(2026, 10, 17))['submitted_at'] == '2026-10-17'
    assert propose('NA')['status'] == 'not_applicable'
    assert propose(None)['status'] == 'pending'
    ok = propose('OK OK OK')
    assert ok['status'] == 'fulfilled' and ok['requires_review'] and ok['original'] == 'OK OK OK'
    assert propose('CEROS')['payment'] == 'not_applicable' and propose('CEROS')['status'] == 'fulfilled'
    assert propose('SIN FIEL')['status'] == 'pending' and 'FIEL' in propose('SIN FIEL')['warnings'][0]
    no = propose('NO SE LLEVARAN')
    assert no['status'] == 'not_applicable' and no['propose_company_not_applicable'] and no['requires_confirmation']
    assert propose('CONFIANZA')['requires_review']
    person = propose('María Pérez')
    assert person['kind'] == 'person' and person['status'] == 'pending' and person['requires_confirmation']
    other = propose('NEGATIVO')
    assert other['status'] == 'unreviewed' and other['requires_review'] and other['kind'] == 'text'
    assert propose('12345')['status'] == 'unreviewed'
    assert propose('RESICO', 'regime')['interpreted'] == 'resico'
    assert propose('CONFIANZA', 'regime')['interpreted'] == 'resico'
    assert classify('texto')['kind'] == 'text'  # generic classification used by company diagnostics is unchanged


def sheet(**cells):
    return [dict(name='OCT 26', rows=[dict(number=2, rfc=COMPANY['rfc'], name='', cells=cells)])]


def cell(data, header):
    return next(c for c in data[0]['cells'] if c['header'] == header)


def test_payment_applies_to_isr_iva_retenciones_only():
    data = preview(
        sheet(ISR=date(2026, 11, 10), IVA='OK', Retenciones=None, IMSS=date(2026, 11, 3), PAGO='CON PAGO'),
        [COMPANY],
        CATALOG,
    )
    assert cell(data, 'ISR')['value']['payment'] == 'pending'
    assert cell(data, 'IVA')['value']['payment'] == 'pending'
    assert cell(data, 'Retenciones')['value']['payment'] == 'pending'
    assert 'payment' not in cell(data, 'IMSS')['value']
    assert not any('payment_obligation_required' in c['conflicts'] for c in data[0]['cells'])


def test_sin_pago_and_paid_only_with_federal_payment_date():
    data = preview(sheet(ISR=date(2026, 11, 10), PAGO='SIN PAGO'), [COMPANY], CATALOG)
    assert cell(data, 'ISR')['value']['payment'] == 'not_applicable'
    unpaid = preview(sheet(ISR=date(2026, 11, 10), PAGO='CON PAGO', **{'PAGO IMPUESTOS FED': None}), [COMPANY], CATALOG)
    assert cell(unpaid, 'ISR')['value']['payment'] == 'pending'
    paid = preview(
        sheet(ISR=date(2026, 11, 10), PAGO='CON PAGO', **{'PAGO IMPUESTOS FED': date(2026, 11, 17)}),
        [COMPANY],
        CATALOG,
    )
    assert cell(paid, 'ISR')['value']['payment'] == 'paid'
    # A date under PAGO alone is not a payment proof.
    dated = preview(sheet(ISR=date(2026, 11, 10), PAGO=date(2026, 11, 12)), [COMPANY], CATALOG)
    assert cell(dated, 'ISR')['value']['payment'] == 'pending'


def test_annual_header_year_and_unknown_columns_are_reported():
    data = preview(sheet(**{'ANUAL 2024': date(2025, 4, 30), '': 'x', 'BIMESTRAL RIF': 'OK'}), [COMPANY], CATALOG)
    assert cell(data, 'ANUAL 2024')['period'] == '2024-A'
    assert cell(data, '')['conflicts'] == ['blank_header']
    assert cell(data, 'BIMESTRAL RIF')['conflicts'] == ['not_added']


def test_name_match_is_only_a_proposal_until_confirmed():
    row = [dict(name='OCT 26', rows=[dict(number=2, name='EMPRESA UNO SA', cells={'ISR': 'OK'})])]
    unconfirmed = preview(row, [COMPANY], CATALOG)
    assert unconfirmed[0]['company_id'] is None and unconfirmed[0]['company_match'] == 'proposed'
    assert unconfirmed[0]['cells'] == [] and 'company_not_confirmed' in unconfirmed[0]['conflicts']
    confirmed = preview(row, [COMPANY], CATALOG, equivalences={'empresa uno sa': 'c1'})
    assert confirmed[0]['company_id'] == 'c1' and confirmed[0]['company_match'] == 'confirmed'
    assert confirmed[0]['cells'][0]['value']['status'] == 'fulfilled'
    clone = [COMPANY, dict(COMPANY, id='c2', rfc='BBB010101BB1')]
    assert preview(row, clone, CATALOG)[0]['company_match'] == 'ambiguous'
