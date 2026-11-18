from app.expediente_groups import ExpedienteIndex, doc_type
from app.finance_groups import FinanceIndex, report_type, year_and_month
from app.folder_groups import classify
from app.payroll_groups import PayrollIndex, WorkersIndex, quincena_label


def test_classification_of_workers_credentials_and_company_documents():
    cases = {
        'TRABAJADOR/01 ROSARIO MORALES/01.-INE ROSARIO.docx': 'trabajadores',  # singular folder name
        'TRABAJADORES/02.- X/ALTA IMSS.pdf': 'trabajadores',
        'DOCUMENTOS DEL TRABAJADOR IMSS/CSF_RIHA9306202BA- ADAN.pdf': 'trabajadores',
        'TRABAJADOR.zip': 'trabajadores',
        'USUARIO INFONAVIT.txt': 'contrasenas',
        'ACCESOS NARIJ.zip': 'contrasenas',
        'TARJETA PATRONAL IMSS VERDE VALLE.pdf': 'legal',
        'OBJETO SOCIAL.pdf': 'legal',
        'REPSE/RECIBO TELMEX MAYO 26.pdf': 'legal',
        'ESTADOS FINANCIEROS/BALANZA DE COMPROBACION 2026.pdf': 'estados_financieros',
    }
    for path, group in cases.items():
        assert classify(path)[0] == group, path


def test_expediente_checklist_and_foreign_csf():
    types = {
        '04.-RPC ACTA ASAMBLEA NARIJ.pdf': 'rpc',  # RPC wins over acta
        'acta narij imss.pdf': 'acta',
        'ACTAPROTOCOLIZADA.pdf': 'acta',
        'Csf_CNA100811RP8.pdf': 'csf',
        '02.-TIP CEMEX.pdf': 'patronal',
        'REGISTR OREPSE CEMEX.pdf': 'repse',
        'INE FRENTE.pdf': 'ine',
    }
    for name, kind in types.items():
        assert doc_type(name) == kind, name
    index = ExpedienteIndex('MPM250210G95')
    for path in ['01.-ACTA X.pdf', '02.-RPC X.pdf', 'Csf_MPM250210G95.pdf', 'Csf_DCE260129K88.pdf', '01.- OSIRIS/CSF- OSIRIS.pdf']:
        index.add(path)
    out = index.result()
    assert out['faltan'] == ['patronal', 'ine']  # the person's folder does not satisfy company documents
    assert [r['p'] for r in out['rows'] if r['s'] == 'revisar'] == ['Csf_DCE260129K88.pdf']


def test_finance_types_years_and_scopes():
    assert report_type('ANALITICAS DE BALANCE 24.pdf') == 'analiticas'
    assert report_type('BALANCE GENERAL 24.pdf') == 'balance'
    assert year_and_month('BALANCE GENERAL 24.pdf') == (2024, None)
    assert year_and_month('CNA100811RP8.38.2026-7.pdf') == (2026, 7)
    assert year_and_month('CNA100811RP8.36.2023.xlsx') == (2023, None)
    index = FinanceIndex()
    index.add('ESTADOS FINANCIEROS/MUNICIPIO OAXACA/FLUJO DE EFECTIVO 25.pdf')
    index.add('ESTADOS FINANCIEROS/LIBRO DIARIO.pdf')
    scopes = {r['p'].split('/')[-1]: r['o'] for r in index.result()['rows']}
    assert scopes == {'FLUJO DE EFECTIVO 25.pdf': 'MUNICIPIO OAXACA', 'LIBRO DIARIO.pdf': ''}


def test_payroll_quincenas_pair_xml_with_recibo_and_find_gaps():
    folder = 'EJERCICIO 2026/NOMINA/13.- 1ERA QNA JULIO/'
    index = PayrollIndex()
    index.add_xml(folder + 'RE_1_Quincenal_2026_13_001_AAA.xml')
    index.add_pdf(folder + 'RE_1_Quincenal_2026_13_001_AAA.pdf')
    index.add_xml(folder + 'RE_1_Quincenal_2026_13_002_BBB.xml')  # recibo missing
    index.add_xml('EJERCICIO 2026/NOMINA/16.- 2DA QNA AGOSTO/RE_1_Quincenal_2026_16_001_CCC.xml')
    index.add_pdf('EJERCICIO 2026/NOMINA/16.- 2DA QNA AGOSTO/RE_1_Quincenal_2026_16_001_CCC.pdf')
    out = index.result()
    first = out['quincenas'][0]
    assert (first['q'], first['paired'], first['sin_pdf'], first['s']) == (13, 1, 1, 'faltante')
    assert out['huecos'] == [14, 15]
    assert quincena_label(13).startswith('1.ª quincena de Julio')


def test_workers_checklist():
    index = WorkersIndex()
    for path in [
        'TRABAJADOR/01.- ANA PEREZ/ALTA IMSS.pdf',
        'TRABAJADOR/01.- ANA PEREZ/INE.pdf',
        'TRABAJADOR/02 LUIS DIAZ/DOCUMENTOS LUIS.pdf',
        'TRABAJADOR.zip',
    ]:
        index.add(path)
    out = index.result()
    by_name = {w['w']: w for w in out['workers']}
    assert by_name['ANA PEREZ']['faltan'] == ['nss', 'csf']
    assert by_name['LUIS DIAZ']['faltan'] == []  # one combined file stands for the set
    assert by_name['']['faltan'] == [] and out['personas'] == 2
