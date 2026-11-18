import importlib.util
from pathlib import Path

from app.folder_groups import cfdi_tipo, classify


def load_agent():
    spec = importlib.util.spec_from_file_location('groups_test_agent', Path(__file__).parents[2] / 'agent/agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classify_by_type_and_folder():
    uuid = '0215C122-B88B-4A2D-B5EB-7B59B376D296'
    cases = {
        'EJERCICIO 2026/CFDI/10.- OCTUBRE/RECIBIDOS/' + uuid + '.pdf': 'cfdi_pdf',
        'EJERCICIO 2026/CFDI/10.- OCTUBRE/Emitidos-SEP250207KK0-202610.xls': 'sat_reportes',
        'EJERCICIO 2026/IMPUESTOS/FEDERALES/1.- DECLARACION ISR E IVA ENERO.pdf': 'impuestos',
        'EJERCICIO 2026/IMSS/07.- JULIO/W2607801.SUA': 'imss',
        'Afil.TXT': 'imss',
        'ESTADOS FINANCIEROS/ESTADOS FINANCIEROS 2026.xlsx': 'estados_financieros',
        'Csf_SEP250207KK0.pdf': 'legal',
        '1.-ACTA CONSTITUTIVA-PRISMA.pdf': 'legal',
        'INE FRENTE.docx': 'identificaciones',
        'FIEL RL/clave.key': 'credenciales',
        'FIEL RL/archivo.cer': 'credenciales',
        'FIEL RL CEMEX.zip': 'credenciales',
        'SELLO DIGITAL/CONTRASEN╠âA PRISMA.txt': 'contrasenas',
        'FIEL RL/CONTRA_1.DOC': 'contrasenas',
        'Thumbs.db': 'ruido',
        'IMPUESTOS - Acceso directo.lnk': 'ruido',
        'notas.pdf': 'otros',
    }
    for path, group in cases.items():
        assert classify(path)[0] == group, path


def test_cfdi_tipo_from_header():
    cfdi = b'<?xml version="1.0"?><cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Version="4.0" TipoDeComprobante="N">'
    assert cfdi_tipo(cfdi) == 'N'
    assert cfdi_tipo(b'<html><body>no es cfdi</body></html>') == ''
    assert classify('a.xml', 0, 'P') == ('cfdi_xml', 'Pago')
    assert classify('a.xml', 0, '') == ('cfdi_xml', 'XML que no es CFDI')


def test_agent_groups_every_type_and_never_names_or_opens_secrets(tmp_path):
    root = tmp_path / 'empresa'
    (root / 'CFDI').mkdir(parents=True)
    (root / 'FIEL').mkdir()
    head = b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="I" Version="4.0"/>'
    (root / 'CFDI' / 'factura.xml').write_bytes(head)
    (root / 'CFDI' / 'Recibidos-AAA010101AAA-202601.xls').write_bytes(b'x')
    (root / 'W2601.SUA').write_bytes(b'x')
    (root / 'FIEL' / 'llave.key').write_bytes(b'SECRETO')
    (root / 'FIEL' / 'CONTRASEÑA.txt').write_bytes(b'SECRETO')
    result = load_agent().safe_inventory(str(root), [str(root)])
    summary = result['summary']
    groups = {g['key']: g for g in summary['groups']}
    assert summary['total'] == 5
    assert groups['cfdi_xml']['subgroups'] == {'Ingreso': 1}
    assert groups['sat_reportes']['count'] == 1 and groups['imss']['count'] == 1
    for key in ('credenciales', 'contrasenas'):
        assert groups[key]['sensitive'] and groups[key]['count'] == 1 and groups[key]['examples'] == []
    assert 'llave.key' not in str(result) and 'SECRETO' not in str(result) and 'CONTRASE' not in str(result)
    assert (root / 'FIEL' / 'llave.key').read_bytes() == b'SECRETO'


def test_folder_names_and_cfdi_placement():
    from app.folder_groups import CfdiIndex, cfdi_info, folder_context, month_of_folder, place_cfdi

    for name, month in {'07.- JULIO': 7, '09- SEPTIEMBRE': 9, '1.- ENERO': 1, '08.-AGOSTO': 8, '3.- ABRIL': None}.items():
        assert month_of_folder(name)[1] == month, name
    assert month_of_folder('2026-01') == (2026, 1)
    assert folder_context('EJERCICIO 2026/CFDI/09- SEPTIEMBRE/RECIBIDAS/a.xml') == (2026, 9, 'R')
    head = (
        b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="2026-03-05T10:00:00" TipoDeComprobante="I">'
        b'<cfdi:Emisor Rfc="AAA010101AAA"/><cfdi:Receptor Nombre="x" Rfc="BBB010101BBB"/>'
    )
    info = cfdi_info(head)
    assert (info['month'], info['tipo'], info['emisor'], info['receptor']) == ((2026, 3), 'I', 'AAA010101AAA', 'BBB010101BBB')
    ok = place_cfdi('EJERCICIO 2026/CFDI/03.- MARZO/RECIBIDOS/a.xml', info, 'BBB010101BBB')
    assert (ok['m'], ok['k'], ok['s']) == (3, 'R', 'ok')
    assert place_cfdi('EJERCICIO 2026/CFDI/04.- ABRIL/RECIBIDOS/a.xml', info, 'BBB010101BBB')['why'] == 'mes_distinto'
    assert place_cfdi('EJERCICIO 2026/CFDI/03.- MARZO/EMITIDOS/a.xml', info, 'BBB010101BBB')['why'] == 'tipo_distinto'
    assert place_cfdi('a.xml', info, 'CCC010101CCC')['why'] == 'rfc_ajeno'
    assert place_cfdi('a.xml', None, 'BBB010101BBB')['why'] == 'xml_ilegible'
    index = CfdiIndex('BBB010101BBB')
    index.add_xml('F/03.- MARZO/RECIBIDOS/u1.xml', info)
    index.add_pdf('F/03.- MARZO/RECIBIDOS/U1.pdf')  # same name: inherits the XML's place
    index.add_pdf('suelto.pdf')  # no evidence: goes to review
    out = index.result()
    assert (out['ok'], out['revisar']) == (2, 1)
