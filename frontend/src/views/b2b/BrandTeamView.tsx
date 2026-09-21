import React, { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { request } from '../../services/apiClient';
import { useAuthStore } from '../../stores/authStore';
import { useNavigate } from 'react-router-dom';

type Page<T> = { items: T[]; next_cursor: number | null };
type Member = { id: number; email: string; role: string };
type Invite = Member & { status: string };
const roles = ['owner', 'manager', 'staff', 'analyst', 'catalog_editor'];

export const BrandTeamView: React.FC = () => {
  const { t } = useTranslation();
  const [members, setMembers] = useState<Page<Member>>({items:[],next_cursor:null});
  const [invites, setInvites] = useState<Page<Invite>>({items:[],next_cursor:null});
  const [after, setAfter] = useState(0);
  const [inviteAfter, setInviteAfter] = useState(0);
  const [owner, setOwner] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('staff');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let live = true;
    setError(false);
    Promise.all([request<{membership_role:string}>('/partner/profile'), request<Page<Member>>(`/partner/team/members?after=${after}`)])
      .then(async ([profile, page]) => {
        const isOwner = profile.membership_role === 'owner';
        if (live) { setMembers(page); setOwner(isOwner); }
        if (isOwner) {
          const invites = await request<Page<Invite>>(`/partner/team/invitations?after=${inviteAfter}`);
          if (live) setInvites(invites);
        }
      }).catch(() => { if (live) setError(true); });
    return () => { live = false; };
  }, [after, inviteAfter, version]);
  const mutate = async (path: string, method: string, body?: object) => {
    if (busy) return;
    setBusy(true); setError(false); setSecret('');
    try {
      const result = await request<{token?:string}>(path, {method, body:body ? JSON.stringify(body) : undefined});
      if (result.token) setSecret(result.token);
      setVersion(v=>v+1);
    } catch { setError(true); } finally { setBusy(false); }
  };
  return <section className="space-y-6">
    <h1 className="text-3xl font-bold">{t('partnerOps.team')}</h1>
    <p>{t('partnerOps.teamPolicy')}</p>
    {error && <p role="alert">{t('partnerOps.failed')} <button onClick={()=>setVersion(v=>v+1)}>{t('partnerOps.retry')}</button></p>}
    {owner && <form className="flex flex-wrap gap-3 rounded-xl border p-4" onSubmit={e=>{e.preventDefault();void mutate('/partner/team/invitations','POST',{email,role});}}>
      <label>{t('partnerOps.email')}<input className="block border rounded p-2" type="email" required value={email} onChange={e=>setEmail(e.target.value)} /></label>
      <label>{t('partnerOps.role')}<select className="block border rounded p-2" value={role} onChange={e=>setRole(e.target.value)}>{roles.map(r=><option key={r} value={r}>{t(`partnerOps.roles.${r}`)}</option>)}</select></label>
      <button className="border rounded p-2" disabled={busy}>{t('partnerOps.invite')}</button>
    </form>}
    {secret && <div className="rounded-xl border p-4 space-y-3"><p>{t('partnerOps.manualShare')}</p><code dir="ltr" className="block break-all">{secret}</code><button onClick={()=>setSecret('')}>{t('partnerOps.hide')}</button></div>}
    <div className="overflow-x-auto"><table className="w-full text-start"><thead><tr><th>{t('partnerOps.email')}</th><th>{t('partnerOps.role')}</th><th>{t('partnerOps.actions')}</th></tr></thead><tbody>
      {members.items.map(member=><tr key={member.id}><td className="p-2" dir="ltr">{member.email}</td><td>{t(`partnerOps.roles.${member.role}`)}</td><td className="flex flex-wrap gap-2 p-2">{owner && <>
        <select aria-label={t('partnerOps.changeRole',{email:member.email})} disabled={busy} value={member.role} onChange={e=>void mutate(`/partner/team/members/${member.id}`,'PATCH',{role:e.target.value})}>{roles.map(r=><option key={r} value={r}>{t(`partnerOps.roles.${r}`)}</option>)}</select>
        <button disabled={busy} onClick={()=>{if(window.confirm(t('partnerOps.confirmRemove')))void mutate(`/partner/team/members/${member.id}`,'DELETE');}}>{t('partnerOps.remove')}</button>
      </>}</td></tr>)}
    </tbody></table></div>
    <div className="flex gap-4"><button onClick={()=>setAfter(0)} disabled={!after}>{t('partnerOps.first')}</button><button disabled={!members.next_cursor} onClick={()=>setAfter(members.next_cursor!)}>{t('partnerOps.next')}</button></div>
    {owner && <><h2 className="text-xl font-bold">{t('partnerOps.invitations')}</h2><ul className="space-y-2">{invites.items.map(i=><li key={i.id} className="flex flex-wrap gap-3"><span dir="ltr">{i.email}</span><span>{t(`partnerOps.states.${i.status}`)}</span>{i.status==='pending' && <button disabled={busy} onClick={()=>void mutate(`/partner/team/invitations/${i.id}`,'DELETE')}>{t('partnerOps.revoke')}</button>}</li>)}</ul><button onClick={()=>setInviteAfter(0)}>{t('partnerOps.first')}</button><button disabled={!invites.next_cursor} onClick={()=>setInviteAfter(invites.next_cursor!)}>{t('partnerOps.next')}</button></>}
  </section>;
};

