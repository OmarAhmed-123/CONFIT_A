import { msg, detail, TranslatableMessage } from '../i18n/messages';
import i18n from '../i18n/i18n';
import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { stylistService, catalogService } from '../services/apiServices';
import { CompositionVerdict, Product, ProductSKU } from '../models';
import { useUIStore } from '../stores/uiStore';
import { useCartStore } from '../stores/cartStore';
import { useAuthStore } from '../stores/authStore';

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
  // C04: the defaults were hard-coded ENGLISH ('Smart Casual Work', 'My
  // Custom Tailored Ensemble'), so the Arabic UI opened with an English look
  // name AND an occasion string that matched none of the (translated) select
  // options — the select silently displayed the first option while the state
  // held something else. Initialise from the live locale instead. Lazy
  // initialisers: evaluated once at mount, in the mount-time language.
  const [targetOccasion, setTargetOccasion] = useState(() =>
    i18n.t('outfit_builder.occasion_smart_casual'),
  );
  const [outfitTitle, setOutfitTitle] = useState(() =>
    i18n.t('outfit_builder.default_look_name'),
  );
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
  // C04 (prod-observed defect): the composition-verdict and compatibility
  // endpoints require an account, so for a GUEST every canvas change fired a
  // 401 → the api client's transparent session refresh failed → the global
  // session-expired handler opened the LOGIN MODAL in the shopper's face,
  // interrupting composition. Guests never get those automatic calls now;
  // the cohesion card states honestly that scoring needs an account, and
  // only a deliberate action (save) routes into authentication.
  const { isAuthenticated } = useAuthStore();

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

  /**
   * Spec "Undo / Remove to Bin" §1: clearing ONE slot is undoable too, not
   * just the whole canvas. Same reasoning as clearCanvas below: this state
   * is memory-only (no server row until "save look"), so restoring the
   * snapshot is a safe, honest reversal — no endpoint involved, none claimed.
   * On reload both the canvas and the Undo offer vanish together: the truth.
   *
   * Restore REPLACES whatever occupies the slot at that moment — the canvas
   * invariant is one item per slot, and this mirrors addItemToCanvas's own
   * replace-on-occupied semantics rather than inventing a second rule.
   */
  const removeItemFromCanvas = useCallback((slot: CanvasItem['slot']) => {
    const removed = selectedItems.find((i) => i.slot === slot);
    if (!removed) return; // empty slot: nothing removed — no toast, no dangling Undo
    setSelectedItems((prev) => prev.filter((i) => i.slot !== slot));
    showToast(msg('toast.slot_cleared', { title: removed.product.title }), 'info', {
      i18nLabel: 'a11y.undo_remove',
      onAction: () => {
        setSelectedItems((prev) => [...prev.filter((i) => i.slot !== slot), removed]);
        showToast(msg('toast.slot_restored', { title: removed.product.title }), 'success');
      },
    });
  }, [selectedItems, showToast]);

  /**
   * Spec 03: clearing the canvas is undoable LOCALLY. This state lives only
   * in memory (no server row is touched until "save look"), so restoring the
   * snapshot is a safe, honest reversal — no endpoint is involved and none is
   * claimed. The snapshot is held in the toast closure only; on reload both
   * the canvas and the Undo offer are gone together, which is the truth.
   */
  const clearCanvas = useCallback(() => {
    if (selectedItems.length === 0) return; // nothing cleared — no toast, no undo
    const snapshotItems = selectedItems;
    const snapshotCompat = compatibility;
    setSelectedItems([]);
    setCompatibility(null);
    showToast(msg('toast.canvas_cleared', { count: snapshotItems.length }), 'info', {
      i18nLabel: 'a11y.undo_remove',
      onAction: () => {
        setSelectedItems(snapshotItems);
        setCompatibility(snapshotCompat);
        showToast(msg('toast.canvas_restored'), 'success');
      },
    });
  }, [selectedItems, compatibility, showToast]);

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
    if (!isAuthenticated) {
      setVerdict(null);
      return;
    }
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
  }, [selectedItems, isAuthenticated]);

  // Live evaluate compatibility whenever items or occasion change
  useEffect(() => {
    if (!isAuthenticated || selectedItems.length === 0) {
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
  }, [selectedItems, targetOccasion, isAuthenticated]);

  // ── C04 pass 4: compatibility SUGGESTIONS (spec row: "اقتراحات التوافق").
  // The backend's Feature-06 fill-in-the-blank endpoint ranks REAL catalog
  // products that complete the current canvas; it had zero consumers until
  // now. The server names its engine honestly (model vs rules fallback) and
  // declares unavailability with a reason — the UI repeats that truth, never
  // papering over it. Auth-gated server-side, so guests never trigger it.
  const [suggestions, setSuggestions] = useState<{
    slot: CanvasItem['slot'];
    engine: string | null;
    items: Product[];
    unavailableReason: string | null;
  } | null>(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState(false);
  const suggestSeq = useRef(0);

  const dismissSuggestions = useCallback(() => {
    setSuggestions(null);
    setSuggestError(false);
  }, []);

  const requestSuggestions = useCallback(
    async (slot: CanvasItem['slot'], availableProducts: Product[]) => {
      const pids = selectedItems.map((i) => i.product.id);
      if (pids.length === 0) return;
      const seq = ++suggestSeq.current;
      setIsSuggesting(true);
      setSuggestError(false);
      setSuggestions(null);
      try {
        // No target_slot on the wire: the canvas slot taxonomy is this VM's
        // (naturalSlotForProduct), so we free-complete server-side and apply
        // the SAME client rule that governs drops — the suggestion rail can
        // never offer a piece the slot itself would reject.
        const res = await stylistService.fillInTheBlank({ product_ids: pids, top_k: 10 });
        if (seq !== suggestSeq.current) return; // stale response: a newer request owns the rail
        if (!res.fitb_available) {
          setSuggestions({ slot, engine: null, items: [], unavailableReason: res.reason || null });
          return;
        }
        const byId = new Map(availableProducts.map((p) => [p.id, p]));
        const inCanvas = new Set(pids);
        const items: Product[] = [];
        for (const cand of res.ranked) {
          if (inCanvas.has(cand.product_id)) continue;
          const product = byId.get(cand.product_id);
          if (!product || !isValidSlotForProduct(product, slot)) continue;
          items.push(product);
          if (items.length >= 4) break;
        }
        setSuggestions({ slot, engine: res.engine, items, unavailableReason: null });
      } catch {
        if (seq !== suggestSeq.current) return;
        setSuggestError(true);
      } finally {
        if (seq === suggestSeq.current) setIsSuggesting(false);
      }
    },
    [selectedItems, isValidSlotForProduct]
  );

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

  // C04: without an in-flight guard a double-click ran the add loop twice
  // and every piece landed in the bag with quantity 2 — the exact
  // "double-submit duplicates" counter-goal. State drives the disabled/busy
  // UI; the ref closes the race between the two synchronous click handlers.
  const [isAddingAll, setIsAddingAll] = useState(false);
  const addAllInFlight = useRef(false);

  const addAllToCart = useCallback(async () => {
    if (selectedItems.length === 0) return;
    if (addAllInFlight.current) return;
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
    addAllInFlight.current = true;
    setIsAddingAll(true);
    try {
      for (const item of ready) {
        await addItem(item.selectedSku!.id, {
          id: item.product.id,
          title: item.product.title,
          category: item.product.category_name,
          color: item.product.color_family,
        });
      }
      // C04: these two toasts were raw English template literals — the only
      // untranslated strings left in this viewmodel. Keyed like every other.
      showToast(
        skipped > 0
          ? msg('toast.builder_added_partial', { count: ready.length, skipped })
          : msg('toast.builder_added_to_bag', { count: ready.length }),
        skipped > 0 ? 'info' : 'success'
      );
      openCart();
    } finally {
      addAllInFlight.current = false;
      setIsAddingAll(false);
    }
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
    isAddingAll,
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
    suggestions,
    isSuggesting,
    suggestError,
    requestSuggestions,
    dismissSuggestions,
  };
}
