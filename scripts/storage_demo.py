"""Create and exercise synthetic storage in a NEW disposable directory only.

Example from project: .venv/Scripts/python.exe scripts/storage_demo.py --output .qa/storage-demo
Never loads or writes the installation's configured database, data or .env.
"""
import argparse
import io
import json
import os
import secrets
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='Demo local aislada de CS-Storage')
    parser.add_argument('--output', type=Path, required=True, help='Directorio nuevo, inexistente y desechable')
    args = parser.parse_args()
    output = args.output.absolute()
    # Refuse re-use, UNC and linked ancestors before creating or modifying any fixture.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.storage.paths import check_no_links
    if str(output).startswith('\\\\'):
        parser.error('La demo sólo admite una ruta local.')
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    check_no_links(ancestor)
    output.parent.mkdir(parents=True, exist_ok=True)
    check_no_links(output.parent)
    output.mkdir(exist_ok=False)
    (output / 'CS_STORAGE_DISPOSABLE_DEMO').write_text('Synthetic fixtures only.\n', encoding='utf-8')
    root = output / 'source'
    (root / 'empresa-a' / '2026' / 'octubre').mkdir(parents=True)
    (root / 'excluded').mkdir()
    os.environ['DATA_DIR'] = str(output / 'data')
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(output / 'demo.db')
    os.environ['CS_STORAGE_ALLOWED_ROOTS'] = json.dumps([str(root)])
    os.environ['APP_TOKEN'] = secrets.token_urlsafe(32)
    os.environ['AGENT_TOKEN'] = secrets.token_urlsafe(32)
    os.environ['SEED_DEMO'] = 'false'
    from app.database import engine, SessionLocal,Base
    from app.models import Company,Task,Obligation,now
    from app.storage.migrate import upgrade_storage
    from app.storage.service import StorageService, StorageActor
    from app.storage.settings import StorageSettings
    from app.storage.indexer import LocalIndexer
    from app.storage.providers import ScanIssue
    from reportlab.pdfgen.canvas import Canvas
    upgrade_storage(engine)
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        db.add_all([Company(id='demo-a', name='Empresa A ficticia', rfc='AAA010101AA1', is_demo=True),
                    Company(id='demo-b', name='Empresa B ficticia', rfc='BBB020202BB2', is_demo=True)])
    def xml(issuer, receiver='XAXX010101000'):
        return (f'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="2026-10-01T10:00:00">'
                f'<cfdi:Emisor Rfc="{issuer}"/><cfdi:Receptor Rfc="{receiver}"/></cfdi:Comprobante>').encode()
    def pdf(text):
        stream = io.BytesIO()
        canvas = Canvas(stream, invariant=1)
        canvas.drawString(50, 750, text)
        canvas.save()
        return stream.getvalue()
    (root / 'empresa-a' / '2026' / 'octubre' / 'factura.xml').write_bytes(xml('AAA010101AA1'))
    (root / 'copia.xml').write_bytes(xml('AAA010101AA1'))
    (root / 'nombre-AAA010101AA1.xml').write_bytes(xml('BBB020202BB2'))  # Filename is not evidence.
    (root / 'ambiguo.xml').write_bytes(xml('AAA010101AA1', 'BBB020202BB2'))
    (root / 'texto.pdf').write_bytes(pdf('RFC BBB020202BB2 - documento ficticio'))
    (root / 'sin-rfc.pdf').write_bytes(pdf('Documento ficticio sin datos fiscales'))
    (root / 'desaparecera.pdf').write_bytes(pdf('Temporal de prueba'))
    (root / 'excluded' / 'omitido.xml').write_bytes(xml('AAA010101AA1'))
    (root / 'clave.key').write_text('NOT A REAL KEY - excluded fixture', encoding='ascii')
    service = StorageService(SessionLocal, StorageSettings.from_environment(output / 'data'))
    actor = StorageActor('synthetic_demo_operator', admin=True)
    source = service.register_local(actor, 'Carpeta ficticia de demostración', root, exclusions=('excluded',)).id
    indexer = LocalIndexer(service)
    results = []
    def run(label):
        job = indexer.enqueue(actor, source)
        owner = 'demo-worker'
        assert indexer.claim(owner) == job['id']
        indexer.run(job['id'], owner)
        results.append({'scenario': label, **next(j for j in indexer.jobs(actor) if j['id'] == job['id'])})
    run('initial')
    # Mutations are restricted to files created above, inside the just-created disposable directory.
    (root / 'copia.xml').write_bytes(xml('BBB020202BB2'))
    (root / 'desaparecera.pdf').unlink()
    run('modified_and_missing')
    real_provider = service._provider
    def simulated_provider(source):
        provider = real_provider(source)
        original_scan = provider.enumerate
        def scan():
            yield ScanIssue('simulated-denied', 'access_denied')
            yield from original_scan()
        provider.enumerate = scan
        return provider
    service._provider = simulated_provider
    run('simulated_access_denied')
    service._provider = real_provider
    from datetime import timedelta
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID,ObjectIdentifier
    for cid,rfc,days,name in [('demo-a','AAA010101AA1',90,'FIEL_vigente_demo.cer'),
                              ('demo-b','BBB020202BB2',20,'FIEL_por_vencer_demo.cer'),
                              ('demo-a','AAA010101AA1',-10,'FIEL_anterior_vencida_demo.cer')]:
        key=ec.generate_private_key(ec.SECP256R1())  # Synthetic signing key stays in memory; never saved.
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CERTIFICADO FICTICIO PARA DEMOSTRACION'),
                          x509.NameAttribute(ObjectIdentifier('2.5.4.45'),rfc)])
        certificate=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now()-timedelta(days=200))
            .not_valid_after(now()+timedelta(days=days)).sign(key,hashes.SHA256()))
        service.upload(actor,io.BytesIO(certificate.public_bytes(serialization.Encoding.DER)),name,
                       company_id=cid,category='e.firma (FIEL)',document_type='certificate')
    with SessionLocal.begin() as db:
        db.add(Task(company_id='demo-a',title='Renovar expediente · DEMO',due_date=(now()-timedelta(days=2)).date()))
        db.add(Obligation(company_id='demo-b',title='Declaración mensual · DEMO',period=now().strftime('%Y-%m'),
                          due_date=(now()+timedelta(days=5)).date()))
    (output / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    (output / 'environment.json').write_text(json.dumps({k: os.environ[k] for k in
        ('DATA_DIR', 'DATABASE_URL', 'CS_STORAGE_ALLOWED_ROOTS','APP_TOKEN','AGENT_TOKEN','SEED_DEMO')}, ensure_ascii=False, indent=2), encoding='utf-8')
    for result in results:
        print(result['scenario'], result['status'], json.dumps(result['counters']))
    engine.dispose()


if __name__ == '__main__':
    main()
