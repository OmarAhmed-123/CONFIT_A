import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConsumerLayout } from '../layouts/ConsumerLayout';
import { BrandLayout } from '../layouts/BrandLayout';

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

// B2B Views
import { BrandDashboardView } from '../views/b2b/BrandDashboardView';
import { BrandCatalogView } from '../views/b2b/BrandCatalogView';
import { BrandInventoryView } from '../views/b2b/BrandInventoryView';
import { BrandAnalyticsView } from '../views/b2b/BrandAnalyticsView';
import { BrandPlacementsView } from '../views/b2b/BrandPlacementsView';
import { AdminAnalyticsView } from '../views/b2b/AdminAnalyticsView';

export const AppRoutes: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Consumer Storefront Routes */}
        <Route path="/" element={<ConsumerLayout />}>
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
          <Route path="orders" element={<OrderTrackingView />} />
          <Route path="orders/:orderNumber" element={<OrderTrackingView />} />
          <Route path="returns" element={<OrderTrackingView />} />
          
          <Route path="profile" element={<UserProfileView />} />
          <Route path="settings" element={<UserProfileView />} />
          <Route path="notifications" element={<UserProfileView />} />
        </Route>

        {/* B2B Brand Partner & Platform Admin Routes */}
        <Route path="/b2b" element={<BrandLayout />}>
          <Route index element={<BrandDashboardView />} />
          <Route path="catalog" element={<BrandCatalogView />} />
          <Route path="inventory" element={<BrandInventoryView />} />
          <Route path="analytics" element={<BrandAnalyticsView />} />
          <Route path="placements" element={<BrandPlacementsView />} />
          <Route path="admin-platform" element={<AdminAnalyticsView />} />
        </Route>

        {/* Partner & Admin Aliases */}
        <Route path="/partner" element={<BrandLayout />}>
          <Route index element={<BrandDashboardView />} />
          <Route path="dashboard" element={<BrandDashboardView />} />
          <Route path="catalog" element={<BrandCatalogView />} />
          <Route path="inventory" element={<BrandInventoryView />} />
          <Route path="analytics" element={<BrandAnalyticsView />} />
          <Route path="placements" element={<BrandPlacementsView />} />
        </Route>

        <Route path="/admin" element={<BrandLayout />}>
          <Route index element={<AdminAnalyticsView />} />
          <Route path="overview" element={<AdminAnalyticsView />} />
          <Route path="analytics" element={<AdminAnalyticsView />} />
          <Route path="partners" element={<BrandDashboardView />} />
          <Route path="audit" element={<AdminAnalyticsView />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
