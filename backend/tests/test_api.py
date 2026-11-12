import importlib.util
import atexit
import os
from pathlib import Path
import tempfile

import pytest
from fastapi.testclient import TestClient

TEMP=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(TEMP.name)/'test.db')
os.environ['DATA_DIR']=str(Path(TEMP.name)/'data')
os.environ['APP_TOKEN']='test-app-token-for-contasuite-only'
os.environ['AGENT_TOKEN']='test-agent-token-for-contasuite-only'
os.environ['SEED_DEMO']='false'
os.environ['PYTHON_DOTENV_DISABLED']='1'
os.environ['CS_STORAGE_ALLOWED_ROOTS']='[]'
os.environ['CS_STORAGE_SMB_ALLOWED_ROOTS']='[]'
from app.main import app
from app.database import Base,engine
from sqlalchemy import text
from app.models import Company
atexit.register(engine.dispose)
A={'Authorization':'Bearer '+os.environ['APP_TOKEN']}
G={'Authorization':'Bearer '+os.environ['AGENT_TOKEN']}

@pytest.fixture()
def client():
    # Explicit synthetic schema setup: ordinary application startup no longer migrates.
    engine.dispose()
    database=Path(TEMP.name)/'test.db'
    if database.exists():database.unlink()
    from app.receipt_migration import migrate_receipts
    from app.storage.migrate import upgrade_storage
    migrate_receipts(engine);upgrade_storage(engine)
    from app.schema_compatibility import metadatas
    for metadata in metadatas():metadata.create_all(engine)
    with TestClient(app) as client:yield client

def company(client,**kw):
    return client.post('/api/companies',headers=A,json={'name':'Arkos Suministros SA de CV','rfc':'ASU260331IWA',**kw})

def test_auth_is_required(client):
    assert client.get('/api/health').status_code==200
    assert client.get('/api/state').status_code==401
    assert client.get('/api/state',headers=G).status_code==401
    assert client.post('/api/agent/heartbeat',headers=A,json={'id':'local','capabilities':[]}).status_code==401

def test_company_create_update_duplicate_and_rfc_validation(client):
    r=company(client);assert r.status_code==201;c=r.json()
    assert not c['is_demo']
    assert company(client).status_code==409
    assert company(client,rfc='ABC261332AA1').status_code==422
    assert company(client,person_type='Física').status_code==422
    data={k:v for k,v in c.items() if k not in {'id','created_at','is_demo'}};data['name']='Arkos actualizado'
    assert client.put('/api/companies/'+c['id'],headers=A,json=data).status_code==200
    assert client.get('/api/state',headers=A).json()['companies'][0]['name']=='Arkos actualizado'

def test_tasks_and_obligations_round_trip(client):
    c=company(client).json()
    t={'company_id':c['id'],'title':'Revisar acuses','due_date':'2026-11-17','responsible':'Jesús Alejandro'}
    r=client.post('/api/tasks',headers=A,json=t);assert r.status_code==201
    data=r.json();id=data.pop('id');data['status']='Completada'
    assert client.put('/api/tasks/'+id,headers=A,json=data).json()['status']=='Completada'
    o={'company_id':c['id'],'title':'ISR mensual','period':'2026-10','due_date':'2026-11-17'}
    r=client.post('/api/obligations',headers=A,json=o);assert r.status_code==201
    data=r.json();id=data.pop('id');data['status']='Presentada';data['reference']='FOLIO-1'
    assert client.put('/api/obligations/'+id,headers=A,json=data).json()['reference']=='FOLIO-1'
    assert client.post('/api/tasks',headers=A,json={**t,'company_id':'missing'}).status_code==404
    assert client.post('/api/obligations',headers=A,json={**o,'period':'2026-13'}).status_code==422

def test_legacy_document_download_registers_and_preserves_history(client):
    c=company(client).json();id=c['id'];pdf=b'%PDF-1.4 test'
    r=client.post(f'/api/companies/{id}/documents',headers=A,files={'file':('..\\test.pdf',pdf,'application/pdf')},data={'category':'Constancia fiscal'})
    assert r.status_code==201;doc=r.json();assert doc['name']=='test.pdf'
    assert client.get('/api/documents/'+doc['id']+'/download',headers=A).content==pdf
    assert client.post(f'/api/companies/{id}/documents',headers=A,files={'file':('secret.key',b'key')}).status_code==422
    assert client.post(f'/api/companies/{id}/documents',headers=A,files={'file':('empty.pdf',b'')}).status_code==422
    client.post('/api/tasks',headers=A,json={'company_id':id,'title':'Prueba','due_date':'2026-11-17'})
    client.post('/api/obligations',headers=A,json={'company_id':id,'title':'ISR','period':'2026-10','due_date':'2026-11-17'})
    # Download now adopts the legacy attachment into CS-Storage; history prevents cascading deletion.
    assert client.delete('/api/companies/'+id,headers=A).status_code==409
    assert client.delete('/api/documents/'+doc['id'],headers=A).status_code==409
    state=client.get('/api/state',headers=A).json()
    assert len(state['companies'])==len(state['tasks'])==len(state['obligations'])==len(state['documents'])==1
    assert list((Path(os.environ['DATA_DIR'])/'documents').iterdir())
    detail=client.get('/api/storage/documents/'+doc['id'],headers=A).json()
    assert detail['versions'][0]['sha256']

