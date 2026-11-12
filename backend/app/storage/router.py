"""Authenticated catalogue, indexing and classification HTTP surface. No client-supplied identities or filesystem paths."""
from typing import Annotated, Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..security import auth, Principal
from ..database import DATA, SessionLocal
from ..models import Company
from .service import StorageActor, StorageService
from .settings import StorageSettings
from .providers import StorageError
from .schemas import CatalogPage, DocumentDetail, DocumentPublic
from .indexer import LocalIndexer
from .connector import ConnectorService
from .dashboard import DashboardService

router = APIRouter(prefix='/api/storage', tags=['CS-Storage'], dependencies=[Depends(auth)])


def installation_actor(principal: Principal = Depends(auth)):
    return principal.storage_actor()


def storage_service():
    return StorageService(SessionLocal, StorageSettings.from_environment(DATA))


def storage_http_error(error):
    descriptions = {
        'not_found': (404, 'Documento o empresa no encontrado.'), 'forbidden': (403, 'No tienes permiso para esta operación.'),
        'unauthenticated': (401, 'Identificación requerida.'), 'missing': (404, 'El archivo no está disponible en su origen.'),
        'integrity_error': (409, 'El contenido del archivo cambió. No se entregó una copia sin verificar.'),
        'file_changed': (409, 'El archivo cambió durante la comprobación. Revisa el origen.'),
        'revision_conflict': (409, 'El documento cambió. Actualiza antes de repetir la operación.'),
        'file_too_large': (413, 'El archivo supera el límite permitido.'), 'empty_file': (422, 'El archivo está vacío.'),
        'unsupported_format': (422, 'Se admiten PDF, XML y certificados públicos CER. Las llaves privadas y contenedores no se admiten.'),
        'protected_file': (422, 'Las claves privadas están excluidas del Centro Documental.'),
        'invalid_format': (422, 'El contenido no corresponde al formato admitido.'),
        'invalid_public_certificate': (422, 'El archivo anterior no es un certificado público CER válido.'),
        'invalid_metadata': (422, 'Revisa el tipo, categoría y periodo del documento.'),
        'invalid_filters': (422, 'Revisa los filtros de búsqueda.'), 'invalid_path': (422, 'El nombre o identificador no es válido.'),
        'access_denied': (409, 'El origen no permite leer este archivo.'),
        'smb_not_configured': (409, 'Configura el servidor y el recurso compartido SMB.'),
        'smb_requires_windows': (409, 'El conector SMB requiere ejecutar ContaSuite en Windows.'),
        'unauthorized_root': (409, 'La carpeta no está incluida en las rutas autorizadas de esta instalación.'),
        'source_busy': (409, 'Espera a que termine el análisis antes de cambiar este origen.'),
        'immutable_source': (409, 'El tipo y la raíz de un origen con historial no se pueden cambiar. Registra otro origen.'),
        'duplicate_source': (409, 'La carpeta ya está registrada como origen.'),
    }
    status, message = descriptions.get(error.code, (409, 'No se pudo acceder al documento o su origen. Actualiza o revisa la configuración.'))
    return HTTPException(status, detail=message)


Actor = Annotated[StorageActor, Depends(installation_actor)]
Service = Annotated[StorageService, Depends(storage_service)]


class CertificateUsage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    usage: Literal['fiel','csd','unknown']


@router.get('/dashboard')
def dashboard(actor: Actor,service: Service,company_id: str | None=None):
    try:
        return DashboardService(service).report(actor,company_id)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.put('/documents/{ident}/certificate-usage')
def certificate_usage(ident: str,payload: CertificateUsage,actor: Actor,service: Service):
    try:
        return DashboardService(service).label(actor,ident,payload.revision,payload.usage)
    except StorageError as exc:
        raise storage_http_error(exc) from None


class WindowsDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    server: str = Field('',max_length=253,pattern=r'^[A-Za-z0-9.-]*$')
    share: str = Field('',max_length=80,pattern=r'^[^\\/:"*?<>|\x00-\x1f]*$')
    subdirectory: str = Field('',max_length=500)
    account_name: str = Field('',max_length=160)
    credential_reference: str = Field('',max_length=120,pattern=r'^[A-Za-z0-9_.:/ -]*$')


class SourceConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int | None = Field(None,ge=1)
    label: str = Field(min_length=1,max_length=160)
    kind: Literal['local_folder','windows_smb']
    root_path: str = Field('',max_length=1000)
    enabled: bool = True
    interval_minutes: int = Field(0,ge=0,le=10080)
    exclusions: list[str] = Field(default_factory=list,max_length=100)
    windows: WindowsDraft = Field(default_factory=WindowsDraft)

    @model_validator(mode='after')
    def valid(self):
        if any(not p or len(p)>200 or '\\' in p or any(ord(c)<32 for c in p) for p in self.exclusions):
            raise ValueError('Revisa los patrones de exclusión.')
        if self.kind == 'local_folder' and not self.root_path:
            raise ValueError('Selecciona una carpeta local autorizada.')
        if self.kind == 'windows_smb':
            from .smb import windows_root
            try:
                windows_root(self.windows.model_dump())
            except StorageError:
                raise ValueError('Revisa el servidor, recurso y subcarpeta SMB.') from None
            if self.root_path:
                raise ValueError('La ruta SMB se construye con servidor, recurso y subcarpeta.')
        return self


@router.get('/connector/options')
def connector_options(actor: Actor,service: Service):
    try:
        return ConnectorService(service).options(actor)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.get('/connector/sources')
def connector_sources(actor: Actor,service: Service):
    try:
        return ConnectorService(service).list(actor)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/connector/sources',status_code=201)
def connector_create(payload: SourceConfiguration,actor: Actor,service: Service):
    try:
        return ConnectorService(service).save(actor,payload)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.put('/connector/sources/{ident}')
