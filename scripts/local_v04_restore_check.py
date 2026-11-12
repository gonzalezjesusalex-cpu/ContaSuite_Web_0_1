"""Restore newest dev snapshot into another new database in the same verified lab cluster."""
import os,json,time,subprocess
from local_v04 import environment,LAB,BIN,PORT,USER,command
def main():
    _,engine,values=environment();engine.dispose()
    import psycopg
    source=sorted((LAB/'backups').glob('*.dump'))[-1]
    name='contasuite_dev_v04_restore_'+str(int(time.time()))
    env=dict(os.environ,PGPASSWORD=values['database'])
    with psycopg.connect(host='127.0.0.1',port=PORT,user=USER,password=values['database'],dbname='postgres',autocommit=True) as c:
        # environment() already verified host, user, port and actual data directory.
        c.execute('CREATE DATABASE '+name)
    command([BIN/'pg_restore.exe','-h','127.0.0.1','-p',str(PORT),'-U',USER,'-d',name,'--exit-on-error',source],env=env)
    with psycopg.connect(host='127.0.0.1',port=PORT,user=USER,password=values['database'],dbname=name) as c:
        assert c.execute("SELECT value FROM settings WHERE key='v04_synthetic_seed'").fetchone()[0]=='true'
        assert c.execute('SELECT count(*) FROM fiscal_records').fetchone()[0]>=5
        count=c.execute('SELECT count(*) FROM companies').fetchone()[0]
    result={'restored_database':name,'synthetic_seed_verified':True,'company_count':count,'same_verified_lab_cluster':True}
    (LAB/'restore-report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':
    try:main()
    except Exception:print('Restauración de prueba detenida; no se muestran credenciales ni mensajes internos.');raise SystemExit(1)
