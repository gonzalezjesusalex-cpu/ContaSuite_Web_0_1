import io
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy import select,func
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID,ObjectIdentifier
from test_api import client,A
from test_storage_core import core,ADMIN,actor,XML
from app.main import app
from app.models import StorageSource,StorageIndexJob,StorageWorkerState,Document,now
from app.storage.router import storage_service,SourceConfiguration
from app.storage.connector import ConnectorService
from app.storage.dashboard import DashboardService
from app.storage.indexer import LocalIndexer
from app.storage.providers import StorageError


def source_payload(root,**kwargs):
    return SourceConfiguration(label='Origen de prueba',kind='local_folder',root_path=str(root),**kwargs)


@pytest.fixture
def connector_api(client,core):
    service,sessions,root=core
    app.dependency_overrides[storage_service]=lambda:service
    try:
        yield client,service,sessions,root
    finally:
        app.dependency_overrides.pop(storage_service,None)


def certificate(rfc='AAA010101AA1',start=-10,end=90):
    key=ec.generate_private_key(ec.SECP256R1())
    subject=[x509.NameAttribute(NameOID.COMMON_NAME,'Certificado sintético')]
    if rfc:
        subject.append(x509.NameAttribute(ObjectIdentifier('2.5.4.45'),rfc))
    cert=(x509.CertificateBuilder().subject_name(x509.Name(subject)).issuer_name(x509.Name(subject))
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now()+timedelta(days=start)).not_valid_after(now()+timedelta(days=end)).sign(key,hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.DER)


def add_cert(service,company='company-a',rfc='AAA010101AA1',start=-10,end=90,category='e.firma (FIEL)',name='fiel.cer'):
    return service.upload(ADMIN,io.BytesIO(certificate(rfc,start,end)),name,company_id=company,category=category,document_type='certificate')


def test_configuration_probe_schedule_and_history(core):
    service,sessions,root=core
    (root/'a.xml').write_bytes(XML)
    connector=ConnectorService(service)
    saved=connector.save(ADMIN,source_payload(root,interval_minutes=5,exclusions=['skip','*.tmp']))
    item=next(s for s in connector.list(ADMIN)['sources'] if s['id']==saved['id'])
    assert item['state']=='unchecked' and item['interval_minutes']==5 and item['document_count']==0
    assert connector.probe(ADMIN,saved['id'])['state']=='available'
    indexer=LocalIndexer(service)
    assert indexer.tick('worker-test')==0
    with sessions.begin() as db:
        db.get(StorageSource,saved['id']).next_scan_at=now()-timedelta(seconds=1)
    assert indexer.tick('worker-test')==1
    assert indexer.tick('worker-two')==0
    assert connector.list(ADMIN)['worker']['online']
    job=indexer.claim('worker-test')
    indexer.run(job,'worker-test')
    item=next(s for s in connector.list(ADMIN)['sources'] if s['id']==saved['id'])
    assert item['document_count']==1 and item['last_job']['status']=='completed'
    with sessions.begin() as db:
        db.get(StorageWorkerState,'indexer').heartbeat_at=now()-timedelta(minutes=4)
    assert not connector.list(ADMIN)['worker']['online']


def test_edit_revisions_immutable_root_busy_and_disable(core):
    service,sessions,root=core
    connector=ConnectorService(service)
    saved=connector.save(ADMIN,source_payload(root))
    with pytest.raises(StorageError,match='duplicate_source'):
        connector.save(ADMIN,source_payload(root))
    with pytest.raises(StorageError,match='revision_conflict'):
        connector.save(ADMIN,source_payload(root,revision=99),saved['id'])
    child=root/'child'
    child.mkdir()
    with pytest.raises(StorageError,match='immutable_source'):
        connector.save(ADMIN,source_payload(child,revision=1),saved['id'])
    LocalIndexer(service).enqueue(ADMIN,saved['id'])
    with pytest.raises(StorageError,match='source_busy'):
        connector.save(ADMIN,source_payload(root,revision=1,enabled=False),saved['id'])
    indexer=LocalIndexer(service)
    job=indexer.claim('w')
    indexer.run(job,'w')
    connector.save(ADMIN,source_payload(root,revision=1,enabled=False),saved['id'])
    assert connector.probe(ADMIN,saved['id'])['code']=='source_disabled'
    assert indexer.tick('w')==0


def test_source_api_admin_and_safe_errors(connector_api):
    c,service,sessions,root=connector_api
    assert c.get('/api/storage/connector/sources').status_code==401
    assert c.get('/api/storage/connector/options',headers=A).json()['allowed_roots']==[str(root)]
    request=dict(label='Local',kind='local_folder',root_path=str(root),interval_minutes=5)
    response=c.post('/api/storage/connector/sources',headers=A,json=request)
    assert response.status_code==201,response.text
    ident=response.json()['id']
    assert c.post('/api/storage/connector/sources/'+ident+'/probe',headers=A).json()['state']=='available'
    request['root_path']=str(root.parent/'unauthorized')
    denied=c.post('/api/storage/connector/sources',headers=A,json=request)
    assert denied.status_code==409 and str(root.parent) not in denied.text
    assert c.post('/api/storage/connector/sources',headers=A,json={**request,'password':'Do-not-echo-secret'}).status_code==422
    assert c.post('/api/storage/connector/sources',headers=A,json={**request,'interval_minutes':1}).status_code in {409,422}


