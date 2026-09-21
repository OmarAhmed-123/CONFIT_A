import React from 'react';
import { useTranslation } from 'react-i18next';
import { SparkleIcon } from '../icons/ConfitIcons';
import { resolveMessage, type TranslatableMessage } from '../../i18n/messages';
import { formatMoney } from '../../i18n/format';

export const Toast: React.FC<{
  /** Either a pre-translated string or a key+params descriptor from a store. */
  message: TranslatableMessage;
  type?: 'success' | 'error' | 'info';
  onClose: () => void;
}> = ({ message, type = 'info', onClose }) => {
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
    <div className="fixed bottom-20 sm:bottom-8 end-4 sm:end-8 z-50 animate-in fade-in slide-in-from-bottom-3 duration-200">
      <div
        className={`flex items-center gap-3.5 px-4 py-3 rounded-2xl border shadow-2xl backdrop-blur-xl max-w-md ${bgClass}`}
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#C5A059] animate-pulse" aria-hidden="true" />
        <span className="text-xs font-medium tracking-wide leading-relaxed">{text}</span>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white text-xs ms-auto ps-2 transition-colors"
          aria-label={t('a11y.dismiss_notification')}
          type="button"
        >
          ✕
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md animate-in fade-in duration-150">
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
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FDF8EE] border border-[#C5A059]/30 shadow-2xs backdrop-blur-xs ${className}`}
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
  price: number;
  currency?: string;
  provider?: string;
  installmentAmount?: number | null;
  eligible?: boolean;
  className?: string;
}> = ({ price, currency = 'USD', provider, installmentAmount, eligible = true, className = '' }) => {
  const { t, i18n } = useTranslation();
  if (!eligible) {
    return null;
  }
  const installment = installmentAmount ?? price / 4;
  if (!Number.isFinite(installment)) {
    return null;
  }
  const lang = i18n.resolvedLanguage ?? 'en';
  return (
    <div
      className={`inline-flex items-center gap-1.5 text-[11px] text-slate-600 bg-slate-50 border border-slate-200/80 px-2.5 py-1 rounded-lg ${className}`}
    >
      <span>
        {t('commerce.bnpl_line', {
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
      className="flex flex-col items-center justify-center p-14 gap-3 text-slate-500 animate-in fade-in duration-200"
      role="status"
      aria-live="polite"
    >
      <div className="w-8 h-8 border-2 border-slate-200 border-t-[#C5A059] rounded-full animate-spin" aria-hidden="true"></div>
      <span className="text-xs font-medium text-slate-600 tracking-wide">{text ?? t('common.loading')}</span>
    </div>
  );
};

export const SkeletonCard: React.FC = () => (
  <div className="bg-white rounded-3xl border border-slate-200/80 p-3.5 shadow-2xs animate-pulse space-y-3" aria-hidden="true">
    <div className="h-64 rounded-2xl bg-slate-100"></div>
    <div className="space-y-1.5 pt-1">
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
  <div className="flex flex-col items-center justify-center text-center p-12 bg-white rounded-3xl border border-slate-200/80 shadow-2xs my-6">
    <div className="w-14 h-14 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/20 flex items-center justify-center text-[#C5A059] mb-3.5 shadow-2xs">
      {icon || <SparkleIcon size={26} color="#C5A059" />}
    </div>
    <h2 className="font-serif text-lg font-bold text-[#1B1F3B] mb-1">{title}</h2>
    <p className="text-xs text-slate-500 max-w-sm mb-4 leading-relaxed font-light">{description}</p>
    {actionText && onAction && (
      <button
        onClick={onAction}
        className="px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold shadow-sm transition-all"
        type="button"
      >
        {actionText}
      </button>
    )}
  </div>
);
