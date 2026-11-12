import {useEffect,useState} from 'react';
import {api} from '../api';
export default function ArchiveActivity({companyId,available}:{companyId:string;available:boolean}){
 const [rows,setRows]=useState<{id:string;action:string;actor_id:string;created_at:string}[]>([]),[error,setError]=useState('');
 useEffect(()=>{setRows([]);setError('');if(!available)return;const abort=new AbortController();api<typeof rows>('/company-lifecycle/'+companyId+'/history','GET',undefined,abort.signal).then(setRows).catch(e=>{if(!abort.signal.aborted)setError(e.message)});return()=>abort.abort()},[companyId,available]);
 return <section className="card padded"><h2>Actividad de archivado</h2>{error?<p role="alert">{error}</p>:!available?<p>Historial pendiente de activar el esquema de archivado.</p>:rows.length?rows.map(r=><p key={r.id}>{r.action==='archived'?'Archivada':'Restaurada'} · {r.actor_id} · {new Date(r.created_at).toLocaleString('es-MX')}</p>):<p>Sin eventos de archivado registrados.</p>}</section>;
}
