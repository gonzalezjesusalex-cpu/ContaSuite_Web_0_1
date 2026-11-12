"""Read-only calendar over existing records. No providers, rules or automatic writes."""
import calendar
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from urllib.parse import urlencode
from fastapi import Depends, Query
from sqlalchemy import select, inspect
from .database import session
from .security import auth, Principal, utc
from .models import Company
from .company_lifecycle import archive_metadata
from .fiscal_read import cutoff

def window(anchor, view):
    if view == 'month':
        return anchor.replace(day=1), anchor.replace(day=calendar.monthrange(anchor.year,anchor.month)[1])
    if view == 'week':
        start=anchor-timedelta(days=anchor.weekday());return start,start+timedelta(days=6)
    return anchor,anchor+timedelta(days=30)

def events(db,p,anchor,view='month',company_id=None,kind=None,state=None,include_archived=False):
    if company_id:p.require_company(company_id)
    companies=list(db.scalars(select(Company).where(True if p.admin else Company.id.in_(p.company_ids))))
    available,archive=archive_metadata(db,[c.id for c in companies])
    ids={c.id for c in companies if (not company_id or c.id==company_id) and (include_archived or not archive.get(c.id,{}).get('archived',False))}
    start,end=window(anchor,view);rows=[];sources={'obligations':False,'certificates':False}
    if inspect(db.connection()).has_table('fiscal_records'):
        from .fiscal_control import records,catalog,periods,ready,effective
        ready(db);sources['obligations']=True
        names=dict(db.execute(select(catalog.c.id,catalog.c.label)).all())
        for r in db.execute(select(records).where(records.c.company_id.in_(ids),records.c.due_verified==True,records.c.due_date>=start,records.c.due_date<=end)).mappings():
            period_start=db.scalar(select(periods.c.start_date).where(periods.c.id==r['period_id']))
            rows.append(dict(id='obligation:'+r['id'],company_id=r['company_id'],source='fiscal_records',reference=r['id'],period=r['period_id'],date=r['due_date'].isoformat(),date_type='confirmed_due',kind='obligation',title=names.get(r['obligation_id'],r['obligation_id']),state=effective(r,cutoff()),provenance='office_confirmed_record',href='/empresas/'+r['company_id']+'?'+urlencode({'tab':'Obligaciones','period':(period_start or r['due_date']).strftime('%Y-%m')})))
    if inspect(db.connection()).has_table('vault_certificates'):
        from .credential_models import certificates
        from .credential_api import ready,allowed,temporal
        ready(db);sources['certificates']=True
        authorized=[]
        from fastapi import HTTPException
        for cid in ids:
            try:allowed(p,db,cid,'metadata');authorized.append(cid)
            except HTTPException as exc:
                if exc.status_code not in (403,404):raise
        for r in db.execute(select(certificates).where(certificates.c.company_id.in_(authorized))).mappings():
            if not r['valid_until']:continue
            day=utc(r['valid_until']).astimezone(ZoneInfo('America/Mexico_City')).date()
            if start<=day<=end:
                rows.append(dict(id='certificate:'+r['id'],company_id=r['company_id'],source='vault_certificates',reference=r['id'],period=None,date=day.isoformat(),date_type='recorded_certificate_expiry',kind='certificate',title='Certificado '+r['kind'],state=temporal(r,[30,15,7])['state'],provenance=r['origin'],current_selection='unknown',sat_state='undetermined',href='/empresas/'+r['company_id']+'?tab=FIEL%2FCSD'))
    from .lote4_lifecycle import available as lifecycle_available,dates
    if lifecycle_available(db):
        for r in db.execute(select(dates).where(dates.c.company_id.in_(ids),dates.c.date>=start,dates.c.date<=end)).mappings():
            rows.append(dict(id='manual:'+r['id'],company_id=r['company_id'],source='calendar_manual_dates',reference=r['id'],period=r['period_id'],date=r['date'].isoformat(),date_type='verified_rule' if r['rule_id'] else 'manual',kind='manual',title=r['title'],state='recorded',provenance=('rule:'+r['rule_id']+':'+str(r['rule_version'])) if r['rule_id'] else 'authorized_manual',href='/empresas/'+r['company_id']+'?tab=Obligaciones'))
    rows=[r for r in rows if (not kind or r['kind']==kind) and (not state or r['state']==state)]
    rows=sorted({r['id']:r for r in rows}.values(),key=lambda r:(r['date'],r['id']))
    return dict(start=start.isoformat(),end=end.isoformat(),timezone='America/Mexico_City',events=rows,count=len(rows),sources=sources,archive_available=available,limitations=['Read only; no legal dates inferred','Certificate history included; current selection is not represented','Dates do not establish tax compliance'])

def register(router):
    @router.get('/calendar')
    def read_calendar(anchor:date,view:Literal['month','week','upcoming']='month',company_id:str|None=None,kind:Literal['obligation','certificate','manual']|None=None,state:str|None=None,include_archived:bool=False,p:Principal=Depends(auth),db=Depends(session)):
        return events(db,p,anchor,view,company_id,kind,state,include_archived)
