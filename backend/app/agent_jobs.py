"""Expiry of agent jobs left in `running` when the agent dies after claiming them.

The claim time is kept inside the existing `jobs.result` JSON (`claimed_at`) so no schema change is
needed; the agent's real result replaces it. Expired jobs become `failed` with a clear message and are
never re-queued automatically: an administrator requests the analysis again.

CS_AGENT_JOB_TIMEOUT_MINUTES: minutes a claimed job may run (default 15, minimum 5).
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from .models import Audit, Job

DEFAULT_MINUTES = 15
MINIMUM_MINUTES = 5


def timeout_minutes(value=None):
    raw = os.getenv('CS_AGENT_JOB_TIMEOUT_MINUTES', str(DEFAULT_MINUTES)) if value is None else value
    try:
        minutes = int(str(raw).strip())
    except ValueError:
        raise ValueError('CS_AGENT_JOB_TIMEOUT_MINUTES must be an integer') from None
    if minutes < MINIMUM_MINUTES:
        raise ValueError(f'CS_AGENT_JOB_TIMEOUT_MINUTES must be at least {MINIMUM_MINUTES}')
    return minutes


def claim_marker(current=None):
    return {'claimed_at': (current or datetime.now(timezone.utc)).isoformat()}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _claimed_at(job):
    raw = (job.result or {}).get('claimed_at') if isinstance(job.result, dict) else None
    if raw:
        try:
            return _aware(datetime.fromisoformat(raw))
        except (TypeError, ValueError):
            pass
    # Jobs claimed before this change carry no marker; their creation time is the only reference.
    return _aware(job.created_at)


def expire_stale_jobs(db, current=None, minutes=None):
    """Mark running jobs older than the timeout as failed. Commits; returns the expired job ids."""
    minutes = timeout_minutes() if minutes is None else timeout_minutes(minutes)
    current = current or datetime.now(timezone.utc)
    cutoff = current - timedelta(minutes=minutes)
    expired = []
    for job in db.scalars(select(Job).where(Job.status == 'running')).all():
        claimed = _claimed_at(job)
        if claimed >= cutoff:
            continue
        message = (
            f'El agente no entregó resultado en {minutes} minutos (pudo cerrarse o perder conexión). '
            'Solicita el análisis de nuevo.'
        )
        result = {'error': message, 'claimed_at': claimed.isoformat(), 'expired_at': current.isoformat()}
        # Compare-and-swap: a result delivered concurrently wins over the expiry.
        changed = db.execute(
            update(Job).where(Job.id == job.id, Job.status == 'running').values(status='failed', result=result)
        )
        if changed.rowcount:
            db.add(Audit(action='Análisis local caducado: el agente no respondió', company_id=job.company_id))
            expired.append(job.id)
    if expired:
        db.commit()
    return expired
