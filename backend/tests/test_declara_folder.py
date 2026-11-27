"""Declara en modo carpeta (sección 6, puntos 7 y 9): agente, bloqueo, respaldo, deshacer, rutas y flujo con el servidor."""

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import setup
from test_agent_links import bearer, pair
from test_declara import pdf
from test_declara_v2 import image_pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'agent'))

import declara_folder as agent  # noqa: E402
from app import declara_engine as motor  # noqa: E402

USER, MACHINE = 'Ana', 'PC-ANA'


def same(path):
    return path


@pytest.fixture(autouse=True)
def _no_held_locks(monkeypatch):
    agent.HELD.clear()
    monkeypatch.setattr(agent, 'RETRY_WAIT', 0)
    yield
    agent.HELD.clear()


@pytest.fixture()
def folder(tmp_path):
    root = tmp_path / 'Clientes'
    target = root / 'ARKOS' / '2026'
    target.mkdir(parents=True)
    (target / 'decl.pdf').write_bytes(pdf())
    (target / 'acuse.pdf').write_bytes(pdf('ACUSE'))
    (target / 'complementaria.pdf').write_bytes(pdf(dtype='Complementaria', operation='200'))
    (target / 'notas.txt').write_text('no es PDF')
    return root, target


def run(root, op, user=USER, machine=MACHINE, **payload):
    return agent.run({'op': op, **payload}, [str(root)], user, machine, resolver=same)


def analyze(root, target, **kw):
    return run(root, 'analizar', ruta=str(target), nombre_corto='ARKOS', rfc='ASU260331IWA', **kw)


def plan_of(result):
    return [
        {'origen': r['path'], 'destino': r['expected_name'], 'sha256': r['sha256']}
        for r in result['registros']
        if r.get('status') == 'RENOMBRAR'
    ]


def names(target):
    return sorted(p.name for p in target.iterdir() if p.is_file())


def write_lock(target, user, machine, minutes_ago=0):
    beat = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    (target / '.declara').mkdir(exist_ok=True)
    (target / '.declara' / 'bloqueo').write_text(
        json.dumps({'usuario': user, 'equipo': machine, 'hora': beat, 'latido': beat}), encoding='utf-8'
    )


# ---------------------------------------------------------------- punto 7: respaldo, registro, deshacer y bloqueo


def test_apply_with_backup_and_undo_restore_exact_names(folder):
    root, target = folder
    before = names(target)
    contents = {n: (target / n).read_bytes() for n in before}
    result = analyze(root, target)
    assert result['total'] == 3 and not result['solo_lectura'] and result['bloqueo']['estado'] == 'propio'
    # The engine in the agent gives the same names as the engine on its own.
    direct = {i.path.name: i.expected_name for i in motor.analyze_folder(target, 'ARKOS', 'ASU260331IWA')}
    assert {r['path']: r.get('expected_name') for r in result['registros']} == direct
    plan = plan_of(result)
    applied = run(root, 'aplicar', ruta=str(target), plan=plan, respaldo=True)
    assert applied['renombrados'] == 3 and applied['pendientes'] == []
    assert names(target) == sorted([p['destino'] for p in plan] + ['notas.txt'])
    backup = target / '.declara' / 'respaldos' / applied['respaldo']
    assert sorted(p.name for p in backup.iterdir()) == sorted(p['origen'] for p in plan)
    registry = json.loads((target / '.declara' / 'registro.json').read_text(encoding='utf-8'))
    assert registry[-1]['usuario'] == USER and registry[-1]['equipo'] == MACHINE
    # Deshacer funciona aunque se haya cerrado la app: sólo necesita el registro de la carpeta.
    agent.HELD.clear()
    undone = run(root, 'deshacer', ruta=str(target))
    assert undone['restaurados'] == 3
    assert names(target) == before
    assert all((target / n).read_bytes() == data for n, data in contents.items())
    with pytest.raises(agent.FolderError) as error:
        run(root, 'deshacer', ruta=str(target))
    assert error.value.code == 'sin_registro'


