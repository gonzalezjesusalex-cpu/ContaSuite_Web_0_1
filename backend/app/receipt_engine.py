"""Recibos: validación, PDF, folios e historial persistente sin dependencias de interfaz."""
from __future__ import annotations
import ctypes
import io
import os
import re
import sqlite3
import sys
import unicodedata
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
MONTHS = ('Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre')
DEFAULTS = {'receiver':'EDUARDO GONZALEZ RUIZ','place':'OAXACA DE JUÁREZ, OAXACA'}

def documents_folder():
    if sys.platform == 'win32':
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buf)==0:
            return Path(buf.value)
    return Path.home()/'Documents'

def money(value):
    try:
        raw = Decimal(str(value).replace('$','').replace(',','').strip())
        if not raw.is_finite() or raw <= 0 or raw > Decimal('999999999.99'):
            raise ValueError('El monto debe ser mayor a cero y no superar $999,999,999.99.')
        result = raw.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        if result <= 0: raise ValueError('El monto mínimo es $0.01.')
        return result
    except InvalidOperation:
        raise ValueError('Escribe un monto válido, por ejemplo 2500.00.') from None

def number_words(n):
    units = ['CERO','UNO','DOS','TRES','CUATRO','CINCO','SEIS','SIETE','OCHO','NUEVE','DIEZ','ONCE','DOCE','TRECE','CATORCE','QUINCE','DIECISÉIS','DIECISIETE','DIECIOCHO','DIECINUEVE','VEINTE','VEINTIUNO','VEINTIDÓS','VEINTITRÉS','VEINTICUATRO','VEINTICINCO','VEINTISÉIS','VEINTISIETE','VEINTIOCHO','VEINTINUEVE']
    if n<30: return units[n]
    if n<100:
        return ['','','','TREINTA','CUARENTA','CINCUENTA','SESENTA','SETENTA','OCHENTA','NOVENTA'][n//10]+(' Y '+units[n%10] if n%10 else '')
    if n==100: return 'CIEN'
    if n<1000:
        h=['','CIENTO','DOSCIENTOS','TRESCIENTOS','CUATROCIENTOS','QUINIENTOS','SEISCIENTOS','SETECIENTOS','OCHOCIENTOS','NOVECIENTOS'][n//100]
        return h+(' '+number_words(n%100) if n%100 else '')
    if n<1000000:
        return ('MIL' if n//1000==1 else apocope(number_words(n//1000))+' MIL')+(' '+number_words(n%1000) if n%1000 else '')
    return ('UN MILLÓN' if n//1000000==1 else apocope(number_words(n//1000000))+' MILLONES')+(' '+number_words(n%1000000) if n%1000000 else '')

def apocope(s):
    if s.endswith('VEINTIUNO'): return s[:-9]+'VEINTIÚN'
    if s.endswith('UNO'): return s[:-3]+'UN'
    return s

def amount_words(value):
    v=money(value); whole=int(v); cents=int((v-whole)*100)
    suffix=' DE PESOS' if whole and whole%1000000==0 else (' PESO' if whole==1 else ' PESOS')
    return f'{apocope(number_words(whole))}{suffix} {cents:02d}/100 M.N.'

def validate(data):
    name=' '.join(str(data.get('name','')).split())
    if not name or len(name)>220: raise ValueError('Escribe un nombre de contribuyente de hasta 220 caracteres.')
    try:
        month=int(data['month']); year=int(data['year']); issued=date.fromisoformat(str(data['issued']))
        if not 1<=month<=12 or not 1900<=year<=2100: raise ValueError()
    except (ValueError,KeyError,TypeError): raise ValueError('Revisa el mes, año y fecha de emisión (AAAA-MM-DD).') from None
    concept=' '.join(str(data.get('concept','')).split())
    if len(concept)>500:raise ValueError('El concepto admite hasta 500 caracteres.')
    return dict(concept=concept,name=name.upper(),month=month,year=year,issued=issued.isoformat(),amount=str(money(data['amount'])))

def slug(s):
    text=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode()
    return re.sub('[^A-Z0-9]+','_',text.upper()).strip('_')[:100] or 'CONTRIBUYENTE'

def receipt_pdf(data, settings=None):
    d=validate(data); cfg=dict(DEFAULTS); cfg.update(settings or {})
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=(612,792))
    c.setTitle('Recibo '+d.get('name','')); c.setAuthor(cfg['receiver'])
    bg=BASE/'assets/membrete.png'
    if bg.exists(): c.drawImage(str(bg),0,0,width=612,height=792)
    c.setFillColorRGB(0,0,0); c.setFont('Helvetica-Bold',11)
    c.drawRightString(558,610,f"BUENO POR ${Decimal(d['amount']):,.2f}")
    folio=data.get('folio','VISTA PREVIA')
    c.setFont('Helvetica',8); c.drawRightString(558,594,'FOLIO '+str(folio))
    body=(f"RECIBÍ DE {escape(d['name'])} <b><u>LA CANTIDAD DE ${Decimal(d['amount']):,.2f} "
          f"({amount_words(d['amount'])})</u></b>. POR CONCEPTO DE "
          + (escape(d['concept']) if d['concept'] else f"SERVICIOS CONTABLES DEL MES DE {MONTHS[d['month']-1].upper()} {d['year']}") + ".")
    style=ParagraphStyle('receipt',fontName='Helvetica',fontSize=11,leading=15,alignment=4)
    p=Paragraph(body,style); _,h=p.wrap(504,180)
    while h>120 and style.fontSize>8:
        style.fontSize-=.5;style.leading=style.fontSize+3
        p=Paragraph(body,style);_,h=p.wrap(504,180)
    if h>120:raise ValueError('El concepto es demasiado largo para el formato del recibo. Reduce el texto.')
    p.drawOn(c,54,505-h)
    dt=date.fromisoformat(d['issued'])
    when=f'{dt.day} DE {MONTHS[dt.month-1].upper()} DEL {dt.year}'
    p=Paragraph('PARA CONSTANCIA Y VALIDEZ SE EXTIENDE LA PRESENTE EL DÍA '+f'<b><u>{when}</u></b>, '+escape(cfg['place'].upper())+'.',style)
    _,h=p.wrap(504,100); p.drawOn(c,54,365-h)
    c.setFont('Helvetica-Bold',11); c.drawCentredString(306,260,'RECIBE')
    c.setLineWidth(.6); c.line(190,192,422,192)
    # Long recipient names wrap within the signature area.
    p=Paragraph(escape(cfg['receiver'].upper()),ParagraphStyle('sign',fontName='Helvetica',fontSize=10,leading=12,alignment=1))
    _,h=p.wrap(340,60); p.drawOn(c,136,184-h)
    c.showPage(); c.save(); return out.getvalue()

