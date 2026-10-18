import React, { useEffect } from "react";
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
   * Which trust domain this guard protects (spec 05 §6.5).
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
  const { user, isAuthenticated, hasAttemptedBootstrap, brandMemberships,
          brandMembershipsStatus, loadBrandMemberships } = useAuthStore();
  const { openAuthModal } = useUIStore();

  // BRD-02: partner-portal admission is TENANT-aware. Members whose global
  // role is still 'consumer' (by design — joining a brand never promotes
  // users.role) enter through their server-resolved active memberships.
  const isPartnerPortalEarly =
    portal === 'partner' ||
    (!portal &&
      ((fallbackTitle || '').toLowerCase().includes('brand') ||
       (fallbackTitle || '').toLowerCase().includes('partner')));
  useEffect(() => {
    if (isAuthenticated && isPartnerPortalEarly && brandMemberships === null
        && brandMembershipsStatus === 'idle') {
      void loadBrandMemberships();
    }
  }, [isAuthenticated, isPartnerPortalEarly, brandMemberships, brandMembershipsStatus, loadBrandMemberships]);

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
        <div className="flex flex-col items-center gap-4 text-brand-muted">
          <div className="w-10 h-10 rounded-full border-2 border-brand-hairline border-t-brand-charcoal motion-safe:animate-spin" aria-hidden="true" />
          <span className="text-[11px] tracking-widest uppercase font-semibold text-brand-muted">
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
  const isPartnerMember = Boolean(brandMemberships && brandMemberships.length > 0);
  const needsPartnerOnboarding =
    isPartnerPortal && user?.role === 'consumer' && !isPartnerMember;
  // A consumer at the portal door while their membership list is still
  // resolving: honest pending state, never a premature wall.
  if (isPartnerPortal && isAuthenticated && user?.role === 'consumer' && !isPartnerMember
      && (brandMembershipsStatus === 'loading' || brandMembershipsStatus === 'idle')) {
    return (
      <div
        className="min-h-[70vh] flex items-center justify-center p-4"
        role="status"
        aria-live="polite"
      >
        <div className="flex flex-col items-center gap-4 text-brand-muted">
          <div className="w-10 h-10 rounded-full border-2 border-brand-hairline border-t-brand-charcoal motion-safe:animate-spin" aria-hidden="true" />
          <span className="text-[11px] tracking-widest uppercase font-semibold text-brand-muted">
            {t('guard.verifying_session')}
          </span>
        </div>
      </div>
    );
  }
  // Public onboarding never grants a role; logged-in consumers see it too.
  if (!isAuthenticated || !user || needsPartnerOnboarding) {
    if (isPartnerPortal) {
      return <PartnerGatewayView />;
    }

    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white text-brand-charcoal border border-brand-hairline rounded-3xl p-8 shadow-xs text-center space-y-6">
          {/* Official mark: the admin sign-in gate was the only portal entry
              without the Logo #3 identity (the partner gate already shows it). */}
          <div className="flex justify-center">
            <ConfitLogo variant="compact" size="sm" />
          </div>
          <div className="w-16 h-16 rounded-2xl bg-brand-wash border border-brand-hairline mx-auto flex items-center justify-center text-brand-charcoal shadow-2xs">
            <LockIcon size={32} color="#252729" />
          </div>

          <div className="space-y-2">
            <span className="text-[10px] font-bold tracking-widest text-brand-muted uppercase">
              {t('partner.governance_label')}
            </span>
            <h2 className="font-serif text-2xl font-bold text-brand-charcoal">
              {fallbackTitle || t('partner.auth_required')}
            </h2>
            <p className="text-xs text-brand-muted font-light leading-relaxed">
              {fallbackMessage || t('partner.auth_required_body')}
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <button data-motion="auth"
              onClick={() => openAuthModal("login")}
              className="w-full min-h-[48px] py-3.5 rounded-xl bg-brand-charcoal hover:bg-black text-white font-bold text-xs tracking-wider uppercase shadow-xs transition-all flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
            >
              <span aria-hidden="true"><UserIcon size={16} color="#FFFFFF" /></span>
              <span>{t('partner.sign_in_to_continue')}</span>
            </button>

            <button data-motion="auth"
              onClick={() => openAuthModal("register")}
              className="w-full min-h-[48px] py-3 rounded-xl bg-white hover:bg-brand-wash text-brand-charcoal font-semibold text-xs border border-brand-field transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
            >
              {t('partner.create_account')}
            </button>

            <div className="pt-2">
              <Link
                to="/"
                className="text-[11px] text-brand-muted hover:text-brand-charcoal underline-offset-2 hover:underline transition-colors inline-flex min-h-11 items-center px-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
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
    !allowedRoles ||
    allowedRoles.includes(userRole) ||
    userRole === "admin" ||
    // Tenant members of THIS brand pass the partner-portal gate by their
    // server-verified membership (never by anything the client asserts).
    (isPartnerPortal && isPartnerMember);

  if (!hasRole) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white text-brand-charcoal border border-rose-200 rounded-3xl p-8 shadow-xs text-center space-y-6">
          {/* Same Logo #3 identity as the sign-in gate above: a refusal is
              still a CONFIT surface, not an anonymous error box. */}
          <div className="flex justify-center">
            <ConfitLogo variant="compact" size="sm" />
          </div>
          <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-200 mx-auto flex items-center justify-center text-rose-600 shadow-2xs">
            <ShieldIcon size={32} color="#E11D48" />
          </div>

          <div className="space-y-2">
            {/* State is text, not colour alone: the badge names the refusal. */}
            <span className="text-[10px] font-bold tracking-widest text-rose-600 uppercase">
              {t('guard.forbidden_badge')}
            </span>
            <h2 className="font-serif text-2xl font-bold text-brand-charcoal">
              {t('guard.access_restricted')}
            </h2>
            <p className="text-xs text-brand-muted font-light leading-relaxed">
              {t('guard.registered_as')}{' '}
              {/* Email and role codes are Latin identifiers — keep them LTR
                  inside the Arabic sentence (spec §7). */}
              <strong className="text-brand-charcoal" dir="ltr">{user.email}</strong>
              {' · '}
              <span className="px-2 py-0.5 rounded bg-brand-wash text-brand-charcoal font-mono text-[11px] border border-brand-hairline" dir="ltr">
                {user.role}
              </span>
              {'. '}
              {t('guard.requires_roles')}{' '}
              <span className="text-brand-charcoal font-medium" dir="ltr">
                {allowedRoles?.join(', ')}
              </span>
              .
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <Link
              to="/"
              className="w-full min-h-[48px] py-3.5 rounded-xl bg-brand-charcoal hover:bg-black text-white font-bold text-xs tracking-wider uppercase shadow-xs transition-all flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
            >
              <span>{t('guard.return_storefront')}</span>
            </Link>

            <button data-motion="auth" data-motion-tone="edge"
              onClick={() => openAuthModal("login")}
              className="w-full min-h-[48px] py-2.5 rounded-xl text-xs text-brand-muted hover:text-brand-charcoal hover:underline"
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
