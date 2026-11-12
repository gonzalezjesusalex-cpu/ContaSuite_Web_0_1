"""Archivos subidos y copias verificadas; el motor de escritorio permanece intacto."""
import json
import re
import shutil
import stat
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .database import DATA, SessionLocal, session
from .models import Audit, Company, OrganizadorRun
from . import organizador_engine as motor

router = APIRouter(prefix='/api/organizador', tags=['Organizador CFDI'])
MAX_UPLOAD = 100 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
MAX_FILES = 5000
EXTENSIONS = {'.xml', '.pdf', '.xls', '.xlsx', '.xlsm'}


def folder(ident):
    return DATA / 'organizador' / ident


def get_run(db, ident):
    run = db.get(OrganizadorRun, ident)
    if not run:
        raise HTTPException(404, 'Análisis no encontrado')
    return run


def safe_path(name):
    raw = name.replace('\\', '/')
    parts = raw.split('/')
    if (not raw or len(raw) > 700 or raw.startswith('/') or
        any(not p or p in ('.', '..') or p.endswith((' ', '.')) or
            re.search(r'[<>:"|?*\x00-\x1f]', p) or
            re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I)
            for p in parts)):
        raise ValueError('La entrada contiene una ruta no válida para Windows.')
    return PurePosixPath(raw)


