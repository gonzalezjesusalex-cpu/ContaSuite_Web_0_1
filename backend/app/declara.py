"""Adaptador web de Declara: planes revisables y copias, ejercicio, control mensual, cambios manuales y bitácora."""

import csv
import io
import json
import logging
import re
import shutil
import stat
import zipfile
from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .database import DATA, SessionLocal, session
from .models import Audit, Company, DeclaraCompanySettings, DeclaraLog, DeclaraRun, Setting
from .organizador import safe_path
from . import declara_engine as motor
from . import declara_rules as rules
from .run_access import DECLARA
from .security import Principal, admin_auth, auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/declara', tags=['Declara'])
MAX_UPLOAD = 100 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
MAX_FILES = 5000
ELIGIBLE = {'RENOMBRAR', 'CORRECTO'}
CHOICES = set(rules.CHOICES)
MODES = {'subir', 'carpeta'}
ACTIONS = {'duplicate', 'type', 'manual', 'exclude', 'include', 'undo'}
TEMPLATE_VARIABLES = ('{NOMBRE_CORTO}', '{RFC}', '{RAZON_SOCIAL}', '{EJERCICIO}')
# Configuración › Declara: clave en `settings` y valor por defecto.
SETTINGS = {
    'template': ('declara_template', ''),
    'due_day': ('declara_due_day', str(rules.DUE_DAY)),
    'poll_seconds': ('declara_poll_seconds', '60'),
    'backup': ('declara_backup', '1'),
}


def folder(ident):
    return DATA / 'declara' / ident


def get_run(db, ident):
    run = db.get(DeclaraRun, ident)
    if not run:
        raise HTTPException(404, 'Análisis de Declara no encontrado')
    return run


def records_of(ident, infos):
    root = folder(ident) / 'input'
    return [{**asdict(i), 'path': i.path.relative_to(root).as_posix()} for i in infos]


def from_record(ident, record):
    return motor.PdfInfo(**{**record, 'path': folder(ident) / 'input' / record['path']})


def write_json(path, data):
    temporary = path.with_name(path.name + '.pending')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_plan(ident, infos):
    write_json(folder(ident) / 'plan.json', records_of(ident, infos))


def load_plan(ident):
    return [from_record(ident, r) for r in read_json(folder(ident) / 'plan.json', [])]


# ---------------------------------------------------------------- ajustes y bitácora


def declara_settings(db):
    values = {}
    for name, (key, default) in SETTINGS.items():
        row = db.get(Setting, key)
        values[name] = row.value if row else default
    return {
        'template': values['template'],
        'due_day': int(values['due_day']),
        'poll_seconds': int(values['poll_seconds']),
        'backup': values['backup'] == '1',
    }


def log(db, action, *, user_id=None, user_name=None, company_id=None, year=None, run_id=None, detail=None, path=None,
        machine=None):  # fmt: skip
    db.add(
        DeclaraLog(
            action=action,
            user_id=user_id,
            user_name=user_name,
            machine=machine,
            company_id=company_id,
            year=year,
            run_id=run_id,
            detail=detail,
            path=path,
        )
    )


def run_year(run, infos=()):
    """Ejercicio del análisis. Los análisis anteriores al rediseño usan el ejercicio más frecuente de sus PDF."""
    if run.year:
        return run.year
    years = Counter(int(i.year) for i in infos if str(i.year or '').isdigit())
    return years.most_common(1)[0][0] if years else date.today().year


# ---------------------------------------------------------------- resumen y control mensual


def summary(infos, expected_rfc, year=None):
    detected = [i.rfc for i in infos if i.rfc and i.status not in {'ERROR', 'OMITIDO'}]
    primary = Counter(detected).most_common(1)[0][0] if detected else None
    return {
        'total': len(infos),
        'rename': sum(i.status == 'RENOMBRAR' for i in infos),
        'correct': sum(i.status == 'CORRECTO' for i in infos),
        'identical': sum(i.status == rules.COPIA for i in infos),
        'omitted': sum(i.status in {'ERROR', 'OMITIDO'} for i in infos),
        'rfc_other': sum(i.status == 'RFC DIFERENTE' for i in infos),
        'excluded_manual': sum(i.status == rules.EXCLUIDO for i in infos),
        'manual': sum(bool(i.manual_override) and i.status in ELIGIBLE for i in infos),
        'excluded': sum(i.status not in ELIGIBLE for i in infos),
        'special': sum(i.is_resico or i.is_salarios for i in infos),
        'other_year': sum(bool(year) and str(i.year or '').isdigit() and int(i.year) != year for i in infos),
        'primary_rfc': primary,
        'rfc_matches': primary == expected_rfc if primary else True,
    }


