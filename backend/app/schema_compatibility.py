"""Schema inspection only. Importing or calling this module never creates tables."""
from sqlalchemy import inspect,UniqueConstraint
def metadatas():
    from .database import Base
    from . import models
    from .fiscal_control import metadata as fiscal
    from .credential_models import metadata as vault
    from .company_import_models import metadata as imports
    from .integral_models import metadata as integral
    from .company_lifecycle import metadata as archive
    from .lote4_lifecycle import metadata as lifecycle
    from .alert_schedule import metadata as schedule
    from .evidence_history import metadata as evidence
    from .document_identity import metadata as identity
    return [Base.metadata,fiscal,vault,imports,integral,archive,lifecycle,schedule,evidence,identity]
def check_schema(engine):
    errors=[]
    with engine.connect() as connection:
        inspector=inspect(connection)
        for metadata in metadatas():
            for table in metadata.tables.values():
                if not inspector.has_table(table.name):errors.append(table.name+':missing');continue
                columns={c['name']:c for c in inspector.get_columns(table.name)}
                for col in table.columns:
                    actual=columns.get(col.name)
                    if actual is None:errors.append(table.name+'.'+col.name+':missing');continue
                    if actual['type']._type_affinity is not col.type._type_affinity:errors.append(table.name+'.'+col.name+':type')
                    if not col.nullable and actual['nullable'] and not col.primary_key:errors.append(table.name+'.'+col.name+':nullable')
                pk=set(inspector.get_pk_constraint(table.name)['constrained_columns'])
                if pk!={c.name for c in table.primary_key.columns}:errors.append(table.name+':primary_key')
                unique={tuple(sorted(c['column_names'])) for c in inspector.get_unique_constraints(table.name)}
                unique|={tuple(sorted(i['column_names'])) for i in inspector.get_indexes(table.name) if i.get('unique') and all(i['column_names'])}
                for constraint in table.constraints:
                    if isinstance(constraint,UniqueConstraint) and tuple(sorted(c.name for c in constraint.columns)) not in unique:errors.append(table.name+':unique_constraint')
                actual_fk={(tuple(k['constrained_columns']),k['referred_table'],tuple(k['referred_columns'])) for k in inspector.get_foreign_keys(table.name)}
                for fk in table.foreign_key_constraints:
                    wanted=(tuple(e.parent.name for e in fk.elements),next(iter(fk.elements)).column.table.name,tuple(e.column.name for e in fk.elements))
                    if wanted not in actual_fk:errors.append(table.name+':foreign_key')
    return {'compatible':not errors,'errors':sorted(set(errors))}
def assert_schema(engine):
    result=check_schema(engine)
    if not result['compatible']:raise RuntimeError('Esquema incompatible. Ejecute actualización explícita con respaldo; no se modificó el esquema. '+', '.join(result['errors'][:20]))
