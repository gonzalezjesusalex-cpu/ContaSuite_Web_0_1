from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select,inspect
from .credential_models import certificates,alerts
from .credential_api import allowed,temporal
from .lote4_lifecycle import available,current
from .fiscal_read import cutoff

def summary(db,p,company_ids,entries):
    if not available(db):return {'available':False,'reason':'lote4_lifecycle_0001 pendiente'}
    ids=set(company_ids);certificate_ids=set();expiring=expired=0
    for r in db.execute(select(certificates).join(current,current.c.certificate_id==certificates.c.id).where(certificates.c.company_id.in_(ids))).mappings():
        try:allowed(p,db,r['company_id'],'metadata')
        except HTTPException as exc:
            if exc.status_code in (403,404):continue
            raise
        certificate_ids.add(r['id']);state=temporal(r,[30,15,7])['state']
        expiring+=state=='expiring';expired+=state=='expired'
    record_ids={r['id'] for r in entries};pending=0
    for r in db.execute(select(alerts).where(alerts.c.company_id.in_(ids),alerts.c.state=='pending')).mappings():
        if (r['source']=='certificate' and r['reference'] in certificate_ids) or (r['source']=='obligation' and r['reference'] in record_ids and r['kind']!='documentation_review'):pending+=1
    day=cutoff();soon=overdue=0
    from datetime import date
    for r in entries:
        if not r['due_verified'] or not r['due_date'] or r['status'] not in ('pending','in_progress'):continue
        due=date.fromisoformat(r['due_date']);soon+=day<=due<=day+timedelta(days=15);overdue+=due<day
    evidence_ready=inspect(db.connection()).has_table('fiscal_verification_decisions')
    evidence_pending=None
    if evidence_ready:
        from .evidence_history import review_condition
        evidence_pending=sum(not review_condition(db,r)[0] for r in entries if r['status']=='fulfilled')
    return dict(available=True,pending_alerts=pending,expiring_certificates=expiring,expired_certificates=expired,
                upcoming_obligations=soon,overdue_obligations=overdue,evidence_pending=evidence_pending,
                evidence_reason='Revisión de evidencia; no modifica cumplimiento declarado ni pago' if evidence_ready else 'Historial de verificaciones pendiente de migración explícita',
                scope='Obligaciones del periodo filtrado; certificados actuales a fecha de corte; alertas persistidas',cutoff=day.isoformat())
