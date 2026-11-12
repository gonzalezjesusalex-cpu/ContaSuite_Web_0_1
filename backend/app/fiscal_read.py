"""Scoped fiscal read contract. No writes, migrations, source files or providers."""
from collections import Counter
from datetime import date
from zoneinfo import ZoneInfo
from sqlalchemy import select, inspect
from .models import Obligation, Document, DocumentVersion, DocumentCompanyLink, now


def cutoff():
    return now().astimezone(ZoneInfo('America/Mexico_City')).date()


def indicators(cells):
    # Identity includes the real period: annual/quarterly rows are never summed twice.
    cells = list({r['cell_key']: r for r in cells}.values())
    states = Counter(r['effective_status'] for r in cells)
    base_states = Counter(r['status'] for r in cells)
    counts = {s: states[s] for s in ('fulfilled', 'pending', 'in_progress', 'not_applicable', 'unreviewed', 'overdue')}
    registered = sum(r['persisted'] for r in cells)
    fulfilled = sum(r['status'] == 'fulfilled' for r in cells)
    verified = sum(r['verification_state'] == 'verified' for r in cells)
    attention = 'Crítico' if counts['overdue'] else 'Requiere revisión' if counts['pending'] or counts['in_progress'] or counts['unreviewed'] or fulfilled > verified else 'Sin pendientes' if cells else 'Sin información'
    return dict(attention_state=attention, counts=counts, base_counts=dict(base_states), universe=len(cells), registered=registered,
                implicit=len(cells)-registered, applicable_confirmed=sum(r['applicability'] is True for r in cells),
                applicability_unknown=sum(r['applicability'] is None for r in cells),
                verified_fulfilled=verified, fulfilled_unverified=fulfilled-verified,
                confirmed_due=sum(bool(r['due_verified'] and r['due_date']) for r in cells),
                denominators={'states': len(cells), 'capture': len(cells), 'verification': fulfilled,
                              'confirmed_due': registered},
                date_recorded_unverified=sum(bool(r['submitted_at']) and r['verification_state'] != 'verified' for r in cells))


def historical(db, principal, company_ids, period):
    """Original values stay intact; ambiguous periods never acquire fiscal conclusions."""
    company_ids = set(company_ids) if principal.admin else set(company_ids) & principal.company_ids
    rows = db.scalars(select(Obligation).where(Obligation.company_id.in_(company_ids))).all()
    result = []
    for row in rows:
        principal.require_company(row.company_id)
        try:
            parsed = date.fromisoformat(row.period + '-01')
            reliable = parsed.strftime('%Y-%m') == row.period
        except (ValueError, TypeError):
            reliable = False
        if reliable and row.period != period:
            continue
        result.append(dict(id=row.id, company_id=row.company_id, title=row.title, period=row.period,
                           due_date=row.due_date.isoformat() if row.due_date else None,
                           status=row.status, reference=row.reference, notes=row.notes,
                           provenance='obligations', period_reliable=reliable,
                           verification_state='unknown', effective_status=None,
                           payment_condition=None, actor_id=None, modified_at=None))
    return result


