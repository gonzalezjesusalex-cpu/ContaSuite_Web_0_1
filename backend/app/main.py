import json

import os

import re


from contextlib import asynccontextmanager

from datetime import date, datetime, timezone, timedelta

from pathlib import Path

from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Request


from fastapi.responses import FileResponse

from fastapi.staticfiles import StaticFiles

from fastapi.exceptions import RequestValidationError

from fastapi.responses import JSONResponse

from sqlalchemy import select, update, func

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session

from .database import engine, session, DATA, ROOT, SessionLocal

from .models import Company, Task, Obligation, Document, Audit, Agent, Job, UserAccount, UserCompanyGrant
from .csf_extract import ocr_available
from .agent_links import agent_caller

from .agent_jobs import claim_marker, expire_stale_jobs, renew_claim
from .job_views import KINDS as JOB_KINDS, job_row, without_workers

from .schemas import BlobCommit, BlobHashes, CompanyIn, TaskIn, ObligationIn, Heartbeat, IndexBatch, JobIn, JobResult


from .security import auth, admin_auth, Principal


def regime_labels(db, company_id):
    from .models import CompanyRegime

    rows = db.scalars(
        select(CompanyRegime).where(CompanyRegime.company_id == company_id).order_by(CompanyRegime.position)
    )
    return [r.label for r in rows]


def store_regimes(db, company_id, regimes):
    """Replace the company's current regimes (Bloque 1); the first one is the main regime."""
    from sqlalchemy import delete as sql_delete

    from .models import CompanyRegime

    db.execute(sql_delete(CompanyRegime).where(CompanyRegime.company_id == company_id))
    db.flush()
    for position, r in enumerate(regimes):
        db.add(CompanyRegime(company_id=company_id, position=position, **r.model_dump()))


def regimes_by_company(db, ids):
    from .models import CompanyRegime

    out = {}
    if ids:
        rows = db.scalars(
            select(CompanyRegime).where(CompanyRegime.company_id.in_(ids)).order_by(CompanyRegime.position)
        )
        for r in rows:
            out.setdefault(r.company_id, []).append(
                {'code': r.code, 'label': r.label, 'start_date': r.start_date, 'end_date': r.end_date}
            )
    return out


def responsibles(db, companies):
    ids = sorted({c.accountant_id for c in companies if c.accountant_id})
    if not ids:
        return []
    users = db.scalars(select(UserAccount).where(UserAccount.id.in_(ids)).order_by(UserAccount.display_name))
    return [{'id': u.id, 'display_name': u.display_name, 'enabled': u.enabled} for u in users]


def record(db, action, company_id=None, actor=None, changes=None):
    db.add(Audit(action=action, company_id=company_id, actor_id=actor, changes=changes or None))


def diff(before, after, hidden=('folder',)):
    """{field: {'before', 'after'}} for changed values; hidden fields only record that they changed."""
    out = {}
    for key, value in after.items():
        old = before.get(key)
        if old != value:
            out[key] = {'changed': True} if key in hidden else {'before': jsonable(old), 'after': jsonable(value)}
    return out


def jsonable(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def get(db, model, id):
    item = db.get(model, id)

    if not item:
        raise HTTPException(404, 'Registro no encontrado')

    return item


def save(db):
    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(409, 'El RFC ya está registrado o la relación es inválida') from None


def online(agent):
    last = agent.last_seen

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) - last < timedelta(seconds=120)


@asynccontextmanager
async def lifespan(app):
    from .schema_compatibility import assert_schema

    assert_schema(engine)

    from .agent_jobs import timeout_minutes

    timeout_minutes()  # an invalid CS_AGENT_JOB_TIMEOUT_MINUTES stops startup instead of failing requests

    from .models import RecopilaRun, OrganizadorRun, DeclaraRun

    with SessionLocal() as recovery_db:
        recovery_db.execute(
            update(RecopilaRun)
            .where(RecopilaRun.status.in_(['analyzing', 'generating']))
            .values(
                status='error',
                message='El servidor se reinició durante el proceso. Vuelve a cargar la entrada o a generar los archivos.',
            )
        )

        recovery_db.execute(
            update(OrganizadorRun)
            .where(OrganizadorRun.status.in_(['analyzing', 'generating']))
            .values(
                status='error',
                message='El servidor se reinició durante el proceso. Carga nuevamente la entrada; los originales de tu equipo se conservan.',
            )
        )

        recovery_db.execute(
            update(DeclaraRun)
            .where(DeclaraRun.status.in_(['analyzing', 'generating', 'editing']))
            .values(
                status='error',
                message='El servidor se reinició durante Declara. Carga nuevamente los PDF; los originales se conservan.',
            )
        )

        recovery_db.commit()

    (DATA / 'documents').mkdir(parents=True, exist_ok=True)

    yield


app = FastAPI(title='ContaSuite Web', version='1.0.0-rc.1', lifespan=lifespan)

if os.environ.get('CS_ALLOWED_HOSTS'):
    import json

    from starlette.middleware.trustedhost import TrustedHostMiddleware

    hosts = json.loads(os.environ['CS_ALLOWED_HOSTS'])

    if (
        not isinstance(hosts, list)
        or not hosts
        or any(not isinstance(h, str) or '*' in h or '/' in h or not h for h in hosts)
    ):
        raise RuntimeError('CS_ALLOWED_HOSTS must contain explicit hostnames')

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts, www_redirect=False)

APP = [Depends(auth)]

ADMIN = [Depends(admin_auth)]


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, exc):
    # Pydantic's default response includes raw inputs, including submitted passwords.

    return JSONResponse(
        status_code=422,
        content={'detail': [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]},
    )


READ_METHODS = {'GET', 'HEAD', 'OPTIONS'}

