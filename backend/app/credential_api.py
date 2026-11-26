from zoneinfo import ZoneInfo
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from .database import session
from .models import Company, Document, DocumentCompanyLink, now
from .security import auth, Principal, utc
from .credential_models import metadata, services, grants, credentials, versions, certificates, audit, settings
from .credential_crypto import VaultLocked
from .schema_cache import tables_ready

PERMISSIONS = {'metadata', 'create', 'modify', 'reveal', 'certificates', 'history', 'alerts', 'permissions'}
router = APIRouter(prefix='/api/credentials', tags=['Credenciales y certificados'])


def ready(db):
    if not tables_ready(db, metadata):
        raise HTTPException(503, 'Módulo pendiente de migración autorizada.')


def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, private'
    response.headers['Pragma'] = 'no-cache'


def by_role(p, company, permission):
    # Bloque 2 (decisions 2-4): administrators and the company's responsible accountant hold every
    # credential permission except reveal. Plan v1.1 (decision 1 of 23/11/2026): seeing or copying passwords is
    # for administrators and for users with the explicit «reveal» grant of the company (no role includes it).
    if permission == 'reveal':
        return p.admin
    return p.admin or (p.role == 'contador' and company.accountant_id == p.subject)


def allowed(p, db, cid, permission):
    p.require_company(cid)
    company = db.get(Company, cid)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada.')
    if by_role(p, company, permission):
        return
    if (
        permission != 'reveal'
        or not db.execute(
            select(grants.c.user_id).where(
                grants.c.user_id == p.subject, grants.c.company_id == cid, grants.c.permission == permission
            )
        ).first()
    ):
        raise HTTPException(403, 'Sin permiso para esta operación.')


def event(db, p, cid, action, ident=None, details=None):
    db.execute(
        audit.insert().values(
            id=str(uuid4()),
            company_id=cid,
            actor_id=p.subject,
            action=action,
            record_id=ident,
            created_at=now(),
            metadata=details or {},
        )
    )


PUBLIC = [
    'id',
    'company_id',
    'service_id',
    'label',
    'revision',
    'archived',
    'created_at',
    'updated_at',
    'username',
    'url',
    'notes',
    'extra',
    'holder',
    'strength',
]


def public_credential(row, repeated=frozenset()):
    # Never the envelope or the fingerprint: only whether the password is repeated elsewhere in the vault.
    out = {k: row.get(k) for k in PUBLIC}
    out['repeated'] = bool(row.get('fingerprint') and row['fingerprint'] in repeated)
    return out


def repeated_fingerprints(db):
    from sqlalchemy import func

    return frozenset(
        r[0]
        for r in db.execute(
            select(credentials.c.fingerprint)
            .where(credentials.c.fingerprint.is_not(None), credentials.c.archived.is_(False))
            .group_by(credentials.c.fingerprint)
            .having(func.count() > 1)
        )
    )


def attached_files(db, company_ids):
    from .credential_models import files as vault_files

    out = {}
    for r in db.execute(
        select(vault_files.c.id, vault_files.c.credential_id, vault_files.c.file_kind, vault_files.c.file_name).where(
            vault_files.c.company_id.in_(company_ids)
        )
    ).mappings():
        out.setdefault(r['credential_id'], []).append({'id': r['id'], 'kind': r['file_kind'], 'name': r['file_name']})
    return out


def temporal(row, thresholds=(60, 30, 15), stamp=None):
    stamp = stamp or now()
    end = row.get('valid_until')
    start = row.get('valid_from')
    if not start or not end:
        return {'state': 'unknown', 'days_remaining': None, 'threshold': None}
    start, end = utc(start), utc(end)
    days = (
        end.astimezone(ZoneInfo('America/Mexico_City')).date()
        - stamp.astimezone(ZoneInfo('America/Mexico_City')).date()
    ).days
    state = (
        'pending_verification'
        if stamp < start
        else 'expired'
        if stamp > end
        else 'expiring'
        if days <= max(thresholds)
        else 'valid'
    )
    return {
        'state': state,
        'days_remaining': days,
        'threshold': next((t for t in sorted(thresholds) if days <= t), None) if days >= 0 else None,
    }


