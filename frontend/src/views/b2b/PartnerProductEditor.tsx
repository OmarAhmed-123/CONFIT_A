import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { request } from '../../services/apiClient';
import { useModalFocus } from '../../hooks/useModalFocus';

type Editable = {id:number; title:string; title_ar:string; description:string; description_ar:string; base_price:number; category_id:number; color_family:string; material:string|null; care_instructions:string|null; status:string; thumbnail_url:string};

export function PartnerProductEditor({productId,onClose,onSaved}:{productId:number;onClose:()=>void;onSaved:()=>void}) {
  const { t } = useTranslation();
  const original=useRef<Editable|null>(null);
  const [value,setValue]=useState<Editable|null>(null);
  const [busy,setBusy]=useState(false); const [error,setError]=useState(false);
  const close=useCallback(()=>{if(!busy)onClose();},[busy,onClose]);
  const dialog=useModalFocus<HTMLDivElement>(close,true);
  useEffect(()=>{let live=true;request<Editable>(`/partner/catalog/products/${productId}`).then(v=>{if(live){setValue(v);original.current=v;}}).catch(()=>{if(live)setError(true);});return()=>{live=false;};},[productId]);
  const save=async(e:React.FormEvent)=>{
    e.preventDefault();if(!value)return;setBusy(true);setError(false);
    try {
      const {title,title_ar,description,description_ar,base_price,category_id,color_family,material,care_instructions,status}=value;
      const fields={title,title_ar,description,description_ar,base_price,category_id,color_family,material,care_instructions,status};
      const changes=Object.fromEntries(Object.entries(fields).filter(([k,v])=>v!==original.current?.[k as keyof Editable]));
      if(Object.keys(changes).length)await request(`/partner/catalog/products/${productId}`,{method:'PATCH',body:JSON.stringify(changes)});
      onSaved();onClose();
    } catch {setError(true);} finally {setBusy(false);}
  };
  const upload=async(file:File)=>{
    setBusy(true);setError(false);
    try {const form=new FormData();form.append('file',file);const asset=await request<{url:string}>(`/partner/catalog/products/${productId}/image`,{method:'POST',body:form});setValue(v=>v?{...v,thumbnail_url:asset.url}:v);}
    catch {setError(true);} finally {setBusy(false);}
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3"><div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="partner-product-title" className="max-h-[90vh] overflow-y-auto w-full max-w-2xl bg-white text-slate-900 rounded-2xl p-5 space-y-4">
    <h2 id="partner-product-title" className="text-xl font-bold">{t('partnerOps.editProduct')}</h2>
    {error&&<p role="alert">{t('partnerOps.failed')}</p>}
    {value&&<form onSubmit={save} className="grid gap-3 sm:grid-cols-2">
      {(['title','title_ar','description','description_ar','color_family','material','care_instructions'] as const).map(key=><label key={key}>{t(`partnerOps.fields.${key}`)}<input className="block border rounded p-2 w-full" required={!['material','care_instructions'].includes(key)} maxLength={key.startsWith('description')?2000:key==='care_instructions'?500:key==='color_family'?50:255} dir={key.endsWith('_ar')?'rtl':undefined} value={value[key]||''} onChange={e=>setValue({...value,[key]:e.target.value})} /></label>)}
      <label>{t('partnerOps.price')}<input className="block border rounded p-2 w-full" type="number" min="0.01" max="100000" step="0.01" required value={value.base_price} onChange={e=>setValue({...value,base_price:Number(e.target.value)})}/></label>
      <label>{t('partnerOps.category')}<input className="block border rounded p-2 w-full" type="number" min="1" step="1" required value={value.category_id} onChange={e=>setValue({...value,category_id:Number(e.target.value)})}/></label>
      <label>{t('partnerOps.status')}<select className="block border rounded p-2" value={value.status} onChange={e=>setValue({...value,status:e.target.value})}>{['draft','active','archived'].map(s=><option key={s} value={s}>{t(`partnerOps.states.${s}`)}</option>)}</select></label>
      <p>{t('partnerOps.archiveHelp')}</p>
      <button className="rounded bg-slate-900 text-white p-2" disabled={busy}>{t('partnerOps.save')}</button>
    </form>}
    {value&&<label className="block">{t('partnerOps.image')}<input disabled={busy} type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);}}/></label>}
    <button disabled={busy} onClick={close}>{t('partnerOps.close')}</button>
  </div></div>;
}
