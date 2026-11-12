"""Redacted preview contract; no XLSX file is opened and no secrets are retained."""
def preview(rows,companies,headers):
    result=[];seen=set()
    # headers maps source names to 'rfc', 'service', 'secret', 'certificate_date'.
    for index,row in enumerate(rows,1):
        rfc=str(row.get(next((k for k,v in headers.items() if v=='rfc'),''),'')).strip().upper()
        matches=[c['id'] for c in companies if c['rfc'].upper()==rfc and rfc]
        service=str(row.get(next((k for k,v in headers.items() if v=='service'),''),'other'))
        # Never echo unknown columns, usernames, original cells, passwords, or formulas.
        key=(rfc,service);issues=[]
        if len(matches)!=1:issues.append('company_not_unique')
        if key in seen:issues.append('possible_duplicate')
        seen.add(key)
        result.append({'row':index,'company_id':matches[0] if len(matches)==1 else None,
                       'has_secret':any(bool(row.get(k)) for k,v in headers.items() if v=='secret'),
                       'has_certificate_date':any(bool(row.get(k)) for k,v in headers.items() if v=='certificate_date'),
                       'conflicts':issues,'requires_confirmation':True})
    return result
