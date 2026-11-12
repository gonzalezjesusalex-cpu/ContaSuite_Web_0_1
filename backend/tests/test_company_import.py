import io,json,importlib.util
from pathlib import Path
from datetime import datetime,timedelta
import pytest
from openpyxl import Workbook
from sqlalchemy import select,func,update
from fastapi import HTTPException
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from test_storage_core import core
from test_api import client
from app.models import Company,now
from app.security import Principal,auth
from app.database import session
from app.company_xlsx import read_xlsx,InvalidWorkbook
from app.company_reconcile import reconcile,document_proposals,normalized_name
from app.company_import_models import metadata,sessions,rows,decisions,history
from app.company_import_api import ready,load,decide,DecisionIn,confirm,ConfirmIn,purge_expired

ADMIN=Principal('import-admin','Import admin',True,session_id='fake-session')
COMPANIES=[dict(id='a',name='Empresa Ficticia Uno SA de CV',rfc='AAA010101AA1'),dict(id='b',name='Otra Empresa Ficticia',rfc='BBB020202BB2')]

def workbook(metadata_source=False):
    book=Workbook();ws=book.active;ws.title='Noviembre 2026'
    ws.append(['Reporte sintético'])
    ws.append(['Razón social','R.F.C.','Régimen fiscal','I.S.R.','IVA','Responsable','Pago','Contraseña SAT','Desconocida','Vencimiento'])
    ws.append(['Empresa Ficticia Uno SA de CV',' aaa010101aa1 ','General',datetime(2026,11,10),'NA','Persona Ficticia','CON PAGO','SYNTHETIC-SECRET-DO-NOT-ECHO','SYNTHETIC-UNKNOWN-DO-NOT-ECHO',datetime(2027,1,1)])
    ws.append(['Empresa Ficticia Dos','CCC030303CC3','General',None,'31/99/2026','Persona Ficticia','SIN PAGO',None,None,None])
    ws.append(['Sin RFC',None,None,'=1+2',None,None,None,None,None,None])
    second=book.create_sheet('2026-12');second.append(['Empresa','RFC','ISR']);second.append(['Empresa Ficticia Uno SA de CV','AAA010101AA1','NA'])
    data=io.BytesIO();book.save(data);book.close();return data.getvalue()

