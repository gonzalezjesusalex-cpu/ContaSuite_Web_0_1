"""Deterministic, conservative content classification. No filename guesses or OCR."""
import re
import hashlib
import json
from datetime import datetime
from pathlib import Path
from defusedxml import ElementTree

RFC = re.compile(r'(?<![A-Z0-9Ñ&])([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})(?![A-Z0-9])')
GENERIC = {'XAXX010101000', 'XEXX010101000'}
CFDI_NAMESPACES = {'http://www.sat.gob.mx/cfd/3', 'http://www.sat.gob.mx/cfd/4'}


def catalog_digest(companies):
    return hashlib.sha256(json.dumps(sorted((c['id'], c['rfc'].upper()) for c in companies)).encode()).hexdigest()


def valid_rfc(value):
    value = value.upper().strip()
    if not RFC.fullmatch(value) or value in GENERIC:
        return False
    try:
        datetime.strptime(value[-9:-3], '%y%m%d')
        return True
    except ValueError:
        return False


def classify(stream, name, companies):
    """Only complete CFDI or a complete text PDF with exactly one known RFC auto-links.

    Results contain RFC/role evidence only, never raw document text or provider paths.
    PDF extraction is run by the worker in an isolated time-limited process.
    """
    # Private keys are rejected before even seeking/reading the supplied stream.
    if Path(name).suffix.lower() == '.key':
        return {'evidence': {'rule': 'rfc-v1', 'reason': 'private_key_excluded', 'rfcs': [], 'complete': False},
                'links': [], 'automatic': False, 'type': 'unknown', 'period': None}
    stream.seek(0)
    evidence = {'rule': 'rfc-v1', 'reason': 'no_rfc', 'rfcs': [], 'complete': True,
                'catalog_digest': catalog_digest(companies)}
    kind, period, roles = 'unknown', None, []
    try:
        if Path(name).suffix.lower() == '.xml':
            root = ElementTree.parse(stream, forbid_dtd=True, forbid_entities=True, forbid_external=True).getroot()
            namespace = root.tag[1:].split('}')[0] if root.tag.startswith('{') else ''
            if namespace in CFDI_NAMESPACES and root.tag == '{' + namespace + '}Comprobante':
                kind = 'cfdi'
                stamps=root.findall('.//{http://www.sat.gob.mx/TimbreFiscalDigital}TimbreFiscalDigital')
                uuids=[s.attrib.get('UUID','').strip().upper() for s in stamps]
                valid_uuid=len(uuids)==1 and bool(re.fullmatch(r'[0-9A-F]{8}-(?:[0-9A-F]{4}-){3}[0-9A-F]{12}',uuids[0]))
                evidence['cfdi_uuid']=uuids[0] if valid_uuid else None
                evidence['uuid_status']='valid' if valid_uuid else 'missing' if not uuids else 'contradictory'
                if uuids and not valid_uuid:evidence['complete']=False
                date = root.attrib.get('Fecha', '')
                try:
                    period = datetime.fromisoformat(date).strftime('%Y-%m')
                    if not 2000 <= int(period[:4]) <= 2100:
                        period = None
                except ValueError:
                    pass
                for tag, role in [('Emisor', 'issuer'), ('Receptor', 'receiver')]:
                    nodes = root.findall('{' + namespace + '}' + tag)
                    values = [''.join(node.attrib.get('Rfc', '').split()).upper() for node in nodes]
                    if len(values) != 1 or not (valid_rfc(values[0]) or values[0] in GENERIC):
                        evidence['complete'] = False
                    roles.extend({'rfc': value, 'role': role} for value in values if valid_rfc(value))
            else:
                # Other XMLs provide suggestions, never automatic fiscal links.
                evidence['complete'] = False
                text = ElementTree.tostring(root, encoding='unicode').upper()
                roles = [{'rfc': r, 'role': 'owner'} for r in sorted(set(RFC.findall(text))) if valid_rfc(r)]
        elif Path(name).suffix.lower() == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                raise ValueError('encrypted')
            if len(reader.pages) > 10:
                evidence['complete'] = False
            text = ''
            for page in list(reader.pages)[:10]:
                text += '\n' + (page.extract_text() or '')
                if len(text) > 100000:
                    evidence['complete'] = False
                    text = text[:100000]
                    break
            roles = [{'rfc': r, 'role': 'owner'} for r in sorted(set(RFC.findall(text.upper()))) if valid_rfc(r)]
        else:
            evidence['reason'] = 'unsupported_classification'
            return {'evidence': evidence, 'links': [], 'automatic': False, 'type': kind, 'period': None}
    except Exception:
        evidence.update(reason='unreadable_content', complete=False)
    evidence['rfcs'] = roles[:100]
    if len(roles) > 100:
        evidence['complete'] = False
    known = {}
    for c in companies:
        key = ''.join(c['rfc'].split()).upper()
        known.setdefault(key, set()).add(c['id'])
    ambiguous = any(len(known.get(r['rfc'], set())) > 1 for r in evidence['rfcs'])
    links = [dict(company_id=next(iter(known[r['rfc']])), role=r['role'])
             for r in evidence['rfcs'] if len(known.get(r['rfc'], set())) == 1]
    links = [dict(company_id=cid, role=role) for cid, role in sorted({(l['company_id'], l['role']) for l in links})]
    distinct_rfcs = {r['rfc'] for r in roles}
    # CFDI naturally includes an external counterparty; other formats must have one RFC total.
    automatic = bool(links) and not ambiguous and evidence['complete'] and len({l['company_id'] for l in links}) == 1
    if kind != 'cfdi' and len(distinct_rfcs) != 1:
        automatic = False
    evidence['authority_validated'] = False
    evidence['reason'] = ('ambiguous_identity' if ambiguous else 'unambiguous' if automatic else 'multiple_companies' if len({l['company_id'] for l in links}) > 1
                          else 'incomplete_content' if not evidence['complete'] else 'unknown_rfc' if roles else 'no_rfc')
    return {'evidence': evidence, 'links': links, 'automatic': automatic, 'type': kind, 'period': period}
