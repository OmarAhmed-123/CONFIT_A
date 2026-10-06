import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConsumerLayout } from '../layouts/ConsumerLayout';
import { BrandLayout } from '../layouts/BrandLayout';
import { RoleGuard, ProtectedRoute } from '../components/auth/RoleGuard';
import { RoutePending } from '../components/navigation/RoutePending';
import { useAuthStore } from '../stores/authStore';

/**
 * OnboardingGate — Group 1 §23 first-run flow.
 *
 * Authenticated users who have not completed the style profile are routed
 * to /profile (the wizard host). Applies only to consumer-scoped routes;
 * B2B / admin surfaces are unaffected.
 */
const OnboardingGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated } = useAuthStore();
  const location = useLocation();
  const skipPaths = ['/profile', '/settings', '/onboarding'];
  const shouldRedirect =
    isAuthenticated &&
    user &&
    !user.has_profile &&
    !skipPaths.some((p) => location.pathname.startsWith(p));
  if (shouldRedirect) {
    return <Navigate to="/profile?onboarding=1" replace />;
  }
  return <>{children}</>;
};

// Consumer Views
import { HomeView } from '../views/consumer/HomeView';
import { DiscoverView } from '../views/consumer/DiscoverView';
import { OutfitBuilderView } from '../views/consumer/OutfitBuilderView';
import { TryOnFitView } from '../views/consumer/TryOnFitView';
import { TryOnStudioErrorBoundary } from '../components/tryon/TryOnStudioErrorBoundary';
import { FitFinderView } from '../views/consumer/FitFinderView';
import { WardrobeView } from '../views/consumer/WardrobeView';
import { MyLooksView } from '../views/consumer/MyLooksView';
import { ProductDetailView } from '../views/consumer/ProductDetailView';
import { CheckoutView } from '../views/consumer/CheckoutView';
import { OrderTrackingView } from '../views/consumer/OrderTrackingView';
import { UserProfileView } from '../views/consumer/UserProfileView';
import { SharedLookView } from '../views/public/SharedLookView';
import { EmailUnsubscribeView } from '../views/public/EmailUnsubscribeView';
import { ResetPasswordView } from '../views/public/ResetPasswordView';
import { VerifyEmailView } from '../views/public/VerifyEmailView';
import { NotFoundView } from '../views/public/NotFoundView';
import { PrivacyPolicyView, TermsOfServiceView, GdprView } from '../views/legal/LegalViews';

// B2B Views
import { BrandDashboardView } from '../views/b2b/BrandDashboardView';
import { BrandCatalogView } from '../views/b2b/BrandCatalogView';
import { BrandInventoryView } from '../views/b2b/BrandInventoryView';
import { BrandOrdersView } from '../views/b2b/BrandOrdersView';
// Spec "Magic Navigation" §5: the two ANALYTICS views are the heaviest
// modules in the app (recharts + dashboards — the 'b2b-analytics' chunk).
// They are code-split with React.lazy so a SHOPPER never downloads partner/
// governance tooling, and the pending navigation state while the chunk
// loads is a visible, translated, politely-announced text — not a blank
// screen (RoutePending below). Every other route stays eager: they are
// small, and an instant shell beats a spinner.
const BrandAnalyticsView = React.lazy(() =>
  import('../views/b2b/BrandAnalyticsView').then((m) => ({ default: m.BrandAnalyticsView })),
);
import { BrandPlacementsView } from '../views/b2b/BrandPlacementsView';
const AdminAnalyticsView = React.lazy(() =>
  import('../views/b2b/AdminAnalyticsView').then((m) => ({ default: m.AdminAnalyticsView })),
);

/** Lazy element + its announced pending state, in one expression. */
const suspended = (node: React.ReactNode) => (
  <React.Suspense fallback={<RoutePending />}>{node}</React.Suspense>
);
import { AdminAuditView } from '../views/b2b/AdminAuditView';
import { AdminCatalogView } from '../views/b2b/AdminCatalogView';

const PARTNER_ROLES = ['brand_owner', 'brand_manager', 'brand_staff'];
const ADMIN_ROLES = ['admin'];

const TryOnStudioRoute: React.FC = () => (
  <TryOnStudioErrorBoundary>
    <TryOnFitView />
  </TryOnStudioErrorBoundary>
);

/**
 * Keep platform administration and partner tenancy as separate trust domains.
 *
 * Admin users have no BrandProfile by design. Before this boundary existed,
 * /b2b pages made six tenant-scoped requests with the admin identity and then
 * rendered "every request failed". Legacy/bookmarked partner URLs now lead an
 * admin to the matching explicit admin surface; partner roles still use the
 * original tenant-isolated portal.
 */
export const PartnerPortalBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, hasAttemptedBootstrap } = useAuthStore();
  const location = useLocation();
  const isAdmin = user?.role?.toLowerCase() === 'admin';

  if (hasAttemptedBootstrap && isAuthenticated && isAdmin) {
    const normalized = location.pathname.replace(/^\/(partner|b2b)(?=\/|$)/, '');
    const destination = normalized === '/analytics' || normalized === '/admin-platform'
      ? '/admin/analytics'
      : normalized === '/catalog'
        ? '/admin/catalog'
        : normalized === '/inventory'
          ? '/admin/catalog?tab=inventory'
          : normalized === '/placements'
            ? '/admin/catalog?tab=placements'
            : '/admin';
    return <Navigate to={destination} replace />;
  }

  return (
    <RoleGuard allowedRoles={PARTNER_ROLES} portal="partner">
      {children}
    </RoleGuard>
  );
};

