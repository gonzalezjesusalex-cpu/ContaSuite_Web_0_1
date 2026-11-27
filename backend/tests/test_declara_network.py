"""Red local de Declara (fase 6): credencial del gestor en memoria, conexión sin letra, red perdida y escritura."""

import json
import sys
import types
from pathlib import Path

import pytest

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_agent_links import bearer
from test_declara_folder import _no_held_locks, analyze, folder, names, plan_of, run  # noqa: F401
from test_declara_sat import linked

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'agent'))

import declara_folder as agent  # noqa: E402
from app import declara_engine as motor  # noqa: E402

SECRET = {'servidor': 'SERVIDOR', 'recurso': 'Clientes', 'usuario': 'conta', 'password': 'clave-red', 'dominio': 'OFI'}


def net_error(code):
    error = OSError('red')
    error.winerror = code
    return error


class FakeMpr:
    def __init__(self, code=0):
        self.code = code
        self.calls = []

    def WNetAddConnection2W(self, resource, password, user, flags):  # noqa: N802
        self.calls.append(('add', resource._obj.lpRemoteName, resource._obj.lpLocalName, user, password, flags))
        return self.code

    def WNetCancelConnection2W(self, share, flags, force):  # noqa: N802
        self.calls.append(('cancel', share))
        return 0


# ---------------------------------------------------------------- agente


def test_share_and_network_errors():
    assert agent.share_of('\\\\SERVIDOR\\Clientes\\ARKOS\\2026') == '\\\\SERVIDOR\\Clientes'
    assert agent.share_of('C:\\Clientes') == ''
    assert agent.network_error(net_error(53)) and agent.network_error(net_error(64))
    assert not agent.network_error(net_error(5)) and not agent.network_error(ValueError())
    assert agent.network_error_text('[WinError 64] El nombre de red ya no está disponible')


def test_connection_without_drive_letter_and_closed_after_the_job(monkeypatch):
    if sys.platform != 'win32':
        pytest.skip('WNetAddConnection2 es de Windows')
    mpr = FakeMpr()
    session = agent.NetworkSession('\\\\SERVIDOR\\Clientes', dict(SECRET), mpr)
    with session:
        assert session.credential is None  # la contraseña no se queda en el objeto
    add, cancel = mpr.calls
    assert add[1:5] == ('\\\\SERVIDOR\\Clientes', None, 'OFI\\conta', 'clave-red')
    assert cancel == ('cancel', '\\\\SERVIDOR\\Clientes')
    for code, reason in ((1326, 'credencial_rechazada'), (53, 'red_no_disponible')):
        with pytest.raises(agent.FolderError) as error:
            with agent.NetworkSession('\\\\SERVIDOR\\Clientes', dict(SECRET), FakeMpr(code)):
                pass
        assert error.value.code == reason
    reused = FakeMpr(1219)  # ya había una conexión de la sesión: se usa y no se cierra la ajena
    with agent.NetworkSession('\\\\SERVIDOR\\Clientes', dict(SECRET), reused):
        pass
    assert [c[0] for c in reused.calls] == ['add']


def test_job_with_credential_fetches_it_once(folder, monkeypatch):
    root, target = folder
    fetched, opened = [], []

    class Session:
        def __init__(self, share, credential, api):
            opened.append((share, credential))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(agent, 'NetworkSession', Session)
    monkeypatch.setattr(agent, 'share_of', lambda path: '\\\\SERVIDOR\\Clientes')
    result = agent.run(
        {'op': 'probar', 'ruta': str(target), 'credencial': True},
        [str(root)],
        'Ana',
        'PC-ANA',
        resolver=lambda p: p,
        fetch_red=lambda: fetched.append(1) or dict(SECRET),
    )
    assert result['lectura'] and fetched == [1] and opened[0][1]['password'] == 'clave-red'
    # Sin la marca de credencial, la sesión de Windows: no se pide nada al servidor.
    agent.run({'op': 'probar', 'ruta': str(target)}, [str(root)], 'Ana', 'PC-ANA', resolver=lambda p: p)
    assert fetched == [1] and opened[1][1] is None


