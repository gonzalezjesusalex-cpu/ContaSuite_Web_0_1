"""Configuración › Alertas and the top-bar bell: one chronological list of the office's alerts.

The conditions are the existing ones: certificates and obligations (credential_alerts.candidates) and the
quality review items of the integral dashboard (company data and documents). They are kept in the existing
lifecycle tables (vault_alerts, alert_lifecycle, lote4_action_history): a condition that disappears is closed
as `obsolete` («Resuelta»), a snoozed alert comes back on its date and a dismissed one stays closed with its
reason. Reading the list evaluates the conditions first (internal evaluator, like the scheduled worker), so
fixing the cause (assigning a responsible, classifying a document) resolves the alert without another step.
"""

import time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query, Response
from sqlalchemy import select

from .database import session
from .models import Company, Document, UserAccount, now
from .schema_cache import has_table
from .security import Principal, auth

TIMEZONE = 'America/Mexico_City'
SYSTEM = Principal('alert-worker', 'Evaluador interno de alertas', True)
ACTIVE = ('pending', 'acknowledged')
CLOSED = ('resolved', 'obsolete', 'dismissed')
# Several screens read the list at once (bell, Configuración); one evaluation serves them for a few seconds.
SYNC_SECONDS = 10
_last_sync = [0.0]


def local_today():
    return now().astimezone(ZoneInfo(TIMEZONE)).date()


def quality_candidates(db, p):
    """Quality review items of the integral dashboard (only those tied to a company) as alert candidates.
    Without the integral dashboard tables (installation not migrated yet) there are none."""
    from .integral_dashboard import dashboard
    from .integral_models import metadata
    from .schema_cache import tables_ready

    if not tables_ready(db, metadata):
        return []

    day = local_today()
    report = dashboard(db, p, day.year, day.month, include_archived=True, alert_limit=None)
    return [
        dict(
            company_id=a['company_id'],
            source='quality',
            reference=a['reference'],
            kind=a['kind'],
            priority=a['priority'],
            due_at=None,
        )
        for a in report['alerts']
        if a['source'] == 'quality' and a['company_id']
    ]


def all_candidates(db, p, stamp=None):
    from .credential_alerts import candidates

    return candidates(db, p, stamp=stamp) + quality_candidates(db, p)


def sync(db, force=False):
    """Bring the stored alerts in step with their conditions. False when the lifecycle tables are missing."""
    from .lote4_lifecycle import available, evaluate

    if not available(db):
        return False
    if force or time.monotonic() - _last_sync[0] >= SYNC_SECONDS:
        evaluate(db, SYSTEM, all_candidates(db, SYSTEM))
        _last_sync[0] = time.monotonic()
    return True


def visible(db, p):
    """Companies whose alerts this user sees, and those whose certificate alerts too (metadata permission)."""
    from .company_lifecycle import archive_metadata
    from .credential_api import allowed

    ids = list(db.scalars(select(Company.id).where(True if p.admin else Company.id.in_(p.company_ids))))
    _, archive = archive_metadata(db, ids)
    ids = [cid for cid in ids if not archive.get(cid, {}).get('archived', False)]
    certs = set()
    if has_table(db, 'vault_certificates'):
        for cid in ids:
            try:
                allowed(p, db, cid, 'metadata')
                certs.add(cid)
            except HTTPException:
                pass
    return set(ids), certs


def details(db, rows):
    """Name of the related document, obligation or certificate (never an identifier)."""
    out = {}
    docs = {r['reference'] for r in rows if r['source'] == 'quality'}
    if docs:
        out.update(dict(db.execute(select(Document.id, Document.name).where(Document.id.in_(docs))).all()))
    obligations = {r['reference'] for r in rows if r['source'] == 'obligation'}
    if obligations and has_table(db, 'fiscal_records'):
        from .fiscal_control import catalog, records

        for ident, label, period in db.execute(
            select(records.c.id, catalog.c.label, records.c.period_id)
            .join(catalog, catalog.c.id == records.c.obligation_id)
            .where(records.c.id.in_(obligations))
        ):
            out[ident] = f'{label} · {period}'
    certs = {r['reference'] for r in rows if r['source'] == 'certificate'}
    if certs:
        from .credential_models import certificates

        for ident, kind, until in db.execute(
            select(certificates.c.id, certificates.c.kind, certificates.c.valid_until).where(
                certificates.c.id.in_(certs)
            )
        ):
            name = {'fiel': 'FIEL', 'csd': 'Sello digital (CSD)'}.get(kind, 'Certificado')
            out[ident] = name + (' · vigencia al ' + until.date().isoformat() if until else '')
    return out


