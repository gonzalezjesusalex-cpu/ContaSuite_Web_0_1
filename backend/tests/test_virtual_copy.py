import hashlib
import importlib.util
from pathlib import Path

import pytest

from test_api import client  # noqa: F401  Isolated environment before app imports.
from test_agent_links import beat, bearer, office, pair  # noqa: F401
from test_accounts import login
from test_permissions import account
from app import virtual_blobs
from app.database import SessionLocal
from app.models import VirtualFile

UUID = 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
XML = (
    '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="2026-07-02T10:00:00" TipoDeComprobante="I" '
    'Total="116.00"><cfdi:Emisor Rfc="AAA010101AAA"/><cfdi:Receptor Rfc="BBB010101BBB"/></cfdi:Comprobante>'
)
SECTIONS = ['cfdi', 'impuestos']


def load_agent():
    spec = importlib.util.spec_from_file_location('copy_test_agent', Path(__file__).parents[2] / 'agent/agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def folder(tmp_path):
    company = tmp_path / 'Acme'
    (company / 'CFDI' / 'JULIO' / 'EMITIDOS').mkdir(parents=True)
    (company / 'IMPUESTOS' / 'FEDERALES').mkdir(parents=True)
    (company / 'FIEL').mkdir()
    (company / 'CFDI' / 'JULIO' / 'EMITIDOS' / f'{UUID}.xml').write_text(XML)
    (company / 'CFDI' / 'JULIO' / 'EMITIDOS' / f'{UUID}.pdf').write_bytes(b'%PDF-1.4 factura')
    (company / 'IMPUESTOS' / 'FEDERALES' / '1.- DECLARACION ISR E IVA ENERO ACME.pdf').write_bytes(
        b'%PDF-1.4 declaracion'
    )
    (company / 'notas.txt').write_bytes(b'notas sueltas')  # section sin_clasificar: not selected below
    (company / 'FIEL' / 'llave.key').write_bytes(b'SECRETO-LLAVE')
    return tmp_path, company


def sha(data):
    return hashlib.sha256(data).hexdigest()


def analyze(c, token, company_id, agent, root, company, copy=SECTIONS):
    """One analysis with an internal copy, as the real agent does it against the real server."""
    body = {'company_id': company_id, 'kind': 'scan_folder'}
    if copy is not None:
        body['copy'] = copy
    created = c.post('/api/jobs', json=body)
    assert created.status_code == 201, created.text
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed['id'] == created.json()['id']
    result = agent.safe_inventory(str(company), [str(root)], 'AAA010101AAA', with_index=True, copy=copy)

    def post(path, data):
        r = c.post('/api' + path, headers=bearer(token), json=data)
        assert r.status_code == 200, (path, r.text)
        return r.json()

    def put(path, data):
        r = c.put('/api' + path, headers=bearer(token), content=data)
        assert r.status_code == 200, (path, r.text)
        return r.json()

    agent.send_index(post, claimed['id'], 'pc-ana', result)
    agent.send_copies(post, put, claimed['id'], 'pc-ana', result)
    done = c.post(
        '/api/agent/jobs/' + claimed['id'] + '/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': result},
    )
    assert done.status_code == 200, done.text
    return result


def summary(c, company_id):
    return c.get(f'/api/companies/{company_id}/virtual-index/summary').json()


def files(c, company_id, **params):
    return c.get(f'/api/companies/{company_id}/virtual-index/files', params=params).json()


