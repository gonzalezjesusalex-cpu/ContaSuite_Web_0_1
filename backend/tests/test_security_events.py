"""security_events: polling reads are not audited; retention purges only expired security events."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from test_api import client, A, company  # noqa: F401  Isolated environment before app imports.
from app.database import SessionLocal
from app.main import should_audit
from app.models import SecurityEvent, StorageEvent, now
from app.security_retention import DailyPurge, purge_security_events, retention_days

PDF = b'%PDF-1.4 synthetic'


def events(action=None):
    with SessionLocal() as db:
        query = select(func.count()).select_from(SecurityEvent)
        if action:
            query = query.where(SecurityEvent.action == action)
        return db.scalar(query)


def test_rules_by_method_status_and_route():
    assert not should_audit('GET', '/api/state', 200)
    assert not should_audit('GET', '/api/storage/documents', 200)
    assert should_audit('GET', '/api/state', 401)
    assert should_audit('GET', '/api/auth/users', 403)
    assert should_audit('GET', '/api/state', 500)
    assert should_audit('POST', '/api/companies', 200)
    assert should_audit('DELETE', '/api/documents/{id}', 409)
    for template in (
        '/api/documents/{id}/download',
        '/api/storage/documents/{ident}/content',
        '/api/receipts/{ident}/pdf',
        '/api/recopila/runs/{ident}/zip',
        '/api/declara/runs/{ident}/file/{index}',
        '/api/auth/audit',
    ):
        assert should_audit('GET', template, 200), template


def test_polling_is_not_audited_but_writes_denials_and_downloads_are(client):
    before = events()
    for _ in range(5):
        assert client.get('/api/state', headers=A).status_code == 200
    assert events() == before
    assert client.get('/api/state').status_code == 401
    assert events('GET /api/state') == 1
    c = company(client).json()
    assert events('POST /api/companies') == 1
    doc = client.post(
        '/api/companies/' + c['id'] + '/documents', headers=A, files={'file': ('a.pdf', PDF, 'application/pdf')}
    ).json()
    assert client.get('/api/documents/' + doc['id'] + '/download', headers=A).content == PDF
    assert events('GET /api/documents/{id}/download') == 1


def test_retention_purges_only_expired_security_events(client):
    current = now()
    with SessionLocal.begin() as db:
        db.query(SecurityEvent).delete()
        db.add(SecurityEvent(actor_id='x', action='old', outcome='success', created_at=current - timedelta(days=400)))
        db.add(SecurityEvent(actor_id='x', action='old', outcome='success', created_at=current - timedelta(days=366)))
        db.add(
            SecurityEvent(actor_id='x', action='recent', outcome='success', created_at=current - timedelta(days=364))
        )
        db.add(StorageEvent(actor_id='x', action='content_read', created_at=current - timedelta(days=900)))
    assert purge_security_events(SessionLocal, days=365, batch=1, current=current) == 2
    assert events('old') == 0 and events('recent') == 1
    with SessionLocal() as db:
        purged = db.scalars(select(SecurityEvent).where(SecurityEvent.action == 'security_events_purged')).one()
        assert purged.code == '2' and purged.actor_id == 'retention'
        assert db.scalar(select(func.count()).select_from(StorageEvent).where(StorageEvent.action == 'content_read'))
    assert purge_security_events(SessionLocal, days=365, current=current) == 0
    assert events('security_events_purged') == 1  # no event when nothing was deleted


def test_retention_configuration(monkeypatch):
    assert retention_days('365') == 365 and retention_days('0') == 0 and retention_days(90) == 90
    for invalid in ('30', '89', '-1', 'abc'):
        with pytest.raises(ValueError):
            retention_days(invalid)
    monkeypatch.delenv('CS_SECURITY_EVENT_RETENTION_DAYS', raising=False)
    assert retention_days() == 365
    monkeypatch.setenv('CS_SECURITY_EVENT_RETENTION_DAYS', '0')
    assert purge_security_events(SessionLocal) == 0


def test_daily_purge_runs_at_most_once_per_interval(monkeypatch):
    calls = []
    monkeypatch.setattr('app.security_retention.purge_security_events', lambda factory, current: calls.append(current))
    clock = [now()]
    purge = DailyPurge(SessionLocal, clock=lambda: clock[0])
    purge()
    clock[0] += timedelta(hours=23)
    purge()
    clock[0] += timedelta(hours=2)
    purge()
    assert len(calls) == 2
