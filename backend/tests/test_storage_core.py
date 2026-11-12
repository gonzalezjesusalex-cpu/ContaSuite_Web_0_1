import hashlib
import io
import os
import stat
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker
from test_api import client, A, company  # Initialize the existing isolated test environment before app imports.
from app.models import (Company, Document, DocumentVersion, DocumentLocation, DocumentClassificationReview,
                        StorageEvent, StorageSource, now)
from app.storage.migrate import upgrade_storage
from app.storage.providers import FileMetadata, ScanIssue, StorageError
from app.storage.paths import safe_key
from app.storage.local import LocalFolderProvider
from app.storage.internal import InternalStorageProvider
from app.storage.service import StorageService, StorageActor
from app.storage.settings import StorageSettings
from app.storage.smb import WindowsSMBProvider

PDF = b'%PDF-1.4\nsynthetic test document\n%%EOF'
XML = b'<?xml version="1.0"?><Comprobante Fecha="2026-10-01"/>'
ADMIN = StorageActor('test-administrator', admin=True)


@pytest.fixture
def core(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'storage.db'))
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    upgrade_storage(engine)
    # Full application baseline is provisioned explicitly by installation, not startup.
    from app.database import Base
    Base.metadata.create_all(engine)
    from app.document_identity import metadata as identity_metadata
    identity_metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as db:
        db.add_all([Company(id='company-a', name='Empresa A', rfc='AAA010101AA1'),
                    Company(id='company-b', name='Empresa B', rfc='BBB020202BB2')])
    external = tmp_path / 'authorized'
    external.mkdir()
    settings = StorageSettings(tmp_path / 'private', tmp_path / 'legacy', (external,))
    service = StorageService(sessions, settings)
    yield service, sessions, external
    engine.dispose()


def actor(company_id, *permissions):
    return StorageActor('user-' + company_id, frozenset({company_id}), frozenset(permissions))


def test_shared_document_requires_write_for_every_linked_company(core):
    from app.models import DocumentCompanyLink
    service, sessions, root = core
    doc = service.upload(ADMIN, io.BytesIO(XML), 'shared.xml', company_id='company-a')
    with sessions.begin() as db:
        db.add(DocumentCompanyLink(document_id=doc.id, company_id='company-b', role='receiver',
                                   method='manual', confirmed_by=ADMIN.subject))
    limited = StorageActor('mixed-permissions', frozenset({'company-a','company-b'}),
                           frozenset({'read','write'}), write_company_ids=frozenset({'company-a'}))
    assert service.document(limited, doc.id).id == doc.id
    with pytest.raises(StorageError, match='forbidden'):
        service.upload(limited, io.BytesIO(XML), 'new.xml', document_id=doc.id, expected_revision=1)
    assert service.document(ADMIN, doc.id).revision == 1


def test_local_enumeration_exclusions_keys_and_originals(tmp_path):
    root = tmp_path / 'source'
    (root / 'deep').mkdir(parents=True)
    (root / 'skip').mkdir()
    (root / 'a.pdf').write_bytes(PDF)
    (root / 'deep' / 'b.xml').write_bytes(XML)
    (root / 'skip' / 'secret.pdf').write_bytes(PDF)
    (root / 'private.key').write_bytes(b'private key')
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    provider = LocalFolderProvider(root, (root,), exclusions=('skip',))
    assert provider.availability().state == 'available'
    assert {e.key for e in provider.enumerate() if isinstance(e, FileMetadata)} == {'a.pdf', 'deep/b.xml'}
    with provider.open_read('deep/b.xml') as stream:
        assert stream.read() == XML
    with pytest.raises(StorageError, match='excluded_path'):
        with provider.open_read('skip/secret.pdf'):
            pass
    with pytest.raises(StorageError, match='unsupported_format'):
        with provider.open_read('private.key'):
            pass
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    for key in ('../a.pdf', '/a.pdf', 'C:/a.pdf', 'a\\b.pdf', 'a//b.pdf', 'a/CON.pdf', 'a./x.pdf', 'a.pdf:secret'):
        with pytest.raises(StorageError, match='invalid_path'):
            safe_key(key)
    with pytest.raises(StorageError, match='unauthorized_root'):
        LocalFolderProvider(tmp_path, (root,))


