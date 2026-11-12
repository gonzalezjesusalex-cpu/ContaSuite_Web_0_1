"""Synthetic-only pilot regression. SQLite exercises transactions; PG gate tested separately."""
import hashlib
import io
import json
from pathlib import Path
import pytest
from sqlalchemy import select,func,update
from test_company_import import imported,ADMIN
from test_storage_core import core
from test_api import client
from app import pilot_import as pilot
from app.pilot_scan import scan,roots_from_environment,configured_limits
from app.pilot_extract import analyze
from app.models import Company,Document,DocumentVersion,DocumentCompanyLink,DocumentClassificationReview as Review,StorageSource
from app.storage.service import StorageService
from app.storage.settings import StorageSettings
from app.storage.providers import StorageError
from app.company_import_models import sessions,rows,history
from app.company_lifecycle import metadata as archive_metadata,states
from app.document_identity import identities
from app.security import Principal,auth
from app.storage.router import storage_service


def xml(total='100',uuid='11111111-1111-1111-1111-111111111111'):
    return (f'<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" Fecha="2026-11-11T12:00:00" Total="{total}"><c:Emisor Rfc="AAA010101AA1" Nombre="SYNTHETIC A"/><c:Receptor Rfc="BBB020202BB2" Nombre="SYNTHETIC B"/><c:Complemento><t:TimbreFiscalDigital UUID="{uuid}"/></c:Complemento></c:Comprobante>').encode()


@pytest.fixture
def pilot_client(imported,tmp_path,monkeypatch):
    client,factory,app=imported
    roots=[tmp_path/'copies/A',tmp_path/'copies/B']
    for root in roots:root.mkdir(parents=True)
    (roots[0]/'one.xml').write_bytes(xml());(roots[1]/'two.xml').write_bytes(xml())
    monkeypatch.setenv('CS_PILOT_ROOTS',json.dumps([str(r) for r in roots]))
    monkeypatch.setattr(pilot,'authorized',lambda p,db:p.require_admin())
    # Test extractor in-process; actual bounded child covered in PostgreSQL/HTTP lab.
    import app.pilot_scan as scanner
    monkeypatch.setattr(scanner,'extract',analyze)
    service=StorageService(factory,StorageSettings(tmp_path/'private',tmp_path/'legacy',tuple(roots)))
    app.dependency_overrides[storage_service]=lambda:service
    yield client,factory,roots,app,service
    app.dependency_overrides.pop(storage_service,None)


def preview(c):
    r=c.post('/api/pilot-imports/preview',json={'folders':['0','1'],'authorized_read':True})
    assert r.status_code==200,r.text
    return r.json()


def reviewed(c,data):
    for row in data['rows']:
        payload={'revision':row['revision'],'reason':'Synthetic human review'}
        if row['kind']=='company':
            payload.update(rfc='AAA010101AA1' if row['folder']=='0' else 'BBB020202BB2',name='SYNTHETIC '+row['folder'])
        else:payload.update(document_type='cfdi',links=[{'folder':'0','role':'issuer'},{'folder':'1','role':'receiver'}])
        r=c.put(f"/api/pilot-imports/{data['id']}/rows/{row['number']}",json=payload);assert r.status_code==200,r.text
    return r.json()


def confirm(c,data):return c.post('/api/pilot-imports/'+data['id']+'/confirm',json={'revision':data['summary']['revision'],'confirmed':True})


def test_preview_does_not_create_documents_or_select_company_by_folder(pilot_client):
    c,factory,roots,_,_=pilot_client;data=preview(c)
    assert all(not r['rfc'] for r in data['rows'] if r['kind']=='company')
    assert {v['rfc'] for v in data['rows'][0]['candidates']}=={'AAA010101AA1','BBB020202BB2'}
    with factory() as db:assert db.scalar(select(func.count()).select_from(Document))==0
    assert confirm(c,data).status_code==422


