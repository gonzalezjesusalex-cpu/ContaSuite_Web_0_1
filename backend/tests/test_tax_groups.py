from app.folder_groups import classify
from app.tax_groups import TaxIndex, tax_kind

FED = 'EJERCICIO 2026/IMPUESTOS/FEDERALES/'
EST = 'EJERCICIO 2026/IMPUESTOS/ESTATALES/'


def build(*paths):
    index = TaxIndex()
    for path in paths:
        index.add(path)
    return index.result()


def row(result, name):
    return next(r for r in result['rows'] if r['p'].split('/')[-1] == name)


def test_kinds_and_group():
    assert tax_kind('1.- DECLARACION ISR E IVA ENERO X.pdf') == 'declaracion'
    assert tax_kind('DECLRACION 2DO BIMESTRE X.pdf') == 'declaracion'  # typo seen in real folders
    assert tax_kind('DEC26125220_h8Kef9.pdf') == 'declaracion'
    assert tax_kind('1.2.- ACUSE ISR E IVA ENERO X.pdf') == 'acuse'
    assert tax_kind('2DO BIMESTRE X.pdf') == 'otro'
    assert classify(FED + '1.- DECLARACION ISR E IVA ENERO X.pdf')[0] == 'impuestos'
    # the acuses of e.firma/CSD belong with the credentials, not with taxes
    assert classify('FIEL EMPRESA/01. FIEL_X/Acuse_renovacion (1).pdf')[0] == 'credenciales'


def test_federal_pairs_complementaria_and_missing():
    out = build(
        FED + '2.- DECLARACION ISR E IVA FEBRERO X.pdf',
        FED + '2.1.- DECLARACION COMPLEMENTARIA ISR E IVA FEBRERO X.pdf',
        FED + '2.2.- ACUSE ISR E IVA FEBRERO X.pdf',
        FED + '2.3.- ACUSE COMPLEMENTARIA ISR E IVA FEBRERO X.pdf',
        FED + '10.2.- ACUSE ISR E IVA OCTUBRE X.pdf',  # no declaration for October
        FED + '4.- DECLARACION ISR E IVA ABRIL X.pdf',  # no acuse for April
    )
    assert out['pairs'] == 2
    assert row(out, '2.- DECLARACION ISR E IVA FEBRERO X.pdf')['pair'].endswith('2.2.- ACUSE ISR E IVA FEBRERO X.pdf')
    assert row(out, '2.1.- DECLARACION COMPLEMENTARIA ISR E IVA FEBRERO X.pdf')['pair'].endswith(
        '2.3.- ACUSE COMPLEMENTARIA ISR E IVA FEBRERO X.pdf'
    )
    assert row(out, '10.2.- ACUSE ISR E IVA OCTUBRE X.pdf')['why'] == 'acuse_sin_declaracion'
    assert row(out, '4.- DECLARACION ISR E IVA ABRIL X.pdf')['why'] == 'declaracion_sin_acuse'


def test_extra_acuse_goes_to_review_and_qualifiers_must_match():
    out = build(
        FED + '10.- DECLARACION ISR E IVA OCTUBRE X.pdf',
        FED + '10.2.- ACUSE ISR E IVA OCTUBRE X.pdf',
        FED + '10.2.1.- ACUSE ISR E IVA OCTUBRE X.pdf',
        FED + '5.- DECLARACION ISR E IVA MAYO X.pdf',
        FED + '5.2.- ACUSE ISR E IVA MAYO X.pdf',
        FED + '5.3.- ACUSE ISR E IVA MAYO X RESICO.pdf',
    )
    assert row(out, '10.2.1.- ACUSE ISR E IVA OCTUBRE X.pdf')['s'] == 'revisar'
    assert row(out, '5.3.- ACUSE ISR E IVA MAYO X RESICO.pdf')['why'] == 'acuse_sin_declaracion'


def test_state_bimestre_and_inferred_acuse():
    out = build(
        EST + 'DECLRACION 2DO BIMESTRE X.pdf',
        EST + '2DO BIMESTRE X.pdf',
        EST + 'DEC26125220_h8Kef9.pdf',
    )
    acuse = row(out, '2DO BIMESTRE X.pdf')
    assert acuse['d'] == 'acuse' and acuse['inf'] and acuse['pair'].endswith('DECLRACION 2DO BIMESTRE X.pdf')
    assert row(out, 'DEC26125220_h8Kef9.pdf')['why'] == 'sin_periodo'


def test_pairs_never_cross_folders():
    out = build(
        'A/DECLARACION ANUAL 2024.pdf',
        'B/ACUSE ANUAL 2024.pdf',
    )
    assert out['pairs'] == 0 and out['faltantes'] == 2