def test_copy_stores_each_content_once_and_serves_it_back(office, folder):  # noqa: F811
    c, companies, _ = office
    root, company = folder
    agent = load_agent()
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']

    result = analyze(c, token, a, agent, root, company)
    copia = result['copia']
    assert (copia['archivos'], copia['subidos'], copia['ya_estaban'], copia['errores']) == (3, 3, 0, 0)
    assert copia['marcados'] == 3 and '_copy' not in result and '_index' not in result
    data = summary(c, a)
    assert data['copia'] == {
        'con_copia': 3,
        'bytes': data['copia']['bytes'],
        'pendientes': 1,
    }  # notas.txt was not selected
    copied = files(c, a, copied='true')
    assert {f['name'] for f in copied['rows']} == {
        f'{UUID}.xml',
        f'{UUID}.pdf',
        '1.- DECLARACION ISR E IVA ENERO ACME.pdf',
    }
    assert [f['name'] for f in files(c, a, copied='false')['rows']] == ['notas.txt']

    # The copy is served as stored, only to people who can see the company's documents.
    pdf = next(f for f in copied['rows'] if f['name'].endswith('.pdf') and f['name'].startswith(UUID))
    url = f'/api/companies/{a}/virtual-index/files/{pdf["id"]}/content'
    download = c.get(url)
    assert download.status_code == 200 and download.content == b'%PDF-1.4 factura'
    assert (
        'attachment' in download.headers['content-disposition']
        and download.headers['x-content-type-options'] == 'nosniff'
    )
    preview = c.get(url, params={'preview': 'true'})
    assert preview.headers['content-type'] == 'application/pdf' and 'inline' in preview.headers['content-disposition']
    xml = next(f for f in copied['rows'] if f['name'].endswith('.xml'))
    assert (
        c.get(f'/api/companies/{a}/virtual-index/files/{xml["id"]}/content', params={'preview': 'true'})
        .headers['content-type']
        .startswith('text/plain')
    )
    # Nothing was stored for the key, the not-selected note or anything outside the copied sections.
    assert not virtual_blobs.exists(sha(b'SECRETO-LLAVE')) and not virtual_blobs.exists(sha(b'notas sueltas'))
    assert c.get(f'/api/companies/{companies["b"]}/virtual-index/files/{pdf["id"]}/content').status_code == 404

    # The same files again: nothing is uploaded twice.
    again = analyze(c, token, a, agent, root, company)['copia']
    assert (again['subidos'], again['ya_estaban']) == (0, 3)


def test_a_changed_original_makes_its_copy_stale_until_it_is_copied_again(office, folder):  # noqa: F811
    c, companies, _ = office
    root, company = folder
    agent = load_agent()
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    analyze(c, token, a, agent, root, company)
    declaration = company / 'IMPUESTOS' / 'FEDERALES' / '1.- DECLARACION ISR E IVA ENERO ACME.pdf'
    old = declaration.read_bytes()
    declaration.write_bytes(b'%PDF-1.4 declaracion corregida')

    analyze(c, token, a, agent, root, company, copy=None)  # a plain analysis: the index changes, no copy is made
    stale = next(f for f in files(c, a)['rows'] if f['name'].startswith('1.- DECLARACION'))
    assert stale['copied'] is False  # the stored copy is the old content
    assert c.get(f'/api/companies/{a}/virtual-index/files/{stale["id"]}/content').status_code == 404
    assert summary(c, a)['copia']['con_copia'] == 2
    assert virtual_blobs.exists(sha(old))  # the old content is still stored

    result = analyze(c, token, a, agent, root, company)['copia']
    assert (result['subidos'], result['ya_estaban']) == (1, 2)
    fresh = next(f for f in files(c, a)['rows'] if f['name'].startswith('1.- DECLARACION'))
    assert fresh['copied'] is True
    assert (
        c.get(f'/api/companies/{a}/virtual-index/files/{fresh["id"]}/content').content
        == b'%PDF-1.4 declaracion corregida'
    )


def test_the_copy_survives_the_original_disappearing(office, folder):  # noqa: F811
    c, companies, _ = office
    root, company = folder
    agent = load_agent()
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    analyze(c, token, a, agent, root, company)
    target = company / 'CFDI' / 'JULIO' / 'EMITIDOS' / f'{UUID}.pdf'
    target.unlink()
    analyze(c, token, a, agent, root, company)
    gone = files(c, a, missing='true')['rows']
    assert [f['name'] for f in gone] == [f'{UUID}.pdf'] and gone[0]['copied'] is True
    assert c.get(f'/api/companies/{a}/virtual-index/files/{gone[0]["id"]}/content').content == b'%PDF-1.4 factura'


