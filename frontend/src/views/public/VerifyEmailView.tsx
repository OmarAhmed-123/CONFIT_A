import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { MailCheck } from 'lucide-react';

import { authService } from '../../services/apiServices';
import { localizeApiError } from '../../i18n/apiErrors';
import {
  StatusIcon,
  usePrefersReducedMotion,
} from '../../components/common/InteractionPrimitives';
import { ConfitLogo } from '../../components/common/ConfitLogo';

/**
 * The page the verification EMAIL lands on.
 *
 * WHY THIS EXISTS (audit 2026-10-06): the backend has mailed
 * `FRONTEND_BASE_URL/verify-email?token=…` since cycle 4, but no route and
 * no frontend service method ever existed — the link bounced to the home
 * page and `user.is_verified` could never flip from the product. Closed.
 *
 * Contract:
 *  · Redemption needs the explicit CTA — the POST never fires on page
 *    load, so a mail scanner that prefetches (and even executes) the page
 *    cannot burn the one-time token.
 *  · Honest verdicts: the server's invalid/used/expired wording is shown,
 *    and the recovery path (resend form) is non-committal by design — it
 *    never reveals whether an address exists.
 */

type Phase = 'ready' | 'submitting' | 'done' | 'error';
type ResendPhase = 'idle' | 'pending' | 'sent' | 'failed';

export const VerifyEmailView: React.FC = () => {
  const { t } = useTranslation();
  const reduce = usePrefersReducedMotion();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [phase, setPhase] = useState<Phase>(token ? 'ready' : 'error');
  const [serverError, setServerError] = useState<string | null>(
    token ? null : t('verify_email.no_token_detail'),
  );
  const [resendEmail, setResendEmail] = useState('');
  const [resendPhase, setResendPhase] = useState<ResendPhase>('idle');
  const [resendMessage, setResendMessage] = useState<string | null>(null);

  const confirm = async () => {
    if (phase === 'submitting') return;
    setPhase('submitting');
    try {
      await authService.verifyEmail(token);
      setPhase('done');
    } catch (err) {
      setServerError(localizeApiError(err, t, 'errors.generic'));
      setPhase('error');
    }
  };

  const resend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resendEmail.trim() || resendPhase === 'pending') return;
    setResendPhase('pending');
    setResendMessage(null);
    try {
      await authService.requestEmailVerification(resendEmail.trim());
      // Non-committal on purpose — same wording whether or not the
      // address exists. That is the server's contract, we repeat it.
      setResendPhase('sent');
    } catch (err) {
      setResendPhase('failed');
      setResendMessage(localizeApiError(err, t, 'errors.generic'));
    }
  };

  return (
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

        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#FDF8EE]">
          {phase === 'ready' && (
            <span aria-hidden="true" className="text-[#A37E44]"><MailCheck size={22} /></span>
          )}
          {phase === 'submitting' && (
            <StatusIcon status="loading" size={22} className="text-[#A37E44]" />
          )}
          {phase === 'done' && (
            <motion.span
              key="done"
              initial={reduce ? false : { scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: reduce ? 0 : 0.35, ease: 'easeOut' }}
              className="flex"
            >
              <StatusIcon status="success" size={24} />
            </motion.span>
          )}
          {phase === 'error' && <StatusIcon status="warning" size={22} />}
        </div>

        <div role="status" aria-live="polite">
          <h1 className="font-serif text-xl font-bold text-[#1B1F3B]">
            {phase === 'ready' && t('verify_email.ready_title')}
            {phase === 'submitting' && t('verify_email.working')}
            {phase === 'done' && t('verify_email.done_title')}
            {phase === 'error' && t('verify_email.error_title')}
          </h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-slate-600">
            {phase === 'ready' && t('verify_email.ready_detail')}
            {phase === 'submitting' && t('verify_email.working_detail')}
            {phase === 'done' && t('verify_email.done_detail')}
            {phase === 'error' && (serverError ?? t('verify_email.no_token_detail'))}
          </p>
        </div>

        {phase === 'ready' && (
          <button
            type="button"
            onClick={confirm}
            className="mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            {t('verify_email.confirm_cta')}
          </button>
        )}

        {phase === 'done' && (
          <Link
            to="/discover"
            className="mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            {t('verify_email.continue_cta')}
          </Link>
        )}

        {/* Recovery: expired/used link → request a fresh one. */}
        {phase === 'error' && (
          <form onSubmit={resend} className="mt-6 text-start" noValidate>
            <label htmlFor="ve-email" className="block text-xs font-bold text-slate-700">
              {t('verify_email.resend_label')}
            </label>
            <input
              id="ve-email"
              type="email"
              autoComplete="email"
              value={resendEmail}
              onChange={(e) => setResendEmail(e.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-[#1B1F3B] focus:border-[#A37E44] focus:outline-none focus:ring-2 focus:ring-[#C5A059]/40"
            />
            <div role="status" aria-live="polite" className="mt-2 min-h-5">
              {resendPhase === 'sent' && (
                <p className="text-xs font-bold text-emerald-700">
                  {t('verify_email.resend_sent')}
                </p>
              )}
              {resendPhase === 'failed' && resendMessage && (
                <p className="text-xs font-bold text-rose-600">{resendMessage}</p>
              )}
              {resendPhase === 'pending' && (
                <p className="flex items-center gap-2 text-xs text-slate-500">
                  <StatusIcon status="loading" size={14} className="text-[#A37E44]" />
                  {t('verify_email.resend_pending')}
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={!resendEmail.trim() || resendPhase === 'pending'}
              aria-busy={resendPhase === 'pending'}
              className="mt-2 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-[#1B1F3B] px-5 text-sm font-bold text-white transition-opacity hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {t('verify_email.resend_cta')}
            </button>
          </form>
        )}
      </motion.section>
    </main>
  );
};
