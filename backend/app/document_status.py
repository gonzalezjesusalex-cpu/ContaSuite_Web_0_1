"""Plan v1.1, Cambio 1: document traffic light per company and summary cards.

Five indicators: FIEL (public CER dates, never an SAT validation), CSF (issue date), SAT opinion, Infonavit and
IMSS opinion. Colors use the office's validity (document_validity), not the official one, which is stored as
printed. A negative opinion or one with debt is red even when recent. «No aplica» (IMSS, Infonavit) is a person's
decision, proposed when the documents report 0 workers. Capture follows the CSF flow of Bloque 1: the PDF is read,
the person confirms or corrects, then the document is saved to the company file and the reading recorded.
"""

import json
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .database import session
from .integral_models import document_settings, document_validity, opinions
from .models import Audit, Company, now
from .schema_cache import has_table
from .security import Principal, auth

router = APIRouter(prefix='/api/integral', tags=['Semáforo documental'])
KINDS = ['fiel', 'csf', 'sat', 'infonavit', 'imss']
LABELS = {
    'fiel': 'Vigencia de la FIEL',
    'csf': 'Constancia de Situación Fiscal',
    'sat': 'Opinión de cumplimiento SAT',
    'infonavit': 'Infonavit',
    'imss': 'Opinión de cumplimiento IMSS',
}
AUTHORITY = {'sat': 'SAT', 'imss': 'IMSS', 'infonavit': 'INFONAVIT'}
DEFAULT_VALIDITY = {'sat': (5, 7), 'csf': (5, 7), 'imss': (0, 1), 'infonavit': (12, 15), 'fiel': (30, 30)}


def today():
    return now().astimezone(ZoneInfo('America/Mexico_City')).date()


def ready(db):
    if not has_table(db, 'document_validity') or not has_table(db, 'integral_opinions'):
        raise HTTPException(503, 'Semáforo documental pendiente de migración autorizada.')


def validity(db):
    out = dict(DEFAULT_VALIDITY)
    for r in db.execute(select(document_validity)).mappings():
        out[r['kind']] = (r['green_days'], r['amber_days'])
    return out


def by_age(issued, rule, day):
    if not issued:
        return 'gray', None, None
    age = (day - issued).days
    green, amber = rule
    state = 'green' if age <= green else 'amber' if age <= amber else 'red'
    return state, age, issued + timedelta(days=amber)


def light(kind, state, **extra):
    return {'kind': kind, 'label': LABELS[kind], 'state': state, **extra}


def latest_opinions(db, ids):
    out = {}
    rows = db.execute(
        select(opinions)
        .where(opinions.c.company_id.in_(ids))
        .order_by(opinions.c.consulted_on.desc(), opinions.c.created_at.desc())
    ).mappings()
    for r in rows:
        if r['review']:
            continue  # A reading awaiting human review does not color the light.
        out.setdefault((r['company_id'], r['authority']), dict(r))
    return out


def fiel_dates(db, ids):
    """Latest FIEL end date per company and holder (company / legal representative), from public CERs."""
    from .credential_models import certificates

    if not has_table(db, 'vault_certificates'):
        return {}
    out = {}
    holder = certificates.c.holder if 'holder' in certificates.c else None
    columns = [certificates.c.company_id, certificates.c.valid_until] + ([holder] if holder is not None else [])
    for r in db.execute(select(*columns).where(certificates.c.company_id.in_(ids), certificates.c.kind == 'fiel')):
        key = (r[0], (r[2] if holder is not None else None) or 'company')
        end = r[1]
        if end and (key not in out or end > out[key]):
            out[key] = end
    return out


