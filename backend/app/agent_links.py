"""Local agent paired to the user's ContaSuite session (Bloque 4, option A approved on 14/11/2026).

1. A signed-in browser asks for a one-time code (`POST /api/agent-links/code`, ~2 minutes, only its hash kept).
2. The browser hands the code to the agent running on the same computer (http://127.0.0.1, see agent/agent.py).
3. The agent exchanges it (`POST /api/agent/pair`) for its own random credential, bound to that user and session.
   Only the credential's hash is stored; no password ever reaches the agent.
4. The credential works while the session does: sign-out, expiry, revocation or a disabled user end the link,
   and the agent waits for the next sign-in.

The agent only reads folders under the roots an administrator defines here, and only for companies where the
linked user may run `carpeta.analizar`. Every analysis records the user, the computer and the agent.
"""

import hashlib
import os
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import PureWindowsPath

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .database import session
from .models import (
    Agent,
    AgentLink,
    AgentPairCode,
    AgentRoot,
    UserAccount,
    UserCompanyAction,
    UserCompanyGrant,
    UserSession,
)
from .permissions import company_actions
from .security import Principal, admin_auth, auth, security, utc

router = APIRouter(tags=['Agente local vinculado'])
CODE_TTL = timedelta(minutes=2)
SESSION_IDLE = timedelta(minutes=30)
ONLINE = timedelta(seconds=45)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PairIn(Input):
    code: str = Field(min_length=8, max_length=64)
    agent_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    machine: str = Field(default='', max_length=120, pattern=r'^[^\x00-\x1f]*$')


class RootsIn(Input):
    paths: list[str] = Field(default_factory=list, max_length=50)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def now():
    return datetime.now(timezone.utc)


def normalized(path):
    """Comparable Windows path: case-insensitive, backslashes, no trailing separator."""
    text = unicodedata.normalize('NFC', str(path or '')).strip().replace('/', '\\')
    return str(PureWindowsPath(text)).rstrip('\\').casefold()


def roots(db):
    return [r.path for r in db.scalars(select(AgentRoot).order_by(AgentRoot.path))]


def inside_roots(folder, allowed):
    target = normalized(folder)
    return any(target == normalized(r) or target.startswith(normalized(r) + '\\') for r in allowed)


def online(link):
    return bool(link.last_seen and utc(link.last_seen) + ONLINE > now())


def user_can_analyze(db, user, company_id):
    """The linked user's right to analyze this company's folder, from its stored role and grants."""
    if not user or not user.enabled:
        return False
    if user.role == 'admin':
        return True
    grant = db.get(UserCompanyGrant, (user.id, company_id))
    if not grant:
        return False
    explicit = None
    if user.role == 'auxiliar':
        rows = db.scalars(
            select(UserCompanyAction.action).where(
                UserCompanyAction.user_id == user.id, UserCompanyAction.company_id == company_id
            )
        ).all()
        explicit = set(rows) if rows else None
    return 'carpeta.analizar' in company_actions(user.role, grant.access == 'write', explicit)


def end_link(db, link, reason):
    if link.revoked_at is None:
        link.revoked_at = now()
        link.revoked_reason = reason


def session_alive(db, link):
    row = db.get(UserSession, link.session_id)
    user = db.get(UserAccount, link.user_id)
    stamp = now()
    if not user or not user.enabled:
        return False, 'Usuario deshabilitado.'
    if not row or row.revoked_at is not None:
        return False, 'La sesión de ContaSuite se cerró.'
    if utc(row.expires_at) <= stamp or utc(row.last_seen_at) + SESSION_IDLE <= stamp:
        return False, 'La sesión de ContaSuite expiró.'
    return True, None


def active_link_for(db, user_id):
    """The user's live link, ending the ones whose session no longer exists."""
    best = None
    for link in db.scalars(
        select(AgentLink)
        .where(AgentLink.user_id == user_id, AgentLink.revoked_at.is_(None))
        .order_by(AgentLink.created_at.desc())
    ):
        alive, reason = session_alive(db, link)
        if not alive:
            end_link(db, link, reason)
        elif best is None:
            best = link
    return best


# ---------------------------------------------------------------- agent credential (used by main.py)


class LinkedAgent:
    def __init__(self, link, user):
        self.link = link
        self.user = user


def shared_token_allowed():
    """The former shared AGENT_TOKEN only works when explicitly kept for a transition (and in tests)."""
    return os.getenv('CS_ALLOW_SHARED_AGENT_TOKEN', '') == '1' and len(os.getenv('AGENT_TOKEN', '')) >= 24


def agent_caller(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    db: Session = Depends(session),
):
    """Linked agent (its own credential) or, only if allowed, the legacy shared token (returns None)."""
    raw = credentials.credentials if credentials else ''
    if not raw or len(raw) > 512:
        raise HTTPException(401, 'Agente no autorizado')
    if shared_token_allowed() and secrets.compare_digest(raw.encode(), os.getenv('AGENT_TOKEN', '').encode()):
        request.state.agent_authenticated = True
        return None
    link = db.scalar(select(AgentLink).where(AgentLink.token_hash == digest(raw)))
    if not link or link.revoked_at is not None:
        raise HTTPException(401, 'Agente sin vínculo: inicia sesión en ContaSuite en este equipo.')
    alive, reason = session_alive(db, link)
    if not alive:
        end_link(db, link, reason)
        db.commit()
        raise HTTPException(401, 'Vínculo terminado: ' + reason)
    request.state.agent_authenticated = True
    return LinkedAgent(link, db.get(UserAccount, link.user_id))


