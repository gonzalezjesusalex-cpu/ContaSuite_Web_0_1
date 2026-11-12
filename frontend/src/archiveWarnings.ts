let companies: {id:string;archived?:boolean|null}[]=[];
export function updateArchiveWarnings(value:typeof companies){companies=value}
export function confirmArchivedCapture(path:string,method:string,data:unknown){
 if(!['POST','PUT','PATCH'].includes(method.toUpperCase()))return true;
 if(!(/^\/companies\/[^/]+$/.test(path)||/^\/(tasks|obligations)(\/[^/]+)?$/.test(path)||path==='/fiscal-control/cell'||path==='/fiscal-control/applicability'))return true;
 const value=data as {company_id?:string}|undefined;
 const id=value?.company_id||(/^\/companies\/([^/]+)$/.exec(path)?.[1]);
 return !companies.some(c=>c.id===id&&c.archived===true)||window.confirm('Esta empresa está archivada. Puedes guardar con tus permisos actuales; la captura no la restaurará. ¿Continuar?');
}
