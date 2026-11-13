"""Native Windows SCM host. No service is registered merely by importing/running tests."""
import argparse,threading,logging,logging.handlers,sys,os,json,time
from pathlib import Path
START_PENDING,RUNNING,STOP_PENDING,STOPPED=2,4,3,1
class Lifecycle:
    def __init__(self,report):self.report=report;self.stop_event=threading.Event();self.state=START_PENDING;self.mutex=threading.RLock()
    def starting(self):
        with self.mutex:self.state=START_PENDING;self.report(self.state,0)
    def ready(self):
        with self.mutex:
            if not self.stop_event.is_set():self.state=RUNNING;self.report(self.state,0)
    def stop(self):
        with self.mutex:
            self.stop_event.set()
            if self.state not in (STOP_PENDING,STOPPED):self.state=STOP_PENDING;self.report(self.state,0)
    def finish(self,error=0):
        with self.mutex:self.state=STOPPED;self.report(self.state,error)

def execute(lifecycle,data_dir,port,log_dir,test_seconds=None,extra_workers=()):
    from service_runtime import configure,api_server
    log_dir.mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(log_dir/'service.log',maxBytes=10*1024*1024,backupCount=8,encoding='utf-8')
    logger=logging.getLogger('contasuite.service');logger.setLevel(logging.INFO);logger.addHandler(handler)
    lifecycle.starting()
    workers=[]
    failures=[]
    instance_lock=None
    try:
        configure(data_dir)
        # Windows releases this byte-range lock even after a process crash.
        import msvcrt
        data_dir.mkdir(parents=True,exist_ok=True)
        instance_lock=(data_dir/'.service.lock').open('a+b')
        instance_lock.seek(0);instance_lock.write(b'0');instance_lock.flush();instance_lock.seek(0)
        msvcrt.locking(instance_lock.fileno(),msvcrt.LK_NBLCK,1)
        # Schema readiness precedes every background task; never migrate on startup.
        from app.database import engine
        from app.schema_compatibility import assert_schema
        assert_schema(engine)
        from app.storage.worker import main as worker
        def run_worker(mode):
            try:
                logger.info('Background worker starting: %s',mode)
                worker(lifecycle.stop_event,['--mode',mode])
                logger.info('Background worker stopped: %s',mode)
            except BaseException:
                failures.append(mode);lifecycle.stop_event.set()
                logger.error('Background worker failed: %s',mode)
        def ready():
            for mode in ('alerts','index'):
                thread=threading.Thread(target=run_worker,args=(mode,),daemon=True,name='contasuite-'+mode)
                workers.append(thread);thread.start()
            for name,callback in extra_workers:
                def extra(name=name,callback=callback):
                    try:callback(lifecycle.stop_event)
                    except BaseException:
                        failures.append(name);lifecycle.stop_event.set();logger.error('Managed component failed: %s',name)
                thread=threading.Thread(target=extra,daemon=True,name=name);workers.append(thread);thread.start()
            lifecycle.ready()
        if test_seconds:threading.Timer(test_seconds,lifecycle.stop).start()
        logger.info('Service starting')
        config={'version':1,'disable_existing_loggers':False,'handlers':{'file':{'class':'logging.handlers.RotatingFileHandler','filename':str(log_dir/'api.log'),'maxBytes':10485760,'backupCount':8,'encoding':'utf-8'}},'loggers':{'uvicorn':{'handlers':['file'],'level':'INFO','propagate':False},'uvicorn.error':{'handlers':['file'],'level':'INFO','propagate':False},'uvicorn.access':{'handlers':['file'],'level':'INFO','propagate':False}}}
        started=api_server(port,stop_event=lifecycle.stop_event,on_ready=ready,log_config=config)
        if not started:raise RuntimeError('startup failed')
        lifecycle.stop_event.set()
        deadline=time.monotonic()+25
        for thread in workers:thread.join(timeout=max(0,deadline-time.monotonic()))
        if failures or any(thread.is_alive() for thread in workers):raise RuntimeError('worker shutdown failed')
        lifecycle.finish();logger.info('Service stopped cleanly');return 0
    except BaseException as exc:
        logger.error('Service failed (%s); inspect isolated application log',type(exc).__name__)
        lifecycle.finish(1);return 1
    finally:
        lifecycle.stop_event.set()
        if instance_lock:instance_lock.close()
        logger.removeHandler(handler);handler.close()

