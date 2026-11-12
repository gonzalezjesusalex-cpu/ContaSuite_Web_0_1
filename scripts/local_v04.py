"""Isolated Windows PostgreSQL lab. Never reads the installation .env or its data."""
import os,sys,json,secrets,subprocess,socket,ctypes,importlib.util,getpass,hashlib
from pathlib import Path
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'.qa'/'dev-v04';BIN=LAB/'runtime'/'pgsql'/'bin';CLUSTER=LAB/'cluster'
DB='contasuite_dev_v04';USER='contasuite_lab';PORT=55484;API=8044;WEB=4184
class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_char))]
def protect(data,decrypt=False):
    buffer=ctypes.create_string_buffer(data);src=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_char)));out=Blob()
    f=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not f(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)):raise RuntimeError('DPAPI unavailable')
    try:return ctypes.string_at(out.data,out.size)
    finally:ctypes.windll.kernel32.LocalFree(out.data)
def secret_values(create=False):
    path=LAB/'secrets.dpapi'
    if not path.exists():
        if not create:raise RuntimeError('Laboratorio no preparado')
        values={k:secrets.token_urlsafe(32) for k in ['database','app','agent','admin_password','reader_password']}
        path.write_bytes(protect(json.dumps(values).encode()))
    return json.loads(protect(path.read_bytes(),True))
def command(args,**kw):
    r=subprocess.run([str(a) for a in args],capture_output=True,**kw)
    if r.returncode:raise RuntimeError('Falló una operación local de PostgreSQL; no se imprimieron argumentos ni salidas sensibles.')
    return r
def initialize_cluster(password):
    import threading
    from uuid import uuid4
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateNamedPipeW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
    kernel.CreateNamedPipeW.restype=wintypes.HANDLE
    for name in ['ConnectNamedPipe','WriteFile','CloseHandle']:
        getattr(kernel,name).restype=wintypes.BOOL
    kernel.ConnectNamedPipe.argtypes=[wintypes.HANDLE,ctypes.c_void_p]
    kernel.WriteFile.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    pipe_name='\\\\.\\pipe\\ContaSuiteLabInit-'+uuid4().hex
    handle=kernel.CreateNamedPipeW(pipe_name,2,0,1,4096,4096,30000,None)
    if handle==wintypes.HANDLE(-1).value:raise RuntimeError('No se pudo crear la tubería privada')
    def writer():
        if kernel.ConnectNamedPipe(handle,None) or ctypes.get_last_error()==535:
            data=(password+'\n').encode();count=wintypes.DWORD();kernel.WriteFile(handle,data,len(data),ctypes.byref(count),None)
        kernel.CloseHandle(handle)
    thread=threading.Thread(target=writer,daemon=True);thread.start()
    command([BIN/'initdb.exe','-D',CLUSTER,'-U',USER,'--encoding=UTF8','--locale=C','--auth=scram-sha-256','--pwfile='+pipe_name],timeout=60)
    thread.join(2)
def setup_pg():
    LAB.mkdir(parents=True,exist_ok=True)
    if not BIN.exists():
        from zipfile import ZipFile
        archive=LAB/'runtime'/'postgresql.zip'
        with ZipFile(archive) as z:
            for i in z.infolist():
                target=(LAB/'runtime'/i.filename).resolve()
                if not target.is_relative_to((LAB/'runtime').resolve()):raise RuntimeError('Archivo inválido')
            z.extractall(LAB/'runtime')
    values=secret_values(True)
    if not (CLUSTER/'PG_VERSION').exists():
        initialize_cluster(values['database'])
        with (CLUSTER/'postgresql.conf').open('a') as f:f.write(f"\nlisten_addresses='127.0.0.1'\nport={PORT}\nlogging_collector=off\nlog_statement='none'\nlog_min_error_statement='panic'\n")
        (LAB/'isolation.json').write_text(json.dumps({'database':DB,'user':USER,'host':'127.0.0.1','port':PORT,'cluster':str(CLUSTER.resolve()),'lab_version':'0.4'}))
    start_pg()
    import psycopg
    with psycopg.connect(host='127.0.0.1',port=PORT,user=USER,password=values['database'],dbname='postgres',autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==CLUSTER.resolve()
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(DB,)).fetchone():c.execute('CREATE DATABASE '+DB)
    print('PostgreSQL aislado preparado: 127.0.0.1:55484 / contasuite_dev_v04')
def start_pg():
    marker=json.loads((LAB/'isolation.json').read_text())
    if marker.get('database')!=DB or marker.get('port')!=PORT or Path(marker.get('cluster','')).resolve()!=CLUSTER.resolve() or not CLUSTER.resolve().is_relative_to(ROOT.resolve()):raise RuntimeError('Clúster no verificable: operación detenida')
    check=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(CLUSTER),'status'],capture_output=True)
    if check.returncode:
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',PORT))==0:raise RuntimeError('Puerto ocupado por otro proceso: operación detenida')
        result=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(CLUSTER),'-l',str(LAB/'postgres.log'),'-w','start'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=40)
        if result.returncode:raise RuntimeError('No se pudo iniciar el clúster de pruebas')
