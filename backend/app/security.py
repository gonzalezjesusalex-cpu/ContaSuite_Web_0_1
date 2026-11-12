"""Server-trusted identities. Installation key stops working after the first named account."""
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import timezone, timedelta
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, update
from .database import SessionLocal
from .models import IdentityState, UserAccount, UserCompanyGrant, UserSession, SecurityEvent, now

security = HTTPBearer(auto_error=False)
SESSION_COOKIE = 'contasuite_session'
CSRF_COOKIE = 'contasuite_csrf'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@dataclass(frozen=True)
class Principal:
    subject: str
    display_name: str
    admin: bool
    company_ids: frozenset[str] = frozenset()
    write_company_ids: frozenset[str] = frozenset()
    bootstrap: bool = False
    session_id: str | None = None

    def require_admin(self):
        if not self.admin:
            raise HTTPException(403, 'Esta operación requiere administración.')

    def require_company(self, company_id, *, write=False):
        if not self.admin and company_id not in (self.write_company_ids if write else self.company_ids):
            raise HTTPException(404, 'Registro no encontrado.')

    def storage_actor(self):
        from .storage.service import StorageActor
        return StorageActor(self.subject, self.company_ids,
            frozenset({'read'} | ({'write'} if self.write_company_ids else set())), self.admin,
            write_company_ids=self.write_company_ids)

    def public(self):
        return dict(id=self.subject, display_name=self.display_name, admin=self.admin, bootstrap=self.bootstrap,
                    company_ids=sorted(self.company_ids), write_company_ids=sorted(self.write_company_ids))


def audit(actor_id, action, outcome='success', code=None):
    with SessionLocal.begin() as db:
        db.add(SecurityEvent(actor_id=actor_id, action=action, outcome=outcome, code=code))


def installation_key(credentials):
    token = os.getenv('APP_TOKEN', '')
    return len(token) >= 24 and credentials is not None and len(credentials.credentials) <= 512 and secrets.compare_digest(credentials.credentials.encode(), token.encode())


def same_origin(request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Origen de solicitud no autorizado.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origen de solicitud no autorizado.')


def session_secure(request):
    if request.url.scheme == 'https':
        return True
    if request.url.hostname in {'localhost', '127.0.0.1', '::1', 'testserver'} and request.client and request.client.host in {'127.0.0.1', '::1', 'testclient'}:
        return False
    raise HTTPException(400, 'Las cuentas requieren HTTPS fuera del equipo local.')


def auth(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(security)):
    if request.method not in SAFE_METHODS:
        same_origin(request)
    cookie = request.cookies.get(SESSION_COOKIE, '')
    with SessionLocal.begin() as db:
        if cookie and len(cookie) <= 128:
            ident = digest(cookie)
            row = db.get(UserSession, ident)
            user = db.get(UserAccount, row.user_id) if row else None
            stamp = now()
            if row and user and user.enabled and row.revoked_at is None and utc(row.expires_at) > stamp and utc(row.last_seen_at) + timedelta(minutes=30) > stamp:
                session_secure(request)
                principal = Principal(user.id, user.display_name, user.admin, session_id=ident)
                request.state.principal = principal
                if request.method not in SAFE_METHODS:
                    csrf = request.headers.get('x-csrf-token', '')
                    if not csrf or len(csrf) > 128 or not secrets.compare_digest(digest(csrf), row.csrf_hash):
                        raise HTTPException(403, 'La sesión requiere una comprobación de seguridad. Actualiza la página.')
                grants = db.scalars(select(UserCompanyGrant).where(UserCompanyGrant.user_id == user.id)).all()
                principal = Principal(user.id, user.display_name, user.admin,
                    frozenset(g.company_id for g in grants), frozenset(g.company_id for g in grants if g.access == 'write'), session_id=ident)
                activity = request.method not in SAFE_METHODS or request.headers.get('x-contasuite-activity') == '1'
                if activity and utc(row.last_seen_at) + timedelta(minutes=1) < stamp:
                    db.execute(update(UserSession).where(UserSession.id == ident, UserSession.revoked_at.is_(None)).values(last_seen_at=stamp))
                request.state.principal = principal
                return principal
        state = db.get(IdentityState, 'identity')
        if state is not None and not state.initialized and installation_key(credentials):
            principal = Principal('installation_admin', 'Administración inicial', True, bootstrap=True)
            request.state.principal = principal
            return principal
    raise HTTPException(401, 'Inicia sesión con tu cuenta de ContaSuite.')


def admin_auth(principal: Principal = Depends(auth)):
    principal.require_admin()
    return principal
