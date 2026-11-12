"""Explicit migration; prerequisite lote4_lifecycle_0001. Never run at startup."""
from datetime import datetime,timezone
from sqlalchemy import select
from app.alert_schedule import metadata,schedule
revision='lote4_schedule_0002'
down_revision='lote4_lifecycle_0001'
def upgrade(connection):
    metadata.create_all(connection)
    if not connection.scalar(select(schedule.c.id).where(schedule.c.id==1)):
        connection.execute(schedule.insert().values(id=1,next_due=datetime(1970,1,1,tzinfo=timezone.utc)))
def downgrade(connection):raise RuntimeError('Conservar historial y programación; reversión destructiva deshabilitada.')