def test_agent_job_lifecycle_and_permissions(client):
    c=company(client,folder=str(Path(TEMP.name))).json()
    assert client.post('/api/agent/heartbeat',headers=G,json={'id':'local','capabilities':['scan_folder']}).status_code==200
    assert client.post('/api/jobs',headers=A,json={'company_id':c['id'],'agent_id':'local','kind':'shell'}).status_code==422
    r=client.post('/api/jobs',headers=A,json={'company_id':c['id'],'agent_id':'local','kind':'scan_folder'});assert r.status_code==201;id=r.json()['id']
    assert client.delete('/api/companies/'+c['id'],headers=A).status_code==409
    job=client.post('/api/agent/local/claim',headers=G).json();assert job['id']==id
    assert client.post('/api/agent/local/claim',headers=G).json() is None
    assert client.post('/api/agent/jobs/'+id+'/result',headers=G,json={'agent_id':'wrong','status':'completed','result':{}}).status_code==409
    assert client.post('/api/agent/jobs/'+id+'/result',headers=G,json={'agent_id':'local','status':'completed','result':{'files':[]}}).status_code==200
    assert client.post('/api/agent/jobs/'+id+'/result',headers=G,json={'agent_id':'local','status':'completed','result':{}}).status_code==409
    assert client.delete('/api/companies/'+c['id'],headers=A).status_code==409
    assert any(row['id']==c['id'] for row in client.get('/api/state',headers=A).json()['companies'])

def test_explicit_demo_preserves_company_history_from_deletion(client):
    assert client.post('/api/demo',headers=A).status_code==200
    state=client.get('/api/state',headers=A).json()
    assert len(state['companies'])==3 and all(c['is_demo'] for c in state['companies'])
    assert len(state['tasks'])==3
    assert client.post('/api/demo',headers=A).status_code==409
    for c in state['companies']:assert client.delete('/api/companies/'+c['id'],headers=A).status_code==409
    assert len(client.get('/api/state',headers=A).json()['companies'])==3

def test_database_survives_app_restart(client):
    c=company(client).json()
    with TestClient(app) as second:
        assert second.get('/api/state',headers=A).json()['companies'][0]['id']==c['id']

def test_scanner_only_authorized_paths(tmp_path):
    spec=importlib.util.spec_from_file_location('agent',Path(__file__).resolve().parents[2]/'agent'/'agent.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    allowed=tmp_path/'allowed';allowed.mkdir();(allowed/'test.pdf').write_bytes(b'pdf');(allowed/'test.key').write_bytes(b'secret');(allowed/'skip.exe').write_bytes(b'ignore')
    outside=tmp_path/'outside';outside.mkdir();(outside/'private.xml').write_bytes(b'private')
    try:
        (allowed/'escape').symlink_to(outside,target_is_directory=True)
    except OSError as exc:
        if getattr(exc,'winerror',None)==1314:
            pytest.skip('Windows no permite crear enlaces simbólicos sin privilegios o modo desarrollador')
        raise
    result=module.scan_folder(str(allowed),[str(allowed)])
    assert {f['name'] for f in result['files']}=={'test.pdf','test.key'}
    assert all('content' not in f for f in result['files'])
    assert (allowed/'test.key').read_bytes()==b'secret'
    with pytest.raises(ValueError):module.scan_folder(str(outside),[str(allowed)])

def test_startup_never_seeds_even_when_old_flag_is_set(client):
    os.environ['SEED_DEMO']='true'
    try:
        with TestClient(app) as first:
            companies=first.get('/api/state',headers=A).json()['companies']
            assert companies==[]
        with TestClient(app) as restarted:
            assert restarted.get('/api/state',headers=A).json()['companies']==[]
    finally:os.environ['SEED_DEMO']='false'
