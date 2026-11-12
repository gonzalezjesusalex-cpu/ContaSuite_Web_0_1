import io,importlib.util
from pathlib import Path
from datetime import date
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from test_storage_core import core,ADMIN as STORAGE_ADMIN,XML
from app.models import Company,Document,StorageSource,DocumentClassificationReview,now
from app.security import Principal
from app.integral_models import metadata,verification,classified
from app.integral_dashboard import dashboard
from app.integral_api import ready,analyze,AnalyzeIn,decision,DecisionIn,verify,VerifyIn,explorer
from app.virtual_classifier import propose,analyze_public
from app.fiscal_control import save_cell,CellIn,records

ADMIN=Principal('v3-admin','Admin',True,session_id='fake')
@pytest.fixture
def integral(core,monkeypatch):
    service,factory,root=core
    from app.database import Base
    Base.metadata.create_all(factory.kw['bind'])
    from app.models import Task
    Task.__table__.create(factory.kw['bind'],checkfirst=True)
    for folder,name in [('fiscal_migrations','001_control_obligaciones.py'),('credential_migrations','001_vault.py'),('integral_migrations','001_integral.py'),('integral_migrations','002_evidence_history.py')]:
        spec=importlib.util.spec_from_file_location(folder,Path(__file__).parents[1]/folder/name)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with factory.kw['bind'].begin() as conn:mod.upgrade(conn)
    import app.storage.router as storage_router
    monkeypatch.setattr(storage_router,'storage_service',lambda:service)
    with factory.begin() as db:
        db.get(Company,'company-a').accountant='Ana'
        db.get(Company,'company-b').accountant='Beto'
    return service,factory,root

def cell(**kw):return CellIn(**(dict(company_id='company-a',obligation_id='fiscal-02',year=2026,month=5,revision=0,status='pending')|kw))

def test_dashboard_filters_na_verified_and_staleness(integral):
    service,factory,_=integral
    doc=service.upload(STORAGE_ADMIN,io.BytesIO(XML),'evidence.xml',company_id='company-a')
    with factory() as db:
        saved=save_cell(cell(status='fulfilled'),ADMIN,db)
        save_cell(cell(company_id='company-b',status='not_applicable'),ADMIN,db)
        report=dashboard(db,ADMIN,2026,5)
        assert report['company_counts']['registered']==2 and report['company_counts']['activity_unknown']==2
        assert report['obligations']['counts']['not_applicable']==1
        assert report['obligations']['verified_fulfilled']==0 and report['obligations']['fulfilled_unverified']==1
        verify(saved['id'],VerifyIn(revision=1,document_id=doc.id),ADMIN,db)
        assert dashboard(db,ADMIN,2026,5)['obligations']['verified_fulfilled']==1
        save_cell(cell(revision=1,status='fulfilled',notes='Modified synthetic record'),ADMIN,db)
        assert dashboard(db,ADMIN,2026,5)['obligations']['verified_fulfilled']==0
        assert dashboard(db,ADMIN,2026,6)['company_counts']['in_period']==0
        assert dashboard(db,ADMIN,2026,5,responsible='Ana')['company_counts']['registered']==1
        reader=Principal('reader','Reader',False,frozenset({'company-a'}))
        scoped=dashboard(db,reader,2026,5)
        assert scoped['company_counts']['registered']==1
        assert all(r['company_id']=='company-a' for r in scoped['obligations']['records'])
        assert scoped['documents']['sources'] is None

def test_classification_idempotence_manual_evidence_and_history(integral):
    service,factory,_=integral
    doc=service.upload(STORAGE_ADMIN,io.BytesIO(XML),'PAGO_ISR_2026-05.xml',company_id='company-a')
    with factory() as db:
        target=save_cell(cell(),ADMIN,db)
        first=analyze(AnalyzeIn(document_ids=[doc.id]),ADMIN,db)['results'][0]
        again=analyze(AnalyzeIn(document_ids=[doc.id]),ADMIN,db)['results'][0]
        assert first['review_id']==again['review_id']
        count=db.scalar(select(func.count()).select_from(DocumentClassificationReview))
        decision(doc.id,DecisionIn(review_id=first['review_id'],revision=doc.revision,action='confirm',company_id='company-a',category_id='category-04',year=2026,period='2026-05',obligation_id=target['id'],reason='Revisión humana sintética'),ADMIN,db)
        assert db.execute(select(records.c.status).where(records.c.id==target['id'])).scalar()=='pending'
        assert db.scalar(select(func.count()).select_from(classified))==1
        analyze(AnalyzeIn(document_ids=[doc.id]),ADMIN,db)
        assert db.scalar(select(func.count()).select_from(DocumentClassificationReview))==count
        organized=explorer('company-a',False,0,ADMIN,db)['documents']
        original=explorer('company-a',True,0,ADMIN,db)['documents']
        assert [r['id'] for r in organized]==[r['id'] for r in original]
        assert organized[0]['relative_paths'] is None
        assert original[0]['relative_paths']

