"""Write the accepted CFDI files into the company's physical folder with the local agent (cambio 5.7).

The server never writes to the user's computer: it queues a `write_cfdi` job; the agent downloads each accepted file
from ContaSuite and COPIES it under `<destination>/MM.- MES/EMITIDOS|RECIBIDOS/`. Rules, all enforced by
`write_files`: only copies, never overwrites (a name that already exists is reported as «Duplicado»), every file is
verified with SHA-256 before and after writing, and the user can cancel between files.
"""

import hashlib
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy.orm import Session

from .agent_jobs import claim_marker
from .agent_links import agent_caller
from .database import session
from .models import Job
from .schemas import CleanModel

KIND = 'write_cfdi'
MONTHS = (
    'ENERO',
    'FEBRERO',
    'MARZO',
    'ABRIL',
    'MAYO',
    'JUNIO',
    'JULIO',
    'AGOSTO',
    'SEPTIEMBRE',
    'OCTUBRE',
    'NOVIEMBRE',
    'DICIEMBRE',
)
PERIOD = re.compile(r'^(20\d{2})-(0[1-9]|1[0-2])$')
MAX_DETAIL = 40
FORBIDDEN_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

router = APIRouter(prefix='/api/agent/jobs', tags=['Agente'])


def month_dir(period, kind):
    """`MM.- MES/EMITIDOS` (or RECIBIDOS) for a period `YYYY-MM`, the structure of the organized folders."""
    match = PERIOD.fullmatch(period or '')
    if not match or kind not in ('Emitidos', 'Recibidos'):
        raise ValueError('periodo o tipo no válido')
    month = int(match[2])
    return Path(f'{month:02d}.- {MONTHS[month - 1]}') / kind.upper()


def destination_problem(destination, folder, allowed_roots):
    """Why a destination is not acceptable, or '' when it is: inside the company folder and an authorized root."""
    from .agent_links import inside_roots

    if not destination or not folder:
        return 'destino_invalido'
    if not inside_roots(folder, allowed_roots) or not inside_roots(destination, [folder]):
        return 'destino_fuera_de_raices'
    return ''


def _digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _exists(folder, name):
    """Windows ignores case: the same name in other letters is the same file."""
    return folder.is_dir() and any(p.name.casefold() == name.casefold() for p in folder.iterdir())


def write_files(files, destination, fetch, cancelled=None, progress=None):
    """Copy `files` (dicts with id, name, kind, period, sha256) under `destination`. Returns the outcome counters.

    `fetch(item_id)` returns the file's bytes. Nothing existing is ever replaced.
    """
    root = Path(destination)
    result = {'escritos': 0, 'duplicados': 0, 'errores': 0, 'cancelado': False, 'detalle': []}
    root.mkdir(parents=True, exist_ok=True)
    for n, item in enumerate(files):
        if cancelled is not None and cancelled.is_set():
            result['cancelado'] = True
            break
        state, why = 'Error', ''
        temporary = None
        try:
            name = str(item['name'])
            if FORBIDDEN_NAME.search(name) or name in ('.', '..'):
                raise ValueError('nombre no válido')
            folder = root / month_dir(item['period'], item['kind'])
            if not folder.resolve().is_relative_to(root.resolve()):
                raise ValueError('fuera del destino')
            if _exists(folder, name):
                state, why = 'Duplicado', 'Ya existe un archivo con ese nombre; no se sobrescribe.'
            else:
                data = fetch(item['id'])
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('El contenido recibido no coincide con su huella.')
                folder.mkdir(parents=True, exist_ok=True)
                temporary = folder / f'.cs-{uuid.uuid4().hex[:12]}.part'
                with open(temporary, 'xb') as out:
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
                if _digest(temporary) != item['sha256']:
                    raise ValueError('Falló la verificación SHA-256 del archivo escrito.')
                final = folder / name
                os.rename(temporary, final)  # never replaces an existing file on Windows
                temporary = None
                state, why = 'Escrito', 'Copia verificada con SHA-256.'
        except FileExistsError:
            state, why = 'Duplicado', 'El nombre se creó durante el proceso; no se sobrescribe.'
        except (ValueError, OSError) as exc:
            state, why = 'Error', str(exc) if isinstance(exc, ValueError) else exc.__class__.__name__
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        key = {'Escrito': 'escritos', 'Duplicado': 'duplicados', 'Error': 'errores'}[state]
        result[key] += 1
        if state != 'Escrito' and len(result['detalle']) < MAX_DETAIL:
            result['detalle'].append({'name': str(item.get('name', '')), 'state': state, 'motivo': why})
        if progress:
            progress({'fase': 'escribiendo', 'total': len(files), 'hechas': n + 1})
    return result


class WriteProgress(CleanModel):
    agent_id: str = Field(max_length=80)
    fase: str = Field(pattern='^escribiendo$')
    total: int = Field(ge=0, le=5000)
    hechas: int = Field(ge=0, le=5000)


def writing_job(db, ident, agent_id, caller):
    job = db.get(Job, ident)
    if not job or job.kind != KIND or job.agent_id != agent_id or job.status != 'running':
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if caller is not None and (agent_id != caller.link.agent_id or job.requested_by != caller.link.user_id):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    return job


@router.get('/{ident}/cfdi/{item_id}')
def download_item(
    ident: str,
    item_id: str,
    agent_id: str = Query(..., max_length=80),
    db: Session = Depends(session),
    caller=Depends(agent_caller),
):
    """One accepted file for the running job: only those the user listed, still identical to what was reviewed."""
    from .models import OrganizadorItem
    from .organizador import folder as run_folder, input_source
    from .organizador_review import sha256_of

    job = writing_job(db, ident, agent_id, caller)
    if item_id not in {f['id'] for f in (job.payload or {}).get('files', [])}:
        raise HTTPException(404, 'Archivo no incluido en este trabajo.')
    item = db.get(OrganizadorItem, item_id)
    if not item or item.run_id != job.payload.get('run_id'):
        raise HTTPException(404, 'Archivo no encontrado.')
    if not (run_folder(item.run_id) / 'plan.json').exists():
        raise HTTPException(410, 'La entrada original ya no está disponible.')
    path = input_source(item.run_id) / item.rel_path
    if not path.is_file() or sha256_of(path) != item.sha256:
        raise HTTPException(410, 'El archivo original cambió o ya no está disponible.')
    return FileResponse(path, media_type='application/octet-stream')


@router.post('/{ident}/cfdi-progress')
def report_progress(ident: str, data: WriteProgress, db: Session = Depends(session), caller=Depends(agent_caller)):
    """Counters of a running write, shown to the user; the reply carries a cancellation request."""
    job = writing_job(db, ident, data.agent_id, caller)
    cancel = bool((job.result or {}).get('cancelar'))
    progress = data.model_dump(exclude={'agent_id'})
    job.result = {**claim_marker(), 'progreso': progress, **({'cancelar': True} if cancel else {})}
    db.commit()
    return {'ok': True, 'cancelar': cancel}
