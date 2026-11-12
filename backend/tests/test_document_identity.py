import io
import pytest
from sqlalchemy import select,func
from test_storage_core import core,ADMIN,actor
from test_integral import integral,ADMIN as FISCAL_ADMIN,cell
from app.models import Document,DocumentVersion,DocumentClassificationReview as Review,DocumentCompanyLink
from app.storage.classifier import classify
from app.storage.providers import StorageError
from app.document_identity import identities,blocked
UUID='12345678-1234-1234-1234-123456789ABC'
def xml(total='100',uuid=UUID):
    return (f'<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" Fecha="2026-11-11T12:00:00" Total="{total}"><c:Emisor Rfc="AAA010101AA1"/><c:Receptor Rfc="CCC010101CC1"/><c:Complemento><t:TimbreFiscalDigital UUID="{uuid}"/></c:Complemento></c:Comprobante>').encode()
def analyze(service,doc,raw):
    result=classify(io.BytesIO(raw),'same.xml',[{'id':'company-a','rfc':'AAA010101AA1'},{'id':'company-b','rfc':'BBB020202BB2'}])
    service.apply_classification(ADMIN,doc.id,doc.revision,result)
def upload(service,total='100',uuid=UUID,company=None):
    raw=xml(total,uuid);doc=service.upload(ADMIN,io.BytesIO(raw),'same.xml',company_id=company);analyze(service,doc,raw);return doc
def pending(factory,doc):
    with factory() as db:return db.scalar(select(Review).where(Review.document_id==doc.id,Review.status=='pending')).id
def test_uuid_conflict_quarantines_both_without_merge_or_cross_company_assignment(core):
    service,factory,_=core;a=upload(service);b=upload(service,'101')
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Document))==2
        assert all(blocked(db,v.id) for v in db.scalars(select(DocumentVersion)))
        assert db.scalar(select(func.count()).select_from(Review).where(Review.status=='pending'))==2
    rid=pending(factory,b)
    with pytest.raises(StorageError):service.resolve_review(ADMIN,b.id,rid,1,'correct',[{'company_id':'company-b','role':'owner'}])
    service.resolve_review(ADMIN,b.id,rid,1,'correct',[{'company_id':'company-b','role':'owner'}],reason='Reviewed contradictory UUID; independent company correction')
    with factory() as db:
        assert set(db.scalars(select(DocumentCompanyLink.company_id).where(DocumentCompanyLink.document_id==b.id)))=={'company-b'}
        assert db.get(Review,rid).evidence['human_decision']['reason']
        assert db.scalar(select(func.count()).select_from(Document))==2
    with pytest.raises(StorageError):service.resolve_review(actor('company-a'),a.id,pending(factory,a),1,'confirm',[],reason='unauthorized')
def test_upload_detects_conflicting_uuid_before_explicit_classification(core):
    service,factory,_=core
    a=service.upload(ADMIN,io.BytesIO(xml()),'a.xml',company_id='company-a')
    b=service.upload(ADMIN,io.BytesIO(xml('999')),'b.xml',company_id='company-b')
    with factory() as db:
        assert all(blocked(db,v.id) for v in db.scalars(select(DocumentVersion)))
        from app.models import StorageEvent
        before=db.scalar(select(func.count()).select_from(StorageEvent).where(StorageEvent.action=='identity_conflict_detected'))
    analyze(service,b,xml('999'))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(StorageEvent).where(StorageEvent.action=='identity_conflict_detected'))==before
def test_identical_bytes_uuid_remain_independent_and_idempotent(core):
    service,factory,_=core;a=upload(service);b=upload(service);analyze(service,b,xml())
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Document))==2
        assert db.scalar(select(func.count()).select_from(identities))==2
        assert not any(blocked(db,v.id) for v in db.scalars(select(DocumentVersion)))
    assert service.duplicates(ADMIN,a.id)[0]['id']==b.id
def test_conflict_reanalysis_does_not_reopen_identical_acknowledged_condition(core):
    service,factory,_=core;a=upload(service);b=upload(service,'101')
    old_pending=pending(factory,a)
    with factory() as db:old_condition=db.get(Review,old_pending).evidence['identity']['condition_hash']
    rid=pending(factory,b);service.resolve_review(ADMIN,b.id,rid,1,'correct',[{'company_id':'company-b','role':'owner'}],reason='human review')
    analyze(service,b,xml('101'))
    with factory() as db:assert not blocked(db,db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id==b.id)))
    upload(service,'102')
    with factory() as db:
        assert blocked(db,db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id==b.id)))
        assert db.get(Review,old_pending).status=='superseded'
        assert db.get(Review,old_pending).evidence['identity']['condition_hash']==old_condition
        assert pending(factory,a)!=old_pending
def test_multiple_or_malformed_uuid_requires_review(core):
    service,factory,_=core;doc=upload(service,uuid='invalid')
    with factory() as db:
        assert blocked(db,db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id==doc.id)))
        assert db.get(Document,doc.id).classification_status=='pending'
