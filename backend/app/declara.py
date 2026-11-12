"""Adaptador web de Declara: planes revisables y copias, sin sesión SAT remota."""
import csv
import json
import shutil
import stat
import zipfile
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .database import DATA, SessionLocal, session
from .models import Audit, Company, DeclaraRun
from .organizador import safe_path
from . import declara_engine as motor

router = APIRouter(prefix='/api/declara', tags=['Declara'])
MAX_UPLOAD = 100 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
MAX_FILES = 5000
ELIGIBLE = {'RENOMBRAR', 'CORRECTO'}
CHOICES = {'DECLARACION NORMAL', 'DECLARACION COMPLEMENTARIA', 'ACUSE NORMAL', 'ACUSE COMPLEMENTARIA'}


def folder(ident):
    return DATA / 'declara' / ident


def get_run(db, ident):
    run = db.get(DeclaraRun, ident)
    if not run:
        raise HTTPException(404, 'Análisis de Declara no encontrado')
    return run


def save_plan(ident, infos):
    root = folder(ident) / 'input'
    records = [{**asdict(i), 'path': i.path.relative_to(root).as_posix()} for i in infos]
    temporary = folder(ident) / 'plan_pending.json'
    temporary.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    temporary.replace(folder(ident) / 'plan.json')


def load_plan(ident):
    records = json.loads((folder(ident) / 'plan.json').read_text(encoding='utf-8'))
    return [motor.PdfInfo(**{**r, 'path': folder(ident) / 'input' / r['path']}) for r in records]


def summary(infos, expected_rfc):
    candidates = [i.rfc for i in infos if i.rfc and i.status not in {'ERROR', 'OMITIDO', 'RFC DIFERENTE'}]
    primary = Counter(candidates).most_common(1)[0][0] if candidates else None
    return {'total': len(infos), 'rename': sum(i.status == 'RENOMBRAR' for i in infos),
            'correct': sum(i.status == 'CORRECTO' for i in infos),
            'excluded': sum(i.status not in ELIGIBLE for i in infos),
            'special': sum(i.is_resico or i.is_salarios for i in infos),
            'primary_rfc': primary, 'rfc_matches': primary == expected_rfc if primary else True}


def control_months(infos, expected_rfc):
    stats = summary(infos, expected_rfc)
    if not stats['rfc_matches']:
        return {}
    return motor.compute_month_completeness(infos, expected_rfc)


def refresh_run(run, infos):
    run.summary = {**(run.summary or {}), **summary(infos, run.expected_rfc)}
    run.months = control_months(infos, run.expected_rfc)
    run.evaluated_on = date.today().isoformat()


def progress(ident, status, message):
    with SessionLocal() as db:
        db.execute(update(DeclaraRun).where(DeclaraRun.id == ident).values(status=status, message=message[:1000]))
        db.commit()