def test_rules_multiple_years_ambiguous_private_and_root():
    rules=[dict(id='r1',category_id='c1',terms=['ISR'],enabled=True),dict(id='r2',category_id='c2',terms=['PAGO'],enabled=True)]
    companies=[dict(id='a',name='Empresa Uno',rfc='AAA010101AA1'),dict(id='b',name='Empresa Dos',rfc='BBB020202BB2')]
    proposal=propose(dict(id='d',name='PAGO_ISR_MAYO.pdf',path='EJERCICIO 2026/2025/AAA010101AA1_BBB020202BB2',period=None),companies,rules)
    assert proposal['year'] is None and proposal['period'] is None
    assert proposal['company_match']=='conflict' and len(proposal['categories'])==2
    assert proposal['requires_review'] and not proposal['automatic_confirmation']
    assert propose(dict(id='k',name='private.key'),companies,rules)['excluded']
    root=propose(dict(id='d',name='ISR_2026-05.xml',path=''),companies,rules)
    assert root['year']==2026 and root['period']=='2026-05'

def test_zero_documents_vs_unavailable_and_missing_sources(integral):
    _,factory,_=integral
    with factory() as db:
        db.add(StorageSource(id='fake-offline',kind='windows_smb',label='Synthetic offline',enabled=True,configuration={},check_state='unavailable'));db.commit()
        report=dashboard(db,ADMIN,2026,5)
        assert report['documents']['indexed']==0
        assert report['documents']['sources'][0]['state']=='unavailable'
        assert not report['documents']['completeness_evaluated']

def test_guard_and_postgresql_ddl(core):
    with core[1]() as db:
        with pytest.raises(HTTPException):ready(db)
    for table in metadata.sorted_tables:assert str(CreateTable(table).compile(dialect=postgresql.dialect()))

def test_public_cer_and_pdf_analyzer_contract():
    from test_connector_dashboard import certificate
    assert analyze_public(certificate(),'cer',[])['public_metadata']['fingerprint']
    assert analyze_public(b'%PDF-1.4','pdf',[])['reason']=='isolated_analyzer_required'

def test_certificate_bands_and_no_metadata_leak(integral):
    from datetime import timedelta
    from app.credential_models import certificates
    from app.integral_models import quality
    _,factory,_=integral
    with factory() as db:
        for days in [70,45,20,5,-2]:
            db.execute(certificates.insert().values(id='synthetic-'+str(days),company_id='company-a',kind='fiel',rfc='AAA010101AA1',origin='cs_storage',reviewed_at=now(),valid_from=now()-timedelta(days=100),valid_until=now()+timedelta(days=days),notes='',revision=1))
        db.execute(quality.insert().values(id='private-cert-issue',company_id='company-a',source='certificate',reference='synthetic-70',code='certificate_dates_mismatch',state='open',created_at=now(),provenance={}));db.commit()
        report=dashboard(db,ADMIN,2026,5)
        assert {c['band'] for c in report['certificates']['records']}=={'over_60','31_60','16_30','0_15','expired'}
        reader=Principal('reader','Reader',False,frozenset({'company-a'}))
        report=dashboard(db,reader,2026,5)
        assert report['certificates']['records']==[]
        assert not any(q['source']=='certificate' for q in report['quality'])

def test_classification_permission_and_original_paths(integral):
    service,factory,_=integral
    doc=service.upload(STORAGE_ADMIN,io.BytesIO(XML),'public.xml',company_id='company-a')
    reader=Principal('reader','Reader',False,frozenset({'company-a'}))
    outsider=Principal('outsider','Outsider',False,frozenset({'company-b'}))
    with factory() as db:
        with pytest.raises(HTTPException):analyze(AnalyzeIn(document_ids=[doc.id]),reader,db)
        assert explorer('company-a',True,0,reader,db)['documents'][0]['relative_paths'] is None
        with pytest.raises(HTTPException):explorer('company-a',False,0,outsider,db)

def test_missing_fiscal_and_vault_are_explicit(core):
    _,factory,_=core
    from app.models import Task
    Task.__table__.create(factory.kw['bind'],checkfirst=True)
    spec=importlib.util.spec_from_file_location('only_integral',Path(__file__).parents[1]/'integral_migrations'/'001_integral.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    with factory.kw['bind'].begin() as conn:mod.upgrade(conn)
    with factory() as db:
        report=dashboard(db,ADMIN,2026,5)
        assert report['obligations']['counts'] is None and not report['obligations']['available']
        assert not report['certificates']['available'] and report['certificates']['without_registered_certificate'] is None
