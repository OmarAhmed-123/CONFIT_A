/**
 * P0-01b / P0-01e regression contract — cart failure honesty + guest merge.
 * - addItem failure must toast (never silent) and keep last known cart.
 * - syncAfterLogin merges a non-empty guest cart via the server merge endpoint.
 * - merge failure falls back to fetchCart with an honest error toast.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

const { mergeMock, fetchCartServiceMock, addToCartMock, showToastMock } = vi.hoisted(() => ({
  mergeMock: vi.fn(),
  fetchCartServiceMock: vi.fn(),
  addToCartMock: vi.fn(),
  showToastMock: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  commerceService: {
    getCart: (...a: unknown[]) => fetchCartServiceMock(...a),
    addToCart: (...a: unknown[]) => addToCartMock(...a),
    mergeGuestCart: (...a: unknown[]) => mergeMock(...a),
  },
  wardrobeService: {},
}));

vi.mock('../../services/apiClient', () => ({
  getSessionToken: () => 'sess_test_guest_1',
}));

vi.mock('../uiStore', () => ({
  useUIStore: {
    getState: () => ({ showToast: showToastMock }),
    subscribe: () => () => {},
  },
}));

vi.mock('../authStore', () => ({
  useAuthStore: {
    getState: () => ({ isAuthenticated: false }),
    subscribe: () => () => {},
  },
}));

import { useCartStore } from '../cartStore';
import { Cart } from '../../models';

const cartWith = (n: number): Cart => ({
  id: 1, user_id: null, status: 'active', items_count: n, subtotal: 100 * n,
  discount: 0, tax: 0, shipping: 0, total: 100 * n, currency: 'USD', promo_code: null,
  bnpl_monthly_quote: 0,
  items: Array.from({ length: n }, (_, i) => ({ id: i + 1, product_sku_id: 100 + i, quantity: 1 })),
  fit_summary: [],
} as unknown as Cart);

describe('P0-01b: add-to-bag failure is never silent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useCartStore.setState({ cart: cartWith(1), error: null, isLoading: false });
  });

  it('toasts the failure and preserves the previous cart state', async () => {
    addToCartMock.mockRejectedValueOnce(Object.assign(new Error('Network error'), { message: 'Network error' }));
    await expect(
      useCartStore.getState().addItem(99, { id: 9, title: 'X', category: 'Tops', color: 'Navy' })
    ).rejects.toThrow('Network error');
    expect(showToastMock).toHaveBeenCalledWith(expect.stringMatching(/network error|could not add/i), 'error');
    expect(useCartStore.getState().cart?.items_count).toBe(1); // no fake success
    expect(useCartStore.getState().error).toBeTruthy();
  });
});

describe('P0-01e: guest cart merges into the authenticated cart on login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('calls the server merge with the guest token and adopts the merged cart', async () => {
    const merged = cartWith(3);
    // simulate a persisted guest cart with items
    localStorage.setItem('confit_cart', JSON.stringify(cartWith(2)));
    mergeMock.mockResolvedValueOnce(merged);

    await useCartStore.getState().syncAfterLogin();

    expect(mergeMock).toHaveBeenCalledWith('sess_test_guest_1');
    expect(useCartStore.getState().cart?.items_count).toBe(3);
    expect(showToastMock).toHaveBeenCalledWith(expect.stringMatching(/bag followed you/i), 'success');
  });

  it('falls back to fetchCart and toasts honestly when the merge call fails', async () => {
    localStorage.setItem('confit_cart', JSON.stringify(cartWith(2)));
    mergeMock.mockRejectedValueOnce(new Error('boom'));
    fetchCartServiceMock.mockResolvedValueOnce(cartWith(0));

    await useCartStore.getState().syncAfterLogin();

    expect(showToastMock).toHaveBeenCalledWith(expect.stringMatching(/could not transfer/i), 'error');
    expect(fetchCartServiceMock).toHaveBeenCalled();
    expect(useCartStore.getState().cart?.items_count).toBe(0);
  });

  it('skips the merge call when the guest bag was empty', async () => {
    await useCartStore.getState().syncAfterLogin();
    expect(mergeMock).not.toHaveBeenCalled();
    expect(fetchCartServiceMock).toHaveBeenCalled();
  });
});
