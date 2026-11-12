"""Additive lifecycle metadata; existing certificates/alerts remain the source identities."""
from uuid import uuid4
from datetime import date,datetime
import hashlib,json
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import MetaData,Table,Column,String,Integer,Date,DateTime,JSON,ForeignKey,select,update,inspect,text
from sqlalchemy.exc import IntegrityError
from .models import Company,now
from .fiscal_read import cutoff
from .credential_models import certificates,alerts
from .credential_api import allowed,ready as vault_ready
from .database import session
from .security import auth,Principal,utc

metadata=MetaData()
current=Table('certificate_current_selection',metadata,Column('company_id',ForeignKey(Company.id),primary_key=True),Column('kind',String(10),primary_key=True),Column('certificate_id',ForeignKey(certificates.c.id),nullable=False),Column('revision',Integer,nullable=False))
renewals=Table('certificate_renewals',metadata,Column('certificate_id',ForeignKey(certificates.c.id),primary_key=True),Column('previous_id',ForeignKey(certificates.c.id),nullable=False))
tracking=Table('alert_lifecycle',metadata,Column('alert_id',ForeignKey(alerts.c.id),primary_key=True),Column('revision',Integer,nullable=False),Column('condition_hash',String(64),nullable=False),Column('snooze_until',Date),Column('updated_at',DateTime(timezone=True),nullable=False))
history=Table('lote4_action_history',metadata,Column('id',String(36),primary_key=True),Column('company_id',ForeignKey(Company.id),nullable=False),Column('entity',String(20),nullable=False),Column('reference',String(100),nullable=False),Column('actor_id',String(100),nullable=False),Column('created_at',DateTime(timezone=True),nullable=False),Column('before',JSON),Column('after',JSON,nullable=False),Column('reason',String(1000),nullable=False))
rules=Table('calendar_verified_rules',metadata,Column('id',String(36),primary_key=True),Column('version',Integer,primary_key=True),Column('company_id',ForeignKey(Company.id),nullable=False),Column('obligation_id',String(36),nullable=False),Column('period_id',String(12),nullable=False),Column('date',Date,nullable=False),Column('source_reference',String(1000),nullable=False),Column('actor_id',String(100),nullable=False))
dates=Table('calendar_manual_dates',metadata,Column('id',String(36),primary_key=True),Column('company_id',ForeignKey(Company.id),nullable=False),Column('title',String(180),nullable=False),Column('date',Date,nullable=False),Column('period_id',String(12),nullable=False),Column('obligation_id',String(36),nullable=False),Column('rule_id',String(36)),Column('rule_version',Integer),Column('revision',Integer,nullable=False))

def available(db):
    i=inspect(db.connection())
    return all(i.has_table(t.name) and {c.name for c in t.columns}<={c['name'] for c in i.get_columns(t.name)} for t in metadata.tables.values())
def lock(db):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(440041)'))
def ready(db):
    if not available(db):raise HTTPException(503,'Ciclo de vida del Lote 4 pendiente de migración explícita autorizada.')
def serial(value):
    return json.loads(json.dumps(dict(value),default=lambda v:v.isoformat())) if value is not None else None
def event(db,p,cid,entity,reference,before,after,reason):
    db.execute(history.insert().values(id=str(uuid4()),company_id=cid,entity=entity,reference=reference,actor_id=p.subject,created_at=now(),before=serial(before),after=serial(after),reason=reason))
def write_access(db,p,cid,permission=None):
    p.require_company(cid,write=True)
    if not db.get(Company,cid):raise HTTPException(404,'Empresa no encontrada.')
    if permission:allowed(p,db,cid,permission)

class SelectionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    certificate_id:str
    previous_id:str|None=None
    revision:int=Field(ge=0)
    reason:str=Field(min_length=3,max_length=1000)