def test_foreign_lock_leaves_the_folder_read_only(folder):
    root, target = folder
    write_lock(target, 'Luis', 'PC-LUIS')
    result = analyze(root, target)
    assert result['solo_lectura'] and result['bloqueo']['estado'] == 'ajeno'
    assert result['bloqueo']['usuario'] == 'Luis' and not (target / '.declara' / 'indice.json').exists()
    with pytest.raises(agent.FolderError) as error:
        run(root, 'aplicar', ruta=str(target), plan=plan_of(result), respaldo=False)
    assert error.value.code == 'carpeta_bloqueada'
    assert names(target) == ['acuse.pdf', 'complementaria.pdf', 'decl.pdf', 'notas.txt']
    listed = run(root, 'listar', ruta=str(target.parent))
    assert listed['carpetas'][0]['bloqueo']['estado'] == 'ajeno'


def test_expired_lock_is_released_and_taken(folder):
    root, target = folder
    write_lock(target, 'Luis', 'PC-LUIS', minutes_ago=3)
    assert agent.lock_state(str(target), USER, MACHINE) == {'estado': 'libre'}
    assert agent.take_lock(str(target), USER, MACHINE)['estado'] == 'propio'
    assert run(root, 'liberar', ruta=str(target))['bloqueo'] == {'estado': 'libre'}
    assert not (target / '.declara' / 'bloqueo').exists()


def test_held_locks_renew_and_abandoned_ones_are_released(folder, monkeypatch):
    root, target = folder
    agent.take_lock(str(target), USER, MACHINE)
    agent.renew_held()
    assert agent.lock_state(str(target), USER, MACHINE)['estado'] == 'propio'
    agent.renew_held(idle_seconds=-1)
    assert agent.lock_state(str(target), USER, MACHINE) == {'estado': 'libre'} and not agent.HELD


def test_changed_file_refuses_apply_and_nothing_is_renamed(folder):
    root, target = folder
    plan = plan_of(analyze(root, target))
    (target / 'decl.pdf').write_bytes(pdf(operation='999'))
    with pytest.raises(agent.FolderError) as error:
        run(root, 'aplicar', ruta=str(target), plan=plan, respaldo=True)
    assert error.value.code == 'cambio_externo'
    assert names(target) == ['acuse.pdf', 'complementaria.pdf', 'decl.pdf', 'notas.txt']


def test_file_in_use_is_left_pending_after_retries(folder, monkeypatch):
    root, target = folder
    plan = plan_of(analyze(root, target))
    original = motor.sha256_file
    attempts = []

    def busy(path):
        if Path(path).name == 'acuse.pdf':
            attempts.append(path)
            raise PermissionError('sharing violation')
        return original(path)

    monkeypatch.setattr(motor, 'sha256_file', busy)
    applied = run(root, 'aplicar', ruta=str(target), plan=plan, respaldo=False)
    assert applied['pendientes'] == ['acuse.pdf'] and applied['renombrados'] == 2 and len(attempts) == 3
    assert 'acuse.pdf' in names(target)


def test_destination_never_overwritten(folder):
    root, target = folder
    plan = plan_of(analyze(root, target))
    (target / plan[0]['destino']).write_bytes(b'otro archivo')
    with pytest.raises(agent.FolderError) as error:
        run(root, 'aplicar', ruta=str(target), plan=plan, respaldo=False)
    assert error.value.code == 'renombrado_fallido'
    assert (target / plan[0]['destino']).read_bytes() == b'otro archivo'


