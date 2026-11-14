"""Named accounts, revocable cookie sessions and installation bootstrap."""

import argparse
import base64
import getpass
import hashlib
import secrets
import threading
from datetime import timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from .database import SessionLocal
from .models import (
    Company,
    IdentityState,
    UserAccount,
    UserCompanyAction,
    UserCompanyGrant,
    UserSession,
    LoginThrottle,
    SecurityEvent,
    StorageEvent,
    now,
)
from .permissions import LEGACY_WRITE_ACTIONS, WRITE_ACTIONS, catalog
from .security import (
    auth,
    admin_auth,
    Principal,
    security,
    digest,
    utc,
    same_origin,
    installation_key,
    audit,
    session_secure,
    SESSION_COOKIE,
    CSRF_COOKIE,
)

router = APIRouter(prefix='/api/auth', tags=['Cuentas y sesiones'])
PrincipalDep = Annotated[Principal, Depends(auth)]
HASH_SLOTS = threading.BoundedSemaphore(2)


def password_hash(password, *, salt=None):
    salt = salt or secrets.token_bytes(16)
    if not HASH_SLOTS.acquire(blocking=False):
        raise HTTPException(429, 'Hay otras verificaciones en curso. Intenta en unos segundos.')
    try:
        value = hashlib.scrypt(
            password.encode('utf-8'), salt=salt, n=2**17, r=8, p=1, dklen=32, maxmem=192 * 1024 * 1024
        )
        return 'scrypt-v1$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(value).decode()
    finally:
        HASH_SLOTS.release()


def password_matches(password, stored):
    try:
        version, salt, _ = stored.split('$')
        if version != 'scrypt-v1':
            return False
        return secrets.compare_digest(password_hash(password, salt=base64.b64decode(salt, validate=True)), stored)
    except (ValueError, TypeError):
        return False


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Input):
    username: str = Field(min_length=3, max_length=64, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=1, max_length=128)

    @field_validator('username')
    @classmethod
    def normalized(cls, value):
        return value.lower()


Role = Literal['admin', 'contador', 'auxiliar']


class Grant(Input):
    company_id: str = Field(min_length=1, max_length=36)
    access: str = Field(pattern='^(read|write)$')
    # Auxiliaries only: explicit actions in this company (catalog in app/permissions.py).
    actions: list[str] | None = Field(None, max_length=40)


class AccountCreate(Login):
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100, pattern=r'^[^\x00-\x1f]+$')
    role: Role = 'auxiliar'
    enabled: bool = True
    grants: list[Grant] = Field(default_factory=list, max_length=1000)


class Bootstrap(Login):
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100, pattern=r'^[^\x00-\x1f]+$')


class AccountEdit(Input):
    revision: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=100, pattern=r'^[^\x00-\x1f]+$')
    enabled: bool
    role: Role
    grants: list[Grant] = Field(default_factory=list, max_length=1000)
    password: str | None = Field(None, min_length=12, max_length=128)


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


def identity_lock(db):
    db.execute(
        update(IdentityState).where(IdentityState.id == 'identity').values(initialized=IdentityState.initialized)
    )
    return db.get(IdentityState, 'identity')


def named_admin(principal: Principal = Depends(admin_auth)):
    if principal.bootstrap:
        raise HTTPException(403, 'Crea primero la cuenta de administración.')
    return principal


AdminDep = Annotated[Principal, Depends(named_admin)]


def account_manager(principal: Principal = Depends(auth)):
    # Administrators manage every account; an accountant manages the auxiliaries of its companies.
    if principal.bootstrap:
        raise HTTPException(403, 'Crea primero la cuenta de administración.')
    if principal.role not in {'admin', 'contador'}:
        raise HTTPException(403, 'Esta operación requiere administración.')
    return principal


ManagerDep = Annotated[Principal, Depends(account_manager)]


def cookie_secure(request):
    return session_secure(request)


def revoke(db, user_id):
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )


