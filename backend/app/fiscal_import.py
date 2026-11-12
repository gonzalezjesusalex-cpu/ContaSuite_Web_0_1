"""Pure preview contract for a future XLSX reader. No database writes or file access.

The reader supplies sheets/cells, preserving coordinates, original types and values.
No final import endpoint is enabled in v0.1.
"""
import re
import unicodedata
from datetime import date,datetime

MONTHS=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',str(value)) if not unicodedata.combining(c)).lower().split())

def sheet_period(name):
    text=normalize(name);year=re.search(r'\b(20\d{2})\b',text)
    months=[i+1 for i,m in enumerate(MONTHS) if re.search(r'\b'+m+r'\b',text)]
    numeric=re.fullmatch(r'(20\d{2})[-/](0?[1-9]|1[0-2])',text)
    if numeric:return f'{int(numeric[1])}-{int(numeric[2]):02d}'
    return f'{year[1]}-{months[0]:02d}' if year and len(months)==1 else None

def classify(value):
    if value is None or value=='':return dict(kind='blank',status='unreviewed',original=value)
    if isinstance(value,(date,datetime)):return dict(kind='date',status='unreviewed',original=value.isoformat(),authority_validated=False)
    if normalize(value) in {'na','n/a','no aplica'}:return dict(kind='not_applicable',status='not_applicable',original=value)
    return dict(kind='text',status='unreviewed',original=value,requires_review=True)

def preview(sheets,companies,catalog):
    result=[];seen=set()
    for sheet in sheets:
        period=sheet_period(sheet['name'])
        for row in sheet['rows']:
            rfc=str(row.get('rfc','')).strip().upper()
            matches=[c for c in companies if rfc and c['rfc'].upper()==rfc]
            if not rfc:matches=[c for c in companies if normalize(c['name'])==normalize(row.get('name',''))]
            conflicts=[]
            if len(matches)!=1:conflicts.append('company_not_unique')
            if not period:conflicts.append('period_ambiguous')
            cells=[]
            for header,value in row['cells'].items():
                ids=[c['id'] for c in catalog if normalize(c['label'])==normalize(header)]
                payment=normalize(header)=='pago'
                issues=[] if len(ids)==1 or payment else ['unknown_header']
                if payment:issues.append('payment_obligation_required')
                key=(matches[0]['id'] if len(matches)==1 else None,ids[0] if len(ids)==1 else None,period)
                if key[0] and key[1] and period:
                    if key in seen:issues.append('duplicate_cell')
                    seen.add(key)
                cells.append(dict(header=header,value=classify(value),obligation_id=ids[0] if len(ids)==1 else None,conflicts=issues))
            result.append(dict(sheet=sheet['name'],row_number=row['number'],period=period,company_id=matches[0]['id'] if len(matches)==1 else None,cells=cells,conflicts=conflicts,original=row))
    return result