def month_view(state):
    """Estado del mes con las claves anteriores (`aplicable`, `razon_no_aplica`) para quien aún las lee."""
    reason = {rules.NO_APLICA_ALTA: 'ALTA', rules.EN_CURSO: 'NO_EXIGIBLE', rules.FUTURO: 'NO_EXIGIBLE'}.get(
        state['estado']
    )
    return {**state, 'aplicable': reason is None, 'razon_no_aplica': reason}


def refresh_run(db, run, infos):
    year = run_year(run, infos)
    settings = declara_settings(db)
    company = db.get(Company, run.company_id)
    start, origin = rules.company_start_date(company.operations_start if company else None, run.expected_rfc, year)
    stats = summary(infos, run.expected_rfc, year)
    stats.update(
        year=year,
        due_day=settings['due_day'],
        alta={'fecha': start.isoformat() if start else None, 'origen': origin},
    )
    run.summary = {**(run.summary or {}), **stats}
    if stats['rfc_matches']:
        months = rules.compute_month_status(infos, year, start, date.today(), settings['due_day'])
        run.months = {str(year): {m: month_view(s) for m, s in months.items()}}
    else:
        run.months = {}
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
    raise ValueError(
        'Selecciona los PDF de una empresa y ejercicio, directamente en la carpeta base. No se combinan subcarpetas.'
    )


