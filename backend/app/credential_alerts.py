"""Explicit, scoped local reconciliation. No scheduler or external network calls."""
import hashlib
from typing import Annotated
from zoneinfo import ZoneInfo
from datetime import datetime,timezone,date
from fastapi import Depends,Response,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,update,inspect
from .credential_api import router,ready,no_cache,allowed,event,temporal
from .credential_models import certificates,alerts,settings
from .database import session
from .models import Company,now
from .security import auth,Principal

def alert_key(source,reference,kind):return hashlib.sha256(f'{source}:{reference}:{kind}'.encode()).hexdigest()
def candidates(db,p,stamp=None):
    result=[];visible=[];local_today=(stamp or now()).astimezone(ZoneInfo('America/Mexico_City')).date()
    for cid in db.scalars(select(Company.id)):
        try:allowed(p,db,cid,'metadata');visible.append(cid)
        except HTTPException:pass
    thresholds=[30,15,7]
    from .lote4_lifecycle import available,current
    selection=set(db.scalars(select(current.c.certificate_id))) if available(db) else None
    for row in db.execute(select(certificates).where(certificates.c.company_id.in_(visible))).mappings():
        if selection is not None and row['id'] not in selection:continue
        state=temporal(row,thresholds,stamp=stamp)['state']
        if state!='valid':result.append(dict(company_id=row['company_id'],source='certificate',reference=row['id'],kind=row['kind']+'_'+state+'_'+str(temporal(row,thresholds,stamp=stamp)['threshold'] or 0),priority='high' if state=='expired' else 'medium',due_at=row['valid_until']))
    # Fiscal tables remain untouched, and may not yet exist in this installation.
    if inspect(db.connection()).has_table('fiscal_records'):
        from .fiscal_control import records,evidence,effective
        fiscal_ids=list(db.scalars(select(Company.id))) if p.admin else list(p.company_ids)
        for row in db.execute(select(records).where(records.c.company_id.in_(fiscal_ids))).mappings():
            types=[];state=effective(row,today=local_today)
            if state=='overdue':types.append(('overdue','high'))
            elif row['due_verified'] and row['due_date'] and 0<=(row['due_date']-local_today).days<=15 and state in ('pending','in_progress'):types.append(('due_soon','medium'))
            if state=='unreviewed':types.append(('unreviewed','medium'))
            condition=None
            if state=='fulfilled' and inspect(db.connection()).has_table('fiscal_verification_decisions'):
                from .evidence_history import review_condition
                verified,condition=review_condition(db,row)
                if not verified:types.append(('evidence_review','low'))
            for kind,priority in types:result.append(dict(company_id=row['company_id'],source='obligation',reference=row['id'],kind=kind,priority=priority,due_at=datetime.combine(row['due_date'],datetime.min.time(),tzinfo=timezone.utc) if row['due_date'] and row['due_verified'] else None))
            if condition and types and types[-1][0]=='evidence_review':result[-1]['_condition']=condition
    return result

@router.post('/alerts/refresh')
def refresh(response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);p.require_admin()
    from .lote4_lifecycle import evaluate_sources,invoke
    return invoke(db,lambda:evaluate_sources(db,p))

@router.get('/alerts')
def list_alerts(response:Response,p:Principal=Depends(auth),db=Depends(session),offset:Annotated[int,Query(ge=0)]=0,limit:Annotated[int,Query(ge=1,le=200)]=50,company_id:str|None=None,state:str|None=None,source:str|None=None,priority:str|None=None,include_archived:bool=False):
    no_cache(response);ready(db)
    from .alert_query import query_alerts
    return query_alerts(db,p,offset=offset,limit=limit,company_id=company_id,state=state,source=source,priority=priority,include_archived=include_archived)

class ThresholdsIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    days:list[int]=Field(min_length=1,max_length=5)
@router.put('/alerts/settings')
def configure(payload:ThresholdsIn,response:Response,p:Principal=Depends(auth),db=Depends(session)):
    no_cache(response);ready(db);p.require_admin()
    if any(d<1 or d>365 for d in payload.days):raise HTTPException(422,'Umbrales entre 1 y 365 días.')
    days=sorted(set(payload.days),reverse=True)
    db.execute(update(settings).where(settings.c.id==1).values(thresholds=days));event(db,p,None,'alert_settings_changed',details={'days':days});db.commit();return {'days':days}
