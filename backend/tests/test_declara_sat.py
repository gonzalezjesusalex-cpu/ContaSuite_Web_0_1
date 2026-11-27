"""Sesión SAT de Declara (sección 6, punto 8): descarga simulada, sin el portal real ni Firefox."""

import json
import sys
from pathlib import Path

import pytest

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import setup
from test_agent_links import bearer, pair
from test_declara import pdf
from test_declara_folder import _no_held_locks, folder  # noqa: F401  fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'agent'))

import declara_folder as agent  # noqa: E402
import sat_session  # noqa: E402
from app import declara_engine as motor  # noqa: E402

USER, MACHINE = 'Ana', 'PC-ANA'


def row(op, periodo='Enero', tipo='Normal', ejercicio='2026', **kw):
    return {'operacion': op, 'periodo': periodo, 'tipo': tipo, 'ejercicio': ejercicio, 'con_pdf': True, **kw}


# ---------------------------------------------------------------- la cola, sin navegador


def test_queue_skips_existing_discards_non_pdf_and_continues_after_a_timeout(tmp_path):
    files = {'B': None, 'C': b'<html>sesion vencida</html>', 'D': b'%PDF-1.4 bueno'}
    saved = []

    def download(r):
        if files[r['operacion']] is None:
            raise TimeoutError
        path = tmp_path / (r['operacion'] + '.pdf')
        path.write_bytes(files[r['operacion']])
        return path

    def save(path, r):
        saved.append((path.read_bytes(), r['operacion']))
        return 'guardado', '1.- DECLARACION.pdf'

    events = []
    rows = [row('A'), row('B'), row('C'), row('D')]
    result = sat_session.run_queue(rows, download, save, {'A'}, lambda e: events.append(e) or {})
    states = {r['operacion']: (r['estado'], r.get('motivo')) for r in result['filas']}
    assert states['A'][0] == 'ya_existia'
    assert states['B'] == ('error', 'tiempo_agotado')
    assert states['C'] == ('error', 'no_es_pdf')
    assert states['D'] == ('guardado', '')
    assert saved == [(b'%PDF-1.4 bueno', 'D')]
    assert not list(tmp_path.glob('*.pdf'))  # los temporales se borran siempre
    assert result['ya_existian'] == 1 and result['errores'] == 2 and result['guardadas'] == 1
    assert events[-1]['procesadas'] == 4 and events[-1]['etapa'] == 'descargando'


def test_queue_pauses_cancels_and_retries_on_web_orders(tmp_path):
    attempts = {'B': 0}

    def download(r):
        if r['operacion'] == 'B':
            attempts['B'] += 1
            if attempts['B'] == 1:
                raise sat_session.RowError('descarga_fallida')
        path = tmp_path / (r['operacion'] + '.pdf')
        path.write_bytes(b'%PDF-1.4 ' + r['operacion'].encode())
        return path

    replies = iter([{}, {}, {'pausar': True}, {'pausar': True}, {}, {}, {'reintentar': ['B']}, {}, {}, {}, {}, {}])
    naps = []
    result = sat_session.run_queue(
        [row('A'), row('B'), row('C')],
        download,
        lambda p, r: ('guardado', r['operacion'] + '.pdf'),
        set(),
        lambda e: next(replies, {}),
        sleep=naps.append,
    )
    assert naps  # se pausó y esperó a que la web la reanudara
    assert {r['operacion']: r['estado'] for r in result['filas']} == {'A': 'guardado', 'B': 'guardado', 'C': 'guardado'}
    assert attempts['B'] == 2
    cancelled = sat_session.run_queue(
        [row('A'), row('B')], download, lambda p, r: ('guardado', 'x'), set(), lambda e: {'cancelar': True}
    )
    assert cancelled['cancelada'] and all(r['estado'] == 'en_cola' for r in cancelled['filas'])


def test_period_and_year_filters():
    assert sat_session.month_of('Setiembre') == 'SEPTIEMBRE' and sat_session.month_of('Del mes') == ''
    assert sat_session.wanted(row('A', 'Marzo'), 'MARZO', 2026)
    assert not sat_session.wanted(row('A', 'Abril'), 'MARZO', 2026)
    assert not sat_session.wanted(row('A', 'Marzo', ejercicio='2025'), 'MARZO', 2026)
    assert sat_session.wanted(row('A', 'Marzo', ejercicio=''), '', 2026)


# ---------------------------------------------------------------- guardar y renombrar en un paso


def guard(root):
    return agent.Guard([str(root)], lambda p: p)


