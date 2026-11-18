"""Descarga de declaraciones del SAT por el agente local: recepción de los PDF que el agente descargó.

El agente abre un navegador en el equipo del usuario, que inicia sesión él mismo. Aquí sólo se reciben los PDF ya
descargados: se verifica que sean PDF y que coincidan con su SHA-256. No se guarda ninguna credencial ni sesión.
Los PDF quedan en un área de recepción por trabajo; crear el análisis de Declara a partir de ellos es un paso posterior.
"""

import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .agent_links import agent_caller
from .database import DATA, session
from .models import Job

KIND = 'sat_declaraciones'
ACTION = 'declara.usar'
MAX_PDF = 25 * 1024 * 1024
MAX_PDFS = 1000
SHA = re.compile(r'[0-9a-f]{64}')

router = APIRouter(prefix='/api/agent/jobs', tags=['Agente'])


def staging(job_id):
    return DATA / 'declara_sat' / job_id


def receiving_job(db, ident, agent_id, caller):
    """The running SAT job this agent holds, checked like the other agent calls."""
    job = db.get(Job, ident)
    if not job or job.kind != KIND or job.agent_id != agent_id or job.status != 'running':
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if caller is not None and (agent_id != caller.link.agent_id or job.requested_by != caller.link.user_id):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    return job


@router.put('/{ident}/sat/{sha}')
async def receive_pdf(
    ident: str,
    sha: str,
    request: Request,
    agent_id: str = Query(..., max_length=80),
    db: Session = Depends(session),
    caller=Depends(agent_caller),
):
    """One downloaded PDF, named by its SHA-256. Stored only if it is a PDF and hashes to that name."""
    job = receiving_job(db, ident, agent_id, caller)
    if not SHA.fullmatch(sha):
        raise HTTPException(422, 'Huella inválida.')
    if int(request.headers.get('content-length') or 0) > MAX_PDF:
        raise HTTPException(413, 'El PDF es demasiado grande.')
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_PDF:
            raise HTTPException(413, 'El PDF es demasiado grande.')
    if not body.startswith(b'%PDF-'):
        raise HTTPException(422, 'El archivo no es un PDF.')
    if hashlib.sha256(body).hexdigest() != sha:
        raise HTTPException(422, 'El contenido no coincide con su huella.')
    folder = staging(job.id)
    target = folder / (sha + '.pdf')
    if target.exists():
        return {'ok': True, 'new': False}
    folder.mkdir(parents=True, exist_ok=True)
    if sum(1 for _ in folder.glob('*.pdf')) >= MAX_PDFS:
        raise HTTPException(413, 'Se alcanzó el máximo de PDF por descarga.')
    pending = Path(str(target) + '.part')
    pending.write_bytes(bytes(body))
    pending.replace(target)
    return {'ok': True, 'new': True}
