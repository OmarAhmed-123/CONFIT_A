import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation } from 'react-router-dom';
import { useModalFocus } from '../../hooks/useModalFocus';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { authService } from '../../services/apiServices';
import { localizeApiError } from '../../i18n/apiErrors';
import { ConfitLogo } from '../../components/common/ConfitLogo';
import { UserIcon } from '../../components/icons/ConfitIcons';
import { usePrefersReducedMotion } from '../../components/common/InteractionPrimitives';
import { Eye, EyeOff } from 'lucide-react';
import { PasswordPolicyChecklist } from '../../components/auth/PasswordPolicyChecklist';
import {
  AUTH_FIELD_CLASS,
  AUTH_PRIMARY_BTN_CLASS,
} from '../../components/auth/authStyles';

// Group 1 §14: demo-persona quick-login buttons are DEV-only. They are
// hard-gated on Vite's build-time constant so production bundles never
// contain either the buttons or the seeded passwords.
const IS_DEV = import.meta.env.DEV === true;

/** AUTH-02 FIX: post-login landing policy. A brand account signing in from
 * anywhere lands on its portal; an admin lands on platform governance;
 * consumers stay where they are (storefront). Keeps the modal a single
 * entry point for every layout instead of duplicating handlers per route. */
const landingPathForRole = (role?: string | null): string | null => {
  const r = (role || '').toLowerCase();
  if (r === 'admin') return '/admin';
  if (r.startsWith('brand_')) return '/b2b';
  return null;
};

/**
 * Spec 02 — Auth / Sign-up transition.
 *
 * LOCAL STATE MACHINE
 * -------------------
 * `view`: 'signin' | 'signup' | 'forgot' — which form is shown. The MFA
 * challenge is an overlay STEP driven by the store's `mfaRequired` flag
 * (the server said so via MFA_REQUIRED; it is a state, not an error).
 * Pending/error phases come from the real mutations in authStore — this
 * component never invents a success the server did not confirm.
 *
 * CONTEXT CONTRACT
 * ----------------
 * The modal renders OVER the page, so the shopper's place survives by
 * construction. On successful auth we additionally:
 *   1. consume `pendingAuthIntent` exactly once (uiStore clears before run);
 *   2. consume `authReturnTo` and navigate only if one was requested;
 *   3. apply the role landing policy (brand/admin portals).
 * Nothing sensitive is ever written to storage from this form: password and
 * MFA code live in component state only.
 *
 * FORGOT PASSWORD — honesty notes
 * -------------------------------
 * POST /auth/forgot-password is real, rate-limited and non-committal by
 * design (it never reveals whether an email exists — the backend enforces
 * this, and we show one fixed confirmation either way, so the UI adds no
 * side-channel). On deployments without an email provider the server
 * answers an honest 501 FEATURE_NOT_CONFIGURED(email_delivery); we surface
 * exactly that instead of pretending a mail was queued.
 */
type AuthView = 'signin' | 'signup' | 'forgot';
type ForgotPhase = 'idle' | 'pending' | 'sent' | 'unconfigured' | 'error';

