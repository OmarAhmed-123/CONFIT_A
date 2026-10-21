import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axe from 'axe-core';
import i18n from '../../i18n/i18n';
import { NoPhotoFitModal, resolveRecommendedInStockSku } from '../../components/tryon/NoPhotoFitModal';
import { ProductDetailView } from '../../views/consumer/ProductDetailView';
import { RouteAnnouncer } from '../../components/common/RouteAnnouncer';
import { useDeviceWishlist, resetWishlistCacheForTests, WISHLIST_STORAGE_KEY } from '../../hooks/useDeviceWishlist';
import { useUIStore } from '../../stores/uiStore';
import { useCartStore } from '../../stores/cartStore';
import { useAuthStore } from '../../stores/authStore';
import { catalogService, profileService, tryOnService } from '../../services/apiServices';
import type { Product } from '../../models';

const MULTI_SKU_PRODUCT: Product = {
  id: 777,
  slug: 'atelier-wool-coat',
  title: 'Atelier Tailored Wool Coat',
  title_ar: 'معطف صوف مُفصّل أتيليه',
  description: 'Structured double-faced merino wool coat.',
  brand_id: 4,
  brand_name: 'Nordhaus',
  category_id: 1,
  category_name: 'Outerwear',
  category_slug: 'outerwear',
  base_price: 420,
  currency: 'AED',
  color_family: 'Charcoal',
  dominant_hex: '#252729',
  style_tags: ['tailored'],
  occasion_tags: ['work'],
  rating: 4.8,
  is_featured: false,
  thumbnail_url: 'https://example.com/coat-0.jpg',
  images: [
    'https://example.com/coat-0.jpg',
    'https://example.com/coat-1.jpg',
  ],
  skus: [
    {
      id: 101,
      product_id: 777,
      sku_code: 'COAT-S',
      size: 'S',
      color: 'Charcoal',
      color_hex: '#252729',
      stock_level: 6,
      is_in_stock: true,
    },
    {
      id: 102,
      product_id: 777,
      sku_code: 'COAT-XL',
      size: 'XL',
      color: 'Charcoal',
      color_hex: '#252729',
      stock_level: 4,
      is_in_stock: true,
    },
    {
      id: 103,
      product_id: 777,
      sku_code: 'COAT-XXL',
      size: 'XXL',
      color: 'Charcoal',
      color_hex: '#252729',
      stock_level: 0,
      is_in_stock: false,
    },
  ],
};

function WishlistProbe() {
  const { wishlist, toggleWishlist, isWishlisted, wishlistError } = useDeviceWishlist();
  return (
    <div>
      <span data-testid="wishlist-ids">{wishlist.join(',')}</span>
      <span data-testid="wishlist-err">{String(wishlistError)}</span>
      <button
        data-motion="filter"
        type="button"
        aria-pressed={isWishlisted(777)}
        onClick={() => toggleWishlist(777)}
      >
        Toggle 777
      </button>
    </div>
  );
}

