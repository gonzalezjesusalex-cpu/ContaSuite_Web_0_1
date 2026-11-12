"""Backup/restore, legacy upgrade and contention on NEW synthetic databases only."""
import os,sys,json,hashlib,shutil,subprocess,threading,argparse,re
from pathlib import Path
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
from integration_runtime import ROOT,RUN,BIN,environment,call

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='initial');args=parser.parse_args()
    assert re.fullmatch('[a-z0-9_]{1,16}',args.run_id)
    config=json.loads((RUN/'synthetic.json').read_text());env=environment(config)
    import psycopg
    from psycopg import sql
    credentials=dict(host='127.0.0.1',port=config['port'],user='recovery_test',password=config['password'],connect_timeout=5)
    target='contasuite_recovery_restore_'+args.run_id
    restored_data=RUN/('restored-data-'+args.run_id)
    with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==RUN/'cluster'
        assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(target,)).fetchone(),'Refuse to replace an existing database'
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
    cli=os.environ.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(config['port']),PGUSER='recovery_test',PGPASSWORD=config['password'])
    dump=RUN/('verified-backup-'+args.run_id+'.dump')
    call([BIN/'pg_dump.exe','-Fc','--file',dump,'contasuite_recovery'],cli)
    call([BIN/'pg_restore.exe','--exit-on-error','--dbname',target,dump],cli)
    def counts(name):
        with psycopg.connect(**credentials,dbname=name) as db:
            tables=[r[0] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
            return {t:db.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in tables}
    original=counts('contasuite_recovery');assert original==counts(target)
    shutil.copytree(RUN/'data',restored_data)
    def hashes(folder):return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    assert hashes(RUN/'data')==hashes(restored_data)
    result=dict(synthetic_only=True,restored_counts=original,backup_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),data_files_restored=len(hashes(RUN/'data')))
    # Model an installation predating integral_0002 on the restored synthetic copy.
    with psycopg.connect(**credentials,dbname=target) as db:db.execute('DROP TABLE fiscal_verification_decisions')
    env['DATABASE_URL']=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+target;env['DATA_DIR']=str(restored_data)
    os.environ.update(env);sys.path.insert(0,str(ROOT/'backend'))
    from app.database import engine
    from app.schema_compatibility import check_schema
    assert not check_schema(engine)['compatible']
    print(call([sys.executable,'-B',ROOT/'scripts/schema_admin.py','--data-dir',restored_data,'--apply','--backup',dump],env))
    assert check_schema(engine)['compatible'];result['legacy_upgrade']='passed; surviving current decision captured'
    from sqlalchemy import select,func,update
    from sqlalchemy.orm import Session
    from app.evidence_history import decisions,review_condition
    from app.fiscal_control import records
    from app.models import Document
    from app.alert_schedule import tick,schedule
    from app.security import Principal
    from app.integral_api import verify,VerifyIn
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(decisions))==1
        record=db.execute(select(records)).mappings().one();cid=record['company_id']
        decision=db.execute(select(decisions)).mappings().one();docid=decision['document_id']
        assert review_condition(db,record)[0]
    start=datetime.now(timezone.utc)
    with engine.begin() as db:db.execute(update(schedule).where(schedule.c.id==1).values(next_due=start-timedelta(days=10)))
    barrier=threading.Barrier(8);calls=[]
    def work(number):
        barrier.wait()
        with Session(engine) as db,db.begin():return tick(db,lambda:start,lambda db,p:(calls.append(number) or []))['state']
    with ThreadPoolExecutor(max_workers=8) as pool:states=list(pool.map(work,range(8)))
    assert states.count('evaluated')==1 and states.count('not_due')==7 and len(calls)==1
    result['concurrent_schedule']=dict(workers=8,states=states)
    def fail(db,p):raise RuntimeError('synthetic failure')
    with engine.begin() as db:db.execute(update(schedule).where(schedule.c.id==1).values(next_due=start-timedelta(days=1)))
    try:
        with Session(engine) as db,db.begin():tick(db,lambda:start,fail)
    except RuntimeError:pass
    else:raise AssertionError('Expected failure')
    with Session(engine) as db,db.begin():assert tick(db,lambda:start,lambda db,p:[])['state']=='evaluated'
    result['failure_recovery']='passed'
    # Genuine independent PostgreSQL transactions; synthetic internal bytes only.
    from io import BytesIO
    from contextlib import contextmanager
    from types import SimpleNamespace
    import app.storage.router as storage_router
    raw=b'<Comprobante xmlns="http://www.sat.gob.mx/cfd/4" Fecha="2026-11-11T12:00:00"><Emisor Rfc="AAA010101AA1"/><Receptor Rfc="BBB010101BB1"/></Comprobante>'
    class Provider:
        @contextmanager
        def read(self,*args):yield SimpleNamespace(stream=BytesIO(raw))
    storage_router.storage_service=lambda:Provider()
    barrier=threading.Barrier(6)
    def verification(number):
        barrier.wait()
        with Session(engine) as db:return verify(record['id'],VerifyIn(revision=record['revision'],document_id=docid),Principal('concurrent-reviewer','Synthetic',True),db)
    with ThreadPoolExecutor(max_workers=6) as pool:verified=list(pool.map(verification,range(6)))
    assert len({v['decision_id'] for v in verified})==1 and sum(not v['idempotent'] for v in verified)==1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(decisions))==2
        db.execute(update(Document).where(Document.id==docid).values(storage_revision=Document.storage_revision+1));db.commit()
        assert not review_condition(db,record)[0]
        assert db.scalar(select(func.count()).select_from(decisions))==2
    result['concurrent_verification']=dict(workers=6,created=1,idempotent=5,history_preserved=True,changed_version_suspends=True)
    from app.credential_models import certificates
    from app.lote4_lifecycle import select_certificate,SelectionIn,current,renewals
    from app.models import now
    with engine.begin() as db:
        for n in ('old','new'):
            db.execute(certificates.insert().values(id='pg-'+n,company_id=cid,kind='fiel',rfc='AAA010101AA1',fingerprint=('a' if n=='old' else 'b')*64,origin='manual',reviewed_at=now(),notes='synthetic',revision=1))
    barrier=threading.Barrier(2)
    def selection(n):
        from fastapi import HTTPException
        barrier.wait()
        with Session(engine) as db:
            try:select_certificate(db,Principal('pg-admin','Synthetic',True),cid,SelectionIn(certificate_id='pg-'+n,revision=0,reason='concurrent synthetic'));return 200
            except HTTPException as e:db.rollback();return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:selection_states=list(pool.map(selection,('old','new')))
    assert sorted(selection_states)==[200,409];result['concurrent_selection']=selection_states
    with Session(engine) as db:
        chosen=db.scalar(select(current.c.certificate_id).where(current.c.company_id==cid))
        other='pg-new' if chosen=='pg-old' else 'pg-old'
        select_certificate(db,Principal('pg-admin','Synthetic',True),cid,SelectionIn(certificate_id=other,previous_id=chosen,revision=1,reason='renewal synthetic'))
        assert db.scalar(select(renewals.c.previous_id).where(renewals.c.certificate_id==other))==chosen
    result['renewal']='passed'
    engine.dispose()
    (RUN/('postgres-results-'+args.run_id+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS: PostgreSQL dump/restore, legacy upgrade, 8 scheduler claims, failure rollback, 6 verifications, competing certificate selection and renewal.')
if __name__=='__main__':main()