def parse_public_certificate(payload):
    try:
        if len(payload) > 1024 * 1024:
            raise ValueError()
        cert = (
            x509.load_pem_x509_certificate(payload)
            if payload.lstrip().startswith(b'-----BEGIN CERTIFICATE-----')
            else x509.load_der_x509_certificate(payload)
        )
        return dict(
            serial=format(cert.serial_number, 'X'),
            subject=cert.subject.rfc4514_string()[:1000],
            fingerprint=cert.fingerprint(hashes.SHA256()).hex(),
            valid_from=cert.not_valid_before_utc,
            valid_until=cert.not_valid_after_utc,
        )
    except Exception:  # noqa: BLE001 - any parse failure means "not an accepted public certificate" (422)
        raise HTTPException(422, 'No es un certificado público X.509 admitido.') from None


@router.get('/companies/{cid}')
def overview(cid: str, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'metadata')
    require_unlocked(db, p, cid, None)  # a locked vault shows no company data at all
    repeated = repeated_fingerprints(db)
    items = [
        public_credential(r, repeated)
        for r in db.execute(select(credentials).where(credentials.c.company_id == cid)).mappings()
    ]
    attached = attached_files(db, [cid])
    for item in items:
        item['files'] = attached.get(item['id'], [])
    thresholds = db.execute(select(settings.c.thresholds).where(settings.c.id == 1)).scalar() or [60, 30, 15]
    certs = [
        {**dict(r), **temporal(r, thresholds), 'authority_validated': False}
        for r in db.execute(select(certificates).where(certificates.c.company_id == cid)).mappings()
    ]
    event(db, p, cid, 'metadata_read')
    db.commit()
    perms = [
        a
        for a in PERMISSIONS
        if by_role(p, db.get(Company, cid), a)
        or a == 'reveal'
        and db.execute(
            select(grants.c.permission).where(
                grants.c.user_id == p.subject, grants.c.company_id == cid, grants.c.permission == a
            )
        ).first()
    ]
    return dict(
        credentials=items,
        certificates=certs,
        services=[dict(r) for r in db.execute(select(services)).mappings()],
        permissions=perms,
        reveal_enabled='reveal' in perms and vault_unlocked(p),
        vault_unlocked=vault_unlocked(p),
        thresholds=thresholds,
    )


def vault_unlocked(p):
    from . import vault_session

    return vault_session.unlocked(p.session_id)


class CredentialIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service_id: str = Field(max_length=50)
    # Plan v1.1: a free name for «Otro» portals; the screen warns not to write passwords in names or notes.
    label: str = Field('Acceso', min_length=1, max_length=100)
    # Omitted when only the visible data change; the stored password is kept.
    secret: SecretStr | None = Field(None, min_length=1, max_length=4096)
    revision: int = Field(0, ge=0)
    username: str | None = Field(None, max_length=200)
    url: str | None = Field(None, max_length=500, pattern=r'^(https?://\S+)?$')
    notes: str | None = Field(None, max_length=2000)
    extra: dict[str, str] = Field(default_factory=dict, max_length=10)
    holder: Literal['company', 'legal_rep'] | None = None