describe('Real-World Accessibility, Localization & Journey Closure Contracts', () => {
  beforeEach(async () => {
    window.localStorage.clear();
    resetWishlistCacheForTests();
    await i18n.changeLanguage('en');
    document.documentElement.dir = 'ltr';
    useUIStore.setState({
      rulerProduct: null,
      rulerMeasurements: null,
      toast: null,
    });
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
    });
    vi.restoreAllMocks();
  });

  it('NoPhotoFitModal adds the EXACT recommended in-stock SKU (never skus[0]) and handles OOS cleanly', async () => {
    expect(resolveRecommendedInStockSku(MULTI_SKU_PRODUCT.skus, 'XL')?.id).toBe(102);
    expect(resolveRecommendedInStockSku(MULTI_SKU_PRODUCT.skus, 'XXL')).toBeNull();

    const addItemSpy = vi.fn().mockResolvedValue(undefined);
    const openCartSpy = vi.fn();
    useCartStore.setState({ addItem: addItemSpy, openCart: openCartSpy } as any);

    vi.spyOn(tryOnService, 'calculateNoPhotoFit').mockResolvedValue({
      recommended: true,
      recommended_size: 'XL',
      confidence_score: 88,
      confidence_band: 'high',
      is_between_sizes: true,
      alternative_size: 'XXL',
      fit_breakdown: { shoulders: 'Balanced drape', chest: 'Comfortable ease' },
      return_risk: { level: 'low', label: 'Low' },
      brand_sizing_tendency: { code: 'true_to_size', summary: 'True to size across shoulders.' },
      size_chart_source: { kind: 'brand', label: 'Nordhaus Outerwear Chart', updated_at: '2026-10-01' },
    } as any);
    vi.spyOn(catalogService, 'recordEngagementEvent').mockResolvedValue({
      status: 'recorded',
      event_id: 'evt-1',
    });

    useUIStore.setState({ rulerProduct: MULTI_SKU_PRODUCT });

    render(
      <MemoryRouter>
        <div>
          <main data-testid="background-main">
            <a href="/products">Background catalog link</a>
          </main>
          <NoPhotoFitModal />
        </div>
      </MemoryRouter>,
    );

    // Sibling background subtree must be hidden from screen-reader browse cursors while modal is open
    expect(screen.getByTestId('background-main')).toHaveAttribute('aria-hidden', 'true');

    // Range sliders must expose explicit labels + human-readable aria-valuetext
    const heightSlider = screen.getByRole('slider', { name: /height in centimeters/i });
    const weightSlider = screen.getByRole('slider', { name: /weight in kilograms/i });
    expect(heightSlider).toHaveAttribute('aria-valuetext', '178 centimeters');
    expect(weightSlider).toHaveAttribute('aria-valuetext', '72 kilograms');

    fireEvent.click(screen.getByRole('button', { name: /calculate my size/i }));

    const addBtn = await screen.findByTestId('no-photo-add-recommended-btn');
    expect(addBtn).toHaveTextContent(/add size xl to bag/i);
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(addItemSpy).toHaveBeenCalledTimes(1);
      // MUST add SKU 102 (XL), NEVER SKU 101 (S at skus[0])!
      expect(addItemSpy.mock.calls[0][0]).toBe(102);
    });

    // After modal closes, background aria-hidden is cleanly restored
    expect(screen.getByTestId('background-main')).not.toHaveAttribute('aria-hidden');
  });

  it('NoPhotoFitModal in Arabic (RTL) passes axe with zero critical/serious violations and localized slider valuetext', async () => {
    await i18n.changeLanguage('ar');
    document.documentElement.dir = 'rtl';
    useUIStore.setState({ rulerProduct: MULTI_SKU_PRODUCT });

    const { container } = render(
      <MemoryRouter>
        <NoPhotoFitModal />
      </MemoryRouter>,
    );

    const sliders = screen.getAllByRole('slider');
    expect(sliders).toHaveLength(2);
    expect(sliders[0].getAttribute('aria-valuetext')).toContain('178');
    expect(container.textContent).not.toContain('📸');
    expect(container.textContent).not.toContain('Open Camera');
    expect(container.textContent).not.toContain('Compute Precision Fit Verdict');

    const results = await axe.run(container);
    const seriousOrCritical = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    expect(seriousOrCritical).toEqual([]);
  });

  it('ProductDetailView pre-selects ?size=XL from Fit Finder, surfaces OOS notice for ?size=XXL, localizes Arabic thumbnail alt, and emits gallery_photo_view', async () => {
    await i18n.changeLanguage('ar');
    document.documentElement.dir = 'rtl';

    vi.spyOn(catalogService, 'getProductDetail').mockResolvedValue(MULTI_SKU_PRODUCT);
    vi.spyOn(catalogService, 'getBopisStoresForSKU').mockResolvedValue([]);
    const eventSpy = vi.spyOn(catalogService, 'recordEngagementEvent').mockResolvedValue({
      status: 'recorded',
      event_id: 'evt-gallery',
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/product/atelier-wool-coat?size=XL']}>
          <Routes>
            <Route path="/product/:slug" element={<ProductDetailView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const appliedBanner = await screen.findByTestId('fit-finder-applied-banner');
    expect(appliedBanner.textContent).toContain('XL');

    // Gallery thumbnail alt must use localized Arabic title_ar, NOT English title
    const imgs = screen.getAllByRole('img');
    const localizedAlts = imgs.map((el) => el.getAttribute('alt') || '');
    expect(localizedAlts.some((a) => a.includes('معطف صوف مُفصّل أتيليه'))).toBe(true);
    expect(localizedAlts.some((a) => a.includes('Atelier Tailored Wool Coat'))).toBe(false);

    // Clicking second gallery frame emits gallery_photo_view with photo_index = 1
    const frame2 = screen.getByRole('button', { name: /2/ });
    fireEvent.click(frame2);

    await waitFor(() => {
      expect(eventSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          product_id: 777,
          event_type: 'gallery_photo_view',
          photo_index: 1,
        }),
      );
    });

    unmount();

    // Out-of-stock recommended size (?size=XXL) surfaces honest OOS banner
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/product/atelier-wool-coat?size=XXL']}>
          <Routes>
            <Route path="/product/:slug" element={<ProductDetailView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const oosBanner = await screen.findByTestId('fit-finder-applied-banner');
    expect(oosBanner.textContent).toContain('XXL');
  });

  it('useDeviceWishlist merges guest items on login without duplicates, rolls back with alert toast on server failure, and isolates on logout', async () => {
    window.localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify([501]));
    const syncSpy = vi
      .spyOn(profileService, 'syncWishlist')
      .mockResolvedValue({ product_ids: [501, 602] });
    const addFailSpy = vi
      .spyOn(profileService, 'addWishlistItem')
      .mockRejectedValue(new Error('503 Upstream Timeout'));

    render(<WishlistProbe />);
    expect(screen.getByTestId('wishlist-ids').textContent).toBe('501');

    // Login -> merges [501] with account items -> [501, 602] and clears anonymous storage
    await act(async () => {
      useAuthStore.setState({
        isAuthenticated: true,
        user: { id: 42, email: 'shopper-a@confit.test', role: 'user' } as any,
      });
    });

    await waitFor(() => {
      expect(syncSpy).toHaveBeenCalledWith([501]);
      expect(screen.getByTestId('wishlist-ids').textContent).toBe('501,602');
      expect(window.localStorage.getItem(WISHLIST_STORAGE_KEY)).toBeNull();
    });

    // Server write failure rolls back optimistic state & announces error toast
    fireEvent.click(screen.getByRole('button', { name: 'Toggle 777' }));
    await waitFor(() => {
      expect(addFailSpy).toHaveBeenCalledWith(777);
      expect(screen.getByTestId('wishlist-ids').textContent).toBe('501,602');
      expect(useUIStore.getState().toast?.type).toBe('error');
    });

    // Logout clears state cleanly so User B never inherits User A's wishlist
    await act(async () => {
      useAuthStore.setState({ isAuthenticated: false, user: null });
    });
    expect(screen.getByTestId('wishlist-ids').textContent).toBe('');
  });

  it('RouteAnnouncer stays silent on initial load and announces client-side route changes cleanly', async () => {
    vi.useFakeTimers();
    try {
      render(
        <MemoryRouter initialEntries={['/']}>
          <RouteAnnouncer />
          <nav>
            <Link to="/brands">Go Brands</Link>
          </nav>
          <Routes>
            <Route path="/" element={<main><h1>Home Atelier</h1></main>} />
            <Route path="/brands" element={<main><h1>Partner Houses</h1></main>} />
          </Routes>
        </MemoryRouter>,
      );

      // Silent on initial load
      act(() => {
        vi.advanceTimersByTime(150);
      });
      expect(screen.getByTestId('spa-route-announcer').textContent).toBe('');

      // Client-side navigation announces new page heading
      fireEvent.click(screen.getByText('Go Brands'));
      act(() => {
        vi.advanceTimersByTime(150);
      });
      expect(screen.getByTestId('spa-route-announcer').textContent).toContain('Partner Houses');
    } finally {
      vi.useRealTimers();
    }
  });
});
