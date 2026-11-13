"""Exercise the generated Windows scripts on a new synthetic package/database only."""
import os,sys,json,zipfile,hashlib,subprocess,time,argparse,re
from pathlib import Path
from integration_runtime import ROOT,RUN,BIN,environment,call
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='cmd');args=parser.parse_args();assert re.fullmatch('[a-z0-9_]{1,16}',args.run_id)
    config=json.loads((RUN/'synthetic.json').read_text());env=environment(config)
    package=ROOT.parent/'ENTREGAS'/'CS_INTEGRATION_RECOVERY_20261111.zip'
    target=RUN/('package-installed-'+args.run_id);assert not target.exists(),'Refuse to replace an installation'
    with zipfile.ZipFile(package) as archive:
        manifest=json.loads(archive.read('PACKAGE_SHA256.json'))
        for name,digest in manifest.items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert hashlib.sha256(archive.read(name)).hexdigest()==digest
        assert not any(n.startswith(('.qa/','data/','.venv/')) or Path(n).name=='.env' for n in archive.namelist())
        archive.extractall(target)
    import psycopg
    credentials=dict(host='127.0.0.1',port=config['port'],user='recovery_test',password=config['password'],connect_timeout=5)
    database='contasuite_recovery_package_'+args.run_id
    with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==RUN/'cluster'
        assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(database,)).fetchone()
        from psycopg import sql
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    data=RUN/('package-test-data-'+args.run_id);data.mkdir()
    env.update(DATABASE_URL=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+database,DATA_DIR=str(data))
    env.pop('PYTHONPATH',None)
    install=target/'deploy/windows/Install-ContaSuite.cmd'
    common=[sys.executable,str(data)]
    print(call([install,*common,'Install'],env))
    # The install must refuse an existing schema instead of silently overwriting it.
    refused=subprocess.run([str(x) for x in [install,*common,'Install']],env=env,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert refused.returncode!=0
    log=(RUN/'package-api.log').open('w')
    server=subprocess.Popen([str(x) for x in [target/'deploy/windows/Start-ContaSuite.cmd',*common,'api','8057']],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    import httpx
    base='http://127.0.0.1:8057'
    checks=[]
    try:
        with httpx.Client(base_url=base,timeout=2) as client:
            for _ in range(60):
                assert server.poll() is None,'Packaged startup failed; inspect package-api.log'
                try:
                    if client.get('/api/health').status_code==200:break
                except httpx.TransportError:pass
                time.sleep(.25)
            else:raise AssertionError('Packaged startup timeout')
            html=client.get('/');assert html.status_code==200 and '/assets/index-' in html.text;checks.append('compiled_frontend_served')
            result=client.post('/api/auth/bootstrap',headers={'Authorization':'Bearer '+config['app_token']},json={'username':'package_admin','display_name':'Synthetic package test','password':'Synthetic-Package-2026!'});assert result.status_code==201
            assert client.post('/api/auth/login',json={'username':'package_admin','password':'Synthetic-Package-2026!'}).status_code==200
            assert client.get('/api/state').status_code==200;checks.append('named_session')
    finally:
        if server.poll() is None:call(['taskkill.exe','/PID',str(server.pid),'/T','/F'])
        log.close()
    worker_env=env.copy();worker_env['PYTHONPATH']=str(target/'backend')
    call([sys.executable,'-B','-m','app.storage.worker','--mode','alerts','--once'],worker_env)
    with psycopg.connect(**credentials,dbname=database) as db:
        assert db.execute('SELECT count(*) FROM storage_index_jobs').fetchone()[0]==0
        assert db.execute('SELECT last_success FROM alert_evaluation_schedule WHERE id=1').fetchone()[0] is not None
    checks.append('alerts_only_worker_without_index_jobs')
    cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(config['port']),PGUSER='recovery_test',PGPASSWORD=config['password'])
    backup_root=RUN/('package-backups-'+args.run_id)
    print(call([sys.executable,'-B',target/'scripts/backup_postgres.py','--pg-bin',BIN,'--database',database,'--destination',backup_root,'--data-dir',data,'--writers-stopped'],cli))
    backup=next(backup_root.glob('contasuite-*'));dump=backup/'database.dump'
    hashes=json.loads((backup/'sha256.json').read_text(encoding='utf-8-sig'))
    for name,digest in hashes.items():assert hashlib.sha256((backup/name).read_bytes()).hexdigest().upper()==digest.upper()
    restored=database+'_backup'
    with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(restored)))
    call([BIN/'pg_restore.exe','--exit-on-error','--dbname',restored,dump],cli)
    with psycopg.connect(**credentials,dbname=restored) as db:assert db.execute('SELECT count(*) FROM user_accounts').fetchone()[0]==1
    print(call([install,*common,'Update',dump],env))
    # Verify schema from the extracted package, not the source checkout.
    print(call([sys.executable,'-B',target/'scripts/schema_admin.py','--data-dir',data],env))
    result=dict(synthetic_only=True,package_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),install='passed CMD',existing_install_refused=True,update='passed CMD',backup_restore='passed Python',http=checks,powershell='blocked by execution policy; not changed',windows_service_registration='not_executed',external_dependency_install='not_executed; reused tested Python environment')
    (RUN/'package-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS: extracted Windows install/update/start/backup scripts, PostgreSQL restore and packaged frontend/session.')
if __name__=='__main__':main()
