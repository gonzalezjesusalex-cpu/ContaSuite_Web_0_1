"""Plan v1.1, Cambio 2: obligations per company and period with a «done» box.

Built on the existing Control de obligaciones tables (fiscal_catalog, fiscal_applicability, fiscal_records,
fiscal_history): a CSF obligation (catalog row with a group) assigned to a company is shown in the month that
closes its period, within the start and end dates read from the constancia. Marking it writes a fiscal_record
(status fulfilled / pending) and a history row with who and when. «Overdue» is calculated when reading, never
stored. Due dates come from the catalog rule unless a verified date was captured on the record.
"""

import io
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from . import obligation_catalog as oc
from .database import session
from .fiscal_control import applicability, catalog, history, periods, ready, records, serial
from .models import Company, UserAccount, now
from .security import Principal, auth

router = APIRouter(prefix='/api/fiscal-control', tags=['Control de obligaciones'])


def today():
    from .fiscal_read import cutoff

    return cutoff()


def csf_catalog(db):
    return [dict(r) for r in db.execute(select(catalog).where(catalog.c.group_name.is_not(None))).mappings()]


def visible_companies(db, principal, company_id=None, responsible=None, person_type=None, include_archived=False):
    query = select(Company).order_by(Company.name)
    if not principal.admin:
        query = query.where(Company.id.in_(principal.company_ids))
    if company_id:
        principal.require_company(company_id)
        query = query.where(Company.id == company_id)
    if responsible:
        query = query.where(Company.accountant_id == responsible)
    if person_type:
        query = query.where(Company.person_type == person_type)
    companies = list(db.scalars(query))
    from .company_lifecycle import archive_metadata

    archive_ready, archived = archive_metadata(db, [c.id for c in companies])
    if archive_ready and not company_id and not include_archived:
        companies = [c for c in companies if not archived.get(c.id, {}).get('archived', False)]
    return companies


def cadence_of(definition):
    return definition.get('cadence') or definition.get('periodicity') or 'monthly'


def build(db, companies, year, month, definitions=None):
    """Checklist cells for `companies` in (year, month). Only applicable, active obligations shown this month."""
    definitions = definitions if definitions is not None else csf_catalog(db)
    by_id = {d['id']: d for d in definitions}
    ids = [c.id for c in companies]
    if not ids or not by_id:
        return {c.id: [] for c in companies}
    rules = [
        dict(r)
        for r in db.execute(
            select(applicability).where(
                applicability.c.company_id.in_(ids),
                applicability.c.obligation_id.in_(list(by_id)),
                applicability.c.applicable.is_(True),
            )
        ).mappings()
    ]
    keys = {oc.period_key(cadence_of(d), year, month) for d in definitions}
    stored = {
        (r['company_id'], r['obligation_id'], r['period_id']): dict(r)
        for r in db.execute(
            select(records).where(records.c.company_id.in_(ids), records.c.period_id.in_(sorted(keys)))
        ).mappings()
    }
    marks = {}
    if stored:
        record_ids = [r['id'] for r in stored.values()]
        rows = db.execute(
            select(history.c.record_id, history.c.actor_id, history.c.created_at)
            .where(history.c.record_id.in_(record_ids))
            .order_by(history.c.created_at)
        ).all()
        for record_id, actor, created in rows:
            marks[record_id] = (actor, created)
    actors = {a for a, _ in marks.values() if a}
    names = (
        dict(db.execute(select(UserAccount.id, UserAccount.display_name).where(UserAccount.id.in_(actors))).all())
        if actors
        else {}
    )
    day = today()
    omitted = sat_omissions(db, ids)
    out = {c.id: [] for c in companies}
    for rule in rules:
        d = by_id[rule['obligation_id']]
        cadence = cadence_of(d)
        if not oc.shown_in(cadence, month):
            continue
        start, end = oc.period_bounds(cadence, year, month)
        if not oc.active_in(rule.get('start_date'), rule.get('end_date'), start, end):
            continue
        key = oc.period_key(cadence, year, month)
        row = stored.get((rule['company_id'], d['id'], key))
        done = bool(row and row['status'] == 'fulfilled')
        due = row['due_date'] if row and row['due_verified'] and row['due_date'] else oc.due_date(d['due_rule'], end)
        actor, marked_at = marks.get(row['id'], (None, None)) if row else (None, None)
        out[rule['company_id']].append(
            {
                'obligation_id': d['id'],
                'short_name': d['short_name'] or d['label'],
                'official_name': d['official_name'] or d['label'],
                'group': d['group_name'],
                'cadence': cadence,
                'period_id': key,
                'done': done,
                'not_applicable': bool(row and row['status'] == 'not_applicable'),
                'revision': row['revision'] if row else 0,
                'due_date': due.isoformat() if due else None,
                'due_text': d['due_text'],
                'overdue': bool(not done and due and due < day),
                'marked_by': names.get(actor) if actor else None,
                'marked_at': marked_at.isoformat() if marked_at else None,
                # Exercises the latest SAT opinion (negative) lists as omitted for this obligation.
                'opinion_omissions': omitted.get((rule['company_id'], d['id']), []),
            }
        )
    order = {g: i for i, g in enumerate(oc.GROUPS)}
    for items in out.values():
        items.sort(key=lambda i: (order.get(i['group'], 99), i['short_name']))
    return out


