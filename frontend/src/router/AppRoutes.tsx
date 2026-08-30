import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConsumerLayout } from '../layouts/ConsumerLayout';
import { BrandLayout } from '../layouts/BrandLayout';
import { RoleGuard, ProtectedRoute } from '../components/auth/RoleGuard';
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
import { WardrobeView } from '../views/consumer/WardrobeView';
import { ProductDetailView } from '../views/consumer/ProductDetailView';
import { CheckoutView } from '../views/consumer/CheckoutView';
import { OrderTrackingView } from '../views/consumer/OrderTrackingView';
import { UserProfileView } from '../views/consumer/UserProfileView';
import { SharedLookView } from '../views/public/SharedLookView';

// B2B Views
import { BrandDashboardView } from '../views/b2b/BrandDashboardView';
import { BrandCatalogView } from '../views/b2b/BrandCatalogView';
import { BrandInventoryView } from '../views/b2b/BrandInventoryView';
import { BrandAnalyticsView } from '../views/b2b/BrandAnalyticsView';
import { BrandPlacementsView } from '../views/b2b/BrandPlacementsView';
import { AdminAnalyticsView } from '../views/b2b/AdminAnalyticsView';

export const AppRoutes: React.FC = () => {
  const BRAND_ROLES = ['brand_owner', 'brand_manager', 'brand_staff', 'admin'];
  const ADMIN_ROLES = ['admin'];

  return (
    <BrowserRouter>
      <Routes>
        {/* 0. Public Shared Look (C8) — intentionally outside any guarded layout */}
        <Route path="/looks/:token" element={<SharedLookView />} />

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
          <Route path="fit" element={<TryOnFitView />} />
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
          <Route path="partners" element={<BrandDashboardView />} />
          <Route path="audit" element={<AdminAnalyticsView />} />
        </Route>

        {/* 5. Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
