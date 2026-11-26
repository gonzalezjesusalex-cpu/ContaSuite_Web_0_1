"""Dashboard principal › Alertas (Configuración) and the bell: one chronological list with its lifecycle.

Synthetic companies only. A company without a responsible raises `missing_responsible`; dismissing, snoozing and
fixing the condition move the alert to the history with its user, date and reason.
"""

from datetime import date, timedelta

from sqlalchemy import update

from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import setup
from app import alert_feed
from app.database import SessionLocal
from app.models import Company


def feed(c, **params):
    alert_feed._last_sync[0] = 0  # evaluate on every read in these tests
    result = c.get('/api/integral/alert-feed', params=params)
    assert result.status_code == 200, result.text
    return result.json()


def missing(data, cid):
    return next(a for a in data['alerts'] if a['company_id'] == cid and a['kind'] == 'missing_responsible')


def test_alert_feed_lists_dismisses_snoozes_and_resolves(client):  # noqa: F811
    first = company(client, name='Alfa Sintética', rfc='ASI010101AB1').json()['id']
    second = company(client, name='Beta Sintética', rfc='BSI010101AB1').json()['id']
    third = company(client, name='Gama Sintética', rfc='GSI010101AB1').json()['id']
    setup(client)

    data = feed(client)
    assert data['lifecycle_available']
    assert {first, second, third} <= {a['company_id'] for a in data['alerts'] if a['kind'] == 'missing_responsible'}
    alert = missing(data, first)
    assert alert['state'] == 'active' and alert['priority'] == 'medium' and alert['company_name'] == 'Alfa Sintética'
    assert data['active_total'] >= 3 and 'missing_responsible' in data['kinds']
    # Filters and text search narrow the list; paging keeps the total.
    assert {a['company_id'] for a in feed(client, company_id=second)['alerts']} == {second}
    assert {a['company_id'] for a in feed(client, q='gama')['alerts']} == {third}
    assert feed(client, severity='high')['total'] == 0
    page = feed(client, limit=1)
    assert len(page['alerts']) == 1 and page['total'] == data['total']

    # Descartar: a short reason is refused; with a reason it goes to the history as dismissed.
    url = '/api/integral/alerts/' + alert['id'] + '/lifecycle'
    short = {'state': 'dismissed', 'revision': alert['revision'], 'reason': 'no'}
    assert client.put(url, json=short).status_code == 422
    done = client.put(url, json={**short, 'reason': 'Empresa en baja'})
    assert done.status_code == 200, done.text
    data = feed(client)
    assert alert['id'] not in {a['id'] for a in data['alerts']}
    closed = next(a for a in feed(client, view='history')['alerts'] if a['id'] == alert['id'])
    assert closed['state'] == 'dismissed' and closed['reason'] == 'Empresa en baja'
    assert closed['changed_by'] == 'Administración de prueba' and closed['changed_at']
    # The condition still holds: evaluating again does not reopen it.
    assert alert['id'] not in {a['id'] for a in feed(client)['alerts']}

    # Posponer: hidden from the active list until the date.
    snooze = missing(data, second)
    until = (date.today() + timedelta(days=3)).isoformat()
    result = client.put(
        '/api/integral/alerts/' + snooze['id'] + '/lifecycle',
        json={'state': 'snoozed', 'revision': snooze['revision'], 'reason': 'Pospuesta', 'snooze_until': until},
    )
    assert result.status_code == 200, result.text
    assert snooze['id'] not in {a['id'] for a in feed(client)['alerts']}
    later = next(a for a in feed(client, view='history')['alerts'] if a['id'] == snooze['id'])
    assert later['state'] == 'snoozed' and later['snooze_until'] == until

    # Resolución automática: once the company has a responsible the alert closes as resolved (obsolete).
    resolved = missing(data, third)
    with SessionLocal() as db:
        admin = client.get('/api/auth/me').json()['id']
        db.execute(update(Company).where(Company.id == third).values(accountant_id=admin, accountant='Admin'))
        db.commit()
    data = feed(client)
    assert resolved['id'] not in {a['id'] for a in data['alerts']}
    gone = next(a for a in feed(client, view='history')['alerts'] if a['id'] == resolved['id'])
    assert gone['state'] == 'obsolete' and gone['changed_by'] == 'Sistema' and gone['reason'] == ''


def test_alert_feed_requires_a_session_and_validates_filters(client):  # noqa: F811
    assert client.get('/api/integral/alert-feed').status_code == 401
    setup(client)
    assert client.get('/api/integral/alert-feed', params={'view': 'all'}).status_code == 422
    assert client.get('/api/integral/alert-feed', params={'limit': 500}).status_code == 422
    empty = feed(client)
    assert empty['alerts'] == [] and empty['active_total'] == 0 and empty['active_high'] == 0
