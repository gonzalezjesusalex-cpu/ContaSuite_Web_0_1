"""The virtual branch reads one level with SQL (counts and LIMIT) instead of loading every row of the company."""

from collections import Counter

import pytest
from sqlalchemy import event

from test_agent_links import office  # noqa: F401
from test_api import client  # noqa: F401  Isolated environment before app imports.
from app.database import SessionLocal
from app.models import VirtualFile


def add_files(company_id, paths):
    with SessionLocal.begin() as db:
        for i, virtual_path in enumerate(paths):
            db.add(
                VirtualFile(
                    company_id=company_id,
                    path='orig/' + virtual_path,
                    name=virtual_path.rsplit('/', 1)[-1],
                    group_key='cfdi_xml',
                    section='cfdi',
                    virtual_path=virtual_path,
                    scan_id='scan-1',
                    sha256=None,
                )
            )


def tree(c, company_id, **params):
    result = c.get(f'/api/companies/{company_id}/virtual-index/tree', params=params)
    assert result.status_code == 200, result.text
    return result.json()


def folders_today(paths, prefix):
    """What the previous implementation counted: files per first folder below the prefix."""
    base = prefix + '/' if prefix else ''
    counts = Counter()
    for path in paths:
        if not path.startswith(base):
            continue
        rest = path[len(base) :].strip('/')
        if '/' in rest:
            counts[rest.split('/', 1)[0]] += 1
    return [{'name': n, 'path': base + n, 'files': k} for n, k in sorted(counts.items())]


@pytest.fixture()
def loaded():
    """How many VirtualFile objects the ORM materializes while the block runs."""
    seen = []
    listener = lambda target, context: seen.append(target)  # noqa: E731
    event.listen(VirtualFile, 'load', listener)
    yield seen
    event.remove(VirtualFile, 'load', listener)


def test_a_level_of_600_files_returns_500_without_loading_them_all(office, loaded):  # noqa: F811
    c, companies, _ = office
    a = companies['a']
    add_files(a, [f'CFDI/JULIO/f{i:03d}.xml' for i in range(600)])
    del loaded[:]
    data = tree(c, a, prefix='CFDI/JULIO')
    assert len(data['files']) == 500 and data['more'] is True and data['total'] == 600
    assert data['folders'] == [] and data['prefix'] == 'CFDI/JULIO'
    assert data['files'][0]['name'] == 'f000.xml' and data['files'][-1]['name'] == 'f499.xml'
    assert 0 < len(loaded) <= 501  # never the 600 rows of the level (nor the company's whole index)


def test_folder_counts_and_totals_match_the_previous_behavior(office, loaded):  # noqa: F811
    c, companies, _ = office
    a, b = companies['a'], companies['b']
    paths = (
        [f'CFDI_X/f{i:03d}.xml' for i in range(520)]
        + [f'CFDI_X/EMITIDOS/e{i}.xml' for i in range(3)]
        + [f'CFDI_X/RECIBIDOS/2026/r{i}.xml' for i in range(2)]
        + ['CFDIyX/ajeno.xml', 'Impuestos/1.pdf', 'Impuestos/2026/2.pdf', 'raiz.xml']
    )
    add_files(a, paths)
    add_files(b, ['CFDI_X/de-otra-empresa.xml'])  # another company never mixes in

    del loaded[:]
    data = tree(c, a, prefix='CFDI_X')
    assert data['folders'] == folders_today(paths, 'CFDI_X')
    assert [f['files'] for f in data['folders']] == [3, 2]
    assert len(data['files']) == 500 and data['more'] is True and data['total'] == 525  # every file below the prefix
    assert len(loaded) <= 501

    root = tree(c, a)
    assert root['folders'] == folders_today(paths, '')
    assert [f['name'] for f in root['files']] == ['raiz.xml'] and root['more'] is False
    assert root['total'] == len(paths)

    deeper = tree(c, a, prefix='CFDI_X/RECIBIDOS')
    assert deeper['folders'] == folders_today(paths, 'CFDI_X/RECIBIDOS') and deeper['files'] == []


def test_search_lists_every_match_below_the_prefix_without_folders(office, loaded):  # noqa: F811
    c, companies, _ = office
    a = companies['a']
    add_files(a, ['CFDI/JULIO/factura-1.xml', 'CFDI/JULIO/EMITIDOS/factura-2.xml', 'CFDI/JULIO/otro.xml', 'X/factura-3.xml'])
    del loaded[:]
    data = tree(c, a, prefix='CFDI', q='factura')
    assert data['folders'] == [] and data['total'] == 2 and data['more'] is False
    assert [f['name'] for f in data['files']] == ['factura-2.xml', 'factura-1.xml']
    assert len(loaded) <= 2
