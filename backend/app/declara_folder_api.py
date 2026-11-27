"""Declara en modo carpeta (rediseño del 26/11/2026, sección 4): trabajos del agente y su cierre en el servidor.

El agente analiza y renombra en la carpeta real. Aquí se encolan sus trabajos (`declara_carpeta`), siempre para el
agente vinculado de quien los pide y con las raíces autorizadas por la administración; el agente vuelve a validar cada
ruta. Al terminar un análisis se crea un análisis de Declara con una «sombra» de la carpeta: archivos vacíos con los
mismos nombres, para que el plan, las colisiones y el panel «Resolver archivo» funcionen igual que con copias.
"""

import hashlib
import re
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import declara as web
from . import declara_engine as motor
from .agent_links import active_link_for, agent_caller, online as link_online, roots
from .database import session
from .models import Agent, Company, DeclaraFolder, DeclaraRun, Job
from .run_access import DECLARA
from .security import Principal, auth

KIND = 'declara_carpeta'
WEB_OPS = {'raices', 'listar', 'probar', 'firma', 'liberar'}
MAX_PDF = 25 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}')
ORIGINS = {'plantilla', 'red', 'equipo'}

router = APIRouter(prefix='/api/declara', tags=['Declara'])
agent_router = APIRouter(prefix='/api/agent/jobs', tags=['Agente'])


def checked_path(raw):
    """Sintaxis mínima: absoluta y sin «..». Las raíces las vuelve a validar el agente (y resuelve las unidades)."""
    text = (raw or '').strip().replace('/', '\\')
    win = PureWindowsPath(text)
    if not text or len(text) > 1000 or '..' in win.parts or not (win.drive and win.root):
        raise HTTPException(422, 'Escribe una ruta absoluta de Windows, sin «..».')
    return str(win)


def queue(db, principal, company_id, payload):
    """Un trabajo para el agente vinculado de quien lo pide. Nunca para el agente de otra persona."""
    DECLARA.require_company(principal, company_id)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    link = active_link_for(db, principal.subject)
    if link is None:
        db.commit()
        raise HTTPException(409, 'Tu agente local no está vinculado: abre ContaSuite en el equipo Windows del agente.')
    if not link_online(link):
        raise HTTPException(
            409, 'Tu agente local está desconectado' + (' en ' + link.machine if link.machine else '') + '.'
        )
    agent = db.get(Agent, link.agent_id)
    if not agent or KIND not in (agent.capabilities or []):
        raise HTTPException(409, 'El agente de este equipo todavía no admite el modo carpeta de Declara.')
    if not roots(db):
        raise HTTPException(409, 'No hay carpetas autorizadas para el agente: las define la administración.')
    job = Job(
        company_id=company.id,
        agent_id=link.agent_id,
        kind=KIND,
        payload=payload,
        requested_by=principal.subject,
        link_id=link.id,
        machine=link.machine,
    )
    db.add(job)
    db.commit()
    return job


def own_job(db, principal, job_id):
    job = db.get(Job, job_id)
    if not job or job.kind != KIND or not (principal.admin or job.requested_by == principal.subject):
        raise HTTPException(404, 'Trabajo no encontrado')
    DECLARA.require_company(principal, job.company_id)
    return job


# ---------------------------------------------------------------- plantilla y carpeta vinculada


