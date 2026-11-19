"""Adaptador web del motor original de Recopila, sin interfaz de escritorio."""

import json
import logging
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
from .models import Company, RecopilaRun, Audit, RecopilaPolicy, RecopilaPolicyCfdi, RecopilaAdjustment, now
from . import recopila_engine as motor
from . import recopila_enrich as enrich

from .run_access import RECOPILA
from .security import Principal, auth

router = APIRouter(prefix='/api/recopila', tags=['Recopila'])
MAX_UPLOAD = 100 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
MAX_FILES = 5000


def folder(ident):
    return DATA / 'recopila' / ident


def get_run(db, ident):
    run = db.get(RecopilaRun, ident)
    if not run:
        raise HTTPException(404, 'Análisis no encontrado')
    return run


def safe_name(name):
    raw = name.replace('\\', '/')
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') or ':' in p or '\x00' in p for p in path.parts):
        raise ValueError('La entrada contiene una ruta no válida.')
    if len(raw) > 700:
        raise ValueError('Hay una ruta demasiado larga.')
    return path.with_suffix(path.suffix.lower())


def extract_zip(archive, target):
    size = 0
    count = 0
    seen = set()
    ignored = 0
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > MAX_FILES * 2:
            raise ValueError('El ZIP contiene demasiadas entradas.')
        for info in z.infolist():
            path = safe_name(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('No se admiten enlaces dentro del ZIP.')
            if info.is_dir():
                continue
            if path.suffix.lower() not in {'.pdf', '.xml'}:
                ignored += 1
                continue
            if info.flag_bits & 1:
                raise ValueError('El ZIP está protegido con contraseña.')
            count += 1
            size += info.file_size
            if count > MAX_FILES or size > MAX_EXPANDED:
                raise ValueError('El ZIP supera el límite de 5,000 documentos o 500 MB descomprimidos.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError('El ZIP repite la misma ruta de documento.')
            seen.add(key)
            dest = target / str(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, dest.open('xb') as out:
                shutil.copyfileobj(src, out)
    if not count:
        raise ValueError('No se encontraron PDF o XML en la entrada.')
    return ignored


def progress(ident, status, message):
    with SessionLocal() as db:
        db.execute(update(RecopilaRun).where(RecopilaRun.id == ident).values(status=status, message=message[:1000]))
        db.commit()


def load_analysis(ident):
    data = json.loads((folder(ident) / 'analysis.json').read_text(encoding='utf-8'))
    return motor.AnalysisResult(
        root=data['root'],
        policies=[motor.PolicyRecord(**p) for p in data['policies']],
        cfdis=[motor.CfdiRecord(**c) for c in data['cfdis']],
        leftovers=data['leftovers'],
        summary=data['summary'],
    )


logger = logging.getLogger(__name__)


def unreadable_pdfs(result):
    """PDFs the original engine would silently leave out of the generated files.

    recopila_engine.generate_* skips any matched or leftover PDF it cannot read (`except Exception: pass`).
    The engine stays unchanged (AGENTS.md); the adapter reads them the same way beforehand so the user is
    told which documents would be missing.
    """
    unreadable = []
    for doc in dict.fromkeys([d for p in result.policies for d in p.matched_pdfs] + list(result.leftovers)):
        try:
            for _ in motor.PdfReader(doc).pages:
                pass
        except Exception:  # noqa: BLE001 - same breadth as the engine's skip; reported, not hidden
            logger.warning('Recopila: PDF ilegible, el motor lo omitiría: %s', Path(doc).name, exc_info=True)
            unreadable.append(Path(doc).name)
    return unreadable


def analyze(ident):
    try:
        root = folder(ident)
        source = root / 'input'
        warnings = []
        if (root / 'input.zip').exists():
            ignored = extract_zip(root / 'input.zip', source)
            if ignored:
                warnings.append(f'Se omitieron {ignored} archivos que no son PDF o XML.')
        result = motor.analyze(source, root / 'work', lambda m: progress(ident, 'analyzing', m))
        if not result.policies:
            warnings.append(
                'No se detectaron pólizas con texto compatible. El motor no incluye OCR para documentos escaneados.'
            )
        stems = {}
        for pdf in source.rglob('*'):
            if pdf.suffix.lower() == '.pdf':
                stems.setdefault(pdf.stem.upper(), []).append(pdf)
        if any(len(v) > 1 for v in stems.values()):
            warnings.append(
                'Hay PDF con el mismo nombre en distintas carpetas. Revisa las coincidencias: el motor relaciona los PDF por nombre/UUID.'
            )
        if result.summary['xml_total'] > result.summary['cfdi_xml_parsed']:
            warnings.append('Hay XML que no se pudieron interpretar como CFDI con UUID.')
        if any(not p.month for p in result.policies):
            warnings.append('Hay pólizas sin un mes identificable; se conservan en el recopilador general.')
        unreadable = unreadable_pdfs(result)
        if unreadable:
            listed = ', '.join(unreadable[:10]) + (' y otros' if len(unreadable) > 10 else '')
            warnings.append(
                f'{len(unreadable)} PDF no se pueden leer y no se incluirán en los documentos generados: {listed}. '
                'Reemplázalos por una copia válida y vuelve a cargar antes de generar.'
            )
        (root / 'analysis.json').write_text(json.dumps(asdict(result), ensure_ascii=False), encoding='utf-8')
        with SessionLocal() as db:
            company_id = get_run(db, ident).company_id
            company = db.get(Company, company_id) if company_id else None
            rfc = company.rfc if company else ''
        enrichment = enrich.build(result, rfc)
        (root / 'enrichment.json').write_text(json.dumps(enrichment, ensure_ascii=False), encoding='utf-8')
        if enrichment['unsupported']['pages']:
            warnings.append(
                f"{enrichment['unsupported']['pages']} páginas parecen pólizas en un formato no compatible"
                + (' (Contalink)' if enrichment['unsupported']['contalink_hint'] else '')
                + '. Recopila sólo lee el «Impreso de pólizas» de CONTPAQi; esas páginas no se incluyen.'
            )
        if any(r['kind'] == 'rfc_ajeno' for r in enrichment['review']):
            warnings.append('Hay CFDI con un RFC distinto al de la empresa: revísalos antes de generar.')
        if any(r['kind'] == 'pareja_no_verificada' for r in enrichment['review']):
            warnings.append('Hay PDF emparejados por nombre cuyo UUID no aparece en su texto (pareja no verificada).')
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.status = 'analyzed'
            run.message = 'Análisis terminado. Revisa las coincidencias antes de generar.'
            run.summary = {
                **result.summary,
                'months_detail': enrichment['months'],
                'leftover_categories': enrichment['leftover_categories'],
            }
            run.warnings = warnings
            persist_policies(db, ident, result, enrichment)
            db.add(Audit(company_id=run.company_id, actor_id=run.created_by, action='Recopila: análisis terminado'))
            db.commit()
    except Exception as exc:  # noqa: BLE001 - background job: logged and reported on the run
        logger.exception('Recopila: falló el análisis %s', ident)
        progress(ident, 'error', 'No se pudo analizar: ' + str(exc))


def persist_policies(db, ident, result, enrichment):
    """Store the policies and their CFDI relations (origin: engine) for later queries (cs_0016)."""
    by_pdf = {c.pdf_path: c.uuid for c in result.cfdis if c.pdf_path}
    db.query(RecopilaPolicy).filter(RecopilaPolicy.run_id == ident).delete()
    for index, pol in enumerate(result.policies):
        row = RecopilaPolicy(
            id=str(uuid4()),
            run_id=ident,
            idx=index,
            policy_type=pol.policy_type,
            policy_date=pol.date,
            period=pol.month,
            status=enrichment['policies'][index]['status'],
            uuids=pol.uuids,
        )
        db.add(row)
        for pdf in pol.matched_pdfs:
            if pdf in by_pdf:
                db.merge(RecopilaPolicyCfdi(policy_id=row.id, cfdi_uuid=by_pdf[pdf], origin='motor', state='active'))


def load_enrichment(ident):
    path = folder(ident) / 'enrichment.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def adjustments_for(db, ident):
    return [
        {
            'id': a.id,
            'policy_idx': a.policy_idx,
            'action': a.action,
            'target': a.target,
            'cfdi_uuid': a.cfdi_uuid,
            'actor_id': a.actor_id,
            'created_at': a.created_at.isoformat(),
            'revoked_at': a.revoked_at.isoformat() if a.revoked_at else None,
        }
        for a in db.scalars(
            select(RecopilaAdjustment).where(RecopilaAdjustment.run_id == ident).order_by(RecopilaAdjustment.created_at)
        )
    ]


def _relative(root, path):
    try:
        return str(Path(path).relative_to(root)).replace(chr(92), '/')
    except ValueError:
        return Path(path).name


def output_files(ident):
    out = folder(ident) / 'output'
    return (
        [
            {'name': str(p.relative_to(out)).replace('\\', '/'), 'size': p.stat().st_size}
            for p in sorted(out.rglob('*'))
            if p.is_file()
        ]
        if out.exists()
        else []
    )


def generate(ident, by_month):
    target = folder(ident) / 'output'
    temporary = folder(ident) / 'output_pending'
    try:
        shutil.rmtree(temporary, ignore_errors=True)
        result = load_analysis(ident)
        with SessionLocal() as db:
            confirmed = adjustments_for(db, ident)
        enrich.apply_adjustments(result, confirmed)
        motor.generate_all(result, temporary, lambda m: progress(ident, 'generating', m), generate_by_month=by_month)
        if target.exists():
            shutil.rmtree(target)
        temporary.rename(target)
        with SessionLocal() as db:
            run = get_run(db, ident)
            run.status = 'generated'
            run.message = 'Archivos generados.'
            run.by_month = by_month
            db.add(Audit(company_id=run.company_id, actor_id=run.created_by, action='Recopila: documentos generados'))
            db.commit()
    except Exception as exc:  # noqa: BLE001 - background job: logged and reported on the run
        logger.exception('Recopila: falló la generación %s', ident)
        shutil.rmtree(temporary, ignore_errors=True)
        progress(ident, 'error', 'No se pudo generar: ' + str(exc))


@router.post('/runs', status_code=202)
async def start(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    company_id: str = Form(''),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    RECOPILA.require_company(principal, company_id)
    if company_id and not db.get(Company, company_id):
        raise HTTPException(404, 'Empresa no encontrada')
    if not files or len(files) > 1000:
        raise HTTPException(422, 'Selecciona hasta 1,000 documentos o un ZIP con hasta 5,000 documentos.')
    ident = str(uuid4())
    root = folder(ident)
    source = root / 'input'
    source.mkdir(parents=True)
    seen = set()
    size = 0
    try:
        is_zip = len(files) == 1 and Path(files[0].filename or '').suffix.lower() == '.zip'
        for file in files:
            path = safe_name(file.filename or '')
            if not is_zip and path.suffix.lower() not in {'.pdf', '.xml'}:
                raise ValueError('Selecciona PDF/XML o un único archivo ZIP.')
            key = str(path).casefold()
            if key in seen:
                raise ValueError(
                    'Hay documentos con la misma ruta. Usa una carpeta o un ZIP para conservar la estructura.'
                )
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
        run = RecopilaRun(
            id=ident,
            created_by=principal.subject,
            company_id=company_id or None,
            name=Path(files[0].filename or 'Documentos').name if len(files) == 1 else f'{len(files)} documentos',
            status='analyzing',
            message='Preparando documentos.',
        )
        db.add(run)
        db.commit()
        background.add_task(analyze, ident)
        return run
    except (ValueError, zipfile.BadZipFile) as exc:
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
        select(RecopilaRun)
        .where(RECOPILA.scope(principal, RecopilaRun))
        .order_by(RecopilaRun.created_at.desc())
        .limit(50)
    ).all()


@router.get('/runs/{ident}')
def detail(ident: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = RECOPILA.check(principal, get_run(db, ident))
    policies = []
    leftovers = []
    if (folder(ident) / 'analysis.json').exists():
        result = load_analysis(ident)
        source = Path(result.root)

        def rel(p):
            return str(Path(p).relative_to(source)).replace('\\', '/')

        for p in motor.sorted_policies(result):
            policies.append(
                {
                    'source': rel(p.source_pdf),
                    'page': p.page,
                    'type': p.policy_type,
                    'date': p.date,
                    'month': p.month,
                    'description': p.description,
                    'uuids': p.uuids,
                    'matches': [rel(v) for v in p.matched_pdfs],
                    'status': p.match_status,
                    'section': p.section,
                }
            )
        leftovers = [rel(p) for p in result.leftovers]
    extra = load_enrichment(ident)
    if extra and policies:
        position = {id(p): i for i, p in enumerate(result.policies)}
        for item, pol in zip(policies, motor.sorted_policies(result), strict=True):
            index = position[id(pol)]
            item['index'] = index
            item['support'] = extra['policies'][index]['status']
            item['missing'] = extra['policies'][index]['missing']
    return {
        'run': run,
        'policies': policies,
        'leftovers': leftovers,
        'outputs': output_files(ident) if run.status == 'generated' else [],
        'enrichment': (
            {
                'proposals': extra['proposals'],
                'review': extra['review'],
                'leftover_items': extra['leftovers'],
                'leftover_categories': extra['leftover_categories'],
                'unsupported': extra['unsupported'],
                'months': extra['months'],
                'cfdis': extra['cfdis'],
            }
            if extra
            else None
        ),
        'adjustments': adjustments_for(db, ident),
    }


class AdjustmentIn(BaseModel):
    policy_index: int
    action: Literal['attach', 'remove']
    target: str


@router.post('/runs/{ident}/adjustments', status_code=201)
def add_adjustment(
    ident: str,
    data: AdjustmentIn,
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    """Associate a leftover/proposed PDF with a policy, or drop a proposal, before generating (cambio 4.2)."""
    run = RECOPILA.check(principal, get_run(db, ident))
    extra = load_enrichment(ident)
    if run.status not in ('analyzed', 'generated') or not extra:
        raise HTTPException(409, 'Primero termina el análisis.')
    if not 0 <= data.policy_index < len(extra['policies']):
        raise HTTPException(422, 'Póliza no encontrada.')
    known = {i['pdf']: i['uuid'] for i in extra['leftovers']} | {p['pdf']: p['uuid'] for p in extra['proposals']}
    analysis = load_analysis(ident)
    matched = {_relative(analysis.root, pdf) for pol in analysis.policies for pdf in pol.matched_pdfs}
    if data.target not in known and data.target not in matched:
        raise HTTPException(422, 'El documento no pertenece a este análisis.')
    from_proposal = any(p['pdf'] == data.target and p['policy_index'] == data.policy_index for p in extra['proposals'])
    adjustment = RecopilaAdjustment(
        id=str(uuid4()),
        run_id=ident,
        policy_idx=data.policy_index,
        action=data.action,
        target=data.target,
        cfdi_uuid=known.get(data.target),
        actor_id=principal.subject,
        created_at=now(),
    )
    db.add(adjustment)
    policy = db.scalar(
        select(RecopilaPolicy).where(RecopilaPolicy.run_id == ident, RecopilaPolicy.idx == data.policy_index)
    )
    if policy and adjustment.cfdi_uuid:
        db.merge(
            RecopilaPolicyCfdi(
                policy_id=policy.id,
                cfdi_uuid=adjustment.cfdi_uuid,
                origin='propuesta' if from_proposal else 'manual',
                state='active' if data.action == 'attach' else 'removed',
                decided_by=principal.subject,
                decided_at=adjustment.created_at,
            )
        )
    db.add(Audit(company_id=run.company_id, actor_id=principal.subject, action='Recopila: ajuste manual de póliza'))
    db.commit()
    return adjustments_for(db, ident)


@router.delete('/runs/{ident}/adjustments/{adjustment_id}')
def revoke_adjustment(
    ident: str, adjustment_id: str, db: Session = Depends(session), principal: Principal = Depends(auth)
):
    RECOPILA.check(principal, get_run(db, ident))
    adjustment = db.get(RecopilaAdjustment, adjustment_id)
    if not adjustment or adjustment.run_id != ident:
        raise HTTPException(404, 'Ajuste no encontrado.')
    if not adjustment.revoked_at:
        adjustment.revoked_at = now()
        db.commit()
    return adjustments_for(db, ident)


class GenerateIn(BaseModel):
    by_month: bool = False


@router.post('/runs/{ident}/generate', status_code=202)
def start_generate(
    ident: str,
    data: GenerateIn,
    background: BackgroundTasks,
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    run = RECOPILA.check(principal, get_run(db, ident))
    if run.status not in ('analyzed', 'generated', 'error') or not (folder(ident) / 'analysis.json').exists():
        raise HTTPException(409, 'Primero termina el análisis.')
    if not run.summary.get('policy_pages'):
        raise HTTPException(422, 'No se detectaron pólizas compatibles para generar el recopilador.')
    # Atomic claim across browsers/processes.
    changed = db.execute(
        update(RecopilaRun)
        .where(RecopilaRun.id == ident, RecopilaRun.status == run.status)
        .values(status='generating', message='Generando documentos.')
    )
    db.commit()
    if not changed.rowcount:
        raise HTTPException(409, 'Este análisis ya tiene una generación en curso.')
    background.add_task(generate, ident, data.by_month)
    return {'status': 'generating'}


@router.get('/runs/{ident}/file')
def file(
    ident: str, name: str, kind: str = 'output', db: Session = Depends(session), principal: Principal = Depends(auth)
):
    run = RECOPILA.check(principal, get_run(db, ident))
    if kind not in ('output', 'input'):
        raise HTTPException(422, 'Tipo de archivo no válido')
    if kind == 'output' and run.status != 'generated':
        raise HTTPException(409, 'Los archivos aún no están listos.')
    root = folder(ident) / kind
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(404, 'Archivo no encontrado')
    if kind == 'input' and path.suffix.lower() != '.pdf':
        raise HTTPException(422, 'La vista previa admite PDF.')
    return FileResponse(
        path,
        filename=path.name,
        media_type='application/pdf' if path.suffix.lower() == '.pdf' else 'application/octet-stream',
    )


@router.get('/runs/{ident}/zip')
def download_zip(ident: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    run = RECOPILA.check(principal, get_run(db, ident))
    if run.status != 'generated':
        raise HTTPException(409, 'Los archivos aún no están listos.')
    from starlette.background import BackgroundTask

    out = folder(ident) / (str(uuid4()) + '.zip')
    root = folder(ident) / 'output'
    try:
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for file in sorted(root.rglob('*')):
                if file.is_file():
                    z.write(file, str(file.relative_to(root)))
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return FileResponse(
        out,
        filename='RECOPILADOR_RESULTADOS.zip',
        media_type='application/zip',
        background=BackgroundTask(out.unlink, missing_ok=True),
    )