def company_lights(db, companies, soon=7):
    ids = [c.id for c in companies]
    day = today()
    rules = validity(db)
    latest = latest_opinions(db, ids)
    fiel = fiel_dates(db, ids)
    settings = {
        (r['company_id'], r['kind']): r['not_applicable']
        for r in db.execute(select(document_settings).where(document_settings.c.company_id.in_(ids))).mappings()
    }
    result = []
    for c in companies:
        lights = []
        # FIEL: days left on the public certificate (company; the legal representative's is reported too).
        end = fiel.get((c.id, 'company'))
        rep = fiel.get((c.id, 'legal_rep'))
        if end:
            left = (end.astimezone(ZoneInfo('America/Mexico_City')).date() - day).days
            state = 'red' if left < 0 else 'amber' if left <= rules['fiel'][1] else 'green'
            lights.append(
                light(
                    'fiel',
                    state,
                    date=end.date().isoformat(),
                    days=left,
                    expires=end.date().isoformat(),
                    detail='Fechas del CER público; no es validación del SAT.',
                    legal_rep=rep.date().isoformat() if rep else None,
                )
            )
        else:
            lights.append(light('fiel', 'gray', detail='Sin certificado FIEL registrado.', legal_rep=None))
        state, age, expires = by_age(c.csf_issued_on, rules['csf'], day)
        lights.append(
            light(
                'csf',
                state,
                date=c.csf_issued_on.isoformat() if c.csf_issued_on else None,
                days=age,
                expires=expires.isoformat() if expires else None,
            )
        )
        for kind in ('sat', 'infonavit', 'imss'):
            if kind != 'sat' and settings.get((c.id, kind)):
                lights.append(light(kind, 'na', detail='No aplica (confirmado).'))
                continue
            o = latest.get((c.id, AUTHORITY[kind]))
            if not o:
                proposal = kind != 'sat' and c.workers == 0
                lights.append(light(kind, 'gray', detail='Sin documento.', propose_not_applicable=proposal))
                continue
            state, age, expires = by_age(o['consulted_on'], rules[kind], day)
            if o['result'] == 'negative':
                state = 'red'
            elif o['result'] in ('no_opinion', 'unreviewed', 'unavailable'):
                state = 'gray'
            lights.append(
                light(
                    kind,
                    state,
                    date=o['consulted_on'].isoformat(),
                    days=age,
                    expires=expires.isoformat() if expires and o['result'] == 'positive' else None,
                    result=o['result'],
                    folio=o['folio'],
                    workers=o['workers'],
                    official_valid_until=o['official_valid_until'].isoformat() if o['official_valid_until'] else None,
                    source=o['source'] or 'manual',
                    omissions=o['omissions'] or [],
                    propose_not_applicable=o['workers'] == 0,
                )
            )
        result.append(
            {
                'company_id': c.id,
                'name': c.name,
                'rfc': c.rfc,
                'person_type': c.person_type,
                'workers': c.workers,
                'lights': lights,
            }
        )
    return result


def summary(rows, soon):
    day = today()
    limit = day + timedelta(days=soon)
    sat = [next(item for item in r['lights'] if item['kind'] == 'sat') for r in rows]
    positive = sum(1 for s in sat if s.get('result') == 'positive')
    negative = sum(1 for s in sat if s.get('result') == 'negative')
    expiring = []
    for r in rows:
        for item in r['lights']:
            exp = item.get('expires')
            if exp and day <= date.fromisoformat(exp) <= limit:
                expiring.append(
                    {'company_id': r['company_id'], 'name': r['name'], 'kind': item['kind'], 'expires': exp}
                )
    return {
        'active_rfcs': len(rows),
        'physical': sum(1 for r in rows if r['person_type'] == 'Física'),
        'moral': sum(1 for r in rows if r['person_type'] != 'Física'),
        'sat': {
            'positive': positive,
            'negative': negative,
            'none': len(rows) - positive - negative,
            'percent': round(positive * 100 / len(rows)) if rows else 0,
        },
        'expiring': {'days': soon, 'count': len(expiring), 'items': sorted(expiring, key=lambda e: e['expires'])[:50]},
        'states': {
            k: {
                s: sum(1 for r in rows for i in r['lights'] if i['kind'] == k and i['state'] == s)
                for s in ('green', 'amber', 'red', 'gray', 'na')
            }
            for k in KINDS
        },
    }


