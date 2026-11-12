"""Explicit runtime for packaged installations. Never provisions configuration or schema."""
import argparse,os,sys,threading,ipaddress,json
from pathlib import Path

def api_server(port=8000,host='127.0.0.1',stop_event=None,on_ready=None,log_config=None):
    import uvicorn
    server=uvicorn.Server(uvicorn.Config('app.main:app',host=host,port=port,workers=1,proxy_headers=True,
        forwarded_allow_ips='127.0.0.1',log_config=log_config or uvicorn.config.LOGGING_CONFIG,timeout_graceful_shutdown=25))
    def watch():
        announced=False
        while not server.should_exit:
            if server.started and not announced:
                announced=True
                if on_ready:on_ready()
            if stop_event and stop_event.wait(.1):server.should_exit=True;break
            if stop_event is None:break
    threading.Thread(target=watch,daemon=True).start();server.run()
    return bool(server.started)

def configure(data_dir):
    for name in ('DATABASE_URL','APP_TOKEN','AGENT_TOKEN'):
        if not os.environ.get(name):raise ValueError(name+' must be explicitly provisioned; no dotenv fallback')
    if not data_dir.is_absolute():raise ValueError('Use an absolute data directory')
    os.environ.update(PYTHON_DOTENV_DISABLED='1',DATA_DIR=str(data_dir),SEED_DEMO='false')
    os.environ.setdefault('CS_STORAGE_ALLOWED_ROOTS','[]');os.environ.setdefault('CS_STORAGE_SMB_ALLOWED_ROOTS','[]')
    os.environ.setdefault('CS_ALLOWED_HOSTS',json.dumps(['127.0.0.1','localhost','[::1]']))
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--mode',choices=['api','alerts','index'],default='api')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--allow-lan',action='store_true')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    if not ipaddress.ip_address(args.host).is_loopback and (not args.allow_lan or os.environ.get('CS_TLS_TERMINATED')!='1'):parser.error('Non-loopback binding requires explicit LAN/TLS configuration')
    try:configure(args.data_dir)
    except ValueError as exc:parser.error(str(exc))
    if args.mode=='api':
        api_server(args.port,args.host)
    else:
        from app.database import engine
        from app.schema_compatibility import assert_schema
        assert_schema(engine)
        from app.storage.worker import main as worker
        sys.argv=['worker','--mode',args.mode];worker()
if __name__=='__main__':main()
