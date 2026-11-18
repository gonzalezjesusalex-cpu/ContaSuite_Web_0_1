import hashlib

from test_api import client  # noqa: F401  Isolated environment before app imports.
from test_agent_links import beat, bearer, office, pair  # noqa: F401
from test_accounts import login
from test_permissions import account
from app.database import SessionLocal
from app.models import VirtualFile, VirtualScan


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def row(path, content, section='cfdi', size=10, group='cfdi_xml', state='ok'):
    return {
        'p': path,
        's': size,
        'm': 1,
        'h': sha(content) if content else None,
        'g': group,
        'sec': section,
        'v': 'CFDI/2026/' + path.split('/')[-1],
        'st': state,
    }


def scan(c, token, company_id, batches, complete=True, finish=True):
    """One analysis as the agent does it: claim the job, send the file batches, deliver the result."""
    job = c.post('/api/jobs', json={'company_id': company_id, 'kind': 'scan_folder'})
    assert job.status_code == 201, job.text
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    assert claimed['id'] == job.json()['id']
    sent = []
    for n, batch in enumerate(batches):
        body = {'agent_id': 'pc-ana', 'seq': n, 'rows': batch, 'last': finish and n == len(batches) - 1, 'complete': complete}
        sent.append(c.post('/api/agent/jobs/' + claimed['id'] + '/index', headers=bearer(token), json=body))
    done = c.post(
        '/api/agent/jobs/' + claimed['id'] + '/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': {'files': []}},
    )
    assert done.status_code == 200
    return claimed['id'], sent


def summary(c, company_id):
    r = c.get(f'/api/companies/{company_id}/virtual-index/summary')
    assert r.status_code == 200, r.text
    return r.json()


