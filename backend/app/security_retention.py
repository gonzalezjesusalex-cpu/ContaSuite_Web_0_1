"""Retention for security_events only. storage_events, audit and fiscal/document history are never touched.

CS_SECURITY_EVENT_RETENTION_DAYS: days to keep (default 365, minimum 90); 0 disables the purge.
Run by the alerts worker at most once a day, or explicitly: python -m app.security_retention --once
"""

import argparse
import os
from datetime import timedelta

from sqlalchemy import delete, select

from .models import SecurityEvent, now

DEFAULT_DAYS = 365
MINIMUM_DAYS = 90
BATCH = 5000


def retention_days(value=None):
    raw = os.getenv('CS_SECURITY_EVENT_RETENTION_DAYS', str(DEFAULT_DAYS)) if value is None else value
    try:
        days = int(str(raw).strip())
    except ValueError:
        raise ValueError('CS_SECURITY_EVENT_RETENTION_DAYS must be an integer') from None
    if days != 0 and days < MINIMUM_DAYS:
        raise ValueError(f'CS_SECURITY_EVENT_RETENTION_DAYS must be 0 (disabled) or at least {MINIMUM_DAYS}')
    return days


def purge_security_events(session_factory, days=None, batch=BATCH, current=None):
    """Delete expired security events in batches; returns the number deleted (0 when disabled)."""
    days = retention_days() if days is None else retention_days(days)
    if days == 0:
        return 0
    cutoff = (current or now()) - timedelta(days=days)
    deleted = 0
    while True:
        with session_factory.begin() as db:
            ids = db.scalars(select(SecurityEvent.id).where(SecurityEvent.created_at < cutoff).limit(batch)).all()
            if not ids:
                break
            db.execute(delete(SecurityEvent).where(SecurityEvent.id.in_(ids)))
            deleted += len(ids)
        if len(ids) < batch:
            break
    if deleted:
        with session_factory.begin() as db:
            db.add(
                SecurityEvent(
                    actor_id='retention', action='security_events_purged', outcome='success', code=str(deleted)
                )
            )
    return deleted


class DailyPurge:
    """Runs the purge at most once per interval within a worker process."""

    def __init__(self, session_factory, interval=timedelta(hours=24), clock=now):
        self.session_factory, self.interval, self.clock, self.last = session_factory, interval, clock, None

    def __call__(self):
        current = self.clock()
        if self.last is not None and current - self.last < self.interval:
            return None
        self.last = current
        return purge_security_events(self.session_factory, current=current)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', required=True)
    parser.parse_args()
    from .database import SessionLocal

    print('Eventos de seguridad purgados:', purge_security_events(SessionLocal))
