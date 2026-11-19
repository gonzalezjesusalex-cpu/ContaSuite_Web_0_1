"""Archivos subidos y copias verificadas; el motor de escritorio permanece intacto."""

import json
import logging
import re
import shutil
import stat
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .database import DATA, SessionLocal, session
from .models import Audit, Company, OrganizadorItem, OrganizadorRun, now
from . import organizador_engine as motor
from . import organizador_review as content
from .expediente_save import save_file
from .run_access import CFDI
from .security import Principal, auth

logger = logging.getLogger(__name__)

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
    if (
        not raw
        or len(raw) > 700
        or raw.startswith('/')
        or any(
            not p
            or p in ('.', '..')
            or p.endswith((' ', '.'))
            or re.search(r'[<>:"|?*\x00-\x1f]', p)
            or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I)
            for p in parts
        )
    ):
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
    raise ValueError(
        'La carpeta base debe contener Emitidos, Recibidos o Reportes. Conserva las rutas Tipo/RFC/AAAA-MM/archivo.'
    )


def progress(ident, status, message):
    with SessionLocal() as db:
        db.execute(
            update(OrganizadorRun).where(OrganizadorRun.id == ident).values(status=status, message=message[:1000])
        )
        db.commit()


def load_plan(ident):
    data = json.loads((folder(ident) / 'plan.json').read_text(encoding='utf-8'))
    return motor.Plan(motor.Options(**data['options']), [motor.Item(**i) for i in data['items']])


def public_records(plan, records):
    source = Path(plan.options.source)
    target = Path(plan.options.destination)
    return [
        {
            **r,
            'source': Path(r['source']).relative_to(source).as_posix(),
            'destination': Path(r['destination']).relative_to(target).as_posix() if r['destination'] else '',
        }
        for r in records
    ]


