from app.folder_groups import classify
from app.imss_groups import ImssIndex, component, month_from_name

BASE = 'EJERCICIO 2026/IMSS/'


def build(*paths):
    index = ImssIndex()
    for path in paths:
        index.add(path)
    return index.result()


def month(result, number):
    return next(m for m in result['months'] if m['m'] == number)


def test_components_and_month_from_names():
    cases = {
        'W2607801.SUA': 'sua',
        'SIPARE PRISMA.pdf': 'sipare',
        'SIAPRE CEMEX.pdf': 'sipare',  # typo seen in real folders
        'D6870905108_609801.pdf': 'sipare',  # the copy the SUA leaves in «Folio_…»
        'D6870905108_607801_Error.log': 'log',
        'resumen liquidacion_gbl.pdf': 'resumen',
        'cedula oportuno obr-pat_gbl.pdf': 'cedula',
        'cedula oportunobim obr-pat_gbl.pdf': 'cedula_bim',
        'CONSFRONTA VERDE VALLE.pdf': 'confronta',
        'ReporteDiferencias.pdf': 'diferencias',
        '20266_PD687090510_EBA_PDF.zip': 'eba',
        '20266_PD687090510_EMA_PDF.zip': 'ema',
        '20266_PD687090510_Excel.zip': 'excel',
        'Afil.TXT': 'idse_txt',
    }
    for name, comp in cases.items():
        assert component(BASE + name) == comp, name
        assert classify(BASE + '6.- JUNIO/' + name)[0] == 'imss', name
    assert month_from_name('W2607801.SUA') == (2026, 7)
    assert month_from_name('D6870905108_610801.pdf') == (2026, 10)
    assert month_from_name('202610_PD687090510_EMA_PDF.zip') == (2026, 10)
    assert month_from_name('20263_PD687090510_EMA_PDF.zip') == (2026, 3)


def test_complete_month_and_bimonthly_requirements():
    month_files = [
        'SIPARE X.pdf',
        'W2606801.SUA',
        'resumen liquidacion_gbl.pdf',
        'cedula oportuno obr-pat_gbl.pdf',
        'confronta.pdf',
    ]
    out = build(*[BASE + '6.- JUNIO/' + f for f in month_files])
    assert month(out, 6)['faltan'] == ['cedula_bim']  # June closes a bimester
    assert month(out, 6)['s'] == 'faltante'
    out = build(*[BASE + '5.- MAYO/' + f.replace('2606', '2605') for f in month_files])
    assert month(out, 5)['s'] == 'completo'  # May needs no bimestral cédula
    july = [BASE + '7.- JULIO/' + f.replace('2606', '2607') for f in month_files if f != 'confronta.pdf']
    out = build(*july, BASE + '7.- JULIO/ReporteDiferencias.pdf')
    assert month(out, 7)['s'] == 'completo'  # the reporte de diferencias stands in for the confronta


def test_folio_copies_log_note_and_multiple_folios():
    out = build(
        BASE + '8.- AGOSTO/W2608821.SUA',
        BASE + '8.- AGOSTO/D6870920107/Folio_1/W2608821.SUA',
        BASE + '8.- AGOSTO/D6870920107/Folio_1/D6870920107_608821_Error.log',
        BASE + '8.- AGOSTO/D6870920107/Folio_2/W2608821.SUA',
    )
    aug = month(out, 8)
    assert aug['s'] == 'revisar' and 'varios_folios' in aug['notas'] and 'log_error' in aug['notas']


def test_month_conflict_only_emissions_and_general_files():
    out = build(
        BASE + '9.- SEPTIEMBRE/W2607801.SUA',  # July's SUA filed under September
        BASE + '20263_PD687090510_EMA_PDF.zip',
        BASE + '20263_PD687090510_Excel.zip',
        'TRABAJADOR/IDSE_D687092010_Lote_440831899.zip',
        'Afil.TXT',
    )
    assert any(r['why'] == 'mes_distinto' for r in out['rows'])
    assert month(out, 3)['s'] == 'parcial' and month(out, 3)['faltan'][0] == 'sua'
    assert out['generales'] == 2 and out['registros'] == 2