# Successful reads that hand out content or the audit log stay audited; other successful reads
# (state polling, lists, dashboards) are not, so security_events does not grow with every poll.
AUDITED_READ = re.compile(r'/(download|content|file|pdf|zip|audit)(/|$)')


def should_audit(method, template, status_code):
    if method not in READ_METHODS or status_code >= 400:
        return True
    return bool(AUDITED_READ.search(template))


# The compiled frontend only loads its own scripts, styles, fonts and icons. Previews embed same-origin
# /api content or blob: URLs in iframes, so /api responses may be framed by this origin only.
CONTENT_SECURITY_POLICY = '; '.join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        # Bloque 4: the page hands the pairing code to the agent on this computer (agent/agent.py).
        "connect-src 'self' http://127.0.0.1:47865",
        "frame-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
PAGE_HEADERS = {
    'Content-Security-Policy': CONTENT_SECURITY_POLICY,
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'X-Content-Type-Options': 'nosniff',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}
API_HEADERS = {
    'Referrer-Policy': 'same-origin',
    'X-Frame-Options': 'SAMEORIGIN',
}


def apply_security_headers(path, response):
    for name, value in (API_HEADERS if path.startswith('/api/') else PAGE_HEADERS).items():
        response.headers[name] = value


@app.middleware('http')
async def security_audit(request, call_next):
    try:
        response = await call_next(request)

    except Exception:
        if request.url.path.startswith('/api/'):
            from .security import audit

            principal = getattr(request.state, 'principal', None)

            route = request.scope.get('route')

            audit(
                principal.subject if principal else 'anonymous',
                request.method + ' ' + getattr(route, 'path', 'unknown'),
                'error',
                '500',
            )

        raise

    apply_security_headers(request.url.path, response)

    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'private, no-store'

        response.headers['X-Content-Type-Options'] = 'nosniff'

        route = request.scope.get('route')

        template = getattr(route, 'path', 'unknown')

        if request.url.path != '/api/health' and should_audit(request.method, template, response.status_code):
            from .security import audit

            principal = getattr(request.state, 'principal', None)

            audit(
                principal.subject
                if principal
                else 'agent_transport'
                if getattr(request.state, 'agent_authenticated', False)
                else 'anonymous',
                request.method + ' ' + template,
                'success'
                if response.status_code < 400
                else 'denied'
                if response.status_code in {401, 403, 404}
                else 'error',
                str(response.status_code),
            )

    return response


@app.get('/api/health')
def health():
    return {'version': '1.0.0-rc.1', 'status': 'ok'}


def vault_access_for(db, principal):
    """Whether the password manager appears in the menu (administrators and people with a vault key)."""
    from .credential_api import vault_member

    return vault_member(db, principal)


@app.get('/api/state', dependencies=APP)
def state(db: Session = Depends(session), principal: Principal = Depends(auth)):
    if principal.admin:
        expire_stale_jobs(db)  # jobs are only shown to administrators

    agents = db.scalars(select(Agent)).all() if principal.admin else []

    from .storage.router import storage_service

    actor = principal.storage_actor()

    companies = db.scalars(
        select(Company).where(True if principal.admin else Company.id.in_(principal.company_ids)).order_by(Company.name)
    ).all()

    from .company_lifecycle import archive_metadata, normalize_rfc

    archive_available, archive_rows = archive_metadata(db, [c.id for c in companies])

    normalized = [normalize_rfc(c.rfc) for c in companies]

    regimes = regimes_by_company(db, [c.id for c in companies])
    from .agent_links import my_agent

    agent_status = my_agent(db, principal)
    db.commit()

    def company_public(c):
        return {
            **{
                column.name: ('' if column.name == 'folder' and not principal.admin else getattr(c, column.name))
                for column in Company.__table__.columns
            },
            'archived': archive_rows.get(c.id, {}).get('archived', False) if archive_available else None,
            'archive_revision': archive_rows.get(c.id, {}).get('revision', 0),
            'duplicate_rfc': normalized.count(normalize_rfc(c.rfc)) > 1,
            'regimes': regimes.get(c.id, []),
        }

    # Counts only: the document list is served paginated by the Document Center, never by this polled endpoint.
    document_counts, document_total = {}, 0
    for company_id, count in db.execute(
        select(Document.company_id, func.count()).where(storage_service()._scope(actor)).group_by(Document.company_id)
    ):
        document_total += count
        if company_id is not None and (principal.admin or company_id in principal.company_ids):
            document_counts[company_id] = count

    return {
        'companies': [company_public(c) for c in companies],
        # Responsible users of the visible companies, so the client can show "(inactivo)".
        'responsibles': responsibles(db, companies),
        'current_user': principal.public(),
        # Renovación del gestor (fase 2): administrators and authorized people see the password manager.
        'vault_access': vault_access_for(db, principal),
        # Bloque 4: the user's own linked agent, or why there is none.
        'agent_link': agent_status,
        'archive_available': archive_available,
        'tasks': db.scalars(
            select(Task)
            .where(True if principal.admin else Task.company_id.in_(principal.company_ids))
            .order_by(Task.due_date)
        ).all(),
        'obligations': db.scalars(
            select(Obligation)
            .where(True if principal.admin else Obligation.company_id.in_(principal.company_ids))
            .order_by(Obligation.due_date)
        ).all(),
        'document_counts': document_counts,
        'document_total': document_total,
        'audit': db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all()
        if principal.admin
        else [],
        'agents': [
            {'id': a.id, 'online': online(a), 'capabilities': a.capabilities, 'last_seen': a.last_seen} for a in agents
        ],
        # Bloque 4: users see the analyses of their companies (administrators, all of them). The payload carries
        # the folder path, which only administrators see, like the company folder above. Their `result` is only a
        # small summary: the full result of a company's latest job comes from /api/companies/{id}/jobs/latest.
        'jobs': [
            job_row(j, principal)
            for j in db.scalars(
                select(Job)
                .where(True if principal.admin else Job.company_id.in_(principal.company_ids))
                .order_by(Job.created_at.desc())
                .limit(50)
            )
        ],
        'database': 'PostgreSQL' if engine.dialect.name == 'postgresql' else 'SQLite (modo de prueba)',
        # OCR: local reading of scanned constancias (Bloque 1), only when the engine is installed.
        'integrations': {'sat': False, 'ocr': ocr_available(), 'printing': False},
    }