def test_save_downloaded_renames_to_the_standard_and_never_overwrites(folder, tmp_path):
    root, target = folder
    downloaded = tmp_path / 'acuse descargado.pdf'
    downloaded.write_bytes(pdf('ACUSE', month='Marzo', operation='777'))
    state, name = agent.save_downloaded(guard(root), str(target), downloaded, 'ARKOS', 'ASU260331IWA', USER, MACHINE)
    assert (state, name) == ('guardado', '3.2.- ACUSE ISR E IVA MARZO ARKOS.pdf')
    assert (target / name).read_bytes() == downloaded.read_bytes()
    # Otro con el mismo nombre estándar recibe consecutivo; el que ya estaba no se toca.
    second = tmp_path / 'otro.pdf'
    second.write_bytes(pdf('ACUSE', month='Marzo', operation='778'))
    state, other = agent.save_downloaded(guard(root), str(target), second, 'ARKOS', 'ASU260331IWA', USER, MACHINE)
    assert other == '3.2.1.- ACUSE ISR E IVA MARZO ARKOS.pdf'
    assert (target / name).read_bytes() == downloaded.read_bytes()
    # Una copia idéntica de lo que ya está no se guarda dos veces.
    assert agent.save_downloaded(guard(root), str(target), second, 'ARKOS', 'ASU260331IWA', USER, MACHINE) == (
        'ya_existia',
        other,
    )
    assert not list(target.glob('~SAT_*'))


def test_save_downloaded_verifies_the_fingerprint(folder, tmp_path, monkeypatch):
    root, target = folder
    downloaded = tmp_path / 'x.pdf'
    downloaded.write_bytes(pdf('ACUSE', month='Marzo', operation='779'))
    real = motor.sha256_file
    calls = []

    def tampered(path):
        calls.append(path)
        return real(path) if len(calls) == 1 else '0' * 64

    monkeypatch.setattr(motor, 'sha256_file', tampered)
    with pytest.raises(agent.FolderError) as error:
        agent.save_downloaded(guard(root), str(target), downloaded, 'ARKOS', 'ASU260331IWA', USER, MACHINE)
    assert error.value.code == 'copia_no_verificada'
    assert sorted(p.name for p in target.iterdir() if p.is_file()) == [
        'acuse.pdf',
        'complementaria.pdf',
        'decl.pdf',
        'notas.txt',
    ]


# ---------------------------------------------------------------- sesión completa con un portal simulado


class FakePortal:
    """Lo que el Firefox de Playwright haría, sin navegador: filas de la consulta y una descarga por fila."""

    rows_served = []
    seen_fiel = []

    def __init__(self, options, notify, fiel=None):
        self.fiel = fiel
        self.options = options
        self.tmp = Path(options['tmp'])

    def open(self):
        pass

    def sign_in(self):
        FakePortal.seen_fiel.append(self.fiel)
        self.fiel = None
        return 'fiel' if FakePortal.seen_fiel[-1] else 'manual'

    def rows(self, login_timeout, stop):
        return [dict(r) for r in FakePortal.rows_served]

    def download(self, r):
        content = r['contenido']
        if content is None:
            raise TimeoutError
        path = self.tmp / (r['operacion'] + '.pdf')
        path.write_bytes(content)
        return path

    def close(self):
        pass


