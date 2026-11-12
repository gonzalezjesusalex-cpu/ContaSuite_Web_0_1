"""Create a clean project ZIP and a separate PRIVATE SQLite/data/config backup.

Original files are read only. SQLite's online backup API supplies a consistent DB
snapshot even while the application records audit events. No network is contacted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
from datetime import datetime,timezone
from uuid import uuid4
from zipfile import ZipFile,ZIP_DEFLATED
from urllib.parse import quote
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

EXCLUDED_DIRS={'.venv','node_modules','.qa','.git','__pycache__','.pytest_cache','.aws','.codex','.agents','RESPALDOS'}
PUBLIC_EXCLUDED_SUFFIXES={'.pyc','.pyo','.tsbuildinfo','.log','.db','.sqlite','.sqlite3','.zip','.key','.pem','.pfx','.p12'}


def files_under(root,*,project=False):
    for folder,dirs,files in os.walk(root,followlinks=False):
        accepted=[]
        for name in sorted(dirs):
            path=Path(folder)/name
            linked=path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)
            if linked:
                if not project:raise RuntimeError('El directorio de datos contiene un enlace; requiere respaldo explícito del destino.')
                continue
            if project and (name in EXCLUDED_DIRS or name.startswith('.venv-anterior-') or name=='data'):
                continue
            accepted.append(name)
        dirs[:]=accepted
        for name in sorted(files):
            path=Path(folder)/name
            if path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400):
                if not project:raise RuntimeError('Un archivo de datos es un enlace; requiere revisión.')
                continue
            relative=path.relative_to(root)
            if project and (name=='.env' or relative.as_posix()=='agent/config.json' or path.suffix.lower() in PUBLIC_EXCLUDED_SUFFIXES):
                continue
            yield path


def copy_into_zip(archive,path,name,*,secrets=()):
    before=path.stat()
    digest=hashlib.sha256()
    overlap=b''
    longest=max((len(s) for s in secrets),default=1)
    with path.open('rb') as source,archive.open(name,'w',force_zip64=True) as target:
        while chunk:=source.read(1024*1024):
            candidate=overlap+chunk
            if any(secret in candidate for secret in secrets):
                raise RuntimeError('Se detectó una clave de configuración en el proyecto limpio; no se completó el ZIP.')
            overlap=candidate[-(longest-1):] if longest>1 else b''
            digest.update(chunk)
            target.write(chunk)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise RuntimeError('Un archivo cambió durante la copia. Repetir el respaldo sin editar los archivos.')
    return digest.hexdigest()


def verify_zip(path,prefix,manifest_name):
    with ZipFile(path) as archive:
        if archive.testzip() is not None:raise RuntimeError('Falló la comprobación CRC del ZIP.')
        for name in archive.namelist():
            if not name.startswith(prefix+'/') or '..' in Path(name).parts or '\\' in name:
                raise RuntimeError('Nombre de archivo no portátil en el ZIP.')
        manifest=json.loads(archive.read(prefix+'/'+manifest_name))
        for relative,expected in manifest['files'].items():
            actual=hashlib.sha256(archive.read(prefix+'/'+relative)).hexdigest()
            if actual!=expected:raise RuntimeError('Falló la comprobación SHA-256 de un archivo.')
        return manifest


def create_backup(root,destination):
    root=root.resolve(strict=True)
    destination=destination.resolve(strict=False)
    if destination.is_relative_to(root):
        raise RuntimeError('El respaldo debe quedar fuera de la carpeta del proyecto.')
    values=dotenv_values(root/'.env')
    url=make_url(values.get('DATABASE_URL',''))
    if url.get_backend_name()!='sqlite' or not url.database or url.database==':memory:':
        raise RuntimeError('Esta herramienta requiere SQLite local. PostgreSQL necesita un respaldo específico de su servidor.')
    database=Path(url.database)
    if not database.is_absolute():database=root/database
    database=database.resolve(strict=True)
    data=Path(values.get('DATA_DIR') or root/'data')
    if not data.is_absolute():data=root/data
    data=data.resolve(strict=True)
    if not data.is_relative_to(root) or not database.is_relative_to(data):
        raise RuntimeError('La base y data deben estar dentro del proyecto para este traslado automático.')
    try:stamp=datetime.now(ZoneInfo('America/Mexico_City'))
    except ZoneInfoNotFoundError:stamp=datetime.now(timezone.utc)
    output=destination/('ContaSuite_'+stamp.strftime('%Y-%m-%d_%H-%M-%S')+'_'+uuid4().hex[:6])
    output.mkdir(parents=True,exist_ok=False)
    prefix='ContaSuite_Web_0_1'
    snapshot=output/'SQLite.snapshot'
    public=output/'ContaSuite_PROYECTO_USB.zip.partial'
    private=output/'ContaSuite_DATOS_PRIVADOS.zip.partial'
    source_uri='file:'+quote(database.as_posix(),safe='/:')+'?mode=ro'
    with closing(sqlite3.connect(source_uri,uri=True)) as source,closing(sqlite3.connect(snapshot)) as target:
        source.backup(target,pages=256,sleep=0.05)
    with closing(sqlite3.connect(snapshot)) as check:
        if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('La copia SQLite no superó la comprobación de integridad.')
        foreign_key_issues=len(check.execute('PRAGMA foreign_key_check').fetchall())
        tables=[r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        row_counts={t:check.execute('SELECT count(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
    sensitive=tuple(v.encode() for key,v in values.items() if v and len(v)>=16 and any(word in key.upper() for word in ('TOKEN','PASSWORD','SECRET')))
    project_files={}
    with ZipFile(public,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files_under(root,project=True):
            relative=path.relative_to(root).as_posix()
            project_files[relative]=copy_into_zip(archive,path,prefix+'/'+relative,secrets=sensitive)
        archive.writestr(prefix+'/MANIFIESTO_PROYECTO.json',json.dumps({
            'created_at':stamp.isoformat(),'files':project_files,'contains_private_data':False,
            'excluded':['.env','data','agent/config.json','.venv','node_modules','.qa','caches','private-key containers']},ensure_ascii=False,indent=2))
    private_files={}
    excluded_db={database,*[Path(str(database)+suffix) for suffix in ('-wal','-shm','-journal')]}
    source_files=list(files_under(data))
    inventory={p.relative_to(data).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in source_files if p not in excluded_db}
    with ZipFile(private,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for path in [root/'.env',root/'agent'/'config.json',*source_files]:
            if path in excluded_db or not path.is_file():continue
            relative=path.relative_to(root).as_posix()
            private_files[relative]=copy_into_zip(archive,path,prefix+'/'+relative)
        database_relative=database.relative_to(root).as_posix()
        private_files[database_relative]=copy_into_zip(archive,snapshot,prefix+'/'+database_relative)
        archive.writestr(prefix+'/MANIFIESTO_DATOS_PRIVADOS.json',json.dumps({
            'created_at':stamp.isoformat(),'database_snapshot':'SQLite online backup API',
            'database_relative':database_relative,'sqlite_integrity':'ok','foreign_key_issues':foreign_key_issues,
            'database_row_counts':row_counts,'files':private_files,'encrypted':False,
            'notice':'PRIVADO: incluye configuración con claves. No compartir como distribución pública.'},ensure_ascii=False,indent=2))
    after_inventory={p.relative_to(data).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in files_under(data) if p not in excluded_db}
    if inventory!=after_inventory:
        raise RuntimeError('Los archivos de data cambiaron durante la copia. Repetir antes de usar los ZIP parciales.')
    verify_zip(public,prefix,'MANIFIESTO_PROYECTO.json')
    verify_zip(private,prefix,'MANIFIESTO_DATOS_PRIVADOS.json')
    with ZipFile(public) as archive:
        build=json.loads(archive.read(prefix+'/frontend/dist/contasuite-build.json'))
        for relative,expected in build['files'].items():
            if hashlib.sha256(archive.read(prefix+'/frontend/dist/'+relative)).hexdigest()!=expected:
                raise RuntimeError('La compilación incluida en el ZIP no coincide con su manifiesto.')
    final_public=public.with_suffix('')
    final_private=private.with_suffix('')
    public.rename(final_public)
    private.rename(final_private)
    snapshot.unlink()  # Only the snapshot created in this new backup directory.
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (final_public,final_private)}
    (output/'SHA256.txt').write_text(''.join(value+'  '+name+'\n' for name,value in hashes.items()),encoding='utf-8')
    (output/'LEEME_RESPALDO.md').write_text(
        '# Respaldo de ContaSuite\n\nFecha: '+stamp.isoformat()+'\n\n'
        '- `ContaSuite_PROYECTO_USB.zip`: proyecto y compilación; sin datos ni claves.\n'
        '- `ContaSuite_DATOS_PRIVADOS.zip`: SQLite consistente, data y configuración privada; ZIP sin cifrar.\n\n'
        'Copia ambos a una USB protegida para conservar el estado actual. En otra PC extrae primero el proyecto y luego los datos sobre la misma carpeta, antes de iniciar. '
        'Lee `ABRIR_EN_OTRA_PC.md` dentro del proyecto. Instala Python 3.12 de 64 bits con el lanzador py e inicia `INICIAR_PRUEBA.bat`; '
        'se necesita Internet para preparar dependencias. No se necesitan Node ni una copia de .venv para ejecutar el frontend compilado.\n\n'
        'Verificado: CRC y SHA-256 de todos los archivos, integridad SQLite y huellas de la compilación. '
        'No incluye archivos de carpetas externas ni recursos del servidor que sólo estén referenciados en el catálogo. '
        'Las rutas del agente deben configurarse para el nuevo equipo. No subir el ZIP privado a un repositorio ni compartirlo como entrega pública.\n',encoding='utf-8')
    return {'directory':str(output),'project_files':len(project_files),'private_files':len(private_files),
            'database_integrity':'ok','foreign_key_issues':foreign_key_issues,
            'archives':[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashes[p.name]} for p in (final_public,final_private)]}


def main():
    parser=argparse.ArgumentParser(description='Respaldo local y traslado USB, sin modificar la instalación')
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    result=create_backup(Path(__file__).resolve().parents[1],args.destination)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