def analyze(ident):
    try:
        root = folder(ident)
        ignored = extract_zip(root / 'input.zip', root / 'input') if (root / 'input.zip').exists() else 0
        base = base_folder(root / 'input')
        with SessionLocal() as db:
            run = get_run(db, ident)
            short_name, expected_rfc = run.short_name, run.expected_rfc
        infos = motor.analyze_folder(base, short_name, expected_rfc)
        for i in infos:
            if not i.sha256:
                i.sha256 = motor.sha256_file(i.path)
        save_plan(ident, infos)
        write_json(root / 'plan_original.json', records_of(ident, infos))
        nested = sum(
            p.is_file() and p.suffix.lower() == '.pdf' and p.parent != base for p in (root / 'input').rglob('*')
        )
        with SessionLocal() as db:
            run = get_run(db, ident)
            refresh_run(db, run, infos)
            warnings = []
            if ignored:
                warnings.append(f'Se omitieron {ignored} archivos que no son PDF.')
            if nested:
                warnings.append(
                    f'{nested} PDF de subcarpetas no se analizaron; el motor sólo procesa archivos directos.'
                )
            if run.summary.get('other_year'):
                warnings.append(
                    f'{run.summary["other_year"]} PDF son de un ejercicio distinto a {run.summary["year"]}. '
                    'El motor original no agrega el año al nombre final.'
                )
            if not run.summary['rfc_matches']:
                warnings.append(
                    'El RFC principal detectado no coincide con la empresa seleccionada. No se publicará control mensual ni se generarán copias; selecciona la empresa correcta en una nueva carga.'
                )
            if any(i.status not in ELIGIBLE for i in infos):
                warnings.append(
                    'Los PDF omitidos, con error, con RFC diferente o copias idénticas no se incluyen en el ZIP. Sus originales se conservan.'
                )
            if any(i.preserve_special_name for i in infos):
                warnings.append(
                    'Algunos RESICO/SALARIOS conservan su nombre por metadatos incompletos. Los archivos sin ejercicio no completan el control mensual.'
                )
            run.warnings = warnings
            run.status = 'analyzed'
            run.message = 'Análisis terminado. Revisa los nombres y el control documental.'
            db.add(Audit(company_id=run.company_id, actor_id=run.created_by, action='Declara: análisis terminado'))
            s = run.summary
            log(
                db,
                'analisis',
                user_id=run.created_by,
                company_id=run.company_id,
                year=s['year'],
                run_id=run.id,
                path=run.folder_path,
                detail={
                    'modo': run.mode or 'subir',
                    'pdf': s['total'],
                    'por_renombrar': s['rename'],
                    'correctos': s['correct'],
                    'copias_identicas': s['identical'],
                    'omitidos': s['omitted'],
                },
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - background job: logged and reported on the run
        logger.exception('Declara: falló el análisis %s', ident)
        progress(ident, 'error', 'No se pudo analizar: ' + str(exc))


def checked_year(year):
    current = date.today().year
    if year is None:
        return current
    if not 2000 <= year <= current + 1:
        raise HTTPException(422, f'El ejercicio debe estar entre 2000 y {current + 1}.')
    return year


def remember_short_name(db, company_id, short_name, principal, mode=None):
    row = db.get(DeclaraCompanySettings, company_id) or DeclaraCompanySettings(company_id=company_id)
    row.short_name = short_name
    if mode:
        row.mode = mode
    row.updated_by = principal.subject
    db.merge(row)


@router.post('/runs', status_code=202)
async def start(
    background: BackgroundTasks,
    company_id: str = Form(...),
    short_name: str = Form(...),
    year: int | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    DECLARA.require_company(principal, company_id)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    short_name = motor.sanitize_company_name(short_name)
    if not short_name or len(short_name) > 80:
        raise HTTPException(422, 'Escribe un nombre corto de empresa de hasta 80 caracteres.')
    year = checked_year(year)
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
        run = DeclaraRun(
            id=ident,
            created_by=principal.subject,
            company_id=company.id,
            expected_rfc=company.rfc,
            short_name=short_name,
            name=path.name[:255] if is_zip else f'{len(files)} PDF',
            message='Preparando PDF.',
            year=year,
            mode='subir',
        )
        db.add(run)
        remember_short_name(db, company.id, short_name, principal)
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


class FromSatIn(BaseModel):
    job_id: str = PydanticField(min_length=1, max_length=36)
    short_name: str = PydanticField(min_length=1, max_length=80)
    year: int | None = None


@router.post('/runs/from-sat', status_code=202)
def start_from_sat(
    data: FromSatIn,
    background: BackgroundTasks,
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    """Analysis of the PDFs a finished SAT download delivered. Same pipeline as an upload; created once per download."""
    from .models import Job
    from .sat_declaraciones import KIND, staging

    job = db.get(Job, data.job_id)
    if (
        not job
        or job.kind != KIND
        or job.status != 'completed'
        or not (principal.admin or job.requested_by == principal.subject)
    ):
        raise HTTPException(404, 'Descarga no encontrada')
    DECLARA.require_company(principal, job.company_id)
    existing = (job.result or {}).get('analisis_id')
    if existing and (run := db.get(DeclaraRun, existing)):
        return run
    company = db.get(Company, job.company_id)
    short_name = motor.sanitize_company_name(data.short_name)
    if not company or not short_name:
        raise HTTPException(422, 'Escribe un nombre corto de empresa de hasta 80 caracteres.')
    payload_year = (job.payload or {}).get('ejercicio')
    year = checked_year(data.year or (int(payload_year) if str(payload_year or '').isdigit() else None))
    received = staging(job.id)
    ident = str(uuid4())
    root = folder(ident)
    (root / 'input').mkdir(parents=True)
    count = 0
    try:
        for item in (job.result or {}).get('archivos', []):
            source = received / (str(item.get('sha256', '')) + '.pdf')
            if not source.is_file():
                continue
            try:
                name = safe_path(Path(str(item.get('nombre') or '').replace('\\', '/')).name).name
            except ValueError:
                name = 'declaracion.pdf'  # the agent's name is never trusted: any odd one gets a plain name
            if Path(name).suffix.lower() != '.pdf':
                name += '.pdf'
            target = root / 'input' / name
            n = 2
            while target.exists():
                target = root / 'input' / f'{Path(name).stem} ({n}).pdf'
                n += 1
            shutil.copyfile(source, target)
            count += 1
        if not count:
            raise ValueError('La descarga no entregó PDF para analizar.')
        run = DeclaraRun(
            id=ident,
            created_by=principal.subject,
            company_id=company.id,
            expected_rfc=company.rfc,
            short_name=short_name,
            name=f'SAT · {count} PDF',
            message='Preparando PDF.',
            year=year,
            mode='subir',
        )
        db.add(run)
        job.result = {**(job.result or {}), 'analisis_id': ident}
        db.commit()
    except ValueError as exc:
        db.rollback()
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        shutil.rmtree(root, ignore_errors=True)
        raise
    shutil.rmtree(received, ignore_errors=True)  # the analysis keeps its own copy
    background.add_task(analyze, ident)
    return run


@router.get('/runs')
def runs(
    company_id: str = '',
    year: int | None = None,
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    query = select(DeclaraRun).where(DECLARA.scope(principal, DeclaraRun))
    if company_id:
        query = query.where(DeclaraRun.company_id == company_id)
    if year:
        query = query.where(DeclaraRun.year == year)
    return db.scalars(query.order_by(DeclaraRun.created_at.desc()).limit(50)).all()


def can_undo(ident):
    """«Deshacer cambio manual» necesita el plan original, que sólo guardan los análisis desde el rediseño."""
    return (folder(ident) / 'plan_original.json').exists()


@router.get('/runs/{ident}')
def detail(ident: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = DECLARA.check(principal, get_run(db, ident))
    records = []
    if (folder(ident) / 'plan.json').exists():
        infos = load_plan(ident)
        # Recalcular la exigibilidad a la fecha actual (o con el nuevo día límite) sin cambiar el plan.
        if run.status in {'analyzed', 'generated'} and (
            run.evaluated_on != date.today().isoformat()
            or (run.summary or {}).get('due_day') != declara_settings(db)['due_day']
        ):
            refresh_run(db, run, infos)
            db.commit()
        year = run_year(run, infos)
        undo = can_undo(ident)
        records = [
            {
                **asdict(i),
                'path': i.path.relative_to(folder(ident) / 'input').as_posix(),
                'index': n,
                'other_year': str(i.year or '').isdigit() and int(i.year) != year,
                'can_undo': undo and (bool(i.manual_override) or i.status == rules.EXCLUIDO),
            }
            for n, i in enumerate(infos)
        ]
    return {'run': run, 'records': records}


# ---------------------------------------------------------------- cambios del plan (panel «Resolver archivo»)


class RevisionIn(BaseModel):
    revision: int = PydanticField(ge=0)


class ChangeIn(BaseModel):
    index: int = PydanticField(ge=0)
    action: str
    choice: str = ''
    month: str = PydanticField(default='', max_length=20)
    name: str = PydanticField(default='', max_length=300)
    count: bool = True


class ResolveIn(RevisionIn, ChangeIn):
    pass


def free_name(info, infos, name):
    """`name`, o el siguiente consecutivo si otro destino del plan o un archivo ajeno al plan ya lo ocupa."""
    info.expected_name = name
    others = {i.expected_name.casefold() for i in infos if i is not info and i.expected_name and i.status in ELIGIBLE}
    if name.casefold() in others or (
        info.expected_path.exists() and info.expected_path.resolve() != info.path.resolve()
    ):
        alt = motor.next_duplicate_name(info, infos)
        if not alt:
            raise ValueError('No se encontró un nombre libre.')
        info.expected_name = alt
        return True
    return False


def change_plan(ident, run, infos, data, principal):
    """Aplica un cambio del panel sobre `infos` (en memoria). Devuelve lo que la interfaz muestra en vivo."""
    if data.action not in ACTIONS:
        raise ValueError('Selecciona una resolución válida.')
    if data.index >= len(infos):
        raise ValueError('Archivo no encontrado.')
    info = infos[data.index]
    year = run_year(run, infos)
    root = folder(ident)
    excluded = read_json(root / 'excluded.json', {})
    result = {'errors': [], 'warnings': [], 'standard': None}

    if data.action == 'exclude':
        if info.status == rules.EXCLUIDO:
            raise ValueError('El archivo ya está excluido.')
        excluded[str(data.index)] = records_of(ident, [info])[0]
        info.status = rules.EXCLUIDO
        info.detail = f'Excluido del plan por {principal.display_name}.'
        return {**result, 'name': None, 'excluded': excluded}
    if data.action == 'include':
        previous = excluded.pop(str(data.index), None)
        if info.status != rules.EXCLUIDO or previous is None:
            raise ValueError('El archivo no está excluido.')
        restored = from_record(ident, previous)
        infos[data.index] = restored
        if restored.expected_name and restored.status in ELIGIBLE:
            free_name(restored, infos, restored.expected_name)
        return {**result, 'name': restored.expected_name, 'excluded': excluded}
    if data.action == 'undo':
        original = read_json(root / 'plan_original.json', None)
        if original is None:
            raise ValueError('Este análisis es anterior al rediseño: vuelve a analizar para deshacer cambios.')
        if not (info.manual_override or info.status == rules.EXCLUIDO):
            raise ValueError('El archivo no tiene cambios manuales.')
        restored = from_record(ident, original[data.index])
        infos[data.index] = restored
        excluded.pop(str(data.index), None)
        if restored.expected_name and restored.status in ELIGIBLE:
            free_name(restored, infos, restored.expected_name)
        return {**result, 'name': restored.expected_name, 'excluded': excluded}

    if info.status == rules.EXCLUIDO:
        raise ValueError('Reincluye el archivo antes de resolverlo.')
    if info.status == 'RFC DIFERENTE' or (info.rfc and info.rfc != run.expected_rfc):
        raise ValueError('Este archivo pertenece a otro RFC.')
    if data.action in {'duplicate', 'type'} and info.status == 'CORRECTO':
        raise ValueError('Este archivo ya tiene el nombre correcto.')

    if data.action == 'manual':
        existing = {p.name for p in info.path.parent.iterdir() if p.is_file()}
        check = rules.validate_manual_name(data.name, info, infos, existing)
        result.update(errors=check['errors'], warnings=check['warnings'], standard=check['standard'])
        if not check['ok']:
            return {**result, 'name': check['name']}
        if data.count:
            if data.choice not in CHOICES or not motor.MONTHS.get(motor.norm(data.month)):
                result['errors'].append('Elige documento, tipo y mes para contarlo en el control mensual.')
                return {**result, 'name': check['name']}
        rules.apply_manual_name(info, check['name'], data.count, data.choice, data.month, str(year))
        return {**result, 'name': check['name']}

    if data.action == 'duplicate':
        if not (info.month and info.document_kind):
            raise ValueError('Para marcarlo como otra copia hace falta conocer el periodo y el tipo.')
        name = motor.next_duplicate_name(info, infos)
        detail_text = 'Resuelto manualmente como duplicado/consecutivo.'
    else:
        if data.choice not in CHOICES:
            raise ValueError('Selecciona una resolución válida.')
        if data.month:
            name = rules.manual_name_for_month(info, data.choice, data.month, infos, run.short_name)
        else:
            name = motor.manual_name_for_type(info, data.choice, infos, run.short_name)
        if name and not info.year:
            info.year = str(year)
        detail_text = f'Tipo de documento seleccionado manualmente: {data.choice}.'
    if not name:
        raise ValueError('No se puede calcular el nombre: revisa si el mes está identificado.')
    if len(name) > 255 or safe_path(name).name != name:
        raise ValueError('El nombre propuesto no es válido para Windows.')
    info.status = 'RENOMBRAR'
    info.manual_override = True
    info.origin = 'manual'
    info.count_in_control = True
    info.detail = detail_text
    if data.action == 'type' and free_name(info, infos, name):
        info.detail += ' Se agregó consecutivo porque el nombre ya estaba ocupado.'
    else:
        info.expected_name = name
    return {**result, 'name': info.expected_name}


def month_effect(db, run, before, after, data):
    """Cómo cambiaría el control del mes elegido: «junio pasaría a Completo»."""
    month = motor.MONTHS.get(motor.norm(data.month or '')) or next(
        (i.month for i in (after[data.index],) if i.month), None
    )
    if not month:
        return None
    year = run_year(run, after)
    company = db.get(Company, run.company_id)
    start, _ = rules.company_start_date(company.operations_start if company else None, run.expected_rfc, year)
    due = declara_settings(db)['due_day']
    old = rules.compute_month_status(before, year, start, date.today(), due)[month]['estado']
    new = rules.compute_month_status(after, year, start, date.today(), due)[month]['estado']
    return {'month': month, 'before': old, 'after': new}


@router.post('/runs/{ident}/preview')
def preview_change(ident: str, data: ChangeIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Lo que haría un cambio del panel, sin guardarlo: nombre final, validaciones y efecto en el mes."""
    run = DECLARA.check(principal, get_run(db, ident))
    if not (folder(ident) / 'plan.json').exists():
        raise HTTPException(409, 'Primero termina el análisis.')
    before = load_plan(ident)
    after = load_plan(ident)
    try:
        result = change_plan(ident, run, after, data, principal)
    except ValueError as exc:
        return {'name': None, 'errors': [str(exc)], 'warnings': [], 'standard': None, 'effect': None}
    result.pop('excluded', None)
    result['effect'] = None if result['errors'] else month_effect(db, run, before, after, data)
    return result


@router.post('/runs/{ident}/resolve')
def resolve(ident: str, data: ResolveIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = DECLARA.check(principal, get_run(db, ident))
    changed = db.execute(
        update(DeclaraRun)
        .where(DeclaraRun.id == ident, DeclaraRun.status == 'analyzed', DeclaraRun.revision == data.revision)
        .values(status='editing')
    )
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'El análisis cambió o está en curso. Actualiza antes de resolver.')
    try:
        infos = load_plan(ident)
        previous = infos[data.index].path.name if data.index < len(infos) else ''
        old_name = infos[data.index].expected_name if data.index < len(infos) else None
        result = change_plan(ident, run, infos, data, principal)
        if result['errors']:
            raise ValueError(' '.join(result['errors']))
        save_plan(ident, infos)
        if 'excluded' in result:
            write_json(folder(ident) / 'excluded.json', result['excluded'])
        db.refresh(run)
        refresh_run(db, run, infos)
        run.status = 'analyzed'
        run.revision += 1
        action = {
            'exclude': 'exclusion',
            'include': 'reinclusion',
            'undo': 'deshacer_cambio_manual',
        }.get(data.action, 'resolucion_manual')
        db.add(
            Audit(company_id=run.company_id, actor_id=principal.subject, action='Declara: resolución manual del plan')
        )
        log(
            db,
            action,
            user_id=principal.subject,
            user_name=principal.display_name,
            company_id=run.company_id,
            year=run_year(run, infos),
            run_id=run.id,
            path=run.folder_path,
            detail={
                'archivo': previous,
                'opcion': data.action,
                'antes': old_name,
                'despues': infos[data.index].expected_name,
                'cuenta': infos[data.index].count_in_control,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(
            update(DeclaraRun).where(DeclaraRun.id == ident, DeclaraRun.status == 'editing').values(status='analyzed')
        )
        db.commit()
        if isinstance(exc, ValueError):
            raise HTTPException(422, str(exc)) from exc
        raise
    return detail(ident, db, principal)


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
        eligible = [
            (original, copied) for original, copied in zip(infos, planned, strict=True) if original.status in ELIGIBLE
        ]
        for _original, copied in eligible:
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
                rows.append(
                    {
                        'archivo': i.path.name,
                        'nombre_final': i.expected_name or '',
                        'estado': 'RENOMBRADO' if i.status == 'RENOMBRAR' else i.status,
                        'rfc': i.rfc or '',
                        'ejercicio': i.year or '',
                        'mes': i.month or '',
                        'tipo': i.declaration_type or '',
                        'detalle': i.detail,
                        'manual': i.manual_override,
                        'cuenta_en_control': i.count_in_control,
                        'sha256': i.sha256,
                    }
                )
        (root / 'result_pending.zip').replace(root / 'result.zip')
        with (root / 'auditoria.csv').open('w', encoding='utf-8-sig', newline='') as out:
            write_csv(out, rows)
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.status = 'generated'
            run.message = 'Copias renombradas y verificadas. Los originales se conservan.'
            run.summary = {**run.summary, 'renamed': renamed, 'output': len(eligible)}
            db.add(
                Audit(
                    company_id=run.company_id, actor_id=run.created_by, action='Declara: copias renombradas generadas'
                )
            )
            log(
                db,
                'copias_generadas',
                user_id=run.created_by,
                company_id=run.company_id,
                year=run_year(run, infos),
                run_id=run.id,
                detail={
                    'copias': len(eligible),
                    'renombradas': renamed,
                    'manuales': sum(bool(i.manual_override) for i, _ in eligible),
                },
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - background job: logged and reported on the run
        logger.exception('Declara: falló la generación %s', ident)
        progress(ident, 'error', 'No se pudo generar: ' + str(exc) + ' Repite la carga para intentarlo de nuevo.')


def safe_cell(value):
    """Celdas de CSV que Excel no interpreta como fórmula."""
    return "'" + str(value) if str(value).startswith(('=', '+', '-', '@', '\t', '\r')) else value


def write_csv(out, rows):
    if not rows:
        return
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: safe_cell(v) for k, v in row.items()})


@router.post('/runs/{ident}/generate', status_code=202)
def start_generate(
    ident: str,
    data: RevisionIn,
    background: BackgroundTasks,
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    run = DECLARA.check(principal, get_run(db, ident))
    if not run.summary.get('rfc_matches'):
        raise HTTPException(422, 'El RFC detectado no coincide con la empresa seleccionada.')
    if not (run.summary.get('rename', 0) + run.summary.get('correct', 0)):
        raise HTTPException(422, 'No hay PDF reconocidos para generar.')
    changed = db.execute(
        update(DeclaraRun)
        .where(DeclaraRun.id == ident, DeclaraRun.status == 'analyzed', DeclaraRun.revision == data.revision)
        .values(status='generating', message='Preparando copias y aplicando nombres.')
    )
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'El análisis cambió o ya fue ejecutado. Actualiza para revisar.')
    background.add_task(generate, ident)
    return {'status': 'generating'}


@router.get('/runs/{ident}/file/{index}')
def preview(ident: str, index: int, db: Session = Depends(session), principal: Principal = Depends(auth)):
    DECLARA.check(principal, get_run(db, ident))
    if not (folder(ident) / 'plan.json').exists():
        raise HTTPException(409, 'Primero termina el análisis.')
    infos = load_plan(ident)
    if index < 0 or index >= len(infos):
        raise HTTPException(404, 'PDF no encontrado')
    return FileResponse(infos[index].path, media_type='application/pdf', content_disposition_type='inline')


@router.get('/runs/{ident}/download')
def download(ident: str, kind: str = 'zip', db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = DECLARA.check(principal, get_run(db, ident))
    if run.status != 'generated':
        raise HTTPException(409, 'Los resultados aún no están listos.')
    if kind not in {'zip', 'csv'}:
        raise HTTPException(422, 'Selecciona ZIP o CSV.')
    return FileResponse(
        folder(ident) / ('result.zip' if kind == 'zip' else 'auditoria.csv'),
        filename=f'DECLARA_{run.expected_rfc}.{kind}',
        media_type='application/zip' if kind == 'zip' else 'text/csv; charset=utf-8',
    )


# ---------------------------------------------------------------- Declara por empresa y Configuración › Declara


class CompanyIn(BaseModel):
    short_name: str = PydanticField(default='', max_length=80)
    mode: str = ''


def company_view(db, company):
    row = db.get(DeclaraCompanySettings, company.id)
    suggested = rules.suggest_short_name(company.name)
    start, origin = rules.company_start_date(company.operations_start, company.rfc)
    return {
        'company_id': company.id,
        'rfc': company.rfc,
        'name': company.name,
        'person_type': company.person_type,
        'short_name': (row.short_name if row and row.short_name else '') or suggested,
        'short_name_saved': bool(row and row.short_name),
        'suggested': suggested,
        'mode': (row.mode if row and row.mode else '') or 'subir',
        'alta': {'fecha': start.isoformat() if start else None, 'origen': origin},
    }


@router.get('/companies/{company_id}')
def company_settings(company_id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    DECLARA.require_company(principal, company_id)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    return company_view(db, company)


@router.put('/companies/{company_id}')
def save_company_settings(
    company_id: str, data: CompanyIn, db: Session = Depends(session), principal: Principal = Depends(auth)
):
    DECLARA.require_company(principal, company_id)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    if data.mode and data.mode not in MODES:
        raise HTTPException(422, 'Modo no válido.')
    short_name = motor.sanitize_company_name(data.short_name) if data.short_name else ''
    if data.short_name and not short_name:
        raise HTTPException(422, 'Escribe un nombre corto de empresa de hasta 80 caracteres.')
    row = db.get(DeclaraCompanySettings, company_id) or DeclaraCompanySettings(company_id=company_id)
    if short_name:
        row.short_name = short_name
    if data.mode:
        row.mode = data.mode
    row.updated_by = principal.subject
    db.merge(row)
    db.commit()
    return company_view(db, company)


class SettingsIn(BaseModel):
    template: str = PydanticField(default='', max_length=200)
    due_day: int = PydanticField(default=rules.DUE_DAY, ge=1, le=28)
    poll_seconds: int = PydanticField(default=60, ge=15, le=3600)
    backup: bool = True


@router.get('/settings')
def get_settings(db: Session = Depends(session), principal: Principal = Depends(auth)):
    return declara_settings(db)


@router.put('/settings')
def put_settings(data: SettingsIn, db: Session = Depends(session), principal: Principal = Depends(admin_auth)):
    template = data.template.strip()
    unknown = [v for v in re.findall(r'\{[^}]*\}', template) if v not in TEMPLATE_VARIABLES]
    if unknown:
        raise HTTPException(422, 'Variables no válidas en la plantilla: ' + ', '.join(unknown))
    values = {'template': template, 'due_day': str(data.due_day), 'poll_seconds': str(data.poll_seconds)}
    values['backup'] = '1' if data.backup else '0'
    for name, value in values.items():
        db.merge(Setting(key=SETTINGS[name][0], value=value))
    db.add(Audit(actor_id=principal.subject, action='Declara: configuración actualizada'))
    db.commit()
    return declara_settings(db)


# ---------------------------------------------------------------- bitácora

LOG_LABELS = {
    'analisis': 'Análisis',
    'resolucion_manual': 'Resolución manual',
    'exclusion': 'Exclusión',
    'reinclusion': 'Reinclusión',
    'deshacer_cambio_manual': 'Deshacer cambio manual',
    'copias_generadas': 'Copias renombradas',
    'sesion_sat': 'Sesión SAT',
    'respaldo': 'Respaldo',
    'renombrado': 'Renombrado aplicado',
    'deshacer': 'Deshacer renombrado',
}


def log_rows(db, principal, company_id, year, run_id):
    DECLARA.require_company(principal, company_id)
    query = select(DeclaraLog).where(DeclaraLog.company_id == company_id)
    if year:
        query = query.where(DeclaraLog.year == year)
    if run_id:
        query = query.where(DeclaraLog.run_id == run_id)
    return db.scalars(query.order_by(DeclaraLog.created_at.desc()).limit(1000)).all()


def log_view(row):
    return {
        'id': row.id,
        'created_at': row.created_at,
        'action': row.action,
        'label': LOG_LABELS.get(row.action, row.action),
        'user': row.user_name or row.user_id or 'Sistema',
        'machine': row.machine or '',
        'year': row.year,
        'run_id': row.run_id,
        'detail': row.detail or {},
        'path': row.path or '',
    }


@router.get('/log')
def get_log(
    company_id: str,
    year: int | None = None,
    run_id: str = '',
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    return [log_view(r) for r in log_rows(db, principal, company_id, year, run_id)]


@router.get('/log.csv')
def export_log(
    company_id: str,
    year: int | None = None,
    run_id: str = '',
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    rows = [
        {
            'fecha': v['created_at'].isoformat() if v['created_at'] else '',
            'accion': v['label'],
            'usuario': v['user'],
            'equipo': v['machine'],
            'ejercicio': v['year'] or '',
            'detalle': json.dumps(v['detail'], ensure_ascii=False),
            'ruta': v['path'],
        }
        for v in map(log_view, log_rows(db, principal, company_id, year, run_id))
    ]
    out = io.StringIO()
    out.write('﻿')
    write_csv(
        out,
        rows or [{'fecha': '', 'accion': '', 'usuario': '', 'equipo': '', 'ejercicio': '', 'detalle': '', 'ruta': ''}],
    )
    return Response(
        out.getvalue(),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="BITACORA_DECLARA_{year or "todos"}.csv"'},
    )
