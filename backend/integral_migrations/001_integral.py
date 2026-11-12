"""Explicit v0.3 migration; no automatic chain, no real database execution."""
from sqlalchemy import select
from app.integral_models import metadata,categories,rules,settings,LABELS,RULES
revision='integral_0001'
def upgrade(connection):
    metadata.create_all(connection)
    for i,label in enumerate(LABELS,1):
        key=f'category-{i:02d}'
        if not connection.execute(select(categories.c.id).where(categories.c.id==key)).first():connection.execute(categories.insert().values(id=key,label=label))
        if i in RULES and not connection.execute(select(rules.c.id).where(rules.c.id==key)).first():connection.execute(rules.insert().values(id=key,category_id=key,terms=RULES[i],enabled=True))
    if not connection.execute(select(settings.c.id)).first():connection.execute(settings.insert().values(id=1,required_categories=[],indicator_config={'evidence_verification':'manual','active_companies':'explicit'}))
def downgrade(connection):raise RuntimeError('Reversión destructiva bloqueada; conservar clasificaciones e historial.')