def select_certificate(db,p,cid,payload):
    ready(db);lock(db);vault_ready(db);write_access(db,p,cid,'certificates')
    row=db.execute(select(certificates).where(certificates.c.id==payload.certificate_id,certificates.c.company_id==cid)).mappings().first()
    if not row:raise HTTPException(404,'Certificado no disponible.')
    if row['kind'] not in ('fiel','csd') or not row['fingerprint']:raise HTTPException(422,'Revisa clasificación e identidad pública antes de seleccionar.')
    old=db.execute(select(current).where(current.c.company_id==cid,current.c.kind==row['kind'])).mappings().first()
    if (old['revision'] if old else 0)!=payload.revision:raise HTTPException(409,'Selección concurrente; actualiza.')
    renewal_changed=False
    if payload.previous_id:
        previous=db.execute(select(certificates).where(certificates.c.id==payload.previous_id,certificates.c.company_id==cid,certificates.c.kind==row['kind'])).mappings().first()
        if not previous or previous['id']==row['id'] or previous['fingerprint']==row['fingerprint']:raise HTTPException(422,'Renovación inválida o contenido duplicado.')
        seen={row['id']};cursor=previous['id']
        while cursor:
            if cursor in seen:raise HTTPException(409,'Ciclo de renovaciones rechazado.')
            seen.add(cursor);cursor=db.scalar(select(renewals.c.previous_id).where(renewals.c.certificate_id==cursor))
        link=db.scalar(select(renewals.c.previous_id).where(renewals.c.certificate_id==row['id']))
        if link and link!=previous['id']:raise HTTPException(409,'La renovación ya tiene antecedente; conservar historial.')
        if not link:
            db.execute(renewals.insert().values(certificate_id=row['id'],previous_id=previous['id']));renewal_changed=True
    if old and old['certificate_id']==row['id']:
        if renewal_changed:event(db,p,cid,'certificate',row['id'],old,old,payload.reason)
        db.commit();return dict(old)
    values=dict(certificate_id=row['id'],revision=payload.revision+1)
    if old:
        if not db.execute(update(current).where(current.c.company_id==cid,current.c.kind==row['kind'],current.c.revision==payload.revision).values(**values)).rowcount:raise HTTPException(409,'Selección concurrente.')
    else:db.execute(current.insert().values(company_id=cid,kind=row['kind'],**values))
    event(db,p,cid,'certificate',row['id'],old,{**values,'previous_id':payload.previous_id},payload.reason);db.commit()
    return values

class ActionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    state:Literal['pending','acknowledged','snoozed','resolved','obsolete']
    revision:int=Field(ge=0)
    reason:str=Field(min_length=3,max_length=1000)
    snooze_until:date|None=None

def alert_action(db,p,ident,payload):
    ready(db);lock(db)
    row=db.execute(select(alerts).where(alerts.c.id==ident)).mappings().first()
    if not row:raise HTTPException(404,'Alerta no encontrada.')
    write_access(db,p,row['company_id'],'alerts')
    old=db.execute(select(tracking).where(tracking.c.alert_id==ident)).mappings().first()
    if not old:raise HTTPException(409,'Evalúa la alerta con el motor compatible antes de cambiar su estado.')
    if old['revision']!=payload.revision:raise HTTPException(409,'Alerta concurrente; actualiza.')
    if payload.state=='snoozed' and (not payload.snooze_until or payload.snooze_until<=cutoff()):raise HTTPException(422,'Elige una fecha futura.')
    if not db.execute(update(tracking).where(tracking.c.alert_id==ident,tracking.c.revision==payload.revision).values(revision=payload.revision+1,snooze_until=payload.snooze_until if payload.state=='snoozed' else None,updated_at=now())).rowcount:raise HTTPException(409,'Alerta concurrente.')
    db.execute(update(alerts).where(alerts.c.id==ident).values(state=payload.state))
    event(db,p,row['company_id'],'alert',ident,{**row,**old},{'state':payload.state,'revision':payload.revision+1,'snooze_until':payload.snooze_until},payload.reason);db.commit()
    return {'state':payload.state,'revision':payload.revision+1}

