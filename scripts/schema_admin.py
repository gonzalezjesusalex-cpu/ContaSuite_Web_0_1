"""Explicit installation/update. No default database or dotenv fallback."""
import argparse,os,sys,importlib.util
from pathlib import Path
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--new',action='store_true')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not os.environ.get('DATABASE_URL'):parser.error('DATABASE_URL must be explicitly provisioned to this process')
    if args.apply and not args.new and (not args.backup or not args.backup.is_file() or args.backup.stat().st_size==0):parser.error('Updates require a nonempty verified backup supplied by the operator')
    os.environ['PYTHON_DOTENV_DISABLED']='1';os.environ['DATA_DIR']=str(args.data_dir.resolve())
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
    from app.database import engine,Base
    from app.schema_compatibility import check_schema
    if args.apply:
        from sqlalchemy import inspect
        if args.new and inspect(engine).has_table('companies'):parser.error('--new refuses an existing installation')
        from app.receipt_migration import migrate_receipts
        from app.storage.migrate import upgrade_storage
        migrate_receipts(engine);upgrade_storage(engine);Base.metadata.create_all(engine)
        for folder,file in [('fiscal_migrations','001_control_obligaciones'),('credential_migrations','001_vault'),('import_migrations','001_reconciliation'),('integral_migrations','001_integral'),('company_migrations','001_archive'),('lote4_migrations','001_lifecycle'),('lote4_migrations','002_schedule'),('integral_migrations','002_evidence_history'),('integral_migrations','003_document_identity')]:
            spec=importlib.util.spec_from_file_location(folder+file,root/'backend'/folder/(file+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with engine.begin() as connection:module.upgrade(connection)
    result=check_schema(engine)
    print('Schema compatible' if result['compatible'] else 'Schema incompatible: '+', '.join(result['errors']))
    return 0 if result['compatible'] else 1
if __name__=='__main__':raise SystemExit(main())
