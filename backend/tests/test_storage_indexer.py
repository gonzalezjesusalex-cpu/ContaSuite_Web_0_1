import io
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from test_storage_core import core, ADMIN, actor, PDF
from test_api import client, A, company
from app.models import (Document, DocumentVersion, DocumentLocation, DocumentCompanyLink,
                        DocumentClassificationReview as Review, StorageIndexJob as Job, StorageEvent, now)
from app.storage.classifier import classify, valid_rfc
from app.storage.indexer import LocalIndexer
from app.storage.providers import ScanIssue, StorageError
from app.storage.router import installation_actor
from app.storage.service import StorageActor

COMPANIES = [{'id': 'company-a', 'rfc': 'AAA010101AA1'}, {'id': 'company-b', 'rfc': 'BBB020202BB2'}]


def xml(issuer='AAA010101AA1', receiver='XAXX010101000', date='2026-10-02T10:00:00'):
    return (f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="{date}">'
            f'<cfdi:Emisor Rfc="{issuer}"/><cfdi:Receptor Rfc="{receiver}"/></cfdi:Comprobante>').encode()


def pdf(text):
    from reportlab.pdfgen.canvas import Canvas
    stream = io.BytesIO()
    canvas = Canvas(stream, invariant=1)
    canvas.drawString(50, 750, text)
    canvas.save()
    return stream.getvalue()


def run(indexer, source, owner='test-worker'):
    job = indexer.enqueue(ADMIN, source)
    assert indexer.claim(owner) == job['id']
    indexer.run(job['id'], owner)
    return next(j for j in indexer.jobs(ADMIN) if j['id'] == job['id'])


def test_classifier_roles_ambiguity_names_and_limits():
    result = classify(io.BytesIO(xml()), 'BBB020202BB2.xml', COMPANIES)
    assert result['automatic'] and result['links'] == [{'company_id':'company-a','role':'issuer'}]
    assert result['period'] == '2026-10' and result['type'] == 'cfdi'
    both = classify(io.BytesIO(xml(receiver='BBB020202BB2')), 'a.xml', COMPANIES)
    assert not both['automatic'] and len(both['links']) == 2
    assert both['evidence']['reason'] == 'multiple_companies'
    unknown = classify(io.BytesIO(b'<x RFC="AAA010101AA1"/>'), 'a.xml', COMPANIES)
    assert not unknown['automatic']  # A non-CFDI XML attribute is only a suggestion.
    missing = xml().replace(b'<cfdi:Receptor Rfc="XAXX010101000"/>', b'')
    assert not classify(io.BytesIO(missing), 'a.xml', COMPANIES)['automatic']
    assert not valid_rfc('AAA991332AA1') and not valid_rfc('XAXX010101000')


def test_pdf_text_without_ocr():
    one = classify(io.BytesIO(pdf('RFC AAA010101AA1')), 'a.pdf', COMPANIES)
    assert one['automatic'] and one['links'][0]['role'] == 'owner'
    both = classify(io.BytesIO(pdf('AAA010101AA1 / BBB020202BB2')), 'a.pdf', COMPANIES)
    assert not both['automatic'] and len(both['links']) == 2
    assert not classify(io.BytesIO(pdf('Sin datos fiscales')), 'AAA010101AA1.pdf', COMPANIES)['automatic']