@router.post('/companies/{cid}/secrets')
def store(
    cid: str,
    payload: CredentialIn,
    response: Response,
    ident: str | None = None,
    p: Principal = Depends(auth),
    db=Depends(session),
):
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'modify' if ident else 'create')
    if p.bootstrap or not p.session_id:
        raise HTTPException(403, 'Se requiere una sesión personal.')
    if not db.execute(select(services.c.id).where(services.c.id == payload.service_id)).first():
        raise HTTPException(422, 'Servicio no registrado.')
    old = (
        db.execute(select(credentials).where(credentials.c.id == ident, credentials.c.company_id == cid))
        .mappings()
        .first()
        if ident
        else None
    )
    if ident and not old:
        raise HTTPException(404, 'Credencial no encontrada.')
    if (old['revision'] if old else 0) != payload.revision:
        raise HTTPException(409, 'El registro cambió; actualiza.')
    if not old and payload.secret is None:
        raise HTTPException(422, 'Captura la contraseña.')
    ident = ident or str(uuid4())
    visible = {
        'username': (payload.username or '').strip() or None,
        'url': payload.url or None,
        'notes': (payload.notes or '').strip() or None,
        'extra': {k[:40]: v[:200] for k, v in payload.extra.items()},
        'holder': payload.holder,
        'label': payload.label.strip() or 'Acceso',
    }
    envelope = old['envelope'] if old else None
    if payload.secret is not None:
        from .credential_crypto import strength

        secret = payload.secret.get_secret_value()
        cipher = require_unlocked(db, p, cid, ident)
        envelope = cipher.seal(secret, cid, ident)
        visible['fingerprint'] = cipher.fingerprint(secret)
        visible['strength'] = strength(secret, db.get(Company, cid).rfc)
        del secret
    revision = payload.revision + 1
    try:
        if old:
            if not db.execute(
                update(credentials)
                .where(credentials.c.id == ident, credentials.c.revision == payload.revision)
                .values(envelope=envelope, revision=revision, updated_at=now(), **visible)
            ).rowcount:
                raise HTTPException(409, 'Edición concurrente.')
        else:
            db.execute(
                credentials.insert().values(
                    id=ident,
                    company_id=cid,
                    service_id=payload.service_id,
                    envelope=envelope,
                    revision=revision,
                    archived=False,
                    created_at=now(),
                    updated_at=now(),
                    **visible,
                )
            )
        db.execute(
            versions.insert().values(
                credential_id=ident, revision=revision, envelope=envelope, actor_id=p.subject, created_at=now()
            )
        )
        event(
            db,
            p,
            cid,
            'credential_modified' if old else 'credential_created',
            ident,
            {'revision': revision, 'secret_changed': payload.secret is not None},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Edición concurrente.') from None
    return {'id': ident, 'revision': revision}


def credential_row(db, cid, ident):
    row = (
        db.execute(select(credentials).where(credentials.c.id == ident, credentials.c.company_id == cid))
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, 'Credencial no encontrada.')
    return row


def require_unlocked(db, p, cid, ident):
    """The cipher of this session's unlocked vault (renovación del gestor, fase 1); 423 and a log entry if locked."""
    from . import vault_session

    try:
        return vault_session.cipher(p.session_id)
    except VaultLocked:
        event(db, p, cid, 'reveal_blocked', ident, {'reason': 'vault_locked'})
        db.commit()
        raise HTTPException(423, 'La bóveda está bloqueada.', headers={'Cache-Control': 'no-store'}) from None


class RevealIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['view', 'copy'] = 'view'
    reason: str = Field('', max_length=200)


@router.post('/companies/{cid}/secrets/{ident}/reveal')
def reveal(
    cid: str,
    ident: str,
    response: Response,
    p: Principal = Depends(auth),
    db=Depends(session),
    payload: RevealIn | None = None,
):
    """Plan v1.1: the password of one credential, with the vault unlocked, for an authorized person.

    Every view or copy is written to the vault log (who, when, which company, why). The value travels only in
    this no-store response; it is never logged, listed or exported here.
    """
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'reveal')
    payload = payload or RevealIn()
    row = credential_row(db, cid, ident)
    cipher = require_unlocked(db, p, cid, ident)
    try:
        secret = cipher.open(row['envelope'], cid, ident, authorize_recent=lambda: True)
    except VaultLocked:
        raise HTTPException(409, 'Este secreto no se pudo abrir con la llave de la bóveda.') from None
    action = 'secret_copied' if payload.action == 'copy' else 'secret_revealed'
    event(db, p, cid, action, ident, {'reason': payload.reason})
    db.commit()
    return {'secret': secret, 'expires_in': 20}


@router.delete('/companies/{cid}/secrets/{ident}')
def archive(
    cid: str,
    ident: str,
    response: Response,
    revision: int = Query(ge=1),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'modify')
    changed = db.execute(
        update(credentials)
        .where(credentials.c.id == ident, credentials.c.company_id == cid, credentials.c.revision == revision)
        .values(archived=True, revision=revision + 1, updated_at=now())
    )
    if not changed.rowcount:
        raise HTTPException(409, 'El registro cambió o no está disponible.')
    event(db, p, cid, 'credential_archived', ident)
    db.commit()
    return {'archived': True}


class CertificateIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['fiel', 'csd', 'unknown'] = 'unknown'
    document_id: str | None = Field(None, max_length=36)
    notes: str = Field('', max_length=2000)
    # Plan v1.1: a second FIEL may belong to the company's legal representative (another RFC).
    holder: Literal['company', 'legal_rep'] = 'company'


