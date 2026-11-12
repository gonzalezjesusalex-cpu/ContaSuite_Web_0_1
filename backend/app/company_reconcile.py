"""Pure identity reconciliation; never creates or merges companies."""
import re
import unicodedata
from difflib import SequenceMatcher
from .storage.classifier import valid_rfc

def normalized_name(value):
    value=''.join(c for c in unicodedata.normalize('NFKD',str(value or '')) if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^A-Z0-9Ñ& ]',' ',value.upper()).split())

def normalized_rfc(value):return re.sub(r'\s+','',str(value or '')).upper()

def reconcile(rows,companies,aliases=()):
    result=[];seen=set()
    for row in rows:
        rfc=normalized_rfc(row.get('rfc'));name=normalized_name(row.get('name'));issues=[];candidates=[]
        matches=[c for c in companies if normalized_rfc(c['rfc'])==rfc] if rfc else []
        names={c['id']:[normalized_name(c['name'])] for c in companies}
        for a in aliases:
            if a['company_id'] in names:names[a['company_id']].append(normalized_name(a['name']))
        for c in companies:
            score=max((SequenceMatcher(None,name,n).ratio() for n in names[c['id']]),default=0) if name else 0
            if score>=.78:candidates.append({'company_id':c['id'],'confidence':round(score,3)})
        candidates.sort(key=lambda c:(-c['confidence'],c['company_id']))
        if not rfc:status='missing_rfc';issues.append('rfc_missing')
        elif not valid_rfc(rfc):status='manual_review';issues.append('rfc_invalid_format')
        elif len(matches)>1:status='identity_conflict';issues.append('multiple_rfc_matches')
        elif len(matches)==1:
            candidates=[{'company_id':matches[0]['id'],'confidence':1.0}]
            similarity=max((SequenceMatcher(None,name,n).ratio() for n in names[matches[0]['id']]),default=0)
            status='exact_rfc' if name and similarity>=.65 else 'identity_conflict'
            if status=='identity_conflict':issues.append('rfc_name_disagreement')
        elif candidates:
            status='possible_name';issues.append('name_is_not_identity')
            if len(candidates)>1:issues.append('multiple_name_candidates')
        else:status='new_company' if name else 'manual_review'
        identity=(('rfc',rfc) if rfc else ('name',name),row.get('source',{}).get('period'))
        if identity in seen:issues.append('duplicate_in_source');status='source_duplicate'
        seen.add(identity)
        result.append({**row,'rfc':rfc if valid_rfc(rfc) else '', 'name':str(row.get('name',''))[:220],
            'status':status,'candidates':candidates[:5],'conflicts':issues,'action':'pending',
            'format_valid':valid_rfc(rfc),'authority_validated':False})
    return result

def document_proposals(documents,companies,aliases=()):
    """Uses metadata only. Paths/names are evidence, never returned raw or treated as proof."""
    from .storage.classifier import RFC
    result=[]
    for doc in documents:
        text=' '.join(str(doc.get(k,'')) for k in ('name','path','metadata'))
        rfcs={r for r in RFC.findall(text.upper()) if valid_rfc(r)}
        exact=[c['id'] for c in companies if normalized_rfc(c['rfc']) in rfcs]
        known=doc.get('linked_company_ids',[])
        probable=set()
        for c in companies:
            options=[c['name']]+[a['name'] for a in aliases if a['company_id']==c['id']]
            if any(len(normalized_name(n))>8 and normalized_name(n) in normalized_name(text) for n in options):probable.add(c['id'])
        candidates=sorted(set(exact)|probable|set(known))
        kind='conflict' if len(candidates)>1 else 'unambiguous' if len(exact)==1 and len(candidates)==1 else 'probable' if candidates else 'unmatched'
        period=doc.get('period')
        if not period:
            periods=set(re.findall(r'(?<!\d)(20\d{2})[-_/](0[1-9]|1[0-2])(?!\d)',text))
            if len(periods)==1:
                year,month=next(iter(periods));period=year+'-'+month
        result.append({'document_id':doc['id'],'period':period,'match':kind,'company_ids':candidates,'action':'pending','evidence':['rfc_metadata'] if exact else ['name_or_path'] if probable else [],'requires_review':True})
    return result
