export const dossierSections=['Resumen','Obligaciones','Documentos','FIEL/CSD','Actividad'];
export function dossierSection(tab:string|null){
 if(tab==='Cumplimiento'||tab==='Histórico fiscal')return 'Obligaciones';
 if(tab==='Credenciales y Certificados'||tab==='e.firma y CSD')return 'FIEL/CSD';
 if(tab==='Tareas'||tab==='Historial'||tab==='Declaraciones')return 'Actividad';
 if(tab==='Explorador documental')return 'Documentos';
 return dossierSections.includes(tab||'')?tab!:'Resumen';
}
export function dossierUrl(id:string,tab:string|null,period:string,context?:URLSearchParams){
 const q=new URLSearchParams({tab:dossierSection(tab),period});for(const key of ['query','accountant','status','archive','sort']){const value=context?.get(key);if(value)q.set(key,value)}
 return '/empresas/'+encodeURIComponent(id)+'?'+q;
}
export function directoryUrl(params:URLSearchParams){
 const q=new URLSearchParams(params);q.set('tab','Directorio');return '/empresas?'+q;
}
