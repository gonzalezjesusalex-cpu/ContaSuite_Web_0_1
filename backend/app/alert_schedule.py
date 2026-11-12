"""Transactional singleton evaluation claim; used only by the existing worker, opt in."""
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import MetaData,Table,Column,Integer,DateTime,select,update,inspect
from .security import Principal,utc
from .models import now
from .lote4_lifecycle import available,evaluate,lock
TIMEZONE='America/Mexico_City'
metadata=MetaData()
schedule=Table('alert_evaluation_schedule',metadata,Column('id',Integer,primary_key=True),Column('next_due',DateTime(timezone=True),nullable=False),Column('last_success',DateTime(timezone=True)))

def tick(db,clock=now,provider=None,interval=900):
    if interval<60:raise ValueError('Interval must be at least 60 seconds')
    if not available(db) or not inspect(db.connection()).has_table(schedule.name):return {'state':'unavailable'}
    stamp=utc(clock());day=stamp.astimezone(ZoneInfo(TIMEZONE)).date()
    # Claim and evaluation commit together; failure leaves next_due unchanged.
    claimed=db.execute(update(schedule).where(schedule.c.id==1,schedule.c.next_due<=stamp).values(next_due=stamp+timedelta(seconds=interval)))
    if not claimed.rowcount:return {'state':'not_due'}
    lock(db)
    principal=Principal('alert-worker','Evaluador interno de alertas',True)
    if provider is None:
        from .credential_alerts import candidates
        provider=lambda session,p: candidates(session,p,stamp=stamp)
    evaluate(db,principal,provider(db,principal),commit=False,today=day)
    db.execute(update(schedule).where(schedule.c.id==1).values(last_success=stamp))
    return {'state':'evaluated','at':stamp,'timezone':TIMEZONE}
