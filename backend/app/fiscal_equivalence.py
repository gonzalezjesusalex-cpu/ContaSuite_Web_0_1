"""Confirmed equivalences «name in the Excel» -> company (cambio 3A.4).

The Excel has no RFC, so a coincidence of names is only a PROPOSAL. A human confirms it; the confirmation records who
and when, keeps a history and can be revoked. Separate metadata: until the explicit migration
`fiscal_migrations/003_equivalencias_excel.py` runs, the module reports itself unavailable and nothing else changes.
"""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, select, update

from .fiscal_import import normalize
from .models import Company, now
from .schema_cache import tables_ready

metadata = MetaData()
equivalences = Table(
    'fiscal_name_equivalences',
    metadata,
    Column('name_key', String(255), primary_key=True),
    Column('excel_name', String(255), nullable=False),
    Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('status', String(12), nullable=False),
    Column('confirmed_by', String(100), nullable=False),
    Column('confirmed_at', DateTime(timezone=True), nullable=False),
    Column('revoked_by', String(100)),
    Column('revoked_at', DateTime(timezone=True)),
    Column('revision', Integer, nullable=False),
)
history = Table(
    'fiscal_name_equivalence_history',
    metadata,
    Column('id', String(36), primary_key=True),
    Column('name_key', String(255), nullable=False),
    Column('company_id', String(36), nullable=False),
    Column('action', String(12), nullable=False),
    Column('actor_id', String(100), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
)


def available(db):
    return tables_ready(db, metadata)


def ready(db):
    if not available(db):
        raise HTTPException(503, 'Equivalencias del Excel pendientes de migración autorizada. No se modificó la base.')


def confirmed(db):
    """Normalized Excel name -> company id for every confirmed (not revoked) equivalence; {} while unavailable."""
    if not available(db):
        return {}
    rows = db.execute(
        select(equivalences.c.name_key, equivalences.c.company_id).where(equivalences.c.status == 'confirmed')
    )
    return {name: company for name, company in rows}


def listing(db):
    if not available(db):
        return []
    out = []
    for row in db.execute(select(equivalences).order_by(equivalences.c.excel_name)).mappings():
        item = dict(row)
        for key in ('confirmed_at', 'revoked_at'):
            item[key] = item[key].isoformat() if item[key] else None
        out.append(item)
    return out


def confirm(db, principal, excel_name, company_id):
    """Confirm the equivalence; an existing one for another company is replaced and the change stays in the history."""
    ready(db)
    key = normalize(excel_name)
    if not key:
        raise HTTPException(422, 'Nombre del Excel requerido.')
    if not db.get(Company, company_id):
        raise HTTPException(404, 'Empresa no encontrada.')
    old = db.execute(select(equivalences).where(equivalences.c.name_key == key)).mappings().first()
    stamp = now()
    if old:
        db.execute(
            update(equivalences)
            .where(equivalences.c.name_key == key)
            .values(
                company_id=company_id,
                excel_name=excel_name[:255],
                status='confirmed',
                confirmed_by=principal.subject,
                confirmed_at=stamp,
                revoked_by=None,
                revoked_at=None,
                revision=old['revision'] + 1,
            )
        )
    else:
        db.execute(
            equivalences.insert().values(
                name_key=key,
                excel_name=excel_name[:255],
                company_id=company_id,
                status='confirmed',
                confirmed_by=principal.subject,
                confirmed_at=stamp,
                revision=1,
            )
        )
    db.execute(
        history.insert().values(
            id=str(uuid4()),
            name_key=key,
            company_id=company_id,
            action='confirmed',
            actor_id=principal.subject,
            created_at=stamp,
        )
    )
    db.commit()
    return {'name_key': key, 'company_id': company_id}


def revoke(db, principal, excel_name):
    ready(db)
    key = normalize(excel_name)
    old = db.execute(select(equivalences).where(equivalences.c.name_key == key)).mappings().first()
    if not old or old['status'] != 'confirmed':
        raise HTTPException(404, 'No hay una equivalencia confirmada para ese nombre.')
    stamp = now()
    db.execute(
        update(equivalences)
        .where(equivalences.c.name_key == key)
        .values(status='revoked', revoked_by=principal.subject, revoked_at=stamp, revision=old['revision'] + 1)
    )
    db.execute(
        history.insert().values(
            id=str(uuid4()),
            name_key=key,
            company_id=old['company_id'],
            action='revoked',
            actor_id=principal.subject,
            created_at=stamp,
        )
    )
    db.commit()
    return {'name_key': key}


def trail(db, excel_name):
    if not available(db):
        return []
    key = normalize(excel_name)
    return [
        {**dict(r), 'created_at': r['created_at'].isoformat()}
        for r in db.execute(
            select(history).where(history.c.name_key == key).order_by(history.c.created_at.desc()).limit(50)
        ).mappings()
    ]
