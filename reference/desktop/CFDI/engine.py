"""Motor fiel a Organizar_CFDI.bat. La GUI consume analyze -> Plan -> execute.
Clasifica exclusivamente por las rutas del BAT, nunca por el contenido del XML.
"""
from __future__ import annotations
import csv
import hashlib
import os
import re
import shutil
import threading
from dataclasses import dataclass,field,asdict
from pathlib import Path

MONTHS=('ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE')
RFC_RE=re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
@dataclass(frozen=True)
class Options:
    source:str
    destination:str
    rfc:str
    year:int
    months:tuple[int,...]=tuple(range(1,13))
    kinds:tuple[str,...]=('Emitidos','Recibidos')
    extensions:tuple[str,...]=('.xml','.pdf')
    operation:str='move'
    reports:bool=True
@dataclass
class Item:
    source:str
    destination:str=''
    date:str=''
    kind:str=''
    uuid:str=''
    state:str='Revisar'
    reason:str=''
    size:int=0
    mtime_ns:int=0
@dataclass
class Plan:
    options:Options
    items:list[Item]=field(default_factory=list)
    @property
    def ready(self):return [i for i in self.items if i.state=='Listo']
@dataclass
class Result:
    records:list[dict]=field(default_factory=list)
    cancelled:bool=False
    @property
    def errors(self):return sum(r['state']=='Error' for r in self.records)

def month_folder(o,month):return Path(o.destination).resolve()/f'{month:02d}.- {MONTHS[month-1]}'
def validate(o):
    if not RFC_RE.fullmatch(o.rfc):raise ValueError('Ingresa un RFC válido de 12 o 13 caracteres.')
    if not 2000<=o.year<=2100:raise ValueError('El ejercicio debe estar entre 2000 y 2100.')
    if not o.months or any(m not in range(1,13) for m in o.months):raise ValueError('Selecciona al menos un mes válido.')
    if not o.kinds or not set(o.kinds)<={'Emitidos','Recibidos'}:raise ValueError('Selecciona Emitidos o Recibidos.')
    if not set(o.extensions)<={'.xml','.pdf'} or (not o.extensions and not o.reports):raise ValueError('Selecciona PDF, XML o reportes Excel.')
    if o.operation not in ('copy','move'):raise ValueError('Operación desconocida.')
    if not o.source.strip() or not Path(o.source).is_dir():raise ValueError('La carpeta base de origen no existe.')
    if not o.destination.strip():raise ValueError('Selecciona la carpeta de destino de la empresa y ejercicio.')
    a,b=Path(o.source).resolve(),Path(o.destination).resolve()
    if a==b or a.is_relative_to(b) or b.is_relative_to(a):raise ValueError('Origen y destino deben estar separados: ninguno puede estar dentro del otro.')

def _child(parent,name):
    """Windows ignora mayúsculas; reproduce esa selección también en las pruebas."""
    direct=parent/name
    if direct.exists():return direct
    if parent.is_dir():
        matches=[p for p in parent.iterdir() if p.name.casefold()==name.casefold()]
        if len(matches)>1:raise ValueError(f'Hay nombres ambiguos: {direct}')
        if matches:return matches[0]
    return direct

def _safe_source(p,root):
    if p.is_symlink() or not p.resolve().is_relative_to(root):return False
    return not any(a.is_symlink() for a in p.parents if a!=root and a.is_relative_to(root))

