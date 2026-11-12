"""Explicit archival, independent from fiscal activity. Never migrated at startup."""
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import MetaData, Table, Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, select, update, inspect, text
from sqlalchemy.exc import IntegrityError
from .database import session
from .models import Company, Audit, now
from .security import auth, Principal

metadata = MetaData()
states = Table('company_archive_states', metadata,
    Column('company_id', ForeignKey(Company.id), primary_key=True),
    Column('archived', Boolean, nullable=False), Column('revision', Integer, nullable=False),
    Column('actor_id', String(100), nullable=False), Column('updated_at', DateTime(timezone=True), nullable=False))
events = Table('company_archive_events', metadata,
    Column('id', String(36), primary_key=True), Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('actor_id', String(100), nullable=False), Column('created_at', DateTime(timezone=True), nullable=False),
    Column('action', String(20), nullable=False), Column('details', JSON, nullable=False))
router = APIRouter(prefix='/api/company-lifecycle', tags=['Empresas'])

def available(db):
    inspector = inspect(db.connection())
    return all(inspector.has_table(t.name) and {c.name for c in t.columns} <= {c['name'] for c in inspector.get_columns(t.name)} for t in metadata.tables.values())

def archive_metadata(db, company_ids):
    if not available(db):
        return False, {}
    return True, {r['company_id']: dict(r) for r in db.execute(select(states).where(states.c.company_id.in_(company_ids))).mappings()}

def normalize_rfc(value):
    return ''.join(value.split()).upper()

def ensure_unique_rfc(db, value, own_id=None):
    key = normalize_rfc(value)
    # Serialize normalized identities for PostgreSQL; raw UNIQUE remains the final guard.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': key})
    if any(c.id != own_id and normalize_rfc(c.rfc) == key for c in db.scalars(select(Company))):
        raise HTTPException(409, 'El RFC normalizado ya está registrado. Revisa la empresa existente; no se fusionaron datos.')

def forbid_delete():
    raise HTTPException(409, 'La eliminación definitiva está deshabilitada. Archiva la empresa para conservar su historial.')

class ArchiveIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    archived: bool
    revision: int = Field(ge=0)

@router.get('')
def directory(principal: Principal = Depends(auth), db=Depends(session), query: str = '',
              archive: Literal['active','archived','all'] = 'active',
              sort: Literal['name','rfc','accountant'] = 'name', accountant: str = ''):
    if not available(db):
        raise HTTPException(503, 'Directorio con archivado pendiente de migración explícita. Los expedientes existentes conservan su acceso autorizado.')
    companies = list(db.scalars(select(Company).where(True if principal.admin else Company.id.in_(principal.company_ids))))
    _, rows = archive_metadata(db, [c.id for c in companies])
    keys = [normalize_rfc(c.rfc) for c in companies]
    result = []
    for c in companies:
        state = rows.get(c.id, {})
        archived = state.get('archived', False)
        if archive != 'all' and archived != (archive == 'archived'):
            continue
        if accountant and c.accountant != accountant:
            continue
        if query.casefold().strip() not in (c.name+' '+c.rfc+' '+c.trade_name).casefold() and normalize_rfc(query) not in normalize_rfc(c.rfc):
            continue
        result.append({**{col.name: ('' if col.name == 'folder' and not principal.admin else getattr(c, col.name)) for col in Company.__table__.columns},
                       'archived': archived, 'archive_revision': state.get('revision', 0), 'duplicate_rfc': keys.count(normalize_rfc(c.rfc)) > 1})
    return {'companies': sorted(result, key=lambda c: (c[sort].casefold(), c['id'])), 'archive_available': True}

@router.put('/{company_id}')
def set_archive(company_id: str, payload: ArchiveIn, principal: Principal = Depends(auth), db=Depends(session)):
    principal.require_admin()
    principal.require_company(company_id, write=True)
    if not available(db):
        raise HTTPException(503, 'Archivado pendiente de migración explícita autorizada. No se modificaron datos.')
    if not db.get(Company, company_id):
        raise HTTPException(404, 'Empresa no encontrada.')
    old = db.execute(select(states).where(states.c.company_id == company_id)).mappings().first()
    if (old['revision'] if old else 0) != payload.revision:
        raise HTTPException(409, 'El estado cambió; actualiza antes de continuar.')
    if old and old['archived'] == payload.archived:
        return dict(archived=old['archived'], revision=old['revision'])
    stamp = now()
    values = dict(archived=payload.archived, revision=payload.revision+1, actor_id=principal.subject, updated_at=stamp)
    try:
        if old:
            if not db.execute(update(states).where(states.c.company_id == company_id, states.c.revision == payload.revision).values(**values)).rowcount:
                raise HTTPException(409, 'Cambio concurrente; actualiza.')
        else:
            db.execute(states.insert().values(company_id=company_id, **values))
        action = 'archived' if payload.archived else 'restored'
        db.execute(events.insert().values(id=str(uuid4()), company_id=company_id, actor_id=principal.subject,
            created_at=stamp, action=action, details={'before': bool(old['archived']) if old else False, 'after': payload.archived, 'revision': values['revision']}))
        db.add(Audit(company_id=company_id, action=f'Empresa {action} por {principal.subject}', created_at=stamp))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Cambio concurrente; actualiza.') from None
    return dict(archived=payload.archived, revision=values['revision'])

@router.get('/{company_id}/history')
def archive_history(company_id: str, principal: Principal = Depends(auth), db=Depends(session)):
    principal.require_company(company_id)
    if not available(db):
        raise HTTPException(503, 'Historial de archivado pendiente de migración autorizada.')
    return [dict(r) for r in db.execute(select(events).where(events.c.company_id == company_id).order_by(events.c.created_at.desc()).limit(100)).mappings()]
