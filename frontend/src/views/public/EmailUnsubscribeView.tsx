import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MailX, Settings } from 'lucide-react';

import { emailService } from '../../services/apiServices';
import { StatusIcon } from '../../components/common/InteractionPrimitives';
import { AuthPageShell } from '../../components/auth/AuthPageShell';
import { AUTH_PRIMARY_BTN_CLASS } from '../../components/auth/authStyles';

/**
 * Spec 15 re-pass — the page every email footer's unsubscribe link lands on.
 *
 * Contract:
 *  · PUBLIC: the signed, expiring token in the URL is the only credential —
 *    a recipient who clicks in their inbox is never asked to sign in (§8).
 *  · GET on load only VALIDATES (the backend never mutates on GET, so a
 *    mail scanner prefetching this URL cannot unsubscribe anyone). The
 *    state change needs the explicit CTA — exactly ONE on this page (§9).
 *  · Honest states: validating / invalid / expired / ready / submitting /
 *    done / error — each spoken as TEXT in a polite live region; never a
 *    fake success before the server confirms (§5, forbidden list).
 *  · The animation layer is one local entrance tween, disabled entirely
 *    under prefers-reduced-motion.
 */

type Phase =
  | 'validating'
  | 'invalid'
  | 'expired'
  | 'ready'
  | 'submitting'
  | 'done'
  | 'error';

export const EmailUnsubscribeView: React.FC = () => {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [phase, setPhase] = useState<Phase>('validating');
  const [category, setCategory] = useState<'engagement' | 'marketing' | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setPhase('invalid');
      return;
    }
    emailService
      .validateUnsubscribeToken(token)
      .then((res) => {
        if (cancelled) return;
        if (res.valid && res.category) {
          setCategory(res.category);
          setPhase('ready');
        } else {
          setPhase(res.reason === 'expired' ? 'expired' : 'invalid');
        }
      })
      .catch(() => { if (!cancelled) setPhase('error'); });
    return () => { cancelled = true; };
  }, [token]);

  const confirm = async () => {
    setPhase('submitting');
    try {
      const res = await emailService.unsubscribe(token);
      setCategory(res.category);
      setPhase('done');
    } catch {
      // Server did not confirm — we say so; we never pretend (§11).
      setPhase('error');
    }
  };

  const categoryLabel =
    category === 'marketing'
      ? t('email_unsubscribe.category_marketing')
      : t('email_unsubscribe.category_engagement');

  const icon: Record<Phase, React.ReactNode> = {
    validating: <StatusIcon status="loading" size={22} className="text-[#A37E44]" />,
    invalid: <StatusIcon status="error" size={22} />,
    expired: <StatusIcon status="warning" size={22} />,
    ready: <span aria-hidden="true" className="text-[#A37E44]"><MailX size={22} /></span>,
    submitting: <StatusIcon status="loading" size={22} className="text-[#A37E44]" />,
    done: <StatusIcon status="success" size={22} />,
    error: <StatusIcon status="error" size={22} />,
  };

  const heading: Record<Phase, string> = {
    validating: t('email_unsubscribe.checking'),
    invalid: t('email_unsubscribe.invalid_title'),
    expired: t('email_unsubscribe.expired_title'),
    ready: t('email_unsubscribe.ready_title', { category: categoryLabel }),
    submitting: t('email_unsubscribe.working'),
    done: t('email_unsubscribe.done_title'),
    error: t('email_unsubscribe.error_title'),
  };

  const detail: Record<Phase, string> = {
    validating: t('email_unsubscribe.checking_detail'),
    invalid: t('email_unsubscribe.invalid_detail'),
    expired: t('email_unsubscribe.expired_detail'),
    ready: t('email_unsubscribe.ready_detail', { category: categoryLabel }),
    submitting: t('email_unsubscribe.working'),
    done: t('email_unsubscribe.done_detail', { category: categoryLabel }),
    error: t('email_unsubscribe.error_detail'),
  };

  return (
    <AuthPageShell>
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#FDF8EE]">
          {icon[phase]}
        </div>

        {/* The state is TEXT in a polite region — never animation-only. */}
        <div role="status" aria-live="polite">
          <h1 className="font-serif text-xl font-bold text-[#1B1F3B]">
            {heading[phase]}
          </h1>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-slate-600">
            {detail[phase]}
          </p>
        </div>

        {phase === 'ready' && (
          <button
            type="button"
            onClick={confirm}
            className={`${AUTH_PRIMARY_BTN_CLASS} mt-6`}
          >
            {t('email_unsubscribe.confirm_cta', { category: categoryLabel })}
          </button>
        )}

        {phase === 'error' && (
          <button
            type="button"
            onClick={confirm}
            className={`${AUTH_PRIMARY_BTN_CLASS} mt-6`}
          >
            {t('email_unsubscribe.retry_cta')}
          </button>
        )}

        {(phase === 'done' || phase === 'expired' || phase === 'invalid') && (
          <p className="mt-6 text-xs leading-relaxed text-slate-500">
            <span aria-hidden="true" className="me-1 inline-block align-middle text-slate-400">
              <Settings size={13} />
            </span>
            {t('email_unsubscribe.manage_hint')}{' '}
            <Link
              to="/settings"
              className="font-bold text-[#A37E44] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] rounded"
            >
              {t('email_unsubscribe.manage_link')}
            </Link>
          </p>
        )}
    </AuthPageShell>
  );
};
