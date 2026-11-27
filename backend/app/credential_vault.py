"""Plan v1.1, Cambio 4: password manager on the existing vault (same router, tables and log).

- Revealing, copying, using, importing or exporting a secret needs the vault unlocked in this session with the
  master password (app/vault_master.py; the data key lives only in server memory, app/vault_session.py).
- List by company and portal with search; user visible, password hidden; strength and repetition checked
  locally (no breach service).
- FIEL/CSD/IMSS files encrypted outside the document folders, never indexed by CS-Storage nor sent to the agent,
  never downloaded: the browser extension uses them through a single-use ticket.
- Import of the office's two Excel formats with a preview that never shows secrets; the file stays in memory.
- Export only for administrators, with re-authentication; every action goes to the vault log.
"""

import base64
import hashlib
import io
import re
import secrets as tokens
import unicodedata
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from fastapi import Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .credential_api import (
    activate,
    attached_files,
    credential_row,
    event,
    no_cache,
    public_credential,
    ready,
    repeated_fingerprints,
    require_unlocked,
    still_valid,
    router,
    vault_access,
)
from . import vault_session
from .credential_crypto import VaultLocked, strength
from .credential_models import cert_class, certificates, credentials, files, services, tickets, versions
from .database import session
from .models import Company, now
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
    items = []
    for r in db.execute(
        select(credentials).where(credentials.c.company_id.in_(list(visible)), credentials.c.archived.is_(False))
    ).mappings():
        c = visible[r['company_id']]
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
    return {
        'items': items,
        'services': [{'id': k, 'label': v} for k, v in sorted(labels.items(), key=lambda kv: kv[1])],
        'companies': [{'id': c.id, 'name': c.name, 'rfc': c.rfc, 'can_create': p.admin} for c in visible.values()],
        'health': {
            'weak': sum(1 for i in items if i['strength'] is not None and i['strength'] <= 1),
            'repeated': sum(1 for i in items if i['repeated']),
            'unknown': sum(1 for i in items if i['strength'] is None),
        },
        'vault_unlocked': vault_unlocked(p),
        'can_export': p.admin,
    }


def fold(text):
    text = unicodedata.normalize('NFD', text or '')
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn').casefold()


# ---------------------------------------------------------------- FIEL / CSD / IMSS files


