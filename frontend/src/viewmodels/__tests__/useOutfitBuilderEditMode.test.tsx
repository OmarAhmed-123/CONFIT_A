import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * OUTFIT-03/04 — editing an existing look, and honest save gating.
 *
 * Before this work `/outfits/:id` mounted an EMPTY builder, so "edit" silently
 * created a duplicate look and the original was never touched. These tests
 * pin the corrected behaviour and the server-authoritative save gate.
 */

const checkCompatibilityMock = vi.fn<(...args: any[]) => any>(async () => ({ compatibility_score: 90 }));
const saveOutfitMock = vi.fn<(...args: any[]) => any>(async () => ({ id: 99 }));
const previewCompositionMock = vi.fn<(...args: any[]) => any>();
const getOutfitMock = vi.fn<(...args: any[]) => any>();
const replaceOutfitItemsMock = vi.fn<(...args: any[]) => any>(async () => ({ id: 7 }));
const updateOutfitMock = vi.fn<(...args: any[]) => any>(async () => ({ id: 7 }));
const getProductDetailMock = vi.fn<(...args: any[]) => any>();
const getProductByIdMock = vi.fn<(...args: any[]) => any>();
const showToastMock = vi.fn();
const addItemMock = vi.fn();
const openCartMock = vi.fn();

vi.mock('../../services/apiServices', () => ({
  stylistService: {
    checkCompatibility: (...a: unknown[]) => checkCompatibilityMock(...a),
    saveOutfit: (...a: unknown[]) => saveOutfitMock(...a),
    previewComposition: (...a: unknown[]) => previewCompositionMock(...a),
    getOutfit: (...a: unknown[]) => getOutfitMock(...a),
    replaceOutfitItems: (...a: unknown[]) => replaceOutfitItemsMock(...a),
    updateOutfit: (...a: unknown[]) => updateOutfitMock(...a),
  },
  catalogService: {
    getProductDetail: (...a: unknown[]) => getProductDetailMock(...a),
    getProductById: (...a: unknown[]) => getProductByIdMock(...a),
  },
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: showToastMock }),
}));
vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: addItemMock, openCart: openCartMock }),
}));

import { renderHook, act, waitFor } from '@testing-library/react';
import { useOutfitBuilderViewModel } from '../useOutfitBuilderViewModel';

const VALID = {
  is_valid: true,
  violations: [],
  warnings: [],
  missing_positions: [],
  resolved_items: [],
  unresolved_ids: [],
};

const product = (id: number, category: string) => ({
  id,
  slug: `p-${id}`,
  title: `Product ${id}`,
  brand_name: 'CONFIT',
  category_name: category,
  base_price: 100,
  thumbnail_url: '',
  color_family: 'Navy',
  skus: [
    {
      id: id * 100,
      product_id: id,
      sku_code: `SKU-${id}`,
      size: 'M',
      color: 'Navy',
      color_hex: '#1B1F3B',
      price_override: null,
      stock_level: 5,
      is_in_stock: true,
    },
  ],
});

