import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuthStore } from "../../stores/authStore";
import { useUIStore } from "../../stores/uiStore";
import { ConfitLogo } from "../common/ConfitLogo";
import { LockIcon, UserIcon, ShieldIcon } from "../icons/ConfitIcons";
import { useTranslation } from "react-i18next";
import { brandService } from "../../services/apiServices";

export const PartnerRequestDemoForm: React.FC = () => {
  const { t } = useTranslation();
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
          ? t('partner.duplicate_request')
          : // An upstream server message cannot be translated client-side; it is
            // shown verbatim rather than replaced with an invented confirmation.
            res.message,
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
        text: err?.message || t('partner.submit_failed'),
      });
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <form
      onSubmit={submit}
      className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm space-y-4"
      id="partner-request"
      aria-label={t('partner.form_label')}
    >
      <div>
        <h3 className="font-serif text-xl font-bold text-[#1B1F3B]">
          {t('partner.form_title')}
        </h3>
        <p className="mt-1 text-xs text-slate-500">
          {t('partner.form_note')}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          required
          value={form.company_name}
          onChange={update("company_name")}
          aria-label={t('partner.field_company')}
          placeholder={t('partner.field_company')}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          required
          value={form.contact_name}
          onChange={update("contact_name")}
          aria-label={t('partner.field_contact')}
          placeholder={t('partner.field_contact')}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          required
          type="email"
          value={form.work_email}
          onChange={update("work_email")}
          aria-label={t('partner.field_email')}
          placeholder={t('partner.field_email')}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          value={form.website}
          onChange={update("website")}
          aria-label={t('partner.field_website')}
          placeholder={t('partner.field_website')}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
        />
        <select
          aria-label={t('partner.field_volume')}
          value={form.monthly_order_volume}
          onChange={update("monthly_order_volume")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm sm:col-span-2"
        >
          <option value="">{t('partner.volume_placeholder')}</option>
          <option value="under_500">{t('partner.volume_under_500')}</option>
          <option value="500_5000">{t('partner.volume_500_5000')}</option>
          <option value="5000_plus">{t('partner.volume_5000_plus')}</option>
        </select>
      </div>
      <textarea
        value={form.message}
        onChange={update("message")}
        placeholder={t('partner.field_message')}
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
        {submitting ? t('partner.submitting') : t('partner.submit')}
      </button>
    </form>
  );
};

interface RoleGuardProps {
  allowedRoles?: string[];
  children?: React.ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
  /**
   * Which trust domain this guard protects (spec 05 §6.5). Previously the
   * partner-portal experience was selected by SNIFFING the English
   * `fallbackTitle` for the words "brand"/"partner" — a translated or
   * reworded title silently swapped the partner onboarding page for the
   * generic auth wall. The domain is now declared, not inferred.
   */
  portal?: 'partner' | 'admin';
}

