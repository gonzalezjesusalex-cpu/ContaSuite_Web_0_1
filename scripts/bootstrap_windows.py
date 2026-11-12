"""Select tested Windows Python runtimes and install only the required database profile."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
SUPPORTED={(3,12),(3,11)}
PROBE='import json,sys,struct; print(json.dumps([sys.version_info.major,sys.version_info.minor,struct.calcsize("P")*8]))'

def probe(command):
    try:
        result=subprocess.run([*command,'-c',PROBE],capture_output=True,text=True,timeout=20)
        major,minor,bits=json.loads(result.stdout.strip())
        return result.returncode==0 and (major,minor) in SUPPORTED and bits==64
    except (OSError,ValueError,subprocess.TimeoutExpired):return False

def select_python():
    for tag in ['-3.12','-3.11']:
        command=['py',tag]
        if probe(command):return command
    raise RuntimeError('Instala Python 3.12 de 64 bits con el lanzador py. Puedes conservar Python 3.15: ContaSuite seleccionara 3.12. No se modificaron tus datos.')

def profile(portable):
    env=ROOT/'.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('DATABASE_URL='):
                return 'base' if line.split('=',1)[1].strip().strip('\"\'').startswith('sqlite:') else 'postgres'
    return 'base' if portable else 'postgres'

def main():
    mode=profile('--portable' in sys.argv)
    venv=ROOT/'.venv';python=venv/'Scripts'/'python.exe'
    if not python.exists() or not probe([str(python)]):
        selected=select_python()
        if venv.exists():
            backup=ROOT/('.venv-anterior-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            venv.rename(backup)
            print('Entorno Python anterior conservado en '+backup.name)
        subprocess.run([*selected,'-m','venv',str(venv)],check=True)
    requirements=ROOT/'backend'/('requirements-base.txt' if mode=='base' else 'requirements.txt')
    signature=hashlib.sha256((requirements.read_bytes()+(ROOT/'backend/requirements-base.txt').read_bytes()+str(python).encode())).hexdigest()
    stamp=venv/'contasuite-dependencies.txt'
    ready=stamp.exists() and stamp.read_text()==signature
    if ready:
        ready=subprocess.run([str(python),'-m','pip','check'],capture_output=True).returncode==0
    if not ready:
        print('Instalando dependencias: '+('SQLite - prueba local' if mode=='base' else 'PostgreSQL'))
        subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],cwd=ROOT,check=True)
        stamp.write_text(signature)
    print('Entorno listo.')

if __name__=='__main__':
    try:main()
    except subprocess.CalledProcessError as error:
        print('\nNo se pudo preparar el entorno. Revisa el error de Python/pip mostrado arriba. No se borro el entorno ni tus datos.');sys.exit(error.returncode or 1)
    except (RuntimeError,OSError) as error:print('\n'+str(error));sys.exit(1)
