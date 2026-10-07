import React from 'react';
import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';

/**
 * PasswordPolicyChecklist — ONE live mirror of the SERVER's real password
 * policy (8–72 chars, ≥3 of lower/upper/digit/symbol; see backend
 * auth_service). Extracted from ResetPasswordView so the REGISTER form can
 * finally give the same guidance: before this, a shopper creating an
 * account typed blind against a static hint line and discovered the policy
 * only from a server rejection — the reset page already did better.
 *
 * Functional: pure derivation from `password` (and optional `confirm` for
 * the match row); no requests, no invented rules — the server stays the
 * authority. Non-functional: state is colour AND text (sr-only met/unmet
 * suffix), icons aria-hidden, 200ms colour transitions only.
 */
export const passwordPolicyChecks = (password: string) => ({
  length: password.length >= 8 && password.length <= 72,
  categories:
    [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter((r) => r.test(password))
      .length >= 3,
});

export const passwordPolicyMet = (password: string): boolean => {
  const c = passwordPolicyChecks(password);
  return c.length && c.categories;
};

const Row: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => {
  const { t } = useTranslation();
  return (
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
          {ok
            ? ` — ${t('reset_password.rule_met')}`
            : ` — ${t('reset_password.rule_unmet')}`}
        </span>
      </span>
    </li>
  );
};

export const PasswordPolicyChecklist: React.FC<{
  password: string;
  /** When provided, a third "passwords match" row is shown. */
  confirm?: string;
  className?: string;
}> = ({ password, confirm, className }) => {
  const { t } = useTranslation();
  const checks = passwordPolicyChecks(password);
  return (
    <ul
      className={`space-y-1.5 ${className ?? ''}`}
      aria-label={t('reset_password.rules_title')}
    >
      <Row ok={checks.length} label={t('reset_password.rule_length')} />
      <Row ok={checks.categories} label={t('reset_password.rule_categories')} />
      {confirm !== undefined && (
        <Row
          ok={password.length > 0 && password === confirm}
          label={t('reset_password.rule_match')}
        />
      )}
    </ul>
  );
};
