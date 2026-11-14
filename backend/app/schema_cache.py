"""Per-session memo of schema introspection used by optional-module guards.

Several modules ask "is this table present?" on every request. Each question is a catalog query
(PostgreSQL) or PRAGMA (SQLite). Within one session the table list is read once and column lists
once per table. A table missing from the memo is re-checked, so a table created during the session
is still found. Nothing is cached across sessions or requests.
"""

from sqlalchemy import inspect


def _memo(db):
    return db.info.setdefault('schema_cache', {'tables': None, 'columns': {}})


def has_table(db, name):
    memo = _memo(db)
    if memo['tables'] is None:
        memo['tables'] = set(inspect(db.connection()).get_table_names())
    if name in memo['tables']:
        return True
    if inspect(db.connection()).has_table(name):
        memo['tables'].add(name)
        return True
    return False


def column_names(db, name):
    memo = _memo(db)
    if name not in memo['columns']:
        memo['columns'][name] = {c['name'] for c in inspect(db.connection()).get_columns(name)}
    return memo['columns'][name]


def tables_ready(db, metadata, check_columns=False):
    """All tables of `metadata` exist (and, optionally, contain every declared column)."""
    return all(
        has_table(db, t.name) and (not check_columns or {c.name for c in t.columns} <= column_names(db, t.name))
        for t in metadata.sorted_tables
    )