def clear_cookies(response):
    response.delete_cookie(SESSION_COOKIE, path='/api')
    response.delete_cookie(CSRF_COOKIE, path='/')


def public_user(db, user, scope=None):
    actions = {}
    for row in db.scalars(select(UserCompanyAction).where(UserCompanyAction.user_id == user.id)):
        actions.setdefault(row.company_id, []).append(row.action)
    return dict(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        admin=user.role == 'admin',
        role=user.role,
        enabled=user.enabled,
        revision=user.revision,
        grants=[
            dict(
                company_id=g.company_id,
                access=g.access,
                actions=sorted(actions.get(g.company_id, [])) if user.role == 'auxiliar' else None,
            )
            for g in db.scalars(
                select(UserCompanyGrant)
                .where(UserCompanyGrant.user_id == user.id)
                .order_by(UserCompanyGrant.company_id)
            )
            if scope is None or g.company_id in scope
        ],
    )


@router.get('/status')
def status(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with SessionLocal() as db:
        state = db.get(IdentityState, 'identity')
        return {'initialized': bool(state and state.initialized)}


@router.post('/bootstrap', status_code=201)
def bootstrap(
    payload: Bootstrap, request: Request, credentials: HTTPAuthorizationCredentials | None = Security(security)
):
    same_origin(request)
    cookie_secure(request)
    with SessionLocal() as db:
        state = db.get(IdentityState, 'identity')
        if state is None or state.initialized:
            raise HTTPException(409, 'La administración inicial ya está configurada.')
    if not installation_key(credentials):
        audit('anonymous', 'bootstrap_denied', 'denied')
        raise HTTPException(401, 'Clave de instalación incorrecta.')
    encoded = password_hash(payload.password)
    with SessionLocal.begin() as db:
        state = identity_lock(db)
        if state is None or state.initialized:
            raise HTTPException(409, 'La administración inicial ya está configurada.')
        user = UserAccount(
            username=payload.username, display_name=payload.display_name, password_hash=encoded, role='admin'
        )
        db.add(user)
        db.flush()
        state.initialized = True
        db.add(SecurityEvent(actor_id=user.id, action='account_bootstrapped', outcome='success'))
        return {'id': user.id}


def throttle(request, username):
    # Serialize across processes; commit the attempt BEFORE expensive password work.
    with SessionLocal.begin() as db:
        identity_lock(db)
        keys = [('account:' + username, 8), ('address:' + (request.client.host if request.client else 'unknown'), 80)]
        rows = []
        for key, limit in keys:
            row = db.get(LoginThrottle, digest(key))
            if row is None:
                row = LoginThrottle(id=digest(key), attempts=0, window_started_at=now())
                db.add(row)
            if utc(row.window_started_at) + timedelta(minutes=15) <= now():
                row.window_started_at, row.attempts = now(), 0
            if row.attempts >= limit:
                raise HTTPException(429, 'Demasiados intentos. Espera quince minutos e intenta de nuevo.')
            rows.append(row)
        for row in rows:
            row.attempts += 1


@router.post('/login')
def login(payload: Login, request: Request, response: Response):
    same_origin(request)
    secure = cookie_secure(request)
    throttle(request, payload.username)
    with SessionLocal() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.username == payload.username))
        # An unknown username still performs the same expensive hash.
        valid = (
            password_matches(payload.password, user.password_hash)
            if user
            else bool(password_hash(payload.password) and False)
        )
        if not valid or not user or not user.enabled:
            audit('anonymous', 'login_failed', 'denied', 'invalid_credentials')
            raise HTTPException(401, 'Usuario o contraseña incorrectos.')
        user_id, revision = user.id, user.revision
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with SessionLocal.begin() as db:
        identity_lock(db)
        user = db.get(UserAccount, user_id)
        if not user.enabled or user.revision != revision:
            raise HTTPException(401, 'La cuenta cambió. Inicia sesión de nuevo.')
        old = request.cookies.get(SESSION_COOKIE, '')
        if old:
            db.execute(update(UserSession).where(UserSession.id == digest(old)).values(revoked_at=now()))
        active = db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.created_at.desc())
        ).all()
        for previous in active[4:]:
            previous.revoked_at = now()
        db.add(
            UserSession(id=digest(raw), user_id=user_id, csrf_hash=digest(csrf), expires_at=now() + timedelta(hours=12))
        )
        account_throttle = db.get(LoginThrottle, digest('account:' + payload.username))
        if account_throttle:
            account_throttle.attempts = 0
        db.add(SecurityEvent(actor_id=user_id, action='login_success', outcome='success'))
    response.set_cookie(
        SESSION_COOKIE, raw, max_age=43200, path='/api', httponly=True, secure=secure, samesite='strict'
    )
    response.set_cookie(CSRF_COOKIE, csrf, max_age=43200, path='/', httponly=False, secure=secure, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True}