def test_initial_incremental_duplicates_modified_missing_and_readonly(core):
    service, sessions, root = core
    (root/'deep').mkdir()
    (root/'one.xml').write_bytes(xml())
    (root/'deep'/'copy.xml').write_bytes(xml())
    (root/'two.pdf').write_bytes(pdf('AAA010101AA1 y BBB020202BB2'))
    (root/'blank.pdf').write_bytes(pdf('Sin RFC'))
    (root/'private.key').write_bytes(b'no processing')
    original = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    first = run(indexer, source)
    assert first['status'] == 'completed', first
    assert first['counters']['new'] == 4 and first['counters']['duplicates'] >= 1
    assert all(p.read_bytes() == b for p,b in original.items())
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 4
        assert db.scalar(select(func.count()).select_from(DocumentCompanyLink)) == 2
        one = db.scalar(select(Document).where(Document.name == 'one.xml'))
        ident = one.id
    assert len(service.duplicates(ADMIN, ident)) == 1
    with pytest.raises(StorageError):
        service.duplicates(actor('company-b', 'read'), ident)
    second = run(indexer, source)
    assert second['counters']['unchanged'] == 4
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 4
    (root/'one.xml').write_bytes(xml(issuer='BBB020202BB2'))
    (root/'blank.pdf').unlink()  # Only a disposable pytest directory.
    third = run(indexer, source)
    assert third['counters']['modified'] == 1 and third['counters']['missing'] == 1
    assert service.document(ADMIN, ident).revision == 2
    assert service.document(ADMIN, ident).company_ids == ['company-b']
    with pytest.raises(StorageError):
        service.document(actor('company-a', 'read'), ident)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 5
        assert db.scalar(select(DocumentLocation).where(DocumentLocation.availability == 'missing'))


def test_checkpoint_restart_expired_lease_and_single_worker(core):
    service, sessions, root = core
    for i in range(3):
        (root/f'{i}.xml').write_bytes(xml())
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    job = indexer.enqueue(ADMIN, source)
    assert indexer.enqueue(ADMIN, source)['id'] == job['id']
    assert indexer.claim('worker-a') == job['id']
    assert indexer.claim('worker-b') is None
    indexer.run(job['id'], 'worker-a', stop_after=1)
    assert indexer.jobs(ADMIN)[0]['counters']['new'] == 1
    assert indexer.claim('worker-a') == job['id']
    with sessions.begin() as db:
        db.get(Job, job['id']).lease_until = now() - timedelta(seconds=1)
    assert indexer.claim('worker-b') == job['id']
    with pytest.raises(StorageError, match='lease_lost'):
        indexer.run(job['id'], 'worker-a')
    restarted = LocalIndexer(service)
    restarted.run(job['id'], 'worker-b')
    assert restarted.jobs(ADMIN)[0]['counters']['new'] == 3
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 3


def test_access_error_continues_and_never_infers_missing(core, monkeypatch):
    service, sessions, root = core
    (root/'known.xml').write_bytes(xml())
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    run(indexer, source)
    (root/'known.xml').unlink()
    (root/'new.xml').write_bytes(xml())
    provider = service._provider
    def with_error(source):
        p = provider(source)
        enumerate_files = p.enumerate
        def scan():
            yield ScanIssue('denied', 'access_denied')
            yield from enumerate_files()
        p.enumerate = scan
        return p
    monkeypatch.setattr(service, '_provider', with_error)
    result = run(indexer, source)
    assert result['status'] == 'completed_with_errors' and result['counters']['new'] == 1
    assert result['error_code'] == 'access_denied' and not result['counters'].get('missing')
    with sessions() as db:
        assert db.scalar(select(StorageEvent).where(StorageEvent.code == 'access_denied'))
        assert not db.scalar(select(DocumentLocation).where(DocumentLocation.availability == 'missing'))


