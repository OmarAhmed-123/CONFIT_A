import { msg, detail, TranslatableMessage } from '../i18n/messages';
import { useState, useCallback, useMemo, useEffect } from 'react';
import { stylistService, catalogService } from '../services/apiServices';
import { CompositionVerdict, Product, ProductSKU } from '../models';
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

/**
 * @param userBudgetLimit running-budget target for the canvas.
 * @param editingOutfitId when set, the builder LOADS that saved look and Save
 *   updates it in place instead of creating a duplicate. Before OUTFIT-03 the
 *   /outfits/:id route mounted an empty builder, so "edit" silently created a
 *   second look and the original was never touched.
 */
export function useOutfitBuilderViewModel(
  userBudgetLimit = 400.0,
  editingOutfitId?: number,
) {
  const [selectedItems, setSelectedItems] = useState<CanvasItem[]>([]);
  const [targetOccasion, setTargetOccasion] = useState('Smart Casual Work');
  const [outfitTitle, setOutfitTitle] = useState('My Custom Tailored Ensemble');
  const [compatibility, setCompatibility] = useState<any>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingExisting, setIsLoadingExisting] = useState(Boolean(editingOutfitId));
  // A translatable descriptor, resolved at the render boundary (i18n contract).
  const [loadError, setLoadError] = useState<TranslatableMessage | null>(null);
  // Server-side composition verdict for the CURRENT canvas. The Save button is
  // gated on this, so the UI can never claim a look is savable when the policy
  // will reject it (and vice versa) — same rules, one source of truth.
  const [verdict, setVerdict] = useState<CompositionVerdict | null>(null);

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
            showToast(msg('toast.no_purchasable_size_for', { title: product.title }), 'error');
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
          showToast(msg('toast.size_load_failed_for', { title: product.title }), 'error');
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

  // OUTFIT-03: hydrate the canvas from a saved look when editing one.
  useEffect(() => {
    if (!editingOutfitId) return;
    let cancelled = false;
    setIsLoadingExisting(true);
    setLoadError(null);
    stylistService
      .getOutfit(editingOutfitId)
      .then(async (outfit) => {
        if (cancelled) return;
        setOutfitTitle(outfit.title);
        setTargetOccasion(outfit.occasion);
        // Resolve each stored item back to a full product so the canvas can
        // re-render, re-price and re-validate it exactly like a fresh pick.
        const hydrated = await Promise.all(
          outfit.items.map(async (item) => {
            try {
              const product = await catalogService.getProductById(item.product_id);
              const sku =
                (product.skus ?? []).find((s) => s.id === item.sku_id) ??
                (product.skus ?? []).find((s) => s.is_in_stock && s.stock_level > 0) ??
                null;
              return {
                product,
                selectedSku: sku,
                slot: item.position as CanvasItem['slot'],
                skuStatus: (sku ? 'ready' : 'unavailable') as CanvasItem['skuStatus'],
              };
            } catch {
              return null;
            }
          }),
        );
        if (cancelled) return;
        const usable = hydrated.filter(Boolean) as CanvasItem[];
        setSelectedItems(usable);
        if (usable.length !== outfit.items.length) {
          // Honest partial-load message rather than a silently smaller canvas.
          showToast(
            msg('toast.look_items_partially_loaded', {
              count: outfit.items.length - usable.length,
            }),
            'error',
          );
        }
        setIsLoadingExisting(false);
      })
      .catch((err: any) => {
        if (cancelled) return;
        setLoadError(
          err?.status === 404
            ? msg('outfit_builder.look_not_found')
            : msg('outfit_builder.look_load_failed'),
        );
        setIsLoadingExisting(false);
      });
    return () => {
      cancelled = true;
    };
  }, [editingOutfitId, showToast]);

  // Server-authoritative composition validity for the current canvas.
  useEffect(() => {
    const ready = selectedItems.filter((i) => i.skuStatus === 'ready' && i.selectedSku);
    if (ready.length === 0) {
      setVerdict(null);
      return;
    }
    let cancelled = false;
    stylistService
      .previewComposition({ product_sku_ids: ready.map((i) => i.selectedSku!.id) })
      .then((v) => !cancelled && setVerdict(v))
      .catch(() => !cancelled && setVerdict(null));
    return () => {
      cancelled = true;
    };
  }, [selectedItems]);

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
      showToast(msg('toast.cannot_save_no_sku'), 'error');
      return;
    }
    // Do not even attempt a save the server will reject: show the real reason.
    if (verdict && !verdict.is_valid) {
      showToast(
        verdict.violations[0]?.message ?? msg('toast.invalid_combination'),
        'error',
      );
      return;
    }
    setIsSaving(true);
    const skuIds = ready.map((i) => i.selectedSku!.id);
    try {
      if (editingOutfitId) {
        // Edit in place — atomic whole-set replacement, then the title/occasion.
        await stylistService.replaceOutfitItems(editingOutfitId, {
          product_sku_ids: skuIds,
        });
        await stylistService.updateOutfit(editingOutfitId, {
          title: outfitTitle,
          occasion: targetOccasion,
        });
        showToast(msg('toast.look_updated'), 'success');
      } else {
        await stylistService.saveOutfit({
          title: outfitTitle,
          occasion: targetOccasion,
          product_sku_ids: skuIds,
        });
        showToast(msg('toast.ensemble_saved'), 'success');
      }
      setIsSaving(false);
      return true;
    } catch (err: any) {
      setIsSaving(false);
      // Surface the server's explainable composition reason verbatim, falling
      // back to the shared error formatter for non-policy failures.
      const raw = err?.data?.detail;
      const reason =
        (raw && typeof raw === 'object' && raw.message) ||
        (typeof raw === 'string' && raw) ||
        detail(err);
      showToast(msg('toast.outfit_save_failed', { reason }), 'error');
      return false;
    }
  }, [selectedItems, outfitTitle, targetOccasion, showToast, verdict, editingOutfitId]);

  const addAllToCart = useCallback(async () => {
    if (selectedItems.length === 0) return;
    if (selectedItems.some((i) => i.skuStatus === 'pending')) {
      showToast(msg('toast.confirming_sizes'), 'error');
      return;
    }
    const ready = selectedItems.filter((i) => i.skuStatus === 'ready' && i.selectedSku);
    const skipped = selectedItems.length - ready.length;
    if (ready.length === 0) {
      showToast(msg('toast.no_item_has_size'), 'error');
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
    isLoadingExisting,
    loadError,
    verdict,
    isEditing: Boolean(editingOutfitId),
    addItemToCanvas,
    naturalSlotForProduct,
    isValidSlotForProduct,
    removeItemFromCanvas,
    clearCanvas,
    saveOutfit,
    addAllToCart,
  };
}
