type Form={title:string;obligation_id:string;period_id:string;date:string;revision:number;reason:string;source_reference:string;rule_id:string;rule_version:number};
export function calendarPayload(form:Form,companyId:string,mode:string){
 if(!companyId||!form.obligation_id||!form.period_id)throw new Error('Selecciona empresa, obligación y periodo.');
 if(form.title.trim().length<2||form.title.length>180||form.reason.trim().length<3||form.reason.length>1000)throw new Error('Completa título y motivo dentro de los límites.');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(form.date)||!Number.isFinite(Date.parse(form.date+'T12:00:00Z'))||new Date(form.date+'T12:00:00Z').toISOString().slice(0,10)!==form.date)throw new Error('Fecha civil inválida.');
 if(mode==='rule'&&form.source_reference.trim().length<3)throw new Error('Indica la fuente revisada de la regla.');
 return {company_id:companyId,obligation_id:form.obligation_id,period_id:form.period_id,title:form.title.trim(),date:form.date,revision:form.revision,reason:form.reason.trim(),rule_id:mode==='rule'?null:form.rule_id||null,rule_version:mode==='rule'||!form.rule_id?null:form.rule_version,...(mode==='rule'?{source_reference:form.source_reference}:{})};
}
