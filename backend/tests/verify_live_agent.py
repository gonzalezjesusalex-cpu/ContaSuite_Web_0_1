"""Standalone integration check using real HTTP, FastAPI and the polling agent (synthetic data only).

Runs in its own interpreter (directly, or from pytest through tests/test_isolated_suites.py with the
`slow` marker): applies the schema explicitly to a temporary SQLite database, starts the API on
127.0.0.1:8129 without reading .env, creates a synthetic administrator and checks
heartbeat -> queue -> claim -> scan -> result, first with the former shared token (transition flag) and then in
linked mode (Bloque 4): one-time code handed by the app origin, job of its own user, link ended at sign-out.
"""

import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import httpx

root = Path(__file__).resolve().parents[2]
port = 8129
base = 'http://127.0.0.1:' + str(port)
with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    allowed = temp / 'companies'
    allowed.mkdir()
    (allowed / 'example.xml').write_text('<Comprobante/>')
    (allowed / 'private.key').write_bytes(b'LOCAL_ONLY')
    env = {
        **os.environ,
        'PYTHON_DOTENV_DISABLED': '1',
        'CS_TEST_SQLITE': '1',
        'DATABASE_URL': 'sqlite:///' + (temp / 'live.db').as_posix(),
        'DATA_DIR': str(temp / 'data'),
        'SEED_DEMO': 'false',
        'APP_TOKEN': 'local-integration-app-token-only',
        'AGENT_TOKEN': 'local-integration-agent-token-only',
        # Bloque 4: this check drives the real agent in the former shared-token mode (transition flag).
        'CS_ALLOW_SHARED_AGENT_TOKEN': '1',
        'CS_STORAGE_ALLOWED_ROOTS': '[]',
        'CS_STORAGE_SMB_ALLOWED_ROOTS': '[]',
        'PYTHONPATH': str(root / 'backend'),
        'NO_PROXY': '127.0.0.1,localhost',
    }
    # Application startup only verifies the schema; create it explicitly, as an installation would.
    subprocess.run(
        [sys.executable, str(root / 'scripts/schema_admin.py'), '--data-dir', env['DATA_DIR'], '--new', '--apply'],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    api = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    worker = None
    try:
        with httpx.Client(base_url=base, headers={'Origin': base}, trust_env=False, timeout=3) as client:
            for _ in range(150):
                try:
                    if client.get('/api/auth/status').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError('La API no inició')
            password = secrets.token_urlsafe(18)
            account = {'username': 'live.agent', 'password': password, 'display_name': 'Live Agent'}
            client.post(
                '/api/auth/bootstrap', json=account, headers={'Authorization': 'Bearer ' + env['APP_TOKEN']}
            ).raise_for_status()
            client.post('/api/auth/login', json={'username': 'live.agent', 'password': password}).raise_for_status()
            client.headers['X-CSRF-Token'] = client.cookies.get('contasuite_csrf')
            config = temp / 'agent.json'
            config.write_text(
                json.dumps(
                    {
                        'api_url': base,
                        'agent_id': 'integration-worker',
                        'token': env['AGENT_TOKEN'],
                        'allowed_roots': [str(allowed)],
                    }
                )
            )
            worker = subprocess.Popen(
                [sys.executable, str(root / 'agent/agent.py'), '--config', str(config)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(100):
                if client.get('/api/state').json()['agents']:
                    break
                time.sleep(0.2)
            else:
                raise AssertionError('El agente no se conectó')
            company = client.post(
                '/api/companies', json={'name': 'Live Agent Test', 'rfc': 'LAT261109AA1', 'folder': str(allowed)}
            )
            company.raise_for_status()
            job = client.post(
                '/api/jobs',
                json={'company_id': company.json()['id'], 'agent_id': 'integration-worker', 'kind': 'scan_folder'},
            )
            job.raise_for_status()
            jobid = job.json()['id']
            # The agent polls every 5 s between claims.
            for _ in range(100):
                state = client.get('/api/state').json()
                result = next(j for j in state['jobs'] if j['id'] == jobid)
                if result['status'] in ['completed', 'failed']:
                    break
                time.sleep(0.2)
            assert result['status'] == 'completed', result
            # The polled state only carries a summary: the full result is the company's latest job.
            result = client.get(f"/api/companies/{company.json()['id']}/jobs/latest", params={'kind': 'scan_folder'}).json()
            # Private keys are excluded from the inventory: neither listed nor transmitted.
            assert {f['name'] for f in result['result']['files']} == {'example.xml'}, result['result']
            assert 'LOCAL_ONLY' not in json.dumps(result)
            assert (allowed / 'private.key').read_bytes() == b'LOCAL_ONLY'
            print(
                'PASS: heartbeat -> queue -> claim -> scan -> result; source files unchanged; '
                'private key neither listed nor transmitted.'
            )
            worker.terminate()
            worker.wait(timeout=5)

            # Bloque 4, linked mode (no token): the browser gives the agent a one-time code at sign-in.
            local_port = 47911
            local = 'http://127.0.0.1:' + str(local_port)
            config.write_text(
                json.dumps(
                    {'api_url': base, 'agent_id': 'linked-worker', 'local_port': local_port, 'app_origins': [base]}
                )
            )
            linked = subprocess.Popen(
                [sys.executable, str(root / 'agent/agent.py'), '--config', str(config)],
                env={k: v for k, v in env.items() if k != 'AGENT_TOKEN'},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            worker = linked
            with httpx.Client(base_url=local, trust_env=False, timeout=3) as agent_http:
                for _ in range(100):
                    try:
                        status = agent_http.get('/status', headers={'Origin': base})
                        break
                    except httpx.HTTPError:
                        time.sleep(0.2)
                else:
                    raise AssertionError('El agente vinculado no abrió su puerto local')
                assert status.json()['paired'] is False
                # Another site cannot read the agent nor hand it a code.
                assert agent_http.get('/status', headers={'Origin': 'https://example.invalid'}).status_code == 403
                assert (
                    agent_http.post(
                        '/pair', json={'code': 'x' * 20}, headers={'Origin': 'https://example.invalid'}
                    ).status_code
                    == 403
                )
                code = client.post('/api/agent-links/code').json()['code']
                paired = agent_http.post('/pair', json={'code': code}, headers={'Origin': base})
                assert paired.status_code == 200 and paired.json()['user'] == 'Live Agent', paired.text
            client.put('/api/agent-links/roots', json={'paths': [str(allowed)]}).raise_for_status()
            for _ in range(100):
                if (client.get('/api/state').json().get('agent_link') or {}).get('state') == 'online':
                    break
                time.sleep(0.2)
            else:
                raise AssertionError('El agente vinculado no se conectó')
            job = client.post('/api/jobs', json={'company_id': company.json()['id'], 'kind': 'scan_folder'})
            job.raise_for_status()
            assert job.json()['agent_id'] == 'linked-worker'
            jobid = job.json()['id']
            for _ in range(100):
                result = next(j for j in client.get('/api/state').json()['jobs'] if j['id'] == jobid)
                if result['status'] in ['completed', 'failed']:
                    break
                time.sleep(0.2)
            assert result['status'] == 'completed', result
            result = client.get(f"/api/companies/{company.json()['id']}/jobs/latest", params={'kind': 'scan_folder'}).json()
            assert {f['name'] for f in result['result']['files']} == {'example.xml'}, result['result']
            # Signing out ends the link: the agent stops working for that user.
            client.post('/api/auth/logout').raise_for_status()
            with httpx.Client(base_url=local, trust_env=False, timeout=3) as agent_http:
                for _ in range(60):
                    if not agent_http.get('/status', headers={'Origin': base}).json()['paired']:
                        break
                    time.sleep(0.5)
                else:
                    raise AssertionError('El agente siguió vinculado después de cerrar sesión')
            print(
                'PASS: linked agent: one-time code from the app origin only, job by its own user, link ends on sign-out.'
            )
    finally:
        if worker:
            worker.terminate()
            worker.wait(timeout=5)
        api.terminate()
        api.wait(timeout=5)
