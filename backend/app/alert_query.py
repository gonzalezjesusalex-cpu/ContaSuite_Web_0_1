"""Authorization and filters precede SQL counting/paging. No content providers."""
from fastapi import HTTPException
from sqlalchemy import select,func,or_,and_
from .models import Company
from .credential_models import alerts,grants
from .company_lifecycle import archive_metadata
from .lote4_lifecycle import available,tracking
def query_alerts(db,p,*,offset=0,limit=50,company_id=None,state=None,source=None,priority=None,include_archived=False):
    if company_id:p.require_company(company_id)
    companies=list(db.scalars(select(Company.id).where(True if p.admin else Company.id.in_(p.company_ids))))
    archive_ready,archive=archive_metadata(db,companies)
    ids=[cid for cid in companies if (not company_id or cid==company_id) and (include_archived or not archive.get(cid,{}).get('archived',False))]
    scope=alerts.c.company_id.in_(ids)
    if not p.admin:
        metadata_ids=select(grants.c.company_id).where(grants.c.user_id==p.subject,grants.c.permission=='metadata')
        scope=and_(scope,or_(alerts.c.source=='obligation',alerts.c.company_id.in_(metadata_ids)))
    filters=[scope]
    for col,value in [(alerts.c.state,state),(alerts.c.source,source),(alerts.c.priority,priority)]:
        if value:filters.append(col==value)
    total=db.scalar(select(func.count()).select_from(alerts).where(*filters))
    rows=list(db.execute(select(alerts).where(*filters).order_by(alerts.c.generated_at.desc(),alerts.c.id).offset(offset).limit(limit)).mappings())
    info={}
    if available(db) and rows:info={r['alert_id']:r for r in db.execute(select(tracking).where(tracking.c.alert_id.in_([r['id'] for r in rows]))).mappings()}
    counts=dict(db.execute(select(alerts.c.state,func.count()).where(*filters).group_by(alerts.c.state)).all())
    return dict(alerts=[{**dict(r),'revision':info[r['id']]['revision'] if r['id'] in info else None,'snooze_until':info[r['id']]['snooze_until'] if r['id'] in info else None} for r in rows],total=total,offset=offset,limit=limit,counts=counts,archive_available=archive_ready,refresh_required=True)
