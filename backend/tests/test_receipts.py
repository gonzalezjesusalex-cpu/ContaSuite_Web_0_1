import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pypdf import PdfReader
from sqlalchemy import select
from test_api import client, company, A
from app.database import SessionLocal, DATA
from app.models import Receipt, ReceiptCounter
from app import receipt_engine


def item(c, **kwargs):
    return dict(company_id=c['id'],month=10,year=2026,amount='2500.25',issued='2026-11-09',**kwargs)

def generate(client, rows, **kwargs):
    return client.post('/api/receipts',headers=A,json={'items':rows,**kwargs})

def test_receipts_auth_preview_no_folio_and_validation(client):
    c=company(client).json();d=item(c)
    assert client.get('/api/receipts').status_code==401
    assert client.post('/api/receipts/preview',json=d).status_code==401
    r=client.post('/api/receipts/preview',headers=A,json=d)
    assert r.status_code==200 and r.content.startswith(b'%PDF')
    page=PdfReader(io.BytesIO(r.content)).pages[0]
    text=" ".join(page.extract_text().split())
    assert 'VISTA PREVIA' in text and 'DOS MIL QUINIENTOS PESOS 25/100 M.N.' in text
    assert len(page.images)==1
    assert client.get('/api/receipts',headers=A).json()==[]
    for changes in [{'amount':'nan'},{'amount':'0'},{'amount':'-5'},{'amount':'1000000000'},{'month':13},{'issued':'bad'}]:
        assert client.post('/api/receipts/preview',headers=A,json=d|changes).status_code==422
    assert client.post('/api/receipts/preview',headers=A,json=d|{'company_id':'missing'}).status_code==404
    assert generate(client,[d]).json()[0]['folio']=='2026-0001'

def test_receipts_batch_exports_history_and_original(client):
    c=company(client).json();rows=[item(c),item(c)|{'month':11}]
    result=generate(client,rows);assert result.status_code==201;rs=result.json()
    assert [r['folio'] for r in rs]==['2026-0001','2026-0002']
    one=client.get('/api/receipts/'+rs[0]['id']+'/pdf',headers=A)
    text=" ".join(PdfReader(io.BytesIO(one.content)).pages[0].extract_text().split())
    assert '2026-0001' in text and 'OCTUBRE 2026' in text
    assert 'VISTA PREVIA' not in text
    for format,count in [('pdf',2),('zip',2)]:
        r=client.post('/api/receipts/export',headers=A,json={'ids':[x['id'] for x in rs],'format':format})
        assert r.status_code==200
        if format=='pdf':assert len(PdfReader(io.BytesIO(r.content)).pages)==count
        else:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                assert z.namelist()==[x['filename'] for x in rs]
                assert z.read(z.namelist()[0])==one.content
    assert len(client.get('/api/receipts?company_id='+c['id']+'&year=2026&q=2026-10',headers=A).json())==1
    assert client.get('/api/receipts?q=%',headers=A).json()==[]
    assert client.get('/api/receipts?company_id=missing',headers=A).json()==[]
    assert client.put('/api/receipts/settings',headers=A,json={'receiver':'OTRA PERSONA','place':'OTRO LUGAR'}).status_code==200
    assert client.get('/api/receipts/'+rs[0]['id']+'/pdf',headers=A).content==one.content
    assert client.delete('/api/companies/'+c['id'],headers=A).status_code==409
    assert len(client.get('/api/receipts',headers=A).json())==2

def test_duplicates_and_annual_counter(client):
    c=company(client).json();d=item(c)
    assert generate(client,[d,d]).status_code==409
    assert client.get('/api/receipts',headers=A).json()==[]
    first=generate(client,[d]).json()[0];assert first['folio']=='2026-0001'
    assert len(client.post('/api/receipts/duplicates',headers=A,json={'items':[d]}).json())==1
    assert generate(client,[d]).status_code==409
    assert generate(client,[d],allow_duplicates=True).json()[0]['folio']=='2026-0002'
    # Counter follows issue year; folders/period follow the month being charged.
    r=generate(client,[d|{'issued':'2027-01-03','month':12}]).json()[0]
    assert r['folio']=='2027-0001' and r['year']==2026 and r['month']==12

def test_batch_rollback_on_generation_failure(client):
    c=company(client).json();d=item(c)
    before=set((DATA/'receipts').glob('*.pdf'))
    original=receipt_engine.receipt_pdf;calls=0
    def fail(data,cfg):
        nonlocal calls
        calls+=1
        if calls==2:raise OSError('Simulated disk failure')
        return original(data,cfg)
    with patch.object(receipt_engine,'receipt_pdf',side_effect=fail):
        try:generate(client,[d,d|{'month':11}])
        except OSError:pass
    assert client.get('/api/receipts',headers=A).json()==[]
    assert set((DATA/'receipts').glob('*.pdf'))==before
    with SessionLocal() as db:assert db.scalar(select(ReceiptCounter)) is None
    assert generate(client,[d]).json()[0]['folio']=='2026-0001'

def test_concurrent_duplicates_only_emit_once(client):
    c=company(client).json();d=item(c)
    with ThreadPoolExecutor(max_workers=2) as executor:
        codes=list(executor.map(lambda _:generate(client,[d]).status_code,range(2)))
    assert sorted(codes)==[201,409]
    assert len(client.get('/api/receipts',headers=A).json())==1

