"""Renovación del gestor de contraseñas, fase 4: import from Excel or CSV in three steps, template and export.

Spec, section 6. Everything happens in memory on the server: the file is never written to disk nor to the database
and the client sends it again at each step (its SHA-256 must not change between the preview and «Aplicar»).
Administrators only, with the vault unlocked.

1. Archivo (`POST /import/read`): .xlsx or .csv (UTF-8 or Latin-1) up to 5 MB. The sheet with an RFC column and at
   least one password column is chosen; the header row is the first one with «RFC».
2. Columnas: headers are recognized without case, accents or spaces (DEFAULT_HEADERS); the person may correct any
   assignment and the mapping is remembered by header signature (`vault_import_templates`).
3. Revisar cambios (`POST /import/preview`): one line per cell with a value and its action. Passwords are never shown:
   only «igual» or «distinta», comparing keyed fingerprints. An import never deletes.
«Aplicar» (`POST /import/apply`) writes every change in one transaction, or none, and logs one IMPORTAR row.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import date, datetime
from uuid import uuid4

from fastapi import Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, update

from .credential_api import active_of, event, no_cache, ready, require_unlocked, router, vault_access
from .credential_crypto import VaultLocked, strength
from .credential_models import (
    KIND_SERVICE,
    certificates,
    credentials,
    files,
    import_templates,
    versions,
)
from .database import session
from .models import Company, now
from .sat_certificates import CertificateError, open_key
from .security import Principal, auth

MAX_FILE = 5 * 1024 * 1024
DESTINATIONS = {
    'rfc': 'RFC (llave para relacionar)',
    'sat': 'Contraseña SAT (CIEC)',
    'fiel_empresa': 'Contraseña de la FIEL de la empresa',
    'fiel_repre': 'Contraseña de la FIEL del representante',
    'csd': 'Contraseña del sello digital (CSD)',
    'infonavit': 'Infonavit',
    'imss': 'IMSS (certificado IDSE)',
    'sipare': 'SIPARE',
    'correo': 'Correo (la dirección va en el usuario)',
    'otro': 'Otra contraseña',
    'registro_patronal': 'Registro patronal (sólo se compara)',
    'empresa': 'Nombre de la empresa (sólo se compara)',
    'ignorar': 'No importar',
}
CREDENTIAL_DEST = {
    'sat': 'SAT_CIEC',
    'infonavit': 'INFONAVIT',
    'imss': 'IMSS_IDSE',
    'sipare': 'SIPARE',
    'correo': 'CORREO',
    'otro': 'OTRO',
}
KEY_DEST = {'fiel_empresa': 'FIEL_EMPRESA', 'fiel_repre': 'FIEL_REPRESENTANTE', 'csd': 'CSD'}
# Format of the office (sheet «CONTRASEÑAS»); keys are headers without case, accents nor spaces.
DEFAULT_HEADERS = {
    'RFC': 'rfc',
    'CONTRASENA': 'sat',
    'FIELEMPRESA': 'fiel_empresa',
    'FIELREPRE': 'fiel_repre',
    'FIELREPRESENTANTE': 'fiel_repre',
    'SELLODIGITAL': 'csd',
    'INFONAVIT': 'infonavit',
    'CONTRASENACERTIFICADOIMSS': 'imss',
    'SIPARE': 'sipare',
    'CORREO': 'correo',
    'REGISTROPATRONAL': 'registro_patronal',
    'EMPRESA': 'empresa',
    'NO': 'ignorar',
    'NIVEL': 'ignorar',
}
TEMPLATE_HEADERS = [
    'NO.',
    'EMPRESA',
    'RFC',
    'REGISTRO PATRONAL',
    'NIVEL',
    'CONTRASEÑA',
    'FIEL EMPRESA',
    'FIEL REPRE',
    'SELLO DIGITAL',
    'INFONAVIT',
    'CONTRASEÑA CERTIFICADO IMSS',
    'SIPARE',
    'CORREO',
]
EMPTY = {'', 'NA', 'N/A', '-', 'SIN'}
RFC_SHAPE = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
ACTION_LABELS = {
    'add': 'Agregar',
    'add_incomplete': 'Agregar (faltan .cer y .key)',
    'update': 'Actualizar',
    'same': 'Sin cambios',
    'empty': 'No se toca',
    'no_password': 'No se toca',
    'review': 'Revisar',
    'decide': 'Necesita tu decisión',
    'skipped': 'Omitida',
}
LABELS = {
    'FIEL_EMPRESA': 'FIEL de la empresa',
    'FIEL_REPRESENTANTE': 'FIEL del representante',
    'CSD': 'Sello digital (CSD)',
}


def key(text):
    text = unicodedata.normalize('NFD', str(text or ''))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn').upper()
    return re.sub(r'[^A-Z0-9]', '', text)


def cell(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value).strip()


# ---------------------------------------------------------------- step 1: file and sheets


def read_file(name, data):
    """{sheet name: rows of text}. Never written anywhere."""
    if not data:
        raise HTTPException(422, 'El archivo está vacío.')
    if len(data) > MAX_FILE:
        raise HTTPException(422, 'El archivo supera 5 MB.')
    ext = (name or '').lower().rsplit('.', 1)[-1]
    if ext == 'xls':
        raise HTTPException(422, 'Los archivos .xls todavía no se leen: guárdalo como .xlsx o .csv desde Excel.')
    if ext == 'csv':
        for encoding in ('utf-8-sig', 'latin-1'):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        return {'CSV': [[cell(v) for v in row] for row in csv.reader(io.StringIO(text), dialect)]}
    if ext not in ('xlsx', 'xlsm'):
        raise HTTPException(422, 'Sube un .xlsx o un .csv.')
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - an unreadable workbook is reported without content
        raise HTTPException(422, 'No se pudo leer el Excel.') from None
    sheets = {
        sheet.title: [[cell(v) for v in row] for row in sheet.iter_rows(values_only=True)] for sheet in book.worksheets
    }
    book.close()
    return sheets


def header_at(rows):
    return next((i for i, row in enumerate(rows[:50]) if any(key(v) == 'RFC' for v in row)), None)


def default_mapping(headers):
    return [DEFAULT_HEADERS.get(key(h), 'ignorar') for h in headers]


def signature(headers):
    return hashlib.sha256('|'.join(key(h) for h in headers).encode()).hexdigest()


def summary(name, rows):
    at = header_at(rows)
    headers = rows[at] if at is not None else []
    mapping = default_mapping(headers)
    return {
        'name': name,
        'header_row': (at + 1) if at is not None else None,
        'headers': headers,
        'rows': max(0, len(rows) - (at + 1)) if at is not None else 0,
        'has_rfc': at is not None,
        'password_columns': sum(1 for d in mapping if d in CREDENTIAL_DEST or d in KEY_DEST),
    }


def choose(sheets):
    infos = [summary(n, r) for n, r in sheets.items()]
    best = next((i for i in infos if i['has_rfc'] and i['password_columns']), None) or next(
        (i for i in infos if i['has_rfc']), None
    )
    return infos, (best or infos[0])['name'] if infos else None


def sheet_rows(sheets, name):
    if name not in sheets:
        raise HTTPException(422, 'Esa hoja no está en el archivo.')
    rows = sheets[name]
    at = header_at(rows)
    if at is None:
        raise HTTPException(422, 'La hoja no tiene una fila de encabezados con «RFC».')
    return rows[at], rows[at + 1 :], at


def check_mapping(headers, mapping):
    if not isinstance(mapping, list) or len(mapping) != len(headers) or any(m not in DESTINATIONS for m in mapping):
        raise HTTPException(422, 'La asignación de columnas no corresponde a la hoja.')
    if mapping.count('rfc') != 1:
        raise HTTPException(422, 'Asigna exactamente una columna como RFC.')


# ---------------------------------------------------------------- step 3: plan of changes


def stored_key(db, cipher, cert):
    row = (
        db.execute(select(files).where(files.c.certificate_id == cert['id'], files.c.file_kind == 'key'))
        .mappings()
        .first()
    )
    if not row:
        return None
    try:
        return cipher.open_bytes(
            row['envelope'], cert['company_id'], 'file:' + row['id'], authorize_recent=lambda: True
        )
    except VaultLocked:
        return None


def fingerprint_of(db, ident):
    return db.execute(select(credentials.c.fingerprint).where(credentials.c.id == ident)).scalar()


def compare_credential(db, cipher, company, kind, label, value):
    if not company:
        return 'add', None
    query = select(credentials).where(
        credentials.c.company_id == company.id, credentials.c.kind == kind, credentials.c.archived.is_(False)
    )
    if kind == 'OTRO':
        query = query.where(credentials.c.label == label)
    existing = list(db.execute(query.order_by(credentials.c.updated_at.desc())).mappings())
    if not existing:
        return 'add', None
    fp = cipher.fingerprint(value)
    if any(r['fingerprint'] == fp for r in existing):
        return 'same', None
    return 'update', existing[0]['id']


def compare_key(db, cipher, company, klass, value):
    """FIEL/CSD password: against the stored .key when there is one, else against the incomplete certificate."""
    if not company:
        return 'add_incomplete', None
    rows = list(
        db.execute(
            select(certificates).where(
                certificates.c.company_id == company.id,
                certificates.c.cert_class == klass,
                certificates.c.active.is_(True),
            )
        ).mappings()
    )
    with_files = [(r, stored_key(db, cipher, r)) for r in rows if r['fingerprint']]
    with_files = [(r, k) for r, k in with_files if k]
    if with_files:
        for row, raw in with_files:
            try:
                open_key(raw, value)
            except CertificateError:
                continue
            same = fingerprint_of(db, row['key_password_id']) == cipher.fingerprint(value)
            return ('same' if same else 'update'), row['key_password_id']
        return 'review', None
    incomplete = next((r for r in rows if not r['fingerprint'] and r['key_password_id']), None)
    if incomplete:
        same = fingerprint_of(db, incomplete['key_password_id']) == cipher.fingerprint(value)
        return ('same' if same else 'update'), incomplete['key_password_id']
    return 'add_incomplete', None


def plan(db, cipher, headers, rows, header_index, mapping, decisions):
    """The changes of the sheet. Lines keep private `_values`/`_target` for «Aplicar»; `public()` strips them."""
    col = {d: mapping.index(d) for d in ('rfc', 'registro_patronal', 'empresa') if d in mapping}
    from .company_lifecycle import normalize_rfc
    from .storage.classifier import valid_rfc

    companies = {normalize_rfc(c.rfc): c for c in db.scalars(select(Company))}
    groups, order, ignored, repeated = {}, [], 0, {}
    for offset, row in enumerate(rows):
        number = header_index + 2 + offset
        rfc = re.sub(r'\s+', '', (row[col['rfc']] if col['rfc'] < len(row) else '')).upper()
        if not RFC_SHAPE.match(rfc):
            if any(v for v in row):
                ignored += 1
            continue
        if rfc in groups:
            repeated.setdefault(rfc, [groups[rfc][0]]).append(number)
        else:
            order.append(rfc)
        groups[rfc] = (number, row)
    notices = []
    if ignored:
        notices.append(f'{ignored} filas sin RFC o con texto suelto se ignoraron.')
    for rfc, numbers in repeated.items():
        notices.append(
            f'El RFC {rfc} se repite en las filas {", ".join(map(str, numbers))}: se usa la última '
            f'(fila {numbers[-1]}) y las demás no se aplican.'
        )
    out = []
    for rfc in order:
        number, row = groups[rfc]

        def value_at(i, row=row):
            return row[i] if i < len(row) else ''

        company = companies.get(normalize_rfc(rfc))
        entry = {
            'rfc': rfc,
            'row': number,
            'company_id': company.id if company else None,
            'name': company.name if company else (value_at(col['empresa']) if 'empresa' in col else '') or rfc,
            'notices': [],
            'decision': None,
            'lines': [],
            'repeated_rows': repeated.get(rfc, [])[:-1],
        }
        create = None
        if not company:
            if not valid_rfc(rfc):
                entry['notices'].append('El RFC no es válido: la fila no se aplica.')
                entry['decision'] = {'id': 'rfc:' + rfc, 'options': [{'id': 'skip', 'label': 'Omitir'}]}
                choice = decisions.get('rfc:' + rfc)
                create = False if choice == 'skip' else None
            else:
                entry['decision'] = {
                    'id': 'rfc:' + rfc,
                    'options': [{'id': 'create', 'label': 'Crear empresa'}, {'id': 'skip', 'label': 'Omitir'}],
                }
                choice = decisions.get('rfc:' + rfc)
                create = {'create': True, 'skip': False}.get(choice)
            entry['decision']['chosen'] = decisions.get('rfc:' + rfc)
        registro = value_at(col['registro_patronal']).strip() if 'registro_patronal' in col else ''
        if registro.upper() in EMPTY:
            registro = ''
        if company and registro and key(registro) != key(company.employer_registration or ''):
            entry['notices'].append(
                'El registro patronal del archivo es distinto al registrado; no se cambia la empresa.'
                if company.employer_registration
                else 'La empresa no tiene registro patronal; el del archivo sólo se usa como usuario de IMSS y SIPARE.'
            )
        name = value_at(col['empresa']).strip() if 'empresa' in col else ''
        if company and name and key(name) != key(company.name):
            entry['notices'].append('El nombre del archivo es distinto al registrado; no se cambia la empresa.')
        for index, dest in enumerate(mapping):
            if dest not in CREDENTIAL_DEST and dest not in KEY_DEST:
                continue
            raw = value_at(index).strip()
            if not raw:
                continue
            header = str(headers[index] or DESTINATIONS[dest])[:100]
            line = {
                'id': f'cell:{number}:{index}',
                'row': number,
                'column': header,
                'destination': dest,
                'destination_label': DESTINATIONS[dest],
                'decision': None,
                'detail': '',
                '_values': [],
            }
            entry['lines'].append(line)
            if raw.upper() in EMPTY:
                line.update(action='empty', detail='vacía')
                continue
            user = None
            parts = [p.strip() for p in raw.split('/') if p.strip()]
            values = [raw]
            if dest == 'correo':
                if len(parts) >= 2 and '@' in parts[0]:
                    user, values = parts[0], ['/'.join(parts[1:]).strip()]
                elif '@' in raw and ' ' not in raw:
                    line.update(action='no_password', detail='sólo trae la dirección')
                    continue
            elif len(parts) >= 2:
                options = [{'id': str(i), 'label': f'Valor {i + 1}'} for i in range(len(parts))]
                options.append({'id': 'all', 'label': 'Guardar todos'})
                chosen = decisions.get(line['id'])
                line['decision'] = {'id': line['id'], 'options': options, 'chosen': chosen, 'count': len(parts)}
                if chosen == 'all':
                    values = parts
                elif chosen is not None and chosen.isdigit() and int(chosen) < len(parts):
                    values = [parts[int(chosen)]]
                else:
                    line.update(action='decide', detail=f'{len(parts)} valores separados por «/»')
                    continue
            if create is False:
                line.update(action='skipped', detail='empresa omitida')
                continue
            actions = []
            for i, value in enumerate(values):
                if dest in KEY_DEST:
                    action, target = compare_key(db, cipher, company, KEY_DEST[dest], value)
                else:
                    kind = CREDENTIAL_DEST[dest]
                    label = header if dest == 'otro' else 'Acceso'
                    if i:
                        label = f'{label} ({i + 1})'
                    action, target = compare_credential(db, cipher, company, kind, label, value)
                    if dest in ('imss', 'sipare') and registro:
                        user = registro
                    if i and action == 'update':
                        action, target = 'add', None  # a second value is a second credential
                line['_values'].append({'value': value, 'action': action, 'target': target, 'user': user, 'index': i})
                actions.append(action)
            # One action per line: the strongest of its values.
            for action in ('review', 'add_incomplete', 'add', 'update', 'same'):
                if action in actions:
                    line['action'] = action
                    break
            line['detail'] = {
                'add': 'nueva',
                'add_incomplete': 'faltan .cer y .key',
                'update': 'distinta',
                'same': 'igual',
                'review': 'no abre la llave guardada',
            }[line['action']]
            if line['action'] == 'review':
                entry['notices'].append(f'«{header}»: la contraseña no abre la llave guardada; no se aplica. Revísala.')
        if not company and create is None:
            for line in entry['lines']:
                if line.get('action') not in ('empty', 'no_password', 'decide'):
                    line['pending_company'] = True
        out.append(entry)
    counts = {'new': 0, 'change': 0, 'unchanged': 0, 'decisions': 0, 'review': 0}
    for entry in out:
        if entry['decision'] and entry['decision'].get('chosen') is None:
            counts['decisions'] += 1
        for line in entry['lines']:
            action = line['action']
            if action in ('add', 'add_incomplete'):
                counts['new'] += 1
            elif action == 'update':
                counts['change'] += 1
            elif action in ('same', 'empty', 'no_password'):
                counts['unchanged'] += 1
            elif action == 'decide':
                counts['decisions'] += 1
            elif action == 'review':
                counts['review'] += 1
    return {'companies': out, 'counts': counts, 'ignored_rows': ignored, 'notices': notices}


def public(result):
    """Never a password: lines carry only the action and «igual» / «distinta»."""
    companies = []
    for entry in result['companies']:
        lines = [
            {
                **{k: v for k, v in line.items() if not k.startswith('_')},
                'action_label': ACTION_LABELS[line['action']],
                'masked': '••••••',
            }
            for line in entry['lines']
        ]
        companies.append({**entry, 'lines': lines})
    return {**result, 'companies': companies}


# ---------------------------------------------------------------- endpoints


async def load(file):
    name = (file.filename or 'archivo').strip()[:200]
    data = await file.read(MAX_FILE + 1)
    await file.close()
    return name, data


def guard(db, p):
    vault_access(db, p, None, 'manage')
    return require_unlocked(db, p, None, None)


def template_for(db, headers):
    row = (
        db.execute(select(import_templates).where(import_templates.c.header_signature == signature(headers)))
        .mappings()
        .first()
    )
    if row and isinstance(row['mapping'], list) and len(row['mapping']) == len(headers):
        return row
    return None


@router.post('/import/read')
async def import_read(
    response: Response, file: UploadFile = File(...), p: Principal = Depends(auth), db=Depends(session)
):
    """Step 1 and 2: sheets of the file, the chosen sheet and the suggested (or remembered) mapping."""
    no_cache(response)
    ready(db)
    guard(db, p)
    name, data = await load(file)
    sheets = read_file(name, data)
    del data
    infos, chosen = choose(sheets)
    out = {'file_name': name, 'sheets': infos, 'sheet': chosen, 'destinations': DESTINATIONS, 'template': None}
    for info in infos:
        remembered = template_for(db, info['headers']) if info['headers'] else None
        info['mapping'] = remembered['mapping'] if remembered else default_mapping(info['headers'])
        info['template'] = remembered['name'] if remembered else None
    return out


def parsed(form_mapping, form_decisions):
    try:
        mapping = json.loads(form_mapping)
        decisions = json.loads(form_decisions or '{}')
    except ValueError:
        raise HTTPException(422, 'Asignación o decisiones mal formadas.') from None
    if not isinstance(decisions, dict):
        raise HTTPException(422, 'Decisiones mal formadas.')
    return mapping, {str(k): str(v) for k, v in decisions.items()}


@router.post('/import/preview')
async def import_preview(
    response: Response,
    file: UploadFile = File(...),
    sheet: str = Form(...),
    mapping: str = Form(...),
    decisions: str = Form('{}'),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """Step 3: every change, with no password. Nothing is stored."""
    no_cache(response)
    ready(db)
    cipher = guard(db, p)
    name, data = await load(file)
    digest = hashlib.sha256(data).hexdigest()
    headers, rows, at = sheet_rows(read_file(name, data), sheet)
    del data
    columns, chosen = parsed(mapping, decisions)
    check_mapping(headers, columns)
    result = plan(db, cipher, headers, rows, at, columns, chosen)
    event(db, p, None, 'vault_import_previewed', details={'file': name, 'counts': result['counts']})
    db.commit()
    return {'sha256': digest, 'file_name': name, **public(result)}


def create_company(db, p, entry):
    from .company_lifecycle import ensure_unique_rfc
    from .main import record

    ensure_unique_rfc(db, entry['rfc'])
    physical = len(entry['rfc']) == 13
    company = Company(
        id=str(uuid4()),
        name=(entry['name'] or entry['rfc'])[:220],
        rfc=entry['rfc'],
        person_type='Física' if physical else 'Moral',
        regime='612 - Personas Físicas con Actividades Empresariales y Profesionales'
        if physical
        else '601 - General de Ley Personas Morales',
    )
    db.add(company)
    db.flush()
    record(db, 'Empresa registrada', company.id, p.subject)
    return company


def write_credential(db, p, cipher, company, kind, label, item):
    from .credential_api import default_username

    value = item['value']
    envelope_id = item['target'] or str(uuid4())
    envelope = cipher.seal(value, company.id, envelope_id)
    values = dict(
        envelope=envelope,
        updated_at=now(),
        updated_by=p.subject,
        strength=strength(value, company.rfc),
        fingerprint=cipher.fingerprint(value),
    )
    if item['target']:
        revision = db.execute(select(credentials.c.revision).where(credentials.c.id == envelope_id)).scalar() + 1
        db.execute(update(credentials).where(credentials.c.id == envelope_id).values(revision=revision, **values))
    else:
        revision = 1
        db.execute(
            credentials.insert().values(
                id=envelope_id,
                company_id=company.id,
                service_id=KIND_SERVICE.get(kind, 'other'),
                label=label,
                revision=1,
                archived=False,
                created_at=now(),
                username=item['user'] or default_username(company, kind),
                kind=kind,
                requires_review=False,
                extra={},
                **values,
            )
        )
    # The previous value stays in the history of the record.
    db.execute(
        versions.insert().values(
            credential_id=envelope_id, revision=revision, envelope=envelope, actor_id=p.subject, created_at=now()
        )
    )
    return envelope_id


def write_incomplete(db, p, cipher, company, klass, item):
    """A FIEL/CSD password without files: its credential and a certificate «Faltan .cer y .key»."""
    holder = 'legal_rep' if klass == 'FIEL_REPRESENTANTE' else 'company'
    item = {**item, 'target': None}
    ident = write_credential(db, p, cipher, company, 'LLAVE', LABELS[klass], item)
    db.execute(
        update(credentials)
        .where(credentials.c.id == ident)
        .values(service_id='csd_password' if klass == 'CSD' else 'fiel_password', holder=holder, username=None)
    )
    db.execute(
        certificates.insert().values(
            id=str(uuid4()),
            company_id=company.id,
            kind='csd' if klass == 'CSD' else 'fiel',
            rfc=company.rfc,
            holder=holder,
            cert_class=klass,
            holder_rfc=None if klass == 'FIEL_REPRESENTANTE' else company.rfc,
            active=not active_of(db, company.id, klass),
            key_password_id=ident,
            origin='import',
            reviewed_at=now(),
            notes='Faltan .cer y .key',
            revision=1,
        )
    )


@router.post('/import/apply')
async def import_apply(
    response: Response,
    file: UploadFile = File(...),
    sheet: str = Form(...),
    mapping: str = Form(...),
    decisions: str = Form('{}'),
    sha256: str = Form(...),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """«Aplicar N cambios»: everything in one transaction, or nothing."""
    no_cache(response)
    ready(db)
    cipher = guard(db, p)
    name, data = await load(file)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(409, 'El archivo cambió desde la vista previa.')
    headers, rows, at = sheet_rows(read_file(name, data), sheet)
    del data
    columns, chosen = parsed(mapping, decisions)
    check_mapping(headers, columns)
    result = plan(db, cipher, headers, rows, at, columns, chosen)
    if result['counts']['decisions']:
        raise HTTPException(409, 'Hay decisiones pendientes: elige qué hacer con cada una antes de aplicar.')
    applied = {'new': 0, 'change': 0, 'companies_created': 0}
    try:
        for entry in result['companies']:
            choice = (entry['decision'] or {}).get('chosen')
            if choice == 'skip':
                continue
            company = db.get(Company, entry['company_id']) if entry['company_id'] else None
            if company is None and choice == 'create':
                company = create_company(db, p, entry)
                applied['companies_created'] += 1
            if company is None:
                continue
            for line in entry['lines']:
                for item in line['_values']:
                    if item['action'] in ('same', 'review'):
                        continue
                    dest = line['destination']
                    if dest in KEY_DEST:
                        if item['action'] == 'add_incomplete':
                            write_incomplete(db, p, cipher, company, KEY_DEST[dest], item)
                        else:
                            write_credential(db, p, cipher, company, 'LLAVE', '', item)
                    else:
                        label = line['column'] if dest == 'otro' else 'Acceso'
                        if item['index']:
                            label = f'{label} ({item["index"] + 1})'
                        write_credential(db, p, cipher, company, CREDENTIAL_DEST[dest], label[:100], item)
                    applied['change' if item['action'] == 'update' else 'new'] += 1
        stored = template_for(db, headers)
        if stored:
            db.execute(
                update(import_templates)
                .where(import_templates.c.id == stored['id'])
                .values(mapping=columns, name=name, updated_at=now(), updated_by=p.subject)
            )
        else:
            db.execute(
                import_templates.insert().values(
                    id=str(uuid4()),
                    name=name,
                    header_signature=signature(headers),
                    mapping=columns,
                    updated_at=now(),
                    updated_by=p.subject,
                )
            )
        event(db, p, None, 'vault_imported', details={'file': name, 'counts': applied})
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:  # noqa: BLE001 - all or nothing; nothing of the file is echoed
        db.rollback()
        raise HTTPException(409, 'No se aplicó ningún cambio: la importación falló a la mitad.') from None
    return {
        **applied,
        'message': 'Listo. Te recomendamos borrar el Excel de tu equipo porque tiene las contraseñas sin cifrar.',
    }


# ---------------------------------------------------------------- template and export


def workbook(rows):
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = 'CONTRASEÑAS'
    sheet.append(TEMPLATE_HEADERS)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    out.seek(0)
    return out


def xlsx(out, filename):
    return StreamingResponse(
        out,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store, private'},
    )


@router.get('/import/template')
def import_template(response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """«Descargar plantilla de Excel»: the headers of the office format, with no data."""
    ready(db)
    vault_access(db, p, None, 'manage')
    return xlsx(workbook([]), 'plantilla_contrasenas_contasuite.xlsx')


class ExportIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    company_ids: list[str] = Field(default_factory=list, max_length=500)
    reason: str = Field(min_length=3, max_length=200)
    password: SecretStr = Field(max_length=256)


@router.post('/export')
def export(payload: ExportIn, response: Response, p: Principal = Depends(auth), db=Depends(session)):
    """Administrators, with the vault unlocked and the master password typed again: the same format as the template,
    with the passwords in clear. The screen warns to protect and delete the file."""
    from .vault_master import check_own

    no_cache(response)
    ready(db)
    vault_access(db, p, None, 'manage')
    cipher = require_unlocked(db, p, None, None)
    check_own(db, p, payload.password.get_secret_value())
    query = select(Company).order_by(Company.name)
    if payload.company_ids:
        query = query.where(Company.id.in_(payload.company_ids))
    by_kind = {
        'SAT_CIEC': 'CONTRASEÑA',
        'INFONAVIT': 'INFONAVIT',
        'IMSS_IDSE': 'CONTRASEÑA CERTIFICADO IMSS',
        'SIPARE': 'SIPARE',
    }
    rows, count = [], 0
    for n, company in enumerate(db.scalars(query), start=1):
        values = dict.fromkeys(TEMPLATE_HEADERS, '')
        values.update({'NO.': n, 'EMPRESA': company.name, 'RFC': company.rfc})
        values['REGISTRO PATRONAL'] = company.employer_registration or ''
        creds = list(
            db.execute(
                select(credentials)
                .where(credentials.c.company_id == company.id, credentials.c.archived.is_(False))
                .order_by(credentials.c.updated_at.desc())
            ).mappings()
        )

        def secret(row, company=company):
            return cipher.open(row['envelope'], company.id, row['id'], authorize_recent=lambda: True)

        for kind, header in by_kind.items():
            row = next((r for r in creds if r['kind'] == kind), None)
            if row:
                values[header] = secret(row)
                count += 1
        mail = next((r for r in creds if r['kind'] == 'CORREO'), None)
        if mail:
            values['CORREO'] = f'{mail["username"]} / {secret(mail)}' if mail['username'] else secret(mail)
            count += 1
        for klass, header in (
            ('FIEL_EMPRESA', 'FIEL EMPRESA'),
            ('FIEL_REPRESENTANTE', 'FIEL REPRE'),
            ('CSD', 'SELLO DIGITAL'),
        ):
            cert = db.execute(
                select(certificates.c.key_password_id).where(
                    certificates.c.company_id == company.id,
                    certificates.c.cert_class == klass,
                    certificates.c.active.is_(True),
                    certificates.c.key_password_id.is_not(None),
                )
            ).first()
            row = next((r for r in creds if cert and r['id'] == cert[0]), None)
            if row:
                values[header] = secret(row)
                count += 1
        rows.append([values[h] for h in TEMPLATE_HEADERS])
    out = workbook(rows)
    event(db, p, None, 'vault_exported', details={'count': count, 'reason': payload.reason})
    db.commit()
    return xlsx(out, 'contrasenas_contasuite.xlsx')