def test_incremental_index_reads_only_new_or_changed(folder, monkeypatch):
    root, target = folder
    assert analyze(root, target)['leidos'] == 3
    calls = []
    original = motor.parse_pdf
    monkeypatch.setattr(motor, 'parse_pdf', lambda path, company: calls.append(path.name) or original(path, company))
    second = analyze(root, target)
    assert second['leidos'] == 0 and calls == []
    (target / 'nuevo.pdf').write_bytes(image_pdf())
    third = analyze(root, target)
    assert third['leidos'] == 1 and third['total'] == 4 and calls == ['nuevo.pdf']
    assert second['firma'] != third['firma']
    # Same plan from the index as from reading every PDF again.
    direct = {i.path.name: (i.status, i.expected_name) for i in motor.analyze_folder(target, 'ARKOS', 'ASU260331IWA')}
    assert {r['path']: (r['status'], r.get('expected_name')) for r in third['registros']} == direct


def test_probe_and_signature(folder):
    root, target = folder
    probe = run(root, 'probar', ruta=str(target))
    assert probe['lectura'] and probe['escritura'] and probe['latencia_ms'] >= 0
    assert probe['bloqueo'] == {'estado': 'libre'} and not (target / '.declara' / '.prueba').exists()
    first = run(root, 'firma', ruta=str(target))
    assert first['archivos'] == 4 and run(root, 'firma', ruta=str(target))['firma'] == first['firma']


def test_list_folder_shows_pdfs_index_template_and_parent(folder):
    root, target = folder
    analyze(root, target)
    year = run(root, 'listar', ruta=str(target.parent), plantilla=str(target))
    row = year['carpetas'][0]
    assert row['nombre'] == '2026' and row['pdf'] == 3 and row['indice'] and row['plantilla']
    assert year['padre'] == str(root)
    assert run(root, 'listar', ruta=str(root))['padre'] is None  # never above the authorized root
    assert [r['ruta'] for r in run(root, 'raices')['raices']] == [str(root)]


def test_read_pdf_checks_the_fingerprint(folder):
    root, target = folder
    data = (target / 'decl.pdf').read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    assert run(root, 'leer_pdf', ruta=str(target), nombre='decl.pdf', sha256=sha)['_pdf'] == data
    for name, code in (('..\\x.pdf', 'invalid_path'), ('notas.txt', 'invalid_path')):
        with pytest.raises(agent.FolderError) as error:
            run(root, 'leer_pdf', ruta=str(target), nombre=name, sha256=sha)
        assert error.value.code == code
    with pytest.raises(agent.FolderError) as error:
        run(root, 'leer_pdf', ruta=str(target), nombre='acuse.pdf', sha256=sha)
    assert error.value.code == 'cambio_externo'


# ---------------------------------------------------------------- punto 9: rutas


def test_mapped_drive_becomes_unc_and_roots_are_enforced():
    def resolver(path):
        return '\\\\SERVIDOR\\Clientes' + path[2:] if path.upper().startswith('Z:') else path

    guard = agent.Guard(['Z:\\'], resolver)
    assert guard.roots == ['\\\\SERVIDOR\\Clientes\\']
    assert guard.check('Z:\\ARKOS\\2026') == '\\\\SERVIDOR\\Clientes\\ARKOS\\2026'
    assert guard.check('\\\\servidor\\clientes\\ARKOS') == '\\\\servidor\\clientes\\ARKOS'
    for bad, code in (
        ('Z:\\ARKOS\\..\\..\\Windows', 'invalid_path'),
        ('ARKOS\\2026', 'invalid_path'),
        ('C:\\Windows', 'unauthorized_root'),
        ('\\\\SERVIDOR\\Clientes2\\x', 'unauthorized_root'),
        ('', 'invalid_path'),
    ):
        with pytest.raises(agent.FolderError) as error:
            guard.check(bad)
        assert error.value.code == code, bad


