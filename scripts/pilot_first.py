"""Authorized first-folder analysis. Separate private cluster; no final import operation."""
import os,sys,json,secrets,socket,subprocess,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from integration_runtime import ROOT,BIN,call
RUN=ROOT/'.qa/pilot-first'
PARENT=Path(r'C:\Users\Usuario\Documents\EMPRESAS PRUEBA')
DATABASE='contasuite_pilot_first_authorized'

def configuration():
    c=json.loads((RUN/'private.json').read_text());assert c['database']==DATABASE and Path(c['cluster'])==RUN/'cluster'
    root=Path(c['root']);assert root.parent==PARENT and root==sorted(p for p in PARENT.iterdir() if p.is_dir())[0]
    env=os.environ.copy()
    env.update(PYTHON_DOTENV_DISABLED='1',DATABASE_URL=f"postgresql+psycopg://pilot_local:{c['db_password']}@127.0.0.1:{c['port']}/{DATABASE}",DATA_DIR=str(RUN/'data'),
        APP_TOKEN=c['app_token'],AGENT_TOKEN=c['agent_token'],PYTHONPATH=str(ROOT/'backend'),SEED_DEMO='false',CS_STORAGE_ALLOWED_ROOTS=json.dumps([str(root)]),CS_STORAGE_SMB_ALLOWED_ROOTS='[]',
        CS_PILOT_ENABLED='0',CS_PILOT_ROOTS='[]',CS_BATCH_DATABASE=DATABASE,CS_ALLOWED_HOSTS=json.dumps(['127.0.0.1','localhost']))
    for key in list(env):
        if key.startswith(('CONTA_VAULT_','CS_VAULT_','VAULT_')):env.pop(key)
    return c,env

