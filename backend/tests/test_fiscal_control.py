import importlib.util
from pathlib import Path
from datetime import date
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from test_storage_core import core
from app.fiscal_control import (metadata,catalog,records,history,CellIn,matrix,save_cell,effective,ready,period_key)
from app.security import Principal
from app.fiscal_import import preview,classify,sheet_period

ADMIN=Principal('test-admin','Administrador',True)
@pytest.fixture
def fiscal(core):
    service,sessions,root=core
    spec=importlib.util.spec_from_file_location('fiscal_migration',Path(__file__).parents[1]/'fiscal_migrations'/'001_control_obligaciones.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with sessions.kw['bind'].begin() as connection:module.upgrade(connection)
    return sessions

def payload(**kw):
    return CellIn(**(dict(company_id='company-a',obligation_id='fiscal-02',year=2026,month=11,revision=0,status='pending')|kw))

def test_migration_guard_and_no_implicit_seed(core):
    with core[1]() as db:
        with pytest.raises(HTTPException) as e:ready(db)
        assert e.value.status_code==503

def test_roundtrip_audit_conflict_and_permissions(fiscal):
    with fiscal() as db:
        saved=save_cell(payload(due_date=date(2020,1,1),due_verified=True),ADMIN,db)
        data=matrix(2026,11,ADMIN,db)
        assert len(data['catalog'])==11 and len(data['companies'])==2
        assert data['records'][0]['effective_status']=='overdue'
        assert db.scalar(select(func.count()).select_from(records))==1
        save_cell(payload(revision=1,status='fulfilled'),ADMIN,db)
        audit=list(db.execute(select(history)).mappings())
        assert len(audit)==2 and audit[1]['before']['status']=='pending' and audit[1]['after']['status']=='fulfilled'
        with pytest.raises(HTTPException) as conflict:save_cell(payload(),ADMIN,db)
        assert conflict.value.status_code==409
        reader=Principal('reader','Reader',False,frozenset({'company-a'}))
        assert len(matrix(2026,11,reader,db)['companies'])==1
        with pytest.raises(HTTPException):save_cell(payload(revision=2),reader,db)
        writer=Principal('writer','Writer',False,frozenset({'company-b'}),frozenset({'company-b'}))
        with pytest.raises(HTTPException):save_cell(payload(revision=2),writer,db)

def test_due_dates_empty_and_periodicity(fiscal):
    assert effective(None)=='unreviewed'
    row=dict(status='pending',due_verified=False,due_date=date(2020,1,1))
    assert effective(row)=='pending'
    assert effective(row|dict(status='not_applicable',due_verified=True))=='not_applicable'
    assert period_key(2026,2,'quarterly')==period_key(2026,3,'quarterly')
    assert period_key(2026,1,'annual')==period_key(2026,12,'annual')
    with fiscal() as db:
        db.execute(catalog.update().where(catalog.c.id=='fiscal-02').values(periodicity='annual'));db.commit()
        save_cell(payload(month=1),ADMIN,db)
        with pytest.raises(HTTPException) as conflict:save_cell(payload(month=12),ADMIN,db)
        assert conflict.value.status_code==409

def test_postgresql_ddl_and_import_preview():
    for table in metadata.sorted_tables:assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert sheet_period('Noviembre 2026')=='2026-11'
    assert sheet_period('Noviembre') is None
    assert classify(date(2026,11,1))['authority_validated'] is False
    assert classify(None)['status']=='unreviewed'
    data=preview([dict(name='2026-11',rows=[dict(number=n,rfc='AAA010101AA1',cells={'ISR':None,'Pago':'NA'}) for n in (2,3)])],[dict(id='company-a',rfc='AAA010101AA1',name='A')],[dict(id='isr',label='ISR')])
    assert 'duplicate_cell' in data[1]['cells'][0]['conflicts']
    assert 'payment_obligation_required' in data[0]['cells'][1]['conflicts']

def test_evidence_company_scope_and_applicability(fiscal,core,monkeypatch):
    import io
    from test_storage_core import ADMIN as STORAGE_ADMIN, XML
    from app.storage import router as storage_router
    from app.fiscal_control import ApplicabilityIn,save_applicability
    service=core[0]
    monkeypatch.setattr(storage_router,'storage_service',lambda:service)
    doc=service.upload(STORAGE_ADMIN,io.BytesIO(XML),'evidence.xml',company_id='company-a')
    with fiscal() as db:
        save_cell(payload(evidence=[{'document_id':doc.id,'role':'receipt'}]),ADMIN,db)
        assert matrix(2026,11,ADMIN,db)['records'][0]['evidence'][0]['document_id']==doc.id
        with pytest.raises(HTTPException) as denied:save_cell(payload(company_id='company-b',evidence=[{'document_id':doc.id}]),ADMIN,db)
        assert denied.value.status_code==422
        result=save_applicability(ApplicabilityIn(company_id='company-a',obligation_id='fiscal-03',applicable=False,revision=0),ADMIN,db)
        assert result['revision']==1
        assert matrix(2026,11,ADMIN,db)['applicability'][0]['applicable'] is False