# ---------------------------------------------------------------- pairing


@router.post('/api/agent-links/code', status_code=201)
def pairing_code(principal: Principal = Depends(auth), db: Session = Depends(session)):
    """One-time code for the agent on this computer; only for a named session (never the installation key)."""
    if principal.bootstrap or not principal.session_id:
        raise HTTPException(403, 'Inicia sesión con tu cuenta para vincular el agente.')
    db.execute(
        update(AgentPairCode)
        .where(AgentPairCode.session_id == principal.session_id, AgentPairCode.used_at.is_(None))
        .values(used_at=now())
    )
    code = secrets.token_urlsafe(18)
    db.add(
        AgentPairCode(
            code_hash=digest(code),
            user_id=principal.subject,
            session_id=principal.session_id,
            expires_at=now() + CODE_TTL,
        )
    )
    db.commit()
    return {'code': code, 'expires_in': int(CODE_TTL.total_seconds())}


@router.post('/api/agent/pair', status_code=201)
def pair(payload: PairIn, db: Session = Depends(session)):
    """Exchange a code for the agent's own credential. The code works once and only for a live session."""
    row = db.get(AgentPairCode, digest(payload.code))
    if not row or row.used_at is not None or utc(row.expires_at) <= now():
        raise HTTPException(401, 'Código de vinculación inválido o vencido.')
    row.used_at = now()
    candidate = AgentLink(user_id=row.user_id, session_id=row.session_id, agent_id=payload.agent_id)
    alive, reason = session_alive(db, candidate)
    if not alive:
        db.commit()
        raise HTTPException(401, reason)
    # One user per agent: a new pairing ends any previous link of this agent.
    for old in db.scalars(
        select(AgentLink).where(AgentLink.agent_id == payload.agent_id, AgentLink.revoked_at.is_(None))
    ):
        end_link(db, old, 'Vinculado de nuevo.')
    token = secrets.token_urlsafe(32)
    user = db.get(UserAccount, row.user_id)
    link = AgentLink(
        agent_id=payload.agent_id,
        user_id=row.user_id,
        session_id=row.session_id,
        machine=payload.machine.strip()[:120],
        token_hash=digest(token),
        last_seen=now(),
        restart_requested=False,
    )
    db.add(link)
    agent = db.get(Agent, payload.agent_id) or Agent(id=payload.agent_id, capabilities=['scan_folder'])
    agent.last_seen = now()
    db.add(agent)
    db.commit()
    return {'token': token, 'user': user.display_name, 'roots': roots(db)}


# ---------------------------------------------------------------- status and administration


def public(db, link):
    user = db.get(UserAccount, link.user_id)
    return {
        'id': link.id,
        'agent_id': link.agent_id,
        'machine': link.machine,
        'user_id': link.user_id,
        'user': user.display_name if user else None,
        'created_at': link.created_at,
        'last_seen': link.last_seen,
        'online': online(link) and link.revoked_at is None,
        'revoked_at': link.revoked_at,
        'revoked_reason': link.revoked_reason,
        'restart_requested': link.restart_requested,
    }


def my_agent(db, principal):
    """Header status: «Agente conectado como Ana» or why it is not (Bloque 4)."""
    if principal.bootstrap:
        return None
    link = active_link_for(db, principal.subject)
    if link is None:
        return {'state': 'unlinked', 'roots': len(roots(db))}
    return {**public(db, link), 'state': 'online' if online(link) else 'offline', 'roots': len(roots(db))}


@router.get('/api/agent-links')
def list_links(principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    rows = db.scalars(select(AgentLink).order_by(AgentLink.created_at.desc()).limit(200)).all()
    for link in rows:
        if link.revoked_at is None:
            alive, reason = session_alive(db, link)
            if not alive:
                end_link(db, link, reason)
    db.commit()
    return {'links': [public(db, r) for r in rows], 'roots': roots(db)}


@router.post('/api/agent-links/{ident}/revoke')
def revoke_link(ident: str, principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    link = db.get(AgentLink, ident)
    if not link:
        raise HTTPException(404, 'Vínculo no encontrado.')
    end_link(db, link, 'Revocado por la administración.')
    db.commit()
    return public(db, link)


@router.post('/api/agent-links/{ident}/restart')
def restart_link(ident: str, principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    """The agent restarts on its next contact and must be paired again at the user's next sign-in."""
    link = db.get(AgentLink, ident)
    if not link or link.revoked_at is not None:
        raise HTTPException(404, 'Vínculo no encontrado o ya terminado.')
    link.restart_requested = True
    db.commit()
    return public(db, link)


@router.put('/api/agent-links/roots')
def set_roots(payload: RootsIn, principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    """Folders agents may read. Absolute local (C:\\…) or UNC (\\\\server\\share\\…) paths only."""
    clean = []
    for raw in payload.paths:
        path = raw.strip()
        win = PureWindowsPath(path)
        if not path or len(path) > 1000 or not (win.drive and win.root) or '..' in win.parts:
            raise HTTPException(422, 'Cada carpeta debe ser una ruta absoluta de Windows, sin «..».')
        if normalized(path) not in {normalized(c) for c in clean}:
            clean.append(str(win))
    for row in db.scalars(select(AgentRoot)).all():
        db.delete(row)
    db.flush()
    db.add_all([AgentRoot(path=p, created_by=principal.subject) for p in clean])
    db.commit()
    return {'roots': roots(db)}
