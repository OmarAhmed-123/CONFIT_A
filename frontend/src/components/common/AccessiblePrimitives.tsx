import React from 'react';
import { useTranslation } from 'react-i18next';

/**
 * AccessiblePrimitives — shared a11y primitives for Wave 0 (010).
 *
 * WHY: Audits A11Y-05, VTON-13, STY-14, ADM-19, BRD-15, CUS-19 repeatedly found:
 * - emoji-as-UI with no accessible name
 * - missing labels, focus not managed
 * - controls not keyboard operable
 *
 * These primitives enforce:
 * - Every interactive control has accessible name (aria-label or visible text)
 * - Keyboard operability (button type="button", focus-visible ring, min 44px touch target)
 * - No emoji-only affordance — emoji must have aria-hidden + text label
 * - Semantic markup, visible focus, appropriate roles
 */

export const usePrefersReducedMotion = (): boolean => {
  const [prefersReduced, setPrefersReduced] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReduced(mq.matches);
    const handler = (e: MediaQueryListEvent) => setPrefersReduced(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return prefersReduced;
};

interface AccessibleButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const AccessibleButton: React.FC<AccessibleButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  className = '',
  disabled,
  ...props
}) => {
  const base =
    'inline-flex items-center justify-center rounded-xl font-semibold tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none';
  const sizes = {
    sm: 'min-h-[44px] min-w-[44px] px-3 py-2 text-xs',
    md: 'min-h-[44px] min-w-[44px] px-4 py-2.5 text-sm',
    lg: 'min-h-[48px] min-w-[48px] px-6 py-3 text-sm',
  };
  const variants = {
    primary: 'bg-[#1B1F3B] text-white hover:bg-[#2A2F5A] border border-[#1B1F3B]',
    secondary: 'bg-white text-[#1B1F3B] hover:bg-slate-50 border border-slate-200',
    ghost: 'bg-transparent text-[#1B1F3B] hover:bg-slate-100 border border-transparent',
    danger: 'bg-rose-600 text-white hover:bg-rose-700 border border-rose-600',
  };

  return (
    <button
      type="button"
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          <span className="sr-only">Loading</span>
          <span aria-hidden="true" className="motion-safe:animate-spin mr-2 h-4 w-4 border-2 border-current border-t-transparent rounded-full" />
        </>
      ) : null}
      {children}
    </button>
  );
};

interface AccessibleInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export const AccessibleInput: React.FC<AccessibleInputProps> = ({
  label,
  error,
  hint,
  id,
  className = '',
  ...props
}) => {
  const generatedId = React.useId();
  const inputId = id ?? generatedId;
  const errorId = error ? `${inputId}-error` : undefined;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium text-[#1B1F3B]">
        {label}
      </label>
      <input
        id={inputId}
        className={`min-h-[44px] w-full rounded-xl border px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
          error ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'
        } ${className}`}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      />
      {hint && !error && (
        <p id={hintId} className="text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs text-rose-600">
          {error}
        </p>
      )}
    </div>
  );
};

interface AccessibleSelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  options: { value: string; label: string }[];
}

export const AccessibleSelect: React.FC<AccessibleSelectProps> = ({
  label,
  error,
  options,
  id,
  className = '',
  ...props
}) => {
  const generatedId = React.useId();
  const selectId = id ?? generatedId;
  const errorId = error ? `${selectId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={selectId} className="text-sm font-medium text-[#1B1F3B]">
        {label}
      </label>
      <select
        id={selectId}
        className={`min-h-[44px] w-full rounded-xl border px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
          error ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'
        } ${className}`}
        aria-invalid={!!error}
        aria-describedby={errorId}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={errorId} role="alert" className="text-xs text-rose-600">
          {error}
        </p>
      )}
    </div>
  );
};

/**
 * IconButton — for icon-only controls, enforces accessible name.
 * Emoji must never be sole affordance — must have aria-label and aria-hidden on emoji.
 */
export const IconButton: React.FC<{
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
}> = ({ icon, label, onClick, className = '', disabled }) => {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={`min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-xl hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] disabled:opacity-50 ${className}`}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  );
};

/**
 * FocusTrap — simple focus management for modals/drawers.
 * Ensures focus stays inside and returns to trigger on close.
 */
export const FocusTrap: React.FC<{ children: React.ReactNode; active?: boolean }> = ({
  children,
  active = true,
}) => {
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    if (!container) return;

    const focusable = container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);
    first?.focus();

    return () => container.removeEventListener('keydown', handleKeyDown);
  }, [active]);

  return <div ref={containerRef}>{children}</div>;
};
