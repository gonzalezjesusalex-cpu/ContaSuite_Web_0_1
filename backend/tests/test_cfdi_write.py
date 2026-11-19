"""Writing accepted CFDI into the company folder (cambio 5.7): never overwrite, verify, cancel, safe destinations."""

import hashlib
import threading

from test_api import A, client, company  # noqa: F401
from test_organizador_api import RFC, run, xml
from test_organizador_review import U1

from app.cfdi_write import destination_problem, month_dir, write_files


def entry(name='a.xml', period='2026-04', kind='Emitidos', data=b'<x/>'):
    return {'id': name, 'name': name, 'period': period, 'kind': kind, 'sha256': hashlib.sha256(data).hexdigest()}, data


def test_structure_copy_verification_and_duplicates_never_overwrite(tmp_path):
    first, data = entry()
    recibido, data2 = entry('b.xml', '2026-11', 'Recibidos', b'<y/>')
    store = {'a.xml': data, 'b.xml': data2}
    out = write_files([first, recibido], tmp_path, store.__getitem__)
    assert (out['escritos'], out['duplicados'], out['errores']) == (2, 0, 0)
    assert (tmp_path / '04.- ABRIL' / 'EMITIDOS' / 'a.xml').read_bytes() == data
    assert (tmp_path / '11.- NOVIEMBRE' / 'RECIBIDOS' / 'b.xml').read_bytes() == data2
    # A file with that name exists (even in other letters, as Windows sees it): Duplicado, content untouched.
    (tmp_path / '04.- ABRIL' / 'EMITIDOS' / 'a.xml').write_bytes(b'distinto')
    again = write_files([{**first, 'name': 'A.XML'}], tmp_path, store.__getitem__)
    assert again['duplicados'] == 1 and again['escritos'] == 0 and again['detalle'][0]['state'] == 'Duplicado'
    assert (tmp_path / '04.- ABRIL' / 'EMITIDOS' / 'a.xml').read_bytes() == b'distinto'
    assert not list(tmp_path.rglob('*.part'))


def test_wrong_content_bad_names_and_cancellation(tmp_path):
    item, _ = entry()
    out = write_files([item], tmp_path, lambda _id: b'otro contenido')
    assert out['errores'] == 1 and out['escritos'] == 0 and not list(tmp_path.rglob('*.xml'))
    assert not list(tmp_path.rglob('*.part'))
    traversal, data = entry('..\\x.xml')
    assert write_files([traversal], tmp_path, lambda _id: data)['errores'] == 1
    stop = threading.Event()
    first, data = entry('1.xml')
    second, data2 = entry('2.xml', data=b'<z/>')
    seen = []

    def fetch(item_id):
        stop.set()  # the user cancels while the first file is being fetched
        seen.append(item_id)
        return {'1.xml': data, '2.xml': data2}[item_id]

    out = write_files([first, second], tmp_path / 'c', fetch, stop)
    assert out['cancelado'] is True and out['escritos'] == 1 and seen == ['1.xml']


def test_month_dir_and_destination_rules():
    assert str(month_dir('2026-04', 'Emitidos')).replace('\\', '/') == '04.- ABRIL/EMITIDOS'
    for bad in (('2026-13', 'Emitidos'), ('2026-04', 'Otros')):
        try:
            month_dir(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    roots = ['C:\\Empresas']
    assert destination_problem('C:\\Empresas\\A\\2026', 'C:\\Empresas\\A', roots) == ''
    assert destination_problem('C:\\Empresas\\B\\2026', 'C:\\Empresas\\A', roots) == 'destino_fuera_de_raices'
    assert destination_problem('C:\\Otro\\2026', 'C:\\Otro', roots) == 'destino_fuera_de_raices'
    assert destination_problem('', 'C:\\Empresas\\A', roots) == 'destino_invalido'


def test_api_requires_confirmation_accepted_files_and_a_linked_agent(client):  # noqa: F811
    c = company(client).json()
    base = run(client, {f'Base/Emitidos/{RFC}/2026-04/f.xml': xml(U1)}, c['id'])
    assert client.post(base + '/write-folder', headers=A, json={}).status_code == 422  # no confirmation
    nothing = client.post(base + '/write-folder', headers=A, json={'confirm': True})
    assert nothing.status_code == 422 and 'aceptados' in nothing.json()['detail']
    client.post(base + '/save', headers=A, json={})
    # Accepted now, but the company has no folder and no agent is linked: the screen explains instead of writing.
    refused = client.get(base + '/write-folder-preview', headers=A)
    assert refused.status_code == 422 and 'carpeta' in refused.json()['detail']
