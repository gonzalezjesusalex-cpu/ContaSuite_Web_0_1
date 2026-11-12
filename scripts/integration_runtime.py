"""Create only a NEW disposable PostgreSQL cluster. Never loads dotenv or old cluster data."""
import os,sys,json,secrets,socket,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'.qa'/'integration-recovery-20261111-v3'
BIN=ROOT/'.qa'/'dev-v04'/'runtime'/'pgsql'/'bin'
def call(args,env=None):
    background=('pg_ctl.exe' in str(args[0]) and 'start' in args)
    result=subprocess.run([str(x) for x in args],env=env,stdout=subprocess.DEVNULL if background else subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(result.stdout[-3000:])
    return result.stdout
def environment(config):
    assert config['synthetic'] is True and Path(config['cluster']).resolve()==RUN/'cluster'
    env=os.environ.copy();env.update(PYTHON_DOTENV_DISABLED='1',DATA_DIR=str(RUN/'data'),DATABASE_URL=f"postgresql+psycopg://recovery_test:{config['password']}@127.0.0.1:{config['port']}/contasuite_recovery",APP_TOKEN=config['app_token'],AGENT_TOKEN=secrets.token_hex(32),SEED_DEMO='false',CS_STORAGE_ALLOWED_ROOTS='[]',CS_STORAGE_SMB_ALLOWED_ROOTS='[]')
    for key in list(env):
        if key.startswith(('CONTA_VAULT_','CS_VAULT_','VAULT_')):env.pop(key)
    return env
def main():
    if sys.argv[1]=='prepare':
        assert not RUN.exists(),'Refuse to reuse any existing test environment'
        assert (BIN/'initdb.exe').is_file()
        RUN.mkdir();(RUN/'data').mkdir()
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        config=dict(synthetic=True,purpose='CS-INTEGRATION-RECOVERY-001',cluster=str(RUN/'cluster'),port=port,password=secrets.token_hex(24),app_token=secrets.token_hex(32))
        pw=RUN/'initdb-test-password.tmp';pw.write_text(config['password'],encoding='utf-8')
        try:call([BIN/'initdb.exe','-D',RUN/'cluster','-U','recovery_test','--pwfile='+str(pw),'--auth=scram-sha-256','--encoding=UTF8','--locale=C'])
        finally:pw.unlink()
        (RUN/'synthetic.json').write_text(json.dumps(config),encoding='utf-8')
        call([BIN/'pg_ctl.exe','-D',RUN/'cluster','-l',RUN/'postgres.log','-o',f'-h 127.0.0.1 -p {port}','-w','start'])
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=port,user='recovery_test',password=config['password'],dbname='postgres',autocommit=True) as db:
            actual=db.execute('SHOW data_directory').fetchone()[0]
            assert Path(actual).resolve()==RUN/'cluster'
            db.execute('CREATE DATABASE contasuite_recovery')
        (RUN/'synthetic.json').write_text(json.dumps(config),encoding='utf-8')
        print('New isolated synthetic PostgreSQL cluster prepared; no existing database reused.')
    config=json.loads((RUN/'synthetic.json').read_text());env=environment(config)
    if sys.argv[1]=='finish':
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=config['port'],user='recovery_test',password=config['password'],dbname='postgres',autocommit=True,connect_timeout=5) as db:
            assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==RUN/'cluster'
            if not db.execute("SELECT 1 FROM pg_database WHERE datname='contasuite_recovery'").fetchone():db.execute('CREATE DATABASE contasuite_recovery')
    if sys.argv[1] in ('prepare','migrate','finish'):
        args=[sys.executable,'-B',ROOT/'scripts/schema_admin.py','--data-dir',RUN/'data','--apply']
        if sys.argv[1] in ('prepare','finish'):args+=['--new']
        else:args+=['--backup',RUN/'verified-backup.dump']
        print(call(args,env))
    if sys.argv[1] in ('restart','stop'):
        pid=int((RUN/'api.pid').read_text())
        # Match the exact test process before stopping it; never stop by port/name alone.
        command=f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if (-not $p -or $p.CommandLine -notmatch 'uvicorn app.main:app --host 127.0.0.1 --port 8056') {{ throw 'Unexpected process; refusing to stop' }}; Stop-Process -Id {pid} -ErrorAction Stop"
        call(['powershell.exe','-NoProfile','-Command',command])
    if sys.argv[1] in ('serve','restart'):
        env['PYTHONPATH']=str(ROOT/'backend')
        api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8056'],cwd=ROOT/'backend',env=env,stdout=(RUN/'api.log').open('w'),stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (RUN/'api.pid').write_text(str(api.pid));print('Isolated API started on 127.0.0.1:8056')
        import time,httpx
        for _ in range(100):
            if api.poll() is not None:raise RuntimeError('Synthetic API startup failed; inspect its isolated log')
            try:
                if httpx.get('http://127.0.0.1:8056/api/health',timeout=1).status_code==200:break
            except httpx.TransportError:pass
            time.sleep(.2)
        else:raise RuntimeError('Synthetic API readiness timeout')
if __name__=='__main__':main()