def test_review_confirm_correct_reject_stale_and_actor(core):
    service, sessions, root = core
    (root/'ambiguous.xml').write_bytes(xml(receiver='BBB020202BB2'))
    source = service.register_local(ADMIN, 'Demo', root).id
    run(LocalIndexer(service), source)
    doc = service.list_documents(ADMIN).items[0]
    review = service.reviews(ADMIN, doc.id)[0]
    assert review['status'] == 'pending' and len(review['proposed_links']) == 2
    with pytest.raises(StorageError):
        service.resolve_review(actor('company-a', 'review'), doc.id, review['id'], 1, 'confirm', [])
    service.resolve_review(ADMIN, doc.id, review['id'], 1, 'correct', [{'company_id':'company-a','role':'receiver'}])
    assert service.document(ADMIN, doc.id).company_ids == ['company-a']
    assert service.reviews(ADMIN, doc.id)[0]['resolved_by'] == ADMIN.subject
    with pytest.raises(StorageError, match='revision_conflict'):
        service.resolve_review(ADMIN, doc.id, review['id'], 1, 'reject', [])
    run(LocalIndexer(service), source)  # A resumed/incremental pass cannot undo a human decision.
    assert service.reviews(ADMIN, doc.id)[0]['resolution'] == 'correct'
    (root/'ambiguous.xml').write_bytes(xml(receiver='BBB020202BB2', date='2026-11-01T10:00:00'))
    run(LocalIndexer(service), source)
    with pytest.raises(StorageError):
        service.document(actor('company-a', 'read'), doc.id)
    current = next(r for r in service.reviews(ADMIN, doc.id) if r['current'])
    assert current['evidence']['reason'] == 'existing_assignment'
    service.resolve_review(ADMIN, doc.id, current['id'], 2, 'reject', [])
    assert service.document(ADMIN, doc.id).company_ids == ['company-a']


def test_index_and_review_auth_input_and_content_endpoint(client):
    assert client.get('/api/storage/index-jobs').status_code == 401
    assert client.post('/api/storage/index-jobs', headers=A, json={'source_id':'cs_internal'}).status_code == 409
    assert client.post('/api/storage/index-jobs', headers=A, json={'source_id':'x','root_path':'C:/secret'}).status_code == 422
    c = company(client).json()
    result = client.post('/api/storage/documents', headers=A, files={'file':('f.xml',xml(issuer=c['rfc']),'application/xml')})
    ident = result.json()['id']
    analysis = client.post(f'/api/storage/documents/{ident}/classify', headers=A)
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()[0]['resolution'] == 'automatic'
    assert client.get(f'/api/storage/documents/{ident}/reviews').status_code == 401
    assert client.get(f'/api/storage/documents/{ident}/duplicates', headers=A).json() == []


def test_rejection_unassigned_and_confirmation(core):
    service, sessions, root = core
    for name in ['confirm.xml', 'reject.xml']:
        (root/name).write_bytes(xml(receiver='BBB020202BB2'))
    source = service.register_local(ADMIN, 'Demo', root).id
    run(LocalIndexer(service), source)
    docs = service.list_documents(ADMIN).items
    for doc in docs:
        review = service.reviews(ADMIN, doc.id)[0]
        action = 'confirm' if doc.name == 'confirm.xml' else 'reject'
        service.resolve_review(ADMIN, doc.id, review['id'], 1, action, [])
        assert service.document(ADMIN, doc.id).classification_status == ('confirmed' if action == 'confirm' else 'rejected')
    assert service.list_documents(ADMIN, pending=True).total == 0


def test_resource_failure_goes_to_review(core, monkeypatch):
    import subprocess
    service, sessions, root = core
    (root/'one.xml').write_bytes(xml())
    source = service.register_local(ADMIN, 'Demo', root).id
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('parser', 25)
    monkeypatch.setattr(subprocess, 'run', timeout)
    run(LocalIndexer(service), source)
    doc = service.list_documents(ADMIN).items[0]
    assert service.reviews(ADMIN, doc.id)[0]['evidence']['reason'] == 'extraction_limit'
    assert doc.classification_status == 'pending'


def test_scan_limit_preserves_locations_and_exclusions(core, monkeypatch):
    service, sessions, root = core
    (root/'known.xml').write_bytes(xml())
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    run(indexer, source)
    (root/'known.xml').unlink()
    from app.models import StorageSource
    with sessions.begin() as db:
        db.get(StorageSource, source).configuration = {'exclusions':['known.xml']}
    result = run(indexer, source)
    assert not result['counters'].get('missing')
    with sessions.begin() as db:
        db.get(StorageSource, source).configuration = {'exclusions':[]}
    provider_factory = service._provider
    def limited(source):
        provider = provider_factory(source)
        provider.enumerate = lambda: iter([ScanIssue('', 'scan_limit')])
        return provider
    monkeypatch.setattr(service, '_provider', limited)
    limited_job = run(indexer, source)
    assert limited_job['status'] == 'completed_with_errors' and limited_job['error_code'] == 'scan_limit'
    with sessions() as db:
        assert db.scalar(select(DocumentLocation)).availability == 'available'


