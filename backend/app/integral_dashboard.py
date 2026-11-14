"""Read-only integration over existing modules; missing migrations remain explicit."""

from collections import Counter
from datetime import date
from zoneinfo import ZoneInfo
from sqlalchemy import select, or_, and_, exists as sql_exists
from fastapi import HTTPException
from .models import (
    Company,
    Document,
    DocumentCompanyLink,
    StorageSource,
    StorageIndexJob,
    DocumentVersion,
    DocumentLocation,
    Task,
    UserAccount,
    DocumentClassificationReview,
    now,
)
from .storage.catalog import DocumentCatalog
from .company_reconcile import normalized_name
from .storage.classifier import valid_rfc
from .integral_models import activity, verification, classified, quality, opinions, cfdi_reviews, relations
from .schema_cache import has_table


def exists(db, name):
    return has_table(db, name)


def dashboard(db, p, year, month, company=None, regime=None, responsible=None, include_archived=False):
    companies = db.scalars(select(Company).where(True if p.admin else Company.id.in_(p.company_ids))).all()
    companies = [c for c in companies if (not company or c.id == company) and (not regime or c.regime == regime)]
    from .company_lifecycle import archive_metadata

    archive_ready, archive_rows = archive_metadata(db, [c.id for c in companies])
    if archive_ready and not company and not include_archived:
        companies = [c for c in companies if not archive_rows.get(c.id, {}).get('archived', False)]
    base_ids = {c.id for c in companies}
    today = now().astimezone(ZoneInfo('America/Mexico_City')).date()
    fiscal_available = exists(db, 'fiscal_records')
    entries = []
    definitions = []
    fiscal = None
    if fiscal_available:
        from .fiscal_read import read_period

        fiscal = read_period(db, p, year, month, company, regime, responsible, include_archived=include_archived)
        entries = fiscal['records']
        definitions = fiscal['catalog']
        scoped = {
            c['id']
            for c in fiscal['companies']
            if not responsible or any(r['company_id'] == c['id'] for r in fiscal['cells'])
        }
        companies = [c for c in companies if c.id in scoped]
    elif responsible:
        companies = [c for c in companies if c.accountant == responsible]
    owner = lambda r: r.get('responsible_name') or next(
        (c.accountant for c in companies if c.id == r['company_id']), 'Sin asignar'
    )
    ids = {c.id for c in companies}
    states = Counter(fiscal['summary']['counts']) if fiscal else Counter()
    verified_ids = {r['id'] for r in entries if r.get('verification_state') == 'verified'}
    verified = len(verified_ids)
    active = {
        r['company_id']: r['active']
        for r in db.execute(select(activity).where(activity.c.company_id.in_(ids))).mappings()
    }
    wanted = or_(
        Document.company_id.in_(ids),
        Document.id.in_(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id.in_(ids))),
    )
    if p.admin and not company and not regime and not responsible:
        wanted = or_(
            wanted,
            and_(
                Document.company_id.is_(None),
                ~sql_exists(
                    select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.document_id == Document.id)
                ),
            ),
        )
    # Summary requires identifiers only, never document payload/metadata for every row. Related rows are
    # selected with this scoped subquery instead of IN lists of every identifier, and narrowed to the final
    # document set in Python, so the result is the same without per-identifier bind parameters.
    scope = DocumentCatalog()._scope(p.storage_actor())
    in_scope = select(Document.id).where(scope, wanted)
    docs = list(db.execute(select(Document.id, Document.company_id).where(scope, wanted)))
    links = {d.id: set([d.company_id]) if d.company_id else set() for d in docs}
    for did, cid in db.execute(
        select(DocumentCompanyLink.document_id, DocumentCompanyLink.company_id).where(
            DocumentCompanyLink.document_id.in_(in_scope)
        )
    ):
        if did in links:
            links[did].add(cid)
    docs = [
        d
        for d in docs
        if links[d.id] & ids or (p.admin and not company and not regime and not responsible and not links[d.id])
    ]
    docids = {d.id for d in docs}
    linked_ids = set().union(*(links[d.id] & ids for d in docs)) if docs else set()
    # Current-version evidence for every obligation of the period in one query (was one query per record).
    evidence = {}
    if entries:
        for relation in db.execute(
            select(relations.c.target_id, relations.c.company_id, relations.c.document_id, relations.c.version_id)
            .join(DocumentVersion, DocumentVersion.id == relations.c.version_id)
            .join(Document, Document.id == relations.c.document_id)
            .where(
                relations.c.target_type == 'obligation',
                relations.c.target_id.in_({r['id'] for r in entries}),
                relations.c.document_id.in_(in_scope),
                DocumentVersion.number == Document.storage_revision,
            )
        ).mappings():
            if relation['document_id'] in docids:
                evidence.setdefault((relation['target_id'], relation['company_id']), []).append(
                    {
                        'document_id': relation['document_id'],
                        'version_id': relation['version_id'],
                        'verified_compliance': False,
                    }
                )
    for record in entries:
        record['virtual_evidence'] = list(evidence.get((record['id'], record['company_id']), []))
    ambiguous_ids = {
        r.document_id
        for r in db.scalars(
            select(DocumentClassificationReview).where(
                DocumentClassificationReview.document_id.in_(in_scope), DocumentClassificationReview.status == 'pending'
            )
        )
        if r.document_id in docids and (len(r.proposed_links) > 1 or r.evidence.get('ambiguities'))
    }
    confirmations = docids & set(
        db.scalars(
            select(classified.c.document_id)
            .join(DocumentVersion, DocumentVersion.id == classified.c.version_id)
            .join(Document, Document.id == classified.c.document_id)
            .where(
                classified.c.document_id.in_(in_scope),
                DocumentVersion.document_id == Document.id,
                DocumentVersion.number == Document.storage_revision,
            )
        )
    )
    certs = []
    cert_access = set()
    cert_available = exists(db, 'vault_certificates')
    if cert_available:
        from .credential_models import certificates, settings
        from .credential_api import allowed, temporal

        for cid in ids:
            try:
                allowed(p, db, cid, 'metadata')
                cert_access.add(cid)
            except HTTPException:
                pass
        thresholds = db.execute(select(settings.c.thresholds).where(settings.c.id == 1)).scalar() or [60, 30, 15]
        for row in db.execute(select(certificates).where(certificates.c.company_id.in_(cert_access))).mappings():
            t = (
                temporal(row, thresholds)
                if row['origin'] == 'cs_storage'
                else {'state': 'unknown', 'days_remaining': None}
            )
            days = t['days_remaining']
            band = (
                'unknown'
                if days is None
                else 'expired'
                if t['state'] == 'expired'
                else 'over_60'
                if days > 60
                else '31_60'
                if days > 30
                else '16_30'
                if days > 15
                else '0_15'
            )
            certs.append(
                dict(
                    id=row['id'],
                    company_id=row['company_id'],
                    kind=row['kind'],
                    origin=row['origin'],
                    valid_until=row['valid_until'],
                    reviewed_at=row['reviewed_at'],
                    state=t['state'],
                    days_remaining=days,
                    band=band,
                    authority_validated=False,
                )
            )
    alerts = []
    if cert_available:
        from .credential_alerts import candidates, alert_key

        entry_ids = {r['id'] for r in entries}
        for row in candidates(db, p):
            if row['company_id'] in ids and (row['source'] != 'obligation' or row['reference'] in entry_ids):
                alerts.append(
                    {
                        **row,
                        'id': alert_key(row['source'], row['reference'], row['kind']),
                        'href': '/empresas/'
                        + row['company_id']
                        + '?tab='
                        + ('Credenciales y Certificados' if row['source'] == 'certificate' else 'Cumplimiento'),
                        'live': True,
                    }
                )
    quality_items = []
    for c in companies:
        for code, bad in [
            ('invalid_or_missing_rfc', not valid_rfc(c.rfc)),
            ('missing_regime', not c.regime.strip()),
            ('missing_responsible', not c.accountant.strip() or c.accountant == 'Sin asignar'),
        ]:
            if bad:
                quality_items.append(dict(company_id=c.id, source='company', reference=c.id, code=code))
        if sum(normalized_name(x.name) == normalized_name(c.name) for x in companies) > 1:
            quality_items.append(
                dict(company_id=c.id, source='company', reference=c.id, code='possible_duplicate_name')
            )
    for d in docs:
        code = (
            'document_without_company'
            if not links[d.id]
            else 'document_pending_classification'
            if d.id not in confirmations
            else None
        )
        if code:
            quality_items.append(
                dict(company_id=next(iter(links[d.id] & ids), None), source='document', reference=d.id, code=code)
            )
        if len(links[d.id] if p.admin else links[d.id] & ids) > 1:
            quality_items.append(
                dict(
                    company_id=next(iter(links[d.id] & ids), None),
                    source='document',
                    reference=d.id,
                    code='shared_document_review',
                )
            )
    for q in db.execute(select(quality).where(quality.c.state == 'open', quality.c.company_id.in_(ids))).mappings():
        if q['source'] == 'certificate' and q['company_id'] not in cert_access:
            continue
        quality_items.append({k: q[k] for k in ('company_id', 'source', 'reference', 'code')})
    for q in quality_items:
        if q['company_id']:
            from .credential_alerts import alert_key

            alerts.append(
                dict(
                    id=alert_key('quality', q['reference'], q['code']),
                    company_id=q['company_id'],
                    source='quality',
                    reference=q['reference'],
                    kind=q['code'],
                    priority='medium',
                    href='/empresas/' + q['company_id'] + '?tab=Documentos',
                    live=True,
                )
            )
    alerts = list({a['id']: a for a in alerts}.values())
    sources = []
    last_scan = None
    access_errors = None
    if p.admin:
        sourceids = {
            source_id
            for source_id, document_id in db.execute(
                select(DocumentLocation.source_id, DocumentVersion.document_id)
                .join(DocumentVersion, DocumentVersion.id == DocumentLocation.version_id)
                .where(DocumentVersion.document_id.in_(in_scope))
                .distinct()
            )
            if document_id in docids
        }
        sources = [
            dict(id=s.id, state=s.check_state, enabled=s.enabled, checked_at=s.checked_at)
            for s in db.scalars(
                select(StorageSource).where(
                    StorageSource.id.in_(sourceids)
                    if (company or regime or responsible)
                    else StorageSource.kind != 'internal'
                )
            )
        ]
        jobs = list(
            db.scalars(
                select(StorageIndexJob)
                .where(StorageIndexJob.source_id.in_([s['id'] for s in sources]))
                .order_by(StorageIndexJob.created_at.desc())
                .limit(100)
            )
        )
        last_scan = next((j.completed_at for j in jobs if j.status == 'completed'), None)
        access_errors = sum(j.counters.get('errors', 0) for j in jobs)
    tasks = list(db.scalars(select(Task).where(Task.company_id.in_(ids))))
    workload = []
    for name in sorted({c.accountant or 'Sin asignar' for c in companies} | {owner(r) for r in entries}):
        workload.append(
            dict(
                responsible=name,
                companies=sum(c.accountant == name for c in companies),
                pending=sum(owner(r) == name and r['effective_status'] in ('pending', 'overdue') for r in entries),
                in_progress=sum(owner(r) == name and r['effective_status'] == 'in_progress' for r in entries),
                completed_tasks=sum(t.responsible == name and t.status == 'Completada' for t in tasks),
            )
        )
    from .lote4_summary import summary as lifecycle_summary

    lifecycle = lifecycle_summary(db, p, ids, entries)
    # The UI renders only these preview rows. Keep exact totals without sending
    # tens of thousands of review records with every summary refresh.
    quality_total = len(quality_items)
    alerts_total = len(alerts)
    quality_items = quality_items[:200]
    alerts = alerts[:100]
    return dict(
        quality_total=quality_total,
        alerts_total=alerts_total,
        lifecycle=lifecycle,
        period=f'{year}-{month:02d}',
        companies=[dict(id=c.id, name=c.name, rfc=c.rfc, regime=c.regime, responsible=c.accountant) for c in companies],
        company_counts={
            'registered': len(ids),
            'active_confirmed': sum(v is True for v in active.values()),
            'activity_unknown': len(ids) - len(active),
            'in_period': len({r['company_id'] for r in entries}) if fiscal_available else None,
        },
        obligations={
            'summary': fiscal['summary'] if fiscal else None,
            'cells': fiscal['cells'] if fiscal else [],
            'available': fiscal_available,
            'counts': dict(states) if fiscal_available else None,
            'verified_fulfilled': verified if fiscal_available else None,
            'fulfilled_unverified': states['fulfilled'] - verified if fiscal_available else None,
            'date_recorded_unverified': sum(bool(r['submitted_at']) and r['id'] not in verified_ids for r in entries)
            if fiscal_available
            else None,
            'records': entries,
            'catalog': definitions,
        },
        certificates={
            'available': cert_available,
            'metadata_authorized_companies': len(cert_access),
            'records': certs,
            'without_registered_certificate': len(cert_access - {r['company_id'] for r in certs})
            if cert_available
            else None,
        },
        documents={
            'indexed': len(docs),
            'associated': sum(bool(links[d.id] & ids) for d in docs),
            'pending': len(docids - confirmations),
            'ambiguous': len(ambiguous_ids),
            'companies_without_documents': len(ids - linked_ids),
            'sources': sources if p.admin else None,
            'last_successful_scan': last_scan,
            'recorded_errors_last_100_jobs': access_errors,
            'completeness_evaluated': False,
        },
        workload=workload,
        alerts=alerts,
        quality=quality_items,
        opinions=[dict(r) for r in db.execute(select(opinions).where(opinions.c.company_id.in_(ids))).mappings()],
        cfdi=[dict(r) for r in db.execute(select(cfdi_reviews).where(cfdi_reviews.c.company_id.in_(ids))).mappings()],
        limitations=[
            'Active companies require explicit confirmation',
            'Documents do not prove compliance',
            'No SAT/IMSS queries',
            'Global source diagnostics restricted to admins',
        ],
    )
