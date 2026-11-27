"""API de Declara tras el rediseño (fase 2): ejercicio, estados de mes, panel «Resolver archivo», ajustes y bitácora."""

import csv
import io
import zipfile
from datetime import date

from reportlab.pdfgen import canvas

from test_api import client, A, company  # noqa: F401  Isolated environment before app imports.
from test_declara import pdf, upload
from app import declara_rules as rules
from app.database import SessionLocal
from app.models import Company


def image_pdf():
    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    c.rect(40, 40, 200, 200, fill=1)
    c.save()
    return stream.getvalue()


def start(client, entries, **kw):
    cid = company(client).json()['id']
    response = upload(client, cid, entries, **kw)
    assert response.status_code == 202, response.text
    base = '/api/declara/runs/' + response.json()['id']
    return cid, base, client.get(base, headers=A).json()


def row(detail, suffix):
    return next(r for r in detail['records'] if r['path'].endswith(suffix))


def test_year_month_states_and_start_date(client):
    cid, base, detail = start(client, {'decl.pdf': pdf(), 'acuse.pdf': pdf('ACUSE')}, year='2026')
    run = detail['run']
    assert run['year'] == 2026 and run['mode'] == 'subir'
    months = run['months']['2026']
    assert months['OCTUBRE']['estado'] == rules.COMPLETO and months['OCTUBRE']['declaracion']
    assert months['ENERO']['estado'] == rules.NO_APLICA_ALTA and not months['ENERO']['aplicable']
    assert run['summary']['alta'] == {'fecha': '2026-03-31', 'origen': 'RFC'}
    assert run['summary']['due_day'] == 17
    # La Constancia manda sobre el RFC.
    with SessionLocal() as db:
        db.get(Company, cid).operations_start = date(2026, 6, 1)
        db.commit()
    response = upload(client, cid, {'decl.pdf': pdf(), 'acuse.pdf': pdf('ACUSE')}, year='2026')
    run = client.get('/api/declara/runs/' + response.json()['id'], headers=A).json()['run']
    assert run['summary']['alta'] == {'fecha': '2026-06-01', 'origen': 'Constancia'}
    assert run['months']['2026']['MAYO']['estado'] == rules.NO_APLICA_ALTA
    assert upload(client, cid, {'a.pdf': pdf()}, year='1999').status_code == 422
    listed = client.get(f'/api/declara/runs?company_id={cid}&year=2026', headers=A).json()
    assert len(listed) == 2 and client.get(f'/api/declara/runs?company_id={cid}&year=2020', headers=A).json() == []


def test_other_year_and_selected_year_without_pdfs(client):
    _cid, _base, detail = start(client, {'decl.pdf': pdf(), 'acuse.pdf': pdf('ACUSE')}, year='2025')
    run = detail['run']
    assert run['summary']['other_year'] == 2 and all(r['other_year'] for r in detail['records'])
    assert any('ejercicio distinto' in w for w in run['warnings'])
    assert set(run['months']) == {'2025'} and len(run['months']['2025']) == 12
    assert run['months']['2025']['OCTUBRE']['estado'] == rules.VENCIDO


def test_identical_copies_are_not_copied_twice(client):
    same = pdf()
    _cid, base, detail = start(client, {'a.pdf': same, 'copia.pdf': same, 'acuse.pdf': pdf('ACUSE')})
    assert detail['run']['summary']['identical'] == 1
    copy = row(detail, 'copia.pdf')
    assert copy['status'] == rules.COPIA and copy['detail'] == 'Igual a a.pdf'
    assert client.post(base + '/generate', headers=A, json={'revision': 0}).status_code == 202
    with zipfile.ZipFile(io.BytesIO(client.get(base + '/download', headers=A).content)) as z:
        assert len(z.namelist()) == 2


