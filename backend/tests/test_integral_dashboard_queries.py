"""Integral dashboard: current-version evidence per obligation and a query count that does not grow with data."""

import io

from sqlalchemy import event

from test_storage_core import core, ADMIN as STORAGE_ADMIN, XML  # noqa: F401
from test_integral import integral, cell, ADMIN  # noqa: F401
from app.models import Document
from app.integral_dashboard import dashboard
from app.integral_api import analyze, AnalyzeIn, decision, DecisionIn
from app.fiscal_control import save_cell


def confirm_as_evidence(db, doc, target):
    review = analyze(AnalyzeIn(document_ids=[doc.id]), ADMIN, db)['results'][0]['review_id']
    decision(
        doc.id,
        DecisionIn(
            review_id=review,
            revision=doc.revision,
            action='confirm',
            company_id='company-a',
            category_id='category-04',
            year=2026,
            period='2026-05',
            obligation_id=target['id'],
            reason='Revisión humana sintética',
        ),
        ADMIN,
        db,
    )


def queries(factory, call):
    count = [0]

    def listener(*_):
        count[0] += 1

    engine = factory.kw['bind']
    event.listen(engine, 'before_cursor_execute', listener)
    try:
        result = call()
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
    return result, count[0]


def evidence_of(report, record_id):
    return next(r for r in report['obligations']['records'] if r['id'] == record_id)['virtual_evidence']


def test_obligation_evidence_only_current_version_and_scoped(integral):
    service, factory, _ = integral
    doc = service.upload(STORAGE_ADMIN, io.BytesIO(XML), 'PAGO_ISR_2026-05.xml', company_id='company-a')
    with factory() as db:
        target = save_cell(cell(), ADMIN, db)
        other = save_cell(cell(company_id='company-b'), ADMIN, db)
        confirm_as_evidence(db, doc, target)
        report = dashboard(db, ADMIN, 2026, 5)
        current = db.get(Document, doc.id)
        assert evidence_of(report, target['id']) == [
            {
                'document_id': doc.id,
                'version_id': evidence_of(report, target['id'])[0]['version_id'],
                'verified_compliance': False,
            }
        ]
        assert evidence_of(report, other['id']) == []
        # A newer storage revision makes the linked version no longer current: it stops counting as evidence.
        current.storage_revision += 1
        db.flush()
        assert evidence_of(dashboard(db, ADMIN, 2026, 5), target['id']) == []
        db.rollback()


def test_query_count_does_not_grow_with_documents_or_obligations(integral):
    service, factory, _ = integral
    first = service.upload(STORAGE_ADMIN, io.BytesIO(XML), 'PAGO_ISR_2026-05.xml', company_id='company-a')
    with factory() as db:
        target = save_cell(cell(), ADMIN, db)
        confirm_as_evidence(db, first, target)
        db.commit()
        _, baseline = queries(factory, lambda: dashboard(db, ADMIN, 2026, 5))
    for i in range(5):
        service.upload(
            STORAGE_ADMIN,
            io.BytesIO(XML + b'<!-- synthetic ' + str(i).encode() + b' -->'),
            f'extra-{i}.xml',
            company_id='company-b',
        )
    with factory() as db:
        for obligation in ('fiscal-03', 'fiscal-04'):
            save_cell(cell(obligation_id=obligation), ADMIN, db)
        report, more = queries(factory, lambda: dashboard(db, ADMIN, 2026, 5))
    assert report['documents']['indexed'] == 6
    assert more == baseline, (baseline, more)
    assert baseline <= 45