def test_missing_pdf_and_config_validation(client):
    c=company(client).json();r=generate(client,[item(c)]).json()[0]
    with SessionLocal() as db:storage=db.get(Receipt,r['id']).storage_name
    (DATA/'receipts'/storage).unlink()
    assert client.get('/api/receipts/'+r['id']+'/pdf',headers=A).status_code==404
    assert client.post('/api/receipts/export',headers=A,json={'ids':[r['id']],'format':'zip'}).status_code==404
    assert client.put('/api/receipts/settings',headers=A,json={'receiver':'   ','place':'X'}).status_code==422
    assert client.get('/api/receipts/settings',headers=A).json()['receiver']==receipt_engine.DEFAULTS['receiver']


def manual(**changes):
    return dict(name='Cliente sin registro',month=10,year=2026,amount='1250.50',issued='2026-11-09',concept='Anticipo por asesoría administrativa',**changes)


def test_manual_client_and_custom_concept_without_company(client):
    d=manual()
    preview=client.post('/api/receipts/preview',headers=A,json=d)
    assert preview.status_code==200
    text=' '.join(PdfReader(io.BytesIO(preview.content)).pages[0].extract_text().split())
    assert 'CLIENTE SIN REGISTRO' in text and d['concept'] in text
    assert 'SERVICIOS CONTABLES DEL MES' not in text
    result=generate(client,[d]);assert result.status_code==201
    r=result.json()[0]
    assert r['company_id'] is None and r['concept']==d['concept']
    assert client.get('/api/state',headers=A).json()['companies']==[]
    assert client.get('/api/receipts?q=asesoría',headers=A).json()[0]['id']==r['id']
    assert client.get('/api/receipts/clients',headers=A).json()==[]
    assert client.post('/api/receipts/preview',headers=A,json=d|{'name':'  '}).status_code==422
    assert client.post('/api/receipts/preview',headers=A,json=d|{'concept':'x'*501}).status_code==422
    escaped=client.post('/api/receipts/preview',headers=A,json=d|{'concept':'Servicio <personalizado> & asesoría'})
    assert escaped.status_code==200
    assert 'Servicio <personalizado> & asesoría' in ' '.join(PdfReader(io.BytesIO(escaped.content)).pages[0].extract_text().split())


def test_saved_clients_delete_preserves_receipts_and_pdf(client):
    assert client.post('/api/receipts/clients',json={'name':'X'}).status_code==401
    c=client.post('/api/receipts/clients',headers=A,json={'name':'  Cliente   particular '}).json()
    assert c['name']=='CLIENTE PARTICULAR'
    second=client.post('/api/receipts/clients',headers=A,json={'name':'cliente particular'}).json()
    assert c['id']==second['id']
    d=manual()|{'client_id':c['id'],'name':c['name']}
    r=generate(client,[d]).json()[0]
    pdf=client.get('/api/receipts/'+r['id']+'/pdf',headers=A).content
    assert len(client.get('/api/receipts/clients',headers=A).json())==1
    assert generate(client,[d|{'client_id':None,'name':'cliente particular'}]).status_code==409
    assert client.delete('/api/receipts/clients/'+c['id'],headers=A).status_code==204
    assert client.get('/api/receipts/clients',headers=A).json()==[]
    row=client.get('/api/receipts',headers=A).json()[0]
    assert row['name']=='CLIENTE PARTICULAR' and row['client_id'] is None
    assert client.get('/api/receipts/'+r['id']+'/pdf',headers=A).content==pdf
    assert client.get('/api/state',headers=A).json()['companies']==[]
    # A draft retains its own name even if the saved client was removed elsewhere.
    assert generate(client,[d|{'month':11}]).status_code==201
    assert client.get('/api/receipts/clients',headers=A).json()==[]


def test_migration_from_previous_receipts_schema(tmp_path):
    from sqlalchemy import create_engine, text, inspect
    from app.receipt_migration import migrate_receipts
    old=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    with old.begin() as db:
        db.execute(text('CREATE TABLE companies (id VARCHAR(36) PRIMARY KEY)'))
        db.execute(text("INSERT INTO companies VALUES ('co')"))
        db.execute(text('''CREATE TABLE receipts (
        id VARCHAR(36) PRIMARY KEY, company_id VARCHAR(36) NOT NULL REFERENCES companies(id),
        folio VARCHAR(30) NOT NULL UNIQUE, name VARCHAR(220) NOT NULL, month INTEGER NOT NULL,
        year INTEGER NOT NULL, amount VARCHAR(30) NOT NULL, issued VARCHAR(10) NOT NULL,
        receiver VARCHAR(180) NOT NULL, place VARCHAR(180) NOT NULL, filename VARCHAR(255) NOT NULL,
        storage_name VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)'''))
        db.execute(text('CREATE INDEX ix_receipts_company_id ON receipts(company_id)'))
        db.execute(text("INSERT INTO receipts VALUES ('r','co','2026-0017','CLIENTE',10,2026,'100.00','2026-11-09','PERSONA','OAXACA','old.pdf','original.pdf','2026-11-09')"))
    migrate_receipts(old);migrate_receipts(old)
    columns={c['name']:c for c in inspect(old).get_columns('receipts')}
    assert columns['company_id']['nullable'] and 'client_id' in columns and 'concept' in columns
    with old.connect() as db:
        r=db.execute(text('SELECT * FROM receipts')).mappings().one()
        assert r['folio']=='2026-0017' and r['storage_name']=='original.pdf' and r['concept']=='' and r['company_id']=='co'
        assert db.execute(text('PRAGMA foreign_key_check')).all()==[]
    old.dispose()
