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

const { checkCompatibilityMock, saveOutfitMock } = vi.hoisted(() => ({
  checkCompatibilityMock: vi.fn().mockResolvedValue({ compatibility_score: 88 }),
  saveOutfitMock: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../services/apiServices', () => ({
  stylistService: {
    checkCompatibility: (...args: unknown[]) => checkCompatibilityMock(...args),
    saveOutfit: (...args: unknown[]) => saveOutfitMock(...args),
  },
  catalogService: {},
}));

import { renderHook, act } from '@testing-library/react';
import { useOutfitBuilderViewModel } from '../useOutfitBuilderViewModel';
import { Product } from '../../models';

const makeProduct = (id: number, categoryName: string, price = 100): Product => ({
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
});
