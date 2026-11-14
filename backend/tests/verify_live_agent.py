"""Standalone integration check using real HTTP, FastAPI and the polling agent (synthetic data only).

Runs in its own interpreter (directly, or from pytest through tests/test_isolated_suites.py with the
`slow` marker): applies the schema explicitly to a temporary SQLite database, starts the API on
127.0.0.1:8129 without reading .env, creates a synthetic administrator and checks
heartbeat -> queue -> claim -> scan -> result.
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
        'DATABASE_URL': 'sqlite:///' + (temp / 'live.db').as_posix(),
        'DATA_DIR': str(temp / 'data'),
        'SEED_DEMO': 'false',
        'APP_TOKEN': 'local-integration-app-token-only',
        'AGENT_TOKEN': 'local-integration-agent-token-only',
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
            # Private keys are excluded from the inventory: neither listed nor transmitted.
            assert {f['name'] for f in result['result']['files']} == {'example.xml'}, result['result']
            assert 'LOCAL_ONLY' not in json.dumps(result)
            assert (allowed / 'private.key').read_bytes() == b'LOCAL_ONLY'
            print(
                'PASS: heartbeat -> queue -> claim -> scan -> result; source files unchanged; '
                'private key neither listed nor transmitted.'
            )
    finally:
        if worker:
            worker.terminate()
            worker.wait(timeout=5)
        api.terminate()
        api.wait(timeout=5)
