import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, session, DATA, ROOT, SessionLocal
from .models import Company, Task, Obligation, Document, Audit, Agent, Job, Setting, Receipt
from .schemas import CompanyIn, TaskIn, ObligationIn, Heartbeat, JobIn, JobResult

from .security import auth, admin_auth, security, Principal

def agent_auth(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(security)):
    token = os.getenv('AGENT_TOKEN', '')
    if len(token) < 24 or not credentials or len(credentials.credentials) > 512 or not secrets.compare_digest(credentials.credentials.encode(), token.encode()):
        raise HTTPException(401, 'Agente no autorizado')
    request.state.agent_authenticated = True

def record(db, action, company_id=None):
    db.add(Audit(action=action, company_id=company_id))
def get(db, model, id):
    item = db.get(model, id)
    if not item: raise HTTPException(404, 'Registro no encontrado')
    return item

def save(db):
    try: db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'El RFC ya está registrado o la relación es inválida')

def online(agent):
    last = agent.last_seen
    if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < timedelta(seconds=120)

@asynccontextmanager
async def lifespan(app):
    from .schema_compatibility import assert_schema
    assert_schema(engine)
    from .models import RecopilaRun, OrganizadorRun, DeclaraRun
    with SessionLocal() as recovery_db:
        recovery_db.execute(update(RecopilaRun).where(RecopilaRun.status.in_(['analyzing','generating'])).values(status='error',message='El servidor se reinició durante el proceso. Vuelve a cargar la entrada o a generar los archivos.'))
        recovery_db.execute(update(OrganizadorRun).where(OrganizadorRun.status.in_(['analyzing','generating'])).values(status='error',message='El servidor se reinició durante el proceso. Carga nuevamente la entrada; los originales de tu equipo se conservan.'))
        recovery_db.execute(update(DeclaraRun).where(DeclaraRun.status.in_(['analyzing','generating','editing'])).values(status='error',message='El servidor se reinició durante Declara. Carga nuevamente los PDF; los originales se conservan.'))
        recovery_db.commit()
    (DATA/'documents').mkdir(parents=True,exist_ok=True)
    yield

app = FastAPI(title='ContaSuite Web', version='0.1.0', lifespan=lifespan)
if os.environ.get('CS_ALLOWED_HOSTS'):
    import json
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    hosts=json.loads(os.environ['CS_ALLOWED_HOSTS'])
    if not isinstance(hosts,list) or not hosts or any(not isinstance(h,str) or '*' in h or '/' in h or not h for h in hosts):raise RuntimeError('CS_ALLOWED_HOSTS must contain explicit hostnames')
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts,www_redirect=False)
APP = [Depends(auth)]
ADMIN = [Depends(admin_auth)]
AGENT = [Depends(agent_auth)]


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, exc):
    # Pydantic's default response includes raw inputs, including submitted passwords.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]})


