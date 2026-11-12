import { createElement, type ReactNode, useState, useEffect } from 'react';
import { Eye, Construction } from 'lucide-react';
import { OriginalIcon, moduleIconNames } from '../components/OriginalIcon';
type Node=string|{tag:string;attrs:Record<string,string|null>;children:Node[]};
function render(node:Node,index=0):ReactNode {
 if(typeof node==='string')return node;
 const props:Record<string,unknown>={key:index};
 for(const [k,v] of Object.entries(node.attrs)){
  if(k==='style'&&v){const s:Record<string,string>={};for(const p of v.split(';')){const i=p.indexOf(':');if(i>0)s[p.slice(0,i).trim().replace(/-([a-z])/g,(_,a:string)=>a.toUpperCase())]=p.slice(i+1).trim()}props.style=s}
  else if(k==='class')props.className=v;
  else if(k==='for')props.htmlFor=v;
  else if(k==='value')props.defaultValue=v;
  else if(k==='checked')props.defaultChecked=true;
  else if(['selected'].includes(k))continue;
  else if(['disabled','multiple','required','readonly'].includes(k))props[k==='readonly'?'readOnly':k]=true;
  else if(!k.startsWith('on'))props[({tabindex:'tabIndex',colspan:'colSpan',rowspan:'rowSpan',strokeWidth:'strokeWidth',viewbox:'viewBox'} as Record<string,string>)[k]||k]=v;
 }
 if(['input','br','hr','img'].includes(node.tag))return createElement(node.tag,props);
 return createElement(node.tag,props,...node.children.map((c,i)=>render(c,i)));
}
const imports=import.meta.glob('../designs/*.json');
export default function DesignPreview({module,title}:{module:string;title:string}){
 const [tree,setTree]=useState<Node|null>(null);useEffect(()=>{let active=true;setTree(null);imports[`../designs/${module}.json`]?.().then(m=>{if(active)setTree((m as {default:Node}).default)});return()=>{active=false}},[module]);
 return <><div className="integration-notice">{moduleIconNames[module]?<OriginalIcon name={moduleIconNames[module]} size={40}/>:<Construction size={20}/>}<div><strong>{title} · Interfaz preparada</strong><p>Motor Python pendiente de integrar. La pantalla inferior conserva el diseño de Stitch con datos de ejemplo; sus acciones están deshabilitadas.</p></div><Eye size={19}/></div><div className="stitch-preview" inert aria-label={'Vista de diseño de '+title}>{tree?render(tree):<p>Cargando diseño…</p>}</div></>
}
