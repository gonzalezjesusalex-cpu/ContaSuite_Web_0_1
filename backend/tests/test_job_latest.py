"""/api/state carries job summaries only; every company gets its own latest job (with result) from its own endpoint."""

from datetime import datetime, timedelta, timezone

from test_agent_links import office  # noqa: F401
from test_accounts import login
from test_api import client  # noqa: F401  Isolated environment before app imports.
from test_permissions import account
from app.database import SessionLocal
from app.models import Job

ROWS = [{'u': f'UUID-{i}', 'f': '2026-07-02'} for i in range(300)]
BIG = {
    'summary': {'total': 7, 'bytes': 70, 'groups': [], 'extensions': {}},
    'files': [{'name': 'a.xml'}] * 7,
    'cfdi': {'rows': ROWS, 'total': 300},
    'trabajadores': {'workers': [], 'total': 0},
    'warnings': ['Incidencia de recorrido: access_denied'],
    'truncated': False,
    'incomplete': True,
}


def add_jobs(company_id, count, kind='scan_folder', start=0, result=None, status='completed'):
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    with SessionLocal.begin() as db:
        for i in range(count):
            db.add(
                Job(
                    company_id=company_id,
                    agent_id='pc-ana',
                    kind=kind,
                    status=status,
                    payload={'folder': r'C:\Empresas\X'},
                    result=dict(result if result is not None else BIG),
                    created_at=base + timedelta(seconds=start + i),
                )
            )


def latest(c, company_id, **params):
    return c.get(f'/api/companies/{company_id}/jobs/latest', params={'kind': 'scan_folder', **params})


def test_latest_job_of_a_company_survives_sixty_jobs_of_another(office):  # noqa: F811
    c, companies, _ = office
    a, b = companies['a'], companies['b']
    add_jobs(a, 1, start=0)
    add_jobs(b, 60, start=10)

    jobs = c.get('/api/state').json()['jobs']
    assert len(jobs) == 50 and all(j['company_id'] == b for j in jobs)  # A's analysis is no longer in the list
    for job in jobs:  # and no result of an analysis travels in the polled state
        assert not {'cfdi', 'files', 'summary', 'trabajadores'} & set(job['result'])
        assert job['result']['total'] == 7 and job['result']['incomplete'] is True

    got = latest(c, a)
    assert got.status_code == 200
    body = got.json()
    assert body['company_id'] == a and body['result']['cfdi']['total'] == 300
    assert len(body['result']['cfdi']['rows']) == 300 and body['result']['summary']['total'] == 7
    assert latest(c, b).json()['id'] != body['id']


def test_latest_by_kind_and_status(office):  # noqa: F811
    c, companies, _ = office
    a = companies['a']
    add_jobs(a, 1, start=0)
    add_jobs(a, 1, start=5, result={'error': 'x'}, status='failed')
    add_jobs(a, 1, kind='export_virtual', start=9, result={'mode': 'preview', 'destination': 'D:\\x'})
    assert latest(c, a).json()['status'] == 'failed'
    assert latest(c, a, status='completed').json()['result']['cfdi']['total'] == 300
    assert latest(c, a, kind='export_virtual').json()['result']['destination'] == 'D:\\x'
    assert latest(c, a, kind='sat_declaraciones').json() is None
    assert latest(c, a, kind='otro').status_code == 422
    assert latest(c, a, status='raro').status_code == 422


def test_latest_job_respects_company_access_and_hides_the_payload(office):  # noqa: F811
    c, companies, ana = office
    a, b = companies['a'], companies['b']
    add_jobs(a, 1)
    add_jobs(b, 1)
    admin_view = latest(c, a).json()
    assert admin_view['payload']['folder']  # only administrators see paths
    account(c, 'ben', 'auxiliar', [(b, 'read')])

    login(c, 'ben')
    assert latest(c, a).status_code in (403, 404)  # a company he cannot see
    assert latest(c, 'no-existe').status_code in (403, 404)
    mine = latest(c, b)
    assert mine.status_code == 200 and 'payload' not in mine.json()
    assert all('payload' not in j for j in c.get('/api/state').json()['jobs'])