def extract_zip(archive, target):
    count = size = ignored = 0
    seen = set()
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > MAX_FILES * 2:
            raise ValueError('El ZIP contiene demasiadas entradas.')
        for info in z.infolist():
            path = safe_path(info.filename.rstrip('/') if info.is_dir() else info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('No se admiten enlaces dentro del ZIP.')
            if info.is_dir():
                continue
            if path.suffix.lower() not in EXTENSIONS:
                ignored += 1
                continue
            if info.flag_bits & 1:
                raise ValueError('El ZIP está protegido con contraseña.')
            count += 1
            size += info.file_size
            if count > MAX_FILES or size > MAX_EXPANDED:
                raise ValueError('Máximo 5,000 archivos o 500 MB descomprimidos.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError('Hay rutas repetidas dentro del ZIP.')
            seen.add(key)
            dest = target / str(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, dest.open('xb') as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
    if not count:
        raise ValueError('No hay PDF, XML o reportes Excel en la entrada.')
    return ignored


def source_root(source):
    # Admitir la carpeta base subida por el navegador o un único envoltorio ZIP.
    if any(p.is_dir() and p.name.casefold() in ('emitidos', 'recibidos', 'reportes') for p in source.iterdir()):
        return source
    children = list(source.iterdir())
    if len(children) == 1 and children[0].is_dir():
        child = children[0]
        if any(p.is_dir() and p.name.casefold() in ('emitidos', 'recibidos', 'reportes') for p in child.iterdir()):
            return child
    raise ValueError('La carpeta base debe contener Emitidos, Recibidos o Reportes. Conserva las rutas Tipo/RFC/AAAA-MM/archivo.')


def progress(ident, status, message):
    with SessionLocal() as db:
        db.execute(update(OrganizadorRun).where(OrganizadorRun.id == ident).values(status=status, message=message[:1000]))
        db.commit()


def load_plan(ident):
    data = json.loads((folder(ident) / 'plan.json').read_text(encoding='utf-8'))
    return motor.Plan(motor.Options(**data['options']), [motor.Item(**i) for i in data['items']])


def public_records(plan, records):
    source = Path(plan.options.source)
    target = Path(plan.options.destination)
    return [{**r, 'source': Path(r['source']).relative_to(source).as_posix(),
             'destination': Path(r['destination']).relative_to(target).as_posix() if r['destination'] else ''}
            for r in records]


def analyze(ident):
    try:
        root = folder(ident)
        ignored = extract_zip(root / 'input.zip', root / 'input') if (root / 'input.zip').exists() else 0
        source = source_root(root / 'input')
        with SessionLocal() as db:
            options = get_run(db, ident).options
        plan = motor.analyze(motor.Options(source=str(source), destination=str(root / 'output'), operation='copy',
                             **options), lambda n, total, m: progress(ident, 'analyzing', m))
        (root / 'plan.json').write_text(json.dumps(asdict(plan), ensure_ascii=False), encoding='utf-8')
        used = {Path(i.source).resolve() for i in plan.items if i.state == 'Listo'}
        unselected = sum(p.is_file() and p.resolve() not in used for p in source.rglob('*'))
        warnings = []
        if ignored:
            warnings.append(f'Se omitieron {ignored} archivos de formatos no admitidos.')
        if unselected:
            warnings.append(f'{unselected} archivos no coinciden con las rutas o filtros elegidos; no se organizarán. Las subcarpetas no se recorren.')
        if not plan.ready:
            warnings.append('No hay archivos listos. Revisa RFC, ejercicio, meses y estructura de origen. Se pueden generar las carpetas vacías del periodo.')
        summary = {'ready': len(plan.ready), 'omitted': sum(i.state == 'Omitido' for i in plan.items),
                   'unselected': unselected, 'copied': 0, 'duplicates': 0, 'errors': 0}
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.status = 'analyzed'
            run.message = 'Análisis terminado. Revisa las rutas antes de organizar.'
            run.summary = summary
            run.warnings = warnings
            db.add(Audit(company_id=run.company_id, action='Organizador CFDI: análisis terminado'))
            db.commit()
    except Exception as exc:
        progress(ident, 'error', 'No se pudo analizar: ' + str(exc))


def generate(ident):
    try:
        root = folder(ident)
        plan = load_plan(ident)
        result = motor.execute(plan, lambda n, total, m: progress(ident, 'generating', m))
        records = [asdict(i) for i in plan.items if i.state != 'Listo'] + result.records
        public = public_records(plan, records)
        (root / 'result.json').write_text(json.dumps(public, ensure_ascii=False), encoding='utf-8')
        motor.export_csv(root / 'auditoria.csv', public)
        with zipfile.ZipFile(root / 'result_pending.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for path in sorted((root / 'output').rglob('*')):
                z.write(path, path.relative_to(root / 'output').as_posix())
        (root / 'result_pending.zip').replace(root / 'result.zip')
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.summary = {**run.summary, 'copied': sum(r['state'] == 'Copiado' for r in records),
                           'duplicates': sum(r['state'] == 'Duplicado' for r in records), 'errors': result.errors}
            run.status = 'generated'
            run.message = 'Organización terminada.' if not result.errors else 'Organización terminada con errores. Revisa la auditoría.'
            db.add(Audit(company_id=run.company_id, action='Organizador CFDI: copias verificadas generadas'))
            db.commit()
    except Exception as exc:
        progress(ident, 'error', 'No se pudo organizar: ' + str(exc) + '. Carga nuevamente la entrada para repetir el proceso.')


@router.post('/runs', status_code=202)
async def start(background: BackgroundTasks, files: list[UploadFile] = File(...),
                rfc: str = Form(...), year: int = Form(...), months: str = Form(...),
                kinds: str = Form(''), extensions: str = Form(''),
                reports: bool = Form(True), company_id: str = Form(''), db: Session = Depends(session)):
    if company_id and not db.get(Company, company_id):
        raise HTTPException(404, 'Empresa no encontrada')
    if not files or len(files) > 1000:
        raise HTTPException(422, 'Selecciona hasta 1,000 archivos o un ZIP con hasta 5,000.')
    ident = str(uuid4())
    root = folder(ident)
    source = root / 'input'
    source.mkdir(parents=True)
    size = 0
    seen = set()
    try:
        options = dict(rfc=rfc.strip().upper(), year=year, months=sorted(set(int(m) for m in months.split(',') if m)),
                       kinds=list(dict.fromkeys(k for k in kinds.split(',') if k)),
                       extensions=list(dict.fromkeys(e for e in extensions.split(',') if e)), reports=reports)
        motor.validate(motor.Options(source=str(source), destination=str(root / 'output'), operation='copy', **options))
        is_zip = len(files) == 1 and Path(files[0].filename or '').suffix.lower() == '.zip'
        for file in files:
            path = safe_path(file.filename or '')
            if not is_zip and path.suffix.lower() not in EXTENSIONS:
                raise ValueError('Carga una carpeta con PDF/XML/reportes Excel o un único ZIP.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError('Hay archivos con la misma ruta.')
            seen.add(key)
            dest = root / 'input.zip' if is_zip else source / str(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, 'La carga admite hasta 100 MB por análisis.')
                    out.write(chunk)
        if not size:
            raise ValueError('La entrada está vacía.')
        run = OrganizadorRun(id=ident, company_id=company_id or None, options=options,
                             name=path.name[:255] if is_zip else f'{len(files)} archivos', message='Preparando entrada.')
        db.add(run)
        db.commit()
        background.add_task(analyze, ident)
        return run
    except ValueError as exc:
        db.rollback()
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        for file in files:
            await file.close()


@router.get('/runs')
def runs(db: Session = Depends(session)):
    return db.scalars(select(OrganizadorRun).order_by(OrganizadorRun.created_at.desc()).limit(50)).all()


@router.get('/runs/{ident}')
def detail(ident: str, db: Session = Depends(session)):
    run = get_run(db, ident)
    records = []
    if (folder(ident) / 'plan.json').exists():
        plan = load_plan(ident)
        records = public_records(plan, [asdict(i) for i in plan.items])
    if run.status == 'generated':
        records = json.loads((folder(ident) / 'result.json').read_text(encoding='utf-8'))
    return {'run': run, 'records': records}


@router.post('/runs/{ident}/generate', status_code=202)
def start_generate(ident: str, background: BackgroundTasks, db: Session = Depends(session)):
    get_run(db, ident)
    changed = db.execute(update(OrganizadorRun).where(OrganizadorRun.id == ident, OrganizadorRun.status == 'analyzed')
                         .values(status='generating', message='Copiando y verificando SHA-256.'))
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'Primero termina el análisis. Cada análisis sólo se ejecuta una vez.')
    background.add_task(generate, ident)
    return {'status': 'generating'}


@router.get('/runs/{ident}/download')
def download(ident: str, kind: str = 'zip', db: Session = Depends(session)):
    run = get_run(db, ident)
    if run.status != 'generated':
        raise HTTPException(409, 'Los resultados aún no están listos.')
    if kind not in ('zip', 'csv'):
        raise HTTPException(422, 'Selecciona ZIP o CSV.')
    return FileResponse(folder(ident) / ('result.zip' if kind == 'zip' else 'auditoria.csv'),
                        filename=f'ORGANIZADOR_{run.options["rfc"]}_{run.options["year"]}.{kind}',
                        media_type='application/zip' if kind == 'zip' else 'text/csv; charset=utf-8')
