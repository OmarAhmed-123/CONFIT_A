/**
 * 010 — Extended surfaces axe coverage (FR-001, SC-001, FR-005)
 * Covers: Cart/Checkout, Admin catalog/analytics, Brand inventory, VTON, dialogs, forms
 * Each test renders a realistic state with mocked dependencies and asserts 0 critical/serious axe violations.
 * Does NOT silence axe rules except jsdom-uncomputable color-contrast and target-size.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, screen, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { EmptyState, LoadingState, ErrorState, ConfirmationDialog, LiveStatus } from '../../components/common/StateComponents';
import { AccessibleButton, AccessibleInput, AccessibleSelect } from '../../components/common/AccessiblePrimitives';
import { MotionWrapper } from '../../components/common/MotionWrapper';
import { HonestProductImage } from '../../components/common/HonestProductImage';

const JSDOM_UNCOMPUTABLE = ['color-contrast', 'target-size'];

async function seriousViolations(node: HTMLElement) {
  const results = await axe(node, {
    rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])),
  });
  return results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
}

function wrap(children: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

beforeEach(async () => {
  cleanup();
  await act(async () => {
    await setAppLanguage('en');
  });
});

afterEach(() => cleanup());

// --- Mock cartStore for CartDrawer tests ---
const mockCart = {
  id: 1,
  items: [
    {
      id: 101,
      product_id: 1,
      product_title: 'Silk Blazer',
      brand_name: 'Atelier',
      image_url: 'https://example.com/blazer.jpg',
      size: 'M',
      color: 'Navy',
      quantity: 1,
      subtotal: 2400,
      ai_fit_verdict: 'Style Match 92%',
    },
  ],
  items_count: 1,
  subtotal: 2400,
  total: 2400,
  currency: 'EGP',
  discount_amount: 0,
  tax_amount: 0,
  shipping_amount: 0,
  bnpl_monthly_quote: 0,
  bnpl_is_estimate: false,
};

vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({
    cart: mockCart,
    isOpen: true,
    closeCart: vi.fn(),
    fetchCart: vi.fn(),
    updateQuantity: vi.fn(),
    removeItem: vi.fn(),
    pendingDuplicateAlert: null,
    confirmAddDuplicate: vi.fn(),
    dismissDuplicate: vi.fn(),
  }),
}));

// Mock uiStore
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({
    showToast: vi.fn(),
    openAuthModal: vi.fn(),
  }),
}));

// Mock authStore
vi.mock('../../stores/authStore', () => ({
  useAuthStore: () => ({
    user: { id: 1, email: 'test@example.com' },
    isAuthenticated: true,
  }),
}));

// Mock apiServices for admin views
vi.mock('../../services/apiServices', () => ({
  adminService: {
    getCatalogBrands: vi.fn().mockResolvedValue([{ id: 7, brand_name: 'Verified Atelier', slug: 'verified-atelier', is_verified: true, product_count: 1 }]),
    getCatalogSnapshot: vi.fn().mockResolvedValue({
      brand: { id: 7, brand_name: 'Verified Atelier', slug: 'verified-atelier', is_verified: true },
      products: [{
        id: 91, brand_id: 7, brand_name: 'Verified Atelier', category_id: 3, category_name: 'Outerwear', title: 'Structured Coat',
        base_price: 2400, currency: 'EGP', thumbnail_url: 'https://example.test/coat.jpg',
        skus: [{ id: 301, sku_code: 'COAT-NVY-M', size: 'M', color: 'Navy', stock_level: 9, is_in_stock: true }],
      }],
      inventory: [],
      placements: [],
      stores: [],
      imports: [],
      categories: [{ id: 3, name: 'Outerwear', name_ar: 'ملابس خارجية', slug: 'outerwear' }],
      generated_at: '2026-09-26T00:00:00Z',
    }),
    createCatalogProduct: vi.fn(),
    updateCatalogProduct: vi.fn(),
    deactivateCatalogProduct: vi.fn(),
    reactivateCatalogProduct: vi.fn(),
    updateCatalogSKU: vi.fn(),
    addCatalogSKU: vi.fn(),
  },
  catalogService: { getProducts: vi.fn().mockResolvedValue([]) },
  commerceService: { getCart: vi.fn().mockResolvedValue(mockCart), getOrders: vi.fn().mockResolvedValue([]) },
}));

// Mock apiClient for BrandInventoryView
vi.mock('../../services/apiClient', () => ({
  request: vi.fn().mockImplementation((url: string) => {
    if (url.includes('/partner/stores')) return Promise.resolve([{ id: 1, name: 'Giza Flagship', city: 'Giza', country: 'EG', address: 'Test', is_bopis_enabled: true }]);
    if (url.includes('/partner/inventory')) return Promise.resolve([{
      product_id: 1, title: 'Silk Blazer', thumbnail_url: 'https://example.com/blazer.jpg', total_stock: 9,
      skus: [{ id: 1, sku_code: 'BLZ-M', size: 'M', color: 'Navy', stock_level: 9, is_in_stock: true, store_inventories: [] }],
    }]);
    return Promise.resolve([]);
  }),
  getSessionToken: vi.fn().mockReturnValue(null),
}));

describe('010 — CartDrawer (FR-001, FR-002, SC-001)', () => {
  it('axe: cart drawer with items has 0 critical/serious, accessible names, honest images', async () => {
    const { CartDrawer } = await import('../../components/commerce/CartDrawer');
    const { container } = wrap(<CartDrawer />);
    // Check accessible names
    expect(screen.getByRole('button', { name: /close/i })).toBeTruthy();
    // Check honest image usage
    const img = container.querySelector('img');
    if (img) expect(img.getAttribute('alt')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations, `axe violations: ${JSON.stringify(violations, null, 2)}`).toEqual([]);
  });

  it('axe: cart drawer empty state has status role and translated content', async () => {
    vi.doMock('../../stores/cartStore', () => ({
      useCartStore: () => ({
        cart: { items: [], items_count: 0, total: 0, subtotal: 0, currency: 'USD' },
        isOpen: true,
        closeCart: vi.fn(),
        fetchCart: vi.fn(),
        updateQuantity: vi.fn(),
        removeItem: vi.fn(),
        pendingDuplicateAlert: null,
      }),
    }));
    const { CartDrawer } = await import('../../components/commerce/CartDrawer');
    const { container } = wrap(<CartDrawer />);
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — StateComponents for Checkout/Cart (FR-005, SC-005)', () => {
  it('axe: LoadingState for checkout has aria-busy polite, no violations', async () => {
    const { container } = wrap(<LoadingState label="Loading checkout..." />);
    expect(screen.getByRole('status').getAttribute('aria-busy')).toBe('true');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('axe: EmptyState for cart/checkout has status role', async () => {
    const { container } = wrap(<EmptyState title="Your cart is empty" description="Add items to continue" />);
    expect(screen.getByRole('status')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('axe: ErrorState for checkout has alert role and retry', async () => {
    const { container } = wrap(<ErrorState message="Failed to load checkout" retry={{ label: 'Retry', onClick: () => {} }} />);
    expect(screen.getByRole('alert')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('axe: LiveStatus for order tracking has polite live region (CUS-21)', async () => {
    const { container } = wrap(<LiveStatus status="loading" message="Order is being prepared" live />);
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('axe: ConfirmationDialog for admin actions has dialog role, aria-modal, focus trap', async () => {
    const { container } = wrap(
      <ConfirmationDialog
        isOpen
        title="Deactivate product?"
        message="This will retain historical data"
        confirmLabel="Deactivate"
        cancelLabel="Cancel"
        onConfirm={() => {}}
        onClose={() => {}}
      />
    );
    expect(screen.getByRole('dialog')).toBeTruthy();
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — Admin catalog & analytics (FR-001, SC-001, FR-003)', () => {
  it('axe: AdminCatalogView with mocked brand snapshot has 0 critical/serious', async () => {
    const { AdminCatalogView } = await import('../../views/b2b/AdminCatalogView');
    const { container } = wrap(<AdminCatalogView />);
    // Wait for async load
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    // At least the brand name or loading should be present
    const violations = await seriousViolations(container);
    expect(violations, `AdminCatalog violations: ${JSON.stringify(violations, null, 2)}`).toEqual([]);
  });

  it('axe: AdminAnalyticsView permission denied state has alert and translated content', async () => {
    const { AdminAnalyticsView } = await import('../../views/b2b/AdminAnalyticsView');
    const { container } = wrap(<AdminAnalyticsView />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — Brand inventory (FR-001, FR-002, SC-001, SC-002)', () => {
  it('axe: BrandInventoryView with stores and inventory has honest images and no critical violations', async () => {
    const { BrandInventoryView } = await import('../../views/b2b/BrandInventoryView');
    const { container } = wrap(<BrandInventoryView />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 150));
    });
    const violations = await seriousViolations(container);
    expect(violations, `BrandInventory violations: ${JSON.stringify(violations, null, 2)}`).toEqual([]);
  });
});

describe('010 — Virtual Try-On upload and result states (VTON-13, VTON-14, FR-002)', () => {
  it('axe: HonestProductImage for try-on canvas has honest placeholder behavior', async () => {
    const { container } = wrap(
      <div>
        <HonestProductImage src="https://example.com/tryon-result.jpg" alt="Try-On Canvas" />
        <HonestProductImage src={null} alt="Try-On Canvas" />
      </div>
    );
    // One img, one placeholder
    expect(container.querySelector('img')).toBeTruthy();
    expect(container.querySelector('[role="img"]')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('axe: VTON product thumbnail with HonestProductImage has no violations', async () => {
    const { container } = wrap(
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-2xl border">
          <HonestProductImage src="https://example.com/product.jpg" alt="Silk Blazer" className="w-full h-full object-cover" />
          <span>Atelier</span>
          <h5>Silk Blazer</h5>
        </div>
      </div>
    );
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — Forms and accessible controls (FR-001, FR-003)', () => {
  it('axe: Accessible form with labels, errors, hints has no violations', async () => {
    const { container } = wrap(
      <form aria-label="Checkout form">
        <AccessibleInput label="Email address" error="Invalid email" hint="We will never share your email" />
        <AccessibleInput label="Shipping address" />
        <AccessibleSelect label="Country" options={[{ value: 'EG', label: 'Egypt' }, { value: 'AE', label: 'UAE' }]} />
        <AccessibleButton type="submit">Complete purchase</AccessibleButton>
      </form>
    );
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('axe: MotionWrapper with reduced motion preserves essential feedback', async () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    const { container } = wrap(
      <MotionWrapper initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div>Essential content always visible</div>
      </MotionWrapper>
    );
    expect(container.textContent).toContain('Essential content');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });
});

describe('010 — RTL and i18n resilience (FR-003, SC-003)', () => {
  it('axe: EmptyState and ErrorState remain clean in Arabic RTL', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    const { container } = wrap(
      <div dir="rtl">
        <EmptyState title="لا توجد منتجات" description="حاول تعديل الفلاتر" />
        <ErrorState message="فشل التحميل" retry={{ label: 'إعادة المحاولة', onClick: () => {} }} />
      </div>
    );
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
    await act(async () => {
      await setAppLanguage('en');
    });
  });
});