def responsible_unchanged(principal, data, current='Sin asignar'):
    # Only an administrator assigns or changes the responsible accountant (Bloque 2).
    if not principal.admin and data.accountant != current:
        raise HTTPException(403, 'Sólo la administración asigna el contador responsable.')


@app.post('/api/companies', dependencies=APP, status_code=201)
def create_company(data: CompanyIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    if principal.role not in {'admin', 'contador'}:
        raise HTTPException(403, 'Tu perfil no permite registrar empresas.')
    responsible_unchanged(principal, data)
    from .company_lifecycle import ensure_unique_rfc

    ensure_unique_rfc(db, data.rfc)

    company = Company(**data.model_dump(exclude={'regimes'}))
    db.add(company)

    # Commit first validates RFC uniqueness; record creation in same transaction.

    company.id = str(uuid4())
    if principal.role == 'contador':
        # The registering accountant can operate it at once; it does not become its responsible.
        db.add(UserCompanyGrant(user_id=principal.subject, company_id=company.id, access='write'))
    store_regimes(db, company.id, data.regimes or [])
    record(db, 'Empresa registrada', company.id, principal.subject)
    save(db)

    return company


@app.put('/api/companies/{id}', dependencies=APP)
def edit_company(id: str, data: CompanyIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require('empresa.editar', id)
    company = get(db, Company, id)
    responsible_unchanged(principal, data, company.accountant)
    from .responsible import text_unchanged

    text_unchanged(company, data)

    from .company_lifecycle import ensure_unique_rfc

    ensure_unique_rfc(db, data.rfc, id)

    values = data.model_dump(exclude={'regimes'})
    changes = diff({k: getattr(company, k) for k in values}, values)
    for key, value in values.items():
        setattr(company, key, value)
    if data.regimes is not None:
        before = regime_labels(db, id)
        store_regimes(db, id, data.regimes)
        after = [r.label for r in data.regimes]
        if before != after:
            changes['regimes'] = {'before': before, 'after': after}

    record(db, 'Datos de empresa actualizados', id, principal.subject, changes)
    save(db)
    return company


@app.post('/api/companies/csf/analyze', dependencies=APP)
async def analyze_csf(
    file: UploadFile = File(...),
    company_id: str = Form(''),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    """Read a Constancia de Situación Fiscal and propose the form values (Bloque 1). Saves nothing.

    Registering needs the right to register companies; updating an existing company needs empresa.editar.
    """
    from starlette.concurrency import run_in_threadpool

    from .csf_extract import MAX_BYTES, CsfError, analyze

    if company_id:
        principal.require('empresa.editar', company_id)
    elif principal.role not in {'admin', 'contador'}:
        raise HTTPException(403, 'Tu perfil no permite registrar empresas.')
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    try:
        result = await run_in_threadpool(analyze, data)
    except CsfError as exc:
        raise HTTPException(422, str(exc)) from None
    rfc = result['fields'].get('rfc')
    if company_id and rfc != get(db, Company, company_id).rfc:
        # Updating a company only accepts its own constancia; nothing is merged across RFCs.
        raise HTTPException(422, 'La constancia no corresponde al RFC de esta empresa.')
    existing = db.scalar(select(Company).where(Company.rfc == rfc)) if rfc else None
    if existing and existing.id != company_id:
        # Never merged: the user is offered the existing company, or only told that it exists.
        visible = principal.admin or existing.id in principal.company_ids
        result['existing_company'] = {'id': existing.id, 'name': existing.name} if visible else {'id': None}
        result['warnings'].insert(0, 'Ya existe una empresa con este RFC. No se fusionará ni se creará otra.')
    result['suggested_obligations'] = obligation_suggestions(db, result['obligations'], company_id or None)
    result['csf_obligations'], result['unmatched_obligations'] = csf_obligation_proposals(
        db, result['obligations'], company_id or None
    )
    return result


def csf_obligation_proposals(db, obligations, company_id):
    """Plan v1.1 (Cambio 2): CSF obligations matched to the catalog with their dates, and those not found."""
    from .csf_extract import propose_csf_obligations
    from .fiscal_control import applicability, catalog, metadata
    from .schema_cache import tables_ready

    if not obligations or not tables_ready(db, metadata):
        return [], []
    entries = [dict(r) for r in db.execute(select(catalog).where(catalog.c.group_name.is_not(None))).mappings()]
    current = {}
    if company_id:
        for r in db.execute(select(applicability).where(applicability.c.company_id == company_id)).mappings():
            current[r['obligation_id']] = (r['applicable'], r['revision'])
    return propose_csf_obligations(obligations, entries, current)


def obligation_suggestions(db, obligations, company_id):
    """Obligations catalog entries pointed to by the constancia (Bloque 1); empty if the module is off."""
    from .csf_extract import suggest_obligations
    from .fiscal_control import applicability, catalog, metadata
    from .schema_cache import tables_ready

    if not obligations or not tables_ready(db, metadata):
        return []
    rows = db.execute(select(catalog.c.id, catalog.c.label)).all()
    current = {}
    if company_id:
        for r in db.execute(select(applicability).where(applicability.c.company_id == company_id)).mappings():
            current[r['obligation_id']] = (r['applicable'], r['revision'])
    return suggest_obligations(obligations, rows, current)


@app.post('/api/companies/{id}/csf/attach', dependencies=APP, status_code=201)
async def attach_csf(
    id: str,
    file: UploadFile = File(...),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    """Attach the constancia to the company file: only its own pages, never the rest of the PDF (Bloque 1).

    The server finds the pages again instead of trusting the client, and refuses a constancia of another RFC.
    """
    import io

    from starlette.concurrency import run_in_threadpool

    from .csf_extract import MAX_BYTES, CsfError, analyze, csf_pages_pdf
    from .storage.providers import StorageError
    from .storage.router import storage_http_error, storage_service

    principal.require('documentos.subir', id)
    company = get(db, Company, id)
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    try:
        result = await run_in_threadpool(analyze, data)
        if result['fields'].get('rfc') != company.rfc:
            raise CsfError('La constancia no corresponde al RFC de esta empresa.')
        only_csf = csf_pages_pdf(data, result['pages'])
    except CsfError as exc:
        raise HTTPException(422, str(exc)) from None
    issued = result['fields'].get('csf_issued_on')
    name = 'CSF_' + company.rfc + ('_' + issued.isoformat() if issued else '') + '.pdf'
    try:
        document = await run_in_threadpool(
            storage_service().upload,
            principal.storage_actor(),
            io.BytesIO(only_csf),
            name,
            company_id=id,
            category='Constancia de Situación Fiscal',
            document_type='other',
            period=issued.strftime('%Y-%m') if issued else None,
        )
    except StorageError as exc:
        raise storage_http_error(exc) from None
    if issued and (company.csf_issued_on is None or issued > company.csf_issued_on):
        company.csf_issued_on = issued
    record(db, 'Constancia de Situación Fiscal adjuntada', id, principal.subject, {'pages': len(result['pages'])})
    save(db)
    return document


@app.get('/api/sat/regimes', dependencies=APP)
def sat_regimes():
    """SAT regime catalog (c_RegimenFiscal) for the company form (Bloque 1)."""
    from .sat_regimes import catalog

    return catalog()


@app.get('/api/companies/{id}/history', dependencies=APP)
def company_history(
    id: str,
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
    limit: int = Query(200, ge=1, le=500),
):
    """The company's change history (Bloque 2): who, when, what, and previous and new values."""
    principal.require('historial.ver', id)
    get(db, Company, id)
    rows = db.scalars(
        select(Audit).where(Audit.company_id == id).order_by(Audit.created_at.desc(), Audit.id).limit(limit)
    ).all()
    ids = {r.actor_id for r in rows if r.actor_id and not r.actor_id.startswith('agent:')}
    names = {u.id: u for u in db.scalars(select(UserAccount).where(UserAccount.id.in_(sorted(ids))))} if ids else {}

    def actor(ident):
        if not ident:
            return 'Sistema o registro anterior'
        if ident.startswith('agent:'):
            return 'Agente ' + ident[6:]
        user = names.get(ident)
        if user is None:
            return 'Cuenta eliminada'
        return user.display_name + ('' if user.enabled else ' (inactivo)')

    return [
        {
            'id': r.id,
            'action': r.action,
            'created_at': r.created_at,
            'actor_id': r.actor_id,
            'actor': actor(r.actor_id),
            'changes': r.changes or {},
        }
        for r in rows
    ]


@app.post('/api/tasks', dependencies=APP, status_code=201)
def create_task(data: TaskIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require('tareas.editar', data.company_id)

    get(db, Company, data.company_id)

    task = Task(**data.model_dump())
    db.add(task)
    record(db, 'Tarea creada: ' + data.title, data.company_id, principal.subject)
    save(db)
    return task


@app.put('/api/tasks/{id}', dependencies=APP)
def edit_task(id: str, data: TaskIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require('tareas.editar', data.company_id)

    task = get(db, Task, id)
    get(db, Company, data.company_id)

    principal.require('tareas.editar', task.company_id)

    values = data.model_dump()
    changes = diff({k: getattr(task, k) for k in values}, values)
    for k, v in values.items():
        setattr(task, k, v)

    record(db, 'Tarea actualizada: ' + data.title, data.company_id, principal.subject, changes)
    save(db)
    return task


@app.post('/api/obligations', dependencies=APP, status_code=201)
def create_obligation(data: ObligationIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require('obligaciones.editar', data.company_id)

    get(db, Company, data.company_id)
    o = Obligation(**data.model_dump())
    db.add(o)

    record(db, 'Obligación registrada: ' + data.title, data.company_id, principal.subject)
    save(db)
    return o


@app.put('/api/obligations/{id}', dependencies=APP)
def edit_obligation(id: str, data: ObligationIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require('obligaciones.editar', data.company_id)

    o = get(db, Obligation, id)
    get(db, Company, data.company_id)

    principal.require('obligaciones.editar', o.company_id)

    values = data.model_dump()
    changes = diff({k: getattr(o, k) for k in values}, values)
    for k, v in values.items():
        setattr(o, k, v)

    record(db, 'Obligación actualizada: ' + data.title, data.company_id, principal.subject, changes)
    save(db)
    return o


@app.post('/api/companies/{id}/documents', dependencies=APP, status_code=201)
async def upload_document(
    id: str,
    file: UploadFile = File(...),
    category: str = Form('General'),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    principal.require('documentos.subir', id)

    get(db, Company, id)

    name = Path((file.filename or 'documento').replace('\\', '/')).name

    ext = Path(name).suffix.lower()

    if ext not in {'.pdf', '.xml', '.cer'}:
        raise HTTPException(422, 'Sólo PDF, XML y CER. Las llaves privadas permanecen en el equipo local.')

    if len(name) > 255 or len(category) > 80:
        raise HTTPException(422, 'Nombre o categoría demasiado largo')

    storage = str(uuid4()) + ext
    path = DATA / 'documents' / storage
    size = 0

    try:
        with path.open('wb') as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)

                if size > 25 * 1024 * 1024:
                    raise HTTPException(413, 'El máximo es 25 MB por archivo')

                out.write(chunk)

        if not size:
            raise HTTPException(422, 'El archivo está vacío')

        from .storage.internal import validate_payload

        from .storage.providers import StorageError

        try:
            with path.open('rb') as reader:
                validate_payload(reader, name, allow_public_cer=True)

        except StorageError:
            raise HTTPException(
                422,
                'El contenido no corresponde a PDF, XML o certificado público CER válido. No se admiten claves privadas.',
            ) from None

        doc = Document(
            company_id=id,
            name=name,
            category=category,
            size=size,
            storage_name=storage,
            classification_status='confirmed',
        )

        db.add(doc)
        record(db, 'Documento adjuntado: ' + name, id, principal.subject)
        save(db)

        return (
            doc
            if principal.admin
            else {
                'id': doc.id,
                'company_id': doc.company_id,
                'name': doc.name,
                'category': doc.category,
                'size': doc.size,
                'created_at': doc.created_at,
            }
        )

    except Exception:
        path.unlink(missing_ok=True)
        raise

    finally:
        await file.close()


@app.get('/api/documents/{id}/download', dependencies=APP)
def download_document(id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    from .storage.router import storage_service, document_response

    return document_response(storage_service(), principal.storage_actor(), id)


@app.delete('/api/documents/{id}', dependencies=APP, status_code=204)
def delete_document(id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    doc = get(db, Document, id)
    if doc.company_id is None:
        principal.require_admin()
    else:
        principal.require('documentos.eliminar', doc.company_id)

    from .models import DocumentVersion

    if doc.managed or db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id == id).limit(1)):
        raise HTTPException(
            409, 'El documento tiene historial de almacenamiento. Se conserva hasta habilitar su gestión documental.'
        )

    path = DATA / 'documents' / doc.storage_name

    record(db, 'Documento eliminado: ' + doc.name, doc.company_id, principal.subject)
    db.delete(doc)
    save(db)
    path.unlink(missing_ok=True)


def job_action(kind):
    """The permission a job needs, by kind: exporting and downloading from the SAT are their own permissions."""
    if kind in ('export_virtual', 'write_cfdi'):
        return 'carpeta.exportar'
    return 'declara.usar' if kind in ('sat_declaraciones', 'declara_carpeta') else 'carpeta.analizar'


@app.post('/api/jobs', dependencies=APP, status_code=201)
def create_job(data: JobIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Folder analysis through the requesting user's own linked agent (Bloque 4)."""
    from .agent_links import active_link_for, inside_roots, online as link_online, roots, shared_token_allowed

    exporting = data.kind == 'export_virtual'
    downloading = data.kind == 'sat_declaraciones'
    # Writing a copy to the person's computer is its own permission: it is never part of a template.
    principal.require(job_action(data.kind), data.company_id)
    if data.copy:
        # Storing a copy of the content inside ContaSuite is an upload: it needs that permission too.
        principal.require('documentos.subir', data.company_id)
        from .export_plan import SECTIONS as COPY_SECTIONS

        if not set(data.copy) <= set(COPY_SECTIONS):
            raise HTTPException(422, 'Hay secciones desconocidas en la copia.')
    company = get(db, Company, data.company_id)
    expire_stale_jobs(db)
    if not downloading and not company.folder:
        raise HTTPException(422, 'La empresa no tiene ruta de carpeta: agrégala en Editar › Expediente digital.')
    allowed = roots(db)
    if exporting:
        from .export_plan import REASONS as EXPORT_REASONS, SECTIONS, destination_problem

        problem = destination_problem(data.destination, company.folder, allowed)
        if problem:
            raise HTTPException(422, EXPORT_REASONS[problem])
        if data.include is not None and not set(data.include) <= set(SECTIONS):
            raise HTTPException(422, 'Hay secciones desconocidas en la exportación.')
    link = active_link_for(db, principal.subject)
    if (
        link is None
        and data.agent_id
        and principal.admin
        and shared_token_allowed()
        and not exporting
        and not downloading
    ):
        # Transition only: an agent with the former shared token, chosen by an administrator.
        agent = get(db, Agent, data.agent_id)
        if not online(agent) or data.kind not in agent.capabilities:
            raise HTTPException(409, 'El agente está desconectado o no tiene esta capacidad.')
        agent_id, link_id, machine = agent.id, None, None
    else:
        if link is None:
            db.commit()
            raise HTTPException(
                409, 'Tu agente local no está vinculado: inicia sesión en ContaSuite en el equipo Windows.'
            )
        if not link_online(link):
            raise HTTPException(
                409,
                'Tu agente local está desconectado: revisa que esté en ejecución en '
                + (link.machine or 'el equipo')
                + '.',
            )
        if not downloading and not allowed:
            raise HTTPException(409, 'No hay carpetas autorizadas para el agente: las define la administración.')
        if not downloading and not inside_roots(company.folder, allowed):
            raise HTTPException(409, 'La ruta de la empresa está fuera de las carpetas autorizadas para el agente.')
        agent_id, link_id, machine = link.agent_id, link.id, link.machine
    # The browser of a SAT download needs no company folder: the portal address comes from the agent's own setup.
    payload = (
        {'rfc': company.rfc, 'ejercicio': data.ejercicio}
        if downloading
        else {'folder': company.folder, 'rfc': company.rfc}
    )
    if exporting:
        payload.update(destination=data.destination, apply=data.apply, include=data.include)
    elif data.copy:
        payload['copy'] = data.copy
    job = Job(
        company_id=company.id,
        agent_id=agent_id,
        kind=data.kind,
        payload=payload,
        requested_by=principal.subject,
        link_id=link_id,
        machine=machine,
    )
    db.add(job)
    record(
        db,
        ('Exportación ordenada solicitada (' + ('copia' if data.apply else 'vista previa') + ')')
        if exporting
        else 'Descarga de declaraciones solicitada'
        if downloading
        else 'Análisis de carpeta solicitado' + (' con copia interna' if data.copy else ''),
        company.id,
        principal.subject,
        {'agente': {'after': agent_id}, 'equipo': {'after': machine}} if link_id else None,
    )
    save(db)
    return job


@app.get('/api/companies/{company_id}/jobs/latest', dependencies=APP)
def latest_job(
    company_id: str,
    kind: str = Query(..., max_length=30),
    status: str | None = Query(None, max_length=12),
    db: Session = Depends(session),
    principal: Principal = Depends(auth),
):
    """The company's latest job of one kind WITH its full result (null when there is none).

    With `status` (queued, running, completed or failed) it is the latest one in that status.

    Same visibility as the jobs of /api/state: the company must be visible to the user.
    """
    principal.require_company(company_id)
    if kind not in JOB_KINDS:
        raise HTTPException(422, 'Tipo de trabajo desconocido.')
    if status is not None and status not in {'queued', 'running', 'completed', 'failed'}:
        raise HTTPException(422, 'Estado de trabajo desconocido.')
    if principal.admin:
        expire_stale_jobs(db)
    query = select(Job).where(Job.company_id == company_id, Job.kind == kind)
    if status:
        query = query.where(Job.status == status)
    job = db.scalar(query.order_by(Job.created_at.desc()).limit(1))
    if job is None:
        return None
    result = job.result if isinstance(job.result, dict) else {}
    if not principal.can('trabajadores.ver', company_id):
        result = without_workers(result)  # personal data of workers needs its own action
    return job_row(job, principal, result)


@app.post('/api/jobs/{id}/cancel', dependencies=APP)
def cancel_job(id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    """Stop a SAT download. Queued: ends now. Running: flagged, and the agent stops at its next report, keeping the
    PDFs it already delivered."""
    job = db.get(Job, id)
    if (
        not job
        or job.kind not in ('sat_declaraciones', 'write_cfdi')
        or not (principal.admin or job.requested_by == principal.subject)
    ):
        raise HTTPException(404, 'Descarga no encontrada')
    principal.require(job_action(job.kind), job.company_id)
    if job.status == 'queued':
        changed = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == 'queued')
            .values(status='failed', result={'error': 'La descarga se canceló.', 'error_code': 'sat_cancelado'})
        )
        if not changed.rowcount:
            db.rollback()
            raise HTTPException(409, 'La descarga ya empezó: vuelve a intentar cancelarla.')
    elif job.status == 'running':
        job.result = {**(job.result or {}), 'cancelar': True}
    else:
        raise HTTPException(409, 'La descarga ya terminó.')
    record(db, 'Descarga de declaraciones: cancelación solicitada', job.company_id, principal.subject)
    save(db)
    return {'ok': True, 'estado': 'cancelando' if job.status == 'running' else 'cancelada'}


@app.post('/api/agent/heartbeat')
def heartbeat(data: Heartbeat, db: Session = Depends(session), caller=Depends(agent_caller)):
    from .agent_links import end_link, roots

    if caller is not None and data.id != caller.link.agent_id:
        raise HTTPException(403, 'El agente no corresponde a su vínculo.')
    agent = db.get(Agent, data.id)
    if not agent:
        agent = Agent(id=data.id)
        db.add(agent)
    agent.last_seen = datetime.now(timezone.utc)
    agent.capabilities = data.capabilities
    renew_claim(db, data.job_id, data.id, caller.link.user_id if caller is not None else None)
    if caller is None:
        save(db)
        return {'ok': True}
    caller.link.last_seen = datetime.now(timezone.utc)
    if caller.link.restart_requested:
        end_link(db, caller.link, 'Reinicio solicitado por la administración.')
        save(db)
        return {'ok': True, 'restart': True}
    save(db)
    return {'ok': True, 'user': caller.user.display_name, 'roots': roots(db)}


@app.post('/api/agent/{agent_id}/claim')
def claim(
    agent_id: str,
    db: Session = Depends(session),
    caller=Depends(agent_caller),
    not_before: datetime | None = Query(None),
):
    from .agent_links import roots, user_can_analyze

    get(db, Agent, agent_id)
    if caller is not None and agent_id != caller.link.agent_id:
        raise HTTPException(403, 'El agente no corresponde a su vínculo.')
    # Atomic compare-and-swap prevents duplicate claims on both supported databases.
    if not_before is not None and (not_before.tzinfo is None or not_before > datetime.now(timezone.utc)):
        raise HTTPException(422, 'Fecha de activación inválida.')
    query = select(Job).where(Job.agent_id == agent_id, Job.status == 'queued')
    if caller is not None:
        # A linked agent only works for its user, and only while that user may still analyze the company.
        query = query.where(Job.requested_by == caller.link.user_id)
    if not_before is not None:
        query = query.where(Job.created_at >= not_before)
    expire_stale_jobs(db)
    for job in db.scalars(query.order_by(Job.created_at).limit(50)).all():
        if caller is not None and not (
            user_can_analyze(
                db,
                caller.user,
                job.company_id,
                job_action(job.kind),
            )
            and (
                not (job.payload or {}).get('copy')
                or user_can_analyze(db, caller.user, job.company_id, 'documentos.subir')
            )
        ):
            db.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == 'queued')
                .values(status='failed', result={'error': 'El usuario ya no tiene permiso para analizar esta empresa.'})
            )
            db.commit()
            continue
        marker = claim_marker()
        changed = db.execute(
            update(Job).where(Job.id == job.id, Job.status == 'queued').values(status='running', result=marker)
        )
        db.commit()
        if changed.rowcount:
            db.refresh(job)
            if caller is not None:
                # The folders the administrator authorizes travel with each job; the agent cannot widen them.
                return {
                    **{c.name: getattr(job, c.name) for c in Job.__table__.columns},
                    'payload': {**job.payload, 'roots': roots(db)},
                }
            return job
    return None


def audit_text(kind, status):
    """History line for a job the agent finished."""
    done = status == 'completed'
    if kind == 'export_virtual':
        return 'Exportación ordenada ' + ('completada' if done else 'fallida')
    if kind == 'sat_declaraciones':
        return 'Descarga de declaraciones ' + ('completada' if done else 'fallida')
    if kind == 'write_cfdi':
        return 'Escritura de CFDI en la carpeta de la empresa ' + ('completada' if done else 'fallida')
    if kind == 'declara_carpeta':
        return 'Declara en carpeta: operación del agente ' + ('completada' if done else 'fallida')
    return 'Análisis local ' + ('completado' if done else 'fallido')


@app.post('/api/agent/jobs/{id}/index')
def index_batch(id: str, data: IndexBatch, db: Session = Depends(session), caller=Depends(agent_caller)):
    """A slice of a folder scan for the persistent virtual index. Sent while the job is still running."""
    from .virtual_index import ingest_batch

    job = get(db, Job, id)
    if job.agent_id != data.agent_id or job.status != 'running' or job.kind != 'scan_folder':
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if caller is not None and (data.agent_id != caller.link.agent_id or job.requested_by != caller.link.user_id):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    scan = ingest_batch(db, job, data)
    if data.last:
        record(
            db,
            'Índice virtual actualizado'
            + (
                f': {scan.added} nuevos, {scan.changed} cambiados, {scan.moved} movidos, {scan.restored} restaurados, '
                f'{scan.missing} ya no están'
                if scan.complete
                else ' (recorrido incompleto: no se comparó lo que falta)'
            ),
            job.company_id,
            job.requested_by or 'agent:' + job.agent_id,
        )
    save(db)
    return {'ok': True, 'scan_id': scan.id, 'total': scan.total}


def copy_job(db, id, agent_id, caller):
    """The running analysis that asked for an internal copy, checked like the other agent calls."""
    job = get(db, Job, id)
    if (
        job.agent_id != agent_id
        or job.status != 'running'
        or job.kind != 'scan_folder'
        or not (job.payload or {}).get('copy')
    ):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if caller is not None and (agent_id != caller.link.agent_id or job.requested_by != caller.link.user_id):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    return job


@app.post('/api/agent/jobs/{id}/blobs/missing')
def blobs_missing(id: str, data: BlobHashes, db: Session = Depends(session), caller=Depends(agent_caller)):
    """Which of these contents the server does not have yet (the agent uploads only those)."""
    from . import virtual_blobs

    copy_job(db, id, data.agent_id, caller)
    return {'missing': virtual_blobs.missing(data.hashes)}


@app.put('/api/agent/jobs/{id}/blobs/{sha}')
async def blob_put(
    id: str,
    sha: str,
    request: Request,
    agent_id: str = Query(..., max_length=80),
    db: Session = Depends(session),
    caller=Depends(agent_caller),
):
    """The bytes of one file, named by its SHA-256. Stored only if they hash to that name."""
    from . import virtual_blobs

    copy_job(db, id, agent_id, caller)
    if not virtual_blobs.SHA.fullmatch(sha):
        raise HTTPException(422, 'Huella inválida.')
    if int(request.headers.get('content-length') or 0) > virtual_blobs.MAX_BLOB:
        raise HTTPException(413, 'Archivo demasiado grande para la copia interna.')
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > virtual_blobs.MAX_BLOB:
            raise HTTPException(413, 'Archivo demasiado grande para la copia interna.')
    try:
        created = virtual_blobs.store(sha, bytes(body))
    except virtual_blobs.BlobError as exc:
        raise HTTPException(
            422,
            {
                'hash_mismatch': 'El contenido no coincide con su huella.',
                'protected_file': 'El archivo contiene una llave privada: no se copia.',
            }.get(exc.code, 'No se pudo guardar la copia.'),
        ) from None
    return {'ok': True, 'new': created}


@app.post('/api/agent/jobs/{id}/blobs/commit')
def blobs_commit(id: str, data: BlobCommit, db: Session = Depends(session), caller=Depends(agent_caller)):
    """Mark the files of this scan whose content now has its internal copy."""
    from .virtual_index import mark_copies

    job = copy_job(db, id, data.agent_id, caller)
    copied = mark_copies(db, job, data.sections)
    record(
        db,
        f'Copia interna guardada: {copied} archivos',
        job.company_id,
        job.requested_by or 'agent:' + job.agent_id,
    )
    save(db)
    return {'copied': copied}


@app.post('/api/agent/jobs/{id}/result')
def result(id: str, data: JobResult, db: Session = Depends(session), caller=Depends(agent_caller)):
    job = get(db, Job, id)
    if job.agent_id != data.agent_id or job.status != 'running':
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if caller is not None and (data.agent_id != caller.link.agent_id or job.requested_by != caller.link.user_id):
        raise HTTPException(409, 'Trabajo no asignado o ya finalizado')
    if len(json.dumps(data.result)) > 2_000_000:
        raise HTTPException(413, 'Resultado demasiado grande')
    job.status = data.status
    job.result = data.result
    record(
        db,
        audit_text(job.kind, data.status),
        job.company_id,
        job.requested_by or 'agent:' + job.agent_id,
        {'agente': {'after': job.agent_id}, 'equipo': {'after': job.machine}} if job.requested_by else None,
    )
    save(db)
    return {'ok': True}


def seed_examples(db):
    examples = [
        ('Distribuidora Bajío S.A. de C.V.', 'DBA180412KJ9', 'C.P. Mariana Rivas', 'León, GTO'),
        ('Soluciones Industriales Mexiquenses S.A.', 'SIM090822TR4', 'C.P. Alejandro Morales', 'Toluca, MEX'),
        ('Consultoría y Logística Integral S.A.S.', 'CLI210315AA2', 'C.P. Roberto Treviño', 'CDMX'),
    ]

    for i, (name, rfc, accountant, location) in enumerate(examples):
        company = Company(
            id=str(uuid4()),
            is_demo=True,
            name=name,
            rfc=rfc,
            accountant=accountant,
            location=location,
            notes='Datos ficticios de Stitch para probar la interfaz. Sin validación SAT.',
        )

        db.add(company)
        db.flush()

        db.add(
            Task(
                company_id=company.id,
                title=['Revisar expediente documental', 'Revisar acuses del periodo', 'Conciliar documentación'][i],
                due_date=date.today() + timedelta(days=[4, -2, 7][i]),
                responsible=company.accountant,
                priority=['Alta', 'Crítica', 'Media'][i],
            )
        )

        db.add(
            Obligation(
                company_id=company.id,
                title='Declaración mensual · DEMO',
                period=date.today().strftime('%Y-%m'),
                due_date=date.today() + timedelta(days=[8, -1, 10][i]),
                notes='Fecha de ejemplo, configurada manualmente.',
            )
        )

        record(db, 'Empresa de prueba creada', company.id)


@app.post('/api/demo', dependencies=ADMIN)
def demo(db: Session = Depends(session)):
    if db.scalar(select(Company.id).limit(1)):
        raise HTTPException(409, 'Los ejemplos sólo se cargan en una base vacía')

    seed_examples(db)
    save(db)
    return {'ok': True}


@app.delete('/api/companies/{id}', dependencies=ADMIN, status_code=204)
def delete_company(id: str, db: Session = Depends(session)):
    from .company_lifecycle import forbid_delete

    forbid_delete()


from .company_lifecycle import router as company_lifecycle_router

app.include_router(company_lifecycle_router)


from .receipts import router as receipts_router
from .run_access import CFDI, DECLARA, RECIBOS, RECOPILA

app.include_router(receipts_router, dependencies=[Depends(RECIBOS.dependency())])


from .recopila import router as recopila_router

app.include_router(recopila_router, dependencies=[Depends(RECOPILA.dependency())])


from .organizador import router as organizador_router

app.include_router(organizador_router, dependencies=[Depends(CFDI.dependency())])


from .declara import router as declara_router

app.include_router(declara_router, dependencies=[Depends(DECLARA.dependency())])

from .declara_folder_api import router as declara_folder_router, agent_router as declara_agent_router

app.include_router(declara_folder_router, dependencies=[Depends(DECLARA.dependency())])
app.include_router(declara_agent_router)


from .storage.router import router as storage_router

app.include_router(storage_router)


from .accounts import router as accounts_router

app.include_router(accounts_router)


from .responsible import router as responsible_router

app.include_router(responsible_router)


from .agent_links import router as agent_links_router

app.include_router(agent_links_router)


from .virtual_index import router as virtual_index_router

app.include_router(virtual_index_router)


from .sat_declaraciones import router as sat_declaraciones_router
from .cfdi_write import router as cfdi_write_router

app.include_router(sat_declaraciones_router)
app.include_router(cfdi_write_router)


from .fiscal_control import router as fiscal_control_router

app.include_router(fiscal_control_router)

from .obligation_checklist import router as obligation_checklist_router

app.include_router(obligation_checklist_router)

from .fiscal_import_api import router as fiscal_import_router

app.include_router(fiscal_import_router)


from .credential_api import router as credential_router

from . import credential_alerts  # noqa: F401 - registers local alert endpoints on the same router
from . import credential_vault  # noqa: F401 - plan v1.1 password manager endpoints on the same router
from . import vault_master  # noqa: F401 - master password, unlock and lock (renovación del gestor, fase 1)
from . import vault_fiel  # noqa: F401 - «Agregar FIEL o CSD» and the FIEL service for Declara (fase 3)
from . import vault_import  # noqa: F401 - import in three steps, template and export (fase 4)

app.include_router(credential_router)


@app.middleware('http')
async def credential_cache_policy(request, call_next):
    token = None
    if request.url.path.startswith('/api/credentials'):
        from .credential_api import CLIENT

        # Fase 2 of the password manager: the vault log records the computer each action came from.
        host = request.client.host if request.client else 'desconocido'
        agent = (request.headers.get('user-agent') or '')[:60]
        token = CLIENT.set(host + (' · ' + agent if agent else ''))
    try:
        response = await call_next(request)
    finally:
        if token is not None:
            CLIENT.reset(token)

    if request.url.path.startswith(('/api/credentials', '/api/pilot-imports', '/api/pilot-batches')):
        response.headers['Cache-Control'] = 'no-store, private'

        response.headers['Pragma'] = 'no-cache'

    return response


from .company_import_api import router as company_import_router

app.include_router(company_import_router)


from .pilot_import import router as pilot_import_router

app.include_router(pilot_import_router)
from .pilot_batch import router as pilot_batch_router

app.include_router(pilot_batch_router)


from .integral_api import router as integral_router

app.include_router(integral_router)

from .document_status import router as document_status_router

app.include_router(document_status_router)

from .cfdi_calendar import router as cfdi_calendar_router

app.include_router(cfdi_calendar_router)


DIST = ROOT / 'frontend' / 'dist'

if DIST.exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

    app.mount('/icons', StaticFiles(directory=DIST / 'icons'), name='icons')

    @app.get('/{path:path}', include_in_schema=False)
    def frontend(path: str):
        if path.startswith('api/') or path == 'api':
            raise HTTPException(404, 'Endpoint no encontrado')

        return FileResponse(DIST / 'index.html')
