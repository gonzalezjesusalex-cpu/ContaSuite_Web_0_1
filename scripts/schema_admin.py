"""Explicit installation/update. No default database or dotenv fallback."""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--new', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--status', action='store_true', help='Read-only: report revision and compatibility')
    args = parser.parse_args()
    if args.status and args.apply:
        parser.error('--status is read-only and cannot be combined with --apply')
    if not os.environ.get('DATABASE_URL'):
        parser.error('DATABASE_URL must be explicitly provisioned to this process')
    if (
        args.apply
        and not args.new
        and (not args.backup or not args.backup.is_file() or args.backup.stat().st_size == 0)
    ):
        parser.error('Updates require a nonempty verified backup supplied by the operator')
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    os.environ['DATA_DIR'] = str(args.data_dir.resolve())
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'backend'))
    from app.database import engine
    from app.schema_compatibility import check_schema
    from app.storage.migrate import schema_revision

    if args.apply:
        from sqlalchemy import inspect

        if args.new and inspect(engine).has_table('companies'):
            parser.error('--new refuses an existing installation')
        from app.receipt_migration import migrate_receipts
        from app.storage.migrate import upgrade_schema

        # Receipts repair predates the Alembic chain; it is a no-op on new or already updated databases.
        migrate_receipts(engine)
        upgrade_schema(engine)
    current, head = schema_revision(engine)
    print(
        'Revision: ' + (current or 'none') + ' (head: ' + head + ')' + ('' if current == head else ' - update pending')
    )
    result = check_schema(engine)
    print('Schema compatible' if result['compatible'] else 'Schema incompatible: ' + ', '.join(result['errors']))
    return 0 if result['compatible'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
