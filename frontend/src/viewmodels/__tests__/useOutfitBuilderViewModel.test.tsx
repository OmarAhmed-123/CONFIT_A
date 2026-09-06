/**
 * BUILDER-01 / BUILDER-02 regression contract — Outfit Builder canvas state.
 *
 * Audit 2026-09-05: "Draggable item product-N was dropped … but Running Total
 * stayed $0.00 and the slots stayed empty". Two independent defects were
 * verified on main with headless-browser probes:
 *
 *  1. The palette buttons' onClick never fired for real pointer clicks
 *     (PointerSensor had no activationConstraint, so dnd-kit swallowed the
 *     click). View-model side: addItemToCanvas works — proven here by calling
 *     it directly, which is the same code path onClick now reliably reaches
 *     (the 6px drag constraint lives in the view layer and is covered by the
 *     Playwright smoke script).
 *  2. Accessories (clutch/tie) had no canvas slot: they mutated state and the
 *     total while remaining invisible. The view now renders the accessory
 *     slot; this test pins the view-model slot taxonomy that backs it.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

const { checkCompatibilityMock, saveOutfitMock, getProductDetailMock, addItemMock, openCartMock } = vi.hoisted(() => ({
  checkCompatibilityMock: vi.fn().mockResolvedValue({ compatibility_score: 88 }),
  saveOutfitMock: vi.fn().mockResolvedValue({}),
  getProductDetailMock: vi.fn(),
  addItemMock: vi.fn().mockResolvedValue({}),
  openCartMock: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  stylistService: {
    checkCompatibility: (...args: unknown[]) => checkCompatibilityMock(...args),
    saveOutfit: (...args: unknown[]) => saveOutfitMock(...args),
  },
  catalogService: {
    getProductDetail: (...args: unknown[]) => getProductDetailMock(...args),
  },
}));

vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: addItemMock, openCart: openCartMock }),
}));

import { renderHook, act } from '@testing-library/react';
import { useOutfitBuilderViewModel } from '../useOutfitBuilderViewModel';
import { Product, ProductSKU } from '../../models';

const skuOf = (id: number): ProductSKU => ({
  id: id * 100,
  product_id: id,
  sku_code: `SKU-TEST-${id}`,
  size: 'M',
  color: 'Navy',
  color_hex: '#1B1F3B',
  price_override: null,
  stock_level: 9,
  is_in_stock: true,
});

const makeProduct = (id: number, categoryName: string, price = 100, skus?: ProductSKU[]): Product => ({
  id,
  brand_id: 1,
  brand_name: 'Test Brand',
  category_id: 1,
  category_name: categoryName,
  title: `Product ${id} (${categoryName})`,
  title_ar: `منتج ${id}`,
  slug: `product-${id}`,
  base_price: price,
  currency: 'USD',
  thumbnail_url: '',
  color_family: 'Navy',
  dominant_hex: '#1B1F3B',
  style_tags: [],
  occasion_tags: [],
  rating: 4.5,
  style_compatibility_score: 90,
  is_featured: false,
  skus: skus === undefined ? [skuOf(id)] : skus,
});

const blazer = makeProduct(1, 'Outerwear', 289);
const shirt = makeProduct(2, 'Tops & Shirts', 95);
const trousers = makeProduct(3, 'Bottoms & Trousers', 165);
const oxfords = makeProduct(4, 'Footwear', 245);
const clutch = makeProduct(5, 'Accessories', 180);
const tie = makeProduct(6, 'Accessories', 75);

describe('BUILDER: slot taxonomy & canvas state transitions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps every seeded category to its natural slot, accessories included', () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    expect(result.current.naturalSlotForProduct(blazer)).toBe('outerwear');
    expect(result.current.naturalSlotForProduct(shirt)).toBe('top');
    expect(result.current.naturalSlotForProduct(trousers)).toBe('bottom');
    expect(result.current.naturalSlotForProduct(oxfords)).toBe('footwear');
    // The audit's exact complaint: clutch/tie must have a destination slot.
    expect(result.current.naturalSlotForProduct(clutch)).toBe('accessory');
    expect(result.current.naturalSlotForProduct(tie)).toBe('accessory');
  });

  it('click-to-add fills the matching slot and moves the running total off $0.00', () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel(450));
    expect(result.current.runningTotal).toBe(0);

    act(() => result.current.addItemToCanvas(blazer));
    act(() => result.current.addItemToCanvas(shirt));
    act(() => result.current.addItemToCanvas(clutch));

    expect(result.current.selectedItems).toHaveLength(3);
    expect(result.current.runningTotal).toBeCloseTo(289 + 95 + 180);
    expect(result.current.selectedItems.find((i) => i.slot === 'accessory')?.product.id).toBe(5);
  });

  it('adding into the same slot replaces the previous piece instead of duplicating', () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => result.current.addItemToCanvas(shirt));
    act(() => result.current.addItemToCanvas(makeProduct(9, 'Tops & Shirts', 120)));
    expect(result.current.selectedItems).toHaveLength(1);
    expect(result.current.selectedItems[0].product.id).toBe(9);
    expect(result.current.runningTotal).toBeCloseTo(120);
  });

  it('an explicit wrong-slot assignment is rejected by the validator (drag parity with click)', () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    expect(result.current.isValidSlotForProduct(clutch, 'outerwear')).toBe(false);
    expect(result.current.isValidSlotForProduct(clutch, 'accessory')).toBe(true);
    expect(result.current.isValidSlotForProduct(blazer, 'outerwear')).toBe(true);
    expect(result.current.isValidSlotForProduct(oxfords, 'top')).toBe(false);
  });

  it('remove and clear return the canvas to a $0.00 idle state', () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => result.current.addItemToCanvas(blazer));
    act(() => result.current.addItemToCanvas(clutch));
    act(() => result.current.removeItemFromCanvas('accessory'));
    expect(result.current.selectedItems).toHaveLength(1);
    expect(result.current.runningTotal).toBeCloseTo(289);
    act(() => result.current.clearCanvas());
    expect(result.current.selectedItems).toHaveLength(0);
    expect(result.current.runningTotal).toBe(0);
  });

  // BUILDER-03 (2026-09-06 remediation): catalog list products carry no SKUs,
  // and the old view-model fabricated one (id = product.id*10, fake stock) —
  // every 'Add Complete Look to Bag' then 409'd server-side. Real SKUs must be
  // resolved from the detail endpoint; fabricated ids must never be posted.
  it('BUILDER-03: sku-less product resolves its real SKU asynchronously', async () => {
    getProductDetailMock.mockResolvedValue({ ...shirt, skus: [skuOf(2)] });
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => result.current.addItemToCanvas(makeProduct(2, 'Tops & Shirts', 95, [])));
    expect(result.current.selectedItems[0].skuStatus).toBe('pending');
    expect(result.current.selectedItems[0].selectedSku).toBeNull();
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(result.current.selectedItems[0].skuStatus).toBe('ready');
    expect(result.current.selectedItems[0].selectedSku?.id).toBe(200);
    expect(result.current.selectedItems[0].selectedSku?.stock_level).toBeGreaterThan(0);
  });

  it('BUILDER-03: add-all-to-bag refuses while a SKU is still pending (no fabricated POST)', async () => {
    getProductDetailMock.mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => result.current.addItemToCanvas(makeProduct(2, 'Tops & Shirts', 95, [])));
    await act(async () => { await result.current.addAllToCart(); });
    expect(addItemMock).not.toHaveBeenCalled();
  });

  it('BUILDER-03: detail-fetch failure marks the item unavailable and blocks the bag add', async () => {
    getProductDetailMock.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => result.current.addItemToCanvas(makeProduct(2, 'Tops & Shirts', 95, [])));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(result.current.selectedItems[0].skuStatus).toBe('unavailable');
    await act(async () => { await result.current.addAllToCart(); });
    expect(addItemMock).not.toHaveBeenCalled();
    expect(result.current.selectedItems).toHaveLength(1); // stays on canvas, honestly labelled
  });

  it('BUILDER-03: ready items post only their real server SKU ids', async () => {
    const { result } = renderHook(() => useOutfitBuilderViewModel());
    act(() => result.current.addItemToCanvas(blazer)); // inline in-stock sku: id 100
    act(() => result.current.addItemToCanvas(oxfords)); // id 400
    await act(async () => { await result.current.addAllToCart(); });
    expect(addItemMock).toHaveBeenCalledTimes(2);
    const postedIds = addItemMock.mock.calls.map((c) => c[0]);
    expect(postedIds).toEqual([100, 400]);
    expect(postedIds.every((id) => id % 100 === 0 && id > 0)).toBe(true);
  });
});