@router.get('/me')
def me(principal: PrincipalDep):
    return principal.public()


@router.post('/logout')
def logout(principal: PrincipalDep, response: Response):
    if principal.session_id:
        with SessionLocal.begin() as db:
            db.execute(update(UserSession).where(UserSession.id == principal.session_id).values(revoked_at=now()))
            db.add(SecurityEvent(actor_id=principal.subject, action='logout', outcome='success'))
    clear_cookies(response)
    return {'ok': True}


@router.post('/logout-all')
def logout_all(principal: PrincipalDep, response: Response):
    with SessionLocal.begin() as db:
        revoke(db, principal.subject)
        db.add(SecurityEvent(actor_id=principal.subject, action='sessions_revoked', outcome='success'))
    clear_cookies(response)
    return {'ok': True}


@router.post('/password')
def change_password(payload: PasswordChange, principal: PrincipalDep, response: Response):
    with SessionLocal() as db:
        user = db.get(UserAccount, principal.subject)
        if not user or not password_matches(payload.current_password, user.password_hash):
            raise HTTPException(401, 'La contraseña actual no es correcta.')
        revision = user.revision
    encoded = password_hash(payload.new_password)
    with SessionLocal.begin() as db:
        identity_lock(db)
        changed = db.execute(
            update(UserAccount)
            .where(UserAccount.id == principal.subject, UserAccount.revision == revision)
            .values(password_hash=encoded, revision=revision + 1)
        )
        if not changed.rowcount:
            raise HTTPException(409, 'La cuenta cambió. Actualiza la página.')
        revoke(db, principal.subject)
        db.add(SecurityEvent(actor_id=principal.subject, action='password_changed', outcome='success'))
    clear_cookies(response)
    return {'ok': True}


@router.get('/catalog')
def permission_catalog(principal: ManagerDep):
    return catalog()


def visible_account(db, principal, user):
    """Administrators manage every account; an accountant only auxiliaries sharing one of its companies."""
    if principal.admin:
        return True
    return user.role == 'auxiliar' and bool(
        db.scalar(
            select(UserCompanyGrant.company_id)
            .where(
                UserCompanyGrant.user_id == user.id,
                UserCompanyGrant.company_id.in_(sorted(principal.write_company_ids)),
            )
            .limit(1)
        )
    )


def scope_of(principal):
    """Companies whose grants this manager may see and change (None = all)."""
    return None if principal.admin else principal.write_company_ids