@pytest.fixture
def imported(core,client):
    _,factory,_=core
    spec=importlib.util.spec_from_file_location('reconcile_migration',Path(__file__).parents[1]/'import_migrations'/'001_reconciliation.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with factory.kw['bind'].begin() as c:module.upgrade(c)
    from app.main import app
    def database():
        with factory() as db:yield db
    app.dependency_overrides[session]=database;app.dependency_overrides[auth]=lambda:ADMIN
    try:yield client,factory,app
    finally:app.dependency_overrides.pop(session,None);app.dependency_overrides.pop(auth,None)

def test_reader_sheets_periods_types_and_secret_exclusion():
    result=read_xlsx(workbook(),'obligations')
    assert len(result['sheets'])==2 and result['sheets'][0]['period']=='2026-11'
    assert len(result['rows'])==4
    first=result['rows'][0]
    assert first['cells']['ISR']['kind']=='date' and not first['cells']['ISR']['authority_validated']
    assert first['cells']['IVA']['status']=='not_applicable'
    assert first['payment']=='with_payment' and first['responsible']=='Persona Ficticia'
    assert result['rows'][1]['cells']['ISR']['status']=='unreviewed'
    assert result['rows'][1]['cells']['IVA']['kind']=='invalid_date'
    assert result['rows'][1]['payment']=='without_payment'
    assert 'formula_omitted' in result['rows'][2]['warnings']
    assert 'SYNTHETIC-SECRET' not in str(result) and 'SYNTHETIC-UNKNOWN' not in str(result)
    other=read_xlsx(workbook(),'fiscal_metadata')
    assert other['rows'][0]['cells']=={} and other['rows'][0]['certificate_date']

def test_identity_exact_approximate_conflicts_duplicates_missing():
    data=reconcile([dict(name='Empresa Ficticia Uno SA de CV',rfc='AAA010101AA1'),dict(name='Empresa Ficticia Uno SA de CV',rfc='AAA010101AA1'),dict(name='Empresa Ficticia Uno SA de C V',rfc='CCC030303CC3'),dict(name='Nueva Ficticia',rfc='DDD040404DD4'),dict(name='Sin RFC'),dict(name='Totalmente ajena',rfc='BBB020202BB2'),dict(name='Inválida',rfc='invalid-secret-input')],COMPANIES)
    assert [r['status'] for r in data]==['exact_rfc','source_duplicate','possible_name','new_company','missing_rfc','identity_conflict','manual_review']
    assert 'invalid-secret-input' not in str(data)
    assert all(r['action']=='pending' for r in data)
    assert normalized_name('Fictícia, S.A.')=='FICTICIA S A'

@pytest.mark.parametrize('content',[b'not-an-xlsx',b'',b'x'* (8*1024*1024+1)],ids=['corrupt','empty','over-limit'])
def test_corrupt_and_size_safe(content):
    with pytest.raises(InvalidWorkbook) as e:read_xlsx(content,'obligations')
    assert content[:50].decode(errors='ignore') not in str(e.value) if content else True

def test_preview_retries_decisions_and_confirmation_block(imported):
    client,dbs,app=imported;content=workbook()
    url='/api/company-imports/preview/xlsx?source=obligations&synthetic_only=true'
    r=client.post(url,content=content,headers={'Content-Type':'application/octet-stream'})
    assert r.status_code==200,r.text
    data=r.json();ident=data['id']
    assert client.post(url,content=content).json()['id']==ident
    assert 'SYNTHETIC-SECRET' not in r.text
    response=client.put(f'/api/company-imports/{ident}/rows/1',json={'revision':0,'action':'link','company_id':'company-a'})
    assert response.status_code==200 and response.json()['applied_to_companies'] is False
    assert client.put(f'/api/company-imports/{ident}/rows/1',json={'revision':0,'action':'exclude'}).status_code==409
    assert client.post(f'/api/company-imports/{ident}/confirm',json={'confirmed':True}).status_code==423
    report=client.get(f'/api/company-imports/{ident}/report').json()
    assert report['applied'] is False and report['secrets_imported']==0
    with dbs() as db:
        assert db.scalar(select(func.count()).select_from(Company))==2
        assert db.scalar(select(func.count()).select_from(sessions))==1
        assert db.scalar(select(func.count()).select_from(decisions))==1

def test_permissions_retention_and_no_schema(core,imported):
    client,factory,app=imported
    r=client.post('/api/company-imports/preview/xlsx?source=obligations&synthetic_only=true',content=workbook());ident=r.json()['id']
    app.dependency_overrides[auth]=lambda:Principal('outsider','Reader',False,frozenset({'company-b'}),session_id='fake')
    assert client.get('/api/company-imports/'+ident).status_code==403
    app.dependency_overrides[auth]=lambda:ADMIN
    with factory() as db:
        db.execute(update(sessions).values(expires_at=now()-timedelta(hours=1)));db.commit()
    assert client.get('/api/company-imports/'+ident).status_code==410
    with factory() as db:
        assert purge_expired(ADMIN,db)['purged']==1
        assert db.scalar(select(func.count()).select_from(rows))==0

def test_document_proposals_no_io():
    docs=[dict(id='one',name='AAA010101AA1_2026.xml'),dict(id='two',name='Empresa Ficticia Uno SA de CV.pdf'),dict(id='three',name='AAA010101AA1_BBB020202BB2.xml'),dict(id='four',name='unrelated.pdf')]
    proposals=document_proposals(docs,COMPANIES)
    assert [p['match'] for p in proposals]==['unambiguous','probable','conflict','unmatched']
    assert all(p['action']=='pending' and p['requires_review'] for p in proposals)
    assert 'AAA010101AA1_2026.xml' not in str(proposals)

def test_postgresql_ddl():
    for table in metadata.sorted_tables:assert str(CreateTable(table).compile(dialect=postgresql.dialect()))

def test_months_are_not_duplicates_and_aliases():
    first=dict(name='Empresa Ficticia Uno SA de CV',rfc='AAA010101AA1',source={'period':'2026-11'})
    result=reconcile([first,{**first,'source':{'period':'2026-12'}}],COMPANIES)
    assert all(r['status']=='exact_rfc' for r in result)
    result=reconcile([dict(name='Marca Alterna Sintetica',rfc='CCC030303CC3')],COMPANIES,[dict(company_id='a',name='Marca Alterna Sintetica')])
    assert result[0]['candidates'][0]['company_id']=='a'

def test_zip_external_content_rejected():
    from zipfile import ZipFile,ZIP_DEFLATED
    stream=io.BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:z.writestr('xl/embeddings/malicious.bin',b'SYNTHETIC-EMBEDDING')
    with pytest.raises(InvalidWorkbook):read_xlsx(stream.getvalue(),'obligations')

def test_import_grant_masking_revocation_and_ownership(imported):
    from app.company_import_models import permissions
    from app.models import UserAccount,UserCompanyGrant
    client,factory,app=imported
    user=Principal('import-user','Fictitious User',False,frozenset({'company-a'}),frozenset({'company-a'}),session_id='fake')
    with factory() as db:
        db.add(UserAccount(id=user.subject,username='synthetic-import-user',display_name='Fake',password_hash='unused',enabled=True,admin=False));db.flush()
        db.add(UserCompanyGrant(user_id=user.subject,company_id='company-a',access='write'));db.flush()
        db.execute(permissions.insert().values(user_id=user.subject,company_id='company-a'));db.commit()
    app.dependency_overrides[auth]=lambda:user
    r=client.post('/api/company-imports/preview/xlsx?source=obligations&synthetic_only=true',content=workbook())
    assert r.status_code==200,r.text
    assert r.json()['rows'][0]['rfc'].startswith('••••')
    ident=r.json()['id']
    assert client.put(f'/api/company-imports/{ident}/rows/1',json={'revision':0,'action':'link','company_id':'company-b'}).status_code==403
    app.dependency_overrides[auth]=lambda:ADMIN
    assert client.get('/api/company-imports/'+ident).status_code==404
    app.dependency_overrides[auth]=lambda:user
    with factory() as db:db.execute(permissions.delete().where(permissions.c.user_id==user.subject));db.commit()
    assert client.get('/api/company-imports/'+ident).status_code==403

def test_schema_guard_without_implicit_creation(core):
    with core[1]() as db:
        with pytest.raises(HTTPException) as e:ready(db)
        assert e.value.status_code==503
