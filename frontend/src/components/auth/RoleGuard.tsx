import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { ConfitLogo } from '../common/ConfitLogo';
import { LockIcon, UserIcon, ShieldIcon } from '../icons/ConfitIcons';
import { brandService } from '../../services/apiServices';
import { useTranslation } from 'react-i18next';

const BRAND_ROLES = ['brand_owner', 'brand_manager', 'brand_staff'];

interface RoleGuardProps {
  allowedRoles?: string[];
  children?: React.ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

const PartnerRequestDemoForm: React.FC = () => {
  const [form, setForm] = React.useState({
    company_name: "",
    contact_name: "",
    work_email: "",
    website: "",
    monthly_order_volume: "",
    message: "",
  });
  const [status, setStatus] = React.useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const update =
    (key: keyof typeof form) =>
    (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >,
    ) => {
      setForm((prev) => ({ ...prev, [key]: e.target.value }));
    };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setStatus(null);
    try {
      const res = await brandService.requestDemo({
        ...form,
        source_path: "/b2b",
      });
      setStatus({
        type: "success",
        text: res.duplicate
          ? "We already have a recent request for this email; the saved lead has been linked for review."
          : res.message,
      });
      setForm({
        company_name: "",
        contact_name: "",
        work_email: "",
        website: "",
        monthly_order_volume: "",
        message: "",
      });
    } catch (err: any) {
      setStatus({
        type: "error",
        text:
          err?.message ||
          "Could not submit the request. Please check the fields and try again.",
      });
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <form
      onSubmit={submit}
      className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm space-y-4"
      aria-label="Request a partner demo"
    >
      <div>
        <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
          Request a partner demo
        </h3>
        <p className="mt-1 text-xs text-slate-500">
          Submissions are persisted for CONFIT review. No partner account or CRM
          success is fabricated.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          required
          value={form.company_name}
          onChange={update("company_name")}
          placeholder="Company name"
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          required
          value={form.contact_name}
          onChange={update("contact_name")}
          placeholder="Contact name"
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          required
          type="email"
          value={form.work_email}
          onChange={update("work_email")}
          placeholder="Work email"
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          value={form.website}
          onChange={update("website")}
          placeholder="Website (optional)"
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <select
          aria-label="Monthly online orders"
          value={form.monthly_order_volume}
          onChange={update("monthly_order_volume")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm sm:col-span-2"
        >
          <option value="">Monthly online orders (optional)</option>
          <option value="under_500">Under 500</option>
          <option value="500_5000">500–5,000</option>
          <option value="5000_plus">5,000+</option>
        </select>
      </div>
      <textarea
        value={form.message}
        onChange={update("message")}
        placeholder="What would you like to evaluate?"
        rows={3}
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
      />
      {status && (
        <div
          role="status"
          className={`rounded-xl p-3 text-xs ${status.type === "success" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-700"}`}
        >
          {status.text}
        </div>
      )}
      <button
        disabled={submitting}
        className="rounded-2xl bg-[#1B1F3B] px-5 py-3 text-xs font-bold uppercase tracking-wider text-white transition hover:bg-slate-800 disabled:opacity-60"
      >
        {submitting ? "Submitting…" : "Submit real request"}
      </button>
    </form>
  );
};

export const RoleGuard: React.FC<RoleGuardProps> = ({
  allowedRoles,
  children,
  fallbackTitle,
  fallbackMessage,
}) => {
  const location = useLocation();
  const { user, isAuthenticated, hasAttemptedBootstrap } = useAuthStore();
  const { openAuthModal } = useUIStore();
  const { t } = useTranslation();

  // 0. AUTH-02 FIX: session bootstrap is in flight — we do not yet know
  // whether the visitor holds a valid httpOnly session. Rendering the guest
  // gate here would flash an auth wall before fetchMe() resolves.
  if (!hasAttemptedBootstrap) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4" role="status" aria-live="polite">
        <div className="flex flex-col items-center gap-4 text-slate-400">
          <div className="w-10 h-10 rounded-full border-2 border-[#C5A059]/30 border-t-[#C5A059] animate-spin" />
          <span className="text-[11px] tracking-widest uppercase font-semibold">
            Verifying your session…
          </span>
        </div>
      </div>
    );
  }