def analyze(o,progress=None,cancel:threading.Event|None=None):
    validate(o);root=Path(o.source).resolve();plan=Plan(o)
    for n,month in enumerate(o.months):
        if cancel and cancel.is_set():raise InterruptedError('Análisis cancelado.')
        period=f'{o.year}-{month:02d}';out=month_folder(o,month)
        def add(p,dst,kind):
            if not _safe_source(p,root):return
            st=p.stat();item=Item(str(p),str(dst),period,kind,state='Listo',reason='Archivo directo de la ruta original del BAT.',size=st.st_size,mtime_ns=st.st_mtime_ns)
            # Igual que el BAT: la existencia del nombre basta para omitirlo.
            if _child(dst.parent,dst.name).exists():item.state='Duplicado';item.reason='Nombre existente en destino; se omite y se conserva el origen.'
            plan.items.append(item)
        for kind in o.kinds:
            folder=_child(_child(_child(root,kind),o.rfc),period)
            if not _safe_source(folder,root):
                plan.items.append(Item(str(folder),date=period,kind=kind,state='Omitido',reason='Ruta enlazada o fuera del origen; no se procesa.'));continue
            if not folder.is_dir():
                plan.items.append(Item(str(folder),date=period,kind=kind,state='Omitido',reason='No existe la carpeta de origen.'));continue
            for p in sorted(folder.iterdir()):
                if cancel and cancel.is_set():raise InterruptedError('Análisis cancelado.')
                if p.is_file() and p.suffix.lower() in o.extensions:add(p,out/kind.upper()/p.name,kind)
        if o.reports:
            reports=_child(root,'Reportes')
            for kind in o.kinds:
                for ext in ('.xls','.xlsx','.xlsm'):
                    p=_child(reports,f'{kind.upper()}-{o.rfc}-{o.year}{month:02d}{ext}')
                    if p.is_file():add(p,out/p.name,f'Reporte {kind}')
        if progress:progress(n+1,len(o.months),f'Revisando {period}')
    return plan

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.digest()

def _mkdir_safe(path,root):
    if not path.resolve().is_relative_to(root):raise ValueError('La carpeta de destino apunta fuera de la ubicación elegida.')
    path.mkdir(parents=True,exist_ok=True)

def execute(plan,progress=None,cancel:threading.Event|None=None):
    o=plan.options;validate(o);result=Result();root=Path(o.destination).resolve();source_root=Path(o.source).resolve()
    if cancel and cancel.is_set():result.cancelled=True;return result
    # El BAT crea ambos tipos, incluso cuando no hay documentos.
    for month in o.months:
        if cancel and cancel.is_set():result.cancelled=True;return result
        for kind in ('EMITIDOS','RECIBIDOS'):_mkdir_safe(month_folder(o,month)/kind,root)
    for n,item in enumerate(plan.ready):
        if cancel and cancel.is_set():result.cancelled=True;break
        record=asdict(item);record.update(state='Error',reason='');result.records.append(record);created=None
        try:
            src=Path(item.source);target=Path(item.destination)
            if not _safe_source(src,source_root):raise ValueError('El origen cambió de ubicación.')
            if not any(target.parent in (month_folder(o,m),month_folder(o,m)/'EMITIDOS',month_folder(o,m)/'RECIBIDOS') for m in o.months):raise ValueError('Destino fuera de los meses seleccionados.')
            _mkdir_safe(target.parent,root)
            if _child(target.parent,target.name).exists():
                record.update(state='Duplicado',reason='Nombre existente en destino; se conserva el origen.');continue
            st=src.stat()
            if (st.st_size,st.st_mtime_ns)!=(item.size,item.mtime_ns):raise ValueError('El archivo cambió después del análisis. Vuelve a analizar.')
            original_hash=digest(src)
            try:handle=target.open('xb');created=target
            except FileExistsError:
                record.update(state='Duplicado',reason='Nombre creado durante el proceso; se conserva el origen.');continue
            with handle,src.open('rb') as reader:
                shutil.copyfileobj(reader,handle,1024*1024);handle.flush();os.fsync(handle.fileno())
            if digest(target)!=original_hash or digest(src)!=original_hash:raise ValueError('Falló la verificación; se conserva el origen.')
            st=src.stat()
            if (st.st_size,st.st_mtime_ns)!=(item.size,item.mtime_ns):raise ValueError('El archivo cambió durante la copia.')
            created=None;record.update(state='Copiado',reason='Copia verificada SHA-256.')
            if o.operation=='move':src.unlink();record.update(state='Movido',reason='Copia verificada; origen retirado.')
        except Exception as e:
            record.update(state='Error',reason=str(e))
            if created:
                try:created.unlink()
                except OSError:pass
        finally:
            if progress:progress(n+1,len(plan.ready),f'{record["state"]}: {Path(item.source).name}')
    return result

def export_csv(path,records):
    fields=['state','date','kind','uuid','source','destination','reason']
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for r in records:w.writerow({k:("'"+str(v) if str(v).startswith(('=','+','-','@')) else v) for k,v in r.items()})
