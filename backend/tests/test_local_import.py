import json
from sqlalchemy import select,func
from test_pilot_import import pilot_client,xml
from test_company_import import imported
from test_storage_core import core
from test_api import client
from app.models import Document,DocumentVersion

def local(monkeypatch,roots):
    monkeypatch.setenv('CS_LOCAL_IMPORT_ENABLED','1')
    monkeypatch.setenv('CS_LOCAL_IMPORT_ROOTS',json.dumps([str(r) for r in roots]))

def review(c,data):
    for row in data['rows']:
        payload={'revision':row['revision'],'reason':'Synthetic explicit local review'}
        if row['kind']=='company':payload.update(rfc='BBB020202BB2',name='Synthetic local company')
        else:payload.update(document_type='cfdi',links=[{'folder':'0','role':'receiver'}])
        response=c.put(f"/api/pilot-imports/{data['id']}/rows/{row['number']}",json=payload)
        assert response.status_code==200,response.text
    return response.json()

def test_local_subset_one_folder_and_idempotent_confirm(pilot_client,monkeypatch):
    c,factory,roots,_,_=pilot_client;local(monkeypatch,roots)
    assert c.get('/api/pilot-imports/options').json()['mode']=='local'
    response=c.post('/api/pilot-imports/preview',json={'folders':['1'],'authorized_read':True})
    assert response.status_code==200,response.text
    data=response.json();assert data['summary']['root_ids']==['1']
    assert data['summary']['folders'][0]['path']==str(roots[1])
    with factory() as db:assert db.scalar(select(func.count()).select_from(Document))==0
    data=review(c,data)
    endpoint='/api/pilot-imports/'+data['id']+'/confirm'
    payload={'revision':data['summary']['revision'],'confirmed':True}
    result=c.post(endpoint,json=payload);assert result.status_code==200,result.text
    assert result.json()['documents']==1 and len(result.json()['companies'])==1
    assert c.post(endpoint,json=payload).json()['idempotent'] is True
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Document))==1
        assert db.scalar(select(func.count()).select_from(DocumentVersion))==1

def test_local_invalid_ids_duplicates_and_missing_consent(pilot_client,monkeypatch):
    c,_,roots,_,_=pilot_client;local(monkeypatch,roots)
    for folders,authorized in [(['19'],True),(['0','0'],True),(['-1'],True),(['0'],False)]:
        assert c.post('/api/pilot-imports/preview',json={'folders':folders,'authorized_read':authorized}).status_code==422

def test_local_changed_roots_and_out_of_scope_links_rejected(pilot_client,monkeypatch):
    c,_,roots,_,_=pilot_client;local(monkeypatch,roots)
    data=c.post('/api/pilot-imports/preview',json={'folders':['1'],'authorized_read':True}).json()
    row=next(r for r in data['rows'] if r['kind']=='document')
    response=c.put(f"/api/pilot-imports/{data['id']}/rows/{row['number']}",json={'revision':row['revision'],'reason':'Synthetic invalid target','links':[{'folder':'1','role':'owner'}]})
    assert response.status_code==422
    data=review(c,data);monkeypatch.setenv('CS_LOCAL_IMPORT_ROOTS',json.dumps([str(roots[0])]))
    assert c.post('/api/pilot-imports/'+data['id']+'/confirm',json={'revision':data['summary']['revision'],'confirmed':True}).status_code==409

def test_local_mode_still_rejects_nonexclusive_database(imported,monkeypatch):
    c,_,_=imported;monkeypatch.setenv('CS_LOCAL_IMPORT_ENABLED','1');monkeypatch.setenv('CS_LOCAL_IMPORT_DATABASE','contasuite_local_example')
    assert c.get('/api/pilot-imports/options').status_code==423