@app.middleware('http')
async def security_audit(request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        if request.url.path.startswith('/api/'):
            from .security import audit
            principal = getattr(request.state, 'principal', None)
            route = request.scope.get('route')
            audit(principal.subject if principal else 'anonymous', request.method + ' ' + getattr(route, 'path', 'unknown'), 'error', '500')
        raise
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.url.path != '/api/health':
            from .security import audit
            principal = getattr(request.state, 'principal', None)
            route = request.scope.get('route')
            template = getattr(route, 'path', 'unknown')
            audit(principal.subject if principal else 'agent_transport' if getattr(request.state, 'agent_authenticated', False) else 'anonymous', request.method + ' ' + template,
                  'success' if response.status_code < 400 else 'denied' if response.status_code in {401,403,404} else 'error',
                  str(response.status_code))
    return response

@app.get('/api/health')
def health(): return {'version':'0.1.0','status':'ok'}

@app.get('/api/state', dependencies=APP)
def state(db: Session = Depends(session), principal: Principal = Depends(auth)):
    agents = db.scalars(select(Agent)).all() if principal.admin else []
    from .storage.router import storage_service
    actor = principal.storage_actor()
    companies = db.scalars(select(Company).where(True if principal.admin else Company.id.in_(principal.company_ids)).order_by(Company.name)).all()
    from .company_lifecycle import archive_metadata, normalize_rfc
    archive_available, archive_rows = archive_metadata(db, [c.id for c in companies])
    normalized = [normalize_rfc(c.rfc) for c in companies]
    def company_public(c):
        return {**{column.name: ('' if column.name == 'folder' and not principal.admin else getattr(c, column.name)) for column in Company.__table__.columns}, 'archived': archive_rows.get(c.id, {}).get('archived', False) if archive_available else None, 'archive_revision': archive_rows.get(c.id, {}).get('revision', 0), 'duplicate_rfc': normalized.count(normalize_rfc(c.rfc))>1}
    return { 'companies': [company_public(c) for c in companies],
             'current_user': principal.public(), 'archive_available': archive_available,
             'tasks': db.scalars(select(Task).where(True if principal.admin else Task.company_id.in_(principal.company_ids)).order_by(Task.due_date)).all(),
             'obligations': db.scalars(select(Obligation).where(True if principal.admin else Obligation.company_id.in_(principal.company_ids)).order_by(Obligation.due_date)).all(),
             'documents': [{'id': d.id, 'company_id': d.company_id if principal.admin or d.company_id in principal.company_ids else None, 'name': d.name, 'category': d.category, 'size': d.size, 'created_at': d.created_at} for d in db.scalars(select(Document).where(storage_service()._scope(actor)).order_by(Document.created_at.desc()))],
             'audit': db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all() if principal.admin else [],
             'agents': [{'id': a.id, 'online': online(a), 'capabilities': a.capabilities, 'last_seen': a.last_seen} for a in agents],
             'jobs': db.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all() if principal.admin else [],
             'database': 'PostgreSQL' if engine.dialect.name == 'postgresql' else 'SQLite (modo de prueba)',
             'integrations': {'sat':False, 'ocr':False, 'printing':False} }

@app.post('/api/companies', dependencies=ADMIN, status_code=201)
def create_company(data: CompanyIn, db: Session = Depends(session)):
    from .company_lifecycle import ensure_unique_rfc
    ensure_unique_rfc(db, data.rfc)
    company = Company(**data.model_dump()); db.add(company)
    # Commit first validates RFC uniqueness; record creation in same transaction.
    company.id = str(uuid4()); record(db,'Empresa registrada',company.id); save(db)
    return company

@app.put('/api/companies/{id}', dependencies=ADMIN)
def edit_company(id: str, data: CompanyIn, db: Session = Depends(session)):
    company = get(db, Company, id)
    from .company_lifecycle import ensure_unique_rfc
    ensure_unique_rfc(db, data.rfc, id)
    for key, value in data.model_dump().items(): setattr(company,key,value)
    record(db,'Datos de empresa actualizados',id); save(db); return company

@app.post('/api/tasks', dependencies=APP, status_code=201)
def create_task(data: TaskIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require_company(data.company_id, write=True)
    get(db,Company,data.company_id)
    task=Task(**data.model_dump());db.add(task);record(db,'Tarea creada: '+data.title,data.company_id);save(db);return task

@app.put('/api/tasks/{id}', dependencies=APP)
def edit_task(id: str, data: TaskIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require_company(data.company_id, write=True)
    task=get(db,Task,id);get(db,Company,data.company_id)
    principal.require_company(task.company_id, write=True)
    for k,v in data.model_dump().items(): setattr(task,k,v)
    record(db,'Tarea actualizada: '+data.title,data.company_id);save(db);return task

@app.post('/api/obligations', dependencies=APP, status_code=201)
def create_obligation(data: ObligationIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require_company(data.company_id, write=True)
    get(db,Company,data.company_id);o=Obligation(**data.model_dump());db.add(o)
    record(db,'Obligación registrada: '+data.title,data.company_id);save(db);return o

@app.put('/api/obligations/{id}', dependencies=APP)
def edit_obligation(id: str, data: ObligationIn, db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require_company(data.company_id, write=True)
    o=get(db,Obligation,id);get(db,Company,data.company_id)
    principal.require_company(o.company_id, write=True)
    for k,v in data.model_dump().items():setattr(o,k,v)
    record(db,'Obligación actualizada: '+data.title,data.company_id);save(db);return o

@app.post('/api/companies/{id}/documents', dependencies=APP, status_code=201)
async def upload_document(id: str, file: UploadFile = File(...), category: str = Form('General'), db: Session = Depends(session), principal: Principal = Depends(auth)):
    principal.require_company(id, write=True)
    get(db,Company,id)
    name=Path((file.filename or 'documento').replace('\\','/')).name
    ext=Path(name).suffix.lower()
    if ext not in {'.pdf','.xml','.cer'}: raise HTTPException(422,'Sólo PDF, XML y CER. Las llaves privadas permanecen en el equipo local.')
    if len(name)>255 or len(category)>80: raise HTTPException(422,'Nombre o categoría demasiado largo')
    storage=str(uuid4())+ext;path=DATA/'documents'/storage;size=0
    try:
        with path.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>25*1024*1024:raise HTTPException(413,'El máximo es 25 MB por archivo')
                out.write(chunk)
        if not size:raise HTTPException(422,'El archivo está vacío')
        from .storage.internal import validate_payload
        from .storage.providers import StorageError
        try:
            with path.open('rb') as reader:validate_payload(reader,name,allow_public_cer=True)
        except StorageError:
            raise HTTPException(422,'El contenido no corresponde a PDF, XML o certificado público CER válido. No se admiten claves privadas.') from None
        doc=Document(company_id=id,name=name,category=category,size=size,storage_name=storage,classification_status='confirmed')
        db.add(doc);record(db,'Documento adjuntado: '+name,id);save(db)
        return doc if principal.admin else {'id':doc.id,'company_id':doc.company_id,'name':doc.name,
                                            'category':doc.category,'size':doc.size,'created_at':doc.created_at}
    except Exception:
        path.unlink(missing_ok=True);raise
    finally:await file.close()

@app.get('/api/documents/{id}/download', dependencies=APP)
def download_document(id: str, db: Session = Depends(session), principal: Principal = Depends(auth)):
    from .storage.router import storage_service, document_response
    return document_response(storage_service(), principal.storage_actor(), id)

@app.delete('/api/documents/{id}', dependencies=ADMIN, status_code=204)
def delete_document(id: str, db: Session = Depends(session)):
    doc=get(db,Document,id)
    from .models import DocumentVersion
    if doc.managed or db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id==id).limit(1)):
        raise HTTPException(409,'El documento tiene historial de almacenamiento. Se conserva hasta habilitar su gestión documental.')
    path=DATA/'documents'/doc.storage_name
    record(db,'Documento eliminado: '+doc.name,doc.company_id);db.delete(doc);save(db);path.unlink(missing_ok=True)

@app.post('/api/jobs', dependencies=ADMIN, status_code=201)
def create_job(data: JobIn, db: Session = Depends(session)):
    company=get(db,Company,data.company_id);agent=get(db,Agent,data.agent_id)
    if not online(agent):raise HTTPException(409,'El agente está desconectado')
    if data.kind not in agent.capabilities:raise HTTPException(409,'El agente no tiene esta capacidad')
    if not company.folder:raise HTTPException(422,'Primero configura la carpeta de la empresa')
    job=Job(company_id=company.id,agent_id=agent.id,kind=data.kind,payload={'folder':company.folder,'rfc':company.rfc})
    db.add(job);record(db,'Análisis de carpeta solicitado',company.id);save(db);return job

@app.post('/api/agent/heartbeat', dependencies=AGENT)
def heartbeat(data: Heartbeat, db: Session = Depends(session)):
    agent=db.get(Agent,data.id)
    if not agent:agent=Agent(id=data.id);db.add(agent)
    agent.last_seen=datetime.now(timezone.utc);agent.capabilities=data.capabilities
    save(db);return {'ok':True}

@app.post('/api/agent/{agent_id}/claim', dependencies=AGENT)
def claim(agent_id: str, db: Session = Depends(session)):
    get(db,Agent,agent_id)
    # Atomic compare-and-swap prevents duplicate claims on both supported databases.
    for job in db.scalars(select(Job).where(Job.agent_id==agent_id,Job.status=='queued').order_by(Job.created_at)).all():
        changed=db.execute(update(Job).where(Job.id==job.id,Job.status=='queued').values(status='running'))
        db.commit()
        if changed.rowcount:db.refresh(job);return job
    return None

@app.post('/api/agent/jobs/{id}/result', dependencies=AGENT)
def result(id: str, data: JobResult, db: Session = Depends(session)):
    job=get(db,Job,id)
    if job.agent_id!=data.agent_id or job.status!='running':raise HTTPException(409,'Trabajo no asignado o ya finalizado')
    if len(json.dumps(data.result))>2_000_000:raise HTTPException(413,'Resultado demasiado grande')
    job.status=data.status;job.result=data.result
    record(db,'Análisis local '+('completado' if data.status=='completed' else 'fallido'),job.company_id)
    save(db);return {'ok':True}

def seed_examples(db):
    examples=[('Distribuidora Bajío S.A. de C.V.', 'DBA180412KJ9', 'C.P. Mariana Rivas', 'León, GTO'),
              ('Soluciones Industriales Mexiquenses S.A.', 'SIM090822TR4', 'C.P. Alejandro Morales', 'Toluca, MEX'),
              ('Consultoría y Logística Integral S.A.S.', 'CLI210315AA2', 'C.P. Roberto Treviño', 'CDMX')]
    for i,(name,rfc,accountant,location) in enumerate(examples):
        company=Company(id=str(uuid4()),is_demo=True,name=name,rfc=rfc,accountant=accountant,location=location,notes='Datos ficticios de Stitch para probar la interfaz. Sin validación SAT.')
        db.add(company);db.flush()
        db.add(Task(company_id=company.id,title=['Revisar expediente documental','Revisar acuses del periodo','Conciliar documentación'][i],due_date=date.today()+timedelta(days=[4,-2,7][i]),responsible=company.accountant,priority=['Alta','Crítica','Media'][i]))
        db.add(Obligation(company_id=company.id,title='Declaración mensual · DEMO',period=date.today().strftime('%Y-%m'),due_date=date.today()+timedelta(days=[8,-1,10][i]),notes='Fecha de ejemplo, configurada manualmente.'))
        record(db,'Empresa de prueba creada',company.id)

@app.post('/api/demo', dependencies=ADMIN)
def demo(db: Session = Depends(session)):
    if db.scalar(select(Company.id).limit(1)):raise HTTPException(409,'Los ejemplos sólo se cargan en una base vacía')
    seed_examples(db);save(db);return {'ok':True}

@app.delete('/api/companies/{id}', dependencies=ADMIN, status_code=204)
def delete_company(id: str, db: Session = Depends(session)):
    from .company_lifecycle import forbid_delete
    forbid_delete()

from .company_lifecycle import router as company_lifecycle_router
app.include_router(company_lifecycle_router)

from .receipts import router as receipts_router
app.include_router(receipts_router, dependencies=ADMIN)

from .recopila import router as recopila_router
app.include_router(recopila_router, dependencies=ADMIN)

from .organizador import router as organizador_router
app.include_router(organizador_router, dependencies=ADMIN)

from .declara import router as declara_router
app.include_router(declara_router, dependencies=ADMIN)

from .storage.router import router as storage_router
app.include_router(storage_router)

from .accounts import router as accounts_router
app.include_router(accounts_router)

from .fiscal_control import router as fiscal_control_router
app.include_router(fiscal_control_router)

from .credential_api import router as credential_router
from . import credential_alerts  # Registers local alert endpoints on the same router.
app.include_router(credential_router)

@app.middleware('http')
async def credential_cache_policy(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith(('/api/credentials','/api/pilot-imports')):
        response.headers['Cache-Control']='no-store, private'
        response.headers['Pragma']='no-cache'
    return response

from .company_import_api import router as company_import_router
app.include_router(company_import_router)

from .pilot_import import router as pilot_import_router
app.include_router(pilot_import_router)

from .integral_api import router as integral_router
app.include_router(integral_router)

DIST=ROOT/'frontend'/'dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    app.mount('/icons',StaticFiles(directory=DIST/'icons'),name='icons')
    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path: str):
        if path.startswith('api/') or path=='api':raise HTTPException(404,'Endpoint no encontrado')
        return FileResponse(DIST/'index.html')
