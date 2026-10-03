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
    // The toast is now a descriptor; the honest failure detail is carried in
    // params.reason, so the assertion is that the key AND the real error text
    // both survive — never a fabricated success message.
    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({
        key: 'errors.generic',
        params: expect.objectContaining({ reason: expect.stringMatching(/network error/i) }),
      }),
      'error',
    );
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
    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'toast.bag_transferred', params: { count: 3 } }),
      'success',
    );
  });

  it('falls back to fetchCart and toasts honestly when the merge call fails', async () => {
    localStorage.setItem('confit_cart', JSON.stringify(cartWith(2)));
    mergeMock.mockRejectedValueOnce(new Error('boom'));
    fetchCartServiceMock.mockResolvedValueOnce(cartWith(0));

    await useCartStore.getState().syncAfterLogin();

    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'toast.bag_transfer_failed' }),
      'error',
    );
    expect(fetchCartServiceMock).toHaveBeenCalled();
    expect(useCartStore.getState().cart?.items_count).toBe(0);
  });

  it('skips the merge call when the guest bag was empty', async () => {
    await useCartStore.getState().syncAfterLogin();
    expect(mergeMock).not.toHaveBeenCalled();
    expect(fetchCartServiceMock).toHaveBeenCalled();
  });
});

describe('spec "flight feedback" §5: a duplicate SKU surfaces the MERGED quantity', () => {
  const lineCart = (skuId: number, qty: number): Cart => ({
    ...cartWith(1),
    items: [{ id: 7, product_sku_id: skuId, quantity: qty }],
  } as unknown as Cart);

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('re-adding an existing SKU resolves { merged: true } with the server-grown quantity', async () => {
    useCartStore.setState({ cart: lineCart(500, 1), error: null, isLoading: false });
    addToCartMock.mockResolvedValueOnce(lineCart(500, 2));

    const res = await useCartStore.getState().addItem(500);

    expect(res).toEqual({ merged: true, quantity: 2 });
    // The claim comes from the server's cart, which the store also adopted.
    expect(useCartStore.getState().cart?.items[0].quantity).toBe(2);
  });

  it('a brand-new SKU resolves { merged: false } — no fake "merged" talk', async () => {
    useCartStore.setState({ cart: lineCart(500, 1), error: null, isLoading: false });
    addToCartMock.mockResolvedValueOnce({
      ...cartWith(2),
      items: [
        { id: 7, product_sku_id: 500, quantity: 1 },
        { id: 8, product_sku_id: 600, quantity: 1 },
      ],
    } as unknown as Cart);

    const res = await useCartStore.getState().addItem(600);

    expect(res).toEqual({ merged: false, quantity: 1 });
  });

  it('confirmAddDuplicate announces the merged quantity in words when the line grew', async () => {
    useCartStore.setState({
      cart: lineCart(500, 1),
      error: null,
      isLoading: false,
      pendingDuplicateAlert: {
        product_sku_id: 500,
        quantity: 1,
        owned_item: { id: 1 } as never,
        alert_message: 'similar piece',
      },
    } as never);
    addToCartMock.mockResolvedValueOnce(lineCart(500, 2));

    await useCartStore.getState().confirmAddDuplicate();

    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'toast.bag_quantity_merged', params: { count: 2 } }),
      'success',
    );
  });

  it('confirmAddDuplicate falls back to the plain added message for a fresh line', async () => {
    useCartStore.setState({
      cart: { ...cartWith(0), items: [] } as unknown as Cart,
      error: null,
      isLoading: false,
      pendingDuplicateAlert: {
        product_sku_id: 500,
        quantity: 1,
        owned_item: { id: 1 } as never,
        alert_message: 'similar piece',
      },
    } as never);
    addToCartMock.mockResolvedValueOnce(lineCart(500, 1));

    await useCartStore.getState().confirmAddDuplicate();

    expect(showToastMock).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'toast.added_to_bag' }),
      'success',
    );
  });
});
