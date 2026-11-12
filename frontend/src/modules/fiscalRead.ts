import {useEffect,useState} from 'react';
import {api,csv} from '../api';
export type Summary={attention_state:string;counts:Record<string,number>;universe:number;registered:number;implicit:number;verified_fulfilled:number;fulfilled_unverified:number;denominators:Record<string,number>};
export type FiscalCell={id:string|null;cell_key:string;company_id:string;concept:string;obligation_id:string;period_id:string;status:string;effective_status:string;persisted:boolean;provenance:string;verification_state:string;due_date:string|null;due_verified:boolean;payment:string;payment_condition:string|null;responsible_name:string;revision:number;submitted_at:string|null};
export type FiscalRead={cells:FiscalCell[];summary:Summary;company_summaries:Record<string,Summary>;historical:{id:string;company_id:string;title:string;period:string;status:string;reference:string;notes:string;period_reliable:boolean}[]};
export function useFiscalRead(period:string,companyId?:string,includeArchived=false){
 const [data,setData]=useState<FiscalRead|null>(null),[error,setError]=useState(''),[reload,setReload]=useState(0);
 useEffect(()=>{const update=()=>setReload(n=>n+1);window.addEventListener('contasuite-data-changed',update);return()=>window.removeEventListener('contasuite-data-changed',update)},[]);
 useEffect(()=>{const abort=new AbortController();setData(null);setError('');const [year,month]=period.split('-');const q=new URLSearchParams({year,month,include_archived:String(includeArchived)});if(companyId)q.set('company_id',companyId);api<FiscalRead>('/fiscal-control?'+q,'GET',undefined,abort.signal).then(setData).catch(e=>{if(!abort.signal.aborted)setError(e.message)});return()=>abort.abort()},[period,companyId,reload,includeArchived]);
 return {data,error};
}
export function fiscalStatus(summary?:Summary){
 return summary?.attention_state||'Sin información';
}
export function exportFiscal(data:FiscalRead,period:string){
 csv('Obligaciones_'+period+'.csv',[['Empresa ID','Concepto','Periodo real','Estado registrado','Estado efectivo','Verificación','Fecha límite confirmada','Pago','Condición de pago','Origen','Persistido','Universo','Registradas'],...data.cells.map(r=>[r.company_id,r.concept,r.period_id,r.status,r.effective_status,r.verification_state,r.due_verified?r.due_date||'':'',r.payment,r.payment_condition||'Sin información',r.provenance,String(r.persisted),String(data.summary.universe),String(data.summary.registered)])]);
}
