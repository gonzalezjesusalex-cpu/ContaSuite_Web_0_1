import {useEffect,useSyncExternalStore} from 'react';
import {useBlocker} from 'react-router-dom';
import {subscribeDirty,notifyDirty,markDirty,hasDirty,confirmDiscard} from './dirtyForms';
export {confirmDiscard,clearDirtyForms} from './dirtyForms';
export function UnsavedNavigation(){
 const changed=useSyncExternalStore(subscribeDirty,hasDirty);
 const blocker=useBlocker(()=>hasDirty());
 useEffect(()=>{if(blocker.state==='blocked'){if(confirmDiscard())blocker.proceed();else blocker.reset()}},[blocker]);
 useEffect(()=>{
  const input=(e:Event)=>{const target=e.target;if(target instanceof HTMLElement){const form=target.closest<HTMLElement>('form, dialog');if(form){markDirty(form)}}};
  const unload=(e:BeforeUnloadEvent)=>{if(hasDirty()){e.preventDefault();e.returnValue=''}};
  document.addEventListener('input',input,true);document.addEventListener('change',input,true);window.addEventListener('beforeunload',unload);
  const observer=new MutationObserver(()=>notifyDirty());observer.observe(document.body,{childList:true,subtree:true});
  return()=>{document.removeEventListener('input',input,true);document.removeEventListener('change',input,true);window.removeEventListener('beforeunload',unload);observer.disconnect()};
 },[]);
 return changed?<span className="sr-only" role="status">Hay cambios sin guardar.</span>:null;
}
