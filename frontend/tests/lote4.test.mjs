import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calendarPayload} from '../src/calendarForm.ts';
const form={title:'Revisión',obligation_id:'m',period_id:'2026-11',date:'2026-11-20',revision:0,reason:'Revisión interna',source_reference:'Instrucción sintética',rule_id:'',rule_version:0};
test('manual date preserves civil date and has no fiscal status',()=>{
 const result=calendarPayload(form,'a','date');assert.equal(result.date,'2026-11-20');assert.equal(result.company_id,'a');assert.equal(result.rule_id,null);assert.equal('status' in result,false);
});
test('missing fields and invalid civil date are rejected',()=>{
 assert.throws(()=>calendarPayload({...form,date:'2026-02-30'},'a','date'));
 assert.throws(()=>calendarPayload(form,'','date'));assert.throws(()=>calendarPayload({...form,reason:''},'a','date'));
});
test('rule version and source are explicit',()=>{
 const result=calendarPayload({...form,rule_id:'r',rule_version:2,revision:1},'a','date');assert.equal(result.rule_version,2);assert.equal(result.revision,1);
 assert.throws(()=>calendarPayload({...form,source_reference:''},'a','rule'));
 assert.equal(calendarPayload(form,'a','rule').source_reference,'Instrucción sintética');
});