@router.get('/document-status')
def document_status(
    company_id: str | None = None,
    soon: int = Query(7, ge=1, le=90),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    ready(db)
    from .obligation_checklist import visible_companies

    companies = visible_companies(db, p, company_id)
    rows = company_lights(db, companies, soon)
    return {'companies': rows, 'summary': summary(rows, soon), 'validity': validity(db)}


@router.post('/companies/{cid}/compliance/analyze')
async def analyze_document(cid: str, file: UploadFile = File(...), p: Principal = Depends(auth), db=Depends(session)):
    """Read an opinion or constancia for the company; saves nothing. Wrong RFC or repeated folio → review."""
    from starlette.concurrency import run_in_threadpool

    from .compliance_extract import MAX_BYTES, ComplianceError, analyze

    ready(db)
    p.require('documentos.subir', cid)
    company = db.get(Company, cid)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada.')
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    try:
        result = await run_in_threadpool(analyze, data)
    except ComplianceError as exc:
        raise HTTPException(422, str(exc)) from None
    return checked(db, company, result)


def checked(db, company, result):
    f = result['fields']
    if f.get('rfc') and f['rfc'] != company.rfc:
        result['warnings'].insert(0, 'El RFC del documento no es el de esta empresa: queda para revisión humana.')
        result['review'] = True
        result['rfc_mismatch'] = True
    if f.get('folio') and result['authority'] in AUTHORITY.values():
        dup = db.execute(
            select(opinions.c.id).where(opinions.c.authority == result['authority'], opinions.c.folio == f['folio'])
        ).first()
        if dup:
            result['duplicate'] = True
            result['warnings'].insert(0, 'Este folio ya está registrado: no se registrará dos veces.')
    if result['kind'] == 'sat_opinion' and f.get('omissions'):
        from .obligation_catalog import match
        from .obligation_checklist import csf_catalog

        entries = csf_catalog(db)
        for o in f['omissions']:
            o['obligation_id'] = match(o['name'], entries)
    if f.get('workers') == 0 and result['authority'] in ('IMSS', 'INFONAVIT'):
        result['propose_not_applicable'] = True
    return result


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str = Field(pattern='^(sat_opinion|imss_opinion|infonavit|csf)$')
    rfc: str | None = Field(None, max_length=13)
    folio: str | None = Field(None, max_length=60)
    issued_on: date
    result: str = Field(pattern='^(positive|negative|no_opinion)$')
    workers: int | None = Field(None, ge=0, le=1_000_000)
    official_valid_until: date | None = None
    omissions: list[dict] = Field(default_factory=list, max_length=30)
    read: list[str] = Field(default_factory=list, max_length=20)
    corrected: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field('', max_length=2000)


@router.post('/companies/{cid}/compliance', status_code=201)
async def confirm_document(
    cid: str,
    file: UploadFile = File(...),
    payload: str = Form(...),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """Save the confirmed reading: the PDF goes to the company file and the light updates.

    The server reads the PDF again (never trusts the client's reading) to know which fields came from the
    document; values the person changed are recorded as typed. A different RFC is refused; a repeated folio too.
    """
    import io

    from starlette.concurrency import run_in_threadpool

    from .compliance_extract import MAX_BYTES, ComplianceError, analyze
    from .storage.providers import StorageError
    from .storage.router import storage_http_error, storage_service

    ready(db)
    p.require('documentos.subir', cid)
    company = db.get(Company, cid)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada.')
    try:
        confirmed = ConfirmIn.model_validate(json.loads(payload))
    except (ValueError, TypeError):
        raise HTTPException(422, 'Datos confirmados no válidos.') from None
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    try:
        reading = await run_in_threadpool(analyze, data)
    except ComplianceError as exc:
        raise HTTPException(422, str(exc)) from None
    if reading['kind'] != confirmed.kind:
        raise HTTPException(422, 'El tipo de documento no coincide con la lectura.')
    if (confirmed.rfc or reading['fields'].get('rfc')) != company.rfc:
        raise HTTPException(422, 'El documento no corresponde al RFC de esta empresa.')
    read_values = reading['fields']
    read_fields = [
        k
        for k in reading['read']
        if k in confirmed.model_fields_set and getattr(confirmed, k, None) == read_values.get(k)
    ]
    authority = {'sat_opinion': 'SAT', 'imss_opinion': 'IMSS', 'infonavit': 'INFONAVIT', 'csf': 'CSF'}[confirmed.kind]
    if authority != 'CSF' and confirmed.folio:
        if db.execute(
            select(opinions.c.id).where(opinions.c.authority == authority, opinions.c.folio == confirmed.folio)
        ).first():
            raise HTTPException(409, 'Este folio ya está registrado.')
    stored = data
    category = 'Opiniones de cumplimiento'
    if authority == 'CSF':
        from .csf_extract import csf_pages_pdf

        stored = csf_pages_pdf(data, reading.get('pages') or [1])
        category = 'Constancia de Situación Fiscal'
    names = {'SAT': 'OPINION_SAT', 'IMSS': 'OPINION_IMSS', 'INFONAVIT': 'INFONAVIT', 'CSF': 'CSF'}
    name = f'{names[authority]}_{company.rfc}_{confirmed.issued_on.isoformat()}.pdf'
    try:
        document = await run_in_threadpool(
            storage_service().upload,
            p.storage_actor(),
            io.BytesIO(stored),
            name,
            company_id=cid,
            category=category,
            document_type='other',
            period=confirmed.issued_on.strftime('%Y-%m'),
        )
    except StorageError as exc:
        raise storage_http_error(exc) from None
    document_id = getattr(document, 'id', None) or (document.get('id') if isinstance(document, dict) else None)
    if authority == 'CSF':
        if company.csf_issued_on is None or confirmed.issued_on > company.csf_issued_on:
            company.csf_issued_on = confirmed.issued_on
        db.add(
            Audit(
                company_id=cid,
                action='Constancia de Situación Fiscal registrada desde el semáforo',
                actor_id=p.subject,
                changes={'read_fields': read_fields},
            )
        )
        db.commit()
        return {'document_id': document_id, 'authority_validated': False}
    ident = str(uuid4())
    issued_at = read_values.get('issued_at') if 'issued_on' in read_fields else None
    try:
        db.execute(
            opinions.insert().values(
                id=ident,
                company_id=cid,
                authority=authority,
                consulted_on=confirmed.issued_on,
                result=confirmed.result,
                next_review=None,
                document_id=document_id,
                responsible='',
                notes=confirmed.notes,
                actor_id=p.subject,
                created_at=now(),
                folio=confirmed.folio,
                source='document' if read_fields else 'manual',
                workers=confirmed.workers,
                official_valid_until=confirmed.official_valid_until,
                issued_at=datetime.fromisoformat(issued_at) if issued_at else None,
                read_fields=read_fields,
                omissions=confirmed.omissions if confirmed.result == 'negative' else [],
                review=False,
            )
        )
        if confirmed.workers is not None and company.workers is None:
            company.workers = confirmed.workers
        db.add(
            Audit(
                company_id=cid,
                action=f'Documento de cumplimiento {authority} registrado (leído del documento, sin validación oficial)',
                actor_id=p.subject,
                changes={'folio': confirmed.folio, 'result': confirmed.result, 'read_fields': read_fields},
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Este folio ya está registrado.') from None
    return {'id': ident, 'document_id': document_id, 'authority_validated': False}


class SettingIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str = Field(pattern='^(imss|infonavit)$')
    not_applicable: bool


@router.put('/companies/{cid}/document-settings')
def save_setting(cid: str, payload: SettingIn, p: Principal = Depends(auth), db=Depends(session)):
    """«No aplica» for IMSS or Infonavit (companies without workers): a person's confirmation."""
    ready(db)
    p.require('empresa.editar', cid)
    if not db.get(Company, cid):
        raise HTTPException(404, 'Empresa no encontrada.')
    condition = (document_settings.c.company_id == cid) & (document_settings.c.kind == payload.kind)
    db.execute(document_settings.delete().where(condition))
    db.execute(
        document_settings.insert().values(
            company_id=cid,
            kind=payload.kind,
            not_applicable=payload.not_applicable,
            actor_id=p.subject,
            updated_at=now(),
        )
    )
    db.add(
        Audit(
            company_id=cid,
            action=f'Semáforo: {payload.kind.upper()} ' + ('no aplica' if payload.not_applicable else 'aplica'),
            actor_id=p.subject,
        )
    )
    db.commit()
    return {'saved': True}


class ValidityIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str = Field(pattern='^(sat|csf|imss|infonavit|fiel)$')
    green_days: int = Field(ge=0, le=365)
    amber_days: int = Field(ge=0, le=365)


@router.put('/document-validity')
def save_validity(payload: ValidityIn, p: Principal = Depends(auth), db=Depends(session)):
    """The office's validity per document (administrators only)."""
    ready(db)
    p.require_admin()
    if payload.amber_days < payload.green_days:
        raise HTTPException(422, 'El límite ámbar no puede ser menor que el verde.')
    changed = db.execute(
        update(document_validity)
        .where(document_validity.c.kind == payload.kind)
        .values(green_days=payload.green_days, amber_days=payload.amber_days, actor_id=p.subject, updated_at=now())
    ).rowcount
    if not changed:
        db.execute(document_validity.insert().values(**payload.model_dump(), actor_id=p.subject, updated_at=now()))
    db.commit()
    return {'saved': True}
