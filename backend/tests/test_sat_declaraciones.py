"""Fase 1 de la descarga de declaraciones por el agente: tipo de trabajo y recepción de los PDF descargados."""

import hashlib
import importlib.util
from pathlib import Path

from test_api import client  # noqa: F401  Isolated environment before app imports.
from test_agent_links import bearer, office, pair  # noqa: F401
from test_accounts import login
from app.database import DATA

PDF = b'%PDF-1.4 declaracion provisional'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def heartbeat(c, token):
    return c.post(
        '/api/agent/heartbeat',
        headers=bearer(token),
        json={'id': 'pc-ana', 'capabilities': ['scan_folder', 'export_virtual', 'sat_declaraciones']},
    )


def start(c, company_id, **extra):
    return c.post('/api/jobs', json={'company_id': company_id, 'kind': 'sat_declaraciones', **extra})


def test_heartbeat_accepts_the_agent_capabilities(office):  # noqa: F811
    c, _, _ = office
    login(c, 'ana')
    _, token = pair(c)
    assert heartbeat(c, token).status_code == 200


def test_job_carries_no_folder_and_the_agent_delivers_validated_pdfs(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    assert heartbeat(c, token).status_code == 200

    created = start(c, companies['a'], ejercicio=2026)
    assert created.status_code == 201, created.text
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed['id'] == created.json()['id'] and claimed['kind'] == 'sat_declaraciones'
    assert claimed['payload']['ejercicio'] == 2026 and claimed['payload']['rfc'] == 'AAA010101AA1'
    assert 'folder' not in claimed['payload']  # the browser needs no company folder

    url = f'/api/agent/jobs/{claimed["id"]}/sat/{sha(PDF)}'
    sent = c.put(url, params={'agent_id': 'pc-ana'}, headers=bearer(token), content=PDF)
    assert sent.status_code == 200 and sent.json() == {'ok': True, 'new': True}
    assert (DATA / 'declara_sat' / claimed['id'] / (sha(PDF) + '.pdf')).read_bytes() == PDF
    again = c.put(url, params={'agent_id': 'pc-ana'}, headers=bearer(token), content=PDF)
    assert again.json()['new'] is False

    # Only real PDF bytes that hash to their name are stored.
    html = b'<html>sesion expirada</html>'
    bad = c.put(
        f'/api/agent/jobs/{claimed["id"]}/sat/{sha(html)}',
        params={'agent_id': 'pc-ana'},
        headers=bearer(token),
        content=html,
    )
    assert bad.status_code == 422
    wrong = c.put(
        f'/api/agent/jobs/{claimed["id"]}/sat/{sha(b"otro")}',
        params={'agent_id': 'pc-ana'},
        headers=bearer(token),
        content=PDF,
    )
    assert wrong.status_code == 422
    assert not (DATA / 'declara_sat' / claimed['id'] / (sha(html) + '.pdf')).exists()

    done = c.post(
        f'/api/agent/jobs/{claimed["id"]}/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': {'detectadas': 1, 'guardadas': 1}},
    )
    assert done.status_code == 200
    # A finished job receives nothing more.
    late = c.put(url, params={'agent_id': 'pc-ana'}, headers=bearer(token), content=PDF)
    assert late.status_code == 409