export const RoleGuard: React.FC<RoleGuardProps> = ({
  allowedRoles,
  children,
  fallbackTitle,
  fallbackMessage,
  portal,
}) => {
  const { t } = useTranslation();
  const location = useLocation();
  const { user, isAuthenticated, hasAttemptedBootstrap } = useAuthStore();
  const { openAuthModal } = useUIStore();

  // 0. AUTH-02 FIX: session bootstrap is in flight — we do not yet know
  // whether the visitor holds a valid httpOnly session. Rendering the guest
  // gate here would flash an auth wall before fetchMe() resolves.
  if (!hasAttemptedBootstrap) {
    return (
      <div
        className="min-h-[70vh] flex items-center justify-center p-4"
        role="status"
        aria-live="polite"
      >
        <div className="flex flex-col items-center gap-4 text-slate-400">
          <div className="w-10 h-10 rounded-full border-2 border-[#C5A059]/30 border-t-[#C5A059] motion-safe:animate-spin" aria-hidden="true" />
          <span className="text-[11px] tracking-widest uppercase font-semibold">
            {t('guard.verifying_session')}
          </span>
        </div>
      </div>
    );
  }

  // Explicit domain declaration, with the legacy title-sniff kept ONLY as a
  // fallback for any call site not yet passing `portal`.
  const isPartnerPortal =
    portal === 'partner' ||
    (!portal &&
      ((fallbackTitle || '').toLowerCase().includes('brand') ||
        (fallbackTitle || '').toLowerCase().includes('partner')));
  const needsPartnerOnboarding = isPartnerPortal && user?.role === 'consumer';
  // Public onboarding never grants a role; logged-in consumers see it too.
  if (!isAuthenticated || !user || needsPartnerOnboarding) {

    if (isPartnerPortal) {
      return (
        <main className="min-h-[80vh] px-4 py-10">
          <div className="mx-auto max-w-6xl space-y-8">
            <section className="overflow-hidden rounded-[36px] border border-[#C5A059]/30 bg-[#0C0E1E] p-6 text-white shadow-2xl sm:p-10 lg:p-14">
              <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
                <div className="space-y-5">
                  <ConfitLogo variant="full" theme="light" size="lg" />
                  <span className="inline-flex rounded-full border border-[#C5A059]/40 bg-[#C5A059]/15 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[#E2BF70]">
                    {t('partner.portal_badge')}
                  </span>
                  <h1 className="font-serif text-4xl font-bold leading-tight sm:text-5xl">
                    {t('partner.hero_title')}
                  </h1>
                  <p className="max-w-2xl text-sm font-light leading-relaxed text-slate-300">
                    {t('partner.hero_body')}
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <button
                      onClick={() => document.getElementById('partner-request')?.scrollIntoView({ behavior: 'smooth' })}
                      className="min-h-11 rounded-2xl bg-[#C5A059] px-5 py-3 text-xs font-bold uppercase tracking-wider text-[#0C0E1E] transition hover:bg-[#E2BF70]"
                    >
                      {t('partner.request_partnership')}
                    </button>
                    <button
                      onClick={() => openAuthModal("login")}
                      className="min-h-11 rounded-2xl border border-white/20 bg-white/10 px-5 py-3 text-xs font-bold uppercase tracking-wider text-white transition hover:bg-white/20"
                    >
                      {t('partner.existing_sign_in')}
                    </button>
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    [t('partner.feat_catalog_title'), t('partner.feat_catalog_copy')],
                    [t('partner.feat_fit_title'), t('partner.feat_fit_copy')],
                    [t('partner.feat_tryon_title'), t('partner.feat_tryon_copy')],
                    [t('partner.feat_ops_title'), t('partner.feat_ops_copy')],
                  ].map(([title, copy]) => (
                    <div
                      key={title}
                      className="rounded-3xl border border-white/10 bg-white/10 p-4 backdrop-blur"
                    >
                      <h2 className="font-serif text-lg font-bold text-white">
                        {title}
                      </h2>
                      <p className="mt-2 text-xs font-light leading-relaxed text-slate-300">
                        {copy}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <PartnerRequestDemoForm />

            <section className="grid gap-4 md:grid-cols-3">
              {[
                [t('partner.pillar_problem_title'), t('partner.pillar_problem_copy')],
                [t('partner.pillar_launch_title'), t('partner.pillar_launch_copy')],
                [t('partner.pillar_proof_title'), t('partner.pillar_proof_copy')],
              ].map(([title, copy]) => (
                <div
                  key={title}
                  className="rounded-3xl border border-slate-200 bg-white p-5 shadow-2xs"
                >
                  <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">
                    {title}
                  </h2>
                  <p className="mt-2 text-sm font-light leading-relaxed text-slate-500">
                    {copy}
                  </p>
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
              {t('partner.governance_label')}
            </span>
            <h2 className="font-serif text-2xl font-bold text-white">
              {fallbackTitle || t('partner.auth_required')}
            </h2>
            <p className="text-xs text-slate-400 font-light leading-relaxed">
              {fallbackMessage || t('partner.auth_required_body')}
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <button
              onClick={() => openAuthModal("login")}
              className="w-full py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <span aria-hidden="true"><UserIcon size={16} color="#0C0E1E" /></span>
              <span>{t('partner.sign_in_to_continue')}</span>
            </button>

            <button
              onClick={() => openAuthModal("register")}
              className="w-full py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-semibold text-xs border border-slate-700 transition-all"
            >
              {t('partner.create_account')}
            </button>

            <div className="pt-2">
              <Link
                to="/"
                className="text-[11px] text-slate-400 hover:text-[#C5A059] transition-colors inline-block"
              >
                {t('partner.return_to_storefront')}
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. Role Verification
  const userRole = user.role?.toLowerCase();
  const hasRole =
    !allowedRoles || allowedRoles.includes(userRole) || userRole === "admin";

  if (!hasRole) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#0C0E1E] text-white border border-rose-500/40 rounded-3xl p-8 shadow-2xl text-center space-y-6 animate-in fade-in duration-200">
          <div className="w-16 h-16 rounded-2xl bg-rose-950/60 border border-rose-500/50 mx-auto flex items-center justify-center text-rose-400 shadow-lg">
            <ShieldIcon size={32} color="#F43F5E" />
          </div>

          <div className="space-y-2">
            {/* State is text, not colour alone: the badge names the refusal. */}
            <span className="text-[10px] font-bold tracking-widest text-rose-400 uppercase">
              {t('guard.forbidden_badge')}
            </span>
            <h2 className="font-serif text-2xl font-bold text-white">
              {t('guard.access_restricted')}
            </h2>
            <p className="text-xs text-slate-400 font-light leading-relaxed">
              {t('guard.registered_as')}{' '}
              {/* Email and role codes are Latin identifiers — keep them LTR
                  inside the Arabic sentence (spec §7). */}
              <strong className="text-white" dir="ltr">{user.email}</strong>
              {' · '}
              <span className="px-2 py-0.5 rounded bg-slate-800 text-[#C5A059] font-mono text-[11px]" dir="ltr">
                {user.role}
              </span>
              {'. '}
              {t('guard.requires_roles')}{' '}
              <span className="text-slate-300 font-medium" dir="ltr">
                {allowedRoles?.join(', ')}
              </span>
              .
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <Link
              to="/"
              className="w-full min-h-11 py-3.5 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-bold text-xs border border-slate-700 tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <span>{t('guard.return_storefront')}</span>
            </Link>

            <button
              onClick={() => openAuthModal("login")}
              className="w-full min-h-11 py-2.5 rounded-xl text-xs text-[#C5A059] hover:underline"
            >
              {t('guard.switch_account')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 3. Authorized -> Render Protected Content
  return <>{children}</>;
};

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  return <RoleGuard>{children}</RoleGuard>;
};
