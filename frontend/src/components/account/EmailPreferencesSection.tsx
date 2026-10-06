import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Lock, Mail } from 'lucide-react';

import { emailService, EmailPreferences } from '../../services/apiServices';
import { localizeApiError } from '../../i18n/apiErrors';
import {
  StatusIcon,
  usePrefersReducedMotion,
} from '../common/InteractionPrimitives';

/**
 * Email-preference switches in Settings (audit 2026-10-06).
 *
 * The /email/unsubscribe landing page has promised "manage every category
 * from account settings" since spec 15 — and nothing existed here. This
 * section keeps that promise with the REAL backend contract:
 *
 *  · GET /email/preferences on mount — lazy server defaults, never
 *    invented client-side.
 *  · Each switch PUTs only its own category and re-renders from the
 *    server's response — no optimistic flip, no fake success; while the
 *    PUT is in flight the switch is busy, not toggled.
 *  · Transactional mail is listed WITHOUT a switch, with the reason —
 *    receipts are facts about the shopper's money, not promotions.
 */
export const EmailPreferencesSection: React.FC = () => {
  const { t } = useTranslation();
  const reduce = usePrefersReducedMotion();

  const [prefs, setPrefs] = useState<EmailPreferences | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [busy, setBusy] = useState<'engagement' | 'marketing' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoadState('loading');
    emailService
      .getPreferences()
      .then((p) => { setPrefs(p); setLoadState('ready'); })
      .catch(() => setLoadState('error'));
  };
  useEffect(load, []);

  const toggle = async (category: 'engagement' | 'marketing') => {
    if (!prefs || busy) return;
    setBusy(category);
    setError(null);
    try {
      const next = await emailService.updatePreferences({
        [category]: !prefs[category],
      });
      setPrefs(next); // the server's answer, not our guess
    } catch (err) {
      setError(localizeApiError(err, t, 'errors.generic'));
    } finally {
      setBusy(null);
    }
  };

  const switchRow = (
    category: 'engagement' | 'marketing',
    title: string,
    detail: string,
  ) => {
    const on = prefs?.[category] ?? false;
    const isBusy = busy === category;
    return (
      <div className="flex items-start justify-between gap-4 pt-1">
        <div>
          <div className="text-sm font-bold text-[#1B1F3B]">{title}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{detail}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-busy={isBusy}
          aria-label={title}
          disabled={isBusy}
          onClick={() => toggle(category)}
          className={`relative mt-0.5 h-7 w-12 shrink-0 rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] disabled:cursor-wait ${
            on ? 'bg-emerald-500' : 'bg-slate-300'
          }`}
        >
          <motion.span
            aria-hidden="true"
            layout={!reduce}
            transition={reduce ? { duration: 0 } : { type: 'tween', duration: 0.18, ease: 'easeOut' }}
            className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow-sm ${
              on ? 'start-6' : 'start-1'
            }`}
          />
        </button>
      </div>
    );
  };

  return (
    <div className="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-2xs space-y-4">
      <h3 className="flex items-center gap-2 border-b border-slate-100 pb-2 font-serif text-base font-bold text-[#1B1F3B]">
        <span aria-hidden="true" className="text-[#A37E44]"><Mail size={16} /></span>
        {t('email_prefs.title')}
      </h3>

      {loadState === 'loading' && (
        <p role="status" className="flex items-center gap-2 text-xs text-slate-500">
          <StatusIcon status="loading" size={14} className="text-[#A37E44]" />
          {t('email_prefs.loading')}
        </p>
      )}

      {loadState === 'error' && (
        <div role="status" className="space-y-2">
          <p className="text-xs font-bold text-rose-600">{t('email_prefs.load_failed')}</p>
          <button
            type="button"
            onClick={load}
            className="inline-flex min-h-9 items-center rounded-xl border border-slate-300 px-4 text-xs font-bold text-[#1B1F3B] hover:border-[#A37E44] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
          >
            {t('email_prefs.retry')}
          </button>
        </div>
      )}

      {loadState === 'ready' && prefs && (
        <>
          {switchRow(
            'engagement',
            t('email_prefs.engagement_title'),
            t('email_prefs.engagement_detail'),
          )}
          {switchRow(
            'marketing',
            t('email_prefs.marketing_title'),
            t('email_prefs.marketing_detail'),
          )}

          {/* Transactional: no switch BY DESIGN — say why. */}
          <div className="flex items-start justify-between gap-4 border-t border-slate-100 pt-3">
            <div>
              <div className="text-sm font-bold text-[#1B1F3B]">
                {t('email_prefs.transactional_title')}
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                {t('email_prefs.transactional_detail')}
              </p>
            </div>
            <span
              className="mt-1 flex shrink-0 items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-500"
              title={t('email_prefs.transactional_always')}
            >
              <span aria-hidden="true"><Lock size={10} /></span>
              {t('email_prefs.transactional_always')}
            </span>
          </div>

          <div role="status" aria-live="polite" className="min-h-4">
            {error && <p className="text-xs font-bold text-rose-600">{error}</p>}
            {busy && (
              <p className="flex items-center gap-2 text-xs text-slate-500">
                <StatusIcon status="loading" size={12} className="text-[#A37E44]" />
                {t('email_prefs.saving')}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
};