def main():
    mode=sys.argv[1]
    if mode=='prepare':
        assert not RUN.exists(),'Refuse existing target'
        roots=sorted(p for p in PARENT.iterdir() if p.is_dir());assert len(roots)==2
        RUN.mkdir();(RUN/'data').mkdir()
        # Private metadata/access files must not inherit access for unrelated accounts.
        who=subprocess.check_output(['whoami'],text=True).strip()
        call(['icacls',RUN,'/inheritance:r','/grant:r',who+':(OI)(CI)F','SYSTEM:(OI)(CI)F'])
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        c=dict(database=DATABASE,cluster=str(RUN/'cluster'),root=str(roots[0]),port=port,db_password=secrets.token_hex(24),app_token=secrets.token_hex(32),agent_token=secrets.token_hex(32))
        (RUN/'private.json').write_text(json.dumps(c),encoding='utf-8')
        password=RUN/'init-password.tmp';password.write_text(c['db_password'])
        try:call([BIN/'initdb.exe','-D',RUN/'cluster','-U','pilot_local','--pwfile='+str(password),'--auth=scram-sha-256','--encoding=UTF8','--locale=C'])
        finally:password.unlink()
        call([BIN/'pg_ctl.exe','-D',RUN/'cluster','-l',RUN/'postgres.log','-o',f'-h 127.0.0.1 -p {port}','-w','start'])
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=port,user='pilot_local',password=c['db_password'],dbname='postgres',autocommit=True) as db:
            assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==RUN/'cluster'
            db.execute('CREATE DATABASE '+DATABASE)
        c,env=configuration()
        (RUN/'schema.txt').write_text(call([sys.executable,'-B',ROOT/'scripts/schema_admin.py','--data-dir',RUN/'data','--apply','--new'],env))
        cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(port),PGUSER='pilot_local',PGPASSWORD=c['db_password'])
        call([BIN/'pg_dump.exe','-Fc','--file',RUN/'before-analysis.dump',DATABASE],cli)
        (RUN/'backup.json').write_text(json.dumps({'sha256':hashlib.sha256((RUN/'before-analysis.dump').read_bytes()).hexdigest(),'before_document_read':True}))
        print('Dedicated private pilot database and pre-analysis backup prepared.',flush=True)
    c,env=configuration()
    if mode=='restart':
        pid=int((RUN/'api.pid').read_text())
        call(['powershell.exe','-NoProfile','-Command',f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if (-not $p -or $p.CommandLine -notmatch 'uvicorn app.main:app --host 127.0.0.1 --port 8062') {{ throw 'Unexpected pilot process' }}; Stop-Process -Id {pid} -ErrorAction Stop"])
        mode='serve'
    if mode=='open':
        status=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(RUN/'cluster'),'status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if status.returncode:call([BIN/'pg_ctl.exe','-D',RUN/'cluster','-l',RUN/'postgres.log','-o',f'-h 127.0.0.1 -p {c["port"]}','-w','start'])
        import httpx
        try:healthy=httpx.get('http://127.0.0.1:8062/api/health',timeout=2).status_code==200
        except httpx.TransportError:healthy=False
        if healthy:
            pid=int((RUN/'api.pid').read_text())
            call(['powershell.exe','-NoProfile','-Command',f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if (-not $p -or $p.CommandLine -notmatch 'uvicorn app.main:app --host 127.0.0.1 --port 8062') {{ throw 'Unexpected pilot process' }}"])
            print('Private pilot ready on 127.0.0.1:8062; no migrations or imports executed.');return
        mode='serve'
    if mode in ('serve','prepare'):
        api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8062','--no-access-log'],cwd=ROOT/'backend',env=env,
            stdout=(RUN/'api.log').open('w'),stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(RUN/'api.pid').write_text(str(api.pid))
        import httpx
        for _ in range(80):
            if api.poll() is not None:raise RuntimeError('Private pilot startup failed')
            try:
                if httpx.get('http://127.0.0.1:8062/api/health',timeout=1).status_code==200:break
            except httpx.TransportError:pass
            time.sleep(.25)
        else:raise RuntimeError('Private pilot startup timeout')
        if mode=='prepare':
            password=secrets.token_urlsafe(24)
            import httpx
            with httpx.Client(timeout=30) as client:
                response=client.post('http://127.0.0.1:8062/api/auth/bootstrap',headers={'Authorization':'Bearer '+c['app_token']},json={'username':'piloto_local_admin','display_name':'Piloto autorizado','password':password})
                assert response.status_code==201,'Account setup failed'
                response=client.post('http://127.0.0.1:8062/api/auth/login',json={'username':'piloto_local_admin','password':password});assert response.status_code==200
                actor=response.json().get('id')
            (RUN/'access.json').write_text(json.dumps({'url':'http://127.0.0.1:8062','username':'piloto_local_admin','password':password}),encoding='utf-8')
            # Obtain the trusted actor from the actual new account, never supplied by a browser.
            import psycopg
            with psycopg.connect(host='127.0.0.1',port=c['port'],user='pilot_local',password=c['db_password'],dbname=DATABASE) as db:
                actor=db.execute("SELECT id FROM user_accounts WHERE username='piloto_local_admin'").fetchone()[0]
            c['actor']=actor;(RUN/'private.json').write_text(json.dumps(c),encoding='utf-8')
        print('Private pilot ready on 127.0.0.1:8062; credentials saved locally, not printed.',flush=True)
    if mode=='analyse':
        os.environ.update(env);sys.path.insert(0,str(ROOT/'backend'))
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=c['port'],user='pilot_local',password=c['db_password'],dbname=DATABASE,autocommit=True) as guard:
            assert Path(guard.execute('SHOW data_directory').fetchone()[0]).resolve()==RUN/'cluster'
            if not guard.execute('SELECT pg_try_advisory_lock(440043)').fetchone()[0]:raise RuntimeError('Another batch worker owns the database; no parallel run allowed')
            analyse(c)
    if mode=='verify':
        os.environ.update(env);sys.path.insert(0,str(ROOT/'backend'));verify(c)

def analyse(c):
    from app.database import SessionLocal
    from app.models import now
    from app.company_import_models import sessions,rows,history
    from app.storage.local import LocalFolderProvider
    from app.storage.providers import ScanIssue,StorageError
    from app.pilot_scan import SECRET_PATTERNS
    from app.pilot_batch import Extractor,finalize
    from sqlalchemy import select,update
    from datetime import timedelta
    from uuid import uuid4
    provider=LocalFolderProvider(Path(c['root']),(Path(c['root']),),exclusions=SECRET_PATTERNS,max_entries=100000,max_seconds=300)
    with SessionLocal() as db:previous=db.execute(select(sessions).where(sessions.c.source=='local_batch')).mappings().first()
    if previous:
        ident=previous['id']
        if previous['status']=='preview':print('Completed analysis already present; no reimport performed.');return
    else:
        inventory=[];issues=[]
        for entry in provider.enumerate():
            if isinstance(entry,ScanIssue):issues.append({'code':entry.code,'key':entry.key})
            else:inventory.append(entry)
        if any(e['code']=='scan_limit' for e in issues):raise RuntimeError('Inventory incomplete; no preview created')
        inventory.sort(key=lambda e:e.key.casefold());ident=str(uuid4())
        with SessionLocal.begin() as db:
            db.execute(sessions.insert().values(id=ident,owner_id=c['actor'],idempotency_key=hashlib.sha256(ident.encode()).hexdigest(),source='local_batch',
                source_sha256=hashlib.sha256(json.dumps([(e.key,e.size,e.mtime_ns) for e in inventory]).encode()).hexdigest(),
                summary={'company':'P-01','total':len(inventory),'processed':0,'issues':issues,'confirmation_enabled':False},created_at=now(),expires_at=now()+timedelta(days=30),status='analysing'))
            for start in range(0,len(inventory),500):
                db.execute(rows.insert(),[{'session_id':ident,'number':i+1,'revision':0,'proposal':{'key':e.key,'size':e.size,'mtime_ns':e.mtime_ns,'status':'queued'}} for i,e in enumerate(inventory[start:start+500],start)])
            db.execute(history.insert().values(id=str(uuid4()),session_id=ident,actor_id=c['actor'],action='batch_inventory',created_at=now(),counts={'files':len(inventory)}))
    extractor=Extractor();digest_rows={};processed=0
    with SessionLocal() as db:
        for n,r in db.execute(select(rows.c.number,rows.c.proposal).where(rows.c.session_id==ident)):
            if r.get('sha256') and r.get('status')=='analysed':digest_rows[(r['sha256'],Path(r['key']).suffix.lower())]=n
    try:
        with SessionLocal() as db:
            total=db.scalar(select(sessions.c.summary).where(sessions.c.id==ident))['total']
            for start in range(0,total,100):
                records=list(db.execute(select(rows).where(rows.c.session_id==ident,rows.c.number>start,rows.c.number<=start+100).order_by(rows.c.number)))
                for record in records:
                    r=record.proposal
                    if r.get('status')=='analysed':processed+=1;continue
                    try:
                        meta=provider.metadata(r['key'])
                        if (meta.size,meta.mtime_ns)!=(r['size'],r['mtime_ns']):raise StorageError('file_changed_since_inventory')
                        with provider.open_read(r['key']) as stream:content=stream.read(provider.max_file_bytes+1)
                        digest=hashlib.sha256(content).hexdigest()
                        cache_key=(digest,Path(r['key']).suffix.lower())
                        prior=digest_rows.get(cache_key)
                        if prior:
                            cached=db.scalar(select(rows.c.proposal).where(rows.c.session_id==ident,rows.c.number==prior));result=cached['result']
                        else:result=extractor.extract(content,Path(r['key']).name)
                        r={**r,'sha256':digest,'type':result['type'],'result':result,'error':None if result['evidence'].get('readable') else result['evidence'].get('reason','unreadable'),'status':'analysed'}
                        digest_rows[cache_key]=record.number
                        del content
                    except StorageError as e:r={**r,'status':'analysed','type':'unknown','error':e.code}
                    db.execute(update(rows).where(rows.c.session_id==ident,rows.c.number==record.number).values(proposal=r));processed+=1
                summary=db.scalar(select(sessions.c.summary).where(sessions.c.id==ident));db.execute(update(sessions).where(sessions.c.id==ident).values(summary={**summary,'processed':processed}));db.commit()
                print(f'Analysed {processed}/{total}; checkpoint saved.',flush=True)
    finally:extractor.close()
    with SessionLocal.begin() as db:
        summary=db.scalar(select(sessions.c.summary).where(sessions.c.id==ident));analysis=finalize(db,ident)
        db.execute(update(sessions).where(sessions.c.id==ident).values(status='preview',summary={**summary,**analysis,'processed':processed}))
        db.execute(history.insert().values(id=str(uuid4()),session_id=ident,actor_id=c['actor'],action='batch_completed',created_at=now(),counts=analysis['counts']))
    report={'company':'P-01','analysed':processed,'total':total,**{k:v for k,v in analysis.items() if k not in {'identity_candidates'}},'companies_imported':0,'documents_imported':0,'original_writes':False}
    (RUN/'summary-anonymized.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Analysis completed; preview only. No companies or documents imported.',flush=True)

def verify(c):
    from app.database import SessionLocal
    from app.company_import_models import sessions,rows
    from app.storage.local import LocalFolderProvider
    from app.storage.providers import StorageError
    from app.pilot_scan import SECRET_PATTERNS
    from sqlalchemy import select,update
    provider=LocalFolderProvider(Path(c['root']),(Path(c['root']),),exclusions=SECRET_PATTERNS,max_entries=100000,max_seconds=300)
    matched=changed=unavailable=unhashed=0
    with SessionLocal() as db:
        value=db.execute(select(sessions).where(sessions.c.source=='local_batch')).mappings().one()
        assert value['status']=='preview','Analysis not complete'
        expected=set()
        for r in db.scalars(select(rows.c.proposal).where(rows.c.session_id==value['id'],rows.c.number>0).execution_options(yield_per=100)):
            expected.add(r['key'])
            if not r.get('sha256'):unhashed+=1;continue
            try:
                sha=hashlib.sha256()
                with provider.open_read(r['key']) as stream:
                    while chunk:=stream.read(1024*1024):sha.update(chunk)
                if sha.hexdigest()==r['sha256']:matched+=1
                else:changed+=1
            except StorageError:unavailable+=1
        from app.storage.providers import ScanIssue
        current=set();scan_issues=0
        for entry in provider.enumerate():
            if isinstance(entry,ScanIssue):scan_issues+=1
            else:current.add(entry.key)
        integrity={'matched_sha256':matched,'changed':changed,'unavailable':unavailable,'unhashed_errors':unhashed,
            'new_files_after_inventory':len(current-expected),'missing_files_after_inventory':len(expected-current),'final_scan_issues':scan_issues}
        db.execute(update(sessions).where(sessions.c.id==value['id']).values(summary={**value['summary'],'integrity':integrity}));db.commit()
    report=json.loads((RUN/'summary-anonymized.json').read_text());report['integrity']=integrity
    (RUN/'summary-anonymized.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Read-only integrity verification:',json.dumps(integrity),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        # Database exception representations can include bound fiscal values: never log them.
        print('Pilot operation stopped; error_class='+type(error).__name__,flush=True)
        raise SystemExit(1) from None
