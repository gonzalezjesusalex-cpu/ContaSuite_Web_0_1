"""Server-trusted identities. Installation key stops working after the first named account."""

import hashlib
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timezone, timedelta
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, update
from .database import SessionLocal
from .models import (
    ROLES,
    IdentityState,
    UserAccount,
    UserCompanyAction,
    UserCompanyGrant,
    UserSession,
    SecurityEvent,
    now,
)
from .permissions import ACTIONS, company_actions

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
    role: str | None = None
    # Explicit actions of an auxiliar per company (UserCompanyAction rows); absent = never set.
    explicit_actions: Mapping[str, frozenset[str]] = field(default_factory=dict, hash=False)

    def __post_init__(self):
        # Role comes from the server-side account; `admin` is derived from it and both must agree.
        role = self.role or ('admin' if self.admin else 'auxiliar')
        if role not in ROLES or self.admin != (role == 'admin'):
            raise ValueError('Rol de sesión incoherente.')
        object.__setattr__(self, 'role', role)

    def require_admin(self):
        if not self.admin:
            raise HTTPException(403, 'Esta operación requiere administración.')

    def require_company(self, company_id, *, write=False):
        if not self.admin and company_id not in (self.write_company_ids if write else self.company_ids):
            raise HTTPException(404, 'Registro no encontrado.')

    def actions(self, company_id):
        if self.admin:
            return ACTIONS
        if company_id not in self.company_ids:
            return frozenset()
        return company_actions(self.role, company_id in self.write_company_ids, self.explicit_actions.get(company_id))

    def can(self, action, company_id):
        if action not in ACTIONS:
            raise ValueError('Acción desconocida: ' + action)
        return action in self.actions(company_id)

    def require(self, action, company_id):
        """Company-scoped action check: 404 without access to the company, 403 without the action."""
        self.require_company(company_id)
        if not self.can(action, company_id):
            raise HTTPException(403, 'Tu perfil no permite esta operación en esta empresa.')

    def storage_actor(self):
        from .storage.service import StorageActor

        uploads = frozenset(c for c in self.company_ids if self.can('documentos.subir', c))
        return StorageActor(
            self.subject,
            self.company_ids,
            frozenset({'read'} | ({'write'} if uploads else set())),
            self.admin,
            write_company_ids=uploads,
        )

    def public(self):
        return dict(
            id=self.subject,
            display_name=self.display_name,
            admin=self.admin,
            role=self.role,
            bootstrap=self.bootstrap,
            company_ids=sorted(self.company_ids),
            write_company_ids=sorted(self.write_company_ids),
            actions={c: sorted(self.actions(c)) for c in sorted(self.company_ids)},
        )


def audit(actor_id, action, outcome='success', code=None):
    with SessionLocal.begin() as db:
        db.add(SecurityEvent(actor_id=actor_id, action=action, outcome=outcome, code=code))


def installation_key(credentials):
    token = os.getenv('APP_TOKEN', '')
    return (
        len(token) >= 24
        and credentials is not None
        and len(credentials.credentials) <= 512
        and secrets.compare_digest(credentials.credentials.encode(), token.encode())
    )


def same_origin(request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Origen de solicitud no autorizado.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origen de solicitud no autorizado.')


def session_secure(request):
    if request.url.scheme == 'https':
        return True
    if (
        request.url.hostname in {'localhost', '127.0.0.1', '::1', 'testserver'}
        and request.client
        and request.client.host in {'127.0.0.1', '::1', 'testclient'}
    ):
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
            if (
                row
                and user
                and user.enabled
                and row.revoked_at is None
                and utc(row.expires_at) > stamp
                and utc(row.last_seen_at) + timedelta(minutes=30) > stamp
            ):
                session_secure(request)
                principal = Principal(
                    user.id, user.display_name, user.role == 'admin', session_id=ident, role=user.role
                )
                request.state.principal = principal
                if request.method not in SAFE_METHODS:
                    csrf = request.headers.get('x-csrf-token', '')
                    if not csrf or len(csrf) > 128 or not secrets.compare_digest(digest(csrf), row.csrf_hash):
                        raise HTTPException(
                            403, 'La sesión requiere una comprobación de seguridad. Actualiza la página.'
                        )
                grants = db.scalars(select(UserCompanyGrant).where(UserCompanyGrant.user_id == user.id)).all()
                explicit = {}
                if user.role == 'auxiliar':
                    for item in db.scalars(select(UserCompanyAction).where(UserCompanyAction.user_id == user.id)):
                        explicit.setdefault(item.company_id, set()).add(item.action)
                principal = Principal(
                    user.id,
                    user.display_name,
                    user.role == 'admin',
                    frozenset(g.company_id for g in grants),
                    frozenset(g.company_id for g in grants if g.access == 'write'),
                    session_id=ident,
                    role=user.role,
                    explicit_actions={c: frozenset(a) for c, a in explicit.items()},
                )
                activity = request.method not in SAFE_METHODS or request.headers.get('x-contasuite-activity') == '1'
                if activity and utc(row.last_seen_at) + timedelta(minutes=1) < stamp:
                    db.execute(
                        update(UserSession)
                        .where(UserSession.id == ident, UserSession.revoked_at.is_(None))
                        .values(last_seen_at=stamp)
                    )
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