export const AppRoutes: React.FC = () => {

  return (
    // Router context is provided by App (AUTH-02: root-mounted AuthModal needs navigate()).
    <>
      <Routes>
        {/* 0. Public Shared Look (C8) — intentionally outside any guarded layout */}
        <Route path="/looks/:token" element={<SharedLookView />} />
        {/* Spec 15: landing for email-footer unsubscribe links. PUBLIC —
            the signed token in the URL is the credential; no session. */}
        <Route path="/email/unsubscribe" element={<EmailUnsubscribeView />} />
        {/* Audit 2026-10-06: the backend has emailed these two URLs since
            cycle 4 and neither route existed — the links bounced to the
            home page via the silent catch-all. PUBLIC: the one-time token
            in the URL is the credential. */}
        <Route path="/reset-password" element={<ResetPasswordView />} />
        <Route path="/verify-email" element={<VerifyEmailView />} />

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
          <Route path="outfits" element={<MyLooksView />} />
          <Route path="outfits/:id" element={<OutfitBuilderView />} />
          <Route path="stylist" element={<DiscoverView />} />
          
          <Route path="tryon-studio" element={<TryOnStudioRoute />} />
          <Route path="try-on" element={<TryOnStudioRoute />} />
          <Route path="try-on/:sessionId" element={<TryOnStudioRoute />} />
          {/* FIT-01: /fit is the dedicated no-photo measurement engine, not an
              alias of the try-on studio. The old mapping rendered TryOnFitView
              here, so the route named "Fit Finder" showed garment overlays —
              the exact promise/product mismatch in the 2026-09-05 audit. */}
          <Route path="fit" element={<FitFinderView />} />
          <Route path="fit-finder" element={<FitFinderView />} />
          <Route path="visual-search" element={<TryOnStudioRoute />} />
          
          <Route path="wardrobe" element={<WardrobeView />} />
          <Route path="wardrobe/item/:id" element={<WardrobeView />} />
          {/* OUTFIT-03: /my-looks rendered the WARDROBE, so saved outfits had no
              home in the product. It now renders the real saved-looks view. */}
          <Route path="my-looks" element={<MyLooksView />} />
          
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

        {/* 2. B2B Brand Partner Routes (tenant roles only; admins redirect) */}
        <Route
          path="/b2b"
          element={
            <PartnerPortalBoundary>
              <BrandLayout />
            </PartnerPortalBoundary>
          }
        >
          <Route index element={<BrandDashboardView />} />
          <Route path="catalog" element={<BrandCatalogView />} />
          <Route path="inventory" element={<BrandInventoryView />} />
          <Route path="orders" element={<BrandOrdersView />} />
          <Route path="analytics" element={suspended(<BrandAnalyticsView />)} />
          <Route path="placements" element={<BrandPlacementsView />} />
          {/* Kept as a legacy URL. PartnerPortalBoundary redirects an admin to
              /admin/analytics; partner roles do not receive platform access. */}
          <Route path="admin-platform" element={<Navigate to="/b2b" replace />} />
        </Route>

        {/* 3. Partner Aliases */}
        <Route
          path="/partner"
          element={
            <PartnerPortalBoundary>
              <BrandLayout />
            </PartnerPortalBoundary>
          }
        >
          <Route index element={<BrandDashboardView />} />
          <Route path="dashboard" element={<BrandDashboardView />} />
          <Route path="catalog" element={<BrandCatalogView />} />
          <Route path="inventory" element={<BrandInventoryView />} />
          <Route path="orders" element={<BrandOrdersView />} />
          <Route path="analytics" element={suspended(<BrandAnalyticsView />)} />
          <Route path="placements" element={<BrandPlacementsView />} />
        </Route>

        {/* 4. Platform Admin Governance Routes (Protected by ADMIN_ROLES) */}
        <Route
          path="/admin"
          element={
            <RoleGuard allowedRoles={ADMIN_ROLES} portal="admin">
              <BrandLayout />
            </RoleGuard>
          }
        >
          <Route index element={suspended(<AdminAnalyticsView />)} />
          <Route path="overview" element={suspended(<AdminAnalyticsView />)} />
          <Route path="analytics" element={suspended(<AdminAnalyticsView />)} />
          <Route path="catalog" element={<AdminCatalogView />} />
          <Route path="partners" element={<AdminCatalogView />} />
          {/* G-07: this route used to render the analytics dashboard, so the
              audit trail had no UI at all. */}
          <Route path="audit" element={<AdminAuditView />} />
        </Route>

        {/* 5. Fallback — an HONEST 404, not a silent redirect home.
            Audit 2026-10-06: the old `Navigate to="/"` hid every broken
            link from the person who followed it. */}
        <Route path="*" element={<NotFoundView />} />
      </Routes>
    </>
  );
};
