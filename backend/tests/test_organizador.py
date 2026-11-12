import io
import zipfile
from pathlib import Path

from test_api import client, A, company
from app import organizador_engine as motor

RFC = 'ASU260331IWA'


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return stream.getvalue()


def upload(client, entries, **options):
    return client.post('/api/organizador/runs', headers=A,
                       files={'files': ('entrada.zip', archive(entries), 'application/zip')},
                       data={'rfc': RFC, 'year': '2026', 'months': '4,5', 'kinds': 'Emitidos,Recibidos', 'extensions': '.xml,.pdf', **options})


def test_web_uses_original_paths_and_preserves_bytes(client):
    c = company(client).json()
    entries = {
        f'Base/Emitidos/{RFC}/2026-04/Factura.XML': b'not XML, route decides',
        f'Base/Recibidos/{RFC}/2026-04/Factura.PDF': b'exact PDF bytes',
        f'Base/Emitidos/{RFC}/2026-04/subcarpeta/omitido.xml': b'skip nested',
        f'Base/Emitidos/OTRO010101AA1/2026-04/otra.xml': b'skip RFC',
        f'Base/Emitidos/{RFC}/2025-04/otra.xml': b'skip year',
        f'Base/Reportes/EMITIDOS-{RFC}-202604.xlsm': b'exact spreadsheet bytes',
        'Base/instrucciones.txt': b'skip format',
    }
    r = upload(client, entries, company_id=c['id'])
    assert r.status_code == 202
    base = '/api/organizador/runs/' + r.json()['id']
    detail = client.get(base, headers=A).json()
    assert detail['run']['status'] == 'analyzed'
    assert detail['run']['summary']['ready'] == 3
    assert detail['run']['summary']['unselected'] == 3
    assert detail['run']['warnings']
    assert len([r for r in detail['records'] if r['state'] == 'Omitido']) == 2
    assert all(not Path(r['source']).is_absolute() for r in detail['records'])
    assert client.get(base + '/download', headers=A).status_code == 409
    assert client.post(base + '/generate', headers=A).status_code == 202
    done = client.get(base, headers=A).json()
    assert done['run']['status'] == 'generated'
    assert done['run']['summary']['copied'] == 3
    assert done['run']['summary']['errors'] == 0
    with zipfile.ZipFile(io.BytesIO(client.get(base + '/download', headers=A).content)) as z:
        assert z.read('04.- ABRIL/EMITIDOS/Factura.XML') == entries[f'Base/Emitidos/{RFC}/2026-04/Factura.XML']
        assert z.read('04.- ABRIL/RECIBIDOS/Factura.PDF') == b'exact PDF bytes'
        assert z.read(f'04.- ABRIL/EMITIDOS-{RFC}-202604.xlsm') == b'exact spreadsheet bytes'
        assert '05.- MAYO/EMITIDOS/' in z.namelist()
        assert '05.- MAYO/RECIBIDOS/' in z.namelist()
        assert len([n for n in z.namelist() if not n.endswith('/')]) == 3
    csv = client.get(base + '/download?kind=csv', headers=A)
    assert csv.content.startswith(b'\xef\xbb\xbf')
    assert 'Copia verificada SHA-256.' in csv.content.decode('utf-8-sig')
    assert client.post(base + '/generate', headers=A).status_code == 409
    assert client.delete('/api/companies/' + c['id'], headers=A).status_code == 409
    assert len(client.get('/api/organizador/runs', headers=A).json()) == 1


def test_web_folder_filters_and_reports_only(client):
    response = client.post('/api/organizador/runs', headers=A,
                          files=[('files', (f'Carpeta/Reportes/RECIBIDOS-{RFC}-202604.xlsx', b'Excel')),
                                 ('files', (f'Carpeta/Emitidos/{RFC}/2026-04/a.xml', b'XML'))],
                          data={'rfc': RFC.lower(), 'year': 2026, 'months': '4',
                                'kinds': 'Recibidos', 'extensions': '', 'reports': 'true'})
    assert response.status_code == 202
    detail = client.get('/api/organizador/runs/' + response.json()['id'], headers=A).json()
    assert detail['run']['summary']['ready'] == 1
    assert next(r for r in detail['records'] if r['state'] == 'Listo')['kind'] == 'Reporte Recibidos'