def evaluate(db,p,candidates,*,commit=True,today=None):
    ready(db);lock(db);p.require_admin()
    active=set()
    from .credential_alerts import alert_key
    for item in candidates:
        if item['source'] not in ('certificate','obligation') or item['kind']=='documentation_review':continue
        ident=alert_key(item['source'],item['reference'],item['kind']);active.add(ident)
        digest=hashlib.sha256(json.dumps(serial(item),sort_keys=True).encode()).hexdigest()
        item={k:v for k,v in item.items() if k!='_condition'}
        row=db.execute(select(alerts).where(alerts.c.id==ident)).mappings().first()
        old=db.execute(select(tracking).where(tracking.c.alert_id==ident)).mappings().first()
        changed=not old or old['condition_hash']!=digest
        expired=old and row and row['state']=='snoozed' and old['snooze_until'] and old['snooze_until']<=(today or cutoff())
        if old and not changed and not expired and row['state']!='obsolete':continue
        revision=(old['revision'] if old else 0)+1
        if row:db.execute(update(alerts).where(alerts.c.id==ident).values(**item,state='pending'))
        else:db.execute(alerts.insert().values(id=ident,generated_at=now(),state='pending',**item))
        values=dict(revision=revision,condition_hash=digest,snooze_until=None,updated_at=now())
        if old:db.execute(update(tracking).where(tracking.c.alert_id==ident).values(**values))
        else:db.execute(tracking.insert().values(alert_id=ident,**values))
        event(db,p,item['company_id'],'alert',ident,row,{'state':'pending','revision':revision,'condition_hash':digest},'source_changed' if changed else 'snooze_elapsed')
    # Only managed alerts are aged out; unavailable documentary sources are untouched.
    for row in db.execute(select(alerts).join(tracking,tracking.c.alert_id==alerts.c.id)).mappings():
        if row['id'] not in active and row['kind']!='documentation_review' and row['state']!='obsolete':
            db.execute(update(alerts).where(alerts.c.id==row['id']).values(state='obsolete'))
            db.execute(update(tracking).where(tracking.c.alert_id==row['id']).values(revision=tracking.c.revision+1,updated_at=now()))
            event(db,p,row['company_id'],'alert',row['id'],row,{'state':'obsolete'},'source_absent')
    if commit:db.commit()
    return {'evaluated':len(active)}

class DateIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_id:str
    obligation_id:str
    period_id:str
    title:str=Field(min_length=2,max_length=180)
    date:date
    revision:int=Field(ge=0)
    reason:str=Field(min_length=3,max_length=1000)
    rule_id:str|None=None
    rule_version:int|None=None

class RuleIn(DateIn):
    source_reference:str=Field(min_length=3,max_length=1000)

def save_rule(db,p,ident,payload):
    ready(db);lock(db);p.require_admin();write_access(db,p,payload.company_id)
    from .fiscal_control import catalog,periods,applicability
    if not db.scalar(select(catalog.c.id).where(catalog.c.id==payload.obligation_id)) or not db.scalar(select(periods.c.id).where(periods.c.id==payload.period_id)):raise HTTPException(422,'Concepto/periodo inexistente.')
    app=db.execute(select(applicability).where(applicability.c.company_id==payload.company_id,applicability.c.obligation_id==payload.obligation_id)).mappings().first()
    if not app or not app['applicable']:raise HTTPException(422,'Aplicabilidad no confirmada.')
    definition=db.execute(select(catalog).where(catalog.c.id==payload.obligation_id)).mappings().one()
    period=db.execute(select(periods).where(periods.c.id==payload.period_id)).mappings().one()
    from .fiscal_control import period_key
    if period_key(period['start_date'].year,period['start_date'].month,definition['periodicity'])!=payload.period_id:raise HTTPException(422,'Periodicidad incompatible con la regla.')
    previous=db.execute(select(rules).where(rules.c.id==ident).order_by(rules.c.version.desc())).mappings().first()
    if previous and previous['company_id']!=payload.company_id:raise HTTPException(422,'Regla de otra empresa.')
    if (previous['version'] if previous else 0)!=payload.revision:raise HTTPException(409,'Versión concurrente.')
    version=payload.revision+1
    values={k:getattr(payload,k) for k in ('company_id','obligation_id','period_id','date','source_reference')}
    db.execute(rules.insert().values(id=ident,version=version,actor_id=p.subject,**values))
    event(db,p,payload.company_id,'rule',ident,previous,{**values,'version':version},payload.reason);db.commit()
    return {'id':ident,'version':version}

