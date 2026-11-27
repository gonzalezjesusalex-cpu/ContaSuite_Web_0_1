"""Renovación del gestor de contraseñas, fase 3: «Agregar FIEL o CSD» and the internal service for Declara.

- `POST /companies/{cid}/certificates/check` reads the .cer, opens the .key with its password and returns what was
  read and the six checks of the spec. Nothing is stored.
- `POST /companies/{cid}/certificates/upload` repeats the checks and, only if every blocking one passes, stores the
  .cer, the .key and the key password encrypted with the vault's data key. An expired certificate is kept only as
  history. Replacing the active FIEL of a class must be asked for (`replace`); the previous one goes to the history.
- `obtener_fiel_para_acceso` (alias `obtenerFielParaAcceso`) is a Python service, not an HTTP route: with the vault
  unlocked it returns the .cer, the .key, the key password and the RFC of the active FIEL of a company and writes
  USO_DECLARA to the log. No route or button downloads the .cer or the .key.
"""

import hashlib
import re
from uuid import uuid4

from fastapi import Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select, update

from .credential_api import (
    activate,
    active_of,
    event,
    no_cache,
    ready,
    require_unlocked,
    router,
    vault_access,
)
from .credential_crypto import VaultLocked, strength
from .credential_models import certificates, credentials, files, versions
from .database import session
from .models import now
from .sat_certificates import MAX_FILE, checks
from .security import Principal, auth

LABELS = {
    'FIEL_EMPRESA': 'FIEL de la empresa',
    'FIEL_REPRESENTANTE': 'FIEL del representante',
    'CSD': 'Sello digital (CSD)',
}
HOLDER = {'FIEL_EMPRESA': 'company', 'FIEL_REPRESENTANTE': 'legal_rep', 'CSD': 'company'}


async def read_upload(upload, kind):
    name = (upload.filename or '').strip()
    data = await upload.read(MAX_FILE + 1)
    await upload.close()
    if not data or len(data) > MAX_FILE:
        raise HTTPException(422, f'El archivo .{kind} está vacío o es demasiado grande.')
    return name[:255] or f'archivo.{kind}', data


def representative_rfc(db, cid):
    """The representative's RFC that the active FIEL of a legal entity carries («RFC empresa / RFC repre»)."""
    subject = db.execute(
        select(certificates.c.subject).where(
            certificates.c.company_id == cid,
            certificates.c.cert_class == 'FIEL_EMPRESA',
            certificates.c.active.is_(True),
        )
    ).scalar()
    found = re.search(r'2\.5\.4\.45=([^,+]+)', subject or '')
    parts = [p.strip().upper() for p in (found.group(1).replace('\\', '') if found else '').split('/') if p.strip()]
    return parts[1] if len(parts) > 1 else ''


def public(data, results, names):
    """What the screen shows: never the password nor the files."""
    if data is None:
        return {'read': None, 'checks': results}
    read = {k: data[k] for k in ('holder_name', 'rfc', 'representative_rfc', 'curp', 'number', 'issuer', 'branch')}
    read.update(
        valid_from=data['valid_from'],
        valid_until=data['valid_until'],
        detected=data['detected'],
        days_left=(data['valid_until'] - now()).days,
    )
    return {
        'read': read,
        'checks': results,
        # Block «Lista para "Acceso con e.firma" del SAT»: the four fields of the SAT form.
        'sat_access': {'cer': names[0], 'key': names[1], 'password': '••••••••', 'rfc': data['rfc']},
    }


async def evaluate(db, p, cid, cer, key, password, cert_class):
    if cert_class not in LABELS:
        raise HTTPException(422, 'Elige de quién es la firma.')
    company = vault_access(db, p, cid, 'manage')
    require_unlocked(db, p, cid, None)
    cer_name, cer_data = await read_upload(cer, 'cer')
    key_name, key_data = await read_upload(key, 'key')
    data, results = checks(cer_data, key_data, password, cert_class, company.rfc, representative_rfc(db, cid))
    return company, (cer_name, cer_data), (key_name, key_data), data, results


