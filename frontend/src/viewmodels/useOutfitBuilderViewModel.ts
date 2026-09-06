import { useState, useCallback, useMemo, useEffect } from 'react';
import { stylistService, catalogService } from '../services/apiServices';
import { Product, ProductSKU } from '../models';
import { useUIStore } from '../stores/uiStore';
import { useCartStore } from '../stores/cartStore';

export interface CanvasItem {
  product: Product;
  selectedSku: ProductSKU | null;
  slot: 'outerwear' | 'top' | 'bottom' | 'footwear' | 'accessory';
  /** 'ready' = a real, server-verified SKU is selected. 'pending' = fetching
   *  the product's real SKUs. 'unavailable' = no purchasable SKU exists. */
  skuStatus: 'ready' | 'pending' | 'unavailable';
}

export function useOutfitBuilderViewModel(userBudgetLimit = 400.0) {
  const [selectedItems, setSelectedItems] = useState<CanvasItem[]>([]);
  const [targetOccasion, setTargetOccasion] = useState('Smart Casual Work');
  const [outfitTitle, setOutfitTitle] = useState('My Custom Tailored Ensemble');
  const [compatibility, setCompatibility] = useState<any>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const { showToast } = useUIStore();
  const { addItem, openCart } = useCartStore();

  // Calculate live running budget
  const runningTotal = useMemo(() => {
    return selectedItems.reduce((acc, item) => {
      const price = (item.selectedSku && item.selectedSku.price_override) || item.product.base_price;
      return acc + price;
    }, 0);
  }, [selectedItems]);

  const isOverBudget = runningTotal > userBudgetLimit;

  // Derive the product's natural canvas slot from its category (single place
  // used by both click-to-add and drag validation).
  const naturalSlotForProduct = useCallback((product: Product): CanvasItem['slot'] => {
    const cat = (product.category_name || '').toLowerCase();
    if (cat.includes('outer') || cat.includes('blazer') || cat.includes('jacket') || cat.includes('coat')) return 'outerwear';
    if (cat.includes('bottom') || cat.includes('trouser') || cat.includes('pant') || cat.includes('jean') || cat.includes('skirt')) return 'bottom';
    if (cat.includes('shoe') || cat.includes('footwear') || cat.includes('sneaker') || cat.includes('loafer') || cat.includes('boot') || cat.includes('heel')) return 'footwear';
    if (cat.includes('accessor') || cat.includes('bag') || cat.includes('belt') || cat.includes('watch')) return 'accessory';
    return 'top';
  }, []);

  // C6: a drop is valid only when the target slot matches the product's
  // natural slot — invalid drops must never corrupt canvas state.
  const isValidSlotForProduct = useCallback(
    (product: Product, slot: CanvasItem['slot']) => naturalSlotForProduct(product) === slot,
    [naturalSlotForProduct]
  );

  const addItemToCanvas = useCallback((product: Product, slot?: CanvasItem['slot']) => {
    const assignedSlot = slot ?? naturalSlotForProduct(product);

    // Only ever use real, server-verified SKUs. Catalog list responses do not
    // embed SKUs, so when none are present we fetch the product detail and
    // resolve asynchronously — never fabricate a placeholder SKU (a made-up id
    // would be rejected by POST /commerce/cart/items with a 409).
    const inlineSku =
      product.skus?.find((s) => s.is_in_stock && s.stock_level > 0) ?? product.skus?.[0] ?? null;

    setSelectedItems((prev) => {
      // Replace if slot already occupied or append
      const filtered = prev.filter((i) => i.slot !== assignedSlot);
      return [
        ...filtered,
        {
          product,
          selectedSku: inlineSku,
          slot: assignedSlot!,
          skuStatus: inlineSku ? ('ready' as const) : ('pending' as const),
        },
      ];
    });

    if (!inlineSku) {
      catalogService
        .getProductDetail(product.slug)
        .then((detail) => {
          const realSku =
            (detail.skus ?? []).find((s) => s.is_in_stock && s.stock_level > 0) ??
            detail.skus?.[0] ??
            null;
          setSelectedItems((prev) =>
            prev.map((it) =>
              it.slot === assignedSlot && it.product.id === product.id
                ? {
                    ...it,
                    product: { ...it.product, ...detail },
                    selectedSku: realSku,
                    skuStatus: realSku ? ('ready' as const) : ('unavailable' as const),
                  }
                : it
            )
          );
          if (!realSku) {
            showToast(`No purchasable size found for ${product.title}`, 'error');
          }
        })
        .catch(() => {
          setSelectedItems((prev) =>
            prev.map((it) =>
              it.slot === assignedSlot && it.product.id === product.id
                ? { ...it, skuStatus: 'unavailable' as const }
                : it
            )
          );
          showToast(`Couldn't load sizes for ${product.title} — try again`, 'error');
        });
    }
  }, [showToast]);

  const removeItemFromCanvas = useCallback((slot: CanvasItem['slot']) => {
    setSelectedItems((prev) => prev.filter((i) => i.slot !== slot));
  }, []);

  const clearCanvas = useCallback(() => {
    setSelectedItems([]);
    setCompatibility(null);
  }, []);

  // Live evaluate compatibility whenever items or occasion change
  useEffect(() => {
    if (selectedItems.length === 0) {
      setCompatibility(null);
      return;
    }

    const pids = selectedItems.map((i) => i.product.id);
    setIsEvaluating(true);
    stylistService
      .checkCompatibility(pids, targetOccasion)
      .then((res) => {
        setCompatibility(res);
        setIsEvaluating(false);
      })
      .catch(() => {
        setIsEvaluating(false);
      });
  }, [selectedItems, targetOccasion]);

  const saveOutfit = useCallback(async () => {
    if (selectedItems.length === 0) return;
    const ready = selectedItems.filter((i) => i.skuStatus === 'ready' && i.selectedSku);
    if (ready.length === 0) {
      showToast('Cannot save yet — no item has a confirmed purchasable size.', 'error');
      return;
    }
    setIsSaving(true);
    try {
      await stylistService.saveOutfit({
        title: outfitTitle,
        occasion: targetOccasion,
        product_sku_ids: ready.map((i) => i.selectedSku!.id),
      });
      setIsSaving(false);
      showToast('Ensemble saved to My Looks!', 'success');
    } catch (err: any) {
      setIsSaving(false);
      showToast('Error saving outfit: ' + err.message, 'error');
    }
  }, [selectedItems, outfitTitle, targetOccasion, showToast]);

  const addAllToCart = useCallback(async () => {
    if (selectedItems.length === 0) return;
    if (selectedItems.some((i) => i.skuStatus === 'pending')) {
      showToast('Still confirming sizes — try again in a moment.', 'error');
      return;
    }
    const ready = selectedItems.filter((i) => i.skuStatus === 'ready' && i.selectedSku);
    const skipped = selectedItems.length - ready.length;
    if (ready.length === 0) {
      showToast('No item has a purchasable size — open a product page to pick one.', 'error');
      return;
    }
    for (const item of ready) {
      await addItem(item.selectedSku!.id, {
        id: item.product.id,
        title: item.product.title,
        category: item.product.category_name,
        color: item.product.color_family,
      });
    }
    showToast(
      skipped > 0
        ? `Added ${ready.length} items to Bag. ${skipped} skipped (size unavailable).`
        : `Added ${ready.length} items from builder to Bag!`,
      skipped > 0 ? 'info' : 'success'
    );
    openCart();
  }, [selectedItems, addItem, openCart, showToast]);

  return {
    selectedItems,
    targetOccasion,
    setTargetOccasion,
    outfitTitle,
    setOutfitTitle,
    runningTotal,
    userBudgetLimit,
    isOverBudget,
    compatibility,
    isEvaluating,
    isSaving,
    addItemToCanvas,
    naturalSlotForProduct,
    isValidSlotForProduct,
    removeItemFromCanvas,
    clearCanvas,
    saveOutfit,
    addAllToCart,
  };
}
