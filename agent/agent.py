"""Outbound-only local worker. Supported operation in 0.1: read-only folder inventory."""
import argparse
import json
import logging
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlparse

SUPPORTED={'.pdf','.xml','.cer','.key'}
MAX_FILES=3000

def scan_folder(folder: str, allowed_roots: list[str]) -> dict:
    base=Path(folder).resolve(strict=True)
    roots=[Path(p).resolve(strict=True) for p in allowed_roots]
    if not base.is_dir() or not any(base.is_relative_to(root) for root in roots):
        raise ValueError('La carpeta no está dentro de las rutas autorizadas del agente')
    files=[];warnings=[];visited=0;directories=0;started=time.monotonic()
    def on_error(error):warnings.append('No se pudo leer una subcarpeta por permisos o disponibilidad')
    for directory,dirs,names in os.walk(base, followlinks=False, onerror=on_error):
        directories+=1
        if directories>10000 or time.monotonic()-started>60:
            return {'files':files,'truncated':True,'warnings':list(set(warnings))[:10]}
        # Resolve junctions and symlinks; never traverse outside the requested folder.
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink() and (Path(directory)/d).resolve().is_relative_to(base)]
        for name in names:
            visited+=1
            if visited>30000 or len(files)>=MAX_FILES or time.monotonic()-started>60:
                return {'files':files,'truncated':True,'warnings':list(set(warnings))[:10]}
            p=Path(directory)/name
            if p.suffix.lower() not in SUPPORTED or p.is_symlink():continue
            try:
                if not p.resolve().is_relative_to(base):continue
                files.append({'name':p.name,'relative_path':str(p.relative_to(base)),'extension':p.suffix.lower(),'size':p.stat().st_size})
            except OSError:warnings.append('Un archivo no se pudo inspeccionar')
    return {'files':files,'truncated':False,'warnings':list(set(warnings))[:10]}

def request(url,token,path,data):
    req=Request(url.rstrip('/')+'/api'+path,data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    with urlopen(req,timeout=20) as response:return json.load(response)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',default=str(Path(__file__).with_name('config.json')));args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    url=config['api_url'];parsed=urlparse(url)
    if parsed.scheme!='https' and not(parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}):
        raise SystemExit('La API remota necesita HTTPS. HTTP sólo está permitido en localhost.')
    token=os.getenv('CONTA_AGENT_TOKEN') or config.get('token','');agent_id=config['agent_id'];roots=config['allowed_roots']
    if not roots:raise SystemExit('Configura allowed_roots con las carpetas autorizadas antes de iniciar.')
    if len(token)<24:raise SystemExit('Configura el token del agente (mínimo 24 caracteres).')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    logging.info('Agente %s iniciado. Escaneo de sólo lectura.',agent_id)
    pending=None
    while True:
        try:
            request(url,token,'/agent/heartbeat',{'id':agent_id,'capabilities':['scan_folder']})
            # Retry delivery before claiming another job. Processing is not repeated on a transient network error.
            if pending:
                try:request(url,token,'/agent/jobs/'+pending[0]+'/result',pending[1])
                except __import__('urllib.error',fromlist=['HTTPError']).HTTPError as error:
                    if error.code!=409:raise
                pending=None
            job=request(url,token,'/agent/'+agent_id+'/claim',{})
            if job:
                logging.info('Procesando trabajo %s',job['id'])
                try:
                    if job['kind']!='scan_folder':raise ValueError('Motor no disponible en esta versión')
                    result=scan_folder(job['payload']['folder'],roots);status='completed'
                except Exception as e:result={'error':str(e)};status='failed'
                pending=(job['id'],{'agent_id':agent_id,'status':status,'result':result})
                continue
        except (URLError,TimeoutError,OSError,ValueError) as e:logging.warning('No se pudo comunicar con la API: %s',type(e).__name__)
        time.sleep(5)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('\nAgente detenido.')
