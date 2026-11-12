"""Explicit migration only. Never included in automatic CS-Storage upgrades."""
from sqlalchemy import select
from app.credential_models import metadata,services,settings,INITIAL
revision='vault_0001'
def upgrade(connection):
    metadata.create_all(connection)
    for key,label in INITIAL.items():
        if not connection.execute(select(services.c.id).where(services.c.id==key)).first():connection.execute(services.insert().values(id=key,label=label))
    if not connection.execute(select(settings.c.id)).first():connection.execute(settings.insert().values(id=1,thresholds=[60,30,15]))
def downgrade(connection):raise RuntimeError('Reversión destructiva deshabilitada.')
