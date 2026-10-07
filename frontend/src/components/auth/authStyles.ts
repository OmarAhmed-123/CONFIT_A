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
  'w-full min-h-12 rounded-xl border border-slate-200 bg-white px-3 py-2.5 ' +
  'text-sm text-[#1B1F3B] transition-colors duration-300 ease-luxury ' +
  'focus:border-[#A37E44] focus:outline-none focus:ring-2 focus:ring-[#C5A059]/40';

/** Primary action: full-width, 48px floor, visible focus ring, honest disabled. */
export const AUTH_PRIMARY_BTN_CLASS =
  'inline-flex w-full min-h-12 items-center justify-center gap-2 rounded-xl ' +
  'bg-[#1B1F3B] px-5 text-sm font-bold text-white shadow-md ' +
  'transition-all duration-300 ease-luxury hover:bg-[#0C0E1E] ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ' +
  'disabled:cursor-not-allowed disabled:opacity-50';