def listing(c, company_id, **params):
    r = c.get(f'/api/companies/{company_id}/virtual-index/files', params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_first_scan_stores_every_file_in_batches(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    first = [row('A/1.xml', 'uno'), row('A/2.xml', 'dos')]
    second = [row('A/3.pdf', 'tres', group='cfdi_pdf')]
    _, sent = scan(c, token, companies['a'], [first, second])
    assert all(r.status_code == 200 for r in sent) and sent[-1].json()['total'] == 3
    data = summary(c, companies['a'])
    assert data['total'] == 3 and data['sections'] == {'cfdi': 3} and data['missing'] == 0
    assert (data['latest']['added'], data['latest']['complete']) == (3, True)
    files = listing(c, companies['a'], section='cfdi', q='.pdf')
    assert [f['path'] for f in files['rows']] == ['A/3.pdf'] and files['total'] == 1
    assert listing(c, companies['a'], change='added')['total'] == 3
    # Another company's index is empty and separate.
    assert summary(c, companies['b'])['total'] == 0


def test_changes_moves_missing_and_restored_are_told_apart(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    scan(c, token, a, [[row('A/1.xml', 'uno'), row('A/2.xml', 'dos'), row('A/3.xml', 'tres'), row('A/4.xml', 'cuatro')]])

    # 1.xml changes content, 2.xml is moved (same content, new path), 3.xml disappears, 5.xml is new, 4.xml stays.
    scan(c, token, a, [[row('A/1.xml', 'uno editado'), row('B/2.xml', 'dos'), row('A/4.xml', 'cuatro'), row('A/5.xml', 'cinco')]])
    latest = summary(c, a)['latest']
    assert (latest['added'], latest['changed'], latest['moved'], latest['missing'], latest['restored']) == (1, 1, 1, 1, 0)
    assert [f['path'] for f in listing(c, a, change='changed')['rows']] == ['A/1.xml']
    moved = listing(c, a, change='moved')['rows']
    assert [(f['path'], f['moved_from']) for f in moved] == [('B/2.xml', 'A/2.xml')]
    assert [f['path'] for f in listing(c, a, change='added')['rows']] == ['A/5.xml']
    gone = listing(c, a, missing=True)
    assert [f['path'] for f in gone['rows']] == ['A/3.xml'] and gone['rows'][0]['missing_since']
    assert summary(c, a)['total'] == 4 and summary(c, a)['missing'] == 1  # the moved file kept one row, not two

    # 3.xml comes back: restored, no longer missing.
    scan(c, token, a, [[row('A/1.xml', 'uno editado'), row('B/2.xml', 'dos'), row('A/3.xml', 'tres'), row('A/4.xml', 'cuatro'), row('A/5.xml', 'cinco')]])
    assert [f['path'] for f in listing(c, a, change='restored')['rows']] == ['A/3.xml']
    assert summary(c, a)['missing'] == 0 and summary(c, a)['latest']['missing'] == 0


def test_an_ambiguous_move_is_not_claimed(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    scan(c, token, a, [[row('A/x.xml', 'igual')]])
    # Two new files with the same content as the one that left: which one moved is unknowable.
    scan(c, token, a, [[row('B/y.xml', 'igual'), row('C/z.xml', 'igual')]])
    latest = summary(c, a)['latest']
    assert (latest['moved'], latest['added'], latest['missing']) == (0, 2, 1)


def test_an_incomplete_walk_never_marks_files_missing(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    scan(c, token, a, [[row('A/1.xml', 'uno'), row('A/2.xml', 'dos')]])
    scan(c, token, a, [[row('A/1.xml', 'uno')]], complete=False)
    latest = summary(c, a)['latest']
    assert latest['complete'] is False and latest['missing'] == 0
    assert summary(c, a)['missing'] == 0 and summary(c, a)['total'] == 2


def test_a_batch_sent_twice_and_an_unclosed_scan_change_nothing(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    batch = [row('A/1.xml', 'uno'), row('A/2.xml', 'dos')]
    job, _ = scan(c, token, a, [batch, batch], finish=False)  # same rows again, scan never closed (agent died)
    with SessionLocal() as db:
        assert db.query(VirtualFile).filter(VirtualFile.company_id == a).count() == 2  # not duplicated
        assert db.query(VirtualScan).filter(VirtualScan.job_id == job).one().finished_at is None
    # An unclosed scan is not "the latest": the summary has no comparison yet.
    assert summary(c, a)['latest'] is None


def test_agent_can_only_send_for_its_own_running_scan_and_valid_rows(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    c.post('/api/jobs', json={'company_id': companies['a'], 'kind': 'scan_folder'})
    claimed = c.post('/api/agent/pc-ana/claim', headers=bearer(token)).json()
    url = '/api/agent/jobs/' + claimed['id'] + '/index'
    ok = {'agent_id': 'pc-ana', 'seq': 0, 'rows': [row('A/1.xml', 'uno')], 'last': False}
    assert c.post(url, headers=bearer(token), json={**ok, 'agent_id': 'otro'}).status_code in (403, 409)
    bad_hash = {**ok, 'rows': [{**row('A/1.xml', 'uno'), 'h': 'no-es-un-hash'}]}
    assert c.post(url, headers=bearer(token), json=bad_hash).status_code == 422
    assert c.post(url, headers=bearer(token), json={**ok, 'rows': [{**row('A/1.xml', 'uno'), 'x': 1}]}).status_code == 422
    assert c.post(url, headers=bearer(token), json={**ok, 'rows': [row(f'A/{n}.xml', str(n)) for n in range(401)]}).status_code == 422
    assert c.post(url, headers=bearer(token), json=ok).status_code == 200
    # Once the result is delivered the job is closed: nothing more can be added to it.
    c.post(
        '/api/agent/jobs/' + claimed['id'] + '/result',
        headers=bearer(token),
        json={'agent_id': 'pc-ana', 'status': 'completed', 'result': {}},
    )
    assert c.post(url, headers=bearer(token), json=ok).status_code == 409


def test_reading_the_index_follows_company_access(office):  # noqa: F811
    c, companies, _ = office
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    scan(c, token, companies['a'], [[row('A/1.xml', 'uno')]])
    login(c)
    account(c, 'sin_acceso', 'auxiliar', [(companies['b'], 'read')])
    login(c, 'sin_acceso')
    assert c.get(f"/api/companies/{companies['a']}/virtual-index/summary").status_code == 404  # no grant: not even listed
    assert c.get(f"/api/companies/{companies['b']}/virtual-index/summary").status_code == 200
    assert c.get(f"/api/companies/{companies['b']}/virtual-index/files", params={'change': 'raro'}).status_code == 422