def scm(name,data_dir,port,log_dir):
    import ctypes as c
    from ctypes import wintypes as w
    api=c.WinDLL('advapi32',use_last_error=True)
    class Status(c.Structure):_fields_=[(n,w.DWORD) for n in ['type','state','accepted','exit','specific','checkpoint','wait']]
    HANDLER=c.WINFUNCTYPE(w.DWORD,w.DWORD,w.DWORD,c.c_void_p,c.c_void_p)
    MAIN=c.WINFUNCTYPE(None,w.DWORD,c.POINTER(w.LPWSTR))
    class Entry(c.Structure):_fields_=[('name',w.LPWSTR),('main',MAIN)]
    api.RegisterServiceCtrlHandlerExW.argtypes=[w.LPCWSTR,HANDLER,c.c_void_p];api.RegisterServiceCtrlHandlerExW.restype=w.HANDLE
    api.SetServiceStatus.argtypes=[w.HANDLE,c.POINTER(Status)];api.SetServiceStatus.restype=w.BOOL
    api.StartServiceCtrlDispatcherW.argtypes=[c.POINTER(Entry)];api.StartServiceCtrlDispatcherW.restype=w.BOOL
    handle=None
    def report(state,error):
        status=Status(0x10,state,5 if state==RUNNING else 0,error,0,1 if state in (START_PENDING,STOP_PENDING) else 0,90000 if state in (START_PENDING,STOP_PENDING) else 0)
        if not api.SetServiceStatus(handle,c.byref(status)):raise c.WinError(c.get_last_error())
    lifecycle=Lifecycle(report)
    @HANDLER
    def control(code,event,event_data,context):
        if code in (1,5):lifecycle.stop();return 0
        if code==4:return 0
        return 120
    @MAIN
    def service_main(count,args):
        nonlocal handle
        handle=api.RegisterServiceCtrlHandlerExW(name,control,None)
        if not handle:return
        execute(lifecycle,data_dir,port,log_dir)
    table=(Entry*2)(Entry(name,service_main),Entry(None,MAIN()))
    if not api.StartServiceCtrlDispatcherW(table):raise c.WinError(c.get_last_error())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',default='ContaSuiteApi')
    parser.add_argument('--data-dir',type=Path,required=True);parser.add_argument('--log-dir',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8062);parser.add_argument('--console-test-seconds',type=float)
    parser.add_argument('--config-file',type=Path)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    if not args.data_dir.is_absolute() or not args.log_dir.is_absolute():parser.error('Absolute data/log directories required')
    if args.config_file:
        if not args.config_file.is_absolute() or args.config_file.suffix.lower()!='.json':parser.error('External absolute JSON configuration required')
        from secure_config import load
        values=load(args.config_file)
        allowed={'DATABASE_URL','APP_TOKEN','AGENT_TOKEN','CS_ALLOWED_HOSTS','CS_STORAGE_ALLOWED_ROOTS','CS_STORAGE_SMB_ALLOWED_ROOTS','CS_LOCAL_IMPORT_ENABLED','CS_LOCAL_IMPORT_DATABASE','CS_LOCAL_IMPORT_ROOTS'}
        if not isinstance(values,dict) or set(values)-allowed or any(not isinstance(v,str) for v in values.values()):parser.error('Invalid service configuration')
        os.environ.update(values)
    if args.console_test_seconds:
        return execute(Lifecycle(lambda state,error:print('STATE',state,error,flush=True)),args.data_dir,args.port,args.log_dir,args.console_test_seconds)
    if os.name!='nt':parser.error('Windows SCM required')
    scm(args.name,args.data_dir,args.port,args.log_dir)
if __name__=='__main__':raise SystemExit(main())
