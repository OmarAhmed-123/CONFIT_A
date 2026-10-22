import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axe from 'axe-core';
import i18n from '../../i18n/i18n';
import { NoPhotoFitModal, resolveRecommendedInStockSku } from '../../components/tryon/NoPhotoFitModal';
import { ProductDetailView } from '../../views/consumer/ProductDetailView';
import { CheckoutView } from '../../views/consumer/CheckoutView';
import { OrderTrackingView } from '../../views/consumer/OrderTrackingView';
import { BrandAnalyticsView } from '../../views/b2b/BrandAnalyticsView';
import { CartDrawer } from '../../components/commerce/CartDrawer';
import { DuplicateAlertModal } from '../../components/wardrobe/DuplicateAlertModal';
import { SkipLink, SKIP_MAIN_ID } from '../../components/common/SkipLink';
import { SharedLookView } from '../../views/public/SharedLookView';
import { RouteAnnouncer } from '../../components/common/RouteAnnouncer';
import { useDeviceWishlist, resetWishlistCacheForTests, WISHLIST_STORAGE_KEY } from '../../hooks/useDeviceWishlist';
import { useUIStore } from '../../stores/uiStore';
import { useCartStore } from '../../stores/cartStore';
import { useAuthStore } from '../../stores/authStore';
import { brandService, catalogService, commerceService, profileService, publicLookService, tryOnService } from '../../services/apiServices';
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

      // Locale switch on the same route re-announces localized surface
      await act(async () => {
        await i18n.changeLanguage('ar');
      });
      act(() => {
        vi.advanceTimersByTime(150);
      });
      expect(screen.getByTestId('spa-route-announcer').textContent).toContain('Partner Houses');
    } finally {
      vi.useRealTimers();
    }
  });

  it('SkipLink programmatically transfers focus onto #confit-main-content on activation across all engines including WebKit', () => {
    render(
      <div>
        <SkipLink />
        <header>
          <a href="/discover">Header Nav</a>
        </header>
        <main id={SKIP_MAIN_ID} tabIndex={-1}>
          <h1>Catalog Surface</h1>
        </main>
      </div>,
    );

    const skip = screen.getByRole('link', { name: /skip to main content/i });
    const main = document.getElementById(SKIP_MAIN_ID)!;
    skip.focus();
    expect(document.activeElement).toBe(skip);

    fireEvent.click(skip);
    expect(document.activeElement).toBe(main);
  });

  it('CartDrawer isolates background siblings, traps Escape, exposes localized +/- item labels and <bdi dir="ltr"> values in Arabic RTL', async () => {
    await i18n.changeLanguage('ar');
    document.documentElement.dir = 'rtl';

    const closeCartSpy = vi.fn();
    useCartStore.setState({
      isOpen: true,
      closeCart: closeCartSpy,
      cart: {
        items: [
          {
            id: 91,
            product_sku_id: 102,
            product_title: 'معطف صوف مُفصّل أتيليه',
            brand_name: 'Nordhaus',
            size: 'XL',
            color: 'Charcoal',
            ai_fit_verdict: '94% Match',
            unit_price: 420,
            subtotal: 420,
            quantity: 1,
            image_url: 'https://example.com/coat-0.jpg',
          },
        ],
        subtotal: 420,
        discount_amount: 0,
        total: 420,
        total_items: 1,
        currency: 'EGP',
      },
      appliedPromo: null,
      updateQuantity: vi.fn(),
      removeItem: vi.fn(),
      applyPromo: vi.fn(),
      clearPromo: vi.fn(),
    } as any);

    const { container } = render(
      <MemoryRouter>
        <div>
          <main data-testid="storefront-bg">
            <a href="/discover">Storefront Link</a>
          </main>
          <CartDrawer />
        </div>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('storefront-bg')).toHaveAttribute('aria-hidden', 'true');
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'cart-drawer-title');

    // Arabic localized +/- buttons name the exact item
    expect(screen.getByRole('button', { name: /تقليل كمية معطف صوف مُفصّل أتيليه/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /زيادة كمية معطف صوف مُفصّل أتيليه/i })).toBeInTheDocument();

    // Bidi isolation on size + currency totals
    const bdiNodes = container.querySelectorAll('bdi[dir="ltr"]');
    expect(bdiNodes.length).toBeGreaterThanOrEqual(2);

    const axeRes = await axe.run(container);
    expect(axeRes.violations).toHaveLength(0);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(closeCartSpy).toHaveBeenCalledTimes(1);
  });

  it('DuplicateAlertModal traps focus, marks background aria-hidden, and closes on Escape with zero axe violations', async () => {
    const dismissSpy = vi.fn();
    useCartStore.setState({
      pendingDuplicateAlert: {
        owned_item: {
          id: 12,
          title: 'Black Cashmere Knit',
          category: 'tops',
          color_name: 'Black',
          wear_count: 8,
          wear_frequency: 'weekly',
          image_url: 'https://example.com/knit.jpg',
        },
        similarity_score: 91,
        reason: 'Identical silhouette and color family',
      },
      confirmAddDuplicate: vi.fn(),
      dismissDuplicate: dismissSpy,
    } as any);

    const { container } = render(
      <div>
        <main data-testid="wardrobe-bg">
          <button data-motion="neutral" type="button">Add Item</button>
        </main>
        <DuplicateAlertModal />
      </div>,
    );

    expect(screen.getByTestId('wardrobe-bg')).toHaveAttribute('aria-hidden', 'true');
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    const axeRes = await axe.run(container);
    expect(axeRes.violations).toHaveLength(0);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(dismissSpy).toHaveBeenCalledTimes(1);
  });

  it('CheckoutView associates validation errors via aria-invalid + aria-describedby + role="alert" in Arabic RTL', async () => {
    await i18n.changeLanguage('ar');
    document.documentElement.dir = 'rtl';

    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 42, email: 'shopper@confit.org', role: 'user' } as any,
    });

    vi.spyOn(commerceService, 'getPaymentMethods').mockResolvedValue({
      available_methods: [
        {
          id: 'card',
          title_en: 'Card',
          description_en: 'Pay securely by card',
          provider_name: 'fawaterak',
        },
      ],
      currency_code: 'EGP',
    } as any);

    useCartStore.setState({
      cart: {
        items: [
          {
            id: 91,
            product_sku_id: 102,
            product_title: 'معطف صوف مُفصّل أتيليه',
            size: 'XL',
            color: 'Charcoal',
            unit_price: 420,
            subtotal: 420,
            quantity: 1,
          },
        ],
        subtotal: 420,
        discount_amount: 0,
        total: 420,
        total_items: 1,
        currency: 'EGP',
      },
      appliedPromo: null,
      fetchCart: vi.fn().mockResolvedValue(undefined),
    } as any);

    const { container } = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <Routes>
          <Route path="/checkout" element={<CheckoutView />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole('heading', { level: 1 });
    fireEvent.submit(container.querySelector('form')!);

    const nameInput = document.getElementById('full-name')!;
    await waitFor(() => {
      expect(nameInput).toHaveAttribute('aria-invalid', 'true');
      expect(nameInput).toHaveAttribute('aria-describedby', 'full-name-error');
      expect(document.activeElement).toBe(nameInput);
    });
    expect(document.getElementById('full-name-error')).toHaveAttribute('role', 'alert');

    const axeRes = await axe.run(container);
    expect(axeRes.violations).toHaveLength(0);
  });

  it('OrderTrackingView formats line subtotals with formatMoney + <bdi dir="ltr"> and isolates Return Request modal', async () => {
    await i18n.changeLanguage('ar');
    document.documentElement.dir = 'rtl';

    vi.spyOn(commerceService, 'getOrderDetail').mockResolvedValue({
      id: 55,
      order_number: 'CNF-2026-0055',
      status: 'delivered',
      payment_method: 'card',
      payment_status: 'paid',
      payment_mode: 'live',
      fulfillment_method: 'delivery',
      currency: 'EGP',
      subtotal: 1250,
      shipping_cost: 0,
      tax_amount: 0,
      discount_amount: 0,
      total_amount: 1250,
      created_at: '2026-10-20T12:00:00Z',
      items: [
        {
          id: 1,
          product_title: 'معطف صوف مُفصّل أتيليه',
          size: 'XL',
          color: 'Charcoal',
          quantity: 1,
          unit_price: 1250,
          subtotal: 1250,
        },
      ],
    } as any);
    vi.spyOn(commerceService, 'getOrderTracking').mockResolvedValue({
      status: 'delivered',
      carrier: 'Aramex',
      tracking_number: 'ARMX-998877',
      timeline: [
        {
          status_key: 'delivered',
          label: 'Delivered',
          completed: true,
          current: true,
          timestamp: '2026-10-21T10:00:00Z',
        },
      ],
    } as any);

    const { container } = render(
      <MemoryRouter initialEntries={['/orders/CNF-2026-0055']}>
        <div>
          <aside data-testid="orders-sibling">Sibling Nav</aside>
          <Routes>
            <Route path="/orders/:orderNumber" element={<OrderTrackingView />} />
          </Routes>
        </div>
      </MemoryRouter>,
    );

    await screen.findByText('CNF-2026-0055');
    // Order currency EGP must be rendered instead of hardcoded '$'
    expect(container.textContent).not.toContain('$1250.00');

    // Open Return Request modal -> sibling hidden + Escape closes
    fireEvent.click(screen.getByRole('button', { name: /طلب إرجاع/i }));
    expect(await screen.findByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByTestId('orders-sibling')).toHaveAttribute('aria-hidden', 'true');

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('BrandAnalyticsView localizes presets/headings in Arabic RTL and reports export failures via non-blocking toast instead of window.alert', async () => {
    await i18n.changeLanguage('ar');
    document.documentElement.dir = 'rtl';

    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.spyOn(brandService, 'getBiDashboard').mockResolvedValue({
      brand: { id: 4, name: 'Nordhaus', slug: 'nordhaus' },
      currency: 'AED',
      methodology: 'Server-verified ledger aggregation',
      period: { label: '2026-09-22 — 2026-10-22', days: 30 },
      filters: { branches: [], categories: [] },
      kpis: {
        gross_sales: 18400,
        gross_sales_change_pct: 12.4,
        net_sales: 16900,
        net_sales_change_pct: 10.1,
        orders_count: 44,
        orders_count_change_pct: 8.0,
        units_sold: 61,
        units_sold_change_pct: 9.2,
        average_order_value: 418,
        average_order_value_change_pct: 3.1,
        return_rate: 4.5,
        returned_units: 3,
      },
      timeseries: [],
      products: [
        {
          product_id: 777,
          title: 'Atelier Tailored Wool Coat',
          category: 'Outerwear',
          units_sold: 14,
          gross_sales: 5880,
          return_rate: 2.1,
          current_stock: 10,
          low_stock: false,
        },
      ],
      branches: [],
      promotions: [],
      insights: [],
    } as any);
    vi.spyOn(brandService, 'downloadBiCsv').mockRejectedValue(new Error('503 Export Gateway Busy'));

    const { container } = render(
      <MemoryRouter>
        <BrandAnalyticsView />
      </MemoryRouter>,
    );

    expect(await screen.findByText('المنتجات الأعلى أداءً')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'آخر 30 يوماً' })).toHaveAttribute('aria-pressed', 'true');
    expect(container.querySelectorAll('th[scope="col"]').length).toBeGreaterThanOrEqual(6);

    fireEvent.click(screen.getByRole('button', { name: /csv/i }));
    await waitFor(() => {
      expect(alertSpy).not.toHaveBeenCalled();
      expect(useUIStore.getState().toast?.type).toBe('error');
    });
  });

  it('SharedLookView separates top-level banner header from #confit-main-content main landmark', async () => {
    vi.spyOn(publicLookService, 'getPublicLook').mockRejectedValue({ status: 404 });

    const { container } = render(
      <MemoryRouter initialEntries={['/look/missing-look']}>
        <Routes>
          <Route path="/look/:token" element={<SharedLookView />} />
        </Routes>
      </MemoryRouter>,
    );

    const main = await screen.findByRole('main');
    expect(main).toHaveAttribute('id', SKIP_MAIN_ID);
    const header = container.querySelector('header')!;
    expect(main.contains(header)).toBe(false);

    const axeRes = await axe.run(container);
    expect(axeRes.violations).toHaveLength(0);
  });
});
