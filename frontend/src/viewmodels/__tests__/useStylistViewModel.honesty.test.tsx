import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  addItem: vi.fn().mockResolvedValue({}),
  openCart: vi.fn(),
  showToast: vi.fn(),
  chat: vi.fn(),
}));

vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: mocks.addItem, openCart: mocks.openCart }),
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: mocks.showToast }),
}));

vi.mock('../../services/apiServices', () => ({
  stylistService: { chat: mocks.chat },
}));

import { useStylistViewModel } from '../useStylistViewModel';

describe('STYLIST honesty contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not fabricate fallback cart items when a stylist outfit has no verified catalog items', async () => {
    const { result } = renderHook(() => useStylistViewModel());

    await act(async () => {
      await result.current.addCompleteLookToCart({ id: 55, title: 'Empty Recommendation', items: [] } as any);
    });

    expect(mocks.addItem).not.toHaveBeenCalled();
    expect(mocks.openCart).not.toHaveBeenCalled();
    expect(mocks.showToast).toHaveBeenCalledWith(
      expect.stringContaining('no verified catalog items'),
      'error',
    );
  });

  it('does not synthesize SKU ids for malformed stylist items', async () => {
    const { result } = renderHook(() => useStylistViewModel());

    await act(async () => {
      await result.current.addCompleteLookToCart({
        id: 77,
        title: 'Malformed Recommendation',
        items: [{ product_id: 10, product_title: 'Catalog Item Missing SKU', category_name: 'Tops', color_hex: '#000000' }],
      } as any);
    });

    expect(mocks.addItem).not.toHaveBeenCalled();
    expect(mocks.openCart).not.toHaveBeenCalled();
    expect(mocks.showToast).toHaveBeenCalledWith(
      expect.stringContaining('missing verified SKU data'),
      'error',
    );
  });

});