def test_confirm_idempotent_reimport_shared_roles_and_audit(pilot_client):
    c,factory,roots,_,_=pilot_client;before={p:hashlib.sha256(p.read_bytes()).hexdigest() for r in roots for p in r.rglob('*') if p.is_file()}
    data=reviewed(c,preview(c));result=confirm(c,data);assert result.status_code==200,result.text
    assert confirm(c,data).json()['idempotent'] is True
    again=reviewed(c,preview(c));assert confirm(c,again).status_code==200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Company))==2
        assert db.scalar(select(func.count()).select_from(Document))==2
        assert db.scalar(select(func.count()).select_from(DocumentVersion))==2
        assert db.scalar(select(func.count()).select_from(DocumentCompanyLink))==4
        assert {r.role for r in db.scalars(select(DocumentCompanyLink))}=={'issuer','receiver'}
        assert db.scalar(select(func.count()).select_from(history).where(history.c.action=='pilot_confirmed'))==2
        assert db.get(Company,'company-a').name=='Empresa A'
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==v for p,v in before.items())


def test_uuid_conflicts_remain_pending_and_have_no_auto_associations(pilot_client):
    c,factory,roots,_,_=pilot_client;(roots[1]/'two.xml').write_bytes(xml('999'))
    data=reviewed(c,preview(c));assert data['summary']['conflicts']==2
    response=confirm(c,data);assert response.status_code==200,response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DocumentCompanyLink))==0
        assert db.scalar(select(func.count()).select_from(Review).where(Review.status=='pending'))==2
        assert all(db.scalars(select(identities.c.requires_review)))


def test_reimport_correction_appends_review_and_keeps_previous_decision(pilot_client):
    c,factory,_,_,_=pilot_client;data=reviewed(c,preview(c));assert confirm(c,data).status_code==200
    with factory() as db:
        old={r.id:dict(r.evidence) for r in db.scalars(select(Review))}
    again=reviewed(c,preview(c))
    row=next(r for r in again['rows'] if r['kind']=='document')
    response=c.put(f"/api/pilot-imports/{again['id']}/rows/{row['number']}",json={'revision':row['revision'],
        'document_type':'other','links':[{'folder':'0','role':'owner'}],'reason':'Explicit synthetic correction'})
    assert response.status_code==200
    assert confirm(c,response.json()).status_code==200
    with factory() as db:
        assert all(db.get(Review,key).evidence==value for key,value in old.items())
        assert db.scalar(select(func.count()).select_from(Review))==len(old)+1
        assert db.scalar(select(func.count()).select_from(DocumentVersion))==2
        assert db.scalar(select(func.count()).select_from(Document).where(Document.document_type=='other'))==1


def test_changed_source_or_stale_revision_rejected_before_writes(pilot_client):
    c,factory,roots,_,_=pilot_client;data=reviewed(c,preview(c))
    stale=c.post('/api/pilot-imports/'+data['id']+'/confirm',json={'revision':0,'confirmed':True});assert stale.status_code==409
    (roots[0]/'one.xml').write_bytes(xml('200'))
    assert confirm(c,data).status_code==409
    with factory() as db:assert db.scalar(select(func.count()).select_from(Document))==0


def test_partial_import_rolls_back_all_companies_sources_and_documents(pilot_client,monkeypatch):
    c,factory,roots,_,service=pilot_client;data=reviewed(c,preview(c));original=StorageService.observe_external;calls=[]
    def fail_second(self,*a,**kw):
        calls.append(1)
        if len(calls)==2:raise StorageError('file_changed')
        return original(self,*a,**kw)
    monkeypatch.setattr(StorageService,'observe_external',fail_second)
    assert confirm(c,data).status_code==409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Document))==0
        assert db.scalar(select(func.count()).select_from(StorageSource).where(StorageSource.kind=='local_folder'))==0
        assert db.scalar(select(sessions.c.status).where(sessions.c.id==data['id']))=='preview'


def test_archived_company_is_not_reactivated(pilot_client):
    c,factory,_,_,_=pilot_client;archive_metadata.create_all(factory.kw['bind'])
    from app.models import now
    with factory.begin() as db:db.execute(states.insert().values(company_id='company-a',archived=True,revision=1,actor_id='synthetic',updated_at=now()))
    data=reviewed(c,preview(c));assert confirm(c,data).status_code==409
    with factory() as db:assert db.scalar(select(func.count()).select_from(Document))==0