def checked_grants(db, principal, role, grants):
    """Validate requested grants and resolve them to {company_id: (access, actions or None)}.

    Auxiliaries always get explicit actions: none for read, the pre-role write reach for a bare write
    grant. An accountant may only grant, in its own companies, actions it holds itself (no escalation).
    """
    ids = [g.company_id for g in grants]
    if len(set(ids)) != len(ids) or any(db.get(Company, cid) is None for cid in ids):
        raise HTTPException(422, 'Revisa las empresas y permisos seleccionados.')
    resolved = {}
    for g in grants:
        if role != 'auxiliar':
            if g.actions is not None:
                raise HTTPException(422, 'Las acciones por empresa sólo se asignan a auxiliares.')
            resolved[g.company_id] = (g.access, None)
            continue
        if g.actions is None:
            actions = set(LEGACY_WRITE_ACTIONS) if g.access == 'write' else set()
        else:
            actions = set(g.actions)
            if actions - WRITE_ACTIONS:
                raise HTTPException(422, 'Acción desconocida en los permisos.')
        if not principal.admin:
            if g.company_id not in principal.write_company_ids:
                raise HTTPException(403, 'Sólo puedes dar acceso a empresas que gestionas.')
            if not actions <= principal.actions(g.company_id):
                raise HTTPException(403, 'No puedes conceder acciones que no tienes.')
        resolved[g.company_id] = ('write' if actions else 'read', frozenset(actions))
    return resolved


def store_grants(db, user_id, resolved, scope=None):
    """Replace the grants (and auxiliary actions) inside `scope`; grants outside it are left untouched."""
    grants = [UserCompanyGrant.user_id == user_id]
    actions = [UserCompanyAction.user_id == user_id]
    if scope is not None:
        grants.append(UserCompanyGrant.company_id.in_(sorted(scope)))
        actions.append(UserCompanyAction.company_id.in_(sorted(scope)))
    db.execute(delete(UserCompanyAction).where(*actions))
    db.execute(delete(UserCompanyGrant).where(*grants))
    for cid, (access, chosen) in resolved.items():
        db.add(UserCompanyGrant(user_id=user_id, company_id=cid, access=access))
        db.add_all([UserCompanyAction(user_id=user_id, company_id=cid, action=a) for a in sorted(chosen or ())])


@router.get('/users')
def users(principal: ManagerDep):
    with SessionLocal() as db:
        rows = db.scalars(select(UserAccount).order_by(UserAccount.username).limit(1000)).all()
        return [public_user(db, u, scope_of(principal)) for u in rows if visible_account(db, principal, u)]


@router.post('/users', status_code=201)
def create_user(payload: AccountCreate, principal: ManagerDep):
    if not principal.admin:
        if payload.role != 'auxiliar':
            raise HTTPException(403, 'Sólo la administración crea contadores y administradores.')
        if not payload.grants:
            raise HTTPException(422, 'Asigna al menos una de tus empresas al auxiliar.')
    encoded = password_hash(payload.password)
    try:
        with SessionLocal.begin() as db:
            identity_lock(db)
            resolved = checked_grants(db, principal, payload.role, payload.grants)
            user = UserAccount(
                username=payload.username,
                display_name=payload.display_name,
                password_hash=encoded,
                role=payload.role,
                enabled=payload.enabled,
            )
            db.add(user)
            db.flush()
            store_grants(db, user.id, resolved)
            db.flush()
            db.add(SecurityEvent(actor_id=principal.subject, action='account_created:' + user.id, outcome='success'))
            return public_user(db, user, scope_of(principal))
    except IntegrityError:
        raise HTTPException(409, 'El nombre de usuario ya está registrado.') from None


