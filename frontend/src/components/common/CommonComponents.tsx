import React from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { SparkleIcon } from '../icons/ConfitIcons';
import { StatusIcon } from './InteractionPrimitives';
import { resolveMessage, type TranslatableMessage } from '../../i18n/messages';
import { formatMoney } from '../../i18n/format';

export const Toast: React.FC<{
  /** Either a pre-translated string or a key+params descriptor from a store. */
  message: TranslatableMessage;
  type?: 'success' | 'error' | 'info';
  onClose: () => void;
  /**
   * Optional recovery action (Undo). Extended here rather than as a separate
   * UndoToast so there is ONE aria-live region, one dismiss control and one
   * set of logical-direction classes; a forked component is how the Arabic
   * layout drifts from the English one.
   */
  action?: { label: string; onAction: () => void } | null;
}> = ({ message, type = 'info', onClose, action = null }) => {
  const { t } = useTranslation();
  const bgClass =
    type === 'success'
      ? 'bg-[#0F291E] border-emerald-500/40 text-emerald-100 shadow-emerald-950/40'
      : type === 'error'
      ? 'bg-[#2A1115] border-rose-500/40 text-rose-100 shadow-rose-950/40'
      : 'bg-[#0C0E1E] border-[#C5A059]/40 text-slate-100 shadow-black/60';

  // A store has no t(); it emits { key, params } and the translated sentence
  // is produced HERE, at the render boundary, in the user's active language.
  const text = resolveMessage(message, t);

  return (
    <div className="fixed bottom-20 sm:bottom-8 end-4 sm:end-8 z-50 confit-slide-up">
      <div
        className={`flex items-center gap-3.5 px-4 py-3 rounded-2xl border shadow-2xl backdrop-blur-xl max-w-md ${bgClass}`}
        /* Spec 14 §6.3: the CONTAINER carries the live-region role, not the
           icon. Errors interrupt (alert/assertive); the rest wait politely. */
        role={type === 'error' ? 'alert' : 'status'}
        aria-live={type === 'error' ? 'assertive' : 'polite'}
        aria-atomic="true"
      >
        {/* Shape per type — state is never colour-only (spec 14 §8). The
            icon is decorative: the sentence beside it IS the status. */}
        <StatusIcon
          status={type === 'success' ? 'success' : type === 'error' ? 'error' : 'info'}
          size={16}
          className={type === 'info' ? 'text-[#C5A059]' : ''}
          data-testid="toast-status-icon"
        />
        <span className="text-xs font-medium tracking-wide leading-relaxed">{text}</span>
        {action ? (
          <button
            type="button"
            onClick={() => { action.onAction(); onClose(); }}
            /* min-h/min-w 44px: the spec's touch target floor. The visible
               pill is smaller, so the tap area is grown rather than the
               label, keeping the toast compact on a 390px screen. */
            className="ms-1 shrink-0 min-h-[44px] min-w-[44px] px-3 inline-flex items-center justify-center rounded-xl border border-[#C5A059]/50 text-[#E9D8A6] hover:bg-[#C5A059]/15 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[#C5A059] text-xs font-semibold tracking-wide transition-colors"
          >
            {action.label}
          </button>
        ) : null}
        <button
          onClick={onClose}
          /* 44px touch floor (spec 14 §7) — grown tap area, compact pill. */
          className="ms-auto shrink-0 min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-xl text-slate-400 hover:text-white focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[#C5A059] transition-colors"
          aria-label={t('a11y.dismiss_notification')}
          type="button"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
};

export const Modal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  maxWidth?: string;
  /** Overrides the generated heading id — set when the caller owns the heading. */
  labelledBy?: string;
}> = ({ isOpen, onClose, title, subtitle, children, maxWidth = 'max-w-2xl', labelledBy }) => {
  const { t } = useTranslation();
  const generatedId = React.useId();
  const titleId = labelledBy ?? (title ? `${generatedId}-title` : undefined);
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md confit-fade-in">
      <div
        className={`w-full ${maxWidth} bg-white rounded-3xl shadow-2xl border border-slate-200/80 overflow-hidden max-h-[92vh] flex flex-col`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        {title && (
          <div className="flex items-center justify-between px-6 py-4.5 border-b border-slate-100 bg-[#FAF9F6]">
            <div>
              <h3 id={titleId} className="font-serif text-lg font-bold text-[#1B1F3B] tracking-tight">
                {title}
              </h3>
              {subtitle && <p className="text-xs text-slate-500 mt-0.5 font-light">{subtitle}</p>}
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-800 hover:bg-slate-200/70 transition-colors"
              aria-label={t('a11y.close_dialog')}
              type="button"
            >
              ✕
            </button>
          </div>
        )}
        <div className="p-6 overflow-y-auto flex-1">{children}</div>
      </div>
    </div>
  );
};

export const FitScoreBadge: React.FC<{ score?: number | null; verdict?: string; label?: string; className?: string }> = ({
  score,
  verdict = 'True to Size',
  label = 'Fit',
  className = '',
}) => {
  if (score === undefined || score === null) {
    return null;
  }
  return (
    <div
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FDF8EE] border border-[#C5A059]/30 shadow-sm ${className}`}
    >
      <SparkleIcon size={13} color="#C5A059" />
      <span className="text-[11px] font-bold text-[#7A5C28]">{score}% {label}</span>
      <span className="text-[10px] text-slate-600 font-medium tracking-wide">· {verdict}</span>
    </div>
  );
};

