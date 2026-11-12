"""Convert trusted Stitch exports to React-renderable element trees; no HTML injection or remote scripts."""
from html.parser import HTMLParser
from pathlib import Path
import json,re,sys
source=Path(sys.argv[1]);target=Path(__file__).resolve().parents[1]/'frontend'
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Parser(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.root={'tag':'root','attrs':{},'children':[]};self.stack=[self.root]
 def handle_starttag(self,tag,attrs):
  n={'tag':tag,'attrs':dict(attrs),'children':[]};self.stack[-1]['children'].append(n)
  if tag not in VOID:self.stack.append(n)
 def handle_startendtag(self,t,a):self.handle_starttag(t,a);self.handle_endtag(t)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i]['tag']==tag:self.stack=self.stack[:i];break
 def handle_data(self,data):self.stack[-1]['children'].append(data)
def find(n,t):
 if isinstance(n,str):return None
 if n['tag']==t:return n
 for c in n['children']:
  found=find(c,t)
  if found:return found

def clean(n):
 if isinstance(n,str):return n
 if n['tag'] in {'script','style','iframe','img'}:return None
 a=n['attrs'];a={k:v for k,v in a.items() if not k.startswith('on') and k not in ['href','src','action','id','data-path']}
 if n['tag']=='main':a['class']='stitch-main';n['tag']='section'
 n['attrs']=a;n['children']=[v for c in n['children'] if (v:=clean(c)) is not None and not (n['tag'] in {'table','thead','tbody','tfoot','tr','colgroup'} and isinstance(v,str) and not v.strip())];return n
mapping={'recopilador-cfdi':'recopilador_cfdi_contasuite','organizador-cfdi':'organizador_cfdi_contasuite','renombrador':'renombrador_de_cotizaciones_contasuite','relacionador':'relacionador_documental_contasuite','recibos':'generador_de_recibos_contasuite','impresion':'centro_de_impresi_n_contasuite','configuracion':'configuraci_n_del_sistema_contasuite'}
for slug,name in mapping.items():
 p=Parser();p.feed((source/name/'code.html').read_text());main=find(p.root,'main');(target/'src/designs'/f'{slug}.json').write_text(json.dumps(clean(main),ensure_ascii=False))
s=(source/'empresas_centro_de_control_fiscal/code.html').read_text();config=re.search(r'tailwind.config=(.*?);</script>',s).group(1)
# Stitch configuration is a trusted, local JavaScript object, copied as build configuration only.
(target/'tailwind.config.cjs').write_text('module.exports={content:["./index.html","./src/**/*.{ts,tsx,json}"],'+config.removeprefix('{').removesuffix('}')+'};\n')
