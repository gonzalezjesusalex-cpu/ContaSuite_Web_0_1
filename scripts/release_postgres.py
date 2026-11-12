"""Stable backup/restore, legacy identity migration and real contention; synthetic databases only."""
import os,sys,json,hashlib,shutil,threading,argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from release_lab import LAB,configuration
from integration_runtime import ROOT,RUN as PREVIOUS,BIN,call
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='final');args=parser.parse_args();assert args.run_id.isalnum()
    config,previous,env=configuration()
    import psycopg
    from psycopg import sql
    credentials=dict(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'])
    target='contasuite_release_restore_'+args.run_id
    with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==PREVIOUS/'cluster'
        assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(target,)).fetchone()
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
    cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(previous['port']),PGUSER='recovery_test',PGPASSWORD=previous['password'])
    dump=LAB/('release-verified-'+args.run_id+'.dump')
    call([BIN/'pg_dump.exe','-Fc','--file',dump,config['database']],cli)
    call([BIN/'pg_restore.exe','--exit-on-error','--dbname',target,dump],cli)
    def counts(name):
        with psycopg.connect(**credentials,dbname=name) as db:
            tables=[r[0] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
            return {t:db.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in tables}
    original=counts(config['database']);assert original==counts(target)
    restored=LAB/('restored-data-'+args.run_id);shutil.copytree(LAB/'data',restored)
    def hashes(folder):return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    assert hashes(LAB/'data')==hashes(restored)
    with psycopg.connect(**credentials,dbname=target) as db:db.execute('DROP TABLE document_cfdi_identities')
    env.update(DATABASE_URL=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+target,DATA_DIR=str(restored))
    os.environ.update(env);sys.path.insert(0,str(ROOT/'backend'))
    from app.database import engine,SessionLocal
    from app.schema_compatibility import check_schema
    assert not check_schema(engine)['compatible']
    print(call([sys.executable,'-B',ROOT/'scripts/schema_admin.py','--data-dir',restored,'--apply','--backup',dump],env))
    assert check_schema(engine)['compatible']
    from app.storage.service import StorageService,StorageActor
    from app.storage.settings import StorageSettings
    from app.storage.classifier import classify
    from app.document_identity import identities
    from app.models import DocumentVersion
    from sqlalchemy import select,func
    from io import BytesIO
    from release_http import xml
    fixtures=json.loads((LAB/'fixtures.json').read_text());cid=fixtures['a']
    service=StorageService(SessionLocal,StorageSettings.from_environment(restored));actor=StorageActor('synthetic-concurrent',admin=True)
    # A pre-identity installation needs authorized analysis; migration never reads original documents.
    for field in ('doc','other'):
        ident=fixtures[field];doc=service.document(actor,ident)
        with service.read(actor,ident) as content:proposal=classify(content.stream,doc.name,[{'id':cid,'rfc':'AAA010101AA1'}])
        service.apply_classification(actor,ident,doc.revision,proposal)
    from app.models import DocumentClassificationReview as Review
    with SessionLocal() as db:pending=db.scalar(select(Review).where(Review.document_id==fixtures['doc'],Review.status=='pending')).id
    service.resolve_review(actor,fixtures['doc'],pending,1,'confirm',[],reason='Synthetic legacy identity reviewed; fiscal verification remains separate')
    barrier=threading.Barrier(2)
    def classify_concurrent(number):
        raw=xml(str(number)).replace(b'12345678-1234-1234-1234-123456789ABC',b'22222222-2222-2222-2222-222222222222')
        doc=service.upload(actor,BytesIO(raw),'same.xml',company_id=cid)
        result=classify(BytesIO(raw),'same.xml',[{'id':cid,'rfc':'AAA010101AA1'}]);barrier.wait()
        service.apply_classification(actor,doc.id,1,result);return doc.id
    with ThreadPoolExecutor(max_workers=2) as pool:docs=list(pool.map(classify_concurrent,range(2)))
    with SessionLocal() as db:
        values=list(db.scalars(select(identities.c.requires_review).join(DocumentVersion,DocumentVersion.id==identities.c.version_id).where(DocumentVersion.document_id.in_(docs))))
        assert values==[True,True]
    from app.integral_api import verify,VerifyIn
    from app.security import Principal
    import app.storage.router as router
    router.storage_service=lambda:service
    barrier=threading.Barrier(6)
    def verification(number):
        barrier.wait()
        with SessionLocal() as db:return verify(fixtures['record'],VerifyIn(revision=1,document_id=fixtures['doc']),Principal('closure-pg-reviewer','Synthetic',True),db)
    with ThreadPoolExecutor(max_workers=6) as pool:decisions=list(pool.map(verification,range(6)))
    assert len({r['decision_id'] for r in decisions})==1 and sum(not r['idempotent'] for r in decisions)==1
    from app.alert_schedule import tick,schedule
    from sqlalchemy import update
    from datetime import datetime,timezone,timedelta
    stamp=datetime.now(timezone.utc)
    with engine.begin() as db:db.execute(update(schedule).where(schedule.c.id==1).values(next_due=stamp-timedelta(days=10)))
    barrier=threading.Barrier(8)
    def scheduled(number):
        barrier.wait()
        with SessionLocal.begin() as db:return tick(db,lambda:stamp,lambda db,p:[])['state']
    with ThreadPoolExecutor(max_workers=8) as pool:states=list(pool.map(scheduled,range(8)))
    assert states.count('evaluated')==1 and states.count('not_due')==7
    with psycopg.connect(**credentials,dbname=target) as db:assert db.execute('SHOW listen_addresses').fetchone()[0]=='127.0.0.1'
    result=dict(synthetic_only=True,backup_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),table_counts_restored=original,
        data_sha256_restored=True,legacy_identity_update='passed',concurrent_uuid_conflict=2,concurrent_verification={'created':1,'idempotent':5},concurrent_schedule={'evaluated':1,'not_due':7},postgres_listens_loopback=True)
    (LAB/('postgres-results-'+args.run_id+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');engine.dispose()
    print('PASS: new PostgreSQL restore, identity update, 2 UUID conflicts, 6 verifications and 8 scheduled claims')
if __name__=='__main__':main()