/**
 * Instalment hint.
 *
 * i18n: the sentence is now a key with two interpolation slots, and the amount
 * is produced by the locale-aware money formatter instead of
 * `$${installment}` — an Arabic page previously showed a US-dollar glyph and
 * Latin digits next to Arabic text.
 *
 * Capability gating (`payments_mode`, `bnpl_live`) is applied by the callers
 * through useCapabilities — see the footer trust block for the pattern.
 */
export const BNPLBadge: React.FC<{
  /**
   * REQUIRED, same precedent as `isEstimate` below: this component used to
   * default to `'USD'`, and the product page forgot to pass the prop — so an
   * EGP storefront showed "4 payments of $18.75" under a price of
   * EGP 3,932.37 (production screenshot, 2026-10-07). A missing currency is
   * now a `tsc --noEmit` failure instead of a silent dollar sign.
   */
  currency: string;
  provider?: string;
  /**
   * The server's figure, verbatim. There is deliberately NO `price / 4`
   * fallback any more: a number invented in the browser is exactly the class
   * of claim this badge exists to prevent. No server figure → no badge.
   */
  installmentAmount?: number | null;
  /**
   * True when the figure is an illustrative split, not an offer from a lender.
   * The server sets this from `bnpl_is_live()`: a live PSP adapter must exist
   * before any provider is named. An estimate therefore renders WITHOUT a
   * provider name — "4 payments ... with Tabby" on a deployment where Tabby has
   * offered nothing is a false claim, not a teaser.
   *
   * REQUIRED, deliberately: with a default, a call site that forgets the flag
   * silently renders one of the two branches, and the wrong one names a lender.
   * Omitting it is now a `tsc --noEmit` failure rather than a judgement call.
   */
  isEstimate: boolean;
  eligible?: boolean;
  className?: string;
}> = ({ currency, provider, installmentAmount, isEstimate, eligible = true, className = '' }) => {
  const { t, i18n } = useTranslation();
  if (!eligible) {
    return null;
  }
  const installment = installmentAmount;
  if (installment == null || !Number.isFinite(installment) || installment <= 0) {
    return null;
  }
  const lang = i18n.resolvedLanguage ?? 'en';
  return (
    <div
      className={`inline-flex items-center gap-1.5 text-[11px] text-slate-600 bg-slate-50 border border-slate-200/80 px-2.5 py-1 rounded-lg ${className}`}
    >
      <span>
        {isEstimate
          ? t('commerce.bnpl_estimate_line', {
              amount: formatMoney(Math.round(installment * 100), currency, lang),
            })
          : t('commerce.bnpl_line', {
              amount: formatMoney(Math.round(installment * 100), currency, lang),
              provider: provider ?? t('commerce.bnpl_default_provider'),
            })}
      </span>
    </div>
  );
};

export const LoadingSpinner: React.FC<{ text?: string }> = ({ text }) => {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-col items-center justify-center p-14 gap-3 text-slate-500 confit-fade-in"
      role="status"
      aria-live="polite"
    >
      <div className="w-8 h-8 border-2 border-slate-200 border-t-[#C5A059] rounded-full motion-safe:animate-spin" aria-hidden="true"></div>
      <span className="text-xs font-medium text-slate-600 tracking-wide">{text ?? t('common.loading')}</span>
    </div>
  );
};

/* Home pass 3: the hero image block carries a directional shimmer sweep
   (geometry-tailored, RTL-aware, auto-disabled under reduced motion — see
   .skeleton-shimmer in styles/index.css) instead of a flat opacity pulse;
   the text lines keep the quieter pulse so the sweep stays ONE light. */
export const SkeletonCard: React.FC = () => (
  <div className="bg-white rounded-3xl border border-slate-200/80 p-3.5 shadow-sm space-y-3" aria-hidden="true">
    <div className="skeleton-shimmer h-64 rounded-2xl bg-slate-100"></div>
    <div className="space-y-1.5 pt-1 animate-pulse">
      <div className="h-3 w-16 bg-slate-100 rounded"></div>
      <div className="h-4 w-3/4 bg-slate-200 rounded"></div>
      <div className="h-4 w-20 bg-slate-100 rounded"></div>
    </div>
  </div>
);

export const EmptyState: React.FC<{
  title: string;
  description: string;
  actionText?: string;
  onAction?: () => void;
  icon?: React.ReactNode;
}> = ({ title, description, actionText, onAction, icon }) => (
  <div className="flex flex-col items-center justify-center text-center p-12 bg-white rounded-3xl border border-slate-200/80 shadow-sm my-6">
    <div className="w-14 h-14 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/20 flex items-center justify-center text-[#C5A059] mb-3.5 shadow-sm">
      {icon || <SparkleIcon size={26} color="#C5A059" />}
    </div>
    <h2 className="font-serif text-lg font-bold text-[#1B1F3B] mb-1">{title}</h2>
    <p className="text-xs text-slate-500 max-w-sm mb-4 leading-relaxed font-light">{description}</p>
    {actionText && onAction && (
      <button
        onClick={onAction}
        className="min-h-12 px-6 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A37E44]"
        type="button"
      >
        {actionText}
      </button>
    )}
  </div>
);
