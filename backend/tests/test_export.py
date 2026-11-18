import hashlib
import importlib.util
from pathlib import Path

import pytest

from test_api import client  # noqa: F401  Isolated environment before app imports.
from test_agent_links import beat, bearer, office, pair  # noqa: F401
from test_accounts import login
from test_permissions import account
from app.export_plan import (
    DEFAULT_INCLUDE,
    SECTIONS,
    build_plan,
    destination_problem,
    manifest_text,
    preview,
    safe_name,
    safe_part,
)
from app.folder_groups import CfdiIndex, cfdi_info
from app.imss_groups import ImssIndex
from app.tax_groups import TaxIndex


def load_agent():
    spec = importlib.util.spec_from_file_location('export_test_agent', Path(__file__).parents[2] / 'agent/agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_names_are_safe_for_windows():
    assert safe_part('a<b>c:d|e?f*') == 'a_b_c_d_e_f_'
    assert safe_part('CON') == '_CON' and safe_part('nul.txt') == '_nul.txt'
    assert safe_part('..') == '_' and safe_part('  ') == '_' and safe_part('termina. ') == 'termina'
    long = safe_name('x' * 300 + '.pdf', 60)
    assert len(long) <= 60 and long.endswith('.pdf')


def test_destination_must_be_new_ground_inside_authorized_roots_and_apart_from_the_source():
    roots, source = [r'C:\Empresas'], r'C:\Empresas\Acme'
    assert destination_problem(r'C:\Empresas\Exportaciones\Acme', source, roots) is None
    assert destination_problem(r'c:/empresas/exportaciones/acme', source, roots) is None
    cases = {
        r'Exportaciones': 'destino_no_absoluto',
        r'\\servidor\comparte\x': 'destino_unc',
        r'C:\Otro\Acme': 'destino_fuera_de_raices',
        r'C:\Empresas2\Acme': 'destino_fuera_de_raices',
        r'C:\Empresas\Acme\Copia': 'destino_dentro_origen',
        r'C:\Empresas\Acme': 'destino_dentro_origen',
        r'C:\Empresas': 'origen_dentro_destino',
        r'C:\Empresas\..\Windows': 'destino_invalido',
        r'C:\Empresas\a|b': 'destino_invalido',
    }
    for destination, code in cases.items():
        assert destination_problem(destination, source, roots) == code, destination
    assert destination_problem(r'C:\Empresas\X', source, []) == 'destino_fuera_de_raices'


def test_plan_excludes_secrets_leaves_workers_out_and_keeps_unplaced_folders():
    entries = [
        ('FIEL/llave.key', 10, 'credenciales'),
        ('FIEL/clave.cer', 10, 'credenciales'),
        ('FIEL/CONTRASEÑA.txt', 5, 'contrasenas'),
        ('Thumbs.db', 1, 'ruido'),
        ('TRABAJADOR/01.- ANA/INE.pdf', 7, 'trabajadores'),
        ('Notas/ideas.txt', 3, 'otros'),
        ('EJERCICIO 2026/IMPUESTOS/1.- DECLARACION.pdf', 9, 'impuestos'),
    ]
    maps = [{'EJERCICIO 2026/IMPUESTOS/1.- DECLARACION.pdf': ('Impuestos', 'Federales', '2026', '01.- ENERO')}]
    plan = build_plan(entries, maps)
    assert plan['excluded'] == {'credenciales': 2, 'contrasenas': 1, 'ruido': 1}
    assert plan['omitted'] == {'trabajadores': 1}  # personal data only when asked for
    places = {i.key: '/'.join((*i.parts, i.name)) for i in plan['items']}
    assert places['Notas/ideas.txt'] == 'Sin clasificar/Notas/ideas.txt'
    assert places['EJERCICIO 2026/IMPUESTOS/1.- DECLARACION.pdf'] == 'Impuestos/Federales/2026/01.- ENERO/1.- DECLARACION.pdf'
    with_workers = build_plan(entries, maps, include=[*DEFAULT_INCLUDE, 'trabajadores'])
    assert any(i.section == 'trabajadores' for i in with_workers['items'])
    # A key is never exported even if it was mislabelled as another group.
    assert build_plan([('x/clave.key', 1, 'otros')], [])['items'] == []
    assert set(SECTIONS) >= set(DEFAULT_INCLUDE)


def test_each_index_gives_the_virtual_folders_of_every_file():
    cfdi = (
        b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="2026-07-02T10:00:00" TipoDeComprobante="I">'
        b'<cfdi:Emisor Rfc="AAA010101AAA"/><cfdi:Receptor Rfc="BBB010101BBB"/>'
    )
    index = CfdiIndex('AAA010101AAA')
    uuid = 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
    index.add_xml(f'CFDI/EMITIDOS/{uuid}.xml', cfdi_info(cfdi))
    index.add_pdf(f'CFDI/EMITIDOS/{uuid}.pdf')
    index.add_xml('suelto/x.xml', None)
    virtual = index.virtual()
    assert virtual[f'CFDI/EMITIDOS/{uuid}.xml'] == ('CFDI', '2026', '07.- JULIO', 'EMITIDOS')
    assert virtual[f'CFDI/EMITIDOS/{uuid}.pdf'] == ('CFDI', '2026', '07.- JULIO', 'EMITIDOS')
    assert virtual['suelto/x.xml'] == ('CFDI', 'Por revisar')

    taxes = TaxIndex()
    for path in ['EJERCICIO 2026/IMPUESTOS/FEDERALES/1.- DECLARACION ISR ENERO X.pdf', 'ACUSE ISN 4TO BIMESTRE X.pdf']:
        taxes.add(path)
    out = taxes.virtual()
    assert out['EJERCICIO 2026/IMPUESTOS/FEDERALES/1.- DECLARACION ISR ENERO X.pdf'] == ('Impuestos', 'Federales', '2026', '01.- ENERO')
    assert out['ACUSE ISN 4TO BIMESTRE X.pdf'][:2] == ('Impuestos', 'Estatales') and out['ACUSE ISN 4TO BIMESTRE X.pdf'][-1] == 'Bimestre 4'

    imss = ImssIndex()
    for path in ['EJERCICIO 2026/IMSS/7.- JULIO/W2607801.SUA', 'EJERCICIO 2026/IMSS/7.- JULIO/D1/Folio_9/W2607801.SUA', 'Afil.TXT']:
        imss.add(path)
    out = imss.virtual()
    assert out['EJERCICIO 2026/IMSS/7.- JULIO/W2607801.SUA'] == ('IMSS', '2026', '07.- JULIO')
    assert out['EJERCICIO 2026/IMSS/7.- JULIO/D1/Folio_9/W2607801.SUA'] == ('IMSS', '2026', '07.- JULIO', 'Folios', 'Folio_9')
    assert out['Afil.TXT'] == ('IMSS', 'General')


def test_manifest_blocks_formula_injection():
    text = manifest_text([('Copiado', 'cfdi', 'CFDI/ok.xml', '=cmd|calc.xml', 'abc', 3, '+SUMA(1)')])
    assert "'=cmd|calc.xml" in text and "'+SUMA(1)" in text and text.startswith('estado,')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture()
def folder(tmp_path):
    root = tmp_path / 'empresas'
    company = root / 'Acme'
    uuid = 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
    (company / 'EJERCICIO 2026' / 'CFDI' / 'JULIO' / 'EMITIDOS').mkdir(parents=True)
    (company / 'EJERCICIO 2026' / 'IMPUESTOS' / 'FEDERALES').mkdir(parents=True)
    (company / 'FIEL').mkdir()
    (company / 'TRABAJADOR' / '01.- ANA').mkdir(parents=True)
    xml = (
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="2026-07-02T10:00:00" TipoDeComprobante="I" '
        'Total="116.00"><cfdi:Emisor Rfc="AAA010101AAA"/><cfdi:Receptor Rfc="BBB010101BBB"/></cfdi:Comprobante>'
    )
    (company / 'EJERCICIO 2026' / 'CFDI' / 'JULIO' / 'EMITIDOS' / f'{uuid}.xml').write_text(xml)
    (company / 'EJERCICIO 2026' / 'CFDI' / 'JULIO' / 'EMITIDOS' / f'{uuid}.pdf').write_bytes(b'%PDF factura')
    (company / 'EJERCICIO 2026' / 'IMPUESTOS' / 'FEDERALES' / '1.- DECLARACION ISR E IVA ENERO ACME.pdf').write_bytes(b'decl')
    (company / 'EJERCICIO 2026' / 'IMPUESTOS' / 'FEDERALES' / '1.2.- ACUSE ISR E IVA ENERO ACME.pdf').write_bytes(b'acuse')
    (company / 'FIEL' / 'llave.key').write_bytes(b'SECRETO-LLAVE')
    (company / 'FIEL' / 'CONTRASEÑA.txt').write_bytes(b'SECRETO-CLAVE')
    (company / 'TRABAJADOR' / '01.- ANA' / 'INE.pdf').write_bytes(b'ine de ana')
    (company / 'notas.txt').write_bytes(b'notas sueltas')
    (company / 'Thumbs.db').write_bytes(b'x')
    return root, company


def run(agent, company, roots, destination, apply, include=None):
    payload = {'folder': str(company), 'rfc': 'AAA010101AAA', 'destination': str(destination), 'apply': apply}
    if include is not None:
        payload['include'] = include
    return agent.run_job({'id': 'job', 'kind': 'export_virtual', 'payload': payload}, [str(r) for r in roots])


def test_export_end_to_end_copies_verified_without_touching_originals_or_secrets(folder):
    root, company = folder
    agent = load_agent()
    destination = root / 'Exportaciones' / 'Acme'  # its parent does not exist yet
    before = {p: sha(p) for p in company.rglob('*') if p.is_file()}

    status, result = run(agent, company, [root], destination, apply=False)
    assert status == 'completed' and result['mode'] == 'preview', result
    assert not destination.exists()  # a preview writes nothing
    assert result['total'] == 5  # xml, pdf, 2 impuestos, notas, and nothing else (workers off, secrets never)
    assert result['excluded'] == {'credenciales': 1, 'contrasenas': 1, 'ruido': 1} and result['omitted'] == {'trabajadores': 1}

    status, done = run(agent, company, [root], destination, apply=True)
    assert status == 'completed' and done['copiados'] == 5 and done['errores'] == 0, done
    month = destination / 'CFDI' / '2026' / '07.- JULIO' / 'EMITIDOS'
    assert sorted(p.suffix for p in month.iterdir()) == ['.pdf', '.xml']
    assert (destination / 'Impuestos' / 'Federales' / '2026' / '01.- ENERO' / '1.2.- ACUSE ISR E IVA ENERO ACME.pdf').is_file()
    assert (destination / 'Sin clasificar' / 'notas.txt').read_bytes() == b'notas sueltas'
    copied = [p for p in destination.rglob('*') if p.is_file()]
    assert not [p for p in copied if p.suffix in {'.key', '.part'} or 'CONTRASE' in p.name.upper() or p.name == 'INE.pdf']
    assert b'SECRETO' not in b''.join(p.read_bytes() for p in copied)
    assert 'sha256' in (destination / done['manifiesto']).read_text(encoding='utf-8-sig').splitlines()[0]
    assert {p: sha(p) for p in company.rglob('*') if p.is_file()} == before  # originals untouched

    # Nothing is ever overwritten: a second export into the same place is refused.
    status, again = run(agent, company, [root], destination, apply=True)
    assert status == 'failed' and again['error_code'] == 'destino_no_vacio'


def test_export_refuses_a_destination_outside_the_roots_or_inside_the_source(folder, tmp_path):
    root, company = folder
    agent = load_agent()
    for destination, code in [
        (tmp_path / 'fuera' / 'Acme', 'destino_fuera_de_raices'),
        (company / 'Copia', 'destino_dentro_origen'),
    ]:
        status, result = run(agent, company, [root], destination, apply=False)
        assert status == 'failed' and result['error_code'] == code, (destination, result)
    assert not (tmp_path / 'fuera').exists()


def test_export_with_workers_name_collisions_and_changed_selection(folder):
    root, company = folder
    agent = load_agent()
    # Same virtual place, same name: identical content is skipped, different content is kept with a number.
    for sub, text in [('a', b'igual'), ('b', b'igual'), ('c', b'distinto')]:
        (company / 'Notas' / sub).mkdir(parents=True, exist_ok=True)
        (company / 'Notas' / sub / 'x.txt').write_bytes(text)
    destination = root / 'Copia'
    status, done = run(agent, company, [root], destination, apply=True, include=['sin_clasificar', 'trabajadores'])
    assert status == 'completed', done
    assert (destination / 'Trabajadores' / 'ANA' / 'INE.pdf').is_file()
    assert not (destination / 'CFDI').exists()  # not selected
    assert done['errores'] == 0


def test_export_job_is_its_own_permission_and_validates_the_destination(office):  # noqa: F811
    c, companies, ana = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    scan_with_destination = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder', 'destination': r'C:\Empresas\X'})
    assert scan_with_destination.status_code == 422
    no_destination = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'export_virtual'})
    assert no_destination.status_code == 422
    for destination, text in [
        (r'D:\Fuera\A', 'autorizadas'),
        (r'C:\Empresas\A\Copia', 'dentro de la carpeta'),
        ('Exportaciones', 'ruta completa'),
    ]:
        refused = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'export_virtual', 'destination': destination})
        assert refused.status_code == 422 and text in refused.json()['detail'], (destination, refused.text)
    ok = c.post(
        '/api/jobs',
        json={'company_id': companies['a'], 'kind': 'export_virtual', 'destination': r'C:\Empresas\Exportaciones\A', 'apply': False},
    )
    assert ok.status_code == 201 and ok.json()['kind'] == 'export_virtual', ok.text
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed['payload']['destination'] == r'C:\Empresas\Exportaciones\A' and claimed['payload']['apply'] is False
    assert all('payload' not in j for j in c.get('/api/state').json()['jobs'])  # only administrators see paths


def test_an_auxiliar_without_the_export_action_cannot_export(office):  # noqa: F811
    c, companies, _ = office
    account(c, 'beto', 'auxiliar', [(companies['a'], 'write')], actions=[(companies['a'], 'carpeta.analizar')])
    login(c, 'beto')
    _, token = pair(c, agent_id='pc-beto', machine='PC-BETO')
    beat(c, token, agent_id='pc-beto')
    denied = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'export_virtual', 'destination': r'C:\Empresas\Exportaciones\A'})
    assert denied.status_code == 403
    assert c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'}).status_code == 201
