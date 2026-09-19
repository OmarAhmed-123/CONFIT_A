import React from 'react';
import { Link } from 'react-router-dom';
import { ConfitLogo } from '../../components/common/ConfitLogo';

/**
 * Shared chrome for every auth flow page (verify / reset / apply / invite).
 * One layout, one set of affordances — the audit found the auth surfaces had
 * drifted into inconsistent ad-hoc cards.
 */
export const AuthShell: React.FC<{
  eyebrow: string;
  title: string;
  children: React.ReactNode;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
}> = ({ eyebrow, title, children, tone = 'neutral' }) => {
  const border = {
    neutral: 'border-[#C5A059]/40',
    success: 'border-emerald-500/40',
    warning: 'border-amber-500/40',
    danger: 'border-rose-500/40',
  }[tone];
  const eyebrowColor = {
    neutral: 'text-[#C5A059]',
    success: 'text-emerald-400',
    warning: 'text-amber-400',
    danger: 'text-rose-400',
  }[tone];

  return (
    <div className="min-h-[70vh] flex items-center justify-center p-4 bg-[#FAF9F6]">
      <div className={`max-w-lg w-full bg-[#0C0E1E] text-white border ${border} rounded-3xl p-8 shadow-2xl space-y-6`}>
        <div className="flex items-center justify-center">
          <ConfitLogo variant="compact" theme="light" size="md" />
        </div>
        <div className="text-center space-y-2">
          <span className={`text-[10px] font-bold tracking-widest uppercase ${eyebrowColor}`}>{eyebrow}</span>
          <h1 className="font-serif text-2xl font-bold text-white">{title}</h1>
        </div>
        <div className="space-y-4 text-xs text-slate-300">{children}</div>
        <div className="pt-2 text-center">
          <Link to="/" className="text-[11px] text-slate-400 hover:text-[#C5A059] transition-colors">
            ← Return to consumer storefront
          </Link>
        </div>
      </div>
    </div>
  );
};

export const AuthInput: React.FC<React.InputHTMLAttributes<HTMLInputElement> & { label: string }> = ({
  label,
  ...rest
}) => (
  <label className="block space-y-1">
    <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</span>
    <input
      {...rest}
      className="w-full px-3.5 py-2.5 rounded-xl bg-[#141833] border border-slate-700 text-white text-sm placeholder:text-slate-500 focus:outline-none focus:border-[#C5A059] focus:ring-1 focus:ring-[#C5A059]/40"
    />
  </label>
);

export const AuthButton: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' }
> = ({ variant = 'primary', className = '', children, ...rest }) => (
  <button
    {...rest}
    className={
      variant === 'primary'
        ? `w-full py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] disabled:opacity-60 disabled:cursor-not-allowed text-[#0C0E1E] font-bold text-xs tracking-wider uppercase shadow-md transition-all ${className}`
        : `w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 disabled:opacity-60 text-white font-semibold text-xs border border-slate-700 transition-all ${className}`
    }
  >
    {children}
  </button>
);

export const AuthNote: React.FC<{ tone?: 'info' | 'success' | 'error'; children: React.ReactNode }> = ({
  tone = 'info',
  children,
}) => {
  const cls = {
    info: 'bg-slate-900/70 border-slate-700 text-slate-300',
    success: 'bg-emerald-950/50 border-emerald-500/40 text-emerald-200',
    error: 'bg-rose-950/50 border-rose-500/40 text-rose-200',
  }[tone];
  return (
    <div className={`p-3 rounded-xl border text-[11px] leading-relaxed ${cls}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
};