@router.post('/companies/{cid}/certificates/check')
async def check_certificate(
    cid: str,
    response: Response,
    cer: UploadFile = File(...),
    key: UploadFile = File(...),
    password: str = Form(..., max_length=256),
    cert_class: str = Form(...),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    no_cache(response)
    ready(db)
    _, cer_file, key_file, data, results = await evaluate(db, p, cid, cer, key, password, cert_class)
    del password
    out = public(data, results, (cer_file[0], key_file[0]))
    if data:
        out['replaces'] = bool(active_of(db, cid, cert_class)) and data['valid_until'] >= now()
        out['duplicate'] = bool(
            db.execute(
                select(certificates.c.id).where(
                    certificates.c.company_id == cid, certificates.c.fingerprint == data['fingerprint']
                )
            ).first()
        )
    return out


@router.post('/companies/{cid}/certificates/upload', status_code=201)
async def upload_certificate(
    cid: str,
    response: Response,
    cer: UploadFile = File(...),
    key: UploadFile = File(...),
    password: str = Form(..., max_length=256),
    cert_class: str = Form(...),
    replace: bool = Form(False),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    no_cache(response)
    ready(db)
    company, (cer_name, cer_data), (key_name, key_data), data, results = await evaluate(
        db, p, cid, cer, key, password, cert_class
    )
    failed = [c for c in results if c['blocking'] and not c['ok']]
    if failed:
        raise HTTPException(422, failed[0]['message'])
    if db.execute(
        select(certificates.c.id).where(
            certificates.c.company_id == cid, certificates.c.fingerprint == data['fingerprint']
        )
    ).first():
        raise HTTPException(409, 'Ese certificado ya está guardado en esta empresa.')
    valid = data['valid_from'] <= now() <= data['valid_until']
    current = active_of(db, cid, cert_class)
    if valid and current and not replace:
        raise HTTPException(409, 'Ya hay una FIEL activa de esa clase. Confirma si la reemplazas.')
    cipher = require_unlocked(db, p, cid, None)
    kind = 'csd' if cert_class == 'CSD' else 'fiel'
    holder = HOLDER[cert_class]
    # The incomplete certificate of this class («Faltan .cer y .key», e.g. from an import) receives the files.
    incomplete = (
        db.execute(
            select(certificates).where(
                certificates.c.company_id == cid,
                certificates.c.cert_class == cert_class,
                certificates.c.fingerprint.is_(None),
                certificates.c.key_password_id.is_not(None),
            )
        )
        .mappings()
        .first()
    )
    credential_id = incomplete['key_password_id'] if incomplete else str(uuid4())
    old = (
        db.execute(select(credentials).where(credentials.c.id == credential_id)).mappings().first()
        if incomplete
        else None
    )
    envelope = cipher.seal(password, cid, credential_id)
    revision = (old['revision'] if old else 0) + 1
    values = dict(
        envelope=envelope,
        revision=revision,
        updated_at=now(),
        updated_by=p.subject,
        strength=strength(password, company.rfc),
        fingerprint=cipher.fingerprint(password),
    )
    del password
    if old:
        db.execute(update(credentials).where(credentials.c.id == credential_id).values(**values))
    else:
        db.execute(
            credentials.insert().values(
                id=credential_id,
                company_id=cid,
                service_id='csd_password' if kind == 'csd' else 'fiel_password',
                label=LABELS[cert_class] + (f' · {data["branch"]}' if data['branch'] else ''),
                archived=False,
                created_at=now(),
                holder=holder,
                kind='LLAVE',
                requires_review=False,
                extra={},
                **values,
            )
        )
    db.execute(
        versions.insert().values(
            credential_id=credential_id, revision=revision, envelope=envelope, actor_id=p.subject, created_at=now()
        )
    )
    certificate_id = incomplete['id'] if incomplete else str(uuid4())
    cert_values = dict(
        kind=kind,
        rfc=company.rfc,
        holder=holder,
        cert_class=cert_class,
        holder_name=data['holder_name'] or None,
        holder_rfc=data['rfc'] or None,
        holder_curp=data['curp'] or None,
        branch=data['branch'] or None,
        serial=data['number'][:100],
        subject=data['subject'],
        fingerprint=data['fingerprint'],
        valid_from=data['valid_from'],
        valid_until=data['valid_until'],
        key_password_id=credential_id,
        reviewed_at=now(),
        notes='',
        active=False,
    )
    if incomplete:
        db.execute(update(certificates).where(certificates.c.id == certificate_id).values(**cert_values))
    else:
        db.execute(
            certificates.insert().values(
                id=certificate_id, company_id=cid, document_id=None, origin='vault', revision=1, **cert_values
            )
        )
    for file_kind, name, raw in (('cer', cer_name, cer_data), ('key', key_name, key_data)):
        file_id = str(uuid4())
        db.execute(
            files.insert().values(
                id=file_id,
                company_id=cid,
                credential_id=credential_id,
                file_kind=file_kind,
                file_name=name,
                envelope=cipher.seal_bytes(raw, cid, 'file:' + file_id),
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                certificate_id=certificate_id,
                actor_id=p.subject,
                created_at=now(),
            )
        )
    del key_data
    if valid:
        activate(db, cid, certificate_id, cert_class)
    event(
        db,
        p,
        cid,
        'certificate_created',
        certificate_id,
        {'class': cert_class, 'active': valid, 'replaced': current if valid else None, 'number': data['number']},
    )
    db.commit()
    return {'id': certificate_id, 'active': valid, 'replaced': current if valid else None, 'authority_validated': False}


# ---------------------------------------------------------------- internal service for Declara (no HTTP route)


class FielUnavailable(LookupError):
    """The company has no active FIEL with its .cer and .key in the vault."""


def obtener_fiel_para_acceso(db, p, company_id, purpose='declara'):
    """The active FIEL of the company, for «Acceso con e.firma» of the SAT: {cer, key, password, rfc, names}.

    Needs the vault unlocked in the person's session (raises VaultLocked otherwise) and access to the company. The
    values live only in the caller's memory: never write them to disk, logs or HTTP responses.
    """
    from . import vault_session

    company = vault_access(db, p, company_id, 'view')
    cipher = vault_session.cipher(p.session_id)
    cert = (
        db.execute(
            select(certificates).where(
                certificates.c.company_id == company_id,
                certificates.c.cert_class == 'FIEL_EMPRESA',
                certificates.c.active.is_(True),
                certificates.c.fingerprint.is_not(None),
            )
        )
        .mappings()
        .first()
    )
    if not cert or not cert['key_password_id']:
        raise FielUnavailable('La empresa no tiene una FIEL activa con su .cer y su .key en el gestor.')
    stored = {
        r['file_kind']: r
        for r in db.execute(
            select(files).where(files.c.certificate_id == cert['id'], files.c.credential_id == cert['key_password_id'])
        ).mappings()
    }
    if not {'cer', 'key'} <= set(stored):
        raise FielUnavailable('Faltan el .cer o el .key de la FIEL activa.')
    password_row = db.execute(select(credentials).where(credentials.c.id == cert['key_password_id'])).mappings().first()
    try:
        out = {
            'cer': cipher.open_bytes(
                stored['cer']['envelope'], company_id, 'file:' + stored['cer']['id'], authorize_recent=lambda: True
            ),
            'key': cipher.open_bytes(
                stored['key']['envelope'], company_id, 'file:' + stored['key']['id'], authorize_recent=lambda: True
            ),
            'password': cipher.open(
                password_row['envelope'], company_id, password_row['id'], authorize_recent=lambda: True
            ),
            'rfc': cert['holder_rfc'] or company.rfc,
            'cer_name': stored['cer']['file_name'],
            'key_name': stored['key']['file_name'],
        }
    except VaultLocked:
        raise FielUnavailable('La FIEL guardada no se pudo abrir con la llave de la bóveda.') from None
    event(db, p, company_id, 'fiel_used', cert['id'], {'purpose': purpose[:40]})
    db.commit()
    return out


obtenerFielParaAcceso = obtener_fiel_para_acceso  # noqa: N816 - name of the spec
