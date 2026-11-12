"""Metadata-only rules. No provider/SMB calls, file opening, OCR or private key handling."""
import re
from .company_reconcile import normalized_name,document_proposals

def propose(document,companies,rules,aliases=()):
    if document['name'].lower().endswith(('.key','.pfx','.p12','.pem')):
        return {'excluded':True,'reason':'private_material'}
    name=normalized_name(document['name']);context=normalized_name(document.get('path',''))
    hits=[]
    for rule in rules:
        if not rule['enabled']:continue
        file_terms=[term for term in rule['terms'] if re.search(r'\b'+re.escape(normalized_name(term))+r'\b',name)]
        path_terms=[term for term in rule['terms'] if re.search(r'\b'+re.escape(normalized_name(term))+r'\b',context)]
        if file_terms or path_terms:hits.append({'category_id':rule['category_id'],'rule_id':rule['id'],'confidence':.65 if file_terms else .35,'origin':'filename' if file_terms else 'folder_context'})
    association=document_proposals([document],companies,aliases)[0]
    years=set(re.findall(r'(?<!\d)(20\d{2})(?!\d)',document['name']+' '+document.get('path','')))
    period=association.get('period')
    return {'excluded':False,'categories':hits,'company_ids':association['company_ids'],'company_match':association['match'],'year':int(period[:4]) if period else int(next(iter(years))) if len(years)==1 else None,'period':period,'requires_review':True,'automatic_confirmation':False,'origin':'metadata_rules_v3','ambiguities':['multiple_categories'] if len(hits)>1 else []}

def analyze_public(payload,format,companies):
    """Explicit offline analyzer contract, bounded; never called against remote files automatically."""
    if len(payload)>1024*1024:raise ValueError('extraction_limit')
    if format=='cer':
        from .credential_api import parse_public_certificate
        return {'type':'certificate','public_metadata':parse_public_certificate(payload),'kind_inferred':False}
    if format=='xml':
        from io import BytesIO
        from .storage.classifier import classify
        return classify(BytesIO(payload),'public.xml',companies)
    if format=='xlsx':
        from .company_xlsx import read_xlsx
        return {'type':'metadata_preview','data':read_xlsx(payload,'fiscal_metadata'),'formulas_executed':False}
    # PDF extraction needs a sandboxed worker. XLSX uses the bounded existing importer only.
    return {'type':'pending','reason':'isolated_analyzer_required','ocr_enabled':False}