def test_blob_uploads_are_verified_and_only_for_a_copy_job(office, monkeypatch):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder'})  # no copy requested
    plain = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    data = b'contenido'
    url = f'/api/agent/jobs/{plain["id"]}/blobs/{sha(data)}?agent_id=pc-ana'
    assert c.put(url, headers=bearer(token), content=data).status_code == 409  # this job did not ask for a copy
    c.post(
        '/api/agent/jobs/' + plain['id'] + '/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': {}},
    )

    c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder', 'copy': SECTIONS})
    job = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    base = f'/api/agent/jobs/{job["id"]}/blobs/'
    ok = c.put(base + sha(data) + '?agent_id=pc-ana', headers=bearer(token), content=data)
    assert ok.status_code == 200 and ok.json()['new'] is True and virtual_blobs.exists(sha(data))
    assert c.put(base + sha(data) + '?agent_id=pc-ana', headers=bearer(token), content=data).json()['new'] is False
    assert (
        c.put(base + sha(b'otro') + '?agent_id=pc-ana', headers=bearer(token), content=data).status_code == 422
    )  # wrong hash
    assert c.put(base + 'no-es-hash?agent_id=pc-ana', headers=bearer(token), content=data).status_code == 422
    key = b'-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----'
    assert c.put(base + sha(key) + '?agent_id=pc-ana', headers=bearer(token), content=key).status_code == 422
    assert not virtual_blobs.exists(sha(key))
    monkeypatch.setattr(virtual_blobs, 'MAX_BLOB', 5)
    assert c.put(base + sha(data) + '?agent_id=pc-ana', headers=bearer(token), content=data).status_code == 413
    asked = c.post(
        base + 'missing', headers=bearer(token), json={'agent_id': 'pc-ana', 'hashes': [sha(data), sha(b'nuevo')]}
    )
    assert asked.json() == {'missing': [sha(b'nuevo')]}
    assert (
        c.post(base + 'missing', headers=bearer(token), json={'agent_id': 'pc-ana', 'hashes': ['xx']}).status_code
        == 422
    )
    assert c.put(base + sha(data) + '?agent_id=otro', headers=bearer(token), content=data).status_code in (403, 409)
    with SessionLocal() as db:
        assert db.query(VirtualFile).filter(VirtualFile.copy_sha256.is_not(None)).count() == 0  # nothing marked yet


def test_asking_for_a_copy_needs_the_upload_permission(office):  # noqa: F811
    c, companies, _ = office
    a = companies['a']
    account(c, 'solo_analiza', 'auxiliar', [(a, 'write')], actions=[(a, 'carpeta.analizar')])
    login(c, 'solo_analiza')
    _, token = pair(c, agent_id='pc-sa', machine='PC-SA')
    beat(c, token, agent_id='pc-sa')
    assert c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder', 'copy': SECTIONS}).status_code == 403
    assert c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder'}).status_code == 201
    assert c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder', 'copy': ['inventado']}).status_code in (
        403,
        422,
    )
    login(c)
    account(c, 'completo', 'auxiliar', [(a, 'write')], actions=[(a, 'carpeta.analizar'), (a, 'documentos.subir')])
    login(c, 'completo')
    _, token = pair(c, agent_id='pc-co', machine='PC-CO')
    beat(c, token, agent_id='pc-co')
    assert c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder', 'copy': SECTIONS}).status_code == 201
    assert c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder', 'copy': ['inventado']}).status_code == 422
    exporting = c.post(
        '/api/jobs', json={'company_id': a, 'kind': 'export_virtual', 'destination': r'C:\Empresas\X', 'copy': SECTIONS}
    )
    assert exporting.status_code == 422
