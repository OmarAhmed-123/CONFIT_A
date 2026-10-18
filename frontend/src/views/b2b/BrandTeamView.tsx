import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../stores/authStore';
import {
  membersService,
  type BrandTeamMember,
  type BrandTeamInvitation,
} from '../../services/apiServices';
import { ApiError } from '../../services/apiClient';
import { ConfitLogo } from '../../components/common/ConfitLogo';

/**
 * BrandTeamView — tenant team management (BRD-02 · spec 005 · #150 residue).
 *
 * Every control mirrors a SERVER-enforced capability (the capability matrix in
 * models/membership.py is the truth; this file only shapes what owners,
 * managers and staff can see). The last-owner guard is deliberately NOT
 * re-implemented client-side beyond a disable hint: the API's 409
 * LAST_ACTIVE_OWNER is the authority and its message surfaces verbatim-translated.
 */

type Role = 'owner' | 'manager' | 'staff';

const ROLES: Role[] = ['owner', 'manager', 'staff'];

const roleLabelKey: Record<Role, string> = {
  owner: 'brand_team.role_owner',
  manager: 'brand_team.role_manager',
  staff: 'brand_team.role_staff',
};

const card = 'bg-white border border-slate-200/80 rounded-3xl shadow-2xs';
const input =
  'w-full rounded-xl border border-brand-field bg-white px-3.5 py-2.5 text-sm text-brand-charcoal '
  + 'placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal';
const btnPrimary =
  'inline-flex items-center justify-center gap-2 min-h-11 px-5 rounded-xl bg-brand-charcoal text-white '
  + 'text-xs font-bold tracking-wider uppercase shadow-xs transition-all '
  + 'hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2';
const btnGhost =
  'inline-flex items-center justify-center gap-2 min-h-11 px-4 rounded-xl border border-brand-field '
  + 'bg-white text-brand-charcoal text-xs font-semibold transition-all hover:bg-brand-wash '
  + 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2';
const btnDanger =
  'inline-flex items-center justify-center gap-2 min-h-11 px-4 rounded-xl border border-rose-200 '
  + 'bg-white text-rose-700 text-xs font-semibold transition-all hover:bg-rose-50 '
  + 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-2';

function errCode(err: unknown): string | null {
  return err instanceof ApiError ? err.code ?? null : null;
}

