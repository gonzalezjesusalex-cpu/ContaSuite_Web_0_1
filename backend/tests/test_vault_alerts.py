"""Renovación del gestor de contraseñas, fase 6: certificate alerts to the bell at 30 days, at 7 days and on the day
of expiration, once per certificate and threshold; only the active, complete certificate of each class alerts."""

from datetime import timedelta

from sqlalchemy import func, select

from sat_fixtures import pair
from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import setup
from app.alert_feed import SYSTEM, sync
from app.credential_alerts import candidates
from app.credential_models import alerts, certificates
from app.database import SessionLocal
from app.models import now
from app.security import utc

RFC = 'SSI260101AB1'
MASTER = 'Maestra-Sintetica-2026!'


def office(c):
    cid = company(c, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(c)
    assert c.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER}).status_code == 201
    return cid


def upload(c, cid, cer, key, **form):
    r = c.post(
        f'/api/credentials/companies/{cid}/certificates/upload',
        files={'cer': ('f.cer', cer, 'application/octet-stream'), 'key': ('f.key', key, 'application/octet-stream')},
        data={'password': 'Llave-Sintetica-1', 'cert_class': 'FIEL_EMPRESA', **form},
    )
    assert r.status_code == 201, r.text
    return r.json()['id']


def cert_kinds(db, stamp):
    return [r['kind'] for r in candidates(db, SYSTEM, stamp=stamp) if r['source'] == 'certificate']


def test_alerts_at_30_7_and_0_days(client):  # noqa: F811
    cid = office(client)
    cer, key, _ = pair(end=40)
    ident = upload(client, cid, cer, key)
    with SessionLocal() as db:
        end = utc(db.execute(select(certificates.c.valid_until).where(certificates.c.id == ident)).scalar())
        assert cert_kinds(db, end - timedelta(days=35)) == []  # more than 30 days: green, no alert
        assert cert_kinds(db, end - timedelta(days=20)) == ['fiel_expiring_30']
        assert cert_kinds(db, end - timedelta(days=5)) == ['fiel_expiring_7']
        assert cert_kinds(db, end - timedelta(hours=2)) == ['fiel_expiring_0']  # the day of expiration
        assert cert_kinds(db, end + timedelta(days=1)) == ['fiel_expired_0']


def test_only_the_active_complete_certificate_alerts_and_once(client):  # noqa: F811
    cid = office(client)
    old = pair(end=20, number='30001000000500000040', seed='vieja')
    first = upload(client, cid, old[0], old[1])
    with SessionLocal() as db:
        assert sync(db, force=True)
        assert sync(db, force=True)  # a second run does not repeat the alert
        rows = list(db.execute(select(alerts).where(alerts.c.reference == first)).mappings())
        assert [r['kind'] for r in rows] == ['fiel_expiring_30']
    # Replaced by a new FIEL: the previous one goes to the history and stops alerting.
    new = pair(end=400, number='30001000000500000041', seed='nueva')
    upload(client, cid, new[0], new[1], replace='true')
    with SessionLocal() as db:
        assert cert_kinds(db, now()) == []
        # An incomplete certificate («Faltan .cer y .key») has no dates and does not alert either.
        db.execute(certificates.update().where(certificates.c.id == first).values(active=True, fingerprint=None))
        db.commit()
        assert cert_kinds(db, now()) == []
        assert db.scalar(select(func.count()).select_from(alerts)) >= 1
