import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuthStore } from "../../stores/authStore";
import { useUIStore } from "../../stores/uiStore";
import { ConfitLogo } from "../common/ConfitLogo";
import { LockIcon, UserIcon, ShieldIcon } from "../icons/ConfitIcons";
import { useTranslation } from "react-i18next";
import { PartnerGatewayView } from "../../views/b2b/PartnerGatewayView";

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
          <div className="w-10 h-10 rounded-full border-2 border-[#B8935A]/30 border-t-[#B8935A] motion-safe:animate-spin" aria-hidden="true" />
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
      // The public partner gateway is its own view, not a branch of a route
      // guard. Keeping a 300-line marketing surface plus a lead-capture form
      // inside this file is what put the conversion action third in the DOM
      // and stacked three identical grids: the layout was shaped by where the
      // code happened to live. The guard now owns the decision only.
      return <PartnerGatewayView />;
    }

    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-[#0C0E1E] text-white border border-[#B8935A]/40 rounded-3xl p-8 shadow-2xl text-center space-y-6 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-16 h-16 rounded-2xl bg-[#1B1F3B] border border-[#B8935A]/50 mx-auto flex items-center justify-center text-[#B8935A] shadow-lg">
            <LockIcon size={32} color="#B8935A" />
          </div>

          <div className="space-y-2">
            <span className="text-[10px] font-bold tracking-widest text-[#B8935A] uppercase">
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
              className="w-full min-h-[48px] py-3.5 rounded-xl bg-[#B8935A] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <span aria-hidden="true"><UserIcon size={16} color="#0C0E1E" /></span>
              <span>{t('partner.sign_in_to_continue')}</span>
            </button>

            <button
              onClick={() => openAuthModal("register")}
              className="w-full min-h-[48px] py-3 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-semibold text-xs border border-slate-700 transition-all"
            >
              {t('partner.create_account')}
            </button>

            <div className="pt-2">
              <Link
                to="/"
                className="text-[11px] text-slate-400 hover:text-[#B8935A] transition-colors inline-block"
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
              <span className="px-2 py-0.5 rounded bg-slate-800 text-[#B8935A] font-mono text-[11px]" dir="ltr">
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
              className="w-full min-h-[48px] py-3.5 rounded-xl bg-[#1B1F3B] hover:bg-slate-800 text-white font-bold text-xs border border-slate-700 tracking-wider uppercase shadow-md transition-all flex items-center justify-center gap-2"
            >
              <span>{t('guard.return_storefront')}</span>
            </Link>

            <button
              onClick={() => openAuthModal("login")}
              className="w-full min-h-[48px] py-2.5 rounded-xl text-xs text-[#B8935A] hover:underline"
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