def test_reader_cannot_select_scan_or_confirm(pilot_client):
    c,_,_,app,_=pilot_client;app.dependency_overrides[auth]=lambda:Principal('reader','Reader',False,session_id='synthetic')
    assert c.get('/api/pilot-imports/options').status_code==403
    assert c.post('/api/pilot-imports/preview',json={'folders':['0','1'],'authorized_read':True}).status_code==403
    assert c.post('/api/pilot-imports/unknown/confirm',json={'revision':0,'confirmed':True}).status_code==403


def test_old_importer_cannot_edit_or_purge_pilot_history(pilot_client):
    c,_,_,_,_=pilot_client;data=reviewed(c,preview(c));assert confirm(c,data).status_code==200
    assert c.delete('/api/company-imports/'+data['id']).status_code==404
    assert c.get('/api/company-imports/'+data['id']).status_code==404
    assert c.get('/api/pilot-imports').json()['items'][0]['id']==data['id']


def test_explicit_confirmation_and_real_database_gate(imported,monkeypatch):
    c,factory,_=imported
    monkeypatch.setenv('CS_PILOT_ENABLED','1');monkeypatch.setenv('CS_PILOT_DATABASE','contasuite_pilot_test')
    assert c.get('/api/pilot-imports/options').status_code==423
    assert c.post('/api/pilot-imports/preview',json={'folders':['0','1'],'authorized_read':True}).status_code==423


def test_secret_and_unsupported_bytes_are_never_opened(tmp_path,monkeypatch):
    roots=[tmp_path/'A',tmp_path/'B']
    for r in roots:r.mkdir()
    (roots[0]/'secret.xml').write_bytes(b'NEVER READ');(roots[0]/'file.key').write_bytes(b'NEVER READ')
    (roots[1]/'passwords').mkdir();(roots[1]/'passwords/file.xml').write_bytes(b'NEVER READ')
    (roots[1]/'notes.txt').write_bytes(b'NEVER READ')
    (roots[0]/'valid.xml').write_bytes(xml())
    from app.storage.local import LocalFolderProvider
    original=LocalFolderProvider.open_read;opened=[]
    def track(self,key):opened.append(key);return original(self,key)
    monkeypatch.setattr(LocalFolderProvider,'open_read',track)
    import app.pilot_scan as scanner;monkeypatch.setattr(scanner,'extract',analyze)
    result=scan(roots);assert opened==['valid.xml'];assert len(result['documents'])==1
    assert result['folders'][1]['issues']==[{'key':'notes.txt','code':'unsupported_format'}]
    assert 'NEVER READ' not in json.dumps(result)


def test_limits_abort_without_partial_preview(tmp_path,monkeypatch):
    roots=[tmp_path/'A',tmp_path/'B']
    for r in roots:r.mkdir();(r/'a.xml').write_bytes(xml())
    import app.pilot_scan as scanner;monkeypatch.setattr(scanner,'extract',analyze)
    with pytest.raises(StorageError,match='scan_limit'):scan(roots,max_files=1)
    monkeypatch.setenv('CS_PILOT_MAX_FILES','10000')
    with pytest.raises(StorageError):configured_limits()


def test_unauthorized_paths_are_rejected_before_probe(monkeypatch):
    monkeypatch.setenv('CS_PILOT_ROOTS',json.dumps(['\\\\forbidden\\share','C:\\authorized']))
    with pytest.raises(StorageError):roots_from_environment()
    monkeypatch.setenv('CS_PILOT_ROOTS',json.dumps(['relative','another']))
    with pytest.raises(StorageError):roots_from_environment()


def test_malformed_content_and_ambiguous_uuid_are_not_fiscal_verification():
    assert analyze(b'not xml','invalid.xml')['evidence']['readable'] is False
    result=analyze(xml(uuid='invalid'),'valid.xml')
    assert result['evidence']['uuid_status']=='contradictory'
    assert result['evidence']['authority_validated'] is False
