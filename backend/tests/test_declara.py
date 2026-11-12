import ast
import csv
import io
import json
import zipfile
from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from test_api import client, A, company
from app import declara, declara_engine as motor
from app.database import SessionLocal
from app.main import app
from app.models import DeclaraRun

RFC = 'ASU260331IWA'


def pdf(kind='DECLARACION', dtype='Normal', month='Octubre', year='2026', rfc=RFC, operation='100'):
    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    lines = ['DECLARACION PROVISIONAL O DEFINITIVA DE IMPUESTOS FEDERALES',
             f'RFC: {rfc}', 'Denominación o razón social: ARKOS SUMINISTROS',
             f'Tipo de declaración: {dtype}', f'Período de la declaración: {month}',
             f'Ejercicio: {year}', f'Número de operación: {operation}']
    if kind == 'ACUSE':
        lines.insert(0, 'ACUSE DE RECIBO')
    for n, line in enumerate(lines):
        c.drawString(40, 800 - n * 25, line)
    c.save()
    return stream.getvalue()


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return stream.getvalue()


def upload(client, cid, entries, **kw):
    return client.post('/api/declara/runs', headers=A,
                       data={'company_id': cid, 'short_name': 'Arkos', **kw},
                       files={'files': ('declaraciones.zip', zip_bytes(entries), 'application/zip')})


