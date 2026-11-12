"""Only new synthetic databases in the previously verified disposable PostgreSQL cluster."""
import os,sys,json,secrets,subprocess,time
from pathlib import Path
from integration_runtime import ROOT,RUN as PREVIOUS,BIN,environment,call
LAB=ROOT/'.qa/release-closure/lab'
def configuration():
    config=json.loads((LAB/'synthetic.json').read_text());assert config['synthetic'] and config['database']=='contasuite_release_closure'
    previous=json.loads((PREVIOUS/'synthetic.json').read_text());env=environment(previous)
    env.update(DATABASE_URL=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+config['database'],DATA_DIR=str(LAB/'data'),APP_TOKEN=config['app_token'],AGENT_TOKEN=config['agent_token'],PYTHONPATH=str(ROOT/'backend'),CS_ALLOWED_HOSTS=json.dumps(['127.0.0.1','localhost','contasuite.test']))
    return config,previous,env
def main():
    mode=sys.argv[1]
    if mode=='prepare':
        assert not LAB.exists(),'Refuse to reuse a release laboratory'
        LAB.mkdir();(LAB/'data').mkdir()
        previous=json.loads((PREVIOUS/'synthetic.json').read_text());environment(previous)
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'],dbname='postgres',autocommit=True) as db:
            assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==PREVIOUS/'cluster'
            assert not db.execute("SELECT 1 FROM pg_database WHERE datname='contasuite_release_closure'").fetchone()
            db.execute('CREATE DATABASE contasuite_release_closure')
        config=dict(synthetic=True,database='contasuite_release_closure',app_token=secrets.token_hex(32),agent_token=secrets.token_hex(32))
        (LAB/'synthetic.json').write_text(json.dumps(config),encoding='utf-8')
        config,previous,env=configuration()
        output=call([sys.executable,'-B',ROOT/'scripts/schema_admin.py','--data-dir',LAB/'data','--apply','--new'],env)
        (LAB/'migration.txt').write_text(output);print(output)
    config,previous,env=configuration()
    if mode in ('stop','restart'):
        pid=int((LAB/'api.pid').read_text());command=f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if (-not $p -or $p.CommandLine -notmatch 'uvicorn app.main:app --host 127.0.0.1 --port 8058') {{ throw 'Unexpected process' }}; Stop-Process -Id {pid} -ErrorAction Stop"
        call(['powershell.exe','-NoProfile','-Command',command])
    if mode in ('serve','restart'):
        api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8058'],cwd=ROOT/'backend',env=env,stdout=(LAB/'api.log').open('w'),stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (LAB/'api.pid').write_text(str(api.pid))
        import httpx
        for _ in range(60):
            if api.poll() is not None:raise RuntimeError('Release startup failed; inspect isolated log')
            try:
                if httpx.get('http://127.0.0.1:8058/api/health',timeout=1).status_code==200:print('Release API ready on 127.0.0.1:8058');return
            except httpx.TransportError:pass
            time.sleep(.25)
        raise RuntimeError('Release API timeout')
if __name__=='__main__':main()