describe('BUILDER edit mode + server-authoritative save gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    previewCompositionMock.mockResolvedValue(VALID);
  });

  it('hydrates the canvas from the saved look being edited', async () => {
    getOutfitMock.mockResolvedValue({
      id: 7,
      title: 'Saved Boardroom',
      occasion: 'Executive Boardroom',
      items: [
        { id: 1, product_id: 1, position: 'top', sku_id: 100 },
        { id: 2, product_id: 2, position: 'bottom', sku_id: 200 },
      ],
    });
    getProductByIdMock.mockImplementation(async (id: number) =>
      product(id, id === 1 ? 'Tops' : 'Bottoms'),
    );

    const { result } = renderHook(() => useOutfitBuilderViewModel(450, 7));
    await waitFor(() => expect(result.current.isLoadingExisting).toBe(false));

    expect(result.current.isEditing).toBe(true);
    expect(result.current.outfitTitle).toBe('Saved Boardroom');
    expect(result.current.targetOccasion).toBe('Executive Boardroom');
    expect(result.current.selectedItems).toHaveLength(2);
    // The exact stored SKU is restored, not "some in-stock SKU".
    expect(result.current.selectedItems[0].selectedSku?.id).toBe(100);
  });

  it('saving while editing UPDATES the look instead of creating a duplicate', async () => {
    getOutfitMock.mockResolvedValue({
      id: 7,
      title: 'Saved Boardroom',
      occasion: 'Executive Boardroom',
      items: [{ id: 1, product_id: 1, position: 'top', sku_id: 100 }],
    });
    getProductByIdMock.mockResolvedValue(product(1, 'Tops'));

    const { result } = renderHook(() => useOutfitBuilderViewModel(450, 7));
    await waitFor(() => expect(result.current.isLoadingExisting).toBe(false));
    await waitFor(() => expect(result.current.verdict).not.toBeNull());

    await act(async () => {
      await result.current.saveOutfit();
    });

    expect(replaceOutfitItemsMock).toHaveBeenCalledWith(7, {
      product_sku_ids: [100],
    });
    expect(updateOutfitMock).toHaveBeenCalled();
    // The critical assertion: no duplicate look is created.
    expect(saveOutfitMock).not.toHaveBeenCalled();
  });

  it('creating a new look still POSTs a new outfit', async () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel(450));
    act(() => {
      result.current.addItemToCanvas(product(1, 'Tops') as never);
    });
    await waitFor(() => expect(result.current.verdict).not.toBeNull());
    await act(async () => {
      await result.current.saveOutfit();
    });
    expect(saveOutfitMock).toHaveBeenCalled();
    expect(replaceOutfitItemsMock).not.toHaveBeenCalled();
  });

  it('an invalid server verdict blocks the save and states the reason', async () => {
    previewCompositionMock.mockResolvedValue({
      ...VALID,
      is_valid: false,
      violations: [
        {
          code: 'slot_over_capacity',
          message: 'The bottom slot holds 1 item(s), but 2 were supplied.',
          positions: ['bottom'],
        },
      ],
    });

    const { result } = renderHook(() => useOutfitBuilderViewModel(450));
    act(() => {
      result.current.addItemToCanvas(product(1, 'Tops') as never);
    });
    await waitFor(() => expect(result.current.verdict?.is_valid).toBe(false));

    await act(async () => {
      await result.current.saveOutfit();
    });

    expect(saveOutfitMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'The bottom slot holds 1 item(s), but 2 were supplied.',
      'error',
    );
  });

  it('reports a load failure rather than silently showing a blank canvas', async () => {
    getOutfitMock.mockRejectedValue({ status: 404 });
    const { result } = renderHook(() => useOutfitBuilderViewModel(450, 404));
    await waitFor(() => expect(result.current.isLoadingExisting).toBe(false));
    expect(result.current.loadError).toContain('does not exist');
    expect(result.current.selectedItems).toHaveLength(0);
  });

  it('warns honestly when only some stored items could be rehydrated', async () => {
    getOutfitMock.mockResolvedValue({
      id: 8,
      title: 'Partly loadable',
      occasion: 'Casual',
      items: [
        { id: 1, product_id: 1, position: 'top', sku_id: 100 },
        { id: 2, product_id: 2, position: 'bottom', sku_id: 200 },
      ],
    });
    getProductByIdMock.mockImplementation(async (id: number) => {
      if (id === 2) throw new Error('gone');
      return product(1, 'Tops');
    });

    const { result } = renderHook(() => useOutfitBuilderViewModel(450, 8));
    await waitFor(() => expect(result.current.isLoadingExisting).toBe(false));
    expect(result.current.selectedItems).toHaveLength(1);
    expect(showToastMock).toHaveBeenCalledWith(
      expect.stringContaining('could not be loaded'),
      'error',
    );
  });
});
