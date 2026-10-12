/**
 * Auth design tokens (auth cluster pass, 2026-10-07).
 *
 * Before this module the SAME field and primary-button were styled four
 * times across AuthModal / ResetPasswordView / VerifyEmailView — with real
 * drift: the modal's fields had no focus ring (border-only), the pages had
 * ring+border; the modal's primary button had NO focus-visible ring at
 * all. One token each now owns the geometry, focus contract and the
 * luxury easing; call sites may only append local modifiers (e.g.
 * font-mono for OTP codes).
 */

/** Text field: 48px floor (master-prompt target floor), gold focus ring + border, luxury easing. */
export const AUTH_FIELD_CLASS =
  'w-full min-h-12 rounded-xl border border-brand-field bg-white px-3 py-2.5 ' +
  'text-sm text-brand-charcoal transition-colors duration-300 ease-luxury ' +
  'focus:border-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal/25';

/** Primary action: full-width, 48px floor, visible focus ring, honest disabled. */
export const AUTH_PRIMARY_BTN_CLASS =
  'inline-flex w-full min-h-12 items-center justify-center gap-2 rounded-xl ' +
  'bg-brand-charcoal px-5 text-sm font-bold text-white shadow-md ' +
  'transition-all duration-300 ease-luxury hover:bg-[#1A1B1D] ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 ' +
  'disabled:cursor-not-allowed disabled:opacity-50';