def analyze(ident):
    try:
        root = folder(ident)
        ignored = extract_zip(root / 'input.zip', root / 'input') if (root / 'input.zip').exists() else 0
        source = source_root(root / 'input')
        with SessionLocal() as db:
            options = get_run(db, ident).options
        plan = motor.analyze(
            motor.Options(source=str(source), destination=str(root / 'output'), operation='copy', **options),
            lambda n, total, m: progress(ident, 'analyzing', m),
        )
        (root / 'plan.json').write_text(json.dumps(asdict(plan), ensure_ascii=False), encoding='utf-8')
        used = {Path(i.source).resolve() for i in plan.items if i.state == 'Listo'}
        unselected = sum(p.is_file() and p.resolve() not in used for p in source.rglob('*'))
        warnings = []
        if ignored:
            warnings.append(f'Se omitieron {ignored} archivos de formatos no admitidos.')
        if unselected:
            warnings.append(
                f'{unselected} archivos no coinciden con las rutas o filtros elegidos; no se organizarán. Las subcarpetas no se recorren.'
            )
        if not plan.ready:
            warnings.append(
                'No hay archivos listos. Revisa RFC, ejercicio, meses y estructura de origen. Se pueden generar las carpetas vacías del periodo.'
            )
        rows = content.review(plan)
        omitted = content.omitted_files(plan)
        foreign = content.foreign_rfc_folders(source, plan.options.rfc)
        (root / 'review.json').write_text(
            json.dumps({'rows': rows, 'omitted': omitted, 'foreign_rfcs': foreign}, ensure_ascii=False),
            encoding='utf-8',
        )
        with SessionLocal() as db:
            company_id = get_run(db, ident).company_id
            company = db.get(Company, company_id) if company_id else None
        if company and company.rfc != plan.options.rfc:
            warnings.append(
                'El RFC capturado no es el de la empresa elegida: no se podrá guardar en su expediente con ese RFC.'
            )
        if foreign:
            warnings.append('La entrada trae carpetas de otro RFC (' + ', '.join(foreign) + '); no se organizan.')
        blocked = sum(bool(r['incoherence']) for r in rows.values())
        if blocked:
            warnings.append(
                f'{blocked} archivos tienen una incoherencia con su carpeta (RFC o fecha); no se guardarán en el expediente sin revisión.'
            )
        summary = {
            'incoherent': blocked,
            'unpaired': sum(r['pair'] != 'identificada' for r in rows.values()),
            'omitted_files': len(omitted),
            'ready': len(plan.ready),
            'omitted': sum(i.state == 'Omitido' for i in plan.items),
            'unselected': unselected,
            'copied': 0,
            'duplicates': 0,
            'errors': 0,
        }
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.status = 'analyzed'
            run.message = 'Análisis terminado. Revisa las rutas antes de organizar.'
            run.summary = summary
            run.warnings = warnings
            db.add(
                Audit(company_id=run.company_id, actor_id=run.created_by, action='Organizador CFDI: análisis terminado')
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - background job: logged and reported on the run
        logger.exception('Organizador CFDI: falló el análisis %s', ident)
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
            run.summary = {
                **run.summary,
                'copied': sum(r['state'] == 'Copiado' for r in records),
                'duplicates': sum(r['state'] == 'Duplicado' for r in records),
                'errors': result.errors,
            }
            run.status = 'generated'
            run.message = (
                'Organización terminada.'
                if not result.errors
                else 'Organización terminada con errores. Revisa la auditoría.'
            )
            db.add(
                Audit(
                    company_id=run.company_id,
                    actor_id=run.created_by,
                    action='Organizador CFDI: copias verificadas generadas',
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - background job: logged and reported on the run
        logger.exception('Organizador CFDI: falló la generación %s', ident)
        progress(
            ident,
            'error',
            'No se pudo organizar: ' + str(exc) + '. Carga nuevamente la entrada para repetir el proceso.',
        )


@router.post('/runs', status_code=202)
async def start(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    rfc: str = Form(...),
    year: int = Form(...),
    months: str = Form(...),
    kinds: str = Form(''),
    extensions: str = Form(''),
    reports: bool = Form(True),
    company_id: str = Form(''),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    CFDI.require_company(principal, company_id)
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
        options = dict(
            rfc=rfc.strip().upper(),
            year=year,
            months=sorted(set(int(m) for m in months.split(',') if m)),
            kinds=list(dict.fromkeys(k for k in kinds.split(',') if k)),
            extensions=list(dict.fromkeys(e for e in extensions.split(',') if e)),
            reports=reports,
        )
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
        run = OrganizadorRun(
            id=ident,
            created_by=principal.subject,
            company_id=company_id or None,
            options=options,
            name=path.name[:255] if is_zip else f'{len(files)} archivos',
            message='Preparando entrada.',
        )
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
def runs(db: Session = Depends(session), principal: Principal = Depends(auth)):
    return db.scalars(
        select(OrganizadorRun)
        .where(CFDI.scope(principal, OrganizadorRun))
        .order_by(OrganizadorRun.created_at.desc())
        .limit(50)
    ).all()


@router.get('/runs/{ident}')
def detail(ident: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = CFDI.check(principal, get_run(db, ident))
    records = []
    if (folder(ident) / 'plan.json').exists():
        plan = load_plan(ident)
        records = public_records(plan, [asdict(i) for i in plan.items])
    if run.status == 'generated':
        records = json.loads((folder(ident) / 'result.json').read_text(encoding='utf-8'))
    review_data = {}
    if (folder(ident) / 'review.json').exists():
        review_data = json.loads((folder(ident) / 'review.json').read_text(encoding='utf-8'))
    items = [public_item(i) for i in db.scalars(select(OrganizadorItem).where(OrganizadorItem.run_id == ident)).all()]
    return {
        'run': run,
        'records': records,
        'review': review_data.get('rows', {}),
        'omitted': review_data.get('omitted', []),
        'foreign_rfcs': review_data.get('foreign_rfcs', []),
        'items': items,
    }


def public_item(i):
    return {
        'id': i.id,
        'run_id': i.run_id,
        'company_id': i.company_id,
        'path': i.rel_path,
        'name': i.name,
        'kind': i.kind,
        'ext': i.ext,
        'uuid': i.uuid,
        'folder_period': i.folder_period,
        'xml_period': i.xml_period,
        'state': i.state,
        'reasons': i.reasons,
        'document_id': i.document_id,
        'decided_by': i.decided_by,
        'decided_at': i.decided_at.isoformat() if i.decided_at else None,
        'decided_period': i.decided_period,
    }


def load_review(ident):
    path = folder(ident) / 'review.json'
    if not path.exists():
        raise HTTPException(409, 'Primero termina el análisis.')
    return json.loads(path.read_text(encoding='utf-8'))


def input_source(ident):
    return Path(load_plan(ident).options.source)


def decide_states(db, ident, company_id):
    """For each XML/PDF of the run: nuevo | ya_registrado | revision | bloqueado, with the reasons (cambios 5.4, 5.5)."""
    rows = load_review(ident)['rows']
    source = input_source(ident)
    clean = {k: r for k, r in rows.items() if not r['incoherence']}
    against = content.against_expediente(db, company_id, clean, source)
    out = {}
    for rel, row in rows.items():
        if row['incoherence']:
            out[rel] = {'state': 'bloqueado', 'reasons': row['incoherence'], 'sha256': ''}
        else:
            a = against[rel]
            out[rel] = {'state': a['state'], 'reasons': [a['reason']] if a['reason'] else [], 'sha256': a['sha256']}
    return out


def company_for_save(db, principal, run, requested):
    company_id = run.company_id or requested
    if not company_id or not db.get(Company, company_id):
        raise HTTPException(422, 'Elige la empresa del expediente donde se guardará.')
    if run.company_id and requested and requested != run.company_id:
        raise HTTPException(422, 'Este análisis pertenece a otra empresa.')
    CFDI.require_company(principal, company_id)
    company = db.get(Company, company_id)
    if company.rfc != run.options['rfc']:
        raise HTTPException(422, 'El RFC del análisis no es el de la empresa: no se guarda en su expediente.')
    return company_id


def summarize_states(states):
    counts = {'nuevo': 0, 'ya_registrado': 0, 'revision': 0, 'bloqueado': 0}
    for item in states.values():
        counts[item['state']] += 1
    return counts


@router.get('/runs/{ident}/save-preview')
def save_preview(
    ident: str, company_id: str = '', db: Session = Depends(session), principal: Principal = Depends(auth)
):
    """Summary before saving: nuevos, ya registrados, en revisión y bloqueados (cambio 5.5)."""
    run = CFDI.check(principal, get_run(db, ident))
    if run.status not in ('analyzed', 'generated'):
        raise HTTPException(409, 'Primero termina el análisis.')
    target = company_for_save(db, principal, run, company_id)
    states = decide_states(db, ident, target)
    return {'company_id': target, 'counts': summarize_states(states), 'files': states}


class SaveIn(BaseModel):
    company_id: str = ''


@router.post('/runs/{ident}/save')
def save_to_expediente(ident: str, data: SaveIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Save the clean files; the blocked and conflicting ones go to «Por revisar» (CFDI). Cambio 5.5."""
    run = CFDI.check(principal, get_run(db, ident))
    if run.status not in ('analyzed', 'generated'):
        raise HTTPException(409, 'Primero termina el análisis.')
    company_id = company_for_save(db, principal, run, data.company_id)
    rows = load_review(ident)['rows']
    source = input_source(ident)
    states = decide_states(db, ident, company_id)
    existing = {i.rel_path: i for i in db.scalars(select(OrganizadorItem).where(OrganizadorItem.run_id == ident)).all()}
    for rel, decided in states.items():
        row = rows[rel]
        item = existing.get(rel)
        if item and item.state in ('saved', 'descartado'):
            continue
        digest = decided['sha256'] or content.sha256_of(source / rel)
        document_id = None
        state = decided['state']
        if state == 'nuevo':
            result = save_file(
                principal,
                company_id,
                source / rel,
                row['name'],
                document_type='cfdi' if row['ext'] == '.xml' else 'cfdi_pdf',
                period=row['period'],
                category='CFDI ' + row['kind'].lower(),
            )
            document_id = result['document_id']
            state = 'saved'
        values = dict(
            company_id=company_id,
            name=row['name'][:255],
            ext=row['ext'],
            kind=row['kind'],
            sha256=digest,
            uuid=row['uuid'] or None,
            folder_period=row['period'],
            xml_period=(row['fecha'][:7] or None),
            state=state,
            reasons=decided['reasons'],
            document_id=document_id,
        )
        if item:
            for key, value in values.items():
                setattr(item, key, value)
        else:
            db.add(OrganizadorItem(id=str(uuid4()), run_id=ident, rel_path=rel, **values))
    db.add(
        Audit(company_id=company_id, actor_id=principal.subject, action='Organizador CFDI: guardado en el expediente')
    )
    db.commit()
    items = db.scalars(select(OrganizadorItem).where(OrganizadorItem.run_id == ident)).all()
    return {'company_id': company_id, 'counts': summarize_states(states), 'items': [public_item(i) for i in items]}


class ResolveIn(BaseModel):
    action: Literal['save', 'dismiss']
    period: Literal['folder', 'xml'] = 'folder'


@router.get('/companies/{company_id}/review')
def company_review(company_id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Files waiting for a person («Por revisar › CFDI») and the saved totals by period (cambios 5.5 and 5.6)."""
    if not db.get(Company, company_id):
        raise HTTPException(404, 'Empresa no encontrada')
    if not principal.admin:
        principal.require(CFDI.action, company_id)
    rows = db.scalars(select(OrganizadorItem).where(OrganizadorItem.company_id == company_id)).all()
    pending = [public_item(i) for i in rows if i.state in ('revision', 'bloqueado')]
    periods = {}
    for i in rows:
        if i.state not in ('saved', 'ya_registrado'):
            continue
        period = i.decided_period or i.folder_period
        row = periods.setdefault(period, {'period': period, 'xml': 0, 'pdf': 0})
        row['xml' if i.ext == '.xml' else 'pdf'] += 1
    for item in pending:
        periods.setdefault(item['folder_period'], {'period': item['folder_period'], 'xml': 0, 'pdf': 0})
    for row in periods.values():
        row['en_revision'] = sum(1 for p in pending if p['folder_period'] == row['period'])
    return {'pending': pending, 'periods': sorted(periods.values(), key=lambda r: r['period'], reverse=True)}


# A reviewer may decide the period of a file whose folder and XML disagree; any other reason is only dismissable.
RESOLVABLE = {'periodo_distinto'}


@router.post('/items/{item_id}/resolve')
def resolve_item(item_id: str, data: ResolveIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    item = db.get(OrganizadorItem, item_id)
    if not item or item.state not in ('revision', 'bloqueado'):
        raise HTTPException(404, 'Archivo no encontrado o ya resuelto.')
    run = CFDI.check(principal, get_run(db, item.run_id))
    CFDI.require_company(principal, item.company_id)
    stamp = now()
    if data.action == 'dismiss':
        item.state = 'descartado'
    else:
        if not set(item.reasons) <= RESOLVABLE or not item.xml_period:
            raise HTTPException(
                422,
                'Este archivo no se puede guardar: su incoherencia no es sólo de periodo. Descártalo o corrige el origen.',
            )
        period = item.folder_period if data.period == 'folder' else item.xml_period
        path = input_source(run.id) / item.rel_path if (folder(run.id) / 'plan.json').exists() else None
        if not path or not path.is_file() or content.sha256_of(path) != item.sha256:
            raise HTTPException(410, 'El archivo original ya no está disponible o cambió. Vuelve a cargar la entrada.')
        result = save_file(
            principal,
            item.company_id,
            path,
            item.name,
            document_type='cfdi' if item.ext == '.xml' else 'cfdi_pdf',
            period=period,
            category='CFDI ' + item.kind.lower(),
        )
        item.document_id = result['document_id']
        item.state = 'saved'
        item.decided_period = period
    item.decided_by = principal.subject
    item.decided_at = stamp
    db.add(
        Audit(company_id=item.company_id, actor_id=principal.subject, action='Organizador CFDI: revisión de archivo')
    )
    db.commit()
    return public_item(item)


@router.get('/companies/{company_id}/suggestion')
def suggestion(company_id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """RFC of the expediente and the year/months to propose after the last organized period (cambio 5.1)."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    if not principal.admin:
        principal.require(CFDI.action, company_id)
    last = db.scalars(
        select(OrganizadorRun)
        .where(OrganizadorRun.company_id == company_id, OrganizadorRun.status == 'generated')
        .order_by(OrganizadorRun.created_at.desc())
        .limit(1)
    ).first()
    from datetime import date

    today = date.today()
    year, month, last_period = today.year, today.month, None
    if last and last.options.get('months'):
        last_year, last_month = last.options['year'], max(last.options['months'])
        last_period = f'{last_year}-{last_month:02d}'
        year, month = (last_year, last_month + 1) if last_month < 12 else (last_year + 1, 1)
    return {'rfc': company.rfc, 'year': year, 'months': [month], 'last_period': last_period}


def accepted_for_write(db, run):
    """Files accepted in 5.5 (saved or already registered) that belong to the run's year, and the ones left out."""
    year = run.options['year']
    included, left_out = [], []
    for i in db.scalars(select(OrganizadorItem).where(OrganizadorItem.run_id == run.id)).all():
        if i.state not in ('saved', 'ya_registrado'):
            continue
        period = i.decided_period or i.folder_period
        entry = {'id': i.id, 'name': i.name, 'kind': i.kind, 'period': period, 'sha256': i.sha256}
        (included if period.startswith(f'{year}-') else left_out).append(entry)
    return included, left_out


def write_target(db, principal, run):
    """(company, destination, link) or an HTTPException saying why the agent cannot write now."""
    from pathlib import PureWindowsPath

    from .agent_links import active_link_for, inside_roots, online as link_online, roots

    if not run.company_id:
        raise HTTPException(422, 'El análisis no pertenece a una empresa: guárdalo primero en un expediente.')
    company = db.get(Company, run.company_id)
    CFDI.require_company(principal, company.id)
    principal.require('carpeta.exportar', company.id)
    if not company.folder:
        raise HTTPException(422, 'La empresa no tiene ruta de carpeta: agrégala en Editar › Expediente digital.')
    allowed = roots(db)
    link = active_link_for(db, principal.subject)
    if link is None:
        raise HTTPException(409, 'Tu agente local no está vinculado: inicia sesión en ContaSuite en el equipo Windows.')
    if not link_online(link):
        raise HTTPException(409, 'Tu agente local está desconectado: revisa que esté en ejecución.')
    if not allowed or not inside_roots(company.folder, allowed):
        raise HTTPException(409, 'La ruta de la empresa está fuera de las carpetas autorizadas para el agente.')
    destination = str(PureWindowsPath(company.folder) / str(run.options['year']))
    return company, destination, link


@router.get('/runs/{ident}/write-folder-preview')
def write_folder_preview(ident: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Destination and list of the files that would be written into the company's folder (cambio 5.7)."""
    run = CFDI.check(principal, get_run(db, ident))
    included, left_out = accepted_for_write(db, run)
    company, destination, link = write_target(db, principal, run)
    return {
        'destination': destination,
        'machine': link.machine,
        'files': [{k: v for k, v in f.items() if k != 'sha256'} for f in included],
        'left_out': [{'name': f['name'], 'period': f['period']} for f in left_out],
        'structure': 'MM.- MES / EMITIDOS o RECIBIDOS',
    }


class WriteIn(BaseModel):
    confirm: bool = False


@router.post('/runs/{ident}/write-folder', status_code=201)
def write_folder(ident: str, data: WriteIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Queue the agent job. It needs the explicit confirmation the user gave on screen."""
    from .models import Job

    if not data.confirm:
        raise HTTPException(422, 'Confirma de forma explícita la escritura en la carpeta de la empresa.')
    run = CFDI.check(principal, get_run(db, ident))
    included, _left_out = accepted_for_write(db, run)
    if not included:
        raise HTTPException(422, 'No hay archivos aceptados para escribir. Guarda primero en el expediente.')
    company, destination, link = write_target(db, principal, run)
    busy = db.scalar(
        select(Job.id).where(
            Job.company_id == company.id, Job.kind == 'write_cfdi', Job.status.in_(('queued', 'running'))
        )
    )
    if busy:
        raise HTTPException(409, 'Ya hay una escritura en curso para esta empresa.')
    job = Job(
        company_id=company.id,
        agent_id=link.agent_id,
        kind='write_cfdi',
        payload={
            'folder': company.folder,
            'rfc': company.rfc,
            'destination': destination,
            'run_id': run.id,
            'files': included,
        },
        requested_by=principal.subject,
        link_id=link.id,
        machine=link.machine,
    )
    db.add(job)
    db.add(
        Audit(
            company_id=company.id,
            actor_id=principal.subject,
            action=f'Escritura de CFDI en la carpeta de la empresa solicitada ({len(included)} archivos)',
        )
    )
    db.commit()
    return {'id': job.id, 'destination': destination, 'files': len(included)}


@router.post('/runs/{ident}/generate', status_code=202)
def start_generate(
    ident: str, background: BackgroundTasks, db: Session = Depends(session), principal: Principal = Depends(auth)
):
    CFDI.check(principal, get_run(db, ident))
    changed = db.execute(
        update(OrganizadorRun)
        .where(OrganizadorRun.id == ident, OrganizadorRun.status == 'analyzed')
        .values(status='generating', message='Copiando y verificando SHA-256.')
    )
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'Primero termina el análisis. Cada análisis sólo se ejecuta una vez.')
    background.add_task(generate, ident)
    return {'status': 'generating'}


@router.get('/runs/{ident}/download')
def download(ident: str, kind: str = 'zip', db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = CFDI.check(principal, get_run(db, ident))
    if run.status != 'generated':
        raise HTTPException(409, 'Los resultados aún no están listos.')
    if kind not in ('zip', 'csv'):
        raise HTTPException(422, 'Selecciona ZIP o CSV.')
    if kind == 'csv' and (folder(ident) / 'review.json').exists():
        # The audit CSV adds UUID, incoherence, pair and saved state, which change after saving.
        review_data = load_review(ident)
        states = {
            i.rel_path: i.state for i in db.scalars(select(OrganizadorItem).where(OrganizadorItem.run_id == ident))
        }
        records = json.loads((folder(ident) / 'result.json').read_text(encoding='utf-8'))
        content.export_csv_extended(folder(ident) / 'auditoria_extendida.csv', records, review_data['rows'], states)
        return FileResponse(
            folder(ident) / 'auditoria_extendida.csv',
            filename=f'ORGANIZADOR_{run.options["rfc"]}_{run.options["year"]}.csv',
            media_type='text/csv; charset=utf-8',
        )
    return FileResponse(
        folder(ident) / ('result.zip' if kind == 'zip' else 'auditoria.csv'),
        filename=f'ORGANIZADOR_{run.options["rfc"]}_{run.options["year"]}.{kind}',
        media_type='application/zip' if kind == 'zip' else 'text/csv; charset=utf-8',
    )