def test_lost_connection_is_retried_on_reads_and_reported(folder, monkeypatch):
    root, target = folder
    monkeypatch.setattr(agent, 'RECONNECT_WAIT', 0)
    calls = []
    real = agent.probe

    def flaky(*args):
        calls.append(1)
        if len(calls) < 3:
            raise net_error(64)
        return real(*args)

    monkeypatch.setattr(agent, 'probe', flaky)
    assert run(root, 'probar', ruta=str(target))['lectura'] and len(calls) == 3
    monkeypatch.setattr(agent, 'probe', lambda *a: (_ for _ in ()).throw(net_error(53)))
    with pytest.raises(agent.FolderError) as error:
        run(root, 'probar', ruta=str(target))
    assert error.value.code == 'conexion_perdida'


def test_apply_interrupted_by_the_network_leaves_a_record(folder, monkeypatch):
    root, target = folder
    plan = plan_of(analyze(root, target))
    monkeypatch.setattr(motor, 'execute_renames', lambda infos: (0, ['[WinError 64] El nombre de red ya no está']))
    with pytest.raises(agent.FolderError) as error:
        run(root, 'aplicar', ruta=str(target), plan=plan, respaldo=False)
    assert error.value.code == 'conexion_perdida'
    registry = json.loads((target / '.declara' / 'registro.json').read_text(encoding='utf-8'))
    assert registry[-1]['estado'] == 'revertido' and len(registry[-1]['cambios']) == 3
    # Un lote revertido no se deshace: no hay nada aplicado.
    with pytest.raises(agent.FolderError) as error:
        run(root, 'deshacer', ruta=str(target))
    assert error.value.code == 'sin_registro'


def test_apply_records_in_progress_then_applied(folder):
    root, target = folder
    plan = plan_of(analyze(root, target))
    run(root, 'aplicar', ruta=str(target), plan=plan, respaldo=False)
    registry = json.loads((target / '.declara' / 'registro.json').read_text(encoding='utf-8'))
    assert registry[-1]['estado'] == 'aplicado'
    assert run(root, 'deshacer', ruta=str(target))['restaurados'] == 3


def test_analysis_reports_whether_the_folder_is_writable(folder, monkeypatch):
    root, target = folder
    assert analyze(root, target)['escritura'] is True
    original = agent.write_json

    def read_only(path, data):
        if path.name == agent.INDEX:
            raise PermissionError('sin permiso')
        return original(path, data)

    monkeypatch.setattr(agent, 'write_json', read_only)
    assert analyze(root, target)['escritura'] is False


# ---------------------------------------------------------------- servidor


@pytest.fixture()
def gestor(monkeypatch):
    """El servicio del gestor «Carpeta de red» (app/vault_network.py), simulado con su contrato."""
    module = types.ModuleType('app.vault_network')
    used = []
    module.credenciales_red = lambda db, p, cid: [
        {
            'id': 'cred-1',
            'label': 'Servidor',
            'servidor': 'SERVIDOR',
            'recurso': 'Clientes',
            'usuario': 'conta',
            'dominio': 'OFI',
        }
    ]

    def obtener(db, p, credential_id, purpose='declara_red'):
        used.append((credential_id, purpose))
        if credential_id != 'cred-1':
            raise LookupError('No es una credencial «Carpeta de red».')
        return dict(SECRET)

    module.obtener_credencial_red = obtener
    monkeypatch.setitem(sys.modules, 'app.vault_network', module)
    import app

    monkeypatch.setattr(app, 'vault_network', module, raising=False)
    return used


