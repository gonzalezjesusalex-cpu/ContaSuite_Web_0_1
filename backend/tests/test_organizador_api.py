"""Organizador CFDI against the expediente: preview, partial save, conflicts and review decisions (5.1, 5.4, 5.5)."""

import csv
import io
import zipfile

from test_api import A, client, company  # noqa: F401
from test_organizador import RFC
from test_organizador_review import U1, U2, U3, U4, pdf

OTHER_RFC = 'BBB010101BBB'
BASE = 'Base/'


def xml(uuid, emisor=RFC, receptor=OTHER_RFC, fecha='2026-04-10', folio='1'):
    return (
        '<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" '
        f'TipoDeComprobante="I" Fecha="{fecha}T10:00:00" Folio="{folio}" Total="10.00">'
        f'<c:Emisor Rfc="{emisor}"/><c:Receptor Rfc="{receptor}"/>'
        f'<c:Complemento><t:TimbreFiscalDigital UUID="{uuid}"/></c:Complemento></c:Comprobante>'
    ).encode()


def run(client, entries, company_id, rfc=RFC, months='4,5'):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, data in entries.items():
            z.writestr(name, data)
    reply = client.post(
        '/api/organizador/runs',
        headers=A,
        files={'files': ('entrada.zip', stream.getvalue(), 'application/zip')},
        data={
            'rfc': rfc,
            'year': '2026',
            'months': months,
            'kinds': 'Emitidos,Recibidos',
            'extensions': '.xml,.pdf',
            'company_id': company_id,
        },
    )
    assert reply.status_code == 202, reply.text
    return '/api/organizador/runs/' + reply.json()['id']


def entries_a():
    folder = f'{BASE}Emitidos/{RFC}/2026-04/'
    return {
        folder + 'ok.xml': xml(U1),
        folder + 'ok.pdf': pdf('Factura', U1),
        folder + 'mes.xml': xml(U2, fecha='2026-05-02'),  # dated in May, filed in April
        f'{BASE}Recibidos/{RFC}/2026-04/ajena.xml': xml(U3, emisor=OTHER_RFC, receptor=OTHER_RFC),
    }


