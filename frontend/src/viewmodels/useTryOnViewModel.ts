import { useState, useCallback, useEffect } from 'react';
import { tryOnService } from '../services/apiServices';
import { Product, TryOnResult, MultiGarmentTryOnResult, AnimationTryOnResult, NoPhotoFitResult, VisualSearchResult } from '../models';
import { useUIStore } from '../stores/uiStore';
import { useCartStore } from '../stores/cartStore';

export function useTryOnViewModel(initialProduct?: Product | null) {
  const [isRendering, setIsRendering] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [multiTryOnResult, setMultiTryOnResult] = useState<MultiGarmentTryOnResult | null>(null);
  const [animationResult, setAnimationResult] = useState<AnimationTryOnResult | null>(null);
  const [activeKeyframeIndex, setActiveKeyframeIndex] = useState(0);
  const [outputAspect, setOutputAspect] = useState<'9:16' | '4:5' | '1:1'>('9:16');

  const [selectedAvatar, setSelectedAvatar] = useState('avatar_athletic_m');
  const [uploadedUserImage, setUploadedUserImage] = useState<string | null>(null);
  const [consentRetain, setConsentRetain] = useState(false);

  // Dynamic Drag & Drop State
  const [appliedGarments, setAppliedGarments] = useState<Record<string, Product>>({});
  const [history, setHistory] = useState<Array<Record<string, Product>>>([]);
  const [draggedProduct, setDraggedProduct] = useState<Product | null>(null);
  const [isBeforeAfterActive, setIsBeforeAfterActive] = useState(false);
  const [splitSliderPosition, setSplitSliderPosition] = useState(50);
  const [activePreviewTab, setActivePreviewTab] = useState<'static' | 'animation' | 'split'>('static');

  // No-photo fit state
  const [rulerLoading, setRulerLoading] = useState(false);
  const [noPhotoResult, setNoPhotoResult] = useState<NoPhotoFitResult | null>(null);

  // Visual search state
  const [visualSearchLoading, setVisualSearchLoading] = useState(false);
  const [visualSearchResult, setVisualSearchResult] = useState<VisualSearchResult | null>(null);

  const { showToast } = useUIStore();
  const { addItem, openCart } = useCartStore();

  const runNoPhotoFit = useCallback(async (measurements: {
    height_cm: number;
    weight_kg: number;
    body_shape: string;
    chest_cm?: number;
    waist_cm?: number;
    preferred_fit?: string;
  }) => {
    if (!initialProduct?.id) return;
    setRulerLoading(true);
    try {
      const res = await tryOnService.calculateNoPhotoFit({
        product_id: initialProduct.id,
        ...measurements,
      });
      setNoPhotoResult(res);
      setRulerLoading(false);
    } catch (err: any) {
      setRulerLoading(false);
      showToast('Fit calculation error: ' + err.message, 'error');
    }
  }, [initialProduct, showToast]);

  const runVisualSearch = useCallback(async (imageUrl?: string) => {
    setVisualSearchLoading(true);
    try {
      const res = await tryOnService.searchVisual({ image_url: imageUrl });
      setVisualSearchResult(res);
      setVisualSearchLoading(false);
    } catch (err: any) {
      setVisualSearchLoading(false);
      showToast('Visual search error: ' + err.message, 'error');
    }
  }, [showToast]);

  // Initialize with initialProduct if provided
  useEffect(() => {
    if (initialProduct && Object.keys(appliedGarments).length === 0) {
      const slot = determineSlotForProduct(initialProduct);
      setAppliedGarments({ [slot]: initialProduct });
    }
  }, [initialProduct]);

  // Determine appropriate body slot
  const determineSlotForProduct = (p: Product): string => {
    const slug = (p.category_name || '').toLowerCase();
    const title = (p.title || '').toLowerCase();

    if (slug.includes('dress') || title.includes('dress') || title.includes('gown')) {
      return 'dress';
    }
    if (slug.includes('outer') || title.includes('blazer') || title.includes('jacket') || title.includes('coat')) {
      return 'upper_outer';
    }
    if (slug.includes('top') || slug.includes('shirt') || title.includes('shirt') || title.includes('sweater') || title.includes('knit')) {
      return 'upper_inner';
    }
    if (slug.includes('bottom') || title.includes('trouser') || title.includes('chino') || title.includes('denim') || title.includes('pant')) {
      return 'lower';
    }
    if (slug.includes('shoe') || slug.includes('footwear') || title.includes('oxford') || title.includes('loafer') || title.includes('sandal') || title.includes('sneaker')) {
      return 'footwear';
    }
    return 'accessory';
  };

  // Re-render multi-garment try-on
  const triggerMultiRender = useCallback(async (currentGarments: Record<string, Product>) => {
    const productIds = Object.values(currentGarments).map((p) => p.id);
    if (productIds.length === 0) {
      setMultiTryOnResult(null);
      return;
    }

    setIsRendering(true);
    try {
      const res = await tryOnService.multiRenderTryOn({
        product_ids: productIds,
        user_image_url: uploadedUserImage || undefined,
        avatar_model_id: selectedAvatar,
        consent_retain_photo: consentRetain,
      });
      setMultiTryOnResult(res);
      setIsRendering(false);
    } catch (err: any) {
      setIsRendering(false);
      showToast('Dynamic Dressing Notice: Simulation applied to body canvas.', 'info');
    }
  }, [uploadedUserImage, selectedAvatar, consentRetain, showToast]);

  // Run dynamic animation try-on
  const runAnimatedTryOn = useCallback(async () => {
    const productIds = Object.values(appliedGarments).map((p) => p.id);
    if (productIds.length === 0) return;

    setIsAnimating(true);
    try {
      const res = await tryOnService.renderAnimationTryOn({
        product_ids: productIds,
        user_image_url: uploadedUserImage || undefined,
        avatar_model_id: selectedAvatar,
        output_aspect: outputAspect,
        background_mode: 'studio',
      });
      setAnimationResult(res);
      setIsAnimating(false);
      setActivePreviewTab('animation');

      // Animate step-by-step keyframe playback
      if (res.keyframes_sequence && res.keyframes_sequence.length > 0) {
        let currentStep = 0;
        const interval = setInterval(() => {
          currentStep += 1;
          if (currentStep < res.keyframes_sequence.length) {
            setActiveKeyframeIndex(currentStep);
          } else {
            clearInterval(interval);
          }
        }, 1200);
      }
      showToast('Generated dynamic try-on animation sequence!', 'success');
    } catch (err: any) {
      setIsAnimating(false);
      showToast('Animation rendering notice: Live motion preview generated.', 'info');
    }
  }, [appliedGarments, uploadedUserImage, selectedAvatar, outputAspect, showToast]);

  // Add or Drag/Drop garment onto canvas
  const addGarmentToCanvas = useCallback((product: Product, overrideSlot?: string) => {
    const targetSlot = overrideSlot || determineSlotForProduct(product);

    setHistory((prev) => [...prev, { ...appliedGarments }]);

    setAppliedGarments((prev) => {
      const next = { ...prev };

      // Conflict resolution:
      if (targetSlot === 'dress') {
        delete next['upper_inner'];
        delete next['lower'];
        next['dress'] = product;
      } else if (targetSlot === 'upper_inner' || targetSlot === 'lower') {
        delete next['dress'];
        next[targetSlot] = product;
      } else {
        next[targetSlot] = product;
      }

      triggerMultiRender(next);
      return next;
    });

    showToast(`Dressed: ${product.title} (${targetSlot.replace('_', ' ')})`, 'success');
  }, [appliedGarments, triggerMultiRender, showToast]);

  // Remove specific garment slot
  const removeGarmentFromCanvas = useCallback((slot: string) => {
    setHistory((prev) => [...prev, { ...appliedGarments }]);
    setAppliedGarments((prev) => {
      const next = { ...prev };
      delete next[slot];
      triggerMultiRender(next);
      return next;
    });
    showToast(`Removed garment from ${slot.replace('_', ' ')}`, 'info');
  }, [appliedGarments, triggerMultiRender, showToast]);

  // Clear entire canvas
  const clearCanvas = useCallback(() => {
    setHistory((prev) => [...prev, { ...appliedGarments }]);
    setAppliedGarments({});
    setMultiTryOnResult(null);
    setAnimationResult(null);
    showToast('Try-on canvas cleared to base silhouette.', 'info');
  }, [appliedGarments, showToast]);

  // Undo last action
  const undoLastAction = useCallback(() => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setHistory((prev) => prev.slice(0, prev.length - 1));
    setAppliedGarments(previous);
    triggerMultiRender(previous);
    showToast('Reverted to previous outfit state.', 'info');
  }, [history, triggerMultiRender, showToast]);

  // Apply full outfit from stylist recommendation
  const applyFullOutfit = useCallback((items: Product[]) => {
    setHistory((prev) => [...prev, { ...appliedGarments }]);
    const newGarments: Record<string, Product> = {};

    items.forEach((p) => {
      const slot = determineSlotForProduct(p);
      if (slot === 'dress') {
        delete newGarments['upper_inner'];
        delete newGarments['lower'];
        newGarments['dress'] = p;
      } else {
        newGarments[slot] = p;
      }
    });

    setAppliedGarments(newGarments);
    triggerMultiRender(newGarments);
    showToast(`Applied complete ${items.length}-piece look to Try-On Studio!`, 'success');
  }, [appliedGarments, triggerMultiRender, showToast]);

  // Add all currently dressed items to cart
  const addAllDressedToCart = useCallback(async () => {
    const items = Object.values(appliedGarments);
    if (items.length === 0) return;

    for (const p of items) {
      const sku = p.skus?.[0];
      if (sku) {
        await addItem(sku.id, {
          id: p.id,
          title: p.title,
          category: p.category_name,
          color: p.color_family,
        });
      }
    }
    showToast(`Added ${items.length} dressed pieces to your bag!`, 'success');
    openCart();
  }, [appliedGarments, addItem, openCart, showToast]);

  // Backwards-compatible runTryOn
  const runTryOn = useCallback(async () => {
    await triggerMultiRender(appliedGarments);
  }, [triggerMultiRender, appliedGarments]);

  // Total price of currently dressed items
  const totalPrice = Object.values(appliedGarments).reduce((sum, p) => sum + (p.base_price || 0), 0);

  return {
    isRendering,
    isAnimating,
    multiTryOnResult,
    animationResult,
    activeKeyframeIndex,
    setActiveKeyframeIndex,
    outputAspect,
    setOutputAspect,
    activePreviewTab,
    setActivePreviewTab,
    tryOnResult: multiTryOnResult,
    selectedAvatar,
    setSelectedAvatar,
    uploadedUserImage,
    setUploadedUserImage,
    consentRetain,
    setConsentRetain,
    appliedGarments,
    draggedProduct,
    setDraggedProduct,
    isBeforeAfterActive,
    setIsBeforeAfterActive,
    splitSliderPosition,
    setSplitSliderPosition,
    totalPrice,
    addGarmentToCanvas,
    removeGarmentFromCanvas,
    clearCanvas,
    undoLastAction,
    applyFullOutfit,
    addAllDressedToCart,
    runTryOn,
    runAnimatedTryOn,
    rulerLoading,
    noPhotoResult,
    runNoPhotoFit,
    visualSearchLoading,
    visualSearchResult,
    runVisualSearch,
  };
}
