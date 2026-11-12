const dirty=new Set<{isConnected:boolean}>();
const listeners=new Set<()=>void>();
export function subscribeDirty(f:()=>void){listeners.add(f);return()=>{listeners.delete(f)}}
export function notifyDirty(){listeners.forEach(f=>f())}
export function markDirty(form:{isConnected:boolean}){dirty.add(form);notifyDirty()}
export function hasDirty(){for(const f of dirty)if(!f.isConnected)dirty.delete(f);return dirty.size>0}
export function clearDirtyForms(){dirty.clear();notifyDirty()}
export function markFormSaved(form:{isConnected:boolean}|null){if(form)dirty.delete(form);notifyDirty()}
export function confirmDiscard(){if(!hasDirty())return true;if(!window.confirm('Hay cambios sin guardar. ¿Descartarlos y continuar?'))return false;clearDirtyForms();return true}
