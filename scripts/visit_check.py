"""Read-only preflight. Never migrates a database, opens UNC or prints credentials."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote


def inspect_project(root):
    checks=[]
    def add(name,state,detail):checks.append({'check':name,'state':state,'detail':detail})
    add('python','ok' if sys.version_info>=(3,11) and sys.maxsize>2**32 else 'error',platform.python_version()+' / '+platform.architecture()[0])
    for package in ['fastapi','sqlalchemy','alembic','cryptography','pypdf','uvicorn','defusedxml','python-dotenv']:
        try:add(package,'ok',importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:add(package,'error','Dependencia no instalada')
    values={}
    env=root/'.env'
    if env.is_file():
        try:
            from dotenv import dotenv_values
            values={**dotenv_values(env),**os.environ}
        except ImportError:
            values=dict(os.environ)
    add('configuration','ok' if env.is_file() else 'error','Archivo de entorno presente' if env.is_file() else 'Falta configurar la instalación')
    add('installation_key','ok' if len(values.get('APP_TOKEN',''))>=24 else 'error','Sólo se comprueba presencia y tamaño; no se muestra la clave')
    manifest=root/'frontend'/'dist'/'contasuite-build.json'
    try:
        build=json.loads(manifest.read_text(encoding='utf-8'))
        files=build['files']
        for key,sha in files.items():
            target=root/'frontend'/'dist'/key
            if '..' in Path(key).parts or Path(key).is_absolute() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
                raise ValueError
        required={'named_sessions','storage_connector','certificate_dashboard'}
        if not required.issubset(build['features']):raise ValueError
        add('compiled_frontend','ok','Archivos y huellas de la compilación verificados')
    except (OSError,ValueError,KeyError,TypeError):
        add('compiled_frontend','error','Falta una compilación actual verificada o sus archivos cambiaron')
    try:
        from sqlalchemy.engine import make_url
        url=make_url(values.get('DATABASE_URL',''))
        if url.get_backend_name()=='sqlite' and url.database and url.database!=':memory:':
            path=Path(url.database)
            if str(path).startswith(('\\\\','//')):raise ValueError('UNC is not probed')
            if not path.is_absolute():path=root/path
            uri='file:'+quote(path.absolute().as_posix(),safe='/:')+'?mode=ro'
            with sqlite3.connect(uri,uri=True) as connection:
                version=connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]
                initialized=bool(connection.execute('SELECT initialized FROM identity_state').fetchone()[0])
            add('database_schema','ok' if version=='cs_storage_0004' else 'pending','Revisión '+version)
            add('personal_accounts','ok' if initialized else 'pending','Alta inicial completada' if initialized else 'Crear primer administrador al iniciar')
        else:
            add('database_schema','pending','Base no SQLite: comprobar conectividad y migración con el técnico; no se sondea por red')
    except Exception:
        add('database_schema','pending','Base nueva o esquema pendiente; respaldar antes de iniciar migraciones')
    add('smb','configured' if values.get('CS_STORAGE_SMB_ALLOWED_ROOTS','[]') != '[]' else 'pending',
        'Proveedor UNC de sólo lectura con identidad Windows; comprobar disponibilidad desde Configuración. Este diagnóstico no accede a la red.')
    return {'product':'ContaSuite','checks':checks,'ready_for_local_demo':not any(c['state']=='error' for c in checks)}


def main():
    parser=argparse.ArgumentParser(description='Diagnóstico de visita sin migraciones ni conexión al despacho')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report=inspect_project(args.root.absolute())
    text=json.dumps(report,ensure_ascii=False,indent=2)
    print(text)
    if args.report:
        with args.report.open('x',encoding='utf-8') as output:output.write(text+'\n')
    return 0 if report['ready_for_local_demo'] else 1


if __name__=='__main__':
    sys.exit(main())