def test_session_downloads_only_missing_and_saves_renamed(folder, tmp_path):
    root, target = folder
    existing_op = '100'  # decl.pdf (octubre) ya está en la carpeta
    FakePortal.rows_served = [
        row(existing_op, 'Octubre', contenido=pdf()),
        row('201', 'Octubre', tipo='Complementaria', contenido=pdf(dtype='Complementaria', operation='201')),
        row('300', 'Noviembre', contenido=pdf(month='Noviembre', operation='300')),
        row('301', 'Octubre', contenido=b'<html>no es pdf</html>'),
        row('302', 'Octubre', contenido=None),
    ]
    FakePortal.seen_fiel = []
    events = []
    fiel = {'cer': b'CER', 'key': b'KEY', 'password': 'secreto', 'cer_name': 'a.cer', 'key_name': 'a.key'}
    payload = {
        'op': 'sat',
        'ruta': str(target),
        'nombre_corto': 'ARKOS',
        'rfc': 'ASU260331IWA',
        'ejercicio': 2026,
        'periodo': 'OCTUBRE',
        'solo_faltantes': True,
        'metodo': 'fiel',
    }
    tmp = tmp_path / 'descargas'
    tmp.mkdir()
    result = sat_session.run(
        payload,
        [str(root)],
        USER,
        MACHINE,
        {'sat': {'base_url': 'http://sat.simulado', 'tmp': str(tmp)}},
        lambda e: events.append(e) or {},
        fetch_fiel=lambda: fiel,
        portal_class=FakePortal,
    )
    session = result['sesion']
    states = {r['operacion']: (r['estado'], r.get('motivo'), r.get('nombre')) for r in session['filas']}
    assert '300' not in states  # periodo elegido: sólo octubre
    assert states[existing_op][0] == 'ya_existia'
    assert states['201'] == ('guardado', '', '10.1.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf')
    assert states['301'][:2] == ('error', 'no_es_pdf') and states['302'][:2] == ('error', 'tiempo_agotado')
    assert session['guardadas'] == 1 and session['ya_existian'] == 1 and session['errores'] == 2
    assert session['acceso'] == 'fiel' and FakePortal.seen_fiel == [fiel]
    assert (target / '10.1.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf').exists()
    assert not (target / '301.pdf').exists() and not list(target.glob('~SAT_*'))
    # Al terminar, la carpeta se reanaliza: el resultado trae el plan nuevo.
    assert {r['path'] for r in result['registros']} >= {
        '10.1.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf'
    }
    stages = events[-1]['etapas']
    assert stages['agente'] == stages['firefox'] == stages['consulta'] == 'hecho'
    # Lo que viaja al servidor es JSON puro, sin contenido de PDF ni la FIEL.
    assert all('secreto' not in json.dumps(e) for e in events)
    assert all(set(r) <= set(sat_session.ROW_KEYS) for e in events for r in e.get('filas', []))
    assert set().union(*(set(r) for r in session['filas'])) <= set(sat_session.ROW_KEYS)


def test_session_needs_a_portal_and_a_free_folder(folder, tmp_path):
    root, target = folder
    payload = {'op': 'sat', 'ruta': str(target), 'nombre_corto': 'ARKOS', 'metodo': 'ciec'}
    with pytest.raises(sat_session.sb.SatError) as error:
        sat_session.run(payload, [str(root)], USER, MACHINE, {}, lambda e: {}, portal_class=FakePortal)
    assert error.value.code == 'sat_no_habilitado'
    from test_declara_folder import write_lock

    write_lock(target, 'Luis', 'PC-LUIS')
    with pytest.raises(agent.FolderError) as error:
        sat_session.run(
            payload, [str(root)], USER, MACHINE, {'sat': {'base_url': 'x'}}, lambda e: {}, portal_class=FakePortal
        )
    assert error.value.code == 'carpeta_bloqueada'


# ---------------------------------------------------------------- servidor: FIEL en memoria, órdenes y bitácora


def linked(client, root):  # noqa: F811
    cid = company(client).json()['id']
    setup(client)
    client.put('/api/agent-links/roots', json={'paths': [str(root)]})
    _, token = pair(client)
    beat = {'id': 'pc-ana', 'capabilities': ['declara_carpeta', 'sat_declaraciones']}
    client.post('/api/agent/heartbeat', headers=bearer(token), json=beat)
    return cid, token


def folder_run(client, token, cid, target, root):  # noqa: F811
    from test_declara_folder import agent_cycle

    body = {'company_id': cid, 'year': 2026, 'short_name': 'Arkos', 'ruta': str(target)}
    job_id = client.post('/api/declara/folder/analyze', json=body).json()['job_id']
    agent_cycle(client, token, root)
    return client.get('/api/declara/folder/jobs/' + job_id).json()['result']['analisis_id']


