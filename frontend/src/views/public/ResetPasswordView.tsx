import React, { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Check, Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react';

import { authService } from '../../services/apiServices';
import { localizeApiError } from '../../i18n/apiErrors';
import {
  StatusIcon,
  usePrefersReducedMotion,
} from '../../components/common/InteractionPrimitives';
import { ConfitLogo } from '../../components/common/ConfitLogo';

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

const POLICY = {
  length: (v: string) => v.length >= 8 && v.length <= 72,
  categories: (v: string) =>
    [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter((r) => r.test(v)).length >= 3,
};

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

  const checks = useMemo(
    () => ({
      length: POLICY.length(password),
      categories: POLICY.categories(password),
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

  const checklistRow = (ok: boolean, label: string) => (
    <li className="flex items-center gap-2 text-xs">
      <span
        aria-hidden="true"
        className={`flex h-4 w-4 items-center justify-center rounded-full transition-colors duration-200 ${
          ok ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-transparent'
        }`}
      >
        <Check size={10} strokeWidth={3} />
      </span>
      <span className={ok ? 'text-emerald-700' : 'text-slate-500'}>
        {label}
        <span className="sr-only">
          {ok ? ` — ${t('reset_password.rule_met')}` : ` — ${t('reset_password.rule_unmet')}`}
        </span>
      </span>
    </li>
  );

  // ---- token missing: honest dead end with a working way forward ----------
  if (!token) {
    return (
      <Shell reduce={reduce}>
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
          className="mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
        >
          {t('reset_password.request_new_link')}
        </Link>
      </Shell>
    );
  }

  // ---- success: sessions are revoked server-side; route to sign-in --------
  if (phase === 'done') {
    return (
      <Shell reduce={reduce}>
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
          className="mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
        >
          {t('reset_password.signin_cta')}
        </Link>
      </Shell>
    );
  }

  // ---- the form ------------------------------------------------------------
  return (
    <Shell reduce={reduce}>
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
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 pe-11 text-sm text-[#1B1F3B] focus:border-[#A37E44] focus:outline-none focus:ring-2 focus:ring-[#C5A059]/40"
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-label={show ? t('reset_password.hide_password') : t('reset_password.show_password')}
            aria-pressed={show}
            className="absolute end-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 hover:text-[#1B1F3B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            <span aria-hidden="true">{show ? <EyeOff size={16} /> : <Eye size={16} />}</span>
          </button>
        </div>

        <label htmlFor="rp-confirm" className="mt-4 block text-xs font-bold text-slate-700">
          {t('reset_password.confirm_label')}
        </label>
        <input
          id="rp-confirm"
          type={show ? 'text' : 'password'}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-[#1B1F3B] focus:border-[#A37E44] focus:outline-none focus:ring-2 focus:ring-[#C5A059]/40"
        />

        {/* Live mirror of the SERVER's real policy — no invented rules. */}
        <ul className="mt-4 space-y-1.5" aria-label={t('reset_password.rules_title')}>
          {checklistRow(checks.length, t('reset_password.rule_length'))}
          {checklistRow(checks.categories, t('reset_password.rule_categories'))}
          {checklistRow(checks.match, t('reset_password.rule_match'))}
        </ul>

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
          className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white transition-opacity hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] disabled:cursor-not-allowed disabled:opacity-40"
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
    </Shell>
  );
};

/** Shared card shell — one entrance tween, disabled under reduced motion. */
const Shell: React.FC<{ reduce: boolean; children: React.ReactNode }> = ({
  reduce,
  children,
}) => (
  <main className="min-h-screen bg-[#FAF9F6] px-4 py-14">
    <motion.section
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0 : 0.3, ease: 'easeOut' }}
      className="mx-auto w-full max-w-md rounded-3xl border border-slate-200/80 bg-white p-8 text-center shadow-sm"
    >
      <div className="mx-auto mb-5 flex justify-center">
        <ConfitLogo variant="compact" theme="dark" size="sm" />
      </div>
      {children}
    </motion.section>
  </main>
);
