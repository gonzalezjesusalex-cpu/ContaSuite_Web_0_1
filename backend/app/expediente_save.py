"""Save generated files into a company's Centro Documental (cambios 4.5 and 5.5).

Always an action of the user, always through the existing storage service (permissions, SHA-256, versions). A file is
a NEW document, or a NEW VERSION of the document that already has the same company, type, period and name; an existing
version is never overwritten. Identical content is reported as already registered and not stored again.
"""

import hashlib
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from .models import Document, DocumentVersion
from .security import Principal
from .storage.providers import StorageError
from .storage.router import storage_http_error, storage_service


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def find_document(db, company_id, document_type, period, name):
    return db.scalar(
        select(Document)
        .where(
            Document.company_id == company_id,
            Document.managed == True,  # noqa: E712
            Document.document_type == document_type,
            Document.period == period,
            Document.name == name,
        )
        .order_by(Document.created_at)
    )


def save_file(principal: Principal, company_id, path, name, *, document_type, period, category='General'):
    """Returns {'status': 'nuevo' | 'version_nueva' | 'ya_registrado', 'document_id': str, 'name': str}."""
    service = storage_service()
    actor = principal.storage_actor()
    digest = sha256_file(path)
    with service.sessions() as db:
        existing = find_document(db, company_id, document_type, period, name)
        revision = existing.storage_revision if existing else None
        existing_id = existing.id if existing else None
        if existing:
            last = db.scalar(
                select(DocumentVersion.sha256)
                .where(DocumentVersion.document_id == existing.id)
                .order_by(DocumentVersion.number.desc())
                .limit(1)
            )
            if last == digest:
                return {'status': 'ya_registrado', 'document_id': existing.id, 'name': name}
    try:
        with Path(path).open('rb') as stream:
            result = service.upload(
                actor,
                stream,
                name,
                company_id=company_id,
                document_id=existing_id,
                expected_revision=revision,
                category=category,
                document_type=document_type,
                period=period,
            )
    except StorageError as exc:
        raise storage_http_error(exc) from None
    except OSError:
        raise HTTPException(409, 'No se pudo leer el archivo generado.') from None
    return {
        'status': 'version_nueva' if existing_id else 'nuevo',
        'document_id': getattr(result, 'id', None) or (result.get('id') if isinstance(result, dict) else None),
        'name': name,
    }
