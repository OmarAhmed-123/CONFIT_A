import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConsumerLayout } from '../layouts/ConsumerLayout';
import { BrandLayout } from '../layouts/BrandLayout';
import { RoleGuard, ProtectedRoute } from '../components/auth/RoleGuard';
import { useAuthStore } from '../stores/authStore';

/**
 * OnboardingGate — first-run / post-auth routing, driven by the SERVER.
 *
 * 2026-09-19: the gate used to decide from `user.has_profile` alone, so the
 * SPA could not distinguish "email unverified", "partner application in
 * review" or "suspended" — and the only surface those states had was a
 * dead-end 403. It now consumes the state machine the backend computes
 * (`UserOut.onboarding`, served by GET /auth/onboarding-state) and:
 *
 *   - never guesses: without a server state it renders the route unchanged;
 *   - forces verification only where the backend already refuses the flow
 *     (brand/partner intent), never for a browsing shopper;
 *   - sends onboarding-incomplete consumers to the style wizard;
 *   - is idempotent (already on the target route -> no navigation) so a
 *     refresh, a slow bootstrap or an expired session cannot loop.
 */
const AUTH_FLOW_PATHS = [
  '/verify-email',
  '/forgot-password',
  '/reset-password',
  '/invite',
  '/partner',
  '/settings',
  '/profile',
  '/privacy',
  '/terms',
  '/gdpr',
];

const OnboardingGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, hasAttemptedBootstrap } = useAuthStore();
  const location = useLocation();

  if (!isAuthenticated || !user || !hasAttemptedBootstrap) return <>{children}</>;

  const state = user.onboarding;
  if (!state) return <>{children}</>;

  const here = location.pathname;
  const exempt = AUTH_FLOW_PATHS.some((p) => here === p || here.startsWith(p + '/'));
  if (exempt) return <>{children}</>;

  // Brand/partner intent needs a verified address before anything else can
  // proceed (the backend refuses the application with 403 otherwise).
  if (
    state.account_state === 'EMAIL_VERIFICATION_REQUIRED' &&
    state.registration_intent === 'brand_partner'
  ) {
    return <Navigate to="/verify-email" replace />;
  }

  const action = state.next_action;
  if (action?.type === 'complete_profile' && action.route && here !== action.route) {
    return <Navigate to={action.route} replace />;
  }

  return <>{children}</>;
};

// Consumer Views
import { HomeView } from '../views/consumer/HomeView';
import { DiscoverView } from '../views/consumer/DiscoverView';
import { OutfitBuilderView } from '../views/consumer/OutfitBuilderView';
import { TryOnFitView } from '../views/consumer/TryOnFitView';
import { FitFinderView } from '../views/consumer/FitFinderView';
import { WardrobeView } from '../views/consumer/WardrobeView';
import { ProductDetailView } from '../views/consumer/ProductDetailView';
import { CheckoutView } from '../views/consumer/CheckoutView';
import { OrderTrackingView } from '../views/consumer/OrderTrackingView';
import { UserProfileView } from '../views/consumer/UserProfileView';
import { SharedLookView } from '../views/public/SharedLookView';
import { PrivacyPolicyView, TermsOfServiceView, GdprView } from '../views/legal/LegalViews';

// B2B Views
import { BrandDashboardView } from '../views/b2b/BrandDashboardView';
import { BrandCatalogView } from '../views/b2b/BrandCatalogView';
import { BrandInventoryView } from '../views/b2b/BrandInventoryView';
import { BrandAnalyticsView } from '../views/b2b/BrandAnalyticsView';
import { BrandPlacementsView } from '../views/b2b/BrandPlacementsView';
import { AdminAnalyticsView } from '../views/b2b/AdminAnalyticsView';
import { AdminPartnersView } from '../views/b2b/AdminPartnersView';
import { BrandTeamView } from '../views/b2b/BrandTeamView';

// Auth lifecycle flows (public — a reset/verify link must work signed out)
import { VerifyEmailView } from '../views/auth/VerifyEmailView';
import { ForgotPasswordView } from '../views/auth/ForgotPasswordView';
import { ResetPasswordView } from '../views/auth/ResetPasswordView';
import { InviteAcceptView } from '../views/auth/InviteAcceptView';
import { EmailChangeConfirmView } from '../views/auth/EmailChangeConfirmView';
import { PartnerApplyView } from '../views/auth/PartnerApplyView';
import { PartnerStatusView } from '../views/auth/PartnerStatusView';