export const AuthModal: React.FC = () => {
  const { t } = useTranslation();
  const {
    isAuthModalOpen,
    authModalMode,
    openAuthModal,
    closeAuthModal,
    showToast,
    consumeAuthIntent,
    consumeAuthReturnTo,
  } = useUIStore();
  const panelRef = useModalFocus<HTMLDivElement>(closeAuthModal, isAuthModalOpen);
  const { login, register, isLoading, error, errorCode, mfaRequired, completeMfaLogin, resetError } =
    useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const reduceMotion = usePrefersReducedMotion();

  const [view, setView] = useState<AuthView>(authModalMode === 'register' ? 'signup' : 'signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [forgotPhase, setForgotPhase] = useState<ForgotPhase>('idle');
  // ── MFA second factor via EMAIL (2026-10-06) ─────────────────────────
  // The dialog offered only authenticator/recovery codes; a shopper
  // without their phone was locked out. 'app' stays the default.
  const [mfaMethod, setMfaMethod] = useState<'app' | 'email'>('app');
  const [emailCodePhase, setEmailCodePhase] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle');
  const [emailCodeInfo, setEmailCodeInfo] = useState<{ sentTo: string; minutes: number } | null>(null);
  const [emailCodeError, setEmailCodeError] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);

  // Resend cooldown ticks once a second while armed.
  useEffect(() => {
    if (resendIn <= 0) return;
    const id = window.setInterval(() => setResendIn((v) => v - 1), 1000);
    return () => window.clearInterval(id);
  }, [resendIn > 0]);

  // Spec 02 §9 "deep link works": `?auth=signin|login|signup|register|forgot`
  // on ANY route opens the modal on that step, then the param is stripped
  // (replace, not push) so Back never re-opens it and the URL stays shareable
  // without the modal baked in. Unknown values are ignored — no modal, no
  // navigation. The shopper stays exactly where the link pointed.
  const deepLinkView = useRef<AuthView | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const raw = params.get('auth');
    if (!raw) return;
    const normalized =
      raw === 'signup' || raw === 'register'
        ? 'register'
        : raw === 'signin' || raw === 'login' || raw === 'forgot'
          ? 'login'
          : null;
    params.delete('auth');
    const nextSearch = params.toString();
    if (normalized) {
      if (raw === 'forgot') deepLinkView.current = 'forgot';
      openAuthModal(normalized);
    }
    navigate(
      { pathname: location.pathname, search: nextSearch ? `?${nextSearch}` : '', hash: location.hash },
      { replace: true },
    );
    // location.search is the full trigger; the rest are stable store/router fns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  // The store's authModalMode can change while the modal stays mounted
  // (e.g. RoleGuard opens 'login', footer opens 'register'). Keep the local
  // view in sync — previously a stale internal mode ignored the caller.
  // A pending deep-link step (forgot) wins exactly once, then is cleared.
  useEffect(() => {
    if (isAuthModalOpen) {
      const deep = deepLinkView.current;
      deepLinkView.current = null;
      setView(deep ?? (authModalMode === 'register' ? 'signup' : 'signin'));
      setShowPassword(false);
      setForgotPhase('idle');
      setMfaMethod('app');
      setEmailCodePhase('idle');
      setEmailCodeInfo(null);
      setEmailCodeError(null);
      setResendIn(0);
    }
  }, [isAuthModalOpen, authModalMode]);

  // One-shot guard: even if two success paths raced, the intent fires once.
  const intentFired = useRef(false);
  useEffect(() => {
    if (isAuthModalOpen) intentFired.current = false;
  }, [isAuthModalOpen]);

  if (!isAuthModalOpen) return null;

  const switchView = (next: AuthView) => {
    resetError();
    setForgotPhase('idle');
    setView(next);
  };

  /** Shared post-auth epilogue: intent once, returnTo once, role landing. */
  const finishAuth = (res: any) => {
    if (!intentFired.current) {
      intentFired.current = true;
      const intent = consumeAuthIntent();
      intent?.();
    }
    const returnTo = consumeAuthReturnTo();
    const landing = landingPathForRole(res?.user?.role);
    const here = location.pathname;
    if (returnTo && returnTo !== here) {
      navigate(returnTo, { replace: true });
    } else if (landing && !here.startsWith(landing)) {
      navigate(landing, { replace: true });
    }
    closeAuthModal();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (view === 'signin') {
        // Group 1 §11: two-step login. If the account has MFA, `login`
        // throws with reason=MFA_REQUIRED and the store flips a flag;
        // the second-step form below sends the code.
        const res = await login(email, password);
        showToast(t('auth.welcome_back'), 'success');
        finishAuth(res);
      } else {
        const res = await register({ email, password, full_name: fullName, phone });
        showToast(t('auth.account_created'), 'success');
        finishAuth(res);
      }
    } catch {
      // MFA_REQUIRED keeps the modal open in the MFA step; real failures
      // surface via `error` from the store, announced in the live region.
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await completeMfaLogin(email, password, mfaCode);
      showToast(t('auth.mfa_signed_in'), 'success');
      finishAuth(res);
    } catch {
      // Error surfaced via `error` in the store.
    }
  };

  const handleSendEmailCode = async () => {
    if (emailCodePhase === 'sending' || resendIn > 0) return;
    setEmailCodePhase('sending');
    setEmailCodeError(null);
    try {
      const res = await authService.requestMfaEmailCode(email, password);
      // "sent" is the SERVER's word — the transport really accepted it.
      setEmailCodeInfo({ sentTo: res.sent_to, minutes: res.expires_in_minutes });
      setEmailCodePhase('sent');
      setResendIn(30);
    } catch (err) {
      // Honest failure (502 transport / 501 unconfigured / 401) — no
      // "check your inbox" for a mail that was never accepted. The generic
      // PROVIDER_ERROR catalogue string talks about PAYMENTS ("nothing was
      // charged") — flatly wrong here, so this path owns its own words.
      const code = (err as { code?: string } | null)?.code;
      setEmailCodeError(
        code === 'PROVIDER_ERROR' || code === 'FEATURE_NOT_CONFIGURED'
          ? t('auth.mfa_email_send_failed')
          : localizeApiError(err, t, 'auth.mfa_email_send_failed'),
      );
      setEmailCodePhase('failed');
    }
  };

  const handleForgotSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotPhase('pending');
    try {
      await authService.forgotPassword(email.trim());
      // ONE fixed message regardless of whether the account exists — the
      // server is non-committal and the UI must not add a side-channel.
      setForgotPhase('sent');
    } catch (err: any) {
      if (err?.code === 'FEATURE_NOT_CONFIGURED' || err?.status === 501) {
        // Honest 501: this deployment cannot send mail. Saying "check your
        // inbox" here would be a lie about a mail that was never queued.
        setForgotPhase('unconfigured');
      } else {
        setForgotPhase('error');
      }
    }
  };

  const heading =
    mfaRequired
      ? t('auth.heading_mfa')
      : view === 'signin'
        ? t('auth.heading_signin')
        : view === 'signup'
          ? t('auth.heading_signup')
          : t('auth.heading_forgot');

  // Spec 02 §6: failures are translated by CODE, never shown as the raw
  // English server string. Context matters: AUTH_FAILED on the login form
  // means "wrong credentials" (errors.auth_failed is the session-expiry
  // copy — wrong message here); on the MFA step it means "bad code".
  // Register conflict arrives as VALIDATION_ERROR — the server message is
  // matched only to pick the translated conflict copy, the API contract is
  // untouched. Everything else (network, timeout, HTTP) goes through the
  // shared localizeApiError map; its last resort is the honest server text.
  const displayError = !error
    ? null
    : errorCode === 'AUTH_FAILED'
      ? mfaRequired
        ? t('auth.mfa_code_invalid')
        : t('auth.invalid_credentials')
      : errorCode === 'VALIDATION_ERROR' && /already exists/i.test(error)
        ? t('auth.email_exists')
        : localizeApiError({ code: errorCode, message: error }, t);

  // 180–240ms local ENTER-only motion (spec 02 §8); none under reduced
  // motion. Enter-only means the next form mounts immediately — no exit
  // waiting, no layout jump, and the switch works identically with the
  // animation disabled (the motion is garnish, not the mechanism).
  const formMotion = reduceMotion
    ? { initial: false as const }
    : {
        initial: { opacity: 0, y: 6 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.2, ease: 'easeOut' as const },
      };

  // Auth design tokens (shared with the reset/verify pages) — the modal's
  // previous local copies had NO focus ring on fields and NO focus-visible
  // ring on the primary button.
  const inputClass = AUTH_FIELD_CLASS;
  const primaryButtonClass = AUTH_PRIMARY_BTN_CLASS;

  const activeStep = mfaRequired ? 'mfa' : view;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-150">
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-heading"
        tabIndex={-1}
        initial={reduceMotion ? false : { y: 16, scale: 0.97 }}
        animate={{ y: 0, scale: 1 }}
        transition={
          reduceMotion
            ? { duration: 0 }
            : { duration: 0.35, ease: [0.25, 1, 0.5, 1] }
        }
        className="w-full max-w-md bg-white rounded-3xl shadow-2xl overflow-hidden border border-slate-100"
      >
        {/* Luxury Top Banner */}
        <div className="p-6 bg-[#0C0E1E] text-white flex justify-between items-center border-b border-slate-800">
          <ConfitLogo variant="compact" theme="light" size="md" />
          <button
            onClick={closeAuthModal}
            aria-label={t('common.close')}
            className="min-w-[44px] min-h-[44px] flex items-center justify-center text-slate-400 hover:text-white text-sm"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        {/* Visible step heading — the current step is readable, not inferred
            from field shapes. Same node carries the dialog's accessible name. */}
        <h2
          id="auth-modal-heading"
          className="px-6 pt-5 font-serif text-lg font-bold text-[#1B1F3B] tracking-tight"
        >
          {heading}
        </h2>

        {/* Spec 02 §7: the auth state is TEXT in a polite live region —
            pending, failure and the MFA step never rely on colour/motion. */}
        <span className="sr-only" role="status" aria-live="polite">
          {isLoading
            ? t('auth.status_pending')
            : displayError
              ? displayError
              : mfaRequired
                ? t('auth.status_mfa_required')
                : forgotPhase === 'sent'
                  ? t('auth.forgot_sent')
                  : forgotPhase === 'unconfigured'
                    ? t('auth.forgot_unconfigured')
                    : ''}
        </span>

        {/* Development-only 1-Click Demo Persona Shortcuts */}
        {IS_DEV && !mfaRequired && (
          <div className="p-4 bg-[#FAF9F6] border-b border-slate-200/80 space-y-2">
            <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider block">
              Dev-only quick-login (never shipped to production):
            </span>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => {
                  setEmail('shopper@confit.io');
                  setPassword('Password123!');
                  switchView('signin');
                }}
                className="py-2 px-3 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-800 font-semibold hover:bg-[#FDF8EE] transition-all text-start truncate shadow-2xs"
              >
                👤 Fill shopper creds
              </button>
              <button
                type="button"
                onClick={() => {
                  setEmail('brand@massimodutti.com');
                  setPassword('Password123!');
                  switchView('signin');
                }}
                className="py-2 px-3 rounded-xl bg-white border border-slate-200 hover:border-[#C5A059] text-slate-800 font-semibold hover:bg-[#FDF8EE] transition-all text-start truncate shadow-2xs"
              >
                🏢 Fill brand creds
              </button>
            </div>
          </div>
        )}

        {/* ── MFA challenge (second step of signin) ─────────────────── */}
        {activeStep === 'mfa' && (
            <motion.form key="mfa" {...formMotion} onSubmit={handleMfaSubmit} className="p-6 space-y-4 text-xs">
              {/* Where should the second factor come from? The shopper
                  chooses: authenticator app (default) or a one-time code
                  REALLY sent to their inbox. */}
              <div
                role="radiogroup"
                aria-label={t('auth.mfa_method_label')}
                className="relative grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1"
              >
                {(['app', 'email'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={mfaMethod === m}
                    onClick={() => { setMfaMethod(m); resetError(); }}
                    className={`relative min-h-9 rounded-lg px-2 font-bold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] ${
                      mfaMethod === m ? 'text-[#1B1F3B]' : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    {mfaMethod === m && (
                      <motion.span
                        layoutId="mfa-method-pill"
                        aria-hidden="true"
                        transition={reduceMotion ? { duration: 0 } : { type: 'tween', duration: 0.18, ease: 'easeOut' }}
                        className="absolute inset-0 rounded-lg bg-white shadow-sm"
                      />
                    )}
                    <span className="relative">
                      {m === 'app' ? t('auth.mfa_method_app') : t('auth.mfa_method_email')}
                    </span>
                  </button>
                ))}
              </div>

              <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs">
                {mfaMethod === 'app' ? t('auth.mfa_instructions') : t('auth.mfa_instructions_email')}
              </div>

              {mfaMethod === 'email' && (
                <div className="space-y-2">
                  {emailCodePhase !== 'sent' && (
                    <button
                      type="button"
                      onClick={handleSendEmailCode}
                      disabled={emailCodePhase === 'sending'}
                      aria-busy={emailCodePhase === 'sending'}
                      className="w-full min-h-10 rounded-xl border border-[#C5A059]/60 bg-[#FDF8EE] px-4 font-bold text-[#1B1F3B] hover:border-[#A37E44] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] disabled:opacity-60"
                    >
                      {emailCodePhase === 'sending' ? t('auth.mfa_email_sending') : t('auth.mfa_email_send')}
                    </button>
                  )}
                  <div role="status" aria-live="polite">
                    {emailCodePhase === 'sent' && emailCodeInfo && (
                      <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 space-y-1.5">
                        <p className="font-medium">
                          {t('auth.mfa_email_sent_to', { email: emailCodeInfo.sentTo, minutes: emailCodeInfo.minutes })}
                        </p>
                        <button
                          type="button"
                          onClick={handleSendEmailCode}
                          disabled={resendIn > 0}
                          className="font-bold text-emerald-900 underline-offset-2 hover:underline disabled:no-underline disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] rounded"
                        >
                          {resendIn > 0
                            ? t('auth.mfa_email_resend_in', { seconds: resendIn })
                            : t('auth.mfa_email_resend')}
                        </button>
                      </div>
                    )}
                    {emailCodePhase === 'failed' && emailCodeError && (
                      <p className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">
                        {emailCodeError}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {displayError && (
                <div role="alert" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">
                  {displayError}
                </div>
              )}
              <div>
                <label htmlFor="auth-mfa-code" className="font-bold text-slate-700 block mb-1">
                  {mfaMethod === 'app' ? t('auth.mfa_code_label') : t('auth.mfa_email_code_label')}
                </label>
                {/* Codes stay LTR in the Arabic page — they are tokens. */}
                <input
                  id="auth-mfa-code"
                  type="text"
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  inputMode={mfaMethod === 'email' ? 'numeric' : undefined}
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder={mfaMethod === 'app' ? '123456 / CONFIT-XXXX-XXXX' : '123456'}
                  dir="ltr"
                  className={`${inputClass} font-mono tracking-wider`}
                />
              </div>
              <button type="submit" disabled={isLoading} aria-busy={isLoading} className={primaryButtonClass}>
                {isLoading ? t('auth.verifying') : t('auth.verify_sign_in')}
              </button>
            </motion.form>
          )}

          {/* ── Forgot password ───────────────────────────────────────── */}
          {activeStep === 'forgot' && (
            <motion.form key="forgot" {...formMotion} onSubmit={handleForgotSubmit} className="p-6 space-y-4 text-xs">
              {forgotPhase === 'sent' ? (
                <div role="status" className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800">
                  {/* Fixed, non-committal — identical whether or not the
                      account exists (no email-existence side channel). */}
                  {t('auth.forgot_sent')}
                </div>
              ) : (
                <>
                  <p className="text-slate-600">{t('auth.forgot_intro')}</p>
                  {forgotPhase === 'unconfigured' && (
                    <div role="alert" className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800">
                      {t('auth.forgot_unconfigured')}
                    </div>
                  )}
                  {forgotPhase === 'error' && (
                    <div role="alert" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">
                      {t('auth.forgot_failed')}
                    </div>
                  )}
                  <div>
                    <label htmlFor="auth-forgot-email" className="font-bold text-slate-700 block mb-1">
                      {t('auth.email_label')}
                    </label>
                    <input
                      id="auth-forgot-email"
                      type="email"
                      required
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="name@example.com"
                      dir="ltr"
                      className={inputClass}
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={forgotPhase === 'pending'}
                    aria-busy={forgotPhase === 'pending'}
                    className={primaryButtonClass}
                  >
                    {forgotPhase === 'pending' ? t('auth.sending') : t('auth.send_reset_link')}
                  </button>
                </>
              )}
              <div className="text-center pt-2 text-slate-500">
                <button
                  type="button"
                  onClick={() => switchView('signin')}
                  className="min-h-[44px] px-2 text-[#C5A059] font-bold hover:underline"
                >
                  {t('auth.back_to_signin')}
                </button>
              </div>
            </motion.form>
          )}

          {/* ── Sign in / Create account ──────────────────────────────── */}
          {(activeStep === 'signin' || activeStep === 'signup') && (
            <motion.form key={view} {...formMotion} onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
              {displayError && (
                <div role="alert" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 font-medium">
                  {displayError}
                </div>
              )}

              {view === 'signup' && (
                <div>
                  <label htmlFor="auth-full-name" className="font-bold text-slate-700 block mb-1">
                    {t('auth.full_name_label')}
                  </label>
                  <input
                    id="auth-full-name"
                    type="text"
                    required
                    autoComplete="name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder={t('auth.full_name_placeholder')}
                    className={inputClass}
                  />
                </div>
              )}

              <div>
                <label htmlFor="auth-email" className="font-bold text-slate-700 block mb-1">
                  {t('auth.email_label')}
                </label>
                <input
                  id="auth-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  dir="ltr"
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="auth-password" className="font-bold text-slate-700 block mb-1">
                  {t('auth.password_label')}
                </label>
                <div className="relative">
                  <input
                    id="auth-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    autoComplete={view === 'signup' ? 'new-password' : 'current-password'}
                    minLength={view === 'signup' ? 8 : undefined}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={view === 'signup' ? t('auth.password_placeholder_new') : '••••••••'}
                    className={`${inputClass} pe-11`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? t('reset_password.hide_password') : t('reset_password.show_password')}
                    aria-pressed={showPassword}
                    className="absolute end-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 transition-colors duration-300 ease-luxury hover:text-[#1B1F3B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
                  >
                    <span aria-hidden="true">{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</span>
                  </button>
                </div>
                {view === 'signup' && (
                  /* LIVE mirror of the server's policy — the same component
                     the reset page uses. Guidance only: the submit stays
                     enabled and the server stays the authority. */
                  <PasswordPolicyChecklist password={password} className="mt-2" />
                )}
              </div>

              {view === 'signup' && (
                <div>
                  <label htmlFor="auth-phone" className="font-bold text-slate-700 block mb-1">
                    {t('auth.phone_label')}
                  </label>
                  <input
                    id="auth-phone"
                    type="tel"
                    autoComplete="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+971 50 123 4567"
                    dir="ltr"
                    className={inputClass}
                  />
                </div>
              )}

              <button type="submit" disabled={isLoading} aria-busy={isLoading} className={primaryButtonClass}>
                {/* Decorative: aria-hidden keeps the accessible name equal to
                    the visible label ("Sign in"), not "User Account Sign in". */}
                <span aria-hidden="true">
                  <UserIcon size={14} color="#FFFFFF" />
                </span>
                <span>
                  {isLoading
                    ? t('auth.processing')
                    : view === 'signin'
                      ? t('auth.sign_in')
                      : t('auth.create_account')}
                </span>
              </button>

              {view === 'signin' && (
                <div className="text-center text-slate-500">
                  <button
                    type="button"
                    onClick={() => switchView('forgot')}
                    className="min-h-[44px] px-2 text-[#C5A059] font-bold hover:underline"
                  >
                    {t('auth.forgot_link')}
                  </button>
                </div>
              )}

              <div className="text-center pt-2 text-slate-500">
                {view === 'signin' ? (
                  <span>
                    {t('auth.new_to_confit')}{' '}
                    <button
                      type="button"
                      onClick={() => switchView('signup')}
                      className="min-h-[44px] px-2 text-[#C5A059] font-bold hover:underline"
                    >
                      {t('auth.create_account')}
                    </button>
                  </span>
                ) : (
                  <span>
                    {t('auth.already_have_account')}{' '}
                    <button
                      type="button"
                      onClick={() => switchView('signin')}
                      className="min-h-[44px] px-2 text-[#C5A059] font-bold hover:underline"
                    >
                      {t('auth.sign_in')}
                    </button>
                  </span>
                )}
              </div>
            </motion.form>
          )}
      </motion.div>
    </div>
  );
};