def read_period(db, principal, year, month, company_id=None, regime=None, responsible=None, filter_status=None, query=None, include_archived=False):
    from .fiscal_control import _matrix_data, period_key, effective, ready
    if company_id:
        principal.require_company(company_id)
    ready(db)
    data = _matrix_data(year, month, principal, db)
    companies = [c for c in data['companies'] if (not company_id or c['id'] == company_id) and (not regime or c['regime'] == regime)]
    companies = [c for c in companies if not query or query.casefold() in (c['name']+' '+c['rfc']).casefold()]
    from .company_lifecycle import archive_metadata
    archive_ready, archive_rows = archive_metadata(db, [c['id'] for c in companies])
    if archive_ready and not company_id and not include_archived:
        companies = [c for c in companies if not archive_rows.get(c['id'], {}).get('archived', False)]
    ids = {c['id'] for c in companies}
    entries = {(r['company_id'], r['obligation_id'], r['period_id']): r for r in data['records'] if r['company_id'] in ids}
    rules = {(r['company_id'], r['obligation_id']): r for r in data['applicability']}
    users = {u['id']: u['display_name'] for u in data['users']}
    day = cutoff()
    checks = {}
    if inspect(db.connection()).has_table('integral_compliance_verification'):
        from .integral_models import verification
        checks = {r['record_id']: r for r in db.execute(select(verification).where(verification.c.company_id.in_(ids))).mappings()}
    cells = []
    for c in companies:
        for d in data['catalog']:
            key = (c['id'], d['id'], period_key(year, month, d['periodicity']))
            row = entries.get(key)
            rule = rules.get(key[:2])
            # Rules have no effective period: expose them as current configuration only.
            app = rule['applicable'] if rule else None
            status = row['status'] if row else 'unreviewed'
            owner = users.get((row or {}).get('responsible_id') or (rule or {}).get('responsible_id')) or c['accountant'] or 'Sin asignar'
            if responsible and owner != responsible:
                continue
            item = dict(row) if row else dict(id=None, company_id=c['id'], obligation_id=d['id'], period_id=key[2],
                    status=status, responsible_id=(rule or {}).get('responsible_id'), submitted_at=None,
                    due_date=None, due_verified=False, payment='unknown', notes='', revision=0, evidence=[])
            item.update(cell_key='|'.join(key), persisted=bool(row), provenance='fiscal_records' if row else 'implicit',
                        concept=d['label'], applicability=app, applicability_scope='current_configuration',
                        applicability_conflict=bool(row and app is False and status != 'not_applicable'),
                        payment_condition=None, responsible_name=owner, verification_state='unverified',
                        effective_status=effective({**row, 'due_date': date.fromisoformat(row['due_date']) if row['due_date'] else None}, day) if row else status)
            check = checks.get(item['id'])
            if check:
                doc = db.get(Document, check['document_id'])
                version = db.get(DocumentVersion, check['version_id'])
                owners = set(db.scalars(select(DocumentCompanyLink.company_id).where(DocumentCompanyLink.document_id == check['document_id'])))
                if doc and doc.company_id:
                    owners.add(doc.company_id)
                valid = (status == 'fulfilled' and check['record_revision'] == item['revision'] and
                         doc and version and version.document_id == doc.id and
                         version.number == doc.storage_revision and c['id'] in owners and check['company_id'] == c['id'])
                from .document_identity import verification_allowed
                valid=valid and verification_allowed(db,check['version_id'],check['verified_at'])
                item['verification_state'] = 'verified' if valid else 'stale'
                item['verification'] = {k: str(check[k]) for k in ('record_revision', 'document_id', 'version_id', 'actor_id', 'verified_at')}
            cells.append(item)
    cells = [r for r in cells if not filter_status or r['effective_status'] == filter_status]
    summary = indicators(cells)
    data.update(companies=companies, records=[r for r in cells if r['persisted']], cells=cells,
                contract='fiscal-read-v1', period=f'{year}-{month:02d}', cutoff=day.isoformat(),
                timezone='America/Mexico_City', summary=summary,
                responsible_summaries={name: indicators([r for r in cells if r['responsible_name'] == name]) for name in {r['responsible_name'] for r in cells}},
                concept_summaries={d['id']: indicators([r for r in cells if r['obligation_id'] == d['id']]) for d in data['catalog']},
                company_summaries={c['id']: indicators([r for r in cells if r['company_id'] == c['id']]) for c in companies},
                historical=historical(db, principal, ids, f'{year}-{month:02d}'),
                limitations=['Applicability is current configuration, not historical determination',
                             'Payment condition is not represented by the canonical schema',
                             'Historical records are excluded from canonical indicators'])
    data['applicability'] = [r for r in data['applicability'] if r['company_id'] in ids]
    return data