def connector_edit(ident: str,payload: SourceConfiguration,actor: Actor,service: Service):
    try:
        return ConnectorService(service).save(actor,payload,ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/connector/sources/{ident}/probe')
def connector_probe(ident: str,actor: Actor,service: Service):
    try:
        return ConnectorService(service).probe(actor,ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.get('/options')
def options(actor: Actor, service: Service):
    try:
        actor.require('read')
        with service.sessions() as db:
            query = select(Company).order_by(Company.name)
            if not actor.admin:
                query = query.where(Company.id.in_(actor.company_ids))
            companies = [{'id': c.id, 'name': c.name, 'rfc': c.rfc} for c in db.scalars(query)]
        return {'companies': companies, 'sources': service.sources(actor) if actor.admin else [],
                'max_file_bytes': service.settings.max_file_bytes, 'upload_formats': ['pdf', 'xml', 'cer'],
                'identity_mode': 'named_session' if actor.subject != 'installation_admin' else 'installation_admin',
                'can_review': actor.admin, 'can_write': actor.admin or 'write' in actor.permissions,
                'write_company_ids': sorted(actor.company_ids if actor.write_company_ids is None else actor.write_company_ids),
                'can_index': actor.admin, 'can_classify': actor.admin}
    except StorageError as exc:
        raise storage_http_error(exc) from None


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(min_length=1, max_length=36)


class ClassificationLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    company_id: str = Field(min_length=1, max_length=36)
    role: str = Field(pattern='^(owner|issuer|receiver)$')


class ResolutionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    action: str = Field(pattern='^(confirm|correct|reject)$')
    links: list[ClassificationLink] = Field(default_factory=list, max_length=20)
    reason: str | None = Field(None,min_length=3,max_length=1000)

class ReopenRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    reason:str=Field(min_length=3,max_length=1000)

@router.post('/documents/{ident}/reviews/{review_id}/reopen')
def reopen_classification(ident:str,review_id:str,payload:ReopenRequest,actor:Actor,service:Service):
    try:return service.reopen_review(actor,ident,review_id,payload.revision,payload.reason)
    except StorageError as exc:raise storage_http_error(exc) from None


@router.get('/index-jobs')
def index_jobs(actor: Actor, service: Service):
    try:
        return LocalIndexer(service).jobs(actor)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/index-jobs', status_code=202)
def queue_index(payload: IndexRequest, actor: Actor, service: Service):
    try:
        return LocalIndexer(service).enqueue(actor, payload.source_id)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.get('/documents/{ident}/reviews')
def classification_reviews(ident: str, actor: Actor, service: Service):
    try:
        return service.reviews(actor, ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.get('/documents/{ident}/duplicates')
def duplicate_documents(ident: str, actor: Actor, service: Service):
    try:
        return service.duplicates(actor, ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/documents/{ident}/classify')
def classify_document(ident: str, actor: Actor, service: Service):
    try:
        actor.require('review')
        if not actor.admin:
            raise StorageError('forbidden')
        doc = service.document(actor, ident)
        with service.sessions() as db:
            companies = [dict(id=c.id, rfc=c.rfc) for c in db.scalars(select(Company))]
        result = LocalIndexer(service)._classification(doc, companies, actor)
        service.apply_classification(actor, ident, doc.revision, result)
        return service.reviews(actor, ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/documents/{ident}/reviews/{review_id}')
def resolve_classification(ident: str, review_id: str, payload: ResolutionRequest, actor: Actor, service: Service):
    try:
        service.resolve_review(actor, ident, review_id, payload.revision, payload.action,
                                 [link.model_dump() for link in payload.links],reason=payload.reason)
        return service.reviews(actor, ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None

@router.get('/reconciliation')
def reconciliation(actor:Actor,service:Service,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),company_id:str|None=None):
    try:
        actor.require('review')
        if not actor.admin:raise StorageError('forbidden')
        from ..models import DocumentClassificationReview as Review,Document,DocumentVersion
        from sqlalchemy import func
        with service.sessions() as db:
            query=select(Review).join(Document,Document.id==Review.document_id).join(DocumentVersion,DocumentVersion.id==Review.version_id).where(
                Review.status=='pending',DocumentVersion.number==Document.storage_revision)
            if company_id:
                from ..models import DocumentCompanyLink
                from sqlalchemy import or_
                query=query.where(or_(Document.company_id==company_id,Document.id.in_(select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id==company_id))))
            total=db.scalar(select(func.count()).select_from(query.subquery()))
            rows=db.scalars(query.order_by(Review.created_at,Review.id).offset(offset).limit(limit))
            return {'total':total,'offset':offset,'limit':limit,'items':[{'review_id':r.id,'document_id':r.document_id,
                'name':db.get(Document,r.document_id).name,'version':db.get(DocumentVersion,r.version_id).number,
                'reason':r.evidence.get('reason','manual_review'),'uuid':r.evidence.get('identity',{}).get('uuid'),
                'requires_identity_review':r.evidence.get('identity',{}).get('requires_review',False)} for r in rows]}
    except StorageError as exc:raise storage_http_error(exc) from None


@router.get('/documents', response_model=CatalogPage)
def documents(actor: Actor, service: Service, q: str = Query('', max_length=200), company_id: str | None = None,
              period: str | None = None, year: int | None = Query(None, ge=2000, le=2100), month: int | None = Query(None, ge=1, le=12),
              format: str | None = None, document_type: str | None = None, source_id: str | None = None,
              pending: bool = False, offset: int = Query(0, ge=0, le=100000), limit: int = Query(25, ge=1, le=100)):
    try:
        return service.list_documents(actor, query=q, company_id=company_id, period=period, year=year, month=month,
            format=format, document_type=document_type, source_id=source_id, pending=pending, offset=offset, limit=limit)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/documents', status_code=201, response_model=DocumentPublic)
def upload(actor: Actor, service: Service, file: UploadFile = File(...), company_id: str = Form(''),
           category: str = Form('General'), document_type: str = Form('unknown'), period: str = Form('')):
    try:
        return service.upload(actor, file.file, file.filename or '', company_id=company_id or None,
                              category=category, document_type=document_type, period=period or None)
    except StorageError as exc:
        raise storage_http_error(exc) from None
    finally:
        file.file.close()


@router.get('/documents/{ident}', response_model=DocumentDetail)
def detail(ident: str, actor: Actor, service: Service):
    try:
        return service.describe(actor, ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


@router.post('/documents/{ident}/verify', response_model=DocumentDetail)
def verify(ident: str, actor: Actor, service: Service):
    try:
        service.verify_legacy(actor, ident)
        with service.read(actor, ident):
            pass
        return service.describe(actor, ident)
    except StorageError as exc:
        raise storage_http_error(exc) from None


def document_response(service, actor, ident, *, preview=False, revision=None):
    manager = None
    try:
        service.verify_legacy(actor, ident)
        manager = service.read(actor, ident, revision=revision)
        content = manager.__enter__()  # Verify before sending HTTP headers or any content.
    except StorageError as exc:
        raise storage_http_error(exc) from None
    closed = False
    def finish():
        nonlocal closed
        if not closed:
            closed = True
            manager.__exit__(None, None, None)
    if preview and content.media_type not in {'application/pdf', 'application/xml'}:
        finish()
        raise HTTPException(415, 'Este formato admite descarga, pero no vista previa.')
    content.stream.seek(0, 2)
    size = content.stream.tell()
    content.stream.seek(0)
    def chunks():
        try:
            while data := content.stream.read(256 * 1024):
                yield data
        finally:
            finish()
    disposition = 'inline' if preview else 'attachment'
    headers = {'Content-Disposition': disposition + "; filename*=UTF-8''" + quote(content.filename or content.document.name, safe=''),
               'Content-Length': str(size), 'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
               'Content-Security-Policy': "frame-ancestors 'self'"}
    media_type = ('application/pdf' if content.media_type == 'application/pdf' else 'text/plain; charset=utf-8') if preview else 'application/octet-stream'
    return StreamingResponse(chunks(), media_type=media_type, headers=headers, background=BackgroundTask(finish))


@router.get('/documents/{ident}/content')
def content(ident: str, actor: Actor, service: Service, preview: bool = False, revision: int | None = Query(None, ge=1)):
    return document_response(service, actor, ident, preview=preview, revision=revision)
