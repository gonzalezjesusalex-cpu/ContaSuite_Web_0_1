"""Private isolated content analysis. No network, raw text, keys or fiscal verification."""
import io
import re
from pathlib import Path
from .storage.classifier import classify, valid_rfc, CFDI_NAMESPACES, RFC
from .storage.internal import validate_payload
from .storage.providers import StorageError


def analyze(content, name):
    stream = io.BytesIO(content)
    try:
        validate_payload(stream, name, allow_public_cer=True)
    except StorageError as e:
        return {'type':'unknown','period':None,'identities':[], 'evidence':{'reason':e.code,'rfcs':[],'complete':False,'readable':False}}
    result = classify(stream, name, [])
    result['identities'] = []
    result['evidence']['readable'] = result['evidence'].get('reason') != 'unreadable_content'
    if Path(name).suffix.lower() == '.xml':
        from defusedxml import ElementTree
        root = ElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        for ns in CFDI_NAMESPACES:
            if root.tag != '{'+ns+'}Comprobante': continue
            for tag, role in [('Emisor','issuer'),('Receptor','receiver')]:
                for node in root.findall('{'+ns+'}'+tag):
                    rfc = ''.join(node.attrib.get('Rfc','').split()).upper()
                    if valid_rfc(rfc): result['identities'].append({'rfc':rfc,'name':node.attrib.get('Nombre','')[:220], 'role':role,'source':'CFDI XML declarado'})
    elif Path(name).suffix.lower() == '.pdf' and result['evidence']['readable']:
        from pypdf import PdfReader
        stream.seek(0)
        text = '\n'.join((p.extract_text() or '')[:10000] for p in list(PdfReader(stream).pages)[:10]).upper()
        phrases = [('CONSTANCIA DE SITUACI','Constancia fiscal'),('OPINI','Opinión de cumplimiento'),('ACUSE','Acuse'),('DECLARACI','Declaración'),('FACTURA','Factura PDF')]
        for phrase, label in phrases:
            if phrase in text:
                result['evidence']['suggested_label'] = label
                result['type'] = 'acknowledgement' if label=='Acuse' else 'declaration' if label=='Declaración' else 'other'
                break
    elif Path(name).suffix.lower() == '.cer':
        from cryptography import x509
        cert=x509.load_pem_x509_certificate(content) if content.lstrip().startswith(b'-----BEGIN') else x509.load_der_x509_certificate(content)
        candidates=sorted({r for attr in cert.subject for r in RFC.findall(str(attr.value).upper()) if valid_rfc(r)})
        result['type'] = 'certificate'
        result['evidence'].update(readable=True, reason='public_certificate', rfcs=[{'rfc':r,'role':'owner'} for r in candidates],
            suggested_label='Certificado público; sin validación SAT')
    result['evidence']['authority_validated'] = False
    return result


if __name__ == '__main__':
    from .storage.classify_process import memory_limit
    guard = memory_limit()
    import sys,json,base64
    payload = json.loads(sys.stdin.buffer.read(36*1024*1024))
    result = analyze(base64.b64decode(payload['content'],validate=True),payload['name'])
    sys.stdout.write(json.dumps(result))
