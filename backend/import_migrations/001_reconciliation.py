"""Independent explicit staging migration; never part of startup or CS-Storage."""
from app.company_import_models import metadata
revision='reconciliation_0001'
def upgrade(connection):metadata.create_all(connection)
def downgrade(connection):
    # Only a verified empty staging schema can be removed. Company data is never touched.
    from sqlalchemy import select,func
    for table in metadata.sorted_tables:
        if connection.scalar(select(func.count()).select_from(table)):raise RuntimeError('Conservar historial: reversión sólo con tablas vacías.')
    metadata.drop_all(connection)