def test_extracted_engine_preserves_original_logic():
    root = Path(__file__).resolve().parents[2]
    original = ast.parse((root / 'reference/desktop/Declara/organizador_sat_v26.py').read_text(encoding='utf-8-sig'))
    extracted = ast.parse((root / 'backend/app/declara_engine.py').read_text(encoding='utf-8'))
    old = {n.name: n for n in original.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    for node in extracted.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in old:
            assert ast.dump(node, include_attributes=False) == ast.dump(old[node.name], include_attributes=False), node.name
    assert 'tkinter' not in (root / 'backend/app/declara_engine.py').read_text(encoding='utf-8')


def test_declara_web_full_flow_and_names(client):
    cid = company(client).json()['id']
    entries = {'Empresa/declaracion.pdf': pdf(), 'Empresa/acuse.PDF': pdf('ACUSE'),
               'Empresa/complementaria.pdf': pdf(dtype='Complementaria', operation='200'),
               'Empresa/complementaria_b.pdf': pdf(dtype='Complementaria', operation='201'),
               'Empresa/otro.pdf': b'not a PDF', 'Empresa/secret.key': b'not uploaded'}
    response = upload(client, cid, entries)
    assert response.status_code == 202
    ident = response.json()['id']
    base = '/api/declara/runs/' + ident
    result = client.get(base, headers=A).json()
    assert result['run']['status'] == 'analyzed'
    assert result['run']['summary']['rename'] == 4
    assert result['run']['summary']['excluded'] == 1
    assert result['run']['months']['2026']['OCTUBRE']['declaracion']
    assert result['run']['months']['2026']['OCTUBRE']['acuse']
    assert result['run']['warnings']
    names = {i['expected_name'] for i in result['records'] if i['status'] == 'RENOMBRAR'}
    assert names == {'10.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf',
                     '10.2.- ACUSE ISR E IVA OCTUBRE ARKOS.pdf',
                     '10.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf',
                     '10.1.1.- DECLARACION COMPLEMENTARIA ISR E IVA OCTUBRE ARKOS.pdf'}
    row = next(i for i in result['records'] if i['path'].endswith('declaracion.pdf'))
    assert client.get(base + '/file/' + str(row['index']), headers=A).content == entries['Empresa/declaracion.pdf']
    assert client.get(base + '/file/999', headers=A).status_code == 404
    assert client.get(base + '/download', headers=A).status_code == 409
    assert client.post(base + '/generate', headers=A, json={'revision': 99}).status_code == 409
    assert client.post(base + '/generate', headers=A, json={'revision': 0}).status_code == 202
    done = client.get(base, headers=A).json()
    assert done['run']['status'] == 'generated' and done['run']['summary']['output'] == 4
    downloaded = client.get(base + '/download', headers=A)
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as z:
        assert set(z.namelist()) == names
        assert z.read('10.- DECLARACION ISR E IVA OCTUBRE ARKOS.pdf') == entries['Empresa/declaracion.pdf']
        assert z.testzip() is None
    rows = list(csv.DictReader(io.StringIO(client.get(base + '/download?kind=csv', headers=A).content.decode('utf-8-sig'))))
    assert len(rows) == 5 and all(len(r['sha256']) == 64 for r in rows)
    assert not any(str(declara.DATA) in str(r) for r in rows)
    assert client.post(base + '/generate', headers=A, json={'revision': 0}).status_code == 409
    assert client.delete('/api/companies/' + cid, headers=A).status_code == 409
    assert len(client.get('/api/declara/runs?company_id=' + cid, headers=A).json()) == 1
    assert client.get('/api/declara/runs?company_id=missing', headers=A).json() == []
    assert (declara.folder(ident) / 'input' / 'Empresa' / 'declaracion.pdf').read_bytes() == entries['Empresa/declaracion.pdf']


def test_month_rules_normal_complementary_and_start_date():
    info = motor.PdfInfo(Path('a.pdf'), rfc=RFC, month='OCTUBRE', year='2026',
                         document_kind='DECLARACION', declaration_type='Normal', status='RENOMBRAR')
    acuse = replace(info, document_kind='ACUSE')
    months = motor.compute_month_completeness([info, acuse], RFC, date(2026, 11, 9))['2026']
    assert not months['ENERO']['aplicable'] and months['ENERO']['razon_no_aplica'] == 'ALTA'
    assert months['MARZO']['aplicable']
    assert months['OCTUBRE']['declaracion'] and months['OCTUBRE']['acuse']
    assert not months['NOVIEMBRE']['aplicable'] and months['NOVIEMBRE']['razon_no_aplica'] == 'NO_EXIGIBLE'
    comp = motor.compute_month_completeness([replace(info, declaration_type='Complementaria')], RFC, date(2026, 11, 9))['2026']
    assert not comp['OCTUBRE']['declaracion']
    assert motor.rfc_company_start_date('GODE800101AA1') is None


def test_special_numbering_and_original_copy_rules(tmp_path):
    (tmp_path / 'decl.pdf').write_bytes(pdf(month='Mayo'))
    (tmp_path / 'acuse.pdf').write_bytes(pdf('ACUSE', month='Mayo'))
    (tmp_path / 'DECLARACION MAYO RESICO.pdf').write_bytes(b'no text; name fallback')
    (tmp_path / 'ACUSE MAYO SALARIOS.pdf').write_bytes(b'no text; name fallback')
    infos = motor.analyze_folder(tmp_path, 'ARKOS')
    resico = next(i for i in infos if i.is_resico)
    salarios = next(i for i in infos if i.is_salarios)
    assert resico.expected_name == '5.3.- DECLARACION MAYO RESICO.pdf'
    assert salarios.expected_name == '5.4.- ACUSE MAYO SALARIOS.pdf'
    assert resico.preserve_special_name and salarios.preserve_special_name
    assert motor.add_duplicate_suffix('5.2.- ACUSE.pdf', 2) == '5.2.1.- ACUSE.pdf'
    assert motor.execute_renames(infos) == (4, [])
    assert (tmp_path / resico.expected_name).read_bytes() == b'no text; name fallback'


def test_manual_resolution_and_stale_revision(client):
    cid = company(client).json()['id']
    response = upload(client, cid, {'declaracion.pdf': pdf(), 'acuse.pdf': pdf('ACUSE')})
    base = '/api/declara/runs/' + response.json()['id']
    detail = client.get(base, headers=A).json()
    index = next(i['index'] for i in detail['records'] if i['document_kind'] == 'DECLARACION')
    data = {'revision': 0, 'index': index, 'action': 'type', 'choice': 'ACUSE NORMAL'}
    resolved = client.post(base + '/resolve', headers=A, json=data)
    assert resolved.status_code == 200
    body = resolved.json()
    assert body['run']['revision'] == 1
    row = next(i for i in body['records'] if i['index'] == index)
    assert row['manual_override'] and row['expected_name'].startswith('10.2.1.- ACUSE')
    assert not body['run']['months']['2026']['OCTUBRE']['declaracion']
    assert client.post(base + '/resolve', headers=A, json=data).status_code == 409
    bad = client.post(base + '/resolve', headers=A, json={**data, 'revision': 1, 'index': 999})
    assert bad.status_code == 422
    assert client.get(base, headers=A).json()['run']['status'] == 'analyzed'
    assert client.post(base + '/generate', headers=A, json={'revision': 1}).status_code == 202


def test_wrong_company_and_mixed_rfc(client):
    cid = company(client).json()['id']
    response = upload(client, cid, {'other.pdf': pdf(rfc='ABC010101AA1')})
    base = '/api/declara/runs/' + response.json()['id']
    detail = client.get(base, headers=A).json()
    assert not detail['run']['summary']['rfc_matches'] and detail['run']['months'] == {}
    assert client.post(base + '/generate', headers=A, json={'revision': 0}).status_code == 422
    response = upload(client, cid, {'a.pdf': pdf(), 'b.pdf': pdf('ACUSE'), 'c.pdf': pdf(rfc='ABC010101AA1')})
    base = '/api/declara/runs/' + response.json()['id']
    detail = client.get(base, headers=A).json()
    assert detail['run']['summary']['excluded'] == 1
    other = next(i for i in detail['records'] if i['status'] == 'RFC DIFERENTE')
    assert client.post(base + '/resolve', headers=A, json={'revision': 0, 'index': other['index'], 'action': 'duplicate'}).status_code == 422


def test_validation_limits_and_traversal(client, monkeypatch):
    assert client.get('/api/declara/runs').status_code == 401
    assert upload(client, 'missing', {'a.pdf': pdf()}).status_code == 404
    cid = company(client).json()['id']
    assert upload(client, cid, {'a.pdf': pdf()}, short_name='...').status_code == 422
    monkeypatch.setattr(declara, 'MAX_UPLOAD', 1)
    assert upload(client, cid, {'a.pdf': pdf()}).status_code == 413
    monkeypatch.setattr(declara, 'MAX_UPLOAD', 1000000)
    for name in ('../escape.pdf', 'a/CON.pdf', 'C:/escape.pdf'):
        r = upload(client, cid, {name: pdf()})
        assert client.get('/api/declara/runs/' + r.json()['id'], headers=A).json()['run']['status'] == 'error'
    r = upload(client, cid, {'a.pdf': pdf(), 'A.PDF': pdf()})
    assert client.get('/api/declara/runs/' + r.json()['id'], headers=A).json()['run']['status'] == 'error'
    monkeypatch.setattr(declara, 'MAX_EXPANDED', 1)
    r = upload(client, cid, {'a.pdf': pdf()})
    assert client.get('/api/declara/runs/' + r.json()['id'], headers=A).json()['run']['status'] == 'error'


def test_modified_input_does_not_publish_results(client):
    cid = company(client).json()['id']
    r = upload(client, cid, {'a.pdf': pdf()})
    ident = r.json()['id']
    (declara.folder(ident) / 'input' / 'a.pdf').write_bytes(b'changed')
    base = '/api/declara/runs/' + ident
    assert client.post(base + '/generate', headers=A, json={'revision': 0}).status_code == 202
    assert client.get(base, headers=A).json()['run']['status'] == 'error'
    assert client.get(base + '/download', headers=A).status_code == 409


def test_folder_upload_and_ignored_subfolders(client):
    cid = company(client).json()['id']
    response = client.post('/api/declara/runs', headers=A, data={'company_id': cid, 'short_name': 'ARKOS'},
                           files=[('files', ('Folder/a.pdf', pdf())), ('files', ('Folder/nested/b.pdf', pdf('ACUSE')))])
    base = '/api/declara/runs/' + response.json()['id']
    detail = client.get(base, headers=A).json()
    assert len(detail['records']) == 1
    assert any('subcarpetas' in w for w in detail['run']['warnings'])


def test_restart_marks_interrupted_runs(client):
    cid = company(client).json()['id']
    with SessionLocal() as db:
        db.add(DeclaraRun(company_id=cid, short_name='ARKOS', expected_rfc=RFC, name='interrupt', status='editing'))
        db.commit()
    with TestClient(app) as restarted:
        run = restarted.get('/api/declara/runs', headers=A).json()[0]
        assert run['status'] == 'error' and 'reinició' in run['message']