def test_manual_rename_preview_resolve_and_undo(client):
    _cid, base, detail = start(client, {'decl.pdf': pdf(), 'escaneo.pdf': image_pdf()}, year='2026')
    scanned = row(detail, 'escaneo.pdf')
    assert scanned['status'] == 'OMITIDO' and 'imagen, sin texto' in scanned['detail']
    assert detail['run']['months']['2026']['OCTUBRE']['estado'] != rules.COMPLETO
    change = {'index': scanned['index'], 'action': 'manual'}
    bad = client.post(base + '/preview', headers=A, json={**change, 'name': 'acuse: octubre', 'count': False}).json()
    assert bad['errors'] and bad['name'] == 'acuse: octubre.pdf'
    taken = '10.- DECLARACION ISR E IVA OCTUBRE ARKOS'
    assert client.post(base + '/preview', headers=A, json={**change, 'name': taken, 'count': False}).json()['errors']
    plain = client.post(base + '/preview', headers=A, json={**change, 'name': 'acuse octubre', 'count': False}).json()
    assert not plain['errors'] and plain['warnings'] == ['El nombre no sigue el estándar del despacho.']
    assert plain['effect'] is None  # no cuenta en el control: no cambia ningún mes
    good = {**change, 'name': '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS', 'choice': 'ACUSE NORMAL', 'month': 'OCTUBRE'}
    seen = client.post(base + '/preview', headers=A, json=good).json()
    assert seen['standard']['texto'] == "se detectó '10.2.-' = acuse normal de octubre"
    assert seen['effect'] == {'month': 'OCTUBRE', 'before': seen['effect']['before'], 'after': rules.COMPLETO}
    missing = client.post(base + '/preview', headers=A, json={**good, 'choice': ''}).json()
    assert missing['errors'] == ['Elige documento, tipo y mes para contarlo en el control mensual.']
    # La vista previa no guarda nada.
    assert client.get(base, headers=A).json()['run']['revision'] == 0
    body = client.post(base + '/resolve', headers=A, json={**good, 'revision': 0}).json()
    resolved = row(body, 'escaneo.pdf')
    assert resolved['status'] == 'RENOMBRAR' and resolved['origin'] == 'manual' and resolved['can_undo']
    assert resolved['expected_name'] == '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf' and resolved['year'] == '2026'
    assert body['run']['months']['2026']['OCTUBRE']['estado'] == rules.COMPLETO
    assert body['run']['summary']['manual'] == 1
    undone = client.post(base + '/resolve', headers=A, json={**change, 'action': 'undo', 'revision': 1}).json()
    assert row(undone, 'escaneo.pdf')['status'] == 'OMITIDO'
    assert undone['run']['months']['2026']['OCTUBRE']['estado'] != rules.COMPLETO
    again = client.post(base + '/resolve', headers=A, json={**change, 'action': 'undo', 'revision': 2})
    assert again.status_code == 422


def test_manual_rename_that_does_not_count(client):
    _cid, base, detail = start(client, {'decl.pdf': pdf(), 'escaneo.pdf': image_pdf()})
    index = row(detail, 'escaneo.pdf')['index']
    data = {'revision': 0, 'index': index, 'action': 'manual', 'name': 'anexo octubre', 'count': False}
    body = client.post(base + '/resolve', headers=A, json=data).json()
    renamed = row(body, 'escaneo.pdf')
    assert renamed['expected_name'] == 'anexo octubre.pdf' and not renamed['count_in_control']
    assert body['run']['months']['2026']['OCTUBRE']['acuse'] is False
    assert client.post(base + '/generate', headers=A, json={'revision': 1}).status_code == 202
    with zipfile.ZipFile(io.BytesIO(client.get(base + '/download', headers=A).content)) as z:
        assert 'anexo octubre.pdf' in z.namelist()


def test_type_with_month_for_scanned_pdf(client):
    cid, base, detail = start(client, {'decl.pdf': pdf(), 'escaneo.pdf': image_pdf()})
    index = row(detail, 'escaneo.pdf')['index']
    data = {'revision': 0, 'index': index, 'action': 'type', 'choice': 'ACUSE NORMAL', 'month': 'Octubre'}
    body = client.post(base + '/resolve', headers=A, json=data).json()
    assert row(body, 'escaneo.pdf')['expected_name'] == '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf'
    assert body['run']['months']['2026']['OCTUBRE']['estado'] == rules.COMPLETO
    # Sin periodo no se puede marcar como otra copia.
    base = '/api/declara/runs/' + upload(client, cid, {'escaneo.pdf': image_pdf()}).json()['id']
    data = {'revision': 0, 'index': 0, 'action': 'duplicate'}
    assert 'periodo' in client.post(base + '/resolve', headers=A, json=data).json()['detail']


