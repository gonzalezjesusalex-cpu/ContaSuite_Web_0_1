"""Explicit user-authorized import of the already analysed first folder only."""

import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pilot_first import configuration, RUN, DATABASE


def main():
    c, env = configuration()
    os.environ.update(env)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from sqlalchemy import select, update, text
    from app.database import SessionLocal, DATA
    from app.models import (
        Company,
        StorageSource,
        DocumentVersion,
        Document,
        DocumentClassificationReview as Review,
        now,
    )
    from app.company_import_models import sessions, rows, history
    from app.storage.service import StorageService, StorageActor
    from app.storage.settings import StorageSettings
    from app.pilot_import import BorrowedSessions
    from app.pilot_scan import SECRET_PATTERNS
    from app.storage.classifier import catalog_digest
    from app.document_identity import lock
    from uuid import uuid4
    import psycopg

    with psycopg.connect(
        host='127.0.0.1',
        port=c['port'],
        user='pilot_local',
        password=c['db_password'],
        dbname=DATABASE,
        autocommit=True,
    ) as guard:
        assert Path(guard.execute('SHOW data_directory').fetchone()[0]).resolve() == RUN / 'cluster'
        assert guard.execute('SELECT pg_try_advisory_lock(440043)').fetchone()[0]
        with SessionLocal.begin() as db:
            item = db.execute(select(sessions).where(sessions.c.source == 'local_batch')).mappings().one()
            ident = item['id']
            summary = item['summary']
            assert summary['processed'] == summary['total'] and summary['integrity']['changed'] == 0
            choices = [x for x in summary['identity_candidates'] if x['rfc'] == c.get('approved_rfc')]
            assert len({x['rfc'] for x in choices}) == 1
            choice = choices[0]
            lock(db)
            db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': choice['rfc']})
            company = db.scalar(select(Company).where(Company.rfc == choice['rfc']))
            if company is None:
                company = Company(
                    name=choice['name'],
                    rfc=choice['rfc'],
                    folder=c['root'],
                    regime='Por revisar',
                    notes='Piloto: alta autorizada expresamente por el usuario; sin validación SAT.',
                )
                db.add(company)
                db.flush()
            cid = company.id
            actor = StorageActor(c['actor'], admin=True)
            service = StorageService(BorrowedSessions(db), StorageSettings.from_environment(DATA))
            source = db.scalar(
                select(StorageSource).where(StorageSource.kind == 'local_folder', StorageSource.root_path == c['root'])
            )
            if source is None:
                registered = service.register_local(
                    actor, 'Primera carpeta autorizada', c['root'], exclusions=SECRET_PATTERNS
                )
                source = db.get(StorageSource, registered.id)
            sid = source.id
            db.execute(
                history.insert().values(
                    id=str(uuid4()),
                    session_id=ident,
                    actor_id=c['actor'],
                    action='user_import_authorized',
                    created_at=now(),
                    counts={
                        'company_id': cid,
                        'scope': 'first_folder_only',
                        'instruction': 'Importa la empresa de la carpeta analizada; ver dashboard y panel de empresas',
                    },
                )
            )
        total = summary['total']
        done = skipped = 0
        # Conservatively review any early non-CFDI proposal containing several RFCs.
        with SessionLocal.begin() as db:
            core = StorageService(BorrowedSessions(db), StorageSettings.from_environment(DATA))
            lock(db)
            for proposal in db.scalars(select(rows.c.proposal).where(rows.c.session_id == ident)):
                result = proposal.get('result', {})
                rfcs = result.get('evidence', {}).get('rfcs', [])
                if (
                    not proposal.get('import_document_id')
                    or result.get('type') == 'cfdi'
                    or len({r['rfc'] for r in rfcs}) <= 1
                ):
                    continue
                doc = db.get(Document, proposal['import_document_id'])
                version = db.scalar(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc.id, DocumentVersion.number == doc.storage_revision
                    )
                )
                old = db.scalar(
                    select(Review).where(Review.version_id == version.id).order_by(Review.created_at.desc()).limit(1)
                )
                if not old or old.resolution != 'automatic':
                    continue
                old.status = 'superseded'
                db.add(
                    Review(
                        document_id=doc.id,
                        version_id=version.id,
                        evidence={'previous_review': old.id, 'reason': 'multiple_rfcs_require_review'},
                    )
                )
                db.flush()
                core.apply_classification(
                    actor, doc.id, doc.storage_revision, {**result, 'links': [], 'automatic': False}
                )
        for offset in range(0, total, 20):
            with SessionLocal.begin() as db:
                core = StorageService(BorrowedSessions(db), StorageSettings.from_environment(DATA))
                lock(db)
                records = list(
                    db.execute(
                        select(rows)
                        .where(rows.c.session_id == ident, rows.c.number > offset, rows.c.number <= offset + 20)
                        .order_by(rows.c.number)
                    )
                )
                for record in records:
                    proposal = record.proposal
                    if proposal.get('import_document_id'):
                        done += 1
                        continue
                    if proposal.get('error'):
                        skipped += 1
                        continue
                    doc = core.observe_external(actor, sid, proposal['key'])
                    version = db.scalar(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc.id, DocumentVersion.number == doc.revision
                        )
                    )
                    if version.sha256 != proposal['sha256']:
                        raise RuntimeError('Source changed; current transaction rolled back')
                    result = dict(proposal['result'])
                    evidence = dict(result['evidence'])
                    links = [
                        {'company_id': cid, 'role': r['role']}
                        for r in evidence.get('rfcs', [])
                        if r['rfc'] == choice['rfc']
                    ]
                    unambiguous = result['type'] == 'cfdi' or len({r['rfc'] for r in evidence.get('rfcs', [])}) == 1
                    result.update(
                        links=links,
                        automatic=bool(
                            links and unambiguous and evidence.get('complete') and not proposal.get('conflict')
                        ),
                    )
                    evidence['catalog_digest'] = catalog_digest([{'id': cid, 'rfc': choice['rfc']}])
                    result['evidence'] = evidence
                    core.apply_classification(actor, doc.id, doc.revision, result)
                    db.execute(
                        update(rows)
                        .where(rows.c.session_id == ident, rows.c.number == record.number)
                        .values(proposal={**proposal, 'import_document_id': doc.id})
                    )
                    done += 1
            if offset % 100 == 0:
                print(f'Imported {done}/{total}; errors excluded {skipped}.', flush=True)
        with SessionLocal.begin() as db:
            db.execute(
                history.insert().values(
                    id=str(uuid4()),
                    session_id=ident,
                    actor_id=c['actor'],
                    action='batch_imported',
                    created_at=now(),
                    counts={'documents': done, 'errors_excluded': skipped, 'company_id': cid},
                )
            )
        (RUN / 'import-summary.json').write_text(
            json.dumps(
                {'company_id': cid, 'imported': done, 'errors_excluded': skipped, 'original_writes': False}, indent=2
            )
        )
        print('First-folder import complete.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Import stopped safely; error_class=' + type(e).__name__, flush=True)
        raise SystemExit(1) from None