def save_date(db,p,ident,payload):
    ready(db);lock(db);write_access(db,p,payload.company_id)
    from .fiscal_control import catalog,periods,applicability
    if not db.scalar(select(catalog.c.id).where(catalog.c.id==payload.obligation_id)) or not db.scalar(select(periods.c.id).where(periods.c.id==payload.period_id)):raise HTTPException(422,'Concepto/periodo inexistente.')
    app=db.execute(select(applicability).where(applicability.c.company_id==payload.company_id,applicability.c.obligation_id==payload.obligation_id)).mappings().first()
    definition=db.execute(select(catalog).where(catalog.c.id==payload.obligation_id)).mappings().one()
    period=db.execute(select(periods).where(periods.c.id==payload.period_id)).mappings().one()
    from .fiscal_control import period_key
    if period_key(period['start_date'].year,period['start_date'].month,definition['periodicity'])!=payload.period_id:raise HTTPException(422,'Periodicidad incompatible con el concepto.')
    if app and not app['applicable']:raise HTTPException(422,'Obligación configurada no aplicable; revisa el contexto.')
    if bool(payload.rule_id)!=(payload.rule_version is not None):raise HTTPException(422,'Regla y versión deben indicarse juntas.')
    if payload.rule_id:
        rule=db.execute(select(rules).where(rules.c.id==payload.rule_id,rules.c.version==payload.rule_version)).mappings().first()
        if not app or not app['applicable'] or not rule or any(rule[k]!=getattr(payload,k) for k in ('company_id','obligation_id','period_id','date')):raise HTTPException(422,'Regla o aplicabilidad incompatible.')
    old=db.execute(select(dates).where(dates.c.id==ident)).mappings().first()
    if old:
        write_access(db,p,old['company_id'])
        if old['company_id']!=payload.company_id:raise HTTPException(422,'No trasladar eventos entre empresas.')
    if (old['revision'] if old else 0)!=payload.revision:raise HTTPException(409,'Evento concurrente.')
    values=payload.model_dump(exclude={'reason','revision'});values['revision']=payload.revision+1
    if old:
        if not db.execute(update(dates).where(dates.c.id==ident,dates.c.revision==payload.revision).values(**values)).rowcount:raise HTTPException(409,'Evento concurrente.')
    else:db.execute(dates.insert().values(id=ident,**values))
    event(db,p,payload.company_id,'calendar',ident,old,values,payload.reason);db.commit();return dict(id=ident,revision=values['revision'])

def invoke(db,operation):
    try:return operation()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Conflicto de identidad o revisión; actualiza.') from None
    except HTTPException:
        db.rollback();raise

def register(router):
    @router.get('/calendar/management/{cid}')
    def management(cid:str,p:Principal=Depends(auth),db=Depends(session)):
        ready(db);p.require_company(cid)
        from .fiscal_control import catalog,periods,ready as fiscal_ready
        fiscal_ready(db)
        return {'dates':[dict(r) for r in db.execute(select(dates).where(dates.c.company_id==cid)).mappings()],
                'rules':[dict(r) for r in db.execute(select(rules).where(rules.c.company_id==cid).order_by(rules.c.id,rules.c.version)).mappings()],
                'catalog':[dict(r) for r in db.execute(select(catalog)).mappings()],
                'periods':[dict(r) for r in db.execute(select(periods).order_by(periods.c.id)).mappings()],
                'history':[dict(r) for r in db.execute(select(history).where(history.c.company_id==cid,history.c.entity.in_(['calendar','rule'])).order_by(history.c.created_at.desc()).limit(200)).mappings()]}
    @router.get('/certificates/{cid}/lifecycle')
    def certificate_lifecycle(cid:str,p:Principal=Depends(auth),db=Depends(session)):
        ready(db);allowed(p,db,cid,'metadata')
        ids=select(certificates.c.id).where(certificates.c.company_id==cid)
        return {'current':[dict(r) for r in db.execute(select(current).where(current.c.company_id==cid)).mappings()],
                'renewals':[dict(r) for r in db.execute(select(renewals).where(renewals.c.certificate_id.in_(ids),renewals.c.previous_id.in_(ids))).mappings()]}
    @router.put('/certificates/{cid}/current')
    def selection(cid:str,payload:SelectionIn,p:Principal=Depends(auth),db=Depends(session)):return invoke(db,lambda:select_certificate(db,p,cid,payload))
    @router.put('/alerts/{ident}/lifecycle')
    def action(ident:str,payload:ActionIn,p:Principal=Depends(auth),db=Depends(session)):return invoke(db,lambda:alert_action(db,p,ident,payload))
    @router.put('/calendar/manual/{ident}')
    def manual(ident:str,payload:DateIn,p:Principal=Depends(auth),db=Depends(session)):return invoke(db,lambda:save_date(db,p,ident,payload))
    @router.post('/calendar/rules/{ident}/versions')
    def rule(ident:str,payload:RuleIn,p:Principal=Depends(auth),db=Depends(session)):return invoke(db,lambda:save_rule(db,p,ident,payload))
    @router.get('/lifecycle/{cid}/history')
    def actions(cid:str,p:Principal=Depends(auth),db=Depends(session)):
        ready(db);allowed(p,db,cid,'history')
        return [dict(r) for r in db.execute(select(history).where(history.c.company_id==cid).order_by(history.c.created_at.desc()).limit(200)).mappings()]


def evaluate_sources(db,p):
    ready(db);lock(db);p.require_admin()
    from .credential_alerts import candidates
    return evaluate(db,p,candidates(db,p))