def test_exclude_and_reinclude(client):
    cid, base, detail = start(client, {'decl.pdf': pdf(), 'acuse.pdf': pdf('ACUSE')})
    index = row(detail, 'acuse.pdf')['index']
    body = client.post(base + '/resolve', headers=A, json={'revision': 0, 'index': index, 'action': 'exclude'}).json()
    excluded = row(body, 'acuse.pdf')
    assert excluded['status'] == rules.EXCLUIDO and excluded['detail'].startswith('Excluido del plan por')
    assert body['run']['summary']['excluded_manual'] == 1
    assert body['run']['months']['2026']['OCTUBRE']['estado'] != rules.COMPLETO
    twice = client.post(base + '/resolve', headers=A, json={'revision': 1, 'index': index, 'action': 'exclude'})
    assert twice.status_code == 422
    blocked = {'revision': 1, 'index': index, 'action': 'manual', 'name': 'x', 'count': False}
    assert client.post(base + '/resolve', headers=A, json=blocked).status_code == 422
    body = client.post(base + '/resolve', headers=A, json={'revision': 1, 'index': index, 'action': 'include'}).json()
    back = row(body, 'acuse.pdf')
    assert back['status'] == 'RENOMBRAR' and back['expected_name'] == '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf'
    assert body['run']['months']['2026']['OCTUBRE']['estado'] == rules.COMPLETO
    actions = [entry['action'] for entry in client.get('/api/declara/log?company_id=' + cid, headers=A).json()]
    assert actions[:3] == ['reinclusion', 'exclusion', 'analisis']


def test_company_settings_and_short_name(client):
    cid = company(client).json()['id']
    view = client.get('/api/declara/companies/' + cid, headers=A).json()
    assert view['suggested'] == 'ARKOS' and view['short_name'] == 'ARKOS' and not view['short_name_saved']
    assert view['alta'] == {'fecha': '2026-03-31', 'origen': 'RFC'} and view['mode'] == 'subir'
    upload(client, cid, {'a.pdf': pdf()}, short_name='Arkos Sum')
    assert client.get('/api/declara/companies/' + cid, headers=A).json()['short_name'] == 'ARKOS SUM'
    saved = client.put('/api/declara/companies/' + cid, headers=A, json={'mode': 'carpeta'}).json()
    assert saved['mode'] == 'carpeta' and saved['short_name'] == 'ARKOS SUM'
    assert client.put('/api/declara/companies/' + cid, headers=A, json={'mode': 'otro'}).status_code == 422
    assert client.get('/api/declara/companies/missing', headers=A).status_code in {403, 404}


def test_declara_settings(client):
    assert client.get('/api/declara/settings', headers=A).json() == {
        'template': '',
        'due_day': 17,
        'poll_seconds': 60,
        'backup': True,
    }
    template = '\\\\SERVIDOR\\Clientes\\{NOMBRE_CORTO}\\{EJERCICIO}\\Declaraciones'
    saved = client.put(
        '/api/declara/settings',
        headers=A,
        json={'template': template, 'due_day': 20, 'poll_seconds': 30, 'backup': False},
    ).json()
    assert saved == {'template': template, 'due_day': 20, 'poll_seconds': 30, 'backup': False}
    assert client.put('/api/declara/settings', headers=A, json={'template': '{OTRA}'}).status_code == 422
    assert client.put('/api/declara/settings', headers=A, json={'due_day': 31}).status_code == 422
    # El día límite configurado llega al control mensual.
    _cid, _base, detail = start(client, {'a.pdf': pdf()})
    assert detail['run']['months']['2026']['OCTUBRE']['vence'] == '2026-11-20'


def test_log_export_csv(client):
    cid, base, detail = start(client, {'decl.pdf': pdf(), 'acuse.pdf': pdf('ACUSE')})
    index = row(detail, 'acuse.pdf')['index']
    client.post(base + '/resolve', headers=A, json={'revision': 0, 'index': index, 'action': 'exclude'})
    entries = client.get(f'/api/declara/log?company_id={cid}&year=2026', headers=A).json()
    assert entries[0]['label'] == 'Exclusión' and entries[0]['user'] and entries[0]['detail']['archivo'] == 'acuse.pdf'
    analysis = entries[-1]
    assert analysis['detail']['pdf'] == 2 and analysis['detail']['modo'] == 'subir'
    exported = client.get(f'/api/declara/log.csv?company_id={cid}', headers=A)
    assert exported.headers['content-type'].startswith('text/csv')
    rows = list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert [r['accion'] for r in rows] == ['Exclusión', 'Análisis']
    assert client.get('/api/declara/log?company_id=missing', headers=A).status_code in {200, 403, 404}