@router.post('/companies/{cid}/secrets/{ident}/files', status_code=201)
async def add_file(
    cid: str,
    ident: str,
    response: Response,
    file: UploadFile = File(...),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """Encrypt a .cer or .key of the credential (FIEL, CSD, IMSS certificate). The .cer also feeds the dates of
    the traffic light (public certificate; never an SAT validation). Nothing is written to document folders."""
    from .credential_api import parse_public_certificate

    no_cache(response)
    ready(db)
    vault_access(db, p, cid, 'manage')
    row = credential_row(db, cid, ident)
    if row['service_id'] not in ('fiel', 'csd', 'imss_certificate', 'fiel_password', 'csd_password'):
        raise HTTPException(422, 'Sólo FIEL, CSD o certificado IMSS llevan archivos.')
    name = (file.filename or '').strip()
    kind = name.lower().rsplit('.', 1)[-1] if '.' in name else ''
    if kind not in ('cer', 'key'):
        raise HTTPException(422, 'Carga el archivo .cer o .key.')
    data = await file.read(MAX_FILE + 1)
    await file.close()
    if not data or len(data) > MAX_FILE:
        raise HTTPException(422, 'Archivo vacío o demasiado grande.')
    holder = row['holder'] or 'company'
    certificate_id = None
    if kind == 'cer':
        parsed = parse_public_certificate(data)
        company = db.get(Company, cid)
        if holder == 'company':
            from .storage.classifier import RFC, valid_rfc

            rfcs = {r for r in RFC.findall(parsed['subject'].upper()) if valid_rfc(r)}
            if rfcs and company.rfc not in rfcs:
                raise HTTPException(422, 'El RFC del certificado no coincide con la empresa.')
        cert_kind = 'csd' if row['service_id'] in ('csd', 'csd_password') else 'fiel'
        klass = cert_class(cert_kind, holder)
        existing = db.execute(
            select(certificates.c.id).where(
                certificates.c.company_id == cid,
                certificates.c.fingerprint == parsed['fingerprint'],
                certificates.c.kind == cert_kind,
            )
        ).first()
        # Fase 2: the incomplete certificate of this credential («Faltan .cer y .key») receives the .cer.
        incomplete = db.execute(
            select(certificates.c.id).where(
                certificates.c.key_password_id == ident, certificates.c.fingerprint.is_(None)
            )
        ).first()
        if existing:
            certificate_id = existing[0]
        elif incomplete:
            certificate_id = incomplete[0]
            db.execute(update(certificates).where(certificates.c.id == certificate_id).values(notes='', **parsed))
        else:
            certificate_id = str(uuid4())
            db.execute(
                certificates.insert().values(
                    id=certificate_id,
                    company_id=cid,
                    rfc=company.rfc,
                    kind=cert_kind,
                    document_id=None,
                    origin='vault',
                    reviewed_at=now(),
                    notes='',
                    revision=1,
                    holder=holder,
                    cert_class=klass,
                    holder_rfc=company.rfc if klass in ('FIEL_EMPRESA', 'CSD') else None,
                    active=False,
                    key_password_id=ident,
                    **parsed,
                )
            )
        if not existing:
            # Uploading a .cer to the FIEL credential replaces the active one; an expired one stays as history.
            if still_valid(parsed):
                activate(db, cid, certificate_id, klass)
            else:
                db.execute(update(certificates).where(certificates.c.id == certificate_id).values(active=False))
    elif data.lstrip().startswith(b'-----BEGIN') is False and data[:1] != b'\x30':
        raise HTTPException(422, 'No parece una llave privada .key del SAT.')
    file_id = str(uuid4())
    envelope = require_unlocked(db, p, cid, ident).seal_bytes(data, cid, 'file:' + file_id)
    db.execute(files.delete().where(files.c.credential_id == ident, files.c.file_kind == kind))
    db.execute(
        files.insert().values(
            id=file_id,
            company_id=cid,
            credential_id=ident,
            file_kind=kind,
            file_name=name[:255],
            envelope=envelope,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
            certificate_id=certificate_id,
            actor_id=p.subject,
            created_at=now(),
        )
    )
    event(db, p, cid, 'vault_file_stored', ident, {'kind': kind})
    db.commit()
    del data
    return {'id': file_id, 'kind': kind, 'certificate_id': certificate_id, 'authority_validated': False}


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
        kinds = {r[0] for r in db.execute(select(files.c.file_kind).where(files.c.credential_id == ident))}
        if not {'cer', 'key'} <= kinds:
            raise HTTPException(422, 'La FIEL necesita su .cer y su .key en el gestor.')
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
        out = {'purpose': row['purpose'], 'rfc': company.rfc, 'username': cred['username'], 'password': secret}
        if row['purpose'] == 'sat_fiel':
            for f in db.execute(select(files).where(files.c.credential_id == ident)).mappings():
                raw = cipher.open_bytes(f['envelope'], cid, 'file:' + f['id'], authorize_recent=lambda: True)
                out[f['file_kind']] = {'name': f['file_name'], 'data': base64.b64encode(raw).decode()}
    except VaultLocked:
        db.commit()
        raise HTTPException(423, 'Bóveda bloqueada.') from None
    from types import SimpleNamespace

    event(db, SimpleNamespace(subject=row['actor_id']), cid, 'autofill_used', ident, {'purpose': row['purpose']})
    db.commit()
    return out


# ---------------------------------------------------------------- import of the office's Excel files

# Header words → destination. Checked in order; the first match wins.
HEADER_RULES = [
    ('ignore', (r'^NO\.?$', r'^NUM', r'^NIVEL', r'VENCIMIENTO', r'FECHA', r'INICIAL', r'^FINAL')),
    ('rfc', (r'^RFC$', r'^R\.?F\.?C')),
    ('company', (r'^EMPRESA', r'^RAZON SOCIAL', r'^CONTRIBUYENTE', r'^NOMBRE$')),
    ('regime', (r'REGIMEN',)),
    ('employer_registration', (r'REG\.? ?PATRONAL', r'REGISTRO PATRONAL')),
    ('business_activity', (r'^GIRO',)),
    ('repse', (r'REPSE',)),
    ('workers', (r'TRABAJADORES',)),
    ('bank', (r'^BANCO',)),
    ('legal_representative', (r'REPRESENTANTE LEGAL', r'^REPRESENTANTE$')),
    ('observations', (r'OBSERVACION',)),
    ('fiel_legal_rep', (r'FIEL.*REPRESENTANTE',)),
    ('fiel', (r'FIEL',)),
    ('csd', (r'SELLO', r'\bCSD\b')),
    ('imss_certificate', (r'CERTIFICADO.*IMSS', r'IMSS.*CERTIFICADO')),
    ('idse', (r'IDSE',)),
    ('sipare', (r'SIPARE',)),
    ('infonavit', (r'INFONAVIT',)),
    ('state_isn', (r'NOMINA', r'\bISN\b')),
    ('email', (r'CORREO', r'E-?MAIL')),
    ('fel', (r'\bFEL\b', r'FACTURACION')),
    ('sat_password', (r'^CONTRASENA$', r'CONTRASENA SAT', r'CIEC', r'^CLAVE$')),
]
PORTAL_OF = {
    'sat_password': ('sat_password', None),
    'fiel': ('fiel', 'company'),
    'fiel_legal_rep': ('fiel', 'legal_rep'),
    'csd': ('csd', 'company'),
    'imss_certificate': ('imss_certificate', None),
    'idse': ('idse', None),
    'sipare': ('sipare', None),
    'infonavit': ('infonavit', None),
    'state_isn': ('state_isn', None),
    'email': ('email', None),
    'fel': ('fel', None),
}
COMPANY_FIELDS = ('employer_registration', 'business_activity', 'repse', 'workers', 'bank', 'legal_representative')
OTHER_WORDS = (r'CREDITO', r'IZZI', r'CONTPAQ', r'BANCA', r'PORTAL')


def header_role(text):
    t = re.sub(r'\s+', ' ', fold(text).upper()).strip()
    t = t.replace('Ñ', 'N')
    if not t:
        return None
    for role, patterns in HEADER_RULES:
        if any(re.search(p, t) for p in patterns):
            return role
    if any(re.search(p, t) for p in OTHER_WORDS):
        return 'other'
    if 'CONTRASENA' in t or 'PASSWORD' in t or 'USUARIO' in t:
        return 'other'
    return None


def split_pair(value):
    """«usuario / contraseña» → (user, password); a «(comment)» after the value goes to the notes."""
    text = str(value).strip()
    note = None
    m = re.fullmatch(r'(\S+)\s+\((.{1,200})\)', text)
    if m:
        text, note = m.group(1), m.group(2)
    if ' / ' in text:
        user, password = text.split(' / ', 1)
        return user.strip() or None, password.strip() or None, note
    return None, text or None, note


def read_book(data):
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - any unreadable workbook is reported without content
        raise HTTPException(422, 'No se pudo leer el Excel.') from None
    sheets = {}
    for sheet in book.worksheets:
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        sheets[sheet.title] = rows
    book.close()
    return sheets


def parse_sheet(rows):
    """Rows of one sheet as {rfc, company, fields:{...}, entries:[...]} using its header row."""
    head_at = next((i for i, r in enumerate(rows[:15]) if any(header_role(str(c or '')) == 'rfc' for c in r)), None)
    if head_at is None:
        return []
    header = rows[head_at]
    # A second header row (user / password under a merged portal title) is detected by its words.
    sub = rows[head_at + 1] if head_at + 1 < len(rows) else []
    # Only a row of bare titles («Usuario», «Contraseña», «Correo») counts; a data row never has an RFC value.
    words = [fold(str(c or '')).upper().replace('Ñ', 'N').strip(' .:') for c in sub]
    has_sub = any(w in ('USUARIO', 'CONTRASENA', 'CORREO', 'PASSWORD') for w in words) and not any(
        re.fullmatch(r'[A-Z&N]{3,4}\d{6}[A-Z0-9]{3}', w) for w in words
    )
    roles, last = [], None
    for i, cell in enumerate(header):
        role = header_role(str(cell or ''))
        label = str(cell or '').strip()
        part = None
        if role is None and last and last[0] in PORTAL_OF | {'other': None}:
            role, label = last  # second column of a merged portal title
        if has_sub and i < len(sub) and role in set(PORTAL_OF) | {'other'}:
            word = fold(str(sub[i] or '')).upper()
            part = 'user' if 'USUARIO' in word or 'CORREO' in word else 'password' if word else None
        roles.append((role, label, part))
        if role is not None and role != 'ignore':
            last = (role, label)
        elif role == 'ignore':
            last = None
    out = []
    for number, row in enumerate(rows[head_at + (2 if has_sub else 1) :], start=head_at + (3 if has_sub else 2)):
        record = {'row': number, 'rfc': None, 'company': None, 'regime': None, 'fields': {}, 'entries': {}}
        for (role, label, part), value in zip(roles, row, strict=False):
            if value is None or str(value).strip() == '' or role in (None, 'ignore'):
                continue
            text = str(value).strip()
            if role == 'rfc':
                record['rfc'] = re.sub(r'\s+', '', text).upper()[:13]
            elif role == 'company':
                record['company'] = text[:220]
            elif role == 'regime':
                record['regime'] = text[:100]
            elif role in COMPANY_FIELDS:
                record['fields'][role] = text[:200]
            elif role == 'observations':
                record['fields']['observations'] = text[:500]
            else:
                key = (role, label if role == 'other' else '')
                entry = record['entries'].setdefault(key, {'user': None, 'password': None, 'notes': []})
                if part == 'user':
                    entry['user'] = text[:200]
                elif part == 'password':
                    entry['password'] = text
                else:
                    user, password, note = split_pair(text)
                    entry['user'] = entry['user'] or user
                    entry['password'] = password if entry['password'] is None else entry['password']
                    if note:
                        entry['notes'].append(note)
        if record['rfc'] or record['entries'] or record['fields']:
            out.append(record)
    return out


def parse_workbook(data):
    """One sheet per office, or EMPRESAS + CONTRASEÑAS per corporate group joined by RFC."""
    sheets = read_book(data)
    merged = {}
    order = []
    for title, rows in sheets.items():
        for rec in parse_sheet(rows):
            key = rec['rfc'] or f'{title}:{rec["row"]}'
            if key not in merged:
                merged[key] = {**rec, 'sheets': [title]}
                order.append(key)
            else:
                target = merged[key]
                target['sheets'].append(title)
                target['company'] = target['company'] or rec['company']
                target['regime'] = target['regime'] or rec['regime']
                target['fields'].update({k: v for k, v in rec['fields'].items() if k not in target['fields']})
                for k, v in rec['entries'].items():
                    target['entries'].setdefault(k, v)
    return [merged[k] for k in order]


def plan_import(db, records):
    companies = {c.rfc.upper(): c for c in db.scalars(select(Company))}
    labels = dict(db.execute(select(services.c.id, services.c.label)).all())
    out = []
    for rec in records:
        company = companies.get(rec['rfc'] or '')
        issues = []
        if not rec['rfc']:
            issues.append('Fila sin RFC: queda para revisión.')
        elif not company:
            issues.append('No hay una empresa con este RFC: queda para revisión (no se crea ni se fusiona).')
        if company and rec['regime'] and fold(rec['regime'])[:6] not in fold(company.regime or ''):
            issues.append('El régimen del Excel es sólo referencia; el oficial sale de la CSF.')
        entries = []
        for (role, label), e in rec['entries'].items():
            service, holder = PORTAL_OF.get(role, ('other', None))
            entries.append(
                {
                    'service_id': service,
                    'portal': labels.get(service, service) if role != 'other' else (label or 'Otro'),
                    'label': label if role == 'other' else 'Acceso',
                    'holder': holder,
                    'has_user': bool(e['user']),
                    'has_password': bool(e['password']),
                    'has_notes': bool(e['notes']),
                }
            )
        out.append(
            {
                'row': rec['row'],
                'sheets': rec['sheets'],
                'rfc': rec['rfc'],
                'company_name': rec['company'],
                'company_id': company.id if company else None,
                'matched_name': company.name if company else None,
                'company_fields': sorted(k for k in rec['fields'] if k != 'observations'),
                'entries': entries,
                'issues': issues,
                'importable': bool(company) and bool(entries or rec['fields']),
            }
        )
    return out


@router.post('/import/preview')
async def import_preview(
    response: Response, file: UploadFile = File(...), p: Principal = Depends(auth), db=Depends(session)
):
    """What the Excel would create, company by company: «present / empty», never the passwords."""
    no_cache(response)
    ready(db)
    p.require_admin()
    require_unlocked(db, p, None, None)
    data = await file.read(MAX_XLSX + 1)
    await file.close()
    if len(data) > MAX_XLSX:
        raise HTTPException(422, 'El archivo supera 5 MB.')
    rows = plan_import(db, parse_workbook(data))
    digest = hashlib.sha256(data).hexdigest()
    del data
    event(db, p, None, 'vault_import_previewed', details={'rows': len(rows)})
    db.commit()
    return {'sha256': digest, 'rows': rows}


@router.post('/import/confirm')
async def import_confirm(
    response: Response,
    file: UploadFile = File(...),
    sha256: str = Form(...),
    rows: str = Form(...),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """Store the chosen rows. Same file as the preview; existing credentials of the same portal are kept
    (reported, not overwritten); company data only fills empty fields. The file is discarded afterwards."""
    no_cache(response)
    ready(db)
    p.require_admin()
    data = await file.read(MAX_XLSX + 1)
    await file.close()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(409, 'El archivo cambió desde la vista previa.')
    chosen = {int(r) for r in rows.split(',') if r.strip().isdigit()}
    records = [r for r in parse_workbook(data) if r['row'] in chosen]
    del data
    cipher = require_unlocked(db, p, None, None)
    companies = {c.rfc.upper(): c for c in db.scalars(select(Company))}
    existing = {
        (r['company_id'], r['service_id'], r['holder'] or '', r['label'] or '')
        for r in db.execute(select(credentials).where(credentials.c.archived.is_(False))).mappings()
    }
    known_services = {r[0] for r in db.execute(select(services.c.id))}
    created = kept = skipped = filled = 0
    for rec in records:
        company = companies.get(rec['rfc'] or '')
        if not company:
            skipped += 1
            continue
        for key, value in rec['fields'].items():
            if key == 'observations':
                continue
            if key == 'workers':
                digits = re.sub(r'\D', '', value)
                value = int(digits) if digits else None
            elif key == 'repse':
                value = fold(value).upper().startswith('S')
            if value not in (None, '') and getattr(company, key) in (None, ''):
                setattr(company, key, value)
                filled += 1
        for (role, label), e in rec['entries'].items():
            service, holder = PORTAL_OF.get(role, ('other', None))
            if service not in known_services:
                service = 'other'
            name = (label if role == 'other' else 'Acceso')[:100] or 'Acceso'
            signature = (company.id, service, holder or '', name)
            if signature in existing:
                kept += 1
                continue
            if not e['password']:
                skipped += 1
                continue
            ident = str(uuid4())
            envelope = cipher.seal(e['password'], company.id, ident)
            db.execute(
                credentials.insert().values(
                    id=ident,
                    company_id=company.id,
                    service_id=service,
                    label=name,
                    envelope=envelope,
                    revision=1,
                    archived=False,
                    created_at=now(),
                    updated_at=now(),
                    username=e['user'],
                    notes='; '.join(e['notes'])[:2000] or None,
                    extra={},
                    holder=holder,
                    strength=strength(e['password'], company.rfc),
                    fingerprint=cipher.fingerprint(e['password']),
                )
            )
            db.execute(
                versions.insert().values(
                    credential_id=ident, revision=1, envelope=envelope, actor_id=p.subject, created_at=now()
                )
            )
            existing.add(signature)
            created += 1
        event(db, p, company.id, 'vault_imported', details={'row': rec['row']})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Importación concurrente; vuelve a intentarlo.') from None
    return {'created': created, 'kept_existing': kept, 'skipped': skipped, 'company_fields_filled': filled}


# ---------------------------------------------------------------- export


class ExportIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    company_ids: list[str] = Field(default_factory=list, max_length=500)
    reason: str = Field(min_length=3, max_length=200)


@router.post('/export')
def export(payload: ExportIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """Administrators only, with the vault unlocked and a reason: an Excel with the passwords in clear. The
    screen warns that the file must be protected and deleted after use."""
    no_cache(response)
    ready(db)
    p.require_admin()
    cipher = require_unlocked(db, p, None, None)
    from openpyxl import Workbook

    labels = dict(db.execute(select(services.c.id, services.c.label)).all())
    query = select(credentials, Company.name, Company.rfc).join(Company, Company.id == credentials.c.company_id)
    query = query.where(credentials.c.archived.is_(False))
    if payload.company_ids:
        query = query.where(credentials.c.company_id.in_(payload.company_ids))
    book = Workbook()
    sheet = book.active
    sheet.title = 'Contraseñas'
    sheet.append(['Empresa', 'RFC', 'Portal', 'Nombre', 'Titular', 'Usuario', 'Contraseña', 'Dirección', 'Notas'])
    count = 0
    for r in db.execute(query.order_by(Company.name)).mappings():
        secret = cipher.open(r['envelope'], r['company_id'], r['id'], authorize_recent=lambda: True)
        sheet.append(
            [
                r['name'],
                r['rfc'],
                labels.get(r['service_id'], r['service_id']),
                r['label'],
                {'legal_rep': 'Representante legal', 'company': 'Empresa'}.get(r['holder'] or '', ''),
                r['username'] or '',
                secret,
                r['url'] or '',
                r['notes'] or '',
            ]
        )
        count += 1
    out = io.BytesIO()
    book.save(out)
    out.seek(0)
    event(db, p, None, 'vault_exported', details={'count': count, 'reason': payload.reason})
    db.commit()
    return StreamingResponse(
        out,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': 'attachment; filename="contrasenas_contasuite.xlsx"',
            'Cache-Control': 'no-store, private',
        },
    )