@router.put('/users/{ident}')
def edit_user(ident: str, payload: AccountEdit, principal: ManagerDep):
    encoded = password_hash(payload.password) if payload.password else None
    with SessionLocal.begin() as db:
        identity_lock(db)
        user = db.get(UserAccount, ident)
        if not user or not visible_account(db, principal, user):
            raise HTTPException(404, 'Cuenta no encontrada.')
        if not principal.admin and payload.role != 'auxiliar':
            raise HTTPException(403, 'Sólo la administración cambia roles.')
        if not principal.admin and (
            payload.display_name != user.display_name or payload.enabled != user.enabled or encoded
        ):
            # The account itself (name, state, password) belongs to every company it works for.
            shared = db.scalar(
                select(UserCompanyGrant.company_id)
                .where(
                    UserCompanyGrant.user_id == ident,
                    UserCompanyGrant.company_id.not_in(sorted(principal.write_company_ids)),
                )
                .limit(1)
            )
            if shared:
                raise HTTPException(403, 'El auxiliar también trabaja en empresas que no gestionas.')
        if not payload.enabled or payload.role != 'admin':
            others = db.scalar(
                select(func.count())
                .select_from(UserAccount)
                .where(UserAccount.id != ident, UserAccount.enabled == True, UserAccount.role == 'admin')
            )
            if user.role == 'admin' and user.enabled and not others:
                raise HTTPException(409, 'Debe permanecer al menos un administrador activo.')
        resolved = checked_grants(db, principal, payload.role, payload.grants)
        values = dict(
            display_name=payload.display_name,
            # A bulk UPDATE skips the ORM hooks that keep `admin` in step, so both columns are written here.
            role=payload.role,
            admin=payload.role == 'admin',
            enabled=payload.enabled,
            revision=payload.revision + 1,
        )
        if encoded:
            values['password_hash'] = encoded
        changed = db.execute(
            update(UserAccount)
            .where(UserAccount.id == ident, UserAccount.revision == payload.revision)
            .values(**values)
        )
        if not changed.rowcount:
            raise HTTPException(409, 'La cuenta cambió. Actualiza antes de guardar.')
        if payload.role != 'auxiliar':
            # Explicit actions only describe auxiliaries; another role keeps none.
            db.execute(delete(UserCompanyAction).where(UserCompanyAction.user_id == ident))
        store_grants(db, ident, resolved, scope_of(principal))
        # All permission/profile changes revoke sessions immediately; the user signs in again.
        revoke(db, ident)
        db.add(SecurityEvent(actor_id=principal.subject, action='account_updated:' + ident, outcome='success'))
        db.flush()
        db.refresh(user)
        return public_user(db, user, scope_of(principal))


@router.post('/users/{ident}/revoke')
def revoke_user(ident: str, principal: ManagerDep):
    with SessionLocal.begin() as db:
        user = db.get(UserAccount, ident)
        if user is None or not visible_account(db, principal, user):
            raise HTTPException(404, 'Cuenta no encontrada.')
        revoke(db, ident)
        db.add(SecurityEvent(actor_id=principal.subject, action='sessions_revoked:' + ident, outcome='success'))
    return {'ok': True}


@router.get('/audit')
def audit_log(
    principal: AdminDep,
    kind: str = Query('security', pattern='^(security|storage)$'),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(50, ge=1, le=100),
):
    model = SecurityEvent if kind == 'security' else StorageEvent
    with SessionLocal() as db:
        rows = db.scalars(select(model).order_by(model.created_at.desc(), model.id).offset(offset).limit(limit))
        return {
            'total': db.scalar(select(func.count()).select_from(model)),
            'items': [
                dict(
                    id=r.id,
                    actor_id=r.actor_id,
                    action=r.action,
                    outcome=r.outcome,
                    code=r.code,
                    created_at=r.created_at,
                    document_id=getattr(r, 'document_id', None),
                    company_id=getattr(r, 'company_id', None),
                )
                for r in rows
            ],
        }


def recover_admin():
    parser = argparse.ArgumentParser(description='Recuperación local de una cuenta administradora existente')
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Nueva contraseña (mínimo 12 caracteres): ')
    if len(password) < 12 or len(password) > 128 or password != getpass.getpass('Repetir contraseña: '):
        parser.error('La contraseña no cumple el tamaño o no coincide.')
    encoded = password_hash(password)
    with SessionLocal.begin() as db:
        identity_lock(db)
        user = db.scalar(select(UserAccount).where(UserAccount.username == args.username.lower()))
        if user is None:
            parser.error('Cuenta inexistente; no se creará una cuenta implícita.')
        user.password_hash, user.enabled, user.role = encoded, True, 'admin'
        user.revision += 1
        revoke(db, user.id)
        db.add(SecurityEvent(actor_id='local_recovery', action='account_recovered:' + user.id, outcome='success'))
    print('Cuenta recuperada; las sesiones anteriores se revocaron.')


if __name__ == '__main__':
    recover_admin()
