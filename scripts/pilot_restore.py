"""Restore into NEW synthetic databases only; verify all table counts and local file hashes."""
import sys,json,hashlib,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pilot_lab import RUN,configuration,original_hashes
from integration_runtime import ROOT,BIN,RUN as PREVIOUS,call

def main():
    config,previous,env=configuration()
    import psycopg
    from psycopg import sql
    credentials=dict(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'],connect_timeout=5)
    targets=['contasuite_pilot_restore_001','contasuite_pilot_empty_restore_001']
    with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==PREVIOUS/'cluster'
        for target in targets:
            assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(target,)).fetchone(),'Refuse an existing restore target'
        for target in targets:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
    assert original_hashes()==json.loads((RUN/'original-hashes.json').read_text())
    cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(previous['port']),PGUSER='recovery_test',PGPASSWORD=previous['password'])
    after=RUN/'after-import.dump'
    call([BIN/'pg_dump.exe','-Fc','--file',after,config['database']],cli)
    call([BIN/'pg_restore.exe','--exit-on-error','--dbname',targets[0],after],cli)
    call([BIN/'pg_restore.exe','--exit-on-error','--dbname',targets[1],RUN/'before-import.dump'],cli)
    def counts(name):
        with psycopg.connect(**credentials,dbname=name) as db:
            tables=[r[0] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
            return {t:db.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in tables}
    source=counts(config['database']);restored=counts(targets[0]);empty=counts(targets[1]);assert source==restored
    assert empty['companies']==empty['documents']==0
    assert source['companies']==2 and source['documents']==6 and source['document_versions']==6
    # Content and associations, not just counts, must survive restore.
    def state(name):
        with psycopg.connect(**credentials,dbname=name) as db:
            return {t:db.execute(sql.SQL('SELECT row_to_json(t) FROM {} AS t ORDER BY row_to_json(t)::text').format(sql.Identifier(t))).fetchall()
                    for t in ['companies','documents','document_versions','document_locations','document_company_links','document_classification_reviews','document_cfdi_identities','reconcile_rows','reconcile_history']}
    assert state(config['database'])==state(targets[0])
    report={'synthetic_only':True,'source_database_preserved':True,'before_dump_sha256':hashlib.sha256((RUN/'before-import.dump').read_bytes()).hexdigest(),
            'after_dump_sha256':hashlib.sha256(after.read_bytes()).hexdigest(),'restored_table_counts':restored,
            'empty_baseline_restored':True,'document_and_audit_rows_equal':True,'original_files_unchanged':True,
            'original_file_count':len(original_hashes()),'postgres_listens_loopback':True}
    with psycopg.connect(**credentials,dbname=config['database']) as db:assert db.execute('SHOW listen_addresses').fetchone()[0]=='127.0.0.1'
    (RUN/'restore-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Both synthetic backups restored into new databases; all rows/counts and original hashes verified.')
if __name__=='__main__':main()
