"""Plan v1.1, Cambio 3: yearly calendar of the CFDI registered in ContaSuite per company.

The XML that already reach CS-Storage (uploads, CFDI saves to the company file, indexed folders) leave one row
here with the issue date, stamping date, issuer and receiver RFC, type and total, read from the XML header. A
CFDI is «issued» or «received» by comparing those RFC with the company's. Nothing is downloaded from the SAT:
the calendar says what ContaSuite has, never what exists. No new import is created; `rebuild` only indexes the
company's XML already stored, reading them through CS-Storage with the person's authorization.
"""

import calendar as cal
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    Table,
    func,
    or_,
    select,
)

from .database import session
from .models import Company, Document, DocumentCompanyLink, DocumentVersion, now
from .schema_cache import has_table
from .security import Principal, auth

metadata = MetaData()
entries = Table(
    'cfdi_calendar_entries',
    metadata,
    Column('document_id', ForeignKey(Document.id), primary_key=True),
    Column('version_id', ForeignKey(DocumentVersion.id), nullable=False),
    Column('uuid', String(36), index=True),
    Column('issued_on', Date, nullable=False, index=True),
    Column('stamped_on', Date),
    Column('issuer_rfc', String(13), nullable=False, index=True),
    Column('receiver_rfc', String(13), nullable=False, index=True),
    Column('cfdi_type', String(2), nullable=False),
    Column('total', Numeric(18, 2)),
    Column('currency', String(5)),
    Column('indexed_at', DateTime(timezone=True), nullable=False),
)
router = APIRouter(prefix='/api/cfdi-calendar', tags=['Calendario de CFDI'])
HEAD = 64 * 1024


def available(db):
    return has_table(db, entries.name)


def facts(stream):
    """Header data of a CFDI XML from its first bytes; None when it is not a CFDI. The stream is rewound."""
    try:
        stream.seek(0)
        head = stream.read(HEAD)
        stream.seek(0)
    except (OSError, ValueError):
        return None
    text = head.decode('utf-8', errors='ignore') if isinstance(head, (bytes, bytearray)) else str(head)
    if 'sat.gob.mx/cfd' not in text:
        return None
    root = re.search(r'<(?:\w+:)?Comprobante\b[^>]*>', text, re.S)
    if not root:
        return None
    attrs = root.group(0)

    def attr(name, scope=attrs):
        m = re.search(r'\b' + name + r'\s*=\s*"([^"]*)"', scope)
        return m.group(1).strip() if m else ''

    def side(tag):
        m = re.search(r'<(?:\w+:)?' + tag + r'\b[^>]*?\bRfc\s*=\s*"([^"]+)"', text, re.S)
        return ''.join(m.group(1).split()).upper()[:13] if m else ''

    try:
        issued = datetime.fromisoformat(attr('Fecha')[:19]).date()
    except ValueError:
        return None
    if not 2000 <= issued.year <= 2100:
        return None
    stamp = re.search(r'<(?:\w+:)?TimbreFiscalDigital\b[^>]*>', text, re.S)
    stamped, uuid = None, None
    if stamp:
        try:
            stamped = datetime.fromisoformat(attr('FechaTimbrado', stamp.group(0))[:19]).date()
        except ValueError:
            stamped = None
        u = attr('UUID', stamp.group(0)).upper()
        uuid = u if re.fullmatch(r'[0-9A-F]{8}-(?:[0-9A-F]{4}-){3}[0-9A-F]{12}', u) else None
    try:
        total = Decimal(attr('Total')) if attr('Total') else None
    except InvalidOperation:
        total = None
    issuer, receiver = side('Emisor'), side('Receptor')
    if not issuer or not receiver:
        return None
    return {
        'uuid': uuid,
        'issued_on': issued,
        'stamped_on': stamped,
        'issuer_rfc': issuer,
        'receiver_rfc': receiver,
        'cfdi_type': (attr('TipoDeComprobante') or '?')[:2].upper(),
        'total': total,
        'currency': attr('Moneda')[:5] or None,
    }


def record(db, doc, version, data):
    """Keep the calendar row of a document's current version; a no-op without the table or the data."""
    if not data or not available(db):
        return
    db.execute(entries.delete().where(entries.c.document_id == doc.id))
    db.execute(entries.insert().values(document_id=doc.id, version_id=version.id, indexed_at=now(), **data))


def company_scope(db, p, cid):
    p.require('documentos.ver', cid)
    company = db.get(Company, cid)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada.')
    if not available(db):
        raise HTTPException(503, 'Calendario de CFDI pendiente de migración autorizada.')
    rfc = ''.join((company.rfc or '').split()).upper()
    linked = select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id == cid)
    owned = select(Document.id).where(Document.company_id == cid)
    where = [
        or_(entries.c.issuer_rfc == rfc, entries.c.receiver_rfc == rfc),
        or_(entries.c.document_id.in_(linked), entries.c.document_id.in_(owned)),
    ]
    return company, rfc, where


def money(value):
    return float(value or 0)