def test_changed_uuid_preserves_versions_and_requires_identity_review(core):
    service,factory,root=core;path=root/'original.xml';path.write_bytes(xml())
    source=service.register_local(ADMIN,'Synthetic original',root).id
    first=service.observe_external(ADMIN,source,'original.xml');analyze(service,first,xml())
    changed=xml(uuid='87654321-4321-4321-4321-CBA987654321');path.write_bytes(changed)
    second=service.observe_external(ADMIN,source,'original.xml');analyze(service,second,changed)
    assert second.id==first.id and second.revision==2 and path.read_bytes()==changed
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id==first.id))==2
        v=db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id==first.id,DocumentVersion.number==2))
        assert blocked(db,v)
        assert db.scalar(select(Review).where(Review.version_id==v,Review.status=='pending')).evidence['reason']=='document_identity_changed'
def test_multiple_timbres_is_contradictory_without_uuid_guess():
    raw=xml().replace(b'</c:Complemento>',b'<t:TimbreFiscalDigital UUID="87654321-4321-4321-4321-CBA987654321"/></c:Complemento>')
    result=classify(io.BytesIO(raw),'x.xml',[])
    assert result['evidence']['cfdi_uuid'] is None and result['evidence']['uuid_status']=='contradictory' and not result['automatic']
def test_explicit_reopen_preserves_rejection_and_is_idempotent(core):
    service,factory,_=core;a=upload(service);upload(service,'101');rid=pending(factory,a)
    service.resolve_review(ADMIN,a.id,rid,1,'reject',[],reason='Synthetic rejection')
    with pytest.raises(StorageError):service.reopen_review(actor('company-a'),a.id,rid,1,'not authorized')
    first=service.reopen_review(ADMIN,a.id,rid,1,'Correct a human rejection')
    again=service.reopen_review(ADMIN,a.id,rid,1,'Repeat same reopening')
    assert first['review_id']==again['review_id'] and again['idempotent']
    with factory() as db:
        assert db.get(Review,rid).resolution=='reject' and db.get(Review,rid).status=='resolved'
        assert db.get(Review,first['review_id']).evidence['reopened_from']==rid
    service.resolve_review(ADMIN,a.id,first['review_id'],1,'correct',[{'company_id':'company-a','role':'owner'}],reason='Identity reviewed after reopening')
def test_conflict_suspends_verification_history_and_requires_new_fiscal_review(integral):
    from app.fiscal_control import save_cell
    from app.integral_api import verify,VerifyIn
    from app.fiscal_read import read_period
    from app.evidence_history import decisions
    from fastapi import HTTPException
    service,factory,_=integral;a=upload(service,company='company-a')
    with factory() as db:
        saved=save_cell(cell(year=2026,month=11,status='fulfilled'),FISCAL_ADMIN,db)
        verify(saved['id'],VerifyIn(revision=1,document_id=a.id),FISCAL_ADMIN,db)
    upload(service,'101')
    with factory() as db:
        assert read_period(db,FISCAL_ADMIN,2026,11)['summary']['verified_fulfilled']==0
        assert db.scalar(select(func.count()).select_from(decisions))==1
        with pytest.raises(HTTPException):verify(saved['id'],VerifyIn(revision=1,document_id=a.id),FISCAL_ADMIN,db)
    service.resolve_review(ADMIN,a.id,pending(factory,a),1,'confirm',[],reason='Identity reviewed; fiscal review separate')
    with factory() as db:
        assert read_period(db,FISCAL_ADMIN,2026,11)['summary']['verified_fulfilled']==0
        assert not verify(saved['id'],VerifyIn(revision=1,document_id=a.id),FISCAL_ADMIN,db)['idempotent']
        assert db.scalar(select(func.count()).select_from(decisions))==2
def test_virtual_classification_cannot_replace_or_resolve_identity_review(integral):
    from app.integral_api import analyze,AnalyzeIn,decision,DecisionIn
    from fastapi import HTTPException
    service,factory,_=integral;a=upload(service,company='company-a')
    with factory() as db:
        v=db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id==a.id))
        legacy=Review(document_id=a.id,version_id=v,evidence={'origin':'metadata_rules_v3','original_proposal':'preserve'},proposed_links=[])
        db.add(legacy);db.commit();legacy_id=legacy.id
    upload(service,'101')
    rid=pending(factory,a)
    with factory() as db:
        before=db.scalar(select(func.count()).select_from(Review))
        assert db.scalar(select(func.count()).select_from(Review).where(Review.document_id==a.id,Review.status=='pending'))==1
        assert db.get(Review,legacy_id).evidence.get('original_proposal')=='preserve'
        result=analyze(AnalyzeIn(document_ids=[a.id]),FISCAL_ADMIN,db)['results'][0]
        assert result['review_id']==rid and result['reason']=='identity_review_required'
        assert db.scalar(select(func.count()).select_from(Review))==before
        with pytest.raises(HTTPException) as error:
            decision(a.id,DecisionIn(review_id=rid,revision=1,action='confirm',company_id='company-a',category_id='unknown',reason='Cannot bypass identity review'),FISCAL_ADMIN,db)
        assert error.value.status_code==409 and db.get(Review,rid).status=='pending'
