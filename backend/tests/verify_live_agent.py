"""Standalone integration check using real HTTP, FastAPI and the polling worker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import httpx

root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as folder:
    temp=Path(folder);allowed=temp/'companies';allowed.mkdir();(allowed/'example.xml').write_text('<Comprobante/>');(allowed/'private.key').write_bytes(b'LOCAL_ONLY')
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(temp/'live.db'),'DATA_DIR':str(temp/'data'),'SEED_DEMO':'false','APP_TOKEN':'local-integration-app-token-only','AGENT_TOKEN':'local-integration-agent-token-only','PYTHONPATH':str(root/'backend'),'NO_PROXY':'127.0.0.1,localhost'}
    api=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8129'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    worker=None
    try:
        with httpx.Client(base_url='http://127.0.0.1:8129',headers={'Authorization':'Bearer '+env['APP_TOKEN']},trust_env=False,timeout=3) as client:
            for _ in range(60):
                try:
                    if client.get('/api/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.2)
            else:raise AssertionError('La API no inició')
            config=temp/'agent.json';config.write_text(json.dumps({'api_url':'http://127.0.0.1:8129','agent_id':'integration-worker','token':env['AGENT_TOKEN'],'allowed_roots':[str(allowed)]}))
            worker=subprocess.Popen([sys.executable,str(root/'agent/agent.py'),'--config',str(config)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(60):
                if client.get('/api/state').json()['agents']:break
                time.sleep(.2)
            else:raise AssertionError('El agente no se conectó')
            company=client.post('/api/companies',json={'name':'Live Agent Test','rfc':'LAT261109AA1','folder':str(allowed)});company.raise_for_status();id=company.json()['id']
            job=client.post('/api/jobs',json={'company_id':id,'agent_id':'integration-worker','kind':'scan_folder'});job.raise_for_status();jobid=job.json()['id']
            for _ in range(80):
                state=client.get('/api/state').json();result=next(j for j in state['jobs'] if j['id']==jobid)
                if result['status'] in ['completed','failed']:break
                time.sleep(.2)
            assert result['status']=='completed',result
            assert {f['name'] for f in result['result']['files']}=={'example.xml','private.key'}
            assert 'LOCAL_ONLY' not in json.dumps(result)
            assert (allowed/'private.key').read_bytes()==b'LOCAL_ONLY'
            print('PASS: heartbeat -> queue -> claim -> scan -> result; source files unchanged; private key contents never transmitted.')
    finally:
        if worker:worker.terminate();worker.wait(timeout=5)
        api.terminate();api.wait(timeout=5)