def environment():
    config=json.loads((LAB/'isolation.json').read_text())
    assert config['database']==DB and config['port']==PORT and Path(config['cluster']).resolve()==CLUSTER.resolve()
    values=secret_values()
    from sqlalchemy import URL
    url=URL.create('postgresql+psycopg',username=USER,password=values['database'],host='127.0.0.1',port=PORT,database=DB)
    env=dict(os.environ,PYTHON_DOTENV_DISABLED='1',DATABASE_URL=url.render_as_string(hide_password=False),DATA_DIR=str(LAB/'data'),APP_TOKEN=values['app'],AGENT_TOKEN=values['agent'],SEED_DEMO='false',CS_STORAGE_ALLOWED_ROOTS='[]',CS_STORAGE_SMB_ALLOWED_ROOTS='[]',CONTA_VAULT_KEYRING='{}',CONTA_VAULT_ACTIVE_KEY='')
    # Explicit overrides stop dotenv fallback from admitting real roots or credentials.
    os.environ.update(env);sys.path.insert(0,str(ROOT/'backend'))
    from sqlalchemy import create_engine,text
    engine=create_engine(url,hide_parameters=True)
    with engine.connect() as c:
        row=c.execute(text('SELECT current_database(),current_user,inet_server_port()')).one()
        assert tuple(row)==(DB,USER,PORT)
        assert Path(c.execute(text('SHOW data_directory')).scalar()).resolve()==CLUSTER.resolve()
    return env,engine,values
def migrate():
    env,engine,values=environment()
    from sqlalchemy import text,inspect
    if inspect(engine).has_table('settings'):
        # Back up an existing dev database before repeat migrations. PGPASSWORD stays in memory.
        import time
        snapshot=LAB/'backups'/('before-migration-'+time.strftime('%Y%m%d-%H%M%S')+'.dump')
        snapshot.parent.mkdir(exist_ok=True)
        dump_env=dict(os.environ,PGPASSWORD=values['database'])
        command([BIN/'pg_dump.exe','-h','127.0.0.1','-p',str(PORT),'-U',USER,'-d',DB,'-Fc','-f',snapshot],env=dump_env)
    from app.storage.migrate import upgrade_storage
    upgrade_storage(engine)
    from app.database import Base
    from app import models
    Base.metadata.create_all(engine)
    for directory,name in [('fiscal_migrations','001_control_obligaciones.py'),('credential_migrations','001_vault.py'),('import_migrations','001_reconciliation.py'),('integral_migrations','001_integral.py')]:
        spec=importlib.util.spec_from_file_location(directory,ROOT/'backend'/directory/name);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with engine.begin() as c:mod.upgrade(c)
    engine.dispose();print('Migraciones verificadas en la base aislada v0.4.')
def seed():
    env,engine,values=environment()
    from local_v04_seed import seed_lab
    seed_lab(engine,values,LAB)
    engine.dispose();print('Datos sintéticos cargados. Usuario de revisión: devadmin. Configure su contraseña con el comando password.')
def password():
    env,engine,values=environment()
    from app.models import UserAccount
    from app.accounts import password_hash
    from sqlalchemy.orm import Session
    value=getpass.getpass('Nueva contraseña local de devadmin (mínimo 12 caracteres): ')
    if len(value)<12 or value!=getpass.getpass('Repita la contraseña: '):raise RuntimeError('Contraseña no confirmada')
    with Session(engine) as db:
        user=db.query(UserAccount).filter_by(username='devadmin').one();user.password_hash=password_hash(value);db.commit()
    values['admin_password']=value;(LAB/'secrets.dpapi').write_bytes(protect(json.dumps(values).encode()));print('Contraseña local actualizada, sin mostrarla.')
def run():
    start_pg();env,engine,_=environment();engine.dispose()
    for port in [API,WEB]:
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',port))==0:raise RuntimeError('Puerto local ocupado; no se detuvo ningún proceso existente')
    node=__import__('shutil').which('node')
    vite_config=LAB/'vite.config.mjs'
    vite_config.write_text("export default {server:{host:'127.0.0.1',port:4184,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8044',changeOrigin:false}}}}")
    processes=[];logs=[]
    try:
        for args,cwd,label in [([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(API)],ROOT/'backend','backend'),([node,str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--config',str(vite_config)],ROOT/'frontend','frontend')]:
            log=(LAB/(label+'.log')).open('ab');logs.append(log)
            processes.append(subprocess.Popen(args,cwd=cwd,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
        print('ContaSuite v0.4: http://127.0.0.1:4184 · Ctrl+C para detener. Sin indexador ni raíces SMB.')
        import time
        while all(p.poll() is None for p in processes):time.sleep(1)
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()
        for log in logs:log.close()
if __name__=='__main__':
    try:
        action=sys.argv[1] if len(sys.argv)>1 else 'run'
        {'setup':setup_pg,'migrate':migrate,'seed':seed,'password':password,'run':run}[action]()
    except Exception:
        print('Operación detenida de forma segura. Revisar aislamiento/dependencias; no se muestran detalles que puedan contener credenciales.');sys.exit(1)