def sat_omissions(db, ids):
    """{(company, obligation): [years]} from each company's latest SAT opinion when it is negative (Cambio 1)."""
    from .schema_cache import column_names, has_table

    if not has_table(db, 'integral_opinions') or 'omissions' not in column_names(db, 'integral_opinions'):
        return {}
    from .integral_models import opinions

    out, seen = {}, set()
    rows = db.execute(
        select(opinions.c.company_id, opinions.c.result, opinions.c.omissions)
        .where(opinions.c.company_id.in_(ids), opinions.c.authority == 'SAT')
        .order_by(opinions.c.consulted_on.desc(), opinions.c.created_at.desc())
    ).all()
    for company, result, omissions in rows:
        if company in seen:
            continue
        seen.add(company)
        if result != 'negative':
            continue
        for o in omissions or []:
            if o.get('obligation_id'):
                out.setdefault((company, o['obligation_id']), []).append(o.get('year'))
    return out


def totals(items):
    counted = [i for i in items if not i['not_applicable']]
    done = sum(1 for i in counted if i['done'])
    return {
        'done': done,
        'total': len(counted),
        'pending': len(counted) - done,
        'overdue': sum(1 for i in counted if i['overdue']),
    }


@router.get('/checklist')
def checklist(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    company_id: str | None = None,
    responsible: str | None = None,
    person_type: str | None = Query(None, pattern='^(Moral|Física)$'),
    pending: bool = False,
    principal: Principal = Depends(auth),
    db=Depends(session),
):
    ready(db)
    companies = visible_companies(db, principal, company_id, responsible, person_type)
    definitions = csf_catalog(db)
    cells = build(db, companies, year, month, definitions)
    rows = []
    for c in companies:
        items = cells[c.id]
        summary = totals(items)
        if (pending and not summary['pending']) or (not items and not company_id):
            continue
        rows.append(
            {
                'id': c.id,
                'name': c.name,
                'rfc': c.rfc,
                'person_type': c.person_type,
                'accountant': c.accountant,
                'accountant_id': c.accountant_id,
                'items': items,
                **summary,
            }
        )
    month_summary = totals([i for r in rows for i in r['items']])
    return {
        'year': year,
        'month': month,
        'groups': oc.GROUPS,
        'catalog': [
            {
                'id': d['id'],
                'short_name': d['short_name'] or d['label'],
                'official_name': d['official_name'] or d['label'],
                'group': d['group_name'],
                'cadence': cadence_of(d),
            }
            for d in definitions
        ],
        'companies': rows,
        'summary': month_summary,
    }


class DoneIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    company_id: str = Field(max_length=36)
    obligation_id: str = Field(max_length=36)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    done: bool
    revision: int = Field(ge=0)


@router.put('/checklist')
def mark(payload: DoneIn, principal: Principal = Depends(auth), db=Depends(session)):
    """Mark an obligation of a period as done or not done; recorded in the history with user and time."""
    ready(db)
    principal.require('obligaciones.editar', payload.company_id)
    definition = (
        db.execute(select(catalog).where(catalog.c.id == payload.obligation_id, catalog.c.group_name.is_not(None)))
        .mappings()
        .first()
    )
    if not definition or not db.get(Company, payload.company_id):
        raise HTTPException(404, 'Empresa u obligación no encontrada.')
    rule = (
        db.execute(
            select(applicability).where(
                applicability.c.company_id == payload.company_id,
                applicability.c.obligation_id == payload.obligation_id,
            )
        )
        .mappings()
        .first()
    )
    cadence = cadence_of(definition)
    start, end = oc.period_bounds(cadence, payload.year, payload.month)
    if (
        not rule
        or not rule['applicable']
        or not oc.active_in(rule['start_date'], rule['end_date'], start, end)
        or not oc.shown_in(cadence, payload.month)
    ):
        raise HTTPException(422, 'La obligación no aplica a la empresa en este periodo.')
    return save_mark(
        db,
        principal,
        payload.company_id,
        definition,
        payload.year,
        payload.month,
        payload.done,
        payload.revision,
        end,
        start,
    )


