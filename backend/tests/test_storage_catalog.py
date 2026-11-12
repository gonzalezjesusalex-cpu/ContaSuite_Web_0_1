import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select, func
from test_api import client, A, G, company
from app.main import app
from app.database import DATA, SessionLocal
from app.models import Document, DocumentVersion, DocumentLocation, StorageEvent
from app.storage.service import StorageService, StorageActor
from app.storage.settings import StorageSettings
from app.storage.router import installation_actor

PDF = b'%PDF-1.4\nsynthetic catalog\n%%EOF'
XML = b'<Comprobante><Texto>&lt;script&gt;alert(1)&lt;/script&gt;</Texto></Comprobante>'


def upload(client, name='document.pdf', payload=PDF, **fields):
    return client.post('/api/storage/documents', headers=A, files={'file': (name, payload)}, data=fields)


def test_storage_routes_require_installation_auth(client):
    for path in ('/options', '/documents', '/documents/missing', '/documents/missing/content'):
        assert client.get('/api/storage' + path).status_code == 401
        assert client.get('/api/storage' + path, headers=G).status_code == 401
    assert client.post('/api/storage/documents/missing/verify').status_code == 401
    assert client.post('/api/storage/documents', files={'file': ('a.pdf', PDF)}).status_code == 401


def test_catalog_upload_search_filters_and_public_metadata(client):
    c = company(client).json()
    first = upload(client, 'factura_%.xml', XML, company_id=c['id'], period='2026-10', document_type='cfdi', category='General')
    assert first.status_code == 201, first.text
    second = upload(client, 'sin-empresa.pdf')
    assert second.status_code == 201
    for params in ({'q': c['rfc']}, {'q': c['name']}, {'q': '2026-10'}, {'q': '_%'},
                   {'year': 2026, 'month': 10}, {'format': 'xml'}, {'document_type': 'cfdi'},
                   {'company_id': c['id']}, {'source_id': 'cs_internal', 'format': 'xml'}):
        result = client.get('/api/storage/documents', headers=A, params=params)
        assert result.status_code == 200, result.text
        page = result.json()
        assert page['total'] == 1 and page['items'][0]['id'] == first.json()['id'], params
        assert page['items'][0]['companies'][0]['rfc'] == c['rfc']
        for forbidden in ('root_path', 'relative_key', 'storage_name', 'configuration', 'password'):
            assert forbidden not in result.text
        assert str(DATA) not in result.text
    pending = client.get('/api/storage/documents?pending=true', headers=A).json()
    assert pending['total'] == pending['pending_count'] == 1
    assert pending['items'][0]['id'] == second.json()['id']
    assert pending['items'][0]['period'] is None
    assert client.get('/api/storage/documents?format=exe', headers=A).status_code == 422
    assert client.get('/api/storage/documents?year=1900', headers=A).status_code == 422
    assert client.get('/api/storage/documents?limit=101', headers=A).status_code == 422
    assert client.get('/api/storage/documents?company_id=missing', headers=A).status_code == 404


def test_catalog_pagination_is_stable_and_search_is_literal(client):
    for n in range(4):
        assert upload(client, f'file-{n}.pdf').status_code == 201
    page1 = client.get('/api/storage/documents?limit=2', headers=A).json()
    page2 = client.get('/api/storage/documents?limit=2&offset=2', headers=A).json()
    assert page1['total'] == page2['total'] == 4
    assert not {d['id'] for d in page1['items']} & {d['id'] for d in page2['items']}
    assert client.get('/api/storage/documents?q=%25', headers=A).json()['total'] == 0


