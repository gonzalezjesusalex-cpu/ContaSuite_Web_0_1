import os,base64,json,importlib.util
from pathlib import Path
from datetime import timedelta
import pytest
from fastapi import Response,HTTPException
from sqlalchemy import select,func
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from test_storage_core import core
from test_api import client
from test_connector_dashboard import certificate
from app.credential_crypto import VaultCipher,VaultLocked
from app.credential_models import metadata,credentials,audit,certificates,alerts,versions
from app.credential_api import (CredentialIn,store,overview,reveal,temporal,parse_public_certificate,ready,archive)
from app.credential_alerts import refresh,list_alerts,alert_key
from app.credential_import import preview
from app.security import Principal
from app.models import now

ADMIN=Principal('admin','Admin',True,session_id='synthetic-session')
@pytest.fixture
def vault(core,monkeypatch):
    service,sessions,root=core
    spec=importlib.util.spec_from_file_location('vault_migration',Path(__file__).parents[1]/'credential_migrations'/'001_vault.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with sessions.kw['bind'].begin() as conn:module.upgrade(conn)
    from app.lote4_lifecycle import metadata as lifecycle
    lifecycle.create_all(sessions.kw['bind'])
    monkeypatch.setenv('CONTA_VAULT_KEYRING',json.dumps({'test-v1':base64.b64encode(os.urandom(32)).decode()}))
    monkeypatch.setenv('CONTA_VAULT_ACTIVE_KEY','test-v1')
    return sessions

def test_cipher_authenticated_context_rotation_and_lock():
    key=os.urandom(32);c=VaultCipher({'v1':key},'v1');secret='Fictional-test-secret-ONLY'
    sealed=c.seal(secret,'company-a','record-a')
    assert secret not in json.dumps(sealed)
    assert c.open(sealed,'company-a','record-a',authorize_recent=lambda:True)==secret
    for cid,rid in [('company-b','record-a'),('company-a','record-b')]:
        with pytest.raises(VaultLocked):c.open(sealed,cid,rid,authorize_recent=lambda:True)
    with pytest.raises(VaultLocked):c.open(sealed,'company-a','record-a',authorize_recent=lambda:False)
    rotated=VaultCipher({'v1':key,'v2':os.urandom(32)},'v2')
    assert rotated.open(sealed,'company-a','record-a',authorize_recent=lambda:True)==secret
    assert rotated.seal(secret,'a','b')['key_version']=='v2'

def test_guard_no_migration(core):
    with core[1]() as db:
        with pytest.raises(HTTPException) as e:ready(db)
        assert e.value.status_code==503

def test_store_redaction_isolation_history_and_reveal(vault):
    secret='Synthetic-secret-DO-NOT-LOG'
    payload=CredentialIn(service_id='sat_password',secret=secret)
    assert secret not in repr(payload)
    with vault() as db:
        saved=store('company-a',payload,Response(),None,ADMIN,db)
        envelope=db.execute(select(credentials.c.envelope)).scalar()
        assert secret not in json.dumps(envelope)
        snap=overview('company-a',Response(),ADMIN,db)
        assert secret not in str(snap) and 'envelope' not in str(snap) and not snap['reveal_enabled']
        assert db.scalar(select(func.count()).select_from(audit))>=2
        assert len(overview('company-b',Response(),ADMIN,db)['credentials'])==0
        outsider=Principal('outsider','Outsider',False,frozenset({'company-b'}),session_id='fake')
        with pytest.raises(HTTPException):overview('company-a',Response(),outsider,db)
        with pytest.raises(HTTPException) as forbidden:reveal('company-a',saved['id'],Response(),ADMIN,db)
        assert forbidden.value.status_code==403 # admins do not implicitly reveal
        from app.credential_models import grants
        # Test explicit reveal grant still cannot bypass missing recent-auth adapter.
        from app.models import UserAccount
        db.add(UserAccount(id='admin',username='fake',display_name='Fake',password_hash='unused',admin=True,enabled=True));db.flush()
        db.execute(grants.insert().values(user_id='admin',company_id='company-a',permission='reveal'));db.commit()
        with pytest.raises(HTTPException) as locked:reveal('company-a',saved['id'],Response(),ADMIN,db)
        assert locked.value.status_code==423
        store('company-a',CredentialIn(service_id='sat_password',secret='Other-synthetic',revision=1),Response(),saved['id'],ADMIN,db)
        assert db.scalar(select(func.count()).select_from(versions))==2
        archive('company-a',saved['id'],Response(),2,ADMIN,db)
        assert db.execute(select(credentials.c.archived)).scalar()

def test_missing_keys_fail_closed(vault,monkeypatch):
    monkeypatch.delenv('CONTA_VAULT_KEYRING');monkeypatch.delenv('CONTA_VAULT_ACTIVE_KEY')
    with vault() as db:
        with pytest.raises(HTTPException) as e:store('company-a',CredentialIn(service_id='sat_password',secret='Dummy-only'),Response(),None,ADMIN,db)
        assert e.value.status_code==423
        assert db.scalar(select(func.count()).select_from(credentials))==0

def test_x509_temporal_and_alert_dedup(vault):
    parsed=parse_public_certificate(certificate())
    assert len(parsed['fingerprint'])==64 and parsed['serial']
    assert temporal({'valid_from':None,'valid_until':None})['state']=='unknown'
    assert temporal({'valid_from':now()-timedelta(days=90),'valid_until':now()-timedelta(days=1)})['state']=='expired'
    assert temporal({'valid_from':now()-timedelta(days=1),'valid_until':now()+timedelta(days=20)})['threshold']==30
    with pytest.raises(HTTPException):parse_public_certificate(b'not-a-public-certificate')
    with vault() as db:
        db.execute(certificates.insert().values(id='cert-test',company_id='company-a',rfc='AAA010101AA1',kind='fiel',origin='synthetic',reviewed_at=now(),notes='',revision=1,**parsed));db.commit()
        # Unknown dates give an alert; no real certificate or network used.
        db.execute(certificates.update().values(valid_until=None));db.commit()
        from app.lote4_lifecycle import select_certificate,SelectionIn
        select_certificate(db,ADMIN,'company-a',SelectionIn(certificate_id='cert-test',revision=0,reason='synthetic explicit selection'))
        refresh(Response(),ADMIN,db);refresh(Response(),ADMIN,db)
        assert db.scalar(select(func.count()).select_from(alerts))==1
        assert len(list_alerts(Response(),ADMIN,db)['alerts'])==1
        assert alert_key('a','b','c')==alert_key('a','b','c')

def test_import_redacts_and_pg_schema():
    for table in metadata.sorted_tables:assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
    rows=[{'RFC':'AAA010101AA1','password':'Only-synthetic-secret','service':'SAT'}]*2
    data=preview(rows,[{'id':'a','rfc':'AAA010101AA1'}],{'RFC':'rfc','password':'secret','service':'service'})
    assert 'Only-synthetic-secret' not in str(data)
    assert data[0]['has_secret'] and 'possible_duplicate' in data[1]['conflicts']

def test_http_validation_no_secret_echo_or_shared_cache(vault,client):
    from app.main import app
    from app.database import session
    from app.security import auth
    def test_session():
        with vault() as db:yield db
    app.dependency_overrides[session]=test_session
    app.dependency_overrides[auth]=lambda:ADMIN
    try:
        dummy='Fictional-http-secret-only'
        r=client.post('/api/credentials/companies/company-a/secrets',json={'service_id':'sat_password','secret':dummy,'unwanted':dummy})
        assert r.status_code==422 and dummy not in r.text
        assert 'no-store' in r.headers['cache-control']
        r=client.get('/api/credentials/companies/company-a')
        assert r.status_code==200 and 'no-store' in r.headers['cache-control'] and 'envelope' not in r.text
    finally:
        app.dependency_overrides.pop(session,None);app.dependency_overrides.pop(auth,None)

def test_document_certificates_and_duplicates(vault,core,monkeypatch):
    import io
    from test_storage_core import ADMIN as STORAGE_ADMIN
    from app.storage import router as storage_router
    from app.credential_api import add_certificate,CertificateIn
    document=core[0].upload(STORAGE_ADMIN,io.BytesIO(certificate()),'public.cer',company_id='company-a')
    monkeypatch.setattr(storage_router,'storage_service',lambda:core[0])
    with vault() as db:
        payload=CertificateIn(document_id=document.id,kind='fiel')
        add_certificate('company-a',payload,Response(),ADMIN,db)
        with pytest.raises(HTTPException) as e:add_certificate('company-a',payload,Response(),ADMIN,db)
        assert e.value.status_code==409
        with pytest.raises(HTTPException):add_certificate('company-b',payload,Response(),ADMIN,db)

def test_obligation_alerts_do_not_infer_overdue(vault):
    spec=importlib.util.spec_from_file_location('fiscal_migration_for_alerts',Path(__file__).parents[1]/'fiscal_migrations'/'001_control_obligaciones.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with vault.kw['bind'].begin() as conn:module.upgrade(conn)
    from app.fiscal_control import CellIn,save_cell
    with vault() as db:
        save_cell(CellIn(company_id='company-a',obligation_id='fiscal-02',year=2026,month=11,revision=0,status='pending',due_date=now().date()-timedelta(days=20),due_verified=False),ADMIN,db)
        refresh(Response(),ADMIN,db)
        assert not list_alerts(Response(),ADMIN,db)['alerts']
        save_cell(CellIn(company_id='company-a',obligation_id='fiscal-02',year=2026,month=11,revision=1,status='pending',due_date=now().date()-timedelta(days=20),due_verified=True),ADMIN,db)
        refresh(Response(),ADMIN,db);refresh(Response(),ADMIN,db)
        assert db.scalar(select(func.count()).select_from(alerts))==1