def feed(db, p, *, view, offset, limit, severity=None, kind=None, company_id=None, q=None):
    from .credential_models import alerts
    from .lote4_lifecycle import history, tracking

    lifecycle = sync(db)
    ids, cert_ids = visible(db, p)
    names = dict(db.execute(select(Company.id, Company.name).where(Company.id.in_(ids))).all())
    if lifecycle:
        rows = [
            {**dict(r), 'revision': r['revision'], 'snooze_until': r['snooze_until']}
            for r in db.execute(
                select(alerts, tracking.c.revision, tracking.c.snooze_until)
                .join(tracking, tracking.c.alert_id == alerts.c.id)
                .where(alerts.c.company_id.in_(ids))
            ).mappings()
        ]
    else:
        # Without the lifecycle tables: the live conditions only, all active and without actions.
        from .credential_alerts import alert_key

        rows = [
            {
                **c,
                'id': alert_key(c['source'], c['reference'], c['kind']),
                'state': 'pending',
                'generated_at': None,
                'revision': None,
                'snooze_until': None,
            }
            for c in all_candidates(db, p)
            if c['company_id'] in ids
        ]
    rows = [r for r in rows if r['source'] != 'certificate' or r['company_id'] in cert_ids]
    today = local_today()

    def is_active(r):
        return r['state'] in ACTIVE or (
            r['state'] == 'snoozed' and (not r['snooze_until'] or r['snooze_until'] <= today)
        )

    active = [r for r in rows if is_active(r)]
    shown = active if view == 'active' else [r for r in rows if not is_active(r)]
    kinds = sorted({r['kind'] for r in shown})
    text = (q or '').strip().casefold()
    labels = details(db, shown)
    shown = [
        r
        for r in shown
        if (not severity or r['priority'] == severity)
        and (not kind or r['kind'] == kind)
        and (not company_id or r['company_id'] == company_id)
        and (not text or text in (names.get(r['company_id'], '') + ' ' + labels.get(r['reference'], '')).casefold())
    ]
    # Chronological like an event log, the newest first; severity does not change the order.
    shown.sort(key=lambda r: (r['generated_at'] is not None, r['generated_at'] or 0, r['id']), reverse=True)
    page = shown[offset : offset + limit]
    closing = {}
    if lifecycle and page:
        for e in db.execute(
            select(history)
            .where(history.c.entity == 'alert', history.c.reference.in_([r['id'] for r in page]))
            .order_by(history.c.created_at)
        ).mappings():
            closing[e['reference']] = e
    users = {}
    actors = {e['actor_id'] for e in closing.values()}
    if actors:
        users = dict(
            db.execute(select(UserAccount.id, UserAccount.display_name).where(UserAccount.id.in_(actors))).all()
        )

    def item(r):
        e = closing.get(r['id'])
        status = 'active' if is_active(r) else 'snoozed' if r['state'] == 'snoozed' else r['state']
        return {
            'id': r['id'],
            'company_id': r['company_id'],
            'company_name': names.get(r['company_id'], 'Empresa'),
            'source': r['source'],
            'reference': r['reference'],
            'kind': r['kind'],
            'priority': r['priority'],
            'generated_at': r['generated_at'],
            'due_at': r['due_at'],
            'state': status,
            'revision': r['revision'],
            'snooze_until': r['snooze_until'],
            'detail': labels.get(r['reference'], ''),
            # Last lifecycle event: who closed, snoozed or reopened it, when and why.
            'changed_at': e['created_at'] if e else None,
            'changed_by': (
                'Sistema' if e and e['actor_id'] == SYSTEM.subject else users.get(e['actor_id'], '') if e else ''
            ),
            'reason': e['reason'] if e and e['actor_id'] != SYSTEM.subject else '',
        }

    return {
        'alerts': [item(r) for r in page],
        'total': len(shown),
        'offset': offset,
        'limit': limit,
        'active_total': len(active),
        'active_high': sum(1 for r in active if r['priority'] == 'high'),
        'kinds': kinds,
        'lifecycle_available': lifecycle,
    }


def register(router):
    @router.get('/alert-feed')
    def alert_feed(
        response: Response,
        p: Principal = Depends(auth),
        db=Depends(session),
        view: Literal['active', 'history'] = 'active',
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
        severity: Literal['low', 'medium', 'high'] | None = None,
        kind: Annotated[str | None, Query(max_length=40)] = None,
        company_id: str | None = None,
        q: Annotated[str | None, Query(max_length=100)] = None,
    ):
        response.headers['Cache-Control'] = 'no-store'
        if company_id:
            p.require_company(company_id)
        return feed(
            db, p, view=view, offset=offset, limit=limit, severity=severity, kind=kind, company_id=company_id, q=q
        )