def test_local_scan_continues_after_denied_directory_and_limits(tmp_path, monkeypatch):
    (tmp_path / 'denied').mkdir()
    (tmp_path / 'ok.pdf').write_bytes(PDF)
    original = os.scandir
    def scandir(path):
        if Path(path).name == 'denied':
            raise PermissionError('Sensitive physical path must not be returned')
        return original(path)
    monkeypatch.setattr(os, 'scandir', scandir)
    entries = list(LocalFolderProvider(tmp_path, (tmp_path,)).enumerate())
    assert any(isinstance(e, ScanIssue) and e.code == 'access_denied' for e in entries)
    assert any(isinstance(e, FileMetadata) and e.key == 'ok.pdf' for e in entries)
    assert any(isinstance(e, ScanIssue) and e.code == 'scan_limit' for e in LocalFolderProvider(tmp_path, (tmp_path,), max_entries=0).enumerate())


def test_reparse_points_are_not_followed(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.pdf').write_bytes(PDF)
    link = root / 'junction'
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    provider = LocalFolderProvider(root, (root,))
    assert list(provider.enumerate()) == [ScanIssue('junction', 'linked_path')]
    with pytest.raises(StorageError, match='linked_path'):
        with provider.open_read('junction/secret.pdf'):
            pass
    with pytest.raises(StorageError, match='linked_path'):
        LocalFolderProvider(link, (tmp_path,))
    assert (outside / 'secret.pdf').read_bytes() == PDF


def test_changed_or_oversized_local_file_is_rejected(tmp_path):
    path = tmp_path / 'x.pdf'
    path.write_bytes(PDF)
    provider = LocalFolderProvider(tmp_path, (tmp_path,))
    with pytest.raises(StorageError, match='file_changed'):
        with provider.open_read('x.pdf') as stream:
            stream.read()
            path.write_bytes(PDF + b'change')
    with pytest.raises(StorageError, match='file_too_large'):
        with LocalFolderProvider(tmp_path, (tmp_path,), max_file_bytes=1).open_read('x.pdf'):
            pass


def test_internal_private_atomic_storage_and_validation(tmp_path):
    repo = InternalStorageProvider(tmp_path / 'private')
    stored = repo.put(io.BytesIO(XML), 'factura.XML')
    assert stored.sha256 == hashlib.sha256(XML).hexdigest()
    with repo.open_read(stored.key) as stream:
        assert stream.read() == XML
    assert not list((tmp_path / 'private' / '.staging').iterdir())
    for name, payload, code in [('a.key', b'secret', 'unsupported_format'), ('a.pfx', b'secret', 'unsupported_format'),
                                ('a.pdf', b'not pdf', 'invalid_format'), ('a.pdf', b'%PDF- PRIVATE KEY', 'protected_file'),
                                ('a.xml', b'<!DOCTYPE x [<!ENTITY e "secret">]><x>&e;</x>', 'invalid_format'),
                                ('a.pdf', b'', 'empty_file')]:
        with pytest.raises(StorageError, match=code):
            repo.put(io.BytesIO(payload), name)
    assert [e.key for e in repo.enumerate() if isinstance(e, FileMetadata)] == [stored.key]
    with pytest.raises(StorageError, match='invalid_path'):
        repo.discard('../outside.pdf')
    assert not list((tmp_path / 'private' / '.staging').iterdir())


def test_internal_publish_failure_and_size_limit_leave_no_partial_files(tmp_path, monkeypatch):
    repo = InternalStorageProvider(tmp_path / 'private', max_file_bytes=2)
    with pytest.raises(StorageError, match='file_too_large'):
        repo.put(io.BytesIO(PDF), 'x.pdf')
    repo = InternalStorageProvider(tmp_path / 'private')
    monkeypatch.setattr(os, 'link', lambda *a, **kw: (_ for _ in ()).throw(OSError('private physical path')))
    with pytest.raises(StorageError, match='write_error'):
        repo.put(io.BytesIO(PDF), 'x.pdf')
    assert not list((repo.root / '.staging').iterdir())
    assert not list((repo.root / 'objects').iterdir())


def test_internal_name_collision_never_overwrites_or_removes_another_staging_file(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.storage import internal
    repo = InternalStorageProvider(tmp_path / 'private')
    token = 'a' * 32
    monkeypatch.setattr(internal, 'uuid4', lambda: SimpleNamespace(hex=token))
    stored = repo.put(io.BytesIO(PDF), 'a.pdf')
    with pytest.raises(StorageError, match='write_error'):
        repo.put(io.BytesIO(PDF + b'other'), 'b.pdf')
    assert (repo.root / stored.key).read_bytes() == PDF
    other_staging = repo.root / '.staging' / token
    other_staging.write_bytes(b'another active upload')
    with pytest.raises(StorageError, match='write_error'):
        repo.put(io.BytesIO(PDF), 'c.pdf')
    assert other_staging.read_bytes() == b'another active upload'


def test_service_versions_scopes_and_no_path_disclosure(core):
    service, sessions, _ = core
    user_a = actor('company-a', 'read', 'write')
    first = service.upload(user_a, io.BytesIO(PDF), 'a.pdf', company_id='company-a')
    assert first.revision == 1 and first.company_ids == ['company-a']
    public = first.model_dump()
    assert not {'root_path', 'relative_key', 'storage_name', 'configuration'} & set(public)
    second = service.upload(user_a, io.BytesIO(XML), 'a.xml', document_id=first.id, expected_revision=1)
    assert second.id == first.id and second.revision == 2
    for revision, content in ((1, PDF), (2, XML)):
        with service.read(user_a, first.id, revision=revision) as verified:
            assert verified.stream.read() == content
    with pytest.raises(StorageError, match='not_found'):
        service.document(actor('company-b', 'read'), first.id)
    with pytest.raises(StorageError, match='forbidden'):
        service.upload(actor('company-b', 'write'), io.BytesIO(PDF), 'b.pdf', company_id='company-a')
    with pytest.raises(StorageError, match='revision_conflict'):
        service.upload(user_a, io.BytesIO(PDF), 'a.pdf', document_id=first.id, expected_revision=1)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 2
        assert db.scalar(select(StorageEvent).where(StorageEvent.action == 'upload_failed'))
    assert len(list((service.internal.root / 'objects').iterdir())) == 2


def test_unclassified_documents_and_duplicate_fingerprints_are_not_merged(core):
    service, sessions, _ = core
    a = service.upload(ADMIN, io.BytesIO(PDF), 'unknown.pdf')
    b = service.upload(ADMIN, io.BytesIO(PDF), 'another.pdf', company_id='company-a')
    assert a.id != b.id and a.classification_status == 'pending'
    with pytest.raises(StorageError, match='not_found'):
        service.document(actor('company-a', 'read'), a.id)
    reviewer = StorageActor('reviewer', permissions=frozenset({'read', 'review'}))
    assert service.document(reviewer, a.id).id == a.id
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentClassificationReview)) == 1
        versions = db.scalars(select(DocumentVersion)).all()
        assert len(versions) == 2 and versions[0].sha256 == versions[1].sha256


