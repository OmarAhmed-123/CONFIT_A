import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { authService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { ApiError } from '../../services/apiClient';
import { ShieldIcon } from '../icons/ConfitIcons';

/**
 * Account & security block for the profile page (2026-09-19).
 *
 * Shows the sign-in email with its REAL verification state, exposes the
 * two-step email change, and — where the deployment cannot send mail — says so
 * instead of promising an email that will never arrive. The delivery badge is
 * read from the server ledger for the caller's own account only.
 */
export const AccountSecurityPanel: React.FC = () => {
  const { user, fetchMe } = useAuthStore();
  const [panel, setPanel] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ tone: 'ok' | 'warn' | 'error'; text: string } | null>(null);
  const [delivery, setDelivery] = useState<{
    status: string;
    accepted: boolean;
    error_class?: string | null;
    provider_configured?: boolean;
  } | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    authService
      .getEmailStatus('email_verification')
      .then((d) => setDelivery(d))
      .catch(() => setDelivery(null));
  }, [user?.id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const res = await authService.requestEmailChange(newEmail);
      setResult({
        tone: res.delivery_status === 'succeeded' ? 'ok' : 'warn',
        text: res.message,
      });
      if (res.delivery_status === 'succeeded') setNewEmail('');
      await fetchMe();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr?.code === 'FEATURE_NOT_CONFIGURED') {
        setUnavailable(true);
        setResult({
          tone: 'error',
          text: 'Email delivery is not configured on this deployment, so no confirmation email was sent and your address was NOT changed.',
        });
      } else {
        setResult({ tone: 'error', text: apiErr?.message || 'The change could not be started.' });
      }
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;

  const color = { ok: 'text-emerald-700 bg-emerald-50 border-emerald-200', warn: 'text-amber-700 bg-amber-50 border-amber-200', error: 'text-rose-700 bg-rose-50 border-rose-200' };

  return (
    <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-xl bg-[#1B1F3B] flex items-center justify-center shrink-0">
          <ShieldIcon size={18} color="#C5A059" />
        </div>
        <div className="flex-1">
          <div className="text-xs font-bold text-slate-900">Sign-in email &amp; account state</div>
          <div className="text-[11px] text-slate-500 font-light break-all">
            {user.email}
            {' · '}
            <span className={user.is_verified ? 'text-emerald-600 font-semibold' : 'text-amber-600 font-semibold'}>
              {user.is_verified
                ? delivery?.provider_configured === false
                  ? 'verified (no email provider configured — no verification was possible here)'
                  : 'verified'
                : 'not verified yet'}
            </span>
            {user.onboarding?.account_state ? ` · ${user.onboarding.account_state}` : ''}
          </div>
        </div>
        <button
          onClick={() => { setPanel(!panel); setResult(null); }}
          className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-semibold text-slate-800 shrink-0"
        >
          {panel ? 'Cancel' : 'Change email'}
        </button>
      </div>

      {!user.is_verified && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] text-amber-800 space-y-1">
          <div className="font-semibold">Your address is not verified.</div>
          <div>
            Verification is required before partner access or privileged actions.{' '}
            <Link to="/verify-email" className="underline font-semibold">Open verification →</Link>
          </div>
          {delivery && (
            <div className="text-[10px] text-amber-700">
              Last delivery attempt: <strong>{delivery.status}</strong>
              {delivery.error_class ? ` (${delivery.error_class})` : ''}
              {delivery.accepted
                ? ' — the mail server accepted it.'
                : ' — no message was accepted, so nothing is waiting in your inbox.'}
            </div>
          )}
        </div>
      )}

      {panel && (
        <form onSubmit={submit} className="space-y-3 pt-3 border-t border-slate-100">
          <p className="text-[11px] text-slate-500">
            Step 1: we send a single-use link to the <strong>new</strong> address (valid 2 hours).
            Step 2: opening it switches the address — nothing changes before that.
          </p>
          <input
            type="email"
            required
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="new-address@example.com"
            className="w-full p-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059]"
          />
          <button
            type="submit"
            disabled={busy || unavailable}
            className="px-4 py-2.5 rounded-xl bg-[#1B1F3B] text-white text-xs font-bold disabled:opacity-50"
          >
            {busy ? 'Sending…' : 'Send confirmation link'}
          </button>
        </form>
      )}

      {result && (
        <div className={`rounded-xl border p-3 text-[11px] ${color[result.tone]}`} role={result.tone === 'error' ? 'alert' : 'status'}>
          {result.text}
        </div>
      )}
    </div>
  );
};
