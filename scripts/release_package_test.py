"""Full private-runtime install/update/retirement and service-host tests, synthetic only."""
import json,os,sys,zipfile,hashlib,subprocess,time,argparse
from pathlib import Path
from release_lab import LAB,configuration
from integration_runtime import ROOT,RUN as PREVIOUS,BIN,call
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='first');args=parser.parse_args()
    assert args.run_id.isalnum() and len(args.run_id)<=12
    config,previous,env=configuration();work=ROOT/'.qa/release-closure'/('pkg-'+args.run_id);assert not work.exists();work.mkdir()
    source=work/'setup';archive=ROOT.parent/'ENTREGAS/CS_RELEASE_CLOSURE_20261111.zip'
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('PACKAGE_SHA256.json'))
        for name,digest in manifest.items():
            assert '..' not in Path(name).parts and not Path(name).is_absolute()
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
        z.extractall(source)
    import psycopg
    from psycopg import sql
    credentials=dict(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'])
    database='contasuite_release_pkg_'+args.run_id;empty=database+'_empty';restore=database+'_restore'
    with psycopg.connect(**credentials,dbname='postgres',autocommit=True) as db:
        assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==PREVIOUS/'cluster'
        for name in [database,empty,restore]:
            assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone()
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    data=work/'data';data.mkdir();env.update(DATABASE_URL=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+database,DATA_DIR=str(data),PATH=os.environ['SystemRoot']+'\\System32')
    for key in ('PYTHONHOME','PYTHONPATH'):env.pop(key,None)
    python=source/'runtime/python.exe';installer=source/'app/scripts/install_release.py';v1=work/'v1';v2=work/'v2'
    print(call([python,'-B',installer,'--mode','Install','--destination',v1,'--data-dir',data],env))
    refused=subprocess.run([str(x) for x in [python,'-B',installer,'--mode','Install','--destination',v1,'--data-dir',data]],env=env,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));assert refused.returncode!=0
    installed_python=v1/'runtime/python.exe'
    smoke=call([installed_python,'-I','-B','-c',"import sys,fastapi,psycopg,ssl,cryptography,pydantic; assert 'runtime' in sys.prefix; assert all('site-packages' not in p or 'runtime' in p for p in sys.path); print('private runtime isolated')"],env);assert 'isolated' in smoke
    stdout=(work/'service-console.txt').open('w')
    private=work/'private';private.mkdir();service_config=private/'service.json'
    keys=('DATABASE_URL','APP_TOKEN','AGENT_TOKEN','CS_ALLOWED_HOSTS')
    service_config.write_text(json.dumps({k:env[k] for k in keys}),encoding='utf-8')
    service_env=env.copy()
    for k in keys:service_env.pop(k,None)
    service=subprocess.Popen([str(x) for x in [installed_python,'-B',v1/'app/scripts/windows_service.py','--data-dir',data,'--log-dir',work/'logs','--config-file',service_config,'--port','8059','--console-test-seconds','15']],env=service_env,stdout=stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    import httpx
    with httpx.Client(base_url='http://127.0.0.1:8059',timeout=2) as client:
        for _ in range(50):
            assert service.poll() is None,'Service host stopped before readiness'
            try:
                if client.get('/api/health').status_code==200:break
            except httpx.TransportError:pass
            time.sleep(.2)
        else:raise AssertionError('Service host readiness timeout')
        assert client.get('/').status_code==200
        r=client.post('/api/auth/bootstrap',headers={'Authorization':'Bearer '+config['app_token']},json={'username':'private_runtime_admin','display_name':'Synthetic private runtime','password':'Private-Synthetic-2026!'});assert r.status_code==201,r.text
        assert client.post('/api/auth/login',json={'username':'private_runtime_admin','password':'Private-Synthetic-2026!'}).status_code==200
        assert client.get('/api/state').status_code==200
        assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    assert service.wait(timeout=35)==0;stdout.close();states=(work/'service-console.txt').read_text()
    assert all(marker in states for marker in ['STATE 2 0','STATE 4 0','STATE 3 0','STATE 1 0'])
    assert 'shutdown complete' in (work/'logs/api.log').read_text().lower()
    failed_env=env.copy();failed_env['DATABASE_URL']=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+empty
    failed=subprocess.run([str(x) for x in [installed_python,'-B',v1/'app/scripts/windows_service.py','--data-dir',work/'empty-data','--log-dir',work/'failure-logs','--port','8059','--console-test-seconds','3']],env=failed_env,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert failed.returncode==1 and 'STATE 1 1' in failed.stdout
    with psycopg.connect(**credentials,dbname=empty) as db:assert db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
    cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(previous['port']),PGUSER='recovery_test',PGPASSWORD=previous['password'])
    print(call([installed_python,'-B',v1/'app/scripts/backup_postgres.py','--pg-bin',BIN,'--database',database,'--destination',work/'backups','--data-dir',data,'--writers-stopped'],cli))
    backup=next((work/'backups').glob('contasuite-*'));dump=backup/'database.dump'
    call([BIN/'pg_restore.exe','--exit-on-error','--dbname',restore,dump],cli)
    with psycopg.connect(**credentials,dbname=restore) as db:assert db.execute('SELECT count(*) FROM user_accounts').fetchone()[0]==1
    print(call([python,'-B',installer,'--mode','Update','--destination',v2,'--data-dir',data,'--backup',dump,'--writers-stopped'],env))
    print(call([python,'-B',installer,'--mode','Uninstall','--destination',v1,'--data-dir',data,'--writers-stopped'],env))
    assert not v1.exists() and len(list(work.glob('v1.retired-*')))==1 and data.is_dir()
    with psycopg.connect(**credentials,dbname=database) as db:assert db.execute('SELECT count(*) FROM user_accounts').fetchone()[0]==1
    result={'synthetic_only':True,'package_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'private_python':'isolated; PATH contains no Python','install':'passed','update':'passed; new directory','retirement':'passed; database/data preserved','service_host':'START_PENDING/RUNNING/STOP_PENDING/STOPPED, hidden, graceful shutdown','failure':'exit1, incompatible schema unchanged','backup_restore':'passed','SCM_registration':'not executed; creation probe WinError5','TLS_LAN':'not executed; no authorized external client/certificate'}
    (LAB/('package-results-'+args.run_id+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS: private runtime, hidden service host, failure handling, installation/update, reversible uninstall and restore')
if __name__=='__main__':main()