def extract_zip(archive, target):
    count = size = ignored = 0
    seen = set()
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > MAX_FILES * 2:
            raise ValueError('El ZIP tiene demasiadas entradas.')
        for item in z.infolist():
            path = safe_path(item.filename.rstrip('/') if item.is_dir() else item.filename)
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('No se admiten enlaces en el ZIP.')
            if item.is_dir():
                continue
            if path.suffix.lower() != '.pdf':
                ignored += 1
                continue
            if item.flag_bits & 1:
                raise ValueError('El ZIP está protegido con contraseña.')
            count += 1
            size += item.file_size
            if count > MAX_FILES or size > MAX_EXPANDED:
                raise ValueError('Máximo 5,000 PDF o 500 MB descomprimidos.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError('El ZIP contiene rutas de PDF repetidas.')
            seen.add(key)
            dest = target / str(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as src, dest.open('xb') as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
    if not count:
        raise ValueError('No se encontraron PDF en el ZIP.')
    return ignored


def base_folder(root):
    if any(p.is_file() and p.suffix.lower() == '.pdf' for p in root.iterdir()):
        return root
    children = list(root.iterdir())
    if len(children) == 1 and children[0].is_dir():
        child = children[0]
        if any(p.is_file() and p.suffix.lower() == '.pdf' for p in child.iterdir()):
            return child
    raise ValueError('Selecciona los PDF de una empresa y ejercicio, directamente en la carpeta base. No se combinan subcarpetas.')


def analyze(ident):
    try:
        root = folder(ident)
        ignored = extract_zip(root / 'input.zip', root / 'input') if (root / 'input.zip').exists() else 0
        base = base_folder(root / 'input')
        with SessionLocal() as db:
            short_name = get_run(db, ident).short_name
        infos = motor.analyze_folder(base, short_name)
        for i in infos:
            i.sha256 = motor.sha256_file(i.path)
        save_plan(ident, infos)
        nested = sum(p.is_file() and p.suffix.lower() == '.pdf' and p.parent != base for p in (root / 'input').rglob('*'))
        with SessionLocal() as db:
            run = get_run(db, ident)
            refresh_run(run, infos)
            warnings = []
            if ignored:
                warnings.append(f'Se omitieron {ignored} archivos que no son PDF.')
            if nested:
                warnings.append(f'{nested} PDF de subcarpetas no se analizaron; el motor sólo procesa archivos directos.')
            if len({i.year for i in infos if i.year}) > 1:
                warnings.append('Hay documentos de varios ejercicios. Revisa los nombres: el motor original no agrega el año al nombre final.')
            if not run.summary['rfc_matches']:
                warnings.append('El RFC principal detectado no coincide con la empresa seleccionada. No se publicará control mensual ni se generarán copias; selecciona la empresa correcta en una nueva carga.')
            if any(i.status not in ELIGIBLE for i in infos):
                warnings.append('Los PDF omitidos, con error o con RFC diferente no se incluyen en el ZIP. Sus originales se conservan.')
            if any(i.preserve_special_name for i in infos):
                warnings.append('Algunos RESICO/SALARIOS conservan su nombre por metadatos incompletos. Los archivos sin ejercicio no completan el control mensual.')
            run.warnings = warnings
            run.status = 'analyzed'
            run.message = 'Análisis terminado. Revisa los nombres y el control documental.'
            db.add(Audit(company_id=run.company_id, action='Declara: análisis terminado'))
            db.commit()
    except Exception as exc:
        progress(ident, 'error', 'No se pudo analizar: ' + str(exc))


@router.post('/runs', status_code=202)
async def start(background: BackgroundTasks, company_id: str = Form(...), short_name: str = Form(...),
                files: list[UploadFile] = File(...), db: Session = Depends(session)):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    short_name = motor.sanitize_company_name(short_name)
    if not short_name or len(short_name) > 80:
        raise HTTPException(422, 'Escribe un nombre corto de empresa de hasta 80 caracteres.')
    if not files or len(files) > 1000:
        raise HTTPException(422, 'Selecciona hasta 1,000 PDF o un ZIP con hasta 5,000.')
    ident = str(uuid4())
    root = folder(ident)
    (root / 'input').mkdir(parents=True)
    size = 0
    seen = set()
    try:
        is_zip = len(files) == 1 and Path(files[0].filename or '').suffix.lower() == '.zip'
        for file in files:
            path = safe_path(file.filename or '')
            if not is_zip and path.suffix.lower() != '.pdf':
                raise ValueError('Selecciona PDF, una carpeta de PDF o un único ZIP.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError('Hay PDF con la misma ruta.')
            seen.add(key)
            dest = root / 'input.zip' if is_zip else root / 'input' / str(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, 'Máximo 100 MB de carga por análisis.')
                    out.write(chunk)
        if not size:
            raise ValueError('La entrada está vacía.')
        run = DeclaraRun(id=ident, company_id=company.id, expected_rfc=company.rfc, short_name=short_name,
                         name=path.name[:255] if is_zip else f'{len(files)} PDF', message='Preparando PDF.')
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
def runs(company_id: str = '', db: Session = Depends(session)):
    query = select(DeclaraRun)
    if company_id:
        query = query.where(DeclaraRun.company_id == company_id)
    return db.scalars(query.order_by(DeclaraRun.created_at.desc()).limit(50)).all()


@router.get('/runs/{ident}')
def detail(ident: str, db: Session = Depends(session)):
    run = get_run(db, ident)
    records = []
    if (folder(ident) / 'plan.json').exists():
        infos = load_plan(ident)
        # Recalcular la exigibilidad a la fecha actual sin cambiar el plan.
        if run.status in {'analyzed', 'generated'} and run.evaluated_on != date.today().isoformat():
            refresh_run(run, infos)
            db.commit()
        records = [{**asdict(i), 'path': i.path.relative_to(folder(ident) / 'input').as_posix(), 'index': n} for n, i in enumerate(infos)]
    return {'run': run, 'records': records}


class RevisionIn(BaseModel):
    revision: int = PydanticField(ge=0)


class ResolveIn(RevisionIn):
    index: int = PydanticField(ge=0)
    action: str
    choice: str = ''


@router.post('/runs/{ident}/resolve')
def resolve(ident: str, data: ResolveIn, db: Session = Depends(session)):
    run = get_run(db, ident)
    changed = db.execute(update(DeclaraRun).where(DeclaraRun.id == ident, DeclaraRun.status == 'analyzed', DeclaraRun.revision == data.revision)
                         .values(status='editing'))
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'El análisis cambió o está en curso. Actualiza antes de resolver.')
    try:
        infos = load_plan(ident)
        if data.index >= len(infos):
            raise ValueError('Archivo no encontrado.')
        info = infos[data.index]
        if info.status in {'CORRECTO', 'RFC DIFERENTE'} or (info.rfc and info.rfc != run.expected_rfc):
            raise ValueError('Este archivo ya es correcto o pertenece a otro RFC.')
        if data.action == 'duplicate':
            name = motor.next_duplicate_name(info, infos)
        elif data.action == 'type' and data.choice in CHOICES:
            name = motor.manual_name_for_type(info, data.choice, infos, run.short_name)
        else:
            raise ValueError('Selecciona una resolución válida.')
        if not name:
            raise ValueError('No se puede calcular el nombre: revisa si el mes está identificado.')
        if len(name) > 255 or safe_path(name).name != name:
            raise ValueError('El nombre propuesto no es válido para Windows.')
        info.expected_name = name
        info.status = 'RENOMBRAR'
        info.manual_override = True
        info.detail = 'Resuelto manualmente como duplicado/consecutivo.' if data.action == 'duplicate' else f'Tipo de documento seleccionado manualmente: {data.choice}.'
        if data.action == 'type':
            others = {i.expected_name.casefold() for i in infos if i is not info and i.expected_name and i.status in ELIGIBLE}
            if name.casefold() in others or (info.expected_path.exists() and info.expected_path.resolve() != info.path.resolve()):
                alt = motor.next_duplicate_name(info, infos)
                if not alt:
                    raise ValueError('No se encontró un nombre libre.')
                info.expected_name = alt
                info.detail += ' Se agregó consecutivo porque el nombre ya estaba ocupado.'
        save_plan(ident, infos)
        db.refresh(run)
        refresh_run(run, infos)
        run.status = 'analyzed'
        run.revision += 1
        db.add(Audit(company_id=run.company_id, action='Declara: resolución manual del plan'))
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(update(DeclaraRun).where(DeclaraRun.id == ident, DeclaraRun.status == 'editing').values(status='analyzed'))
        db.commit()
        if isinstance(exc, ValueError):
            raise HTTPException(422, str(exc)) from exc
        raise
    return detail(ident, db)


def generate(ident):
    try:
        root = folder(ident)
        infos = load_plan(ident)
        work = root / 'work'
        work.mkdir()
        planned = []
        # Copiar todos los PDF de la carpeta conserva la detección original de colisiones.
        for i in infos:
            if motor.sha256_file(i.path) != i.sha256:
                raise ValueError('Un PDF cambió después del análisis. Carga nuevamente la entrada.')
            dest = work / i.path.name
            shutil.copy2(i.path, dest)
            if motor.sha256_file(dest) != i.sha256:
                raise ValueError('Falló la verificación de una copia.')
            planned.append(motor.PdfInfo(**{**asdict(i), 'path': dest}))
        eligible = [(original, copied) for original, copied in zip(infos, planned) if original.status in ELIGIBLE]
        for original, copied in eligible:
            name = copied.expected_name
            if not name or len(name) > 255 or safe_path(name).name != name:
                raise ValueError('Hay un nombre de destino no válido. Revisa el archivo o acorta el nombre de empresa.')
        renamed, errors = motor.execute_renames(planned)
        if errors:
            raise ValueError('; '.join(errors))
        rows = []
        with zipfile.ZipFile(root / 'result_pending.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for original, copied in eligible:
                final = copied.expected_path if copied.status == 'RENOMBRAR' else copied.path
                if motor.sha256_file(final) != original.sha256 or motor.sha256_file(original.path) != original.sha256:
                    raise ValueError('El contenido cambió durante el proceso.')
                z.write(final, final.name)
            for i in infos:
                rows.append({'archivo': i.path.name, 'nombre_final': i.expected_name or '', 'estado': 'RENOMBRADO' if i.status == 'RENOMBRAR' else i.status,
                             'rfc': i.rfc or '', 'ejercicio': i.year or '', 'mes': i.month or '', 'tipo': i.declaration_type or '',
                             'detalle': i.detail, 'manual': i.manual_override, 'sha256': i.sha256})
        (root / 'result_pending.zip').replace(root / 'result.zip')
        with (root / 'auditoria.csv').open('w', encoding='utf-8-sig', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: "'" + str(v) if str(v).startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()})
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.status = 'generated'
            run.message = 'Copias renombradas y verificadas. Los originales se conservan.'
            run.summary = {**run.summary, 'renamed': renamed, 'output': len(eligible)}
            db.add(Audit(company_id=run.company_id, action='Declara: copias renombradas generadas'))
            db.commit()
    except Exception as exc:
        progress(ident, 'error', 'No se pudo generar: ' + str(exc) + ' Repite la carga para intentarlo de nuevo.')


@router.post('/runs/{ident}/generate', status_code=202)
def start_generate(ident: str, data: RevisionIn, background: BackgroundTasks, db: Session = Depends(session)):
    run = get_run(db, ident)
    if not run.summary.get('rfc_matches'):
        raise HTTPException(422, 'El RFC detectado no coincide con la empresa seleccionada.')
    if not (run.summary.get('rename', 0) + run.summary.get('correct', 0)):
        raise HTTPException(422, 'No hay PDF reconocidos para generar.')
    changed = db.execute(update(DeclaraRun).where(DeclaraRun.id == ident, DeclaraRun.status == 'analyzed', DeclaraRun.revision == data.revision)
                         .values(status='generating', message='Preparando copias y aplicando nombres.'))
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'El análisis cambió o ya fue ejecutado. Actualiza para revisar.')
    background.add_task(generate, ident)
    return {'status': 'generating'}


@router.get('/runs/{ident}/file/{index}')
def preview(ident: str, index: int, db: Session = Depends(session)):
    get_run(db, ident)
    if not (folder(ident) / 'plan.json').exists():
        raise HTTPException(409, 'Primero termina el análisis.')
    infos = load_plan(ident)
    if index < 0 or index >= len(infos):
        raise HTTPException(404, 'PDF no encontrado')
    return FileResponse(infos[index].path, media_type='application/pdf', content_disposition_type='inline')


@router.get('/runs/{ident}/download')
def download(ident: str, kind: str = 'zip', db: Session = Depends(session)):
    run = get_run(db, ident)
    if run.status != 'generated':
        raise HTTPException(409, 'Los resultados aún no están listos.')
    if kind not in {'zip', 'csv'}:
        raise HTTPException(422, 'Selecciona ZIP o CSV.')
    return FileResponse(folder(ident) / ('result.zip' if kind == 'zip' else 'auditoria.csv'),
                        filename=f'DECLARA_{run.expected_rfc}.{kind}', media_type='application/zip' if kind == 'zip' else 'text/csv; charset=utf-8')