def test_hash_detects_same_metadata_change_and_worker_cli(core):
    import os
    import json
    import subprocess
    import sys
    from pathlib import Path
    service, sessions, root = core
    file = root/'same.xml'
    file.write_bytes(xml())
    initial = file.stat()
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    run(indexer, source)
    file.write_bytes(xml(issuer='BBB020202BB2'))
    os.utime(file, ns=(initial.st_atime_ns, initial.st_mtime_ns))
    job = indexer.enqueue(ADMIN, source)
    env = dict(os.environ, DATABASE_URL=str(sessions.kw['bind'].url),
        DATA_DIR=str(service.settings.internal_root.parent/'cli-data'),
        CS_STORAGE_ALLOWED_ROOTS=json.dumps([str(root)]))
    proc = subprocess.run([sys.executable, '-m', 'app.storage.worker', '--once'],
        env=env, capture_output=True, timeout=45, cwd=Path(__file__).resolve().parents[1])
    assert proc.returncode == 0, proc.stderr.decode(errors='replace')
    result = next(j for j in indexer.jobs(ADMIN) if j['id'] == job['id'])
    assert result['status'] == 'completed' and result['counters']['modified'] == 1
    assert service.list_documents(ADMIN).items[0].company_ids == ['company-b']


def test_duplicate_results_are_scoped_to_current_versions(core):
    service, sessions, root = core
    payload = xml(receiver='BBB020202BB2')
    first = service.upload(ADMIN, io.BytesIO(payload), 'a.xml', company_id='company-a')
    second = service.upload(ADMIN, io.BytesIO(payload), 'b.xml', company_id='company-b')
    assert len(service.duplicates(ADMIN, first.id)) == 1
    assert service.duplicates(actor('company-a','read'), first.id) == []
    service.upload(ADMIN, io.BytesIO(xml()), 'b.xml', document_id=second.id, expected_revision=1)
    assert service.duplicates(ADMIN, first.id) == []


def test_catalog_change_reclassifies_unchanged_content(core):
    from app.models import Company
    service, sessions, root = core
    with sessions.begin() as db:
        db.delete(db.get(Company, 'company-b'))
    (root/'known.xml').write_bytes(xml(receiver='BBB020202BB2'))
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    run(indexer, source)
    doc = service.list_documents(ADMIN).items[0]
    assert doc.company_ids == ['company-a'] and doc.classification_status == 'confirmed'
    with sessions.begin() as db:
        db.add(Company(id='company-b', name='Empresa B', rfc='BBB020202BB2'))
    result = run(indexer, source)
    assert result['counters']['unchanged'] == 1
    doc = service.document(ADMIN, doc.id)
    assert not doc.company_ids and doc.classification_status == 'pending'
    review = service.reviews(ADMIN, doc.id)[0]
    assert review['evidence']['reason'] == 'multiple_companies'
    assert len(review['proposed_links']) == 2


def test_access_failure_updates_existing_location(core, monkeypatch):
    service, sessions, root = core
    (root/'known.xml').write_bytes(xml())
    source = service.register_local(ADMIN, 'Demo', root).id
    indexer = LocalIndexer(service)
    run(indexer, source)
    def denied(*args, **kwargs):
        raise StorageError('access_denied')
    monkeypatch.setattr(service, '_buffer', denied)
    result = run(indexer, source)
    assert result['status'] == 'completed_with_errors'
    with sessions() as db:
        location = db.scalar(select(DocumentLocation))
        assert location.availability == 'denied' and location.error_code == 'access_denied'