@router.get('/{cid}')
def year_view(
    cid: str,
    year: int = Query(ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """Counts and totals of issued and received CFDI per month of the year (and per day of `month`)."""
    company, rfc, where = company_scope(db, p, cid)
    start, end = date(year, 1, 1), date(year, 12, 31)
    # One CFDI stored twice (same UUID) counts once; rows without UUID count per document.
    key = func.coalesce(entries.c.uuid, entries.c.document_id)
    rows = db.execute(
        select(
            entries.c.issued_on,
            entries.c.issuer_rfc == rfc,
            entries.c.receiver_rfc == rfc,
            func.count(func.distinct(key)),
            func.sum(entries.c.total),
        )
        .where(*where, entries.c.issued_on >= start, entries.c.issued_on <= end)
        .group_by(entries.c.issued_on, entries.c.issuer_rfc == rfc, entries.c.receiver_rfc == rfc)
    ).all()
    months = {m: {'issued': [0, 0.0], 'received': [0, 0.0]} for m in range(1, 13)}
    days = {}
    for day, issued, received, count, total in rows:
        if isinstance(day, str):
            day = date.fromisoformat(day[:10])
        kinds = (['issued'] if issued else []) + (['received'] if received else [])
        for kind in kinds:
            months[day.month][kind][0] += count
            months[day.month][kind][1] += money(total)
            if month and day.month == month:
                slot = days.setdefault(day.day, {'issued': [0, 0.0], 'received': [0, 0.0]})
                slot[kind][0] += count
                slot[kind][1] += money(total)

    def shape(v):
        return {
            'issued': {'count': v['issued'][0], 'total': round(v['issued'][1], 2)},
            'received': {'count': v['received'][0], 'total': round(v['received'][1], 2)},
        }

    out = {
        'company': {'id': company.id, 'name': company.name, 'rfc': company.rfc},
        'year': year,
        'months': [{'month': m, **shape(v)} for m, v in months.items()],
        'indexed': db.scalar(select(func.count()).select_from(entries).where(*where)) or 0,
        'source': 'ContaSuite',
        'authority_validated': False,
    }
    if month:
        last = cal.monthrange(year, month)[1]
        out['month'] = month
        out['days'] = [
            {'day': d, **shape(days.get(d, {'issued': [0, 0.0], 'received': [0, 0.0]}))} for d in range(1, last + 1)
        ]
    return out


@router.get('/{cid}/documents')
def documents(
    cid: str,
    day: date,
    kind: str = Query(pattern='^(issued|received)$'),
    p: Principal = Depends(auth),
    db=Depends(session),
):
    """The CFDI of one day and kind, to open from the calendar."""
    _, rfc, where = company_scope(db, p, cid)
    side = entries.c.issuer_rfc == rfc if kind == 'issued' else entries.c.receiver_rfc == rfc
    rows = db.execute(
        select(entries, Document.name)
        .join(Document, Document.id == entries.c.document_id)
        .where(*where, side, entries.c.issued_on == day)
        .order_by(Document.name)
        .limit(500)
    ).mappings()
    return [
        {
            'document_id': r['document_id'],
            'name': r['name'],
            'uuid': r['uuid'],
            'counterpart_rfc': r['receiver_rfc'] if kind == 'issued' else r['issuer_rfc'],
            'type': r['cfdi_type'],
            'total': money(r['total']),
            'currency': r['currency'],
            'stamped_on': r['stamped_on'].isoformat() if r['stamped_on'] else None,
        }
        for r in rows
    ]


@router.post('/{cid}/rebuild')
def rebuild(cid: str, p: Principal = Depends(auth), db=Depends(session)):
    """Index the company's XML already in CS-Storage that have no calendar row (or an older version)."""
    from .storage.providers import StorageError
    from .storage.router import storage_service

    p.require('documentos.subir', cid)
    if not db.get(Company, cid):
        raise HTTPException(404, 'Empresa no encontrada.')
    if not available(db):
        raise HTTPException(503, 'Calendario de CFDI pendiente de migración autorizada.')
    linked = select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id == cid)
    candidates = db.execute(
        select(Document.id, DocumentVersion.id)
        .join(
            DocumentVersion,
            (DocumentVersion.document_id == Document.id) & (DocumentVersion.number == Document.storage_revision),
        )
        .outerjoin(entries, entries.c.document_id == Document.id)
        .where(
            or_(Document.company_id == cid, Document.id.in_(linked)),
            func.lower(Document.name).like('%.xml'),
            or_(entries.c.version_id.is_(None), entries.c.version_id != DocumentVersion.id),
        )
        .limit(5000)
    ).all()
    indexed = skipped = 0
    service = storage_service()
    for doc_id, version_id in candidates:
        try:
            with service.read(p.storage_actor(), doc_id) as content:
                data = facts(content.stream)
        except StorageError:
            skipped += 1
            continue
        if not data:
            skipped += 1
            continue
        db.execute(entries.delete().where(entries.c.document_id == doc_id))
        db.execute(entries.insert().values(document_id=doc_id, version_id=version_id, indexed_at=now(), **data))
        indexed += 1
        if indexed % 200 == 0:
            db.commit()
    db.commit()
    return {'indexed': indexed, 'skipped': skipped, 'pending': len(candidates) == 5000}