def test_scoped_core_actor_cannot_access_another_company_through_api(client):
    a = company(client).json()
    b = company(client, name='Empresa secreta B', rfc='BBB020202BB2').json()
    doc_a = upload(client, company_id=a['id']).json()
    doc_b = upload(client, company_id=b['id']).json()
    pending = upload(client).json()
    restricted = StorageActor('test-user-a', frozenset({a['id']}), frozenset({'read', 'write'}))
    app.dependency_overrides[installation_actor] = lambda: restricted
    try:
        listing = client.get('/api/storage/documents', headers=A).json()
        assert [d['id'] for d in listing['items']] == [doc_a['id']]
        assert client.get('/api/storage/documents?q=secreta', headers=A).json()['total'] == 0
        assert client.get('/api/storage/documents?q=' + b['rfc'], headers=A).json()['total'] == 0
        assert client.get('/api/storage/documents?company_id=' + b['id'], headers=A).status_code == 403
        assert client.get('/api/storage/documents?pending=true', headers=A).status_code == 403
        for ident in (doc_b['id'], pending['id']):
            assert client.get('/api/storage/documents/' + ident, headers=A).status_code == 404
            assert client.get('/api/storage/documents/' + ident + '/content', headers=A).status_code == 404
            assert client.post('/api/storage/documents/' + ident + '/verify', headers=A).status_code == 404
        assert upload(client, company_id=b['id']).status_code == 403
        options = client.get('/api/storage/options', headers=A).json()
        assert [c['id'] for c in options['companies']] == [a['id']]
        assert not options['can_review']
        assert client.get('/api/storage/documents/' + doc_a['id'] + '/content').status_code == 401
    finally:
        app.dependency_overrides.pop(installation_actor, None)


def test_verified_download_preview_and_versions(client):
    response = upload(client, 'acuse-á.xml', XML, period='2026-10')
    ident = response.json()['id']
    base = '/api/storage/documents/' + ident
    download = client.get(base + '/content', headers=A)
    assert download.status_code == 200 and download.content == XML
    assert download.headers['cache-control'] == 'private, no-store'
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert '%C3%A1' in download.headers['content-disposition']
    preview = client.get(base + '/content?preview=true', headers=A)
    assert preview.status_code == 200 and preview.content == XML
    assert preview.headers['content-type'].startswith('text/plain')
    assert client.get(base + '/content?revision=99', headers=A).status_code == 404
    assert client.get(base + '/content?revision=0', headers=A).status_code == 422
    detail = client.get(base, headers=A).json()
    assert detail['versions'][0]['sha256'] == hashlib.sha256(XML).hexdigest()
    assert client.post(base + '/verify', headers=A).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(StorageEvent).where(StorageEvent.action == 'content_read', StorageEvent.document_id == ident))


def test_legacy_adoption_preserves_bytes_and_id_and_checks_integrity_on_old_route(client):
    c = company(client).json()
    response = client.post('/api/companies/' + c['id'] + '/documents', headers=A, files={'file': ('anterior.pdf', PDF)})
    ident = response.json()['id']
    with SessionLocal() as db:
        storage_name = db.get(Document, ident).storage_name
    path = DATA / 'documents' / storage_name
    before = path.read_bytes()
    initial = client.get('/api/storage/documents/' + ident, headers=A).json()
    assert initial['document']['availability'] == 'unchecked' and initial['versions'] == []
    result = client.post('/api/storage/documents/' + ident + '/verify', headers=A)
    assert result.status_code == 200, result.text
    assert result.json()['document']['id'] == ident
    assert path.read_bytes() == before
    assert result.json()['versions'][0]['sha256'] == hashlib.sha256(before).hexdigest()
    assert client.get('/api/documents/' + ident + '/download', headers=A).content == PDF
    with SessionLocal() as db:
        assert db.get(Document, ident).storage_name == storage_name
        assert db.scalar(select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id == ident)) == 1
    path.write_bytes(PDF + b'changed')  # DATA is the test_api disposable directory, never the installation DATA.
    altered = client.get('/api/documents/' + ident + '/download', headers=A)
    assert altered.status_code == 409 and PDF not in altered.content
    assert client.get('/api/storage/documents/' + ident + '/content', headers=A).status_code == 409