def test_external_observations_are_incremental_and_read_only(core):
    service, sessions, root = core
    source = service.register_local(ADMIN, 'Servidor ficticio', root)
    assert str(root) not in source.model_dump_json()
    path = root / 'a.pdf'
    path.write_bytes(PDF)
    initial = service.observe_external(ADMIN, source.id, 'a.pdf', company_id='company-a')
    again = service.observe_external(ADMIN, source.id, 'a.pdf', company_id='company-a')
    assert initial.id == again.id and again.revision == 1
    assert path.read_bytes() == PDF
    path.write_bytes(PDF + b' v2')
    with pytest.raises(StorageError, match='integrity_error'):
        with service.read(ADMIN, initial.id):
            pass
    updated = service.observe_external(ADMIN, source.id, 'a.pdf', company_id='company-a')
    assert updated.id == initial.id and updated.revision == 2
    with service.read(ADMIN, initial.id) as verified:
        assert verified.stream.read() == PDF + b' v2'
    with pytest.raises(StorageError, match='unavailable'):
        with service.read(ADMIN, initial.id, revision=1):
            pass
    path.unlink()  # Destructive scenario limited to this fixture's disposable origin.
    with pytest.raises(StorageError, match='missing'):
        with service.read(ADMIN, initial.id):
            pass
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 2
        assert db.scalar(select(func.count()).select_from(DocumentLocation)) == 2
        assert db.scalar(select(DocumentLocation.availability).join(DocumentVersion).where(DocumentVersion.number == 2)) == 'missing'
    path.write_bytes(PDF + b' v2')
    with service.read(ADMIN, initial.id) as restored:
        assert restored.stream.read() == PDF + b' v2'