def test_network_credential_lives_only_in_memory_and_is_delivered_once(client, folder, gestor):  # noqa: F811
    from app.database import SessionLocal
    from app.models import Job

    root, _target = folder
    cid, token = linked(client, root)
    listed = client.get(f'/api/declara/companies/{cid}/network').json()
    assert listed['disponible'] and listed['credenciales'][0]['id'] == 'cred-1' and listed['elegida'] is None
    assert 'password' not in json.dumps(listed)
    assert client.put(f'/api/declara/companies/{cid}/network', json={'credential_id': 'otra'}).status_code == 422
    chosen = client.put(f'/api/declara/companies/{cid}/network', json={'credential_id': 'cred-1'}).json()
    assert chosen['elegida'] == 'cred-1'

    # Una ruta local nunca pide la credencial; una UNC sí, y sólo su marca va en el trabajo.
    client.put('/api/agent-links/roots', json={'paths': [str(root), '\\\\SERVIDOR\\Clientes']})
    local = client.post('/api/declara/folder', json={'company_id': cid, 'op': 'probar', 'ruta': str(root)})
    assert local.status_code == 202 and gestor == []
    unc = client.post(
        '/api/declara/folder', json={'company_id': cid, 'op': 'probar', 'ruta': '\\\\SERVIDOR\\Clientes\\A'}
    )
    job_id = unc.json()['job_id']
    assert gestor == [('cred-1', 'declara_red')]
    with SessionLocal() as db:
        payload = db.get(Job, job_id).payload
    assert (
        payload['credencial'] is True and 'clave-red' not in json.dumps(payload) and 'cred-1' not in json.dumps(payload)
    )

    client.post('/api/agent/pc-ana/claim', headers=bearer(token))  # el de la ruta local
    client.post('/api/agent/pc-ana/claim', headers=bearer(token))  # el de la ruta UNC
    got = client.get(f'/api/agent/jobs/{job_id}/red?agent_id=pc-ana', headers=bearer(token))
    assert (
        got.status_code == 200 and got.json()['password'] == 'clave-red' and 'no-store' in got.headers['cache-control']
    )
    assert client.get(f'/api/agent/jobs/{job_id}/red?agent_id=pc-ana', headers=bearer(token)).status_code == 404
    assert client.get(f'/api/agent/jobs/{job_id}/red?agent_id=otro', headers=bearer(token)).status_code == 409

    # Probar una credencial concreta antes de elegirla; para otras operaciones no se acepta.
    tested = client.post(
        '/api/declara/folder',
        json={'company_id': cid, 'op': 'probar', 'ruta': '\\\\SERVIDOR\\Clientes\\A', 'credential_id': 'cred-1'},
    )
    assert tested.status_code == 202
    assert (
        client.post(
            '/api/declara/folder',
            json={'company_id': cid, 'op': 'listar', 'ruta': '\\\\SERVIDOR\\Clientes', 'credential_id': 'cred-1'},
        ).status_code
        == 422
    )


def test_without_the_gestor_type_windows_session_is_used(client, folder, monkeypatch):  # noqa: F811
    root, _target = folder
    monkeypatch.setitem(sys.modules, 'app.vault_network', None)  # el gestor aún no tiene el tipo
    cid, _token = linked(client, root)
    listed = client.get(f'/api/declara/companies/{cid}/network').json()
    assert listed == {'disponible': False, 'credenciales': [], 'elegida': None}
    assert client.put(f'/api/declara/companies/{cid}/network', json={'credential_id': 'cred-1'}).status_code == 422


def test_apply_is_blocked_without_write_permission(client, folder):  # noqa: F811
    from test_declara_folder import agent_cycle

    from app.database import SessionLocal
    from app.models import DeclaraRun

    root, target = folder
    cid, token = linked(client, root)
    body = {'company_id': cid, 'year': 2026, 'short_name': 'Arkos', 'ruta': str(target)}
    job_id = client.post('/api/declara/folder/analyze', json=body).json()['job_id']
    agent_cycle(client, token, root)
    run_id = client.get('/api/declara/folder/jobs/' + job_id).json()['result']['analisis_id']
    with SessionLocal() as db:
        row = db.get(DeclaraRun, run_id)
        row.summary = {**row.summary, 'escritura': False}
        db.commit()
    refused = client.post(f'/api/declara/runs/{run_id}/apply', json={'revision': 0, 'respaldo': True})
    assert refused.status_code == 409 and 'escritura' in refused.json()['detail']
    assert names(target) == ['acuse.pdf', 'complementaria.pdf', 'decl.pdf', 'notas.txt']