def save_mark(db, principal, company_id, definition, year, month, done, revision, end, start, reason=None):
    key = oc.period_key(cadence_of(definition), year, month)
    previous = (
        db.execute(
            select(records).where(
                records.c.company_id == company_id,
                records.c.obligation_id == definition['id'],
                records.c.period_id == key,
            )
        )
        .mappings()
        .first()
    )
    if (previous['revision'] if previous else 0) != revision:
        raise HTTPException(409, 'La obligación cambió; actualiza antes de marcar.')
    status = 'fulfilled' if done else 'pending'
    ident = previous['id'] if previous else str(uuid4())
    stamp = now()
    try:
        if previous:
            if not db.execute(
                update(records)
                .where(records.c.id == ident, records.c.revision == revision)
                .values(status=status, revision=revision + 1, updated_at=stamp)
            ).rowcount:
                raise HTTPException(409, 'Edición concurrente; actualiza.')
        else:
            if not db.execute(select(periods.c.id).where(periods.c.id == key)).first():
                db.execute(periods.insert().values(id=key, start_date=start, end_date=end))
            db.execute(
                records.insert().values(
                    id=ident,
                    company_id=company_id,
                    obligation_id=definition['id'],
                    period_id=key,
                    status=status,
                    responsible_id=None,
                    registered_at=stamp,
                    submitted_at=None,
                    due_date=None,
                    due_verified=False,
                    payment='unknown',
                    notes='',
                    revision=1,
                    updated_at=stamp,
                )
            )
        db.execute(
            history.insert().values(
                id=str(uuid4()),
                record_id=ident,
                company_id=company_id,
                actor_id=principal.subject,
                created_at=stamp,
                before=serial(previous) if previous else None,
                after={'action': 'checklist', 'done': done, 'period_id': key, **({'reason': reason} if reason else {})},
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Registro concurrente; actualiza.') from None
    return {'revision': revision + 1, 'done': done}


@router.get('/checklist.xlsx')
def export(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    company_id: str | None = None,
    responsible: str | None = None,
    person_type: str | None = Query(None, pattern='^(Moral|Física)$'),
    pending: bool = False,
    principal: Principal = Depends(auth),
    db=Depends(session),
):
    """The checklist as shown, to Excel: one row per company and obligation (no documents, no secrets)."""
    from openpyxl import Workbook

    data = checklist(year, month, company_id, responsible, person_type, pending, principal, db)
    book = Workbook()
    sheet = book.active
    sheet.title = f'{year}-{month:02d}'
    sheet.append(['Empresa', 'RFC', 'Contador', 'Grupo', 'Obligación', 'Periodo', 'Vence', 'Hecha', 'Vencida'])
    for c in data['companies']:
        for i in c['items']:
            sheet.append(
                [
                    c['name'],
                    c['rfc'],
                    c['accountant'],
                    i['group'],
                    i['official_name'],
                    i['period_id'],
                    i['due_date'] or '',
                    'Sí' if i['done'] else 'No',
                    'Sí' if i['overdue'] else '',
                ]
            )
    out = io.BytesIO()
    book.save(out)
    out.seek(0)
    name = f'obligaciones_{year}-{month:02d}.xlsx'
    return StreamingResponse(
        out,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{name}"'},
    )


@router.get('/companies/{cid}/assignments')
def assignments(cid: str, principal: Principal = Depends(auth), db=Depends(session)):
    """CSF obligations of the catalog and the company's assignment (dates, source), for the company file."""
    ready(db)
    principal.require_company(cid)
    if not db.get(Company, cid):
        raise HTTPException(404, 'Empresa no encontrada.')
    rules = {
        r['obligation_id']: dict(r)
        for r in db.execute(select(applicability).where(applicability.c.company_id == cid)).mappings()
    }
    out = []
    for d in csf_catalog(db):
        r = rules.get(d['id'])
        out.append(
            {
                'obligation_id': d['id'],
                'short_name': d['short_name'] or d['label'],
                'official_name': d['official_name'] or d['label'],
                'group': d['group_name'],
                'cadence': cadence_of(d),
                'due_text': d['due_text'],
                'applicable': bool(r and r['applicable']),
                'revision': r['revision'] if r else 0,
                'start_date': r['start_date'].isoformat() if r and r['start_date'] else None,
                'end_date': r['end_date'].isoformat() if r and r['end_date'] else None,
                'source': r['source'] if r else None,
            }
        )
    return {'items': out, 'can_edit': principal.can('obligaciones.editar', cid)}


@router.get('/catalog/csf')
def csf_definitions(principal: Principal = Depends(auth), db=Depends(session)):
    """CSF obligations of the catalog with their due rule (plan v1.1), for the catalog screen."""
    ready(db)
    rows = csf_catalog(db)
    for r in rows:
        r['cadence'] = cadence_of(r)
        r['aliases'] = r.get('aliases') or []
    order = {g: i for i, g in enumerate(oc.GROUPS)}
    return {
        'items': sorted(rows, key=lambda r: (order.get(r['group_name'], 99), r['short_name'] or r['label'])),
        'can_edit': principal.admin,
    }


@router.post('/catalog/parse-due')
def parse_due(payload: dict, principal: Principal = Depends(auth)):
    """Calculable rule for a «Descripción vencimiento» text, to prefill the catalog form."""
    text = str(payload.get('text', ''))[:300]
    return {'due_rule': oc.parse_due_rule(text)}
