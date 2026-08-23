import { useState, useCallback, useEffect } from 'react';
import { tryOnService } from '../services/apiServices';
import { Product, MultiGarmentTryOnResult, AnimationTryOnResult, NoPhotoFitResult, VisualSearchResult } from '../models';
import { useUIStore } from '../stores/uiStore';
import { useCartStore } from '../stores/cartStore';

export type TryOnWorkflowStatus = 'idle' | 'selected' | 'rendering' | 'completed' | 'failed';
export type MotionWorkflowStatus = 'idle' | 'generating' | 'ready' | 'failed';

export function useTryOnViewModel(initialProduct?: Product | null) {
  const [tryOnStatus, setTryOnStatus] = useState<TryOnWorkflowStatus>('idle');
  const [motionStatus, setMotionStatus] = useState<MotionWorkflowStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [multiTryOnResult, setMultiTryOnResult] = useState<MultiGarmentTryOnResult | null>(null);
  const [animationResult, setAnimationResult] = useState<AnimationTryOnResult | null>(null);
  const [activeKeyframeIndex, setActiveKeyframeIndex] = useState(0);
  const [outputAspect, setOutputAspect] = useState<'9:16' | '4:5' | '1:1'>('9:16');

  const [selectedAvatar, setSelectedAvatar] = useState('avatar_athletic_m');
  const [uploadedUserImage, setUploadedUserImage] = useState<string | null>(null);
  const [consentRetain, setConsentRetain] = useState(false);

  // Dynamic Garments State
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

  // Dynamic compatibility score calculation from actual products
  const dynamicFitScore = Object.values(appliedGarments).length > 0
    ? Math.round(
        Object.values(appliedGarments).reduce((acc, p) => acc + (p.style_compatibility_score || 92), 0) /
          Object.values(appliedGarments).length
      )
    : 94;

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
      showToast('Fit calculation: ' + (err.message || 'Check body parameters'), 'error');
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
      showToast('Visual search: ' + (err.message || 'Image analysis failed'), 'error');
    }
  }, [showToast]);

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
      setTryOnStatus('idle');
      return;
    }

    setTryOnStatus('rendering');
    setErrorMessage(null);

    try {
      const res = await tryOnService.multiRenderTryOn({
        product_ids: productIds,
        user_image_url: uploadedUserImage || undefined,
        avatar_model_id: selectedAvatar,
        consent_retain_photo: consentRetain,
      });

      if (res && (res.status === 'completed' || res.rendered_result_url)) {
        setMultiTryOnResult(res);
        setTryOnStatus('completed');
      } else {
        setTryOnStatus('completed');
      }
    } catch (err: any) {
      setTryOnStatus('failed');
      setErrorMessage(err.message || 'Try-on rendering failed');
      console.warn('Try-on render error:', err);
    }
  }, [uploadedUserImage, selectedAvatar, consentRetain]);

  // Initialize with initialProduct if provided
  useEffect(() => {
    if (initialProduct && Object.keys(appliedGarments).length === 0) {
      const slot = determineSlotForProduct(initialProduct);
      const initialMap = { [slot]: initialProduct };
      setAppliedGarments(initialMap);
      setTryOnStatus('selected');
      triggerMultiRender(initialMap);
    }
  }, [initialProduct, triggerMultiRender]);

  // Run dynamic animation try-on
  const runAnimatedTryOn = useCallback(async () => {
    const productIds = Object.values(appliedGarments).map((p) => p.id);
    if (productIds.length === 0) {
      showToast('Select at least one garment before generating motion.', 'info');
      return;
    }

    setMotionStatus('generating');
    try {
      const res = await tryOnService.renderAnimationTryOn({
        product_ids: productIds,
        user_image_url: uploadedUserImage || undefined,
        avatar_model_id: selectedAvatar,
        output_aspect: outputAspect,
        background_mode: 'studio',
      });

      if (res && res.status === 'completed') {
        setAnimationResult(res);
        setMotionStatus('ready');
        setActivePreviewTab('animation');

        // Step-by-step keyframe playback
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
        showToast('Layer assembly sequence ready for playback.', 'info');
      } else {
        setMotionStatus('failed');
        showToast('Motion sequence could not be completed for current pose.', 'error');
      }
    } catch (err: any) {
      setMotionStatus('failed');
      showToast('Layer sequence notice: ' + (err.message || 'Service unavailable'), 'error');
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

      setTryOnStatus('selected');
      triggerMultiRender(next);
      return next;
    });

    showToast(`Added to Outfit: ${product.title}`, 'info');
  }, [appliedGarments, triggerMultiRender, showToast]);

  // Remove specific garment slot
  const removeGarmentFromCanvas = useCallback((slot: string) => {
    setHistory((prev) => [...prev, { ...appliedGarments }]);
    setAppliedGarments((prev) => {
      const next = { ...prev };
      delete next[slot];
      if (Object.keys(next).length === 0) {
        setTryOnStatus('idle');
      } else {
        triggerMultiRender(next);
      }
      return next;
    });
  }, [appliedGarments, triggerMultiRender]);

  // Clear entire canvas
  const clearCanvas = useCallback(() => {
    setHistory((prev) => [...prev, { ...appliedGarments }]);
    setAppliedGarments({});
    setMultiTryOnResult(null);
    setAnimationResult(null);
    setTryOnStatus('idle');
    setMotionStatus('idle');
  }, [appliedGarments]);

  // Undo last action
  const undoLastAction = useCallback(() => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setHistory((prev) => prev.slice(0, prev.length - 1));
    setAppliedGarments(previous);
    if (Object.keys(previous).length === 0) {
      setTryOnStatus('idle');
    } else {
      triggerMultiRender(previous);
    }
  }, [history, triggerMultiRender]);

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
    setTryOnStatus('selected');
    triggerMultiRender(newGarments);
    showToast(`Loaded ${items.length} garments into Try-On Studio!`, 'success');
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
    showToast(`Added ${items.length} dressed pieces to shopping bag!`, 'success');
    openCart();
  }, [appliedGarments, addItem, openCart, showToast]);

  const runTryOn = useCallback(async () => {
    await triggerMultiRender(appliedGarments);
  }, [triggerMultiRender, appliedGarments]);

  const totalPrice = Object.values(appliedGarments).reduce((sum, p) => sum + (p.base_price || 0), 0);

  return {
    tryOnStatus,
    motionStatus,
    errorMessage,
    isRendering: tryOnStatus === 'rendering',
    isAnimating: motionStatus === 'generating',
    multiTryOnResult,
    animationResult,
    activeKeyframeIndex,
    setActiveKeyframeIndex,
    outputAspect,
    setOutputAspect,
    activePreviewTab,
    setActivePreviewTab,
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
    dynamicFitScore,
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