def test_windows_is_private_disabled_draft_without_any_network(core,monkeypatch):
    import os
    import socket
    service,sessions,root=core
    def forbidden(*args,**kwargs):
        raise AssertionError('A Windows draft must not touch filesystem/network')
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    monkeypatch.setattr(os,'scandir',forbidden)
    connector=ConnectorService(service)
    payload=SourceConfiguration(label='Windows futuro',kind='windows_smb',enabled=False,
        windows={'server':'server-example','share':'fiscal','subdirectory':'clientes','account_name':'DEMO\\lector','credential_reference':'CredentialManager/cs-read'})
    saved=connector.save(ADMIN,payload)
    assert connector.probe(ADMIN,saved['id'])['state']=='pending_configuration'
    assert LocalIndexer(service).tick('w')==0
    with pytest.raises(StorageError):
        LocalIndexer(service).enqueue(ADMIN,saved['id'])
    with pytest.raises(StorageError,match='forbidden'):
        connector.list(actor('company-a','read'))
    with pytest.raises(StorageError,match='forbidden'):
        connector.options(actor('company-a','read'))


@pytest.mark.parametrize('end,expected',[(90,'valid'),(20,'expiring'),(-1,'expired')])
def test_certificate_dates_and_company_counts(core,end,expected):
    service,sessions,root=core
    doc=add_cert(service,start=-100,end=end)
    report=DashboardService(service).report(ADMIN)
    company=next(c for c in report['companies'] if c['id']=='company-a')
    assert company['fiel_state']==expected and company['document_count']==1
    assert company['certificate_id']==doc.id and report['sat_validated'] is False
    assert report['certificates'][0]['rfcs']==['AAA010101AA1']
    assert report['counts'][expected]==1 and report['counts']['missing']==1


def test_renewed_certificate_supersedes_old_for_company_alert(core):
    service,sessions,root=core
    add_cert(service,start=-200,end=-10,name='old.cer')
    current=add_cert(service,name='new.cer')
    report=DashboardService(service).report(ADMIN,'company-a')
    assert len(report['companies'])==1 and report['counts']['valid']==1 and report['counts']['expired']==0
    assert report['companies'][0]['certificate_id']==current.id


def test_csd_unknown_rfc_mismatch_future_missing_and_missing_file(core):
    service,sessions,root=core
    add_cert(service,category='CSD')
    assert DashboardService(service).report(ADMIN)['counts']['missing']==2
    add_cert(service,rfc='',name='no-rfc.cer')
    assert DashboardService(service).report(ADMIN,'company-a')['companies'][0]['fiel_state']=='unverified'
    add_cert(service,company='company-b',name='wrong-rfc.cer')
    assert DashboardService(service).report(ADMIN,'company-b')['companies'][0]['fiel_state']=='rfc_mismatch'
    doc=add_cert(service,start=10,end=100,name='future.cer')
    assert DashboardService(service).report(ADMIN,'company-a')['companies'][0]['fiel_state']=='not_yet_valid'
    from app.models import DocumentLocation,DocumentVersion
    with sessions() as db:
        location=db.scalar(select(DocumentLocation).join(DocumentVersion).where(DocumentVersion.document_id==doc.id))
        path=service.settings.internal_root/location.relative_key
    path.unlink()  # Disposable pytest repository only.
    assert any(c['id']==doc.id and c['state']=='unavailable' for c in DashboardService(service).report(ADMIN)['certificates'])


def test_label_permissions_revision_and_dashboard_scope(core):
    service,sessions,root=core
    doc=add_cert(service,category='General')
    other=add_cert(service,company='company-b',rfc='BBB020202BB2',name='b.cer')
    reader=actor('company-a','read')
    assert [c['id'] for c in DashboardService(service).report(reader)['companies']]==['company-a']
    assert [c['id'] for c in DashboardService(service).report(reader)['certificates']]==[doc.id]
    with pytest.raises(StorageError):
        DashboardService(service).report(reader,'company-b')
    with pytest.raises(StorageError):
        DashboardService(service).label(reader,doc.id,1,'fiel')
    with pytest.raises(StorageError,match='revision_conflict'):
        DashboardService(service).label(ADMIN,doc.id,99,'fiel')
    DashboardService(service).label(actor('company-a','read','write'),doc.id,1,'fiel')
    assert DashboardService(service).report(reader)['counts']['valid']==1
    assert service.document(ADMIN,doc.id).revision==1


def test_dashboard_api(connector_api):
    c,service,sessions,root=connector_api
    doc=add_cert(service)
    assert c.get('/api/storage/dashboard').status_code==401
    result=c.get('/api/storage/dashboard',headers=A)
    assert result.status_code==200,result.text
    assert result.json()['counts']['valid']==1
    assert c.put('/api/storage/documents/'+doc.id+'/certificate-usage',headers=A,json={'revision':1,'usage':'csd'}).status_code==200
    assert c.get('/api/storage/dashboard',headers=A).json()['counts']['valid']==0


def test_disable_remains_possible_after_allowlist_is_revoked(core):
    from dataclasses import replace
    from app.storage.service import StorageService
    service,sessions,root=core
    saved=ConnectorService(service).save(ADMIN,source_payload(root))
    restricted=StorageService(sessions,replace(service.settings,allowed_roots=()))
    ConnectorService(restricted).save(ADMIN,source_payload(root,revision=1,enabled=False),saved['id'])
    with sessions() as db:
        assert not db.get(StorageSource,saved['id']).enabled
