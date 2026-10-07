import React, { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react';

import { authService } from '../../services/apiServices';
import { localizeApiError } from '../../i18n/apiErrors';
import {
  StatusIcon,
  usePrefersReducedMotion,
} from '../../components/common/InteractionPrimitives';
import { AuthPageShell } from '../../components/auth/AuthPageShell';
import {
  PasswordPolicyChecklist,
  passwordPolicyChecks,
} from '../../components/auth/PasswordPolicyChecklist';
import {
  AUTH_FIELD_CLASS,
  AUTH_PRIMARY_BTN_CLASS,
} from '../../components/auth/authStyles';
import { useCapsLock, CapsLockHint } from '../../components/auth/CapsLockHint';

/**
 * The page the password-reset EMAIL lands on.
 *
 * WHY THIS EXISTS (audit 2026-10-06): the backend has mailed
 * `FRONTEND_BASE_URL/reset-password?token=…` since cycle 4, but no route
 * ever existed — the catch-all silently bounced the shopper to the home
 * page and the reset loop was BROKEN in production. This closes it.
 *
 * Contract:
 *  · PUBLIC — the one-time token from the email is the only credential.
 *  · The policy checklist mirrors the server's real rule (8–72 chars,
 *    ≥3 of lowercase/uppercase/digit/symbol) so the first submit is the
 *    one that succeeds; the server remains the authority.
 *  · Success only after the server confirms; it revokes every session,
 *    so the CTA sends the shopper to sign in (deep link `?auth=signin`).
 *  · Invalid / used / expired tokens show the server's honest verdict
 *    with a working path to request a fresh link (`?auth=forgot`).
 */

type Phase = 'form' | 'submitting' | 'done' | 'error';

export const ResetPasswordView: React.FC = () => {
  const { t } = useTranslation();
  const reduce = usePrefersReducedMotion();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [phase, setPhase] = useState<Phase>('form');
  const [serverError, setServerError] = useState<string | null>(null);
  const { capsLockOn, capsLockProps } = useCapsLock();

  const checks = useMemo(
    () => ({
      ...passwordPolicyChecks(password),
      match: password.length > 0 && password === confirm,
    }),
    [password, confirm],
  );
  const ready = checks.length && checks.categories && checks.match;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ready || phase === 'submitting') return;
    setPhase('submitting');
    setServerError(null);
    try {
      await authService.resetPassword(token, password);
      setPhase('done');
    } catch (err) {
      // Invalid / used / expired token, policy rejection, or transport —
      // the server's verdict, localized; never a fake success.
      setServerError(localizeApiError(err, t, 'errors.generic'));
      setPhase('error');
    }
  };

  // ---- token missing: honest dead end with a working way forward ----------
  if (!token) {
    return (
      <AuthPageShell>
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#FDF8EE]">
          <StatusIcon status="error" size={22} />
        </div>
        <div role="status" aria-live="polite">
          <h1 className="font-serif text-xl font-bold text-[#1B1F3B]">
            {t('reset_password.no_token_title')}
          </h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-slate-600">
            {t('reset_password.no_token_detail')}
          </p>
        </div>
        <Link
          to="/?auth=forgot"
          className={`${AUTH_PRIMARY_BTN_CLASS} mt-6`}
        >
          {t('reset_password.request_new_link')}
        </Link>
      </AuthPageShell>
    );
  }

  // ---- success: sessions are revoked server-side; route to sign-in --------
  if (phase === 'done') {
    return (
      <AuthPageShell>
        <motion.div
          initial={reduce ? false : { scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: reduce ? 0 : 0.35, ease: 'easeOut' }}
          className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50"
        >
          <StatusIcon status="success" size={24} />
        </motion.div>
        <div role="status" aria-live="polite">
          <h1 className="font-serif text-xl font-bold text-[#1B1F3B]">
            {t('reset_password.done_title')}
          </h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-slate-600">
            {t('reset_password.done_detail')}
          </p>
        </div>
        <Link
          to="/?auth=signin"
          className={`${AUTH_PRIMARY_BTN_CLASS} mt-6`}
        >
          {t('reset_password.signin_cta')}
        </Link>
      </AuthPageShell>
    );
  }

  // ---- the form ------------------------------------------------------------
  return (
    <AuthPageShell>
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#FDF8EE] text-[#A37E44]">
        <span aria-hidden="true"><KeyRound size={22} /></span>
      </div>
      <h1 className="font-serif text-xl font-bold text-[#1B1F3B]">
        {t('reset_password.title')}
      </h1>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-slate-600">
        {t('reset_password.subtitle')}
      </p>

      <form onSubmit={submit} className="mt-6 text-start" noValidate>
        <label htmlFor="rp-new" className="block text-xs font-bold text-slate-700">
          {t('reset_password.new_password_label')}
        </label>
        <div className="relative mt-1">
          <input
            id="rp-new"
            type={show ? 'text' : 'password'}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`${AUTH_FIELD_CLASS} pe-11`}
            {...capsLockProps}
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-label={show ? t('reset_password.hide_password') : t('reset_password.show_password')}
            aria-pressed={show}
            className="absolute end-0.5 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 hover:text-[#1B1F3B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            <span aria-hidden="true">{show ? <EyeOff size={16} /> : <Eye size={16} />}</span>
          </button>
        </div>
        <CapsLockHint on={capsLockOn} />

        <label htmlFor="rp-confirm" className="mt-4 block text-xs font-bold text-slate-700">
          {t('reset_password.confirm_label')}
        </label>
        <input
          id="rp-confirm"
          type={show ? 'text' : 'password'}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className={`${AUTH_FIELD_CLASS} mt-1`}
        />

        {/* Live mirror of the SERVER's real policy — shared with the
            register form (PasswordPolicyChecklist), no invented rules. */}
        <PasswordPolicyChecklist password={password} confirm={confirm} className="mt-4" />

        <div role="status" aria-live="polite" className="mt-3 min-h-5">
          {phase === 'error' && serverError && (
            <p className="text-xs font-bold text-rose-600">{serverError}</p>
          )}
          {phase === 'submitting' && (
            <p className="flex items-center gap-2 text-xs text-slate-500">
              <StatusIcon status="loading" size={14} className="text-[#A37E44]" />
              {t('reset_password.working')}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={!ready}
          aria-busy={phase === 'submitting'}
          className={`${AUTH_PRIMARY_BTN_CLASS} mt-3`}
        >
          <span aria-hidden="true"><ShieldCheck size={16} /></span>
          {t('reset_password.submit_cta')}
        </button>

        {phase === 'error' && (
          <p className="mt-4 text-center text-xs text-slate-500">
            {t('reset_password.expired_hint')}{' '}
            <Link
              to="/?auth=forgot"
              className="font-bold text-[#A37E44] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] rounded"
            >
              {t('reset_password.request_new_link')}
            </Link>
          </p>
        )}
      </form>
    </AuthPageShell>
  );
};

