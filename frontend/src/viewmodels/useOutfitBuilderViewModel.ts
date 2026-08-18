import { useState, useCallback, useMemo, useEffect } from 'react';
import { stylistService, catalogService } from '../services/apiServices';
import { Product, ProductSKU } from '../models';
import { useUIStore } from '../stores/uiStore';
import { useCartStore } from '../stores/cartStore';

export interface CanvasItem {
  product: Product;
  selectedSku: ProductSKU;
  slot: 'outerwear' | 'top' | 'bottom' | 'footwear' | 'accessory';
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
      const price = item.selectedSku.price_override || item.product.base_price;
      return acc + price;
    }, 0);
  }, [selectedItems]);

  const isOverBudget = runningTotal > userBudgetLimit;

  const addItemToCanvas = useCallback((product: Product, slot?: CanvasItem['slot']) => {
    let assignedSlot = slot;
    if (!assignedSlot) {
      const cat = product.category_name.toLowerCase();
      if (cat.includes('outer') || cat.includes('blazer')) assignedSlot = 'outerwear';
      else if (cat.includes('bottom') || cat.includes('trouser')) assignedSlot = 'bottom';
      else if (cat.includes('shoe') || cat.includes('footwear')) assignedSlot = 'footwear';
      else if (cat.includes('dress')) assignedSlot = 'top';
      else assignedSlot = 'top';
    }

    const defaultSku = product.skus?.[0] || {
      id: product.id * 10,
      product_id: product.id,
      sku_code: `${product.slug}-M`,
      size: 'M',
      color: product.color_family,
      color_hex: product.dominant_hex,
      stock_level: 10,
      is_in_stock: true,
    };

    setSelectedItems((prev) => {
      // Replace if slot already occupied or append
      const filtered = prev.filter((i) => i.slot !== assignedSlot);
      return [...filtered, { product, selectedSku: defaultSku, slot: assignedSlot! }];
    });
  }, []);

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
    setIsSaving(true);
    try {
      await stylistService.saveOutfit({
        title: outfitTitle,
        occasion: targetOccasion,
        product_sku_ids: selectedItems.map((i) => i.selectedSku.id),
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
    for (const item of selectedItems) {
      await addItem(item.selectedSku.id, {
        id: item.product.id,
        title: item.product.title,
        category: item.product.category_name,
        color: item.product.color_family,
      });
    }
    showToast(`Added ${selectedItems.length} items from builder to Bag!`, 'success');
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
    removeItemFromCanvas,
    clearCanvas,
    saveOutfit,
    addAllToCart,
  };
}