def test_long_paths_are_flagged_and_prefixed(monkeypatch):
    folder = 'C:\\' + 'x' * 200
    plan = [{'origen': 'a.pdf', 'destino': 'N' * 60 + '.pdf'}, {'origen': 'b.pdf', 'destino': 'corto.pdf'}]
    assert agent.long_names(folder, plan) == ['N' * 60 + '.pdf']
    monkeypatch.setattr(agent.os, 'name', 'nt')
    assert str(agent.io_path('\\\\srv\\share\\' + 'y' * 250)).startswith('\\\\?\\UNC\\srv\\share')
    assert str(agent.io_path('C:\\' + 'y' * 250)).startswith('\\\\?\\C:\\')
    assert str(agent.io_path('C:\\corto')) == 'C:\\corto'


def test_plan_names_are_checked_before_touching_files(folder):
    root, target = folder
    result = analyze(root, target)
    plan = plan_of(result)
    for bad in ({**plan[0], 'destino': '..\\fuera.pdf'}, {**plan[0], 'destino': 'a:b.pdf'}):
        with pytest.raises(agent.FolderError) as error:
            run(root, 'aplicar', ruta=str(target), plan=[bad], respaldo=False)
        assert error.value.code == 'invalid_path'
    with pytest.raises(agent.FolderError) as error:
        run(
            root,
            'aplicar',
            ruta=str(target),
            plan=[plan[0], {**plan[1], 'destino': plan[0]['destino']}],
            respaldo=False,
        )
    assert error.value.code == 'destinos_duplicados'


# ---------------------------------------------------------------- flujo con el servidor y un agente simulado


def agent_cycle(c, token, root):
    """Lo que hace el agente vinculado: reclamar el trabajo, ejecutarlo y entregar el resultado (y el PDF pedido)."""
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed and claimed['kind'] == 'declara_carpeta'
    payload = dict(claimed['payload'])
    payload.pop('roots')
    try:
        result = agent.run(payload, [str(root)], 'Administración de prueba', 'PC-ANA', resolver=same)
        status = 'completed'
    except agent.FolderError as error:
        result, status = {'error': error.code, 'error_code': error.code}, 'failed'
    data = result.pop('_pdf', None)
    if data is not None:
        put = c.put(
            f'/api/agent/jobs/{claimed["id"]}/declara/{result["sha256"]}?agent_id=pc-ana',
            headers=bearer(token),
            content=data,
        )
        assert put.status_code == 200, put.text
    done = c.post(
        f'/api/agent/jobs/{claimed["id"]}/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': status, 'result': result},
    )
    assert done.status_code == 200, done.text
    return claimed