  // 1. Not Authenticated -> Show public partner value page for merchant routes, otherwise auth gate.
  if (!isAuthenticated || !user) {
    const isPartnerPortal = (fallbackTitle || '').toLowerCase().includes('brand') ||
      (fallbackTitle || '').toLowerCase().includes('partner');

    if (isPartnerPortal) {
      return (
        <main className="min-h-[80vh] px-4 py-10">
          <div className="mx-auto max-w-6xl space-y-8">
            <section className="overflow-hidden rounded-[36px] border border-[#C5A059]/30 bg-[#0C0E1E] p-6 text-white shadow-2xl sm:p-10 lg:p-14">
              <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
                <div className="space-y-5">
                  <ConfitLogo variant="full" theme="light" size="lg" />
                  <span className="inline-flex rounded-full border border-[#C5A059]/40 bg-[#C5A059]/15 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[#E2BF70]">
                    Public Partner Portal
                  </span>
                  <h1 className="font-serif text-4xl font-bold leading-tight sm:text-5xl">
                    Reduce fit uncertainty before shoppers reach checkout.
                  </h1>
                  <p className="max-w-2xl text-sm font-light leading-relaxed text-slate-300">
                    CONFIT connects premium catalog ingestion, fit intelligence, and virtual try-on workflows so brand teams can understand the partner workflow before signing in.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <button
                      onClick={() => openAuthModal('register')}
                      className="rounded-2xl bg-[#C5A059] px-5 py-3 text-xs font-bold uppercase tracking-wider text-[#0C0E1E] transition hover:bg-[#E2BF70]"
                    >
                      Create partner account
                    </button>
                    <button
                      onClick={() => openAuthModal('login')}
                      className="rounded-2xl border border-white/20 bg-white/10 px-5 py-3 text-xs font-bold uppercase tracking-wider text-white transition hover:bg-white/20"
                    >
                      Existing partner sign in
                    </button>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    ['Catalog ingestion', 'Validate imagery, attributes, SKU availability, and try-on readiness before publishing.'],
                    ['Fit intelligence', 'Expose supported categories, measurement confidence, and return-risk signals.'],
                    ['Virtual try-on', 'Give shoppers an honest visual preview while keeping fit recommendations separate.'],
                    ['Operational clarity', 'Track pickup, inventory, placement, and analytics workflows from one portal.'],
                  ].map(([title, copy]) => (
                    <div key={title} className="rounded-3xl border border-white/10 bg-white/10 p-4 backdrop-blur">
                      <h2 className="font-serif text-lg font-bold text-white">{title}</h2>
                      <p className="mt-2 text-xs font-light leading-relaxed text-slate-300">{copy}</p>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <PartnerRequestDemoForm />

            <section className="grid gap-4 md:grid-cols-3">
              {[
                ['Merchant problem', 'Sizing uncertainty, low confidence, and unready product data create preventable friction.'],
                ['Launch path', 'Connect catalog, verify product metadata, then activate fit and try-on experiences by supported category.'],
                ['Proof readiness', 'Use real analytics only—views, try-ons, conversions, inventory, returns, and attribution are never fabricated.'],
              ].map(([title, copy]) => (
                <div key={title} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-2xs">
                  <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">{title}</h2>
                  <p className="mt-2 text-sm font-light leading-relaxed text-slate-500">{copy}</p>
                </div>
              ))}
            </section>
          </div>
        </main>
      );
    }

    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#0C0E1E] text-white border border-[#C5A059]/40 rounded-3xl p-8 shadow-2xl text-center space-y-6 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-16 h-16 rounded-2xl bg-[#1B1F3B] border border-[#C5A059]/50 mx-auto flex items-center justify-center text-[#C5A059] shadow-lg">
            <LockIcon size={32} color="#C5A059" />
          </div>
          <div className="space-y-2">
            <span className="text-[10px] font-bold tracking-widest text-[#C5A059] uppercase">
              {t('auth.gate_eyebrow')}
            </span>
            <h2 className="font-serif text-2xl font-bold text-white">
              {fallbackTitle || t('auth.authentication_required')}
            </h2>
            <p className="text-xs text-slate-400 font-light leading-relaxed">
              {fallbackMessage || t('auth.gate_401_body')}
            </p>
          </div>
          <div className="space-y-3 pt-2">
            <button
              onClick={() => openAuthModal('login')}
              className="w-full py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <UserIcon size={16} color="#0C0E1E" />
              <span>{t('auth.sign_in_to_continue')}</span>
            </button>
            <button
              onClick={() => openAuthModal('register')}
              className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-semibold text-xs border border-slate-700 transition-all"
            >
              {t('auth.create_account')}
            </button>
            <div className="pt-2">
              <Link to="/" className="text-[11px] text-slate-400 hover:text-[#C5A059] transition-colors inline-block">
                ← {t('auth.return_storefront')}
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const userRole = user.role?.toLowerCase();
  const hasRole = !allowedRoles || allowedRoles.includes(userRole) || userRole === 'admin';
  // Authorization itself is unchanged and stays server-side: this only decides
  // what the SPA renders. A forged local role never reaches the guarded area.
  if (hasRole) return <>{children}</>;

  // 3. Authenticated but not authorized — render the REAL state and the way out.
  const state = user.onboarding;
  const accountState = state?.account_state;
  const partnerAccess = user.partner_access ?? state?.partner_access ?? 'none';
  const adminOnly = (allowedRoles || []).length === 1 && allowedRoles?.[0] === 'admin';
  const isBrandArea = !adminOnly && (allowedRoles || []).some((r) => BRAND_ROLES.includes(r));

  let headlineEn = 'Access Restricted';
  let reasonEn = t('auth.gate_403_generic');
  let primary: { label: string; to: string } | null = null;
  let secondary: { label: string; to: string } | null = null;

  if (accountState === 'SUSPENDED' || user.is_active === false) {
    headlineEn = t('auth.account_suspended');
    reasonEn = t('auth.gate_suspended_body');
  } else if (isBrandArea && partnerAccess === 'pending') {
    headlineEn = t('auth.partner_review_in_progress');
    reasonEn = t('auth.gate_pending_body');
    primary = { label: t('auth.view_application_status'), to: '/partner/status' };
  } else if (isBrandArea && partnerAccess === 'rejected') {
    headlineEn = t('auth.partner_application_rejected');
    reasonEn = t('auth.gate_rejected_body');
    primary = { label: t('auth.apply_again'), to: '/partner/apply' };
  } else if (isBrandArea && (accountState === 'EMAIL_VERIFICATION_REQUIRED' || user.is_verified === false)) {
    headlineEn = t('auth.verify_email_first');
    reasonEn = t('auth.gate_verify_body');
    primary = { label: t('auth.verify_email'), to: '/verify-email' };
  } else if (isBrandArea) {
    headlineEn = t('auth.partner_access_not_enabled');
    reasonEn = t('auth.gate_apply_body');
    primary = { label: t('auth.apply_for_partner_access'), to: '/partner/apply' };
  } else if (adminOnly) {
    reasonEn = t('auth.gate_admin_body');
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-[#0C0E1E] text-white border border-amber-500/30 rounded-3xl p-8 shadow-2xl text-center space-y-6 animate-in fade-in duration-200">
        <div className="w-16 h-16 rounded-2xl bg-amber-950/40 border border-amber-500/40 mx-auto flex items-center justify-center">
          <ShieldIcon size={32} color="#F59E0B" />
        </div>
        <div className="space-y-2">
          <span className="text-[10px] font-bold tracking-widest text-amber-400 uppercase">
            {partnerAccess === 'pending' ? t('auth.status_pending') : '403 · ' + t('auth.role_restriction')}
          </span>
          <h2 className="font-serif text-2xl font-bold text-white">{headlineEn}</h2>
          <p className="text-xs text-slate-400 font-light leading-relaxed">{reasonEn}</p>
          <p className="text-[11px] text-slate-500">
            {t('auth.signed_in_as')} <strong className="text-slate-300">{user.email}</strong> · {t('auth.current_role')}{' '}
            <span className="px-2 py-0.5 rounded bg-slate-800 text-[#C5A059] font-mono text-[11px]">{user.role}</span>
          </p>
        </div>
        <div className="space-y-3 pt-2">
          {primary && (
            <Link
              to={primary.to}
              className="w-full py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs tracking-wider uppercase shadow-md transition-all flex items-center justify-center"
            >
              {primary.label}
            </Link>
          )}
          {secondary && (
            <Link
              to={secondary.to}
              className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-semibold text-xs border border-slate-700 transition-all flex items-center justify-center"
            >
              {secondary.label}
            </Link>
          )}
          <Link
            to="/"
            className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-bold text-xs border border-slate-700 tracking-wider uppercase shadow-md transition-all flex items-center justify-center"
          >
            ← {t('auth.return_storefront')}
          </Link>
          <button
            onClick={() => openAuthModal('login')}
            className="w-full py-2.5 rounded-xl text-xs text-[#C5A059] hover:underline"
          >
            {t('auth.switch_account')}
          </button>
        </div>
      </div>
    </div>
  );
};

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return <RoleGuard>{children}</RoleGuard>;
};