@router.post('/companies/{cid}/certificates')
def add_certificate(
    cid: str, payload: CertificateIn, response: Response, p: Principal = Depends(auth), db=Depends(session)
):
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'certificates')
    company = db.get(Company, cid)
    parsed = {}
    origin = 'manual'
    if payload.document_id:
        doc = db.get(Document, payload.document_id)
        linked = doc and (
            doc.company_id == cid
            or db.execute(
                select(DocumentCompanyLink.document_id).where(
                    DocumentCompanyLink.document_id == doc.id, DocumentCompanyLink.company_id == cid
                )
            ).first()
        )
        if not linked or not doc.name.lower().endswith('.cer'):
            raise HTTPException(422, 'Selecciona un CER público vinculado a esta empresa. No se procesan KEY.')
        from .storage.router import storage_service
        from .storage.providers import StorageError

        try:
            with storage_service().read(p.storage_actor(), doc.id) as content:
                parsed = parse_public_certificate(content.stream.read(1024 * 1024 + 1))
        except StorageError:
            raise HTTPException(409, 'No se pudo leer el certificado público.') from None
        origin = 'cs_storage'
        from .storage.classifier import RFC, valid_rfc

        rfcs = {r for r in RFC.findall(parsed['subject'].upper()) if valid_rfc(r)}
        if rfcs and company.rfc not in rfcs and payload.holder == 'company':
            raise HTTPException(422, 'El RFC del certificado no coincide con la empresa.')
    ident = str(uuid4())
    try:
        db.execute(
            certificates.insert().values(
                id=ident,
                company_id=cid,
                rfc=company.rfc,
                kind=payload.kind,
                document_id=payload.document_id,
                origin=origin,
                reviewed_at=now(),
                notes=payload.notes,
                revision=1,
                holder=payload.holder,
                **parsed,
            )
        )
        event(db, p, cid, 'certificate_created', ident, {'kind': payload.kind, 'origin': origin})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Certificado ya registrado.') from None
    return {'id': ident, 'authority_validated': False}


@router.get('/companies/{cid}/history')
def history(cid: str, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'history')
    require_unlocked(db, p, cid, None)
    rows = [
        dict(r)
        for r in db.execute(
            select(audit).where(audit.c.company_id == cid).order_by(audit.c.created_at.desc()).limit(100)
        ).mappings()
    ]
    event(db, p, cid, 'history_read')
    db.commit()
    return rows


class CertificateEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    kind: Literal['fiel', 'csd', 'unknown']
    notes: str = Field('', max_length=2000)


@router.put('/companies/{cid}/certificates/{ident}')
def edit_certificate(
    cid: str,
    ident: str,
    payload: CertificateEdit,
    response: Response,
    p: Principal = Depends(auth),
    db=Depends(session),
):
    no_cache(response)
    ready(db)
    allowed(p, db, cid, 'certificates')
    old = (
        db.execute(select(certificates).where(certificates.c.id == ident, certificates.c.company_id == cid))
        .mappings()
        .first()
    )
    if not old:
        raise HTTPException(404, 'Certificado no encontrado.')
    try:
        result = db.execute(
            update(certificates)
            .where(certificates.c.id == ident, certificates.c.revision == payload.revision)
            .values(kind=payload.kind, notes=payload.notes, reviewed_at=now(), revision=payload.revision + 1)
        )
        if not result.rowcount:
            raise HTTPException(409, 'El certificado cambió; actualiza.')
        event(
            db,
            p,
            cid,
            'certificate_modified',
            ident,
            {'before_kind': old['kind'], 'after_kind': payload.kind, 'revision': payload.revision + 1},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Certificado ya registrado con ese tipo.') from None
    return {'revision': payload.revision + 1}


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=100)


@router.post('/services')
def service(payload: ServiceIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    p.require_admin()
    if not payload.label.strip():
        raise HTTPException(422, 'Nombre requerido.')
    ident = str(uuid4())
    db.execute(services.insert().values(id=ident, label=payload.label.strip()))
    event(db, p, None, 'service_created', ident)
    db.commit()
    return {'id': ident}


class GrantIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: str = Field(max_length=36)
    permission: Literal['metadata', 'create', 'modify', 'reveal', 'certificates', 'history', 'alerts', 'permissions']
    enabled: bool


@router.put('/companies/{cid}/permissions')
def grant(cid: str, payload: GrantIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    no_cache(response)
    ready(db)
    p.require_admin()
    allowed(p, db, cid, 'permissions')
    from .models import UserAccount, UserCompanyGrant

    user = db.get(UserAccount, payload.user_id)
    if not user or not user.enabled or (not user.admin and not db.get(UserCompanyGrant, (user.id, cid))):
        raise HTTPException(422, 'Usuario sin acceso a la empresa.')
    condition = (
        (grants.c.company_id == cid) & (grants.c.user_id == user.id) & (grants.c.permission == payload.permission)
    )
    db.execute(grants.delete().where(condition))
    if payload.enabled:
        db.execute(grants.insert().values(company_id=cid, user_id=user.id, permission=payload.permission))
    event(db, p, cid, 'permission_changed', details=payload.model_dump())
    db.commit()
    return {'saved': True}