def test_sat_session_flow_keeps_the_fiel_out_of_the_database(client, folder, monkeypatch):  # noqa: F811
    from app import vault_fiel
    from app.database import SessionLocal
    from app.models import Job

    root, target = folder
    cid, token = linked(client, root)
    run_id = folder_run(client, token, cid, target, root)
    base = f'/api/declara/runs/{run_id}/sat'
    assert client.post(base, json={'metodo': 'otro'}).status_code == 422
    assert client.post(base, json={'metodo': 'fiel'}).status_code in {422, 423}  # sin FIEL o con la bóveda cerrada

    secret = {'cer': b'CER-BYTES', 'key': b'KEY-BYTES', 'password': 'clave-fiel', 'rfc': 'ASU260331IWA'}
    monkeypatch.setattr(vault_fiel, 'obtener_fiel_para_acceso', lambda db, p, cid, purpose='declara': dict(secret))
    started = client.post(base, json={'metodo': 'fiel', 'periodo': 'octubre', 'solo_faltantes': True})
    assert started.status_code == 202, started.text
    job_id = started.json()['job_id']
    with SessionLocal() as db:
        stored = json.dumps(db.get(Job, job_id).payload)
    assert 'clave-fiel' not in stored and 'CER' not in stored and '"periodo": "OCTUBRE"' in stored

    claimed = client.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed['payload']['op'] == 'sat' and claimed['payload']['metodo'] == 'fiel'
    fiel = client.get(f'/api/agent/jobs/{job_id}/fiel?agent_id=pc-ana', headers=bearer(token))
    assert fiel.status_code == 200 and fiel.json()['password'] == 'clave-fiel'
    assert 'no-store' in fiel.headers['cache-control']
    assert client.get(f'/api/agent/jobs/{job_id}/fiel?agent_id=pc-ana', headers=bearer(token)).status_code == 404

    progress = {'agent_id': 'pc-ana', 'etapa': 'descargando', 'total': 2, 'procesadas': 1, 'filas': [row('1')]}
    assert client.post(f'/api/agent/jobs/{job_id}/declara-progress', headers=bearer(token), json=progress).json() == {
        'reintentar': []
    }
    control = f'/api/declara/folder/jobs/{job_id}/control'
    assert client.post(control, json={'accion': 'pausar'}).status_code == 200
    assert client.post(control, json={'accion': 'reintentar', 'operacion': '302'}).status_code == 200
    orders = client.post(f'/api/agent/jobs/{job_id}/declara-progress', headers=bearer(token), json=progress).json()
    assert orders == {'pausar': True, 'reintentar': ['302']}
    again = client.post(f'/api/agent/jobs/{job_id}/declara-progress', headers=bearer(token), json=progress).json()
    assert again == {'pausar': True, 'reintentar': []}  # cada reintento se entrega una vez
    live = client.get('/api/declara/folder/jobs/' + job_id).json()
    assert live['result']['progreso']['procesadas'] == 1 and live['result']['progreso']['filas'][0]['operacion'] == '1'
    assert client.post(control, json={'accion': 'reanudar'}).status_code == 200

    # El agente termina con el reanálisis de la carpeta: se crea un análisis nuevo y queda en la bitácora.
    final = agent.analyze(guard(root), str(target), 'ARKOS', 'ASU260331IWA', 'Administración de prueba', 'PC-ANA')
    final['sesion'] = {'encontradas': 3, 'total': 2, 'guardadas': 1, 'ya_existian': 1, 'errores': 0, 'acceso': 'fiel'}
    done = client.post(
        f'/api/agent/jobs/{job_id}/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': final},
    )
    assert done.status_code == 200
    finished = client.get('/api/declara/folder/jobs/' + job_id).json()
    assert finished['result']['analisis_id'] and 'registros' not in finished['result']
    log = client.get(f'/api/declara/log?company_id={cid}').json()
    entry = next(e for e in log if e['action'] == 'sesion_sat')
    assert entry['detail']['guardadas'] == 1 and entry['machine'] == 'PC-ANA' and entry['path'] == str(target)
    assert entry['run_id'] == finished['result']['analisis_id']
    assert client.post(control, json={'accion': 'pausar'}).status_code == 409


def test_sat_status_and_requirements(client, folder):  # noqa: F811
    root, target = folder
    cid, token = linked(client, root)
    status = client.get(f'/api/declara/companies/{cid}/sat').json()
    assert status['fiel']['disponible'] is False and status['boveda_abierta'] is False
    assert status['agente']['en_linea'] and status['portal'] and status['persona'] == 'moral'
    upload = client.post(
        '/api/declara/runs',
        data={'company_id': cid, 'short_name': 'Arkos'},
        files={'files': ('a.pdf', pdf(), 'application/pdf')},
    ).json()['id']
    assert client.post(f'/api/declara/runs/{upload}/sat', json={'metodo': 'ciec'}).status_code == 422
    run_id = folder_run(client, token, cid, target, root)
    client.post(
        '/api/agent/heartbeat', headers=bearer(token), json={'id': 'pc-ana', 'capabilities': ['declara_carpeta']}
    )
    refused = client.post(f'/api/declara/runs/{run_id}/sat', json={'metodo': 'ciec'})
    assert refused.status_code == 409 and 'no está habilitada' in refused.json()['detail']
    assert client.post('/api/declara/folder', json={'company_id': cid, 'op': 'sat_estado'}).status_code == 202