def test_repository_integrity_and_transaction_rollback(core, monkeypatch):
    service, sessions, _ = core
    doc = service.upload(ADMIN, io.BytesIO(PDF), 'a.pdf', company_id='company-a')
    with sessions() as db:
        key = db.scalar(select(DocumentLocation.relative_key))
    (service.internal.root / key).write_bytes(PDF + b'tampered')
    with pytest.raises(StorageError, match='integrity_error'):
        with service.read(ADMIN, doc.id):
            pass
    monkeypatch.setattr(service, '_version', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('private details')))
    with pytest.raises(StorageError, match='storage_error'):
        service.upload(ADMIN, io.BytesIO(PDF), 'b.pdf', company_id='company-b')
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
    assert len(list((service.internal.root / 'objects').iterdir())) == 1


def test_sources_are_admin_only_smb_is_explicitly_unavailable(core):
    service, sessions, root = core
    with pytest.raises(StorageError, match='forbidden'):
        service.sources(actor('company-a', 'read'))
    with pytest.raises(StorageError, match='unauthorized_root'):
        service.register_local(ADMIN, 'Forbidden', root.parent)
    smb = WindowsSMBProvider()
    assert smb.availability().state == 'pending_configuration'
    for operation in (smb.enumerate, lambda: smb.metadata('a.pdf'), lambda: smb.open_read('a.pdf')):
        with pytest.raises(StorageError, match='smb_not_configured'):
            operation()
    with sessions.begin() as db:
        db.add(StorageSource(id='pending-smb', label='Servidor pendiente', kind='windows_smb', enabled=True, configuration={}))
    listing = service.sources(ADMIN)
    assert next(s for s in listing if s.id == 'pending-smb').state == 'pending_configuration'


def test_windows_unc_is_rejected_before_any_filesystem_probe(tmp_path, monkeypatch):
    if os.name != 'nt':
        pytest.skip('Windows UNC path handling')
    from app.storage import paths
    def no_probe(path):
        raise AssertionError('UNC must be rejected before a filesystem or network probe')
    monkeypatch.setattr(paths, 'check_no_links', no_probe)
    with pytest.raises(StorageError, match='smb_not_configured'):
        LocalFolderProvider(Path(r'\\not-a-real-server\share'), (tmp_path,))


def test_existing_document_api_cannot_bypass_managed_storage(client):
    c = company(client).json()
    from app.database import SessionLocal, DATA
    service = StorageService(SessionLocal, StorageSettings(DATA / 'cs-storage', DATA / 'documents'))
    doc = service.upload(ADMIN, io.BytesIO(PDF), 'managed.pdf', company_id=c['id'])
    assert client.get('/api/documents/' + doc.id + '/download', headers=A).content == PDF
    assert client.get('/api/documents/' + doc.id + '/download').status_code == 401
    assert client.delete('/api/documents/' + doc.id, headers=A).status_code == 409
    assert client.delete('/api/companies/' + c['id'], headers=A).status_code == 409
    assert doc.id in {d['id'] for d in client.get('/api/state', headers=A).json()['documents']}
    assert 'storage_name' not in client.get('/api/state', headers=A).json()['documents'][0]
