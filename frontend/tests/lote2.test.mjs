import assert from 'node:assert/strict';
import {test} from 'node:test';
import {dossierUrl,dossierSection,directoryUrl} from '../src/companyNavigation.ts';
import {markDirty,hasDirty,clearDirtyForms,markFormSaved,confirmDiscard} from '../src/dirtyForms.ts';
import {updateArchiveWarnings,confirmArchivedCapture} from '../src/archiveWarnings.ts';
globalThis.window={confirm:()=>false};
test('company switch preserves compatible section, period and directory filters; drops evidence/view',()=>{
 const context=new URLSearchParams({query:'RFC',archive:'all',view:'old',document_id:'secret'});
 const url=new URL(dossierUrl('b','Cumplimiento','2026-11',context),'http://synthetic');
 assert.equal(url.pathname,'/empresas/b');assert.equal(url.searchParams.get('tab'),'Obligaciones');
 assert.equal(url.searchParams.get('period'),'2026-11');assert.equal(url.searchParams.get('archive'),'all');
 assert.equal(url.searchParams.has('document_id'),false);assert.equal(url.searchParams.has('view'),false);
 assert.equal(new URL(directoryUrl(url.searchParams),'http://synthetic').searchParams.get('tab'),'Directorio');
});
test('legacy sections map to compatible new sections',()=>{
 assert.equal(dossierSection('e.firma y CSD'),'FIEL/CSD');assert.equal(dossierSection('Historial'),'Actividad');assert.equal(dossierSection('invalid'),'Resumen');
});
test('dirty forms require consent, retain changes on cancel, and reset on consent',()=>{
 clearDirtyForms();const form={isConnected:true};markDirty(form);assert.equal(hasDirty(),true);
 window.confirm=()=>false;assert.equal(confirmDiscard(),false);assert.equal(hasDirty(),true);
 window.confirm=()=>true;assert.equal(confirmDiscard(),true);assert.equal(hasDirty(),false);
});
test('saving one form preserves another draft, detached company forms cannot transfer',()=>{
 const a={isConnected:true},b={isConnected:true};markDirty(a);markDirty(b);markFormSaved(a);assert.equal(hasDirty(),true);
 b.isConnected=false;assert.equal(hasDirty(),false);
});
test('archived captures warn, allow consent, and never restore automatically',()=>{
 updateArchiveWarnings([{id:'a',archived:true},{id:'b',archived:false}]);window.confirm=()=>false;
 assert.equal(confirmArchivedCapture('/fiscal-control/cell','PUT',{company_id:'a'}),false);
 assert.equal(confirmArchivedCapture('/tasks','POST',{company_id:'a'}),false);
 assert.equal(confirmArchivedCapture('/companies/a','PUT',{}),false);
 assert.equal(confirmArchivedCapture('/tasks','POST',{company_id:'b'}),true);
 window.confirm=()=>true;assert.equal(confirmArchivedCapture('/fiscal-control/cell','PUT',{company_id:'a'}),true);
 window.confirm=()=>false;assert.equal(confirmArchivedCapture('/fiscal-control/cell','PUT',{company_id:'a'}),false);
});