def certificate_and_key():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CS-Storage synthetic certificate')])
    now = datetime.now(timezone.utc)
    cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1234).not_valid_before(now).not_valid_after(now + timedelta(days=30)).sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.DER), key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def test_public_cer_is_preserved_but_private_or_appended_key_is_rejected(client):
    cert, private = certificate_and_key()
    uploaded = upload(client, 'publico.cer', cert, document_type='certificate')
    assert uploaded.status_code == 201, uploaded.text
    base = '/api/storage/documents/' + uploaded.json()['id']
    assert client.get(base + '/content', headers=A).content == cert
    assert client.get(base + '/content?preview=true', headers=A).status_code == 415
    for filename, data in [('privada.cer', private), ('mixto.cer', cert + private), ('clave.key', private), ('firma.pfx', private)]:
        assert upload(client, filename, data).status_code == 422
    assert client.get('/api/storage/documents?format=cer', headers=A).json()['total'] == 1


def test_content_validation_and_metadata_limits(client):
    for name, data in [('falso.pdf', b'not a PDF'), ('falso.xml', b'<!DOCTYPE x [<!ENTITY e "x">]><x>&e;</x>'),
                       ('key.pdf', b'%PDF- PRIVATE KEY'), ('../escape.pdf', PDF), ('empty.pdf', b'')]:
        assert upload(client, name, data).status_code == 422
    assert upload(client, period='2026-13').status_code == 422
    assert upload(client, document_type='inventado').status_code == 422
    assert upload(client, category='x' * 81).status_code == 422
    assert client.get('/api/storage/documents', headers=A).json()['total'] == 0


def test_external_missing_and_changed_files_return_safe_error_statuses(client, tmp_path, monkeypatch):
    monkeypatch.setenv('CS_STORAGE_ALLOWED_ROOTS', json.dumps([str(tmp_path)]))
    service = StorageService(SessionLocal, StorageSettings.from_environment(DATA))
    admin = StorageActor('test-indexer', admin=True)
    source = service.register_local(admin, 'Origen de prueba', tmp_path)
    path = tmp_path / 'file.pdf'
    path.write_bytes(PDF)
    doc = service.observe_external(admin, source.id, 'file.pdf')
    assert client.get('/api/storage/documents?source_id=' + source.id, headers=A).json()['total'] == 1
    path.unlink()
    result = client.get('/api/storage/documents/' + doc.id + '/content', headers=A)
    assert result.status_code == 404 and str(tmp_path) not in result.text
    row = client.get('/api/storage/documents/' + doc.id, headers=A).json()['document']
    assert row['availability'] == 'missing'
    path.write_bytes(PDF)
    assert client.post('/api/storage/documents/' + doc.id + '/verify', headers=A).json()['document']['availability'] == 'available'
    path.write_bytes(PDF + b'changed')
    assert client.get('/api/storage/documents/' + doc.id + '/content', headers=A).status_code == 409


def test_download_rejects_oversized_or_invalid_old_attachments(client):
    c = company(client).json()
    for name, content in [('fake.cer', b'not cert'), ('private.cer', certificate_and_key()[1]), ('fake.pdf', b'not pdf')]:
        assert client.post('/api/companies/' + c['id'] + '/documents', headers=A, files={'file': (name, content)}).status_code == 422
    assert client.get('/api/storage/documents', headers=A).json()['total'] == 0


def test_historical_download_keeps_original_version_name(client):
    import io
    service = StorageService(SessionLocal, StorageSettings.from_environment(DATA))
    admin = StorageActor('test-version-owner', admin=True)
    first = service.upload(admin, io.BytesIO(PDF), 'antes.pdf')
    service.upload(admin, io.BytesIO(XML), 'ahora.xml', document_id=first.id, expected_revision=1)
    result = client.get('/api/storage/documents/' + first.id + '/content?revision=1', headers=A)
    assert result.status_code == 200 and result.content == PDF
    assert 'antes.pdf' in result.headers['content-disposition']
