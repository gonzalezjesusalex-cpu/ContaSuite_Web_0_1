"""Repeatable synthetic-only seed. Caller must verify lab connection first."""
def seed_lab(engine,values,lab):
    import io
    from datetime import timedelta,date
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from app.models import Company,UserAccount,UserCompanyGrant,IdentityState,Setting,now,Task
    from app.accounts import password_hash
    from app.security import Principal
    from app.storage.service import StorageService,StorageActor
    from app.storage.settings import StorageSettings
    from app.fiscal_control import CellIn,save_cell,records
    from app.credential_models import certificates,grants
    from app.integral_api import analyze,AnalyzeIn,decision,DecisionIn,verify,VerifyIn,company_activity,ActiveIn,add_opinion,OpinionIn,add_cfdi,CfdiIn
    from app.credential_alerts import refresh
    from fastapi import Response
    sessions=sessionmaker(engine,expire_on_commit=False)
    with sessions() as db:
        if db.get(Setting,'v04_synthetic_seed'):
            db.get(IdentityState,'identity').initialized=True;db.commit();return
        db.add_all([UserAccount(id='lab-admin',username='devadmin',display_name='Administrador PRUEBAS',password_hash=password_hash(values['admin_password']),admin=True,enabled=True),UserAccount(id='lab-reader',username='devlector',display_name='Lector PRUEBAS',password_hash=password_hash(values['reader_password']),admin=False,enabled=True)])
        db.flush()
        identity=db.get(IdentityState,'identity')
        if identity:identity.initialized=True
        else:db.add(IdentityState(id='identity',initialized=True))
        for i,(regime,rfc) in enumerate([('601 - General de Ley Personas Morales','AAA010101AA1'),('626 - RESICO','BBB020202BB2'),('612 - PFAE','CCC030303CC3'),('621 - RIF HISTORICO','DDD040404DD4')],1):
            db.add(Company(id=f'lab-company-{i}',name=f'EMPRESA FICTICIA {i} · PRUEBAS',rfc=rfc,is_demo=True,regime=regime,accountant='Ana PRUEBAS' if i%2 else 'Luis PRUEBAS',notes='Datos exclusivamente sintéticos. No representan contribuyentes reales.'))
        db.commit();db.add(UserCompanyGrant(user_id='lab-reader',company_id='lab-company-1',access='read'));db.execute(grants.insert().values(user_id='lab-reader',company_id='lab-company-1',permission='metadata'));db.commit()
    admin=Principal('lab-admin','Admin PRUEBAS',True,session_id='seed-local-only')
    storage=StorageService(sessions,StorageSettings(lab/'data'/'cs-storage',lab/'data'/'documents'))
    actor=StorageActor('lab-seed',admin=True)
    xml=b'<?xml version="1.0"?><Comprobante Fecha="2026-11-01"/>'
    document=storage.upload(actor,io.BytesIO(xml),'PAGO_ISR_2026-11.xml',company_id='lab-company-1')
    storage.upload(actor,io.BytesIO(xml),'SIN_CLASIFICAR.xml',company_id='lab-company-2')
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID,ObjectIdentifier
    for i,days in [(1,90),(2,20),(3,-5)]:
        rfc=['AAA010101AA1','BBB020202BB2','CCC030303CC3'][i-1]
        key=ec.generate_private_key(ec.SECP256R1());subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CERTIFICADO SINTETICO NO SAT'),x509.NameAttribute(ObjectIdentifier('2.5.4.45'),rfc)])
        cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now()-timedelta(days=100)).not_valid_after(now()+timedelta(days=days)).sign(key,hashes.SHA256())
        public=cert.public_bytes(serialization.Encoding.DER)
        doc=storage.upload(actor,io.BytesIO(public),f'PUBLICO_FICTICIO_{i}.cer',company_id=f'lab-company-{i}')
        from app.credential_api import parse_public_certificate
        with sessions() as db:
            db.execute(certificates.insert().values(id=f'lab-cert-{i}',company_id=f'lab-company-{i}',rfc=rfc,kind='csd' if i==2 else 'fiel',origin='cs_storage',document_id=doc.id,reviewed_at=now(),notes='Certificado sintético, sin firma SAT.',revision=1,**parse_public_certificate(public)));db.commit()
    today=now().date()
    with sessions() as db:
        for i,status in [(1,'fulfilled'),(2,'pending'),(3,'unreviewed'),(4,'not_applicable')]:
            save_cell(CellIn(company_id=f'lab-company-{i}',obligation_id='fiscal-02',year=today.year,month=today.month,revision=0,status=status,due_date=today-timedelta(days=2) if i==2 else today+timedelta(days=10),due_verified=i==2),admin,db)
            company_activity(f'lab-company-{i}',ActiveIn(active=i!=4),admin,db)
        save_cell(CellIn(company_id='lab-company-1',obligation_id='fiscal-03',year=today.year,month=today.month,revision=0,status='fulfilled',submitted_at=today),admin,db)
        target=db.execute(select(records).where(records.c.company_id=='lab-company-1',records.c.obligation_id=='fiscal-02')).mappings().one()
        verify(target['id'],VerifyIn(revision=1,document_id=document.id),admin,db)
        review=analyze(AnalyzeIn(document_ids=[document.id]),admin,db)['results'][0]
        decision(document.id,DecisionIn(review_id=review['review_id'],revision=1,action='confirm',company_id='lab-company-1',category_id='category-04',year=today.year,period=f'{today.year}-{today.month:02d}',obligation_id=target['id'],reason='Clasificación sintética para laboratorio'),admin,db)
        add_opinion('lab-company-1',OpinionIn(authority='SAT',consulted_on=today,result='unreviewed',next_review=today+timedelta(days=15),responsible='Ana PRUEBAS'),admin,db)
        add_cfdi('lab-company-1',CfdiIn(period=f'{today.year}-{today.month:02d}',kind='issued',reviewed_on=today,state='in_progress',responsible='Ana PRUEBAS'),admin,db)
        refresh(Response(),admin,db)
        db.add(Task(company_id='lab-company-1',title='Revisión ficticia',due_date=today,responsible='Ana PRUEBAS',status='Completada'))
        db.add(Setting(key='v04_synthetic_seed',value='true'));db.commit()
    from openpyxl import Workbook
    book=Workbook();sheet=book.active;sheet.title=f'{today.year}-{today.month:02d}'
    sheet.append(['Empresa','RFC','ISR','IVA','Pago']);sheet.append(['EMPRESA FICTICIA 1 · PRUEBAS','AAA010101AA1','NA',today,'CON PAGO']);sheet.append(['EMPRESA FICTICIA 1 · PRUEBAS','AAA010101AA1',None,None,'SIN PAGO'])
    (lab/'fixtures').mkdir(exist_ok=True);book.save(lab/'fixtures'/'obligaciones_FICTICIAS.xlsx');book.close()
