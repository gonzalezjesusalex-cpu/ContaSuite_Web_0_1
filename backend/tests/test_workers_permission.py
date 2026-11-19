"""«trabajadores.ver»: the workers' files (personal data) need their own action, never part of a template."""

from test_virtual_copy import analyze, beat, client, files, folder, load_agent, login, office, pair, summary  # noqa: F401
from test_permissions import account
from app.permissions import ACTIONS, TEMPLATES, WRITE_ACTIONS, company_actions, catalog

COPY = ['cfdi', 'impuestos', 'trabajadores']


def tree(c, company_id):
    return c.get(f'/api/companies/{company_id}/virtual-index/tree').json()


def tree_files(c, company_id):
    data = tree(c, company_id)
    return sum(f['files'] for f in data['folders']) + len(data['files'])


def latest(c, company_id):
    return c.get(f'/api/companies/{company_id}/jobs/latest', params={'kind': 'scan_folder'}).json()


def test_action_is_explicit_only():
    assert 'trabajadores.ver' in WRITE_ACTIONS and 'trabajadores.ver' in ACTIONS
    assert all('trabajadores.ver' not in t['actions'] for t in TEMPLATES.values())
    assert 'trabajadores.ver' not in company_actions('auxiliar', True)  # not part of the former write grant either
    assert 'trabajadores.ver' not in company_actions('auxiliar', False, set())
    assert 'trabajadores.ver' in company_actions('auxiliar', False, {'trabajadores.ver'})
    assert {'id': 'trabajadores.ver', 'label': 'Ver expedientes de trabajadores (datos personales)'} in catalog()[
        'actions'
    ]


def test_workers_files_need_the_explicit_action(office, folder):  # noqa: F811
    c, companies, _ = office
    root, company = folder
    (company / 'TRABAJADORES' / 'JUAN PEREZ').mkdir(parents=True)
    (company / 'TRABAJADORES' / 'JUAN PEREZ' / 'INE.pdf').write_bytes(b'%PDF-1.4 ine de juan')
    agent = load_agent()
    a = companies['a']
    account(c, 'consulta', 'auxiliar', [(a, 'read')])  # «Solo consulta»
    account(c, 'con_permiso', 'auxiliar', [(a, 'read')], actions=[(a, 'trabajadores.ver')])

    login(c, 'ana')  # a contador with write access has every action of the company
    _, token = pair(c)
    beat(c, token)
    analyze(c, token, a, agent, root, company, copy=COPY)
    full_total = tree_files(c, a)
    workers = files(c, a, section='trabajadores')['rows']
    assert [w['name'] for w in workers] == ['INE.pdf'] and 'trabajadores' in summary(c, a)['sections']
    url = f'/api/companies/{a}/virtual-index/files/{workers[0]["id"]}/content'
    assert c.get(url).content == b'%PDF-1.4 ine de juan'
    assert latest(c, a)['result']['trabajadores']['total'] == 1

    login(c, 'consulta')
    assert 'trabajadores' not in summary(c, a)['sections']
    assert files(c, a, section='trabajadores')['rows'] == []
    assert all(f['section'] != 'trabajadores' for f in files(c, a, limit=200)['rows'])
    assert files(c, a, q='INE')['rows'] == []
    assert tree_files(c, a) == full_total - 1  # the worker's file is not in the virtual branch
    assert c.get(url).status_code == 403  # nor can its internal copy be downloaded
    assert c.get(url, params={'preview': 'true'}).status_code == 403
    result = latest(c, a)['result']
    assert 'trabajadores' not in result and result['summary']['total'] >= 1
    group = next(g for g in result['summary']['groups'] if g['key'] == 'trabajadores')
    assert group['examples'] == [] and group['sensitive'] is True
    assert 'JUAN' not in str(result).upper()  # no name or path of a worker anywhere in the analysis

    login(c, 'con_permiso')
    assert files(c, a, section='trabajadores')['rows'][0]['name'] == 'INE.pdf'
    assert c.get(url).content == b'%PDF-1.4 ine de juan'
    assert tree_files(c, a) == full_total
    assert latest(c, a)['result']['trabajadores']['total'] == 1

    login(c, 'admin')  # the administrator always has it
    assert c.get(url).status_code == 200 and 'trabajadores' in summary(c, a)['sections']