def test_partial_save_blocks_incoherent_files_and_keeps_audit(client):  # noqa: F811
    c = company(client).json()
    base = run(client, entries_a(), c['id'])
    detail = client.get(base, headers=A).json()
    assert detail['run']['summary']['incoherent'] == 2 and len(detail['omitted']) == 0
    preview = client.get(base + '/save-preview', headers=A).json()
    assert preview['counts'] == {'nuevo': 2, 'ya_registrado': 0, 'revision': 0, 'bloqueado': 2}

    saved = client.post(base + '/save', headers=A, json={}).json()
    states = {i['name']: i['state'] for i in saved['items']}
    assert states == {'ok.xml': 'saved', 'ok.pdf': 'saved', 'mes.xml': 'bloqueado', 'ajena.xml': 'bloqueado'}
    docs = client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']
    assert {(d['name'], d['document_type'], d['period']) for d in docs} == {
        ('ok.xml', 'cfdi', '2026-04'),
        ('ok.pdf', 'cfdi_pdf', '2026-04'),
    }
    # Saving again changes nothing: saved files stay saved and blocked ones stay waiting.
    again = client.post(base + '/save', headers=A, json={}).json()
    assert {i['name']: i['state'] for i in again['items']} == states
    assert len(client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']) == 2

    queue = client.get('/api/organizador/companies/' + c['id'] + '/review', headers=A).json()
    assert {p['name'] for p in queue['pending']} == {'mes.xml', 'ajena.xml'}
    assert {p['period']: (p['xml'], p['pdf'], p['en_revision']) for p in queue['periods']} == {'2026-04': (1, 1, 2)}

    mes = next(p for p in queue['pending'] if p['name'] == 'mes.xml')
    ajena = next(p for p in queue['pending'] if p['name'] == 'ajena.xml')
    assert (
        client.post(
            '/api/organizador/items/' + ajena['id'] + '/resolve', headers=A, json={'action': 'save'}
        ).status_code
        == 422
    )
    # The reviewer, not the folder, decides the period of a file whose XML disagrees.
    done = client.post(
        '/api/organizador/items/' + mes['id'] + '/resolve', headers=A, json={'action': 'save', 'period': 'xml'}
    ).json()
    assert (
        done['state'] == 'saved' and done['decided_period'] == '2026-05' and done['decided_by'] and done['decided_at']
    )
    dismissed = client.post('/api/organizador/items/' + ajena['id'] + '/resolve', headers=A, json={'action': 'dismiss'})
    assert dismissed.json()['state'] == 'descartado'
    docs = client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']
    assert {(d['name'], d['period']) for d in docs} >= {('mes.xml', '2026-05')}
    assert client.get('/api/organizador/companies/' + c['id'] + '/review', headers=A).json()['pending'] == []

    # The audit CSV carries UUID, incoherence, pair and saved state.
    client.post(base + '/generate', headers=A)
    rows = list(
        csv.DictReader(io.StringIO(client.get(base + '/download?kind=csv', headers=A).content.decode('utf-8-sig')))
    )
    by = {r['source'].rsplit('/', 1)[-1]: r for r in rows}
    assert (
        by['ok.xml']['uuid'] == U1
        and by['ok.xml']['guardado'] == 'guardado'
        and by['ok.xml']['pareja'].endswith('ok.pdf')
    )
    assert by['mes.xml']['incoherencia'] == 'periodo_distinto' and by['mes.xml']['guardado'] == 'guardado'
    assert by['ajena.xml']['guardado'] == 'descartado'


def test_same_content_elsewhere_and_same_uuid_with_other_content_go_to_review(client):  # noqa: F811
    a = company(client).json()
    b = company(client, name='Beta SA', rfc=OTHER_RFC).json()
    first = run(client, {f'{BASE}Emitidos/{RFC}/2026-04/f.xml': xml(U4)}, a['id'])
    client.post(first + '/save', headers=A, json={})

    # The same bytes filed by the other company (it is the receiver there): same SHA linked elsewhere -> review.
    other = run(client, {f'{BASE}Recibidos/{OTHER_RFC}/2026-04/f.xml': xml(U4)}, b['id'], rfc=OTHER_RFC)
    counts = client.get(other + '/save-preview', headers=A).json()['counts']
    assert counts == {'nuevo': 0, 'ya_registrado': 0, 'revision': 1, 'bloqueado': 0}

    # The same file again for the first company: already registered.
    again = run(client, {f'{BASE}Emitidos/{RFC}/2026-04/f.xml': xml(U4)}, a['id'])
    assert client.get(again + '/save-preview', headers=A).json()['counts']['ya_registrado'] == 1

    # The same UUID with different content never merges or overwrites: review.
    changed = run(client, {f'{BASE}Emitidos/{RFC}/2026-04/f.xml': xml(U4, folio='999')}, a['id'])
    preview = client.get(changed + '/save-preview', headers=A).json()
    assert preview['counts']['revision'] == 1
    assert list(preview['files'].values())[0]['reasons'] == ['uuid_contenido_distinto']
    saved = client.post(changed + '/save', headers=A, json={}).json()
    assert [i['state'] for i in saved['items']] == ['revision']
    assert len(client.get('/api/storage/documents', headers=A, params={'company_id': a['id']}).json()['items']) == 1


def test_company_rfc_must_match_and_suggestion_follows_last_period(client):  # noqa: F811
    a = company(client).json()
    wrong = run(
        client, {f'{BASE}Emitidos/{OTHER_RFC}/2026-04/f.xml': xml(U1, emisor=OTHER_RFC)}, a['id'], rfc=OTHER_RFC
    )
    detail = client.get(wrong, headers=A).json()
    assert any('no es el de la empresa' in w for w in detail['run']['warnings'])
    assert client.get(wrong + '/save-preview', headers=A).status_code == 422
    first = client.get('/api/organizador/companies/' + a['id'] + '/suggestion', headers=A).json()
    assert first['rfc'] == RFC and first['last_period'] is None

    good = run(client, entries_a(), a['id'], months='4')
    client.post(good + '/generate', headers=A)
    nxt = client.get('/api/organizador/companies/' + a['id'] + '/suggestion', headers=A).json()
    assert nxt == {'rfc': RFC, 'year': 2026, 'months': [5], 'last_period': '2026-04'}