export const AppRoutes: React.FC = () => {
  const BRAND_ROLES = ['brand_owner', 'brand_manager', 'brand_staff', 'admin'];
  const ADMIN_ROLES = ['admin'];

  return (
    // Router context is provided by App (AUTH-02: root-mounted AuthModal needs navigate()).
    <>
      <Routes>
        {/* 0. Public Shared Look (C8) — intentionally outside any guarded layout */}
        <Route path="/looks/:token" element={<SharedLookView />} />

        {/* 0b. LEGAL-01: real legal pages — public, not gated behind /profile.
            The audit found Privacy/Terms/GDPR links landing on the
            Authentication Required screen of /profile. */}
        <Route path="/" element={<ConsumerLayout />}>
          <Route path="privacy" element={<PrivacyPolicyView />} />
          <Route path="privacy-policy" element={<PrivacyPolicyView />} />
          <Route path="terms" element={<TermsOfServiceView />} />
          <Route path="terms-of-service" element={<TermsOfServiceView />} />
          <Route path="gdpr" element={<GdprView />} />
        </Route>

        {/* 0c. AUTH LIFECYCLE (2026-09-19) — public routes.
             Every email CONFIT sends links here. Before this group existed the
             links fell through the catch-all to "/", so users believed they had
             verified/reset when nothing had happened. */}
        <Route path="/verify-email" element={<VerifyEmailView />} />
        <Route path="/forgot-password" element={<ForgotPasswordView />} />
        <Route path="/reset-password" element={<ResetPasswordView />} />
        <Route path="/invite" element={<InviteAcceptView />} />
        <Route path="/settings/confirm-email" element={<EmailChangeConfirmView />} />

        {/* 0d. PARTNER ONBOARDING — the legitimate path from a consumer
             account to a brand role. Public (they render their own sign-in
             gate); access is granted by the server, never by these routes. */}
        <Route path="/partner/apply" element={<PartnerApplyView />} />
        <Route path="/partner/status" element={<PartnerStatusView />} />

        {/* 1. Consumer Storefront Routes (Browse-First / Guest-Friendly).
             The OnboardingGate wrapper handles Group 1 §23 first-run
             routing: authenticated users without a completed profile
             get bounced to /profile?onboarding=1 the first time they
             touch anything other than /profile / /settings. */}
        <Route path="/" element={<OnboardingGate><ConsumerLayout /></OnboardingGate>}>
          <Route index element={<HomeView />} />
          <Route path="discover" element={<DiscoverView />} />
          <Route path="products" element={<DiscoverView />} />
          <Route path="product/:slug" element={<ProductDetailView />} />
          <Route path="products/:slug" element={<ProductDetailView />} />
          
          <Route path="builder" element={<OutfitBuilderView />} />
          <Route path="outfits" element={<OutfitBuilderView />} />
          <Route path="outfits/:id" element={<OutfitBuilderView />} />
          <Route path="stylist" element={<DiscoverView />} />
          
          <Route path="tryon-studio" element={<TryOnFitView />} />
          <Route path="try-on" element={<TryOnFitView />} />
          <Route path="try-on/:sessionId" element={<TryOnFitView />} />
          {/* FIT-01: /fit is the dedicated no-photo measurement engine, not an
              alias of the try-on studio. The old mapping rendered TryOnFitView
              here, so the route named "Fit Finder" showed garment overlays —
              the exact promise/product mismatch in the 2026-09-05 audit. */}
          <Route path="fit" element={<FitFinderView />} />
          <Route path="fit-finder" element={<FitFinderView />} />
          <Route path="visual-search" element={<TryOnFitView />} />
          
          <Route path="wardrobe" element={<WardrobeView />} />
          <Route path="wardrobe/item/:id" element={<WardrobeView />} />
          <Route path="my-looks" element={<WardrobeView />} />
          
          <Route path="cart" element={<CheckoutView />} />
          <Route path="checkout" element={<CheckoutView />} />

          {/* Customer Authenticated Routes */}
          <Route
            path="orders"
            element={
              <ProtectedRoute>
                <OrderTrackingView />
              </ProtectedRoute>
            }
          />
          <Route
            path="orders/:orderNumber"
            element={<OrderTrackingView />}
          />
          <Route
            path="returns"
            element={
              <ProtectedRoute>
                <OrderTrackingView />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="profile"
            element={
              <ProtectedRoute>
                <UserProfileView />
              </ProtectedRoute>
            }
          />
          <Route
            path="settings"
            element={
              <ProtectedRoute>
                <UserProfileView />
              </ProtectedRoute>
            }
          />
          <Route
            path="notifications"
            element={
              <ProtectedRoute>
                <UserProfileView />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* 2. B2B Brand Partner Routes (Protected by BRAND_ROLES) */}
        <Route
          path="/b2b"
          element={
            <RoleGuard allowedRoles={BRAND_ROLES} fallbackTitle="Brand Partner Hub Access">
              <BrandLayout />
            </RoleGuard>
          }
        >
          <Route index element={<BrandDashboardView />} />
          <Route path="catalog" element={<BrandCatalogView />} />
          <Route path="inventory" element={<BrandInventoryView />} />
          <Route path="analytics" element={<BrandAnalyticsView />} />
          <Route path="placements" element={<BrandPlacementsView />} />
          <Route path="team" element={<BrandTeamView />} />
          <Route
            path="admin-platform"
            element={
              <RoleGuard allowedRoles={ADMIN_ROLES} fallbackTitle="Platform Governance Only">
                <AdminAnalyticsView />
              </RoleGuard>
            }
          />
        </Route>

        {/* 3. Partner Aliases */}
        <Route
          path="/partner"
          element={
            <RoleGuard allowedRoles={BRAND_ROLES} fallbackTitle="Brand Partner Portal">
              <BrandLayout />
            </RoleGuard>
          }
        >
          <Route index element={<BrandDashboardView />} />
          <Route path="dashboard" element={<BrandDashboardView />} />
          <Route path="catalog" element={<BrandCatalogView />} />
          <Route path="inventory" element={<BrandInventoryView />} />
          <Route path="analytics" element={<BrandAnalyticsView />} />
          <Route path="placements" element={<BrandPlacementsView />} />
          <Route path="team" element={<BrandTeamView />} />
        </Route>

        {/* 4. Platform Admin Governance Routes (Protected by ADMIN_ROLES) */}
        <Route
          path="/admin"
          element={
            <RoleGuard allowedRoles={ADMIN_ROLES} fallbackTitle="Platform Super-Admin Portal">
              <BrandLayout />
            </RoleGuard>
          }
        >
          <Route index element={<AdminAnalyticsView />} />
          <Route path="overview" element={<AdminAnalyticsView />} />
          <Route path="analytics" element={<AdminAnalyticsView />} />
          {/* Partner onboarding approvals: the ONLY self-service path from a
              consumer account to a brand role (BRD G6 §2.2). */}
          <Route path="partners" element={<AdminPartnersView />} />
          <Route path="audit" element={<AdminAnalyticsView />} />
        </Route>

        {/* 5. Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
};