def test_invalid_input_and_access(client):
    assert client.get('/api/organizador/runs').status_code == 401
    good = {f'Emitidos/{RFC}/2026-04/a.xml': b'xml'}
    for options in ({'rfc': 'INVALID'}, {'year': 1999}, {'months': '13'}, {'months': ''},
                    {'kinds': 'Pagos'}, {'extensions': '.key'}, {'extensions': '', 'reports': 'false'}):
        assert upload(client, good, **options).status_code == 422
    assert upload(client, good, company_id='missing').status_code == 404
    for bad in ('../escape.xml', 'C:/escape.xml', 'a/CON.xml', 'a/b./c.xml', 'a//b.xml'):
        response = upload(client, {bad: b'bad'})
        base = '/api/organizador/runs/' + response.json()['id']
        assert client.get(base, headers=A).json()['run']['status'] == 'error'
        assert client.post(base + '/generate', headers=A).status_code == 409
    response = upload(client, {'carpeta/factura.xml': b'flat file'})
    assert client.get('/api/organizador/runs/' + response.json()['id'], headers=A).json()['run']['status'] == 'error'


def test_engine_duplicates_changes_and_move(tmp_path):
    source = tmp_path / 'source'
    period = source / 'Emitidos' / RFC / '2026-04'
    period.mkdir(parents=True)
    a = period / 'a.xml'
    a.write_bytes(b'original')
    target = tmp_path / 'out'
    opts = motor.Options(str(source), str(target), RFC, 2026, months=(4,), operation='move')
    plan = motor.analyze(opts)
    a.write_bytes(b'changed after analysis')
    result = motor.execute(plan)
    assert result.errors == 1 and a.exists()
    plan = motor.analyze(opts)
    existing = target / '04.- ABRIL' / 'EMITIDOS' / 'a.xml'
    existing.write_bytes(b'different, keep it')
    result = motor.execute(plan)
    assert result.records[0]['state'] == 'Duplicado'
    assert a.exists() and existing.read_bytes() == b'different, keep it'
    existing.unlink()
    result = motor.execute(motor.analyze(opts))
    assert result.records[0]['state'] == 'Movido'
    assert not a.exists() and existing.read_bytes() == b'changed after analysis'


def test_web_limits_and_duplicate_paths(client, monkeypatch):
    from app import organizador
    good = {f'Emitidos/{RFC}/2026-04/a.xml': b'long enough'}
    monkeypatch.setattr(organizador, 'MAX_UPLOAD', 1)
    assert upload(client, good).status_code == 413
    monkeypatch.setattr(organizador, 'MAX_UPLOAD', 100000)
    monkeypatch.setattr(organizador, 'MAX_EXPANDED', 1)
    r = upload(client, good)
    assert client.get('/api/organizador/runs/' + r.json()['id'], headers=A).json()['run']['status'] == 'error'
    monkeypatch.setattr(organizador, 'MAX_EXPANDED', 100000)
    r = upload(client, {f'Emitidos/{RFC}/2026-04/a.xml': b'a', f'emitidos/{RFC}/2026-04/A.XML': b'b'})
    assert client.get('/api/organizador/runs/' + r.json()['id'], headers=A).json()['run']['status'] == 'error'


def test_restart_recovers_incomplete_run(client):
    from app.database import SessionLocal
    from app.models import OrganizadorRun
    from app.main import app
    from fastapi.testclient import TestClient
    with SessionLocal() as db:
        db.add(OrganizadorRun(name='interrupted', status='generating', options={}))
        db.commit()
    with TestClient(app) as restarted:
        run = restarted.get('/api/organizador/runs', headers=A).json()[0]
        assert run['status'] == 'error'
        assert 'reinició' in run['message']
