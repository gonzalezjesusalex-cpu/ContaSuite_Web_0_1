import io
import zipfile
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from test_api import client, A, company

UUID='11111111-2222-3333-4444-555555555555'
OTHER='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'

def pdf(*lines):
    stream=io.BytesIO();c=canvas.Canvas(stream)
    y=750
    for line in lines:c.drawString(50,y,line);y-=20
    c.save();return stream.getvalue()

def xml(uuid):
    return f'<Comprobante TipoDeComprobante="I" Fecha="2026-10-01"><TimbreFiscalDigital UUID="{uuid}"/></Comprobante>'.encode()

def source():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('Polizas/compra.Pdf',pdf('IMPRESO DE POLIZAS','Compra (Egreso)','Fecha 05/10/2026','Descripcion Compra prueba','CFDI asociados a la poliza',UUID))
        z.writestr('Polizas/diario.pdf',pdf('IMPRESO DE POLIZAS','Diario (Manual)','Fecha 03/11/2026','Descripcion Ajuste prueba'))
        z.writestr(f'CFDI/{UUID}.XML',xml(UUID));z.writestr(f'CFDI/{UUID}.pdf',pdf('Comprobante relacionado'))
        z.writestr(f'CFDI/{OTHER}.xml',xml(OTHER));z.writestr(f'CFDI/{OTHER}.pdf',pdf('Comprobante sobrante'))
        z.writestr('ignorado.txt','No entra en el motor')
    return stream.getvalue()

def upload(client,payload,filename='documentos.zip',company_id=''):
    return client.post('/api/recopila/runs',headers=A,files={'files':(filename,payload,'application/zip')},data={'company_id':company_id})

def test_recopila_original_rules_and_outputs(client):
    c=company(client).json();r=upload(client,source(),company_id=c['id']);assert r.status_code==202
    ident=r.json()['id'];base='/api/recopila/runs/'+ident
    detail=client.get(base,headers=A).json();run=detail['run']
    assert run['status']=='analyzed' and run['summary']['policy_pages']==2
    assert run['summary']['policies_with_document']==1 and run['summary']['leftover_cfdi_pdfs']==1
    assert len(detail['warnings']) if 'warnings' in detail else len(run['warnings'])
    assert [p['month'] for p in detail['policies']]==['2026-11','2026-10']
    assert any(p['status']=='POLIZA_SOLA_DIARIO' for p in detail['policies'])
    assert client.post(base+'/generate',headers=A,json={'by_month':True}).status_code==202
    result=client.get(base,headers=A).json()
    assert result['run']['status']=='generated'
    names={f['name'] for f in result['outputs']}
    assert {'RECOPILADOR.pdf','SOBRANTES.pdf','SEPARADORES_MESES.pdf','resumen.json','reporte_polizas.csv','sobrantes.csv','POR_MESES/2026-10_OCTUBRE.pdf','POR_MESES/2026-11_NOVIEMBRE.pdf'}==names
    file=client.get(base+'/file',headers=A,params={'name':'RECOPILADOR.pdf'})
    pages=PdfReader(io.BytesIO(file.content)).pages
    assert len(pages)==3 and 'Ajuste prueba' in pages[0].extract_text()
    assert 'Comprobante relacionado' in pages[2].extract_text()
    original=client.get(base+'/file',headers=A,params={'name':detail['policies'][1]['source'],'kind':'input'})
    assert original.content.startswith(b'%PDF')
    archive=client.get(base+'/zip',headers=A)
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:assert set(z.namelist())==names
    assert client.delete('/api/companies/'+c['id'],headers=A).status_code==409

def test_recopila_auth_and_upload_validation(client):
    assert client.get('/api/recopila/runs').status_code==401
    assert upload(client,source(),company_id='missing').status_code==404
    assert upload(client,b'hello','file.key').status_code==422
    bad=io.BytesIO()
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../evil.pdf',pdf('test'))
    r=upload(client,bad.getvalue());base='/api/recopila/runs/'+r.json()['id']
    assert client.get(base,headers=A).json()['run']['status']=='error'
    assert client.get(base+'/file',headers=A,params={'kind':'input','name':'../../secret.pdf'}).status_code==404
    assert client.post(base+'/generate',headers=A,json={}).status_code==409
    assert client.get(base+'/zip',headers=A).status_code==409
    assert upload(client,b'broken.zip').status_code==202

def test_recopila_empty_input_and_multiple_documents(client):
    r=client.post('/api/recopila/runs',headers=A,files=[('files',('folder/plain.pdf',pdf('Documento sin poliza'),'application/pdf')),('files',('folder/notas.xml',b'<invalid/>','text/xml'))])
    assert r.status_code==202
    base='/api/recopila/runs/'+r.json()['id'];result=client.get(base,headers=A).json()
    assert result['run']['status']=='analyzed' and result['run']['summary']['policy_pages']==0
    assert result['run']['warnings']
    assert client.post(base+'/generate',headers=A,json={}).status_code==422