def test_folder_mode_end_to_end_with_simulated_agent(client, folder):  # noqa: F811
    root, target = folder
    cid = company(client).json()['id']
    setup(client)
    assert client.put('/api/agent-links/roots', json={'paths': [str(root)]}).status_code == 200
    _, token = pair(client)
    beat = {'id': 'pc-ana', 'capabilities': ['scan_folder']}
    client.post('/api/agent/heartbeat', headers=bearer(token), json=beat)
    body = {'company_id': cid, 'year': 2026, 'short_name': 'Arkos', 'ruta': str(target), 'vincular': True}
    refused = client.post('/api/declara/folder/analyze', json=body)
    assert refused.status_code == 409 and 'modo carpeta' in refused.json()['detail']
    client.post('/api/agent/heartbeat', headers=bearer(token), json={**beat, 'capabilities': ['declara_carpeta']})
    assert client.post('/api/declara/folder/analyze', json={**body, 'ruta': 'C:\\x\\..\\y'}).status_code == 422

    job_id = client.post('/api/declara/folder/analyze', json=body).json()['job_id']
    assert client.get('/api/declara/folder/jobs/' + job_id).json()['status'] == 'queued'
    agent_cycle(client, token, root)
    finished = client.get('/api/declara/folder/jobs/' + job_id).json()
    run_id = finished['result']['analisis_id']
    assert finished['status'] == 'completed' and 'registros' not in finished['result']
    base = '/api/declara/runs/' + run_id
    detail = client.get(base).json()
    run_row = detail['run']
    assert run_row['mode'] == 'carpeta' and run_row['folder_path'] == str(target) and run_row['year'] == 2026
    assert run_row['summary']['leidos'] == 3 and run_row['months']['2026']['OCTUBRE']['estado'] == 'COMPLETO'
    assert len(detail['records']) == 3
    folders = client.get(f'/api/declara/companies/{cid}/folder?year=2026').json()
    assert folders['vinculada'] == {'ruta': str(target), 'origen': 'equipo'} and str(target) in folders['recientes']

    # Vista previa: el agente entrega el PDF verificado por su huella.
    decl = next(r for r in detail['records'] if r['path'] == 'decl.pdf')
    assert client.get(f'{base}/file/{decl["index"]}').status_code == 409
    fetched = client.post(f'{base}/fetch-pdf/{decl["index"]}').json()
    agent_cycle(client, token, root)
    assert client.get('/api/declara/folder/jobs/' + fetched['job_id']).json()['status'] == 'completed'
    assert client.get(f'{base}/file/{decl["index"]}').content == (target / 'decl.pdf').read_bytes()

    # Las colisiones del plan ven los archivos de la carpeta (la sombra), igual que con copias.
    other = next(r for r in detail['records'] if r['path'] == 'complementaria.pdf')
    seen = client.post(
        base + '/preview', json={'index': other['index'], 'action': 'manual', 'name': 'notas', 'count': False}
    ).json()
    assert seen['errors'] == [] and seen['name'] == 'notas.pdf'
    taken = client.post(
        base + '/preview', json={'index': other['index'], 'action': 'manual', 'name': 'decl', 'count': False}
    ).json()
    assert taken['errors'] == []  # decl.pdf se renombra en el mismo plan: su nombre queda libre

    assert client.post(base + '/generate', json={'revision': 0}).status_code == 422
    apply_job = client.post(base + '/apply', json={'revision': 0, 'respaldo': True})
    assert apply_job.status_code == 202, apply_job.text
    assert client.post(base + '/apply', json={'revision': 0, 'respaldo': True}).status_code == 409
    claimed = agent_cycle(client, token, root)
    assert len(claimed['payload']['plan']) == 3
    applied = client.get(base).json()['run']
    assert applied['status'] == 'applied' and applied['summary']['renamed'] == 3
    assert '10.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf' in names(target)
    log = client.get(f'/api/declara/log?company_id={cid}&year=2026').json()
    actions = [e['action'] for e in log]
    assert actions[:3] == ['renombrado', 'respaldo', 'analisis']
    assert log[0]['machine'] == 'PC-ANA' and log[0]['path'] == str(target)

    undo_job = client.post(base + '/undo')
    assert undo_job.status_code == 202
    agent_cycle(client, token, root)
    assert client.get(base).json()['run']['status'] == 'undone'
    assert names(target) == ['acuse.pdf', 'complementaria.pdf', 'decl.pdf', 'notas.txt']
    assert client.get(f'/api/declara/log?company_id={cid}').json()[0]['action'] == 'deshacer'


def test_folder_job_errors_are_reported(client, folder):  # noqa: F811
    root, target = folder
    cid = company(client).json()['id']
    setup(client)
    client.put('/api/agent-links/roots', json={'paths': [str(root)]})
    _, token = pair(client)
    client.post(
        '/api/agent/heartbeat', headers=bearer(token), json={'id': 'pc-ana', 'capabilities': ['declara_carpeta']}
    )
    job_id = client.post('/api/declara/folder', json={'company_id': cid, 'op': 'probar', 'ruta': 'C:\\Windows'}).json()[
        'job_id'
    ]
    agent_cycle(client, token, root)
    failed = client.get('/api/declara/folder/jobs/' + job_id).json()
    assert failed['status'] == 'failed' and failed['result']['error_code'] == 'unauthorized_root'
    assert (
        client.post('/api/declara/folder', json={'company_id': cid, 'op': 'aplicar', 'ruta': str(target)}).status_code
        == 422
    )
