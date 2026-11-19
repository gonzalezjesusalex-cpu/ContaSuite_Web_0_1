"""Recopila through the API: enrichment, manual adjustments with actor and date, and persistence (4.1 to 4.3)."""

import io
import zipfile

from pypdf import PdfReader
from sqlalchemy import select
from test_api import A, client, company  # noqa: F401
from test_recopila import pdf, upload, xml

from app.database import SessionLocal
from app.models import RecopilaPolicy, RecopilaPolicyCfdi

DIARIO = 'AAAAAAAA-0000-0000-0000-000000000001'


def archive():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr(
            'Polizas/diario.pdf',
            pdf(
                'IMPRESO DE POLIZAS',
                'Diario (Manual)',
                'Fecha 09/10/2026',
                'Descripcion Ajuste',
                'CFDI asociados a la poliza',
                DIARIO,
            ),
        )
        z.writestr(f'CFDI/{DIARIO}.xml', xml(DIARIO))
        z.writestr(f'CFDI/{DIARIO}.pdf', pdf('Factura del diario', DIARIO))
    return stream.getvalue()


def test_manual_adjustment_changes_the_generated_file_and_is_audited(client):  # noqa: F811
    c = company(client).json()
    ident = upload(client, archive(), company_id=c['id']).json()['id']
    base = '/api/recopila/runs/' + ident
    detail = client.get(base, headers=A).json()
    assert detail['run']['status'] == 'analyzed'
    assert detail['policies'][0]['support'] == 'Sin soporte'
    proposal = detail['enrichment']['proposals'][0]
    assert proposal['kind'] == 'diario' and proposal['uuid'] == DIARIO and detail['adjustments'] == []
    with SessionLocal() as db:
        rows = db.scalars(select(RecopilaPolicy).where(RecopilaPolicy.run_id == ident)).all()
        assert [(r.policy_type, r.period, r.status) for r in rows] == [('Diario (Manual)', '2026-10', 'Sin soporte')]
        assert db.scalars(select(RecopilaPolicyCfdi)).all() == []  # the engine related nothing

    # Without the adjustment the generated recopilador has only the policy page.
    assert client.post(base + '/generate', headers=A, json={'by_month': False}).status_code == 202
    first = client.get(base + '/file', headers=A, params={'name': 'RECOPILADOR.pdf'}).content
    assert len(PdfReader(io.BytesIO(first)).pages) == 1

    bad = client.post(
        base + '/adjustments', headers=A, json={'policy_index': 0, 'action': 'attach', 'target': '../../fuera.pdf'}
    )
    assert bad.status_code == 422
    made = client.post(
        base + '/adjustments',
        headers=A,
        json={'policy_index': proposal['policy_index'], 'action': 'attach', 'target': proposal['pdf']},
    )
    assert made.status_code == 201
    adjustment = made.json()[0]
    assert adjustment['actor_id'] and adjustment['created_at'] and adjustment['revoked_at'] is None
    with SessionLocal() as db:
        relation = db.scalars(select(RecopilaPolicyCfdi)).one()
        assert relation.origin == 'propuesta' and relation.state == 'active' and relation.decided_by

    assert client.post(base + '/generate', headers=A, json={'by_month': False}).status_code == 202
    second = client.get(base + '/file', headers=A, params={'name': 'RECOPILADOR.pdf'}).content
    pages = PdfReader(io.BytesIO(second)).pages
    assert len(pages) == 2 and 'Factura del diario' in pages[1].extract_text()

    revoked = client.delete(base + '/adjustments/' + adjustment['id'], headers=A).json()
    assert revoked[0]['revoked_at']
    assert client.post(base + '/generate', headers=A, json={'by_month': False}).status_code == 202
    third = client.get(base + '/file', headers=A, params={'name': 'RECOPILADOR.pdf'}).content
    assert len(PdfReader(io.BytesIO(third)).pages) == 1


def test_save_to_expediente_creates_documents_then_versions_and_never_overwrites(client):  # noqa: F811
    c = company(client).json()
    ident = upload(client, archive(), company_id='').json()['id']  # a run without company
    base = '/api/recopila/runs/' + ident
    assert client.post(base + '/save', headers=A, json={}).status_code == 409  # nothing generated yet
    assert client.post(base + '/generate', headers=A, json={'by_month': True}).status_code == 202
    assert client.post(base + '/save', headers=A, json={}).status_code == 422  # a company must be chosen
    assert client.post(base + '/save', headers=A, json={'company_id': 'no-existe'}).status_code == 422

    first = client.post(base + '/save', headers=A, json={'company_id': c['id']}).json()
    assert [f['status'] for f in first['files']] == ['nuevo', 'nuevo']
    docs = client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']
    assert {(d['name'], d['document_type'], d['period']) for d in docs} == {
        ('RECOPILADOR.pdf', 'recopilador', '2026-10'),
        ('RECOPILADOR_2026-10_OCTUBRE.pdf', 'recopilador', '2026-10'),
    }
    again = client.post(base + '/save', headers=A, json={'company_id': c['id']}).json()
    assert [f['status'] for f in again['files']] == ['ya_registrado', 'ya_registrado']

    proposal = client.get(base, headers=A).json()['enrichment']['proposals'][0]
    client.post(
        base + '/adjustments',
        headers=A,
        json={'policy_index': proposal['policy_index'], 'action': 'attach', 'target': proposal['pdf']},
    )
    assert client.post(base + '/generate', headers=A, json={'by_month': True}).status_code == 202
    changed = client.post(base + '/save', headers=A, json={'company_id': c['id']}).json()
    assert [f['status'] for f in changed['files']] == ['version_nueva', 'version_nueva']
    docs = client.get('/api/storage/documents', headers=A, params={'company_id': c['id']}).json()['items']
    assert len(docs) == 2  # the same two documents, now with a second version each
    detail = client.get('/api/storage/documents/' + docs[0]['id'], headers=A).json()
    assert [v['number'] for v in detail['versions']] == [2, 1] or [v['number'] for v in detail['versions']] == [1, 2]