def template_path(template, company, short_name, year):
    if not template:
        return ''
    values = {
        '{NOMBRE_CORTO}': motor.sanitize_company_name(short_name or ''),
        '{RFC}': company.rfc,
        '{RAZON_SOCIAL}': motor.sanitize_company_name(company.name),
        '{EJERCICIO}': str(year),
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template


def folders_of(db, company_id):
    rows = db.scalars(select(DeclaraFolder).where(DeclaraFolder.company_id == company_id)).all()
    return {str(r.year): {'ruta': r.path, 'origen': r.origin} for r in rows}


def link_folder(db, principal, company_id, year, path, origin):
    row = db.scalar(select(DeclaraFolder).where(DeclaraFolder.company_id == company_id, DeclaraFolder.year == year))
    if row is None:
        row = DeclaraFolder(company_id=company_id, year=year, path=path, origin=origin, created_by=principal.subject)
        db.add(row)
    else:
        row.path, row.origin = path, origin


class FolderIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    path: str = Field(min_length=3, max_length=1000)
    origin: str = 'equipo'


@router.put('/companies/{company_id}/folders')
def save_folder(company_id: str, data: FolderIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    DECLARA.require_company(principal, company_id)
    if not db.get(Company, company_id):
        raise HTTPException(404, 'Empresa no encontrada')
    if data.origin not in ORIGINS:
        raise HTTPException(422, 'Origen de carpeta no válido.')
    link_folder(db, principal, company_id, data.year, checked_path(data.path), data.origin)
    db.commit()
    return folders_of(db, company_id)


@router.get('/companies/{company_id}/folder')
def company_folder(
    company_id: str,
    year: int = Query(ge=2000, le=2100),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    """Carpeta del ejercicio: la vinculada o, si no hay, la de la plantilla de Configuración › Declara."""
    DECLARA.require_company(principal, company_id)
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, 'Empresa no encontrada')
    linked = folders_of(db, company_id).get(str(year))
    view = web.company_view(db, company)
    template = template_path(web.declara_settings(db)['template'], company, view['short_name'], year)
    recent = list(
        dict.fromkeys(
            [f['ruta'] for f in folders_of(db, company_id).values()]
            + [
                r.folder_path
                for r in db.scalars(
                    select(DeclaraRun)
                    .where(DeclaraRun.company_id == company_id, DeclaraRun.folder_path.is_not(None))
                    .order_by(DeclaraRun.created_at.desc())
                    .limit(20)
                )
            ]
        )
    )[:8]
    return {
        'vinculada': linked,
        'plantilla': template,
        'ruta': (linked or {}).get('ruta') or template,
        'origen': (linked or {}).get('origen') or ('plantilla' if template else None),
        'recientes': recent,
        'raices': roots(db),
    }


# ---------------------------------------------------------------- operaciones del selector y de la carpeta


class OpIn(BaseModel):
    company_id: str
    op: str
    ruta: str = Field(default='', max_length=1000)
    plantilla: str = Field(default='', max_length=1000)


@router.post('/folder', status_code=202)
def folder_op(data: OpIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    if data.op not in WEB_OPS:
        raise HTTPException(422, 'Operación no válida.')
    payload = {'op': data.op}
    if data.op != 'raices':
        payload['ruta'] = checked_path(data.ruta)
    if data.plantilla:
        payload['plantilla'] = data.plantilla
    return {'job_id': queue(db, principal, data.company_id, payload).id}


class AnalyzeIn(BaseModel):
    company_id: str
    year: int = Field(ge=2000, le=2100)
    short_name: str = Field(min_length=1, max_length=80)
    ruta: str = Field(min_length=3, max_length=1000)
    vincular: bool = False
    origen: str = 'equipo'


@router.post('/folder/analyze', status_code=202)
def folder_analyze(data: AnalyzeIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    company = db.get(Company, data.company_id)
    short_name = motor.sanitize_company_name(data.short_name)
    if not company or not short_name:
        raise HTTPException(422, 'Escribe un nombre corto de empresa de hasta 80 caracteres.')
    path = checked_path(data.ruta)
    job = queue(
        db,
        principal,
        data.company_id,
        {'op': 'analizar', 'ruta': path, 'nombre_corto': short_name, 'rfc': company.rfc, 'year': data.year},
    )
    web.remember_short_name(db, company.id, short_name, principal, mode='carpeta')
    if data.vincular:
        link_folder(db, principal, company.id, data.year, path, data.origen if data.origen in ORIGINS else 'equipo')
    db.commit()
    return {'job_id': job.id}


def brief(result):
    """El resultado sin los registros del plan, que pueden ser muchos."""
    return {k: v for k, v in (result or {}).items() if k not in {'registros', 'nombres', 'claimed_at'}}


@router.get('/folder/jobs/{job_id}')
def folder_job(job_id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    job = own_job(db, principal, job_id)
    if job.status in {'completed', 'failed'}:
        finish(db, job)
    return {'id': job.id, 'op': (job.payload or {}).get('op'), 'status': job.status, 'result': brief(job.result)}


# ---------------------------------------------------------------- cierre de trabajos


def safe_name(name):
    return (
        isinstance(name, str)
        and 0 < len(name) <= 255
        and PureWindowsPath(name).name == name
        and not motor.INVALID_FILENAME_CHARS.search(name)
        and name not in {'.', '..'}
    )


def finish(db, job):
    """Idempotente: cada trabajo terminado se procesa una vez (marca `cerrado` en su resultado)."""
    result = dict(job.result or {})
    if result.get('cerrado'):
        return
    op = (job.payload or {}).get('op')
    if job.status == 'completed' and op == 'analizar':
        result['analisis_id'] = create_run(db, job, result)
    elif op in {'aplicar', 'deshacer'}:
        close_apply(db, job, result)
    result['cerrado'] = True
    result.pop('registros', None)
    result.pop('nombres', None)
    changed = db.execute(update(Job).where(Job.id == job.id, Job.status == job.status).values(result=result))
    if changed.rowcount:
        db.commit()
        db.refresh(job)
    else:
        db.rollback()


def create_run(db, job, result):
    payload = job.payload
    company = db.get(Company, job.company_id)
    ident = str(uuid4())
    root = web.folder(ident) / 'input'
    root.mkdir(parents=True)
    for name in result.get('nombres', []):
        if safe_name(name):
            (root / name).touch()  # sombra: el nombre existe, sin contenido
    infos = []
    for record in result.get('registros', []):
        if not safe_name(record.get('path')):
            continue
        fields = {k: v for k, v in record.items() if k in motor.PdfInfo.__dataclass_fields__ and k != 'path'}
        infos.append(motor.PdfInfo(path=root / record['path'], **fields))
    web.save_plan(ident, infos)
    web.write_json(web.folder(ident) / 'plan_original.json', web.records_of(ident, infos))
    run = DeclaraRun(
        id=ident,
        created_by=job.requested_by,
        company_id=company.id,
        expected_rfc=company.rfc,
        short_name=payload['nombre_corto'],
        name=f'Carpeta · {len(infos)} PDF',
        message='Análisis de la carpeta terminado. Revisa los nombres y el control documental.',
        status='analyzed',
        year=payload.get('year'),
        mode='carpeta',
        folder_path=result.get('ruta') or payload['ruta'],
    )
    db.add(run)
    db.flush()
    web.refresh_run(db, run, infos)
    run.summary = {
        **run.summary,
        'leidos': result.get('leidos'),
        'archivos': result.get('total'),
        'firma': result.get('firma'),
        'solo_lectura': bool(result.get('solo_lectura')),
        'bloqueo': result.get('bloqueo'),
        'deshacer': bool(result.get('deshacer')),
        'equipo': job.machine,
    }
    warnings = []
    if run.summary.get('other_year'):
        warnings.append(f'{run.summary["other_year"]} PDF son de un ejercicio distinto a {run.summary["year"]}.')
    if not run.summary['rfc_matches']:
        warnings.append('El RFC principal de la carpeta no coincide con la empresa: no se aplicará el renombrado.')
    if run.summary['solo_lectura']:
        lock = result.get('bloqueo') or {}
        warnings.append(
            f'En uso por {lock.get("usuario", "otra persona")} · {lock.get("equipo", "")}: la carpeta queda en sólo lectura.'
        )
    long = [i.expected_name for i in infos if i.expected_name and len(run.folder_path) + 1 + len(i.expected_name) > 240]
    if long:
        warnings.append(f'{len(long)} nombres finales pasan de 240 caracteres con la ruta: se usarán rutas largas.')
    run.warnings = warnings
    s = run.summary
    web.log(
        db,
        'analisis',
        user_id=job.requested_by,
        company_id=company.id,
        year=s['year'],
        run_id=ident,
        machine=job.machine,
        path=run.folder_path,
        detail={
            'modo': 'carpeta',
            'pdf': s['total'],
            'leidos': s.get('leidos'),
            'por_renombrar': s['rename'],
            'correctos': s['correct'],
            'copias_identicas': s['identical'],
            'omitidos': s['omitted'],
        },
    )
    return ident


def close_apply(db, job, result):
    payload = job.payload
    run = db.get(DeclaraRun, payload.get('run_id')) if payload.get('run_id') else None
    op = payload['op']
    common = dict(
        user_id=job.requested_by,
        company_id=job.company_id,
        year=run.year if run else payload.get('year'),
        run_id=run.id if run else None,
        machine=job.machine,
        path=payload.get('ruta'),
    )
    if job.status != 'completed':
        if run is not None and run.status in {'applying', 'undoing'}:
            run.status = 'analyzed' if run.status == 'applying' else 'applied'
            run.message = 'No se aplicó: ' + (result.get('error') or 'el agente no pudo completar el trabajo.')
        web.log(db, 'error_' + op, detail={'error': result.get('error')}, **common)
        return
    if op == 'aplicar':
        if result.get('respaldo'):
            web.log(db, 'respaldo', detail={'carpeta': '.declara\\respaldos\\' + result['respaldo']}, **common)
        web.log(
            db,
            'renombrado',
            detail={
                'renombrados': result.get('renombrados'),
                'pendientes': result.get('pendientes'),
                'lote': result.get('lote'),
                'cambios': payload.get('plan', [])[:200],
            },
            **common,
        )
        if run is not None:
            run.status = 'applied'
            pending = result.get('pendientes') or []
            run.message = f'Renombrado aplicado en la carpeta: {result.get("renombrados", 0)} archivos.' + (
                f' {len(pending)} pendientes · en uso por otro usuario.' if pending else ''
            )
            run.summary = {
                **run.summary,
                'renamed': result.get('renombrados', 0),
                'pendientes': pending,
                'deshacer': True,
            }
    else:
        web.log(db, 'deshacer', detail={'restaurados': result.get('restaurados'), 'lote': result.get('lote')}, **common)
        if run is not None:
            run.status = 'undone'
            run.message = f'Se deshizo el último renombrado: {result.get("restaurados", 0)} archivos.'


def finish_pending(db, run):
    """Al consultar un análisis en curso de aplicar/deshacer, cierra su trabajo si el agente ya respondió."""
    job_id = (run.summary or {}).get('trabajo')
    if not job_id or run.status not in {'applying', 'undoing'}:
        return
    job = db.get(Job, job_id)
    if job and job.status in {'completed', 'failed'}:
        finish(db, job)
        db.refresh(run)


# ---------------------------------------------------------------- aplicar, deshacer y vista previa


class ApplyIn(BaseModel):
    revision: int = Field(ge=0)
    respaldo: bool = True


@router.post('/runs/{ident}/apply', status_code=202)
def apply(ident: str, data: ApplyIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = DECLARA.check(principal, web.get_run(db, ident))
    if run.mode != 'carpeta':
        raise HTTPException(422, 'Este análisis trabaja con copias: genera las copias renombradas.')
    s = run.summary or {}
    if not s.get('rfc_matches'):
        raise HTTPException(422, 'El RFC detectado no coincide con la empresa seleccionada.')
    if s.get('solo_lectura'):
        raise HTTPException(409, 'La carpeta está en uso por otra persona: vuelve a analizarla cuando se libere.')
    infos = web.load_plan(ident)
    plan = [
        {'origen': i.path.name, 'destino': i.expected_name, 'sha256': i.sha256}
        for i in infos
        if i.status == 'RENOMBRAR' and i.expected_name
    ]
    if not plan:
        raise HTTPException(422, 'No hay archivos por renombrar.')
    changed = db.execute(
        update(DeclaraRun)
        .where(DeclaraRun.id == ident, DeclaraRun.status == 'analyzed', DeclaraRun.revision == data.revision)
        .values(status='applying', message='Aplicando el renombrado en la carpeta…')
    )
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'El análisis cambió o ya se aplicó. Actualiza para revisar.')
    try:
        job = queue(
            db,
            principal,
            run.company_id,
            {'op': 'aplicar', 'ruta': run.folder_path, 'plan': plan, 'respaldo': data.respaldo, 'run_id': ident},
        )
    except HTTPException:
        db.execute(update(DeclaraRun).where(DeclaraRun.id == ident).values(status='analyzed', message=''))
        db.commit()
        raise
    db.refresh(run)
    run.summary = {**run.summary, 'trabajo': job.id, 'respaldo': data.respaldo}
    db.commit()
    return {'job_id': job.id}


@router.post('/runs/{ident}/undo', status_code=202)
def undo(ident: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = DECLARA.check(principal, web.get_run(db, ident))
    if run.mode != 'carpeta' or not run.folder_path:
        raise HTTPException(422, 'Sólo el modo carpeta tiene renombrados que deshacer.')
    if run.status in {'applying', 'undoing'}:
        raise HTTPException(409, 'Hay una operación en curso en esta carpeta.')
    previous = run.status
    job = queue(
        db, principal, run.company_id, {'op': 'deshacer', 'ruta': run.folder_path, 'run_id': ident, 'year': run.year}
    )
    run.status = 'undoing' if previous == 'applied' else previous
    run.summary = {**run.summary, 'trabajo': job.id}
    db.commit()
    return {'job_id': job.id}


@router.post('/runs/{ident}/fetch-pdf/{index}', status_code=202)
def fetch_pdf(ident: str, index: int, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = DECLARA.check(principal, web.get_run(db, ident))
    if run.mode != 'carpeta':
        raise HTTPException(422, 'La vista previa de este análisis ya está en ContaSuite.')
    infos = web.load_plan(ident)
    if index < 0 or index >= len(infos) or not infos[index].sha256:
        raise HTTPException(404, 'PDF no encontrado')
    info = infos[index]
    if (web.folder(ident) / 'cache' / (info.sha256 + '.pdf')).exists():
        return {'job_id': None, 'listo': True}
    job = queue(
        db,
        principal,
        run.company_id,
        {'op': 'leer_pdf', 'ruta': run.folder_path, 'nombre': info.path.name, 'sha256': info.sha256, 'run_id': ident},
    )
    return {'job_id': job.id, 'listo': False}


@agent_router.put('/{ident}/declara/{sha}')
async def receive_pdf(
    ident: str,
    sha: str,
    request: Request,
    agent_id: str = Query(..., max_length=80),
    db: Session = Depends(session),
    caller=Depends(agent_caller),
):
    """El PDF de una vista previa: sólo si es el pedido por ese trabajo, es PDF y coincide con su huella."""
    job = db.get(Job, ident)
    if not job or job.kind != KIND or job.agent_id != agent_id or job.status != 'running':
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if caller is not None and (agent_id != caller.link.agent_id or job.requested_by != caller.link.user_id):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    payload = job.payload or {}
    if payload.get('op') != 'leer_pdf' or payload.get('sha256') != sha or not SHA.fullmatch(sha):
        raise HTTPException(422, 'Huella inválida.')
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_PDF:
            raise HTTPException(413, 'El PDF es demasiado grande.')
    if not body.startswith(b'%PDF-') or hashlib.sha256(body).hexdigest() != sha:
        raise HTTPException(422, 'El contenido no coincide con su huella.')
    folder = web.folder(payload['run_id']) / 'cache'
    folder.mkdir(parents=True, exist_ok=True)
    pending = folder / (sha + '.pdf.part')
    pending.write_bytes(bytes(body))
    pending.replace(folder / (sha + '.pdf'))
    return {'ok': True}


def cached_pdf(ident, info) -> Path | None:
    path = web.folder(ident) / 'cache' / ((info.sha256 or '') + '.pdf')
    return path if info.sha256 and path.exists() else None