export const AcceptBrandInvitation: React.FC = () => {
  const { t } = useTranslation(); const navigate = useNavigate();
  const fetchMe = useAuthStore(s=>s.fetchMe);
  const [token,setToken]=useState(''); const [busy,setBusy]=useState(false); const [error,setError]=useState(false);
  const accept=useCallback(async (e:React.FormEvent)=>{
    e.preventDefault();setBusy(true);setError(false);
    try { await request('/partner/team/accept',{method:'POST',body:JSON.stringify({token})});setToken('');await fetchMe();navigate('/b2b'); }
    catch { setError(true); } finally { setBusy(false); }
  },[token,fetchMe,navigate]);
  return <main className="mx-auto max-w-xl p-6 space-y-4"><h1 className="text-2xl font-bold">{t('partnerOps.accept')}</h1><p>{t('partnerOps.acceptHelp')}</p><form onSubmit={accept} className="space-y-4"><label>{t('partnerOps.invitationCode')}<input type="password" autoComplete="off" required minLength={32} maxLength={128} value={token} onChange={e=>setToken(e.target.value)} className="block w-full border rounded p-2" /></label><button disabled={busy}>{t('partnerOps.accept')}</button></form>{error && <p role="alert">{t('partnerOps.failed')}</p>}</main>;
};

export const BrandAuditView: React.FC = () => {
  const { t, i18n } = useTranslation();
  const [page,setPage]=useState<Page<{id:number;timestamp:string;action:string;entity:string;entity_id:string;request_id:string}>>({items:[],next_cursor:null});
  const [after,setAfter]=useState(0); const [error,setError]=useState(false); const [version,setVersion]=useState(0);
  useEffect(()=>{let live=true;setError(false);request<typeof page>(`/partner/audit?after=${after}`).then(p=>{if(live)setPage(p);}).catch(()=>{if(live)setError(true);});return()=>{live=false;};},[after,version]);
  return <section className="space-y-4"><h1 className="text-3xl font-bold">{t('partnerOps.audit')}</h1><p>{t('partnerOps.auditHelp')}</p>{error && <p role="alert">{t('partnerOps.failed')}<button onClick={()=>setVersion(v=>v+1)}>{t('partnerOps.retry')}</button></p>}<div className="overflow-x-auto"><table className="w-full text-start"><thead><tr><th>{t('partnerOps.time')}</th><th>{t('partnerOps.action')}</th><th>{t('partnerOps.entity')}</th><th>{t('partnerOps.request')}</th></tr></thead><tbody>{page.items.map(e=><tr key={e.id}><td>{new Date(e.timestamp).toLocaleString(i18n.language)}</td><td><code>{e.action}</code></td><td>{e.entity} #{e.entity_id}</td><td><code>{e.request_id}</code></td></tr>)}</tbody></table></div>{!page.items.length&&!error&&<p>{t('partnerOps.empty')}</p>}<button disabled={!after} onClick={()=>setAfter(0)}>{t('partnerOps.first')}</button><button disabled={!page.next_cursor} onClick={()=>setAfter(page.next_cursor!)}>{t('partnerOps.next')}</button></section>;
};
