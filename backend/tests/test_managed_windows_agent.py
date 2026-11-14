import importlib.util
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from test_api import client, company, A, G


def agent():
    spec = importlib.util.spec_from_file_location('managed_test_agent', Path(__file__).parents[2] / 'agent/agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_managed_inventory_excludes_secrets_and_only_lists_metadata(tmp_path):
    root = tmp_path / 'authorized'
    root.mkdir()
    for name in ['public.pdf', 'public.xml', 'public.cer', 'passwords.xml', 'private.key', 'backup.pdf']:
        (root / name).write_bytes(b'SYNTHETIC DO NOT READ')
    result = agent().safe_inventory(str(root), [str(root)])
    assert {f['name'] for f in result['files']} == {'public.pdf', 'public.xml', 'public.cer'}
    assert result['read_only'] and not result['content_analyzed'] and not result['catalog_imported']
    assert 'SYNTHETIC DO NOT READ' not in str(result)


def test_cutoff_skips_queued_work_before_activation(client):
    c = company(client, folder='C:\\synthetic').json()
    client.post('/api/agent/heartbeat', headers=G, json={'id': 'windows-test', 'capabilities': ['scan_folder']})
    old = client.post(
        '/api/jobs', headers=A, json={'company_id': c['id'], 'agent_id': 'windows-test', 'kind': 'scan_folder'}
    ).json()
    cutoff = datetime.now(timezone.utc).isoformat()
    new = client.post(
        '/api/jobs', headers=A, json={'company_id': c['id'], 'agent_id': 'windows-test', 'kind': 'scan_folder'}
    ).json()
    response = client.post('/api/agent/windows-test/claim', params={'not_before': cutoff}, headers=G)
    assert response.status_code == 200 and response.json()['id'] == new['id']
    assert client.post('/api/agent/windows-test/claim', params={'not_before': cutoff}, headers=G).json() is None
    assert client.post('/api/agent/windows-test/claim', headers=G).json()['id'] == old['id']


def test_managed_loop_delivers_result_and_stops(tmp_path):
    root = tmp_path / 'folder'
    root.mkdir()
    (root / 'public.pdf').write_bytes(b'fake')
    event = threading.Event()
    calls = []
    given = [False]

    def request(url, token, path, data):
        calls.append((path, data))
        if path.endswith('/result'):
            event.set()
            return {'ok': True}
        if '/claim' in path and not given[0]:
            given[0] = True
            return {'id': 'job', 'kind': 'scan_folder', 'payload': {'folder': str(root)}}
        return None

    agent().run(
        {
            'api_url': 'http://127.0.0.1:9999',
            'token': 'synthetic-agent-token-123456',
            'agent_id': 'test',
            'allowed_roots': [str(root)],
            'not_before': datetime.now(timezone.utc).isoformat(),
        },
        event,
        request,
    )
    assert calls[-1][0].endswith('/result') and calls[-1][1]['status'] == 'completed'
