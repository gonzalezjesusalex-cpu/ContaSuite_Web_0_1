import {confirmArchivedCapture} from './archiveWarnings';
import {markFormSaved} from './dirtyForms';
export const getToken=()=>sessionStorage.getItem('contasuite-token')||'';
let lastActivity=Date.now();
for(const event of ['pointerdown','keydown','touchstart','wheel','focus'])window.addEventListener(event,e=>{if(e.isTrusted)lastActivity=Date.now()},{passive:true,capture:true});
export function authHeaders(){const csrf=document.cookie.split('; ').find(c=>c.startsWith('contasuite_csrf='))?.split('=')[1]||'';return {...(getToken()?{Authorization:'Bearer '+getToken()}:{}),'X-CSRF-Token':decodeURIComponent(csrf),'X-ContaSuite-Activity':Date.now()-lastActivity<60000?'1':'0'}}
export async function api<T>(path:string, method='GET', data?:unknown, signal?:AbortSignal, headers?:Record<string,string>):Promise<T>{
 if(!confirmArchivedCapture(path,method,data))throw new Error('Guardado cancelado.');
 const sourceForm=document.activeElement instanceof HTMLElement?document.activeElement.closest<HTMLElement>('form, dialog'):null;
 const response=await fetch('/api'+path,{method,signal,credentials:'same-origin',headers:{...authHeaders(),...(data instanceof FormData?{}:{'Content-Type':'application/json'}),...headers},body:data===undefined?undefined:data instanceof FormData?data:JSON.stringify(data)});
 if(!response.ok){if(response.status===401&&!['/auth/login','/auth/password','/auth/bootstrap'].includes(path))window.dispatchEvent(new Event('contasuite-session-expired'));let message='No se pudo completar la operación';try{const e=await response.json();message=typeof e.detail==='string'?e.detail:Array.isArray(e.detail)?e.detail.map((v:{msg:string})=>v.msg).join('. '):e.detail?.message||message}catch{/* response without JSON */}throw new Error(message)}
 if(!['GET','HEAD'].includes(method.toUpperCase())&&!path.startsWith('/auth/')){markFormSaved(sourceForm);window.dispatchEvent(new Event('contasuite-data-changed'))};
 return response.status===204?undefined as T:response.json();
}
export async function download(id:string,name:string){
 const response=await fetch('/api/documents/'+id+'/download',{headers:{Authorization:'Bearer '+getToken()}});
 if(!response.ok)throw new Error('No se pudo descargar el documento');
 const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export function csv(name:string, rows:string[][]){const text='\uFEFF'+rows.map(row=>row.map(v=>'"'+(/^[=+\-@\t\r]/.test(v)?"'":'')+v.replaceAll('"','""')+'"').join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
export const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
export const dateLabel=(date:string)=>new Date(date.length===10?date+'T12:00:00':date).toLocaleDateString('es-MX',{day:'2-digit',month:'short',year:'numeric'});
