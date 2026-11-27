"""Plan v1.1, Cambio 4: password manager on the existing vault (same router, tables and log).

- Revealing, copying, using, importing or exporting a secret needs the vault unlocked in this session with the
  master password (app/vault_master.py; the data key lives only in server memory, app/vault_session.py).
- List by company and portal with search; user visible, password hidden; strength and repetition checked
  locally (no breach service).
- FIEL/CSD files encrypted outside the document folders, never indexed by CS-Storage nor sent to the agent, never
  downloaded nor sent over HTTP (fase 3: app/vault_fiel.py). Extension tickets carry only passwords.
- Import in three steps, template and export with the master password: app/vault_import.py (fase 4).
"""

import hashlib
import secrets as tokens
import unicodedata
from datetime import timedelta
from typing import Literal

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from .credential_api import (
    attached_files,
    credential_row,
    event,
    no_cache,
    public_credential,
    ready,
    repeated_fingerprints,
    require_unlocked,
    router,
    vault_access,
)
from . import vault_session
from .credential_crypto import VaultLocked
from .credential_models import certificates, credentials, files, services, tickets
from .database import session
from .models import Company, UserAccount, now
from .security import Principal, auth, utc

MAX_FILE = 64 * 1024
MAX_XLSX = 5 * 1024 * 1024
TICKET_SECONDS = 60


# ---------------------------------------------------------------- list and health