def test_pdfs_are_only_accepted_for_the_sat_job_of_that_agent(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    scan = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'})
    assert scan.status_code == 201, scan.text
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    url = f'/api/agent/jobs/{claimed["id"]}/sat/{sha(PDF)}'
    # A folder analysis is not a SAT download.
    assert c.put(url, params={'agent_id': 'pc-ana'}, headers=bearer(token), content=PDF).status_code == 409
    # Unknown job.
    missing = f'/api/agent/jobs/no-existe/sat/{sha(PDF)}'
    assert c.put(missing, params={'agent_id': 'pc-ana'}, headers=bearer(token), content=PDF).status_code == 409


def test_job_fields_do_not_mix_between_kinds(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    a = companies['a']
    assert start(c, a, destination=r'C:\Empresas\copia').status_code == 422
    assert start(c, a, copy=['cfdi']).status_code == 422
    assert start(c, a, ejercicio=1999).status_code == 422
    assert c.post('/api/jobs', json={'company_id': a, 'kind': 'scan_folder', 'ejercicio': 2026}).status_code == 422
    # The client cannot name an address or an actor for the browser.
    assert start(c, a, url='https://example.com').status_code == 422


def test_job_needs_the_declara_permission_on_that_company(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    other = start(c, 'no-existe')
    assert other.status_code in (403, 404)


def load_agent():
    spec = importlib.util.spec_from_file_location('sat_test_agent', Path(__file__).parents[2] / 'agent/agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_advertises_the_download_only_when_its_setup_names_the_portal():
    agent = load_agent()
    assert 'sat_declaraciones' not in agent.capabilities({})
    assert 'sat_declaraciones' not in agent.capabilities({'sat': {}})
    assert 'sat_declaraciones' in agent.capabilities({'sat': {'base_url': 'http://127.0.0.1:9/consulta'}})


def test_agent_without_a_configured_portal_fails_the_job_without_opening_anything():
    agent = load_agent()
    status, result = agent.run_job({'id': 'x', 'kind': 'sat_declaraciones', 'payload': {'ejercicio': 2026}}, [], {})
    assert status == 'failed' and result['error_code'] == 'sat_no_habilitado'
    assert 'no está habilitada' in result['error']


def test_agent_uploads_what_it_downloaded_and_removes_its_temporary_folder(office, tmp_path):  # noqa: F811
    c, companies, _ = office
    agent = load_agent()
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    start(c, companies['a'])
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    staged = tmp_path / 'staged'
    staged.mkdir()
    (staged / 'declaracion1.pdf').write_bytes(PDF)
    (staged / 'falsa.pdf').write_bytes(b'<html>no soy pdf</html>')
    result = {
        'archivos': [
            {'nombre': 'declaracion1.pdf', 'sha256': sha(PDF)},
            {'nombre': 'falsa.pdf', 'sha256': sha(b'<html>no soy pdf</html>')},
            {'nombre': 'no-existe.pdf', 'sha256': sha(b'x')},
        ],
        '_sat': {'dir': str(staged)},
    }

    def put(path, data):
        r = c.put('/api' + path, headers=bearer(token), content=data)
        assert r.status_code in (200, 422), r.text
        if r.status_code != 200:
            raise ValueError('rechazado')
        return r.json()

    agent.send_sat_pdfs(put, claimed['id'], 'pc-ana', result)
    assert (result['entregados'], result['no_entregados']) == (1, 2) and '_sat' not in result
    assert not staged.exists()
    assert (DATA / 'declara_sat' / claimed['id'] / (sha(PDF) + '.pdf')).exists()


def test_progress_is_shown_and_renews_the_claim_while_the_person_signs_in(office):  # noqa: F811
    from datetime import datetime, timedelta, timezone

    from app.database import SessionLocal
    from app.models import Job

    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    start(c, companies['a'])
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    url = f'/api/agent/jobs/{claimed["id"]}/progress'

    # Claimed long ago, but the agent keeps reporting: the job is not expired.
    old = (datetime.now(timezone.utc) - timedelta(minutes=14)).isoformat()
    with SessionLocal.begin() as db:
        db.get(Job, claimed['id']).result = {'claimed_at': old}
    waiting = c.post(url, headers=bearer(token), json={'agent_id': 'pc-ana', 'fase': 'esperando_sesion'})
    assert waiting.status_code == 200
    with SessionLocal() as db:
        result = db.get(Job, claimed['id']).result
    assert result['progreso'] == {'fase': 'esperando_sesion'}
    assert datetime.fromisoformat(result['claimed_at']) > datetime.now(timezone.utc) - timedelta(minutes=1)

    c.post(url, headers=bearer(token), json={'agent_id': 'pc-ana', 'fase': 'descargando', 'total': 12, 'hechas': 3})
    shown = next(j for j in c.get('/api/state').json()['jobs'] if j['id'] == claimed['id'])
    assert shown['result']['progreso'] == {'fase': 'descargando', 'total': 12, 'hechas': 3}

    # Only a phase and counters: nothing else is accepted, and only from the agent holding the job.
    assert c.post(url, headers=bearer(token), json={'agent_id': 'pc-ana', 'fase': 'otra'}).status_code == 422
    extra = {'agent_id': 'pc-ana', 'fase': 'abriendo', 'url': 'https://x'}
    assert c.post(url, headers=bearer(token), json=extra).status_code == 422
    assert c.post(url, headers=bearer(token), json={'agent_id': 'otro', 'fase': 'abriendo'}).status_code == 409


def test_analysis_is_created_once_from_the_received_pdfs(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    start(c, companies['a'])
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    c.put(
        f'/api/agent/jobs/{claimed["id"]}/sat/{sha(PDF)}',
        params={'agent_id': 'pc-ana'},
        headers=bearer(token),
        content=PDF,
    )
    ask = {'job_id': claimed['id'], 'short_name': 'ACME'}
    # Not yet finished: nothing to analyze.
    assert c.post('/api/declara/runs/from-sat', json=ask).status_code == 404
    archivos = [{'nombre': '../DECLARACION 1', 'sha256': sha(PDF)}, {'nombre': 'falta.pdf', 'sha256': sha(b'x')}]
    done = c.post(
        f'/api/agent/jobs/{claimed["id"]}/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': {'archivos': archivos, 'entregados': 1}},
    )
    assert done.status_code == 200

    created = c.post('/api/declara/runs/from-sat', json=ask)
    assert created.status_code == 202, created.text
    run = created.json()
    assert run['company_id'] == companies['a'] and run['short_name'] == 'ACME' and run['name'] == 'SAT · 1 PDF'
    # The file keeps a safe name inside the analysis and the reception area is emptied.
    assert (DATA / 'declara' / run['id'] / 'input' / 'DECLARACION 1.pdf').read_bytes() == PDF
    assert not (DATA / 'declara_sat' / claimed['id']).exists()
    # The same download never creates a second analysis.
    again = c.post('/api/declara/runs/from-sat', json=ask)
    assert again.status_code == 202 and again.json()['id'] == run['id']
    shown = next(j for j in c.get('/api/state').json()['jobs'] if j['id'] == claimed['id'])
    assert shown['result']['analisis_id'] == run['id']
    assert c.post('/api/declara/runs/from-sat', json={'job_id': 'no-existe', 'short_name': 'X'}).status_code == 404


def test_a_queued_download_is_cancelled_at_once_and_only_once(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    job = start(c, companies['a']).json()
    assert c.post(f'/api/jobs/{job["id"]}/cancel').json() == {'ok': True, 'estado': 'cancelada'}
    shown = next(j for j in c.get('/api/state').json()['jobs'] if j['id'] == job['id'])
    assert shown['status'] == 'failed' and shown['result']['error_code'] == 'sat_cancelado'
    # The agent finds nothing to claim, and a finished job cannot be cancelled again.
    assert c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json() is None
    assert c.post(f'/api/jobs/{job["id"]}/cancel').status_code == 409
    assert c.post('/api/jobs/no-existe/cancel').status_code == 404


def test_a_running_download_is_told_to_stop_through_its_next_report(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    heartbeat(c, token)
    job = start(c, companies['a']).json()
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    url = f'/api/agent/jobs/{claimed["id"]}/progress'
    assert (
        c.post(url, headers=bearer(token), json={'agent_id': 'pc-ana', 'fase': 'abriendo'}).json()['cancelar'] is False
    )
    assert c.post(f'/api/jobs/{job["id"]}/cancel').json() == {'ok': True, 'estado': 'cancelando'}
    # The flag survives the agent's reports until it stops.
    stop = c.post(
        url, headers=bearer(token), json={'agent_id': 'pc-ana', 'fase': 'descargando', 'total': 3, 'hechas': 1}
    )
    assert stop.json() == {'ok': True, 'cancelar': True}
    again = c.post(
        url, headers=bearer(token), json={'agent_id': 'pc-ana', 'fase': 'descargando', 'total': 3, 'hechas': 2}
    )
    assert again.json()['cancelar'] is True


def test_cancelling_is_only_for_sat_downloads_of_the_requester(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    pair(c)
    scan = c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'}).json()
    assert c.post(f'/api/jobs/{scan["id"]}/cancel').status_code == 404


def test_progress_reporter_learns_of_the_cancellation():
    agent = load_agent()
    calls = []

    def post(path, data):
        calls.append((path, data))
        return {'ok': True, 'cancelar': len(calls) >= 2}

    report = agent.progress_reporter(post, 'j1', 'pc-ana')
    report({'fase': 'descargando', 'total': 2, 'hechas': 0})
    assert not report.cancelled.is_set()
    report({'fase': 'descargando', 'total': 2, 'hechas': 1})
    assert report.cancelled.is_set() and calls[0][0] == '/agent/jobs/j1/progress'