const BrandTeamView: React.FC = () => {
  const { t } = useTranslation();
  const { user, brandMemberships, loadBrandMemberships } = useAuthStore();

  const role: Role | null = useMemo(() => {
    const m = brandMemberships?.[0]?.role;
    if (m) return m;
    const legacy = ({ brand_owner: 'owner', brand_manager: 'manager', brand_staff: 'staff' } as const);
    const r = (user?.role || '') as keyof typeof legacy;
    return legacy[r] ?? null;
  }, [brandMemberships, user]);
  const isOwner = role === 'owner';

  const [members, setMembers] = useState<BrandTeamMember[] | null>(null);
  const [invitations, setInvitations] = useState<BrandTeamInvitation[] | null>(null);
  const [membersError, setMembersError] = useState(false);
  const [invitationsError, setInvitationsError] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'ok' | 'warn'; text: string } | null>(null);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Role>('manager');
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const inviteRef = useRef<HTMLDivElement | null>(null);
  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  const [confirmRemove, setConfirmRemove] = useState<BrandTeamMember | null>(null);
  const [removeBusy, setRemoveBusy] = useState<number | null>(null);
  const [roleBusy, setRoleBusy] = useState<number | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setMembersError(false);
    setInvitationsError(false);
    const [m, i] = await Promise.allSettled([
      membersService.listMembers(),
      role === 'staff' ? Promise.resolve([] as BrandTeamInvitation[]) : membersService.listInvitations(),
    ]);
    if (m.status === 'fulfilled') setMembers(m.value); else { setMembers(null); setMembersError(true); }
    if (i.status === 'fulfilled') setInvitations(i.value); else { setInvitations(null); setInvitationsError(true); }
  }, [role]);

  useEffect(() => {
    if (brandMemberships === null) void loadBrandMemberships();
    void load();
  }, [load, brandMemberships, loadBrandMemberships]);

  // Invite dialog a11y: focus on open, Tab-cycle within, Escape closes.
  useEffect(() => {
    if (!inviteOpen) return;
    firstFieldRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setInviteOpen(false); return; }
      if (e.key !== 'Tab' || !inviteRef.current) return;
      const nodes = inviteRef.current.querySelectorAll<HTMLElement>(
        'button, input, select, [href], [tabindex]:not([tabindex="-1"])',
      );
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [inviteOpen]);

  const submitInvite = async () => {
    setInviteBusy(true);
    setInviteError(null);
    try {
      const res = await membersService.invite({ email: inviteEmail.trim(), role: inviteRole });
      const created = Boolean(res?.id);
      setInviteOpen(false);
      setInviteEmail('');
      setNotice({ tone: 'ok', text: created ? t('brand_team.invite_queued') : t('brand_team.invite_reused') });
      await load();
    } catch (err) {
      const code = errCode(err);
      const known = code && ['MULTI_BRAND_NOT_SUPPORTED', 'ALREADY_MEMBER', 'EMAIL_SEND_UNAVAILABLE']
        .includes(code) ? code : null;
      setInviteError(known
        ? t(`brand_team.err.${known}`)
        : t('brand_team.invite_failed', { defaultValue: t('brand_team.action_failed') }));
    } finally {
      setInviteBusy(false);
    }
  };

  const doResend = async (id: number) => {
    try {
      await membersService.resendInvitation(id);
      setNotice({ tone: 'ok', text: t('brand_team.invite_re_sent') });
    } catch {
      setNotice({ tone: 'warn', text: t('brand_team.action_failed') });
    }
  };

  const doRevokeInvite = async (id: number) => {
    try {
      await membersService.revokeInvitation(id);
      setNotice({ tone: 'ok', text: t('brand_team.invite_revoked') });
      await load();
    } catch {
      setNotice({ tone: 'warn', text: t('brand_team.action_failed') });
    }
  };

  const doChangeRole = async (m: BrandTeamMember, next: Role) => {
    setRoleBusy(m.id);
    setRowError(null);
    try {
      await membersService.changeRole(m.id, next);
      await load();
    } catch (err) {
      setRowError(errCode(err) === 'LAST_ACTIVE_OWNER'
        ? t('brand_team.err.LAST_ACTIVE_OWNER')
        : t('brand_team.action_failed'));
    } finally {
      setRoleBusy(null);
    }
  };

  const doRemove = async (m: BrandTeamMember) => {
    setRemoveBusy(m.id);
    setRowError(null);
    try {
      await membersService.removeMember(m.id);
      setNotice({ tone: 'ok', text: t('brand_team.member_removed') });
      setConfirmRemove(null);
      await load();
    } catch (err) {
      setRowError(errCode(err) === 'LAST_ACTIVE_OWNER'
        ? t('brand_team.err.LAST_ACTIVE_OWNER')
        : t('brand_team.action_failed'));
    } finally {
      setRemoveBusy(null);
    }
  };

  const fmtDate = (iso: string) => {
    try { return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); }
    catch { return iso; }
  };

  const activeMembers = (members ?? []).filter((m) => m.status === 'active');
  const ownerCount = activeMembers.filter((m) => m.role === 'owner').length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 space-y-8">
      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <ConfitLogo variant="compact" size="sm" />
          <span className="text-[10px] font-bold tracking-widest text-brand-muted uppercase">
            {t('brand_team.eyebrow')}
          </span>
        </div>
        <h1 className="font-serif text-3xl sm:text-4xl font-bold text-brand-charcoal">
          {t('brand_team.title')}
        </h1>
        <p className="text-sm text-brand-muted font-light max-w-2xl">
          {t('brand_team.subtitle')}
          {role ? (
            <span className="ms-2 inline-flex items-center rounded-full bg-brand-wash border border-brand-hairline px-2.5 py-0.5 text-[11px] font-semibold text-brand-charcoal align-middle">
              {t(roleLabelKey[role])}
            </span>
          ) : null}
        </p>
      </header>

      {notice ? (
        <div role="status" aria-live="polite"
          className={`rounded-2xl border px-4 py-3 text-sm ${notice.tone === 'ok' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-amber-50 border-amber-200 text-amber-800'}`}
        >{notice.text}</div>
      ) : null}

      {/* ── Members ─────────────────────────────────────────────────────── */}
      <section className={`${card} p-6 space-y-4`} aria-labelledby="team-members-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="team-members-heading" className="font-serif text-xl font-bold text-brand-charcoal">
            {t('brand_team.members_heading')}
            {members ? <span className="ms-2 text-xs font-sans font-semibold text-brand-muted">({activeMembers.length})</span> : null}
          </h2>
          {isOwner ? (
            <button type="button" data-motion="send" className={btnPrimary}
              onClick={() => { setInviteError(null); setInviteOpen(true); }}>
              {t('brand_team.invite_button')}
            </button>
          ) : (
            <span className="text-[11px] text-brand-muted">
              {role === 'staff' ? t('brand_team.readonly_staff') : t('brand_team.readonly_manager')}
            </span>
          )}
        </div>

        {membersError ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-6 text-center space-y-3">
            <p className="text-sm text-rose-800">{t('brand_team.members_load_failed')}</p>
            <button type="button" data-motion="recovery" className={btnGhost} onClick={() => void load()}>
              {t('common.retry', { defaultValue: 'Retry' })}
            </button>
          </div>
        ) : members === null ? (
          <div className="space-y-2" aria-hidden="true">
            {[0, 1, 2].map((i) => <div key={i} className="h-12 rounded-xl bg-slate-100 animate-pulse" />)}
          </div>
        ) : activeMembers.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-brand-muted">
            {t('brand_team.members_empty')}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {activeMembers.map((m) => (
              <li key={m.id} className="py-3.5 flex flex-wrap items-center gap-3">
                <div className="min-w-[180px] flex-1">
                  <p className="text-sm font-semibold text-brand-charcoal">
                    {m.full_name}
                    {user && m.user_id === user.id
                      ? <span className="ms-2 text-[10px] uppercase tracking-wider rounded-full bg-brand-wash border border-brand-hairline px-2 py-0.5">{t('brand_team.you')}</span>
                      : null}
                  </p>
                  <p className="text-xs text-brand-muted">
                    {m.email ?? t('brand_team.email_hidden')} · {t('brand_team.joined', { date: fmtDate(m.created_at) })}
                  </p>
                </div>
                {isOwner ? (
                  <div className="flex items-center gap-2">
                    <label className="sr-only" htmlFor={`role-${m.id}`}>{t('brand_team.role_label', { name: m.full_name })}</label>
                    <select id={`role-${m.id}`}
                      aria-label={t('brand_team.role_label', { name: m.full_name })}
                      className="h-11 rounded-xl border border-brand-field bg-white px-3 text-xs font-semibold text-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                      value={m.role}
                      disabled={roleBusy === m.id}
                      onChange={(e) => void doChangeRole(m, e.target.value as Role)}>
                      {ROLES.map((r) => <option key={r} value={r}>{t(roleLabelKey[r])}</option>)}
                    </select>
                    <button type="button" data-motion="admin" className={btnDanger}
                      disabled={removeBusy === m.id}
                      title={ownerCount <= 1 && m.role === 'owner' ? t('brand_team.err.LAST_ACTIVE_OWNER') : undefined}
                      onClick={() => { setRowError(null); setConfirmRemove(m); }}>
                      {t('brand_team.remove_button')}
                    </button>
                  </div>
                ) : (
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted">{t(roleLabelKey[m.role])}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {rowError ? <p role="alert" className="text-xs text-rose-700">{rowError}</p> : null}
        {members && members.some((m) => m.status === 'revoked') ? (
          <p className="text-[11px] text-brand-muted">{t('brand_team.revoked_note', { count: members.filter((m) => m.status === 'revoked').length })}</p>
        ) : null}
      </section>

      {/* ── Pending invitations (owner + manager visibility) ─────────────── */}
      {role !== 'staff' ? (
        <section className={`${card} p-6 space-y-4`} aria-labelledby="team-invites-heading">
          <h2 id="team-invites-heading" className="font-serif text-xl font-bold text-brand-charcoal">
            {t('brand_team.invitations_heading')}
            {invitations ? <span className="ms-2 text-xs font-sans font-semibold text-brand-muted">({invitations.length})</span> : null}
          </h2>
          {invitationsError ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-6 text-center space-y-3">
              <p className="text-sm text-rose-800">{t('brand_team.invitations_load_failed')}</p>
              <button type="button" data-motion="recovery" className={btnGhost} onClick={() => void load()}>
                {t('common.retry', { defaultValue: 'Retry' })}
              </button>
            </div>
          ) : invitations === null ? (
            <div className="space-y-2" aria-hidden="true"><div className="h-12 rounded-xl bg-slate-100 animate-pulse" /></div>
          ) : invitations.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-brand-muted">
              {t('brand_team.invitations_empty')}
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {invitations.map((inv) => (
                <li key={inv.id} className="py-3.5 flex flex-wrap items-center gap-3">
                  <div className="min-w-[200px] flex-1">
                    <p className="text-sm font-semibold text-brand-charcoal">{inv.email}</p>
                    <p className="text-xs text-brand-muted">
                      {t(roleLabelKey[inv.role])} · {t('brand_team.expires', { date: fmtDate(inv.expires_at) })}
                    </p>
                  </div>
                  {isOwner ? (
                    <div className="flex items-center gap-2">
                      <button type="button" data-motion="send" className={btnGhost} onClick={() => void doResend(inv.id)}>
                        {t('brand_team.resend_button')}
                      </button>
                      <button type="button" data-motion="admin" className={btnDanger} onClick={() => void doRevokeInvite(inv.id)}>
                        {t('brand_team.revoke_button')}
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {/* ── Invite dialog ────────────────────────────────────────────────── */}
      {inviteOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md confit-fade-in"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setInviteOpen(false); }}>
          <div ref={inviteRef} role="dialog" aria-modal="true" aria-labelledby="invite-dialog-title"
            className="w-full max-w-md bg-white rounded-3xl shadow-2xl border border-slate-200/80 p-6 space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="invite-dialog-title" className="font-serif text-lg font-bold text-brand-charcoal">{t('brand_team.invite_title')}</h3>
                <p className="text-xs text-brand-muted mt-1 font-light">{t('brand_team.invite_intro')}</p>
              </div>
              <button data-motion-tone="icon" type="button" data-motion="neutral" onClick={() => setInviteOpen(false)}
                aria-label={t('a11y.close_dialog')}
                className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-800 hover:bg-slate-200/70 transition-colors">✕</button>
            </div>
            <div className="space-y-3">
              <label className="block text-xs font-semibold text-brand-charcoal" htmlFor="invite-email">
                {t('brand_team.invite_email_label')}
              </label>
              <input id="invite-email" ref={firstFieldRef} type="email" autoComplete="email" className={input}
                value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="name@company.com" />
              <label className="block text-xs font-semibold text-brand-charcoal pt-1" htmlFor="invite-role">
                {t('brand_team.invite_role_label')}
              </label>
              <select id="invite-role" className={input} value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as Role)}>
                {ROLES.map((r) => <option key={r} value={r}>{t(roleLabelKey[r])}</option>)}
              </select>
              <p className="text-[11px] text-brand-muted font-light leading-relaxed">{t(`brand_team.role_hint_${inviteRole}`)}</p>
            </div>
            {inviteError ? <p role="alert" className="text-xs text-rose-700">{inviteError}</p> : null}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" data-motion="neutral" className={btnGhost} onClick={() => setInviteOpen(false)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </button>
              <button data-motion-tone="icon" type="button" data-motion="send" className={btnPrimary} disabled={inviteBusy || !inviteEmail.includes('@')}
                onClick={() => void submitInvite()}>
                {inviteBusy ? t('brand_team.invite_sending') : t('brand_team.invite_send')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* ── Remove confirmation ─────────────────────────────────────────── */}
      {confirmRemove ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md confit-fade-in"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmRemove(null); }}>
          <div role="alertdialog" aria-modal="true" aria-labelledby="remove-dialog-title"
            className="w-full max-w-sm bg-white rounded-3xl shadow-2xl border border-slate-200/80 p-6 space-y-4">
            <h3 id="remove-dialog-title" className="font-serif text-lg font-bold text-brand-charcoal">{t('brand_team.remove_title')}</h3>
            <p className="text-sm text-brand-muted font-light">
              {t('brand_team.remove_body', { name: confirmRemove.full_name })}
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" data-motion="neutral" className={btnGhost} onClick={() => setConfirmRemove(null)}>
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </button>
              <button data-motion-tone="icon" type="button" data-motion="admin" className={btnDanger} disabled={removeBusy === confirmRemove.id}
                onClick={() => void doRemove(confirmRemove)}>
                {removeBusy === confirmRemove.id ? t('brand_team.remove_busy') : t('brand_team.remove_confirm')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export { BrandTeamView };
export default BrandTeamView;