@router.get('/vault')
def vault_list(
    response: Response,
    query: str = '',
    service: str = '',
    company_id: str | None = None,
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """Every credential the person may see, by company and portal, with search. Never a secret."""
    no_cache(response)
    ready(db)
    vault_access(db, p, None, 'view')
    require_unlocked(db, p, company_id, None)  # a locked vault shows no company data at all
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    visible = {
        c.id: c for c in companies if (p.admin or c.id in p.company_ids) and (not company_id or c.id == company_id)
    }
    labels = dict(db.execute(select(services.c.id, services.c.label)).all())
    repeated = repeated_fingerprints(db)
    attached = attached_files(db, list(visible))
    q = fold(query)
    items, everything = [], []
    for r in db.execute(
        select(credentials).where(credentials.c.company_id.in_(list(visible)), credentials.c.archived.is_(False))
    ).mappings():
        c = visible[r['company_id']]
        everything.append(public_credential(r, repeated))
        if service and r['service_id'] != service:
            continue
        portal = labels.get(r['service_id'], r['service_id'])
        haystack = fold(' '.join([c.name, c.rfc, portal, r['label'] or '', r['username'] or '', r['url'] or '']))
        if q and q not in haystack:
            continue
        item = public_credential(r, repeated)
        item.update(
            company_name=c.name,
            company_rfc=c.rfc,
            portal=portal,
            files=attached.get(r['id'], []),
            can_reveal=True,
            can_modify=p.admin,
        )
        items.append(item)
    items.sort(key=lambda i: (i['company_name'], i['portal'], i['label'] or ''))
    event(db, p, company_id, 'vault_listed', details={'query': bool(query)})
    db.commit()
    from .credential_api import vault_unlocked

    vault_session.touch(p.session_id)
    certs = vault_certificates(db, list(visible))
    passwords = [i for i in everything if i['kind'] != 'LLAVE']
    return {
        'items': items,
        'certificates': certs,
        'summary': summary(db, p, visible, passwords, certs),
        'services': [{'id': k, 'label': v} for k, v in sorted(labels.items(), key=lambda kv: kv[1])],
        'companies': [
            {
                'id': c.id,
                'name': c.name,
                'rfc': c.rfc,
                'regime': c.regime,
                'person_type': c.person_type,
                'can_create': p.admin,
                'fiel': fiel_badge(certs, c.id),
                'certificate_count': sum(1 for x in certs if x['company_id'] == c.id and x['active']),
                'password_count': sum(1 for x in passwords if x['company_id'] == c.id),
            }
            for c in visible.values()
        ],
        'health': {
            'weak': sum(1 for i in items if i['strength'] is not None and i['strength'] <= 1),
            'repeated': sum(1 for i in items if i['repeated']),
            'unknown': sum(1 for i in items if i['strength'] is None),
        },
        'vault_unlocked': vault_unlocked(p),
        'can_export': p.admin,
    }


# ---------------------------------------------------------------- fase 5: certificates and summary of the screen


def days_left(end):
    from zoneinfo import ZoneInfo

    if not end:
        return None
    zone = ZoneInfo('America/Mexico_City')
    return (utc(end).astimezone(zone).date() - now().astimezone(zone).date()).days


def validity(days):
    """Recomputed on every read from `valid_until`: more than 30 days green, 30 or fewer amber, expired red."""
    if days is None:
        return 'unknown'
    return 'expired' if days < 0 else 'expiring' if days <= 30 else 'valid'


def vault_certificates(db, company_ids):
    """Every certificate of the companies (active and history), never a file or a password."""
    names = {}
    for r in db.execute(
        select(files.c.certificate_id, files.c.file_kind, files.c.file_name).where(files.c.company_id.in_(company_ids))
    ):
        if r[0]:
            names.setdefault(r[0], {})[r[1]] = r[2]
    out = []
    for r in db.execute(select(certificates).where(certificates.c.company_id.in_(company_ids))).mappings():
        if not r['cert_class']:
            continue
        days = days_left(r['valid_until'])
        out.append(
            {
                'id': r['id'],
                'company_id': r['company_id'],
                'cert_class': r['cert_class'],
                'holder_name': r['holder_name'],
                'holder_rfc': r['holder_rfc'],
                'holder_curp': r['holder_curp'],
                'branch': r['branch'],
                'number': r['serial'],
                'valid_from': r['valid_from'],
                'valid_until': r['valid_until'],
                'days_left': days,
                'validity': validity(days),
                'active': bool(r['active']),
                'replaced_by': r['replaced_by'],
                'incomplete': not r['fingerprint'],
                'files': names.get(r['id'], {}),
                'key_password_id': r['key_password_id'],
            }
        )
    out.sort(key=lambda x: ({'FIEL_EMPRESA': 0, 'FIEL_REPRESENTANTE': 1, 'CSD': 2}[x['cert_class']], x['branch'] or ''))
    return out


def fiel_badge(certs, company_id):
    """«FIEL vigente», «FIEL vence en N días», «FIEL vencida» or «Sin FIEL» for the list of companies."""
    fiel = next(
        (
            c
            for c in certs
            if c['company_id'] == company_id
            and c['cert_class'] == 'FIEL_EMPRESA'
            and c['active']
            and not c['incomplete']
        ),
        None,
    )
    if not fiel:
        return {'state': 'none', 'days': None}
    return {'state': fiel['validity'], 'days': fiel['days_left']}


ACCESS_KINDS = ('VER', 'COPIAR', 'USO_DECLARA')


def summary(db, p, visible, passwords, certs):
    """The four indicators of «Revisión de seguridad», checked locally (nothing is sent outside)."""
    from .credential_models import audit

    complete = [c for c in certs if c['active'] and not c['incomplete']]
    query = select(audit).where(audit.c.kind.in_(ACCESS_KINDS), audit.c.company_id.in_(list(visible)))
    if not p.admin:
        query = query.where(audit.c.actor_id == p.subject)
    last = db.execute(query.order_by(audit.c.created_at.desc()).limit(1)).mappings().first()
    last_access = None
    if last:
        label = db.execute(
            select(credentials.c.label, credentials.c.kind).where(credentials.c.id == last['record_id'])
        ).first()
        actor = db.get(UserAccount, last['actor_id'])
        last_access = {
            'at': last['created_at'],
            'kind': last['kind'],
            'company': visible[last['company_id']].name if last['company_id'] in visible else None,
            'what': (label[1] if label else None),
            'who': actor.display_name if actor else None,
        }
    return {
        'passwords': len(passwords),
        'certificates': len(complete),
        'expiring': sum(1 for c in complete if c['validity'] == 'expiring'),
        'expired': sum(1 for c in complete if c['validity'] == 'expired'),
        'weak_or_repeated': sum(
            1 for i in passwords if i['repeated'] or (i['strength'] is not None and i['strength'] <= 1)
        ),
        'last_access': last_access,
    }


def fold(text):
    text = unicodedata.normalize('NFD', text or '')
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn').casefold()


# ---------------------------------------------------------------- FIEL / CSD / IMSS files


@router.post('/companies/{cid}/secrets/{ident}/files', status_code=410)
def add_file(cid: str, ident: str, p: Principal = Depends(auth)):
    """Retired in fase 3 of the renovación del gestor: a .cer or .key is stored only through «Agregar FIEL o CSD»
    (app/vault_fiel.py), which opens the key with its password and checks that it matches the certificate."""
    raise HTTPException(410, 'Carga la FIEL o el CSD con «Agregar FIEL o CSD»: se validan juntos el .cer y el .key.')


@router.delete('/companies/{cid}/secrets/{ident}/files/{file_id}')
def remove_file(
    cid: str, ident: str, file_id: str, response: Response, p: Principal = Depends(auth), db=Depends(session)
):
    no_cache(response)
    ready(db)
    vault_access(db, p, cid, 'manage')
    gone = db.execute(
        files.delete().where(files.c.id == file_id, files.c.credential_id == ident, files.c.company_id == cid)
    ).rowcount
    if not gone:
        raise HTTPException(404, 'Archivo no encontrado.')
    event(db, p, cid, 'vault_file_removed', ident)
    db.commit()
    return {'removed': True}


# ---------------------------------------------------------------- browser extension tickets


class TicketIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: Literal['sat_password', 'sat_fiel', 'portal_login']
    reason: str = Field('', max_length=200)


@router.post('/companies/{cid}/secrets/{ident}/ticket')
def ticket(
    cid: str, ident: str, payload: TicketIn, response: Response, p: Principal = Depends(auth), db=Depends(session)
):
    """A single-use, 60-second ticket the ContaSuite extension exchanges for the secret to fill the portal.

    The FIEL is never downloaded: the extension receives it in memory for one use and never writes it to disk.
    """
    no_cache(response)
    ready(db)
    vault_access(db, p, cid, 'view')
    row = credential_row(db, cid, ident)
    require_unlocked(db, p, cid, ident)
    if payload.purpose == 'sat_fiel':
        # Fase 3: the .cer and the .key never leave the server; Declara uses them through obtener_fiel_para_acceso.
        raise HTTPException(422, 'La FIEL ya no se entrega a la extensión: el acceso con e.firma lo hará Declara.')
    token = tokens.token_urlsafe(32)
    # The extension has no session: the ticket is exchanged with the data key of the session that issued it.
    vault_session.remember_ticket(hashlib.sha256(token.encode()).hexdigest(), p.session_id, TICKET_SECONDS)
    db.execute(
        tickets.insert().values(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            credential_id=row['id'],
            company_id=cid,
            actor_id=p.subject,
            purpose=payload.purpose,
            expires_at=now() + timedelta(seconds=TICKET_SECONDS),
            used_at=None,
        )
    )
    event(db, p, cid, 'autofill_ticket_issued', ident, {'purpose': payload.purpose, 'reason': payload.reason})
    db.commit()
    return {'ticket': token, 'expires_in': TICKET_SECONDS}


@router.post('/tickets/redeem')
def redeem(payload: dict, response: Response, db=Depends(session)):
    """Exchanged once by the extension (no session: the ticket is the authorization, 256 bits, 60 s)."""
    no_cache(response)
    ready(db)
    token = str(payload.get('ticket', ''))[:100]
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute(select(tickets).where(tickets.c.token_hash == digest)).mappings().first()
    if not row or row['used_at'] or utc(row['expires_at']) < now():
        raise HTTPException(410, 'Boleto vencido o ya usado.')
    if not db.execute(
        update(tickets).where(tickets.c.token_hash == digest, tickets.c.used_at.is_(None)).values(used_at=now())
    ).rowcount:
        raise HTTPException(410, 'Boleto vencido o ya usado.')
    cid, ident = row['company_id'], row['credential_id']
    cred = credential_row(db, cid, ident)
    company = db.get(Company, cid)
    try:
        cipher = vault_session.cipher(vault_session.ticket_session(digest))
        secret = cipher.open(cred['envelope'], cid, ident, authorize_recent=lambda: True)
        # Only the password and the user: the .cer and the .key are never sent over HTTP (fase 3).
        out = {'purpose': row['purpose'], 'rfc': company.rfc, 'username': cred['username'], 'password': secret}
    except VaultLocked:
        db.commit()
        raise HTTPException(423, 'Bóveda bloqueada.') from None
    from types import SimpleNamespace

    event(db, SimpleNamespace(subject=row['actor_id']), cid, 'autofill_used', ident, {'purpose': row['purpose']})
    db.commit()
    return out


# Import, template and export: app/vault_import.py (renovación del gestor, fase 4).
