import { msg as msgKey, detail } from '../i18n/messages';
import { useState, useCallback, useEffect } from "react";
import {
  catalogService,
  tryOnService,
  TryOnProductCapability,
  TryOnCapabilitiesResponse,
} from "../services/apiServices";
import {
  Product,
  MultiGarmentTryOnResult,
  AnimationTryOnResult,
  NoPhotoFitResult,
  VisualSearchResult,
} from "../models";
import { useUIStore } from "../stores/uiStore";
import { useCartStore } from "../stores/cartStore";

export type TryOnWorkflowStatus =
  "idle" | "selected" | "rendering" | "completed" | "failed";
export type MotionWorkflowStatus = "idle" | "generating" | "ready" | "failed";

/**
 * Try-on failure CODES.
 *
 * These are machine discriminators, NOT user-facing copy: every branch that
 * matches on them renders its own localized toast. They were previously inline
 * prose ("VTON_ANIMATED_ALL_FAILED: All keyframes failed"), which meant (a) the
 * discriminator depended on the exact wording of a sentence, and (b) the i18n
 * audit's inventory counted English that no user can ever read.
 */
export const VTON_ERR = {
  workerNotReady: 'VTON_WORKER_NOT_READY',
  animatedFirstFrameFailed: 'VTON_ANIMATED_FIRST_FRAME_FAILED',
  animatedAllFailed: 'VTON_ANIMATED_ALL_FAILED',
  animatedFailed: 'VTON_ANIMATED_FAILED',
} as const;

export function useTryOnViewModel(initialProduct?: Product | null) {
  const [tryOnStatus, setTryOnStatus] = useState<TryOnWorkflowStatus>("idle");
  const [motionStatus, setMotionStatus] =
    useState<MotionWorkflowStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [multiTryOnResult, setMultiTryOnResult] =
    useState<MultiGarmentTryOnResult | null>(null);
  const [animationResult, setAnimationResult] =
    useState<AnimationTryOnResult | null>(null);
  const [activeKeyframeIndex, setActiveKeyframeIndex] = useState(0);
  const [outputAspect, setOutputAspect] = useState<"9:16" | "4:5" | "1:1">(
    "9:16",
  );

  const [selectedAvatar, setSelectedAvatar] = useState("avatar_athletic_m");
  const [uploadedUserImage, setUploadedUserImage] = useState<string | null>(
    null,
  );
  const [consentRetain, setConsentRetain] = useState(false);

  // Dynamic Garments State
  const [appliedGarments, setAppliedGarments] = useState<
    Record<string, Product>
  >({});
  const [history, setHistory] = useState<Array<Record<string, Product>>>([]);
  const [draggedProduct, setDraggedProduct] = useState<Product | null>(null);
  const [isBeforeAfterActive, setIsBeforeAfterActive] = useState(false);
  const [splitSliderPosition, setSplitSliderPosition] = useState(50);
  const [activePreviewTab, setActivePreviewTab] = useState<
    "static" | "animation" | "split"
  >("static");
  const [vtonCapabilities, setVtonCapabilities] = useState<
    Record<number, TryOnProductCapability>
  >({});
  const [capabilityLoading, setCapabilityLoading] = useState(false);
  const [capabilityMessage, setCapabilityMessage] = useState<string | null>(
    null,
  );

  // No-photo fit state
  const [rulerLoading, setRulerLoading] = useState(false);
  const [noPhotoResult, setNoPhotoResult] = useState<NoPhotoFitResult | null>(
    null,
  );

  // Visual search state — the error is surfaced inline by the modal, not
  // only as a transient toast, so a failed analysis has a visible terminal
  // state instead of an eternal 'Analyzing...'.
  const [visualSearchLoading, setVisualSearchLoading] = useState(false);
  const [visualSearchResult, setVisualSearchResult] =
    useState<VisualSearchResult | null>(null);
  const [visualSearchError, setVisualSearchError] = useState<string | null>(
    null,
  );

  const { showToast } = useUIStore();
  const { addItem, openCart } = useCartStore();

  // Dynamic style score calculation from actual product scores only.
  // Catalog list rows often carry null here; null hides the badge rather
  // than inventing a 92/94% match.
  const scoredGarments = Object.values(appliedGarments).filter(
    (p) =>
      p.style_compatibility_score !== undefined &&
      p.style_compatibility_score !== null,
  );
  const dynamicFitScore =
    scoredGarments.length > 0
      ? Math.round(
          scoredGarments.reduce(
            (acc, p) => acc + Number(p.style_compatibility_score),
            0,
          ) / scoredGarments.length,
        )
      : null;

  /**
   * No-photo fit for the try-on drawer.
   *
   * Takes CENTIMETRE/KILOGRAM values (the caller's existing shape) and states
   * `units: 'metric'` on the wire, so the server performs the single
   * conversion. Callers must not pre-convert imperial input here.
   */
  const runNoPhotoFit = useCallback(
    async (measurements: {
      height_cm: number;
      weight_kg: number;
      body_shape?: string;
      chest_cm?: number;
      waist_cm?: number;
      hip_cm?: number;
      preferred_fit?: string;
    }) => {
      if (!initialProduct?.id) return;
      setRulerLoading(true);
      try {
        const res = await tryOnService.calculateNoPhotoFit({
          product_id: initialProduct.id,
          units: 'metric',
          height: measurements.height_cm,
          weight: measurements.weight_kg,
          chest: measurements.chest_cm ?? null,
          waist: measurements.waist_cm ?? null,
          hip: measurements.hip_cm ?? null,
          body_shape: measurements.body_shape ?? null,
          preferred_fit: measurements.preferred_fit ?? 'regular',
        });
        setNoPhotoResult(res);
        setRulerLoading(false);
      } catch (err: any) {
        setRulerLoading(false);
        showToast(
          "Fit calculation: " + (err.message || "Check body parameters"),
          "error",
        );
      }
    },
    [initialProduct, showToast],
  );

  const runVisualSearch = useCallback(
    async (source?: string | { imageUrl?: string; imageBase64?: string }) => {
      // Accepts a URL string (samples / pasted link) or an object carrying an
      // uploaded photo as a data URL — both go to the SAME real endpoint
      // (POST /tryon/visual-search, image_url | image_base64).
      const opts =
        typeof source === "string" ? { imageUrl: source } : (source ?? {});
      setVisualSearchLoading(true);
      setVisualSearchError(null);
      try {
        const res = await tryOnService.searchVisual({
          image_url: opts.imageUrl,
          image_base64: opts.imageBase64,
        });
        setVisualSearchResult(res);
        setVisualSearchLoading(false);
      } catch (err: any) {
        setVisualSearchResult(null);
        setVisualSearchLoading(false);
        const msg =
          err?.code === "REQUEST_TIMEOUT"
            ? "The image analysis timed out. Please try again."
            : err?.message || "Image analysis failed.";
        setVisualSearchError(msg);
        showToast(msgKey('toast.visual_search_failed', { reason: detail(msg) }), "error");
      }
    },
    [showToast],
  );

  const conservativeCapability = (
    productId: number,
  ): TryOnProductCapability => ({
    product_id: productId,
    product_slug: null,
    category_slug: null,
    slot_type: null,
    state: "unknown",
    reason_code: "CAPABILITY_UNAVAILABLE",
    message:
      "Virtual try-on support could not be verified by the backend capability registry. Try-on is disabled for this item.",
    provider: "unknown",
  });

  const capabilityErrorMessage = (cap: TryOnProductCapability): string => {
    if (cap.state === "temporarily_unavailable") {
      return (
        cap.message ||
        "Virtual try-on is temporarily unavailable. Please retry later."
      );
    }
    if (cap.state === "misconfigured") {
      return (
        cap.message || "Virtual try-on is not configured for this deployment."
      );
    }
    if (cap.state === "unsupported") {
      return (
        cap.message ||
        "This product category is not supported by virtual try-on."
      );
    }
    return cap.message || "Virtual try-on support for this item is unknown.";
  };

  const ensureCapabilities = useCallback(async (productIds: number[]) => {
    const uniqueIds = Array.from(new Set(productIds.filter(Boolean)));
    if (uniqueIds.length === 0)
      return {} as Record<number, TryOnProductCapability>;
    setCapabilityLoading(true);
    setCapabilityMessage(null);
    try {
      const response: TryOnCapabilitiesResponse =
        await tryOnService.getCapabilities(uniqueIds);
      const mapped: Record<number, TryOnProductCapability> = {};
      uniqueIds.forEach((id) => {
        mapped[id] = conservativeCapability(id);
      });
      response.products.forEach((cap) => {
        mapped[cap.product_id] = cap;
      });
      if (response.engine_state && response.engine_state !== "available") {
        Object.values(mapped).forEach((cap) => {
          if (cap.state === "supported") {
            cap.state =
              response.engine_state === "misconfigured"
                ? "misconfigured"
                : "temporarily_unavailable";
            cap.reason_code = `ENGINE_${String(response.engine_state).toUpperCase()}`;
            cap.message =
              response.engine_state === "misconfigured"
                ? "Virtual try-on is not configured for this deployment."
                : "Virtual try-on is temporarily unavailable. Please retry later.";
          }
        });
      }
      setVtonCapabilities((prev) => ({ ...prev, ...mapped }));
      return mapped;
    } catch {
      const mapped = Object.fromEntries(
        uniqueIds.map((id) => [id, conservativeCapability(id)]),
      ) as Record<number, TryOnProductCapability>;
      setVtonCapabilities((prev) => ({ ...prev, ...mapped }));
      setCapabilityMessage(
        "Virtual try-on capability could not be verified, so rendering is disabled rather than guessed.",
      );
      return mapped;
    } finally {
      setCapabilityLoading(false);
    }
  }, []);

  const slotForProduct = (product: Product, cap?: TryOnProductCapability) => {
    if (cap?.state === "supported" && cap.slot_type) return cap.slot_type;
    const cached = vtonCapabilities[product.id];
    return cached?.state === "supported" && cached.slot_type
      ? cached.slot_type
      : "unknown";
  };

  // Re-render multi-garment try-on with honest error taxonomy.
  //
  // `overrides` is REQUIRED for call sites that change the person reference
  // or avatar in the SAME tick as the render (photo upload, avatar pick):
  // React state setters are async, so `uploadedUserImage` / `selectedAvatar`
  // captured in this closure are still the PREVIOUS values when runTryOn()
  // runs immediately after the setState. Rendering with the stale values
  // would silently ignore the photo the user just uploaded (the person
  // image is the only human/pose authority — hard product invariant).
  const triggerMultiRender = useCallback(
    async (
      currentGarments: Record<string, Product>,
      overrides?: { userImageUrl?: string | null; avatarId?: string | null },
    ) => {
      const productIds = Object.values(currentGarments).map((p) => p.id);
      if (productIds.length === 0) {
        setMultiTryOnResult(null);
        setTryOnStatus("idle");
        return;
      }

      setTryOnStatus("rendering");
      setErrorMessage(null);

      const capabilities = await ensureCapabilities(productIds);
      const blocked = Object.values(capabilities).find(
        (cap) => cap.state !== "supported",
      );
      if (blocked) {
        const msg = capabilityErrorMessage(blocked);
        setMultiTryOnResult(null);
        setTryOnStatus("failed");
        setErrorMessage(msg);
        setCapabilityMessage(msg);
        return;
      }

      const effectiveUserImage =
        overrides && overrides.userImageUrl !== undefined
          ? overrides.userImageUrl
          : uploadedUserImage;
      const effectiveAvatar =
        overrides && overrides.avatarId !== undefined
          ? overrides.avatarId
          : selectedAvatar;

      try {
        const res = await tryOnService.multiRenderTryOn({
          product_ids: productIds,
          user_image_url: effectiveUserImage || undefined,
          avatar_model_id: effectiveAvatar,
          consent_retain_photo: consentRetain,
        });

        if (res && res.status === "completed" && res.rendered_result_url) {
          setMultiTryOnResult(res);
          setTryOnStatus("completed");
        } else {
          setMultiTryOnResult(null);
          setTryOnStatus("failed");
          const honestMsg =
            (res as any)?.error_message ||
            (res as any)?.detail?.error?.message ||
            "Virtual try-on rendering is unavailable right now. Your photo was not modified.";
          setErrorMessage(honestMsg);
          // Show toast with honest taxonomy
          if (honestMsg.includes("VTON_ENGINE_UNAVAILABLE")) {
            showToast(
              "VTON engine unavailable: GPU worker not configured. Set VTON_WORKER_URL to enable real CatVTON inference.",
              "error",
            );
          } else if (honestMsg.includes("VTON_WORKER_NOT_READY")) {
            showToast(
              "VTON worker not ready: model loading or GPU unavailable. Please try again.",
              "error",
            );
          } else if (honestMsg.includes("VTON_AUTH_FAILURE")) {
            showToast(
              "VTON authentication failed: worker token invalid.",
              "error",
            );
          } else if (honestMsg.includes("VTON_LAYER_NOT_APPLIED")) {
            showToast(
              "One or more garments could not be applied to your photo, so no complete, verified result was produced. Please try again.",
              "error",
            );
          }
        }
      } catch (err: any) {
        setMultiTryOnResult(null);
        setTryOnStatus("failed");
        // Extract honest error from API response
        let msg =
          err?.message || "Virtual try-on rendering is unavailable right now.";
        try {
          // Try to parse error body if it's JSON
          if (err?.response) {
            const body = err.response;
            if (body?.error?.message) msg = body.error.message;
            else if (body?.detail?.error?.message)
              msg = body.detail.error.message;
          }
          // Check for error code in message
          if (err?.detail?.error?.message) msg = err.detail.error.message;
          if (err?.error?.message) msg = err.error.message;
        } catch {}
        setErrorMessage(msg);
        // Don't show generic toast here - let the UI show errorMessage
      }
    },
    [
      uploadedUserImage,
      selectedAvatar,
      consentRetain,
      ensureCapabilities,
      showToast,
    ],
  );

  // Initialize the canvas with `initialProduct`. Re-initialize whenever the
  // active product CHANGES (not only when the canvas is empty): the try-on
  // modal is rendered once and kept mounted in the layout, so without this a
  // new "Try On" click would silently keep the PREVIOUS garment (stale state)
  // and re-render the wrong item. Each "Try On" is a fresh session seeded
  // with the clicked garment; the previous result/animation/history are
  // cleared so a stale render is never displayed for a different garment.
  // `addGarmentToCanvas` does not change `initialProduct`, so building a
  // multi-garment outfit on the canvas is unaffected by this reset.
  const [initProductId, setInitProductId] = useState<number | null>(null);
  useEffect(() => {
    if (initialProduct && initialProduct.id !== initProductId) {
      let cancelled = false;
      (async () => {
        const caps = await ensureCapabilities([initialProduct.id]);
        if (cancelled) return;
        const cap = caps[initialProduct.id];
        if (!cap || cap.state !== "supported") {
          const msg = capabilityErrorMessage(
            cap || conservativeCapability(initialProduct.id),
          );
          setAppliedGarments({});
          setMultiTryOnResult(null);
          setAnimationResult(null);
          setHistory([]);
          setTryOnStatus("failed");
          setErrorMessage(msg);
          setCapabilityMessage(msg);
          setInitProductId(initialProduct.id);
          return;
        }
        const slot = slotForProduct(initialProduct, cap);
        const initialMap = { [slot]: initialProduct };
        setAppliedGarments(initialMap);
        setMultiTryOnResult(null);
        setAnimationResult(null);
        setHistory([]);
        setTryOnStatus("selected");
        setInitProductId(initialProduct.id);
        triggerMultiRender(initialMap);
      })();
      return () => {
        cancelled = true;
      };
    }
  }, [initialProduct, initProductId, ensureCapabilities, triggerMultiRender]);

  // Run dynamic animation try-on with real per-layer inference
  const runAnimatedTryOn = useCallback(async () => {
    const productIds = Object.values(appliedGarments).map((p) => p.id);
    if (productIds.length === 0) {
      showToast(
        "Select at least one garment before generating motion.",
        "info",
      );
      return;
    }

    setMotionStatus("generating");
    setErrorMessage(null);
    const caps = await ensureCapabilities(productIds);
    const blocked = Object.values(caps).find(
      (cap) => cap.state !== "supported",
    );
    if (blocked) {
      const msg = capabilityErrorMessage(blocked);
      setMotionStatus("failed");
      setErrorMessage(msg);
      setCapabilityMessage(msg);
      showToast(msg, "error");
      return;
    }
    try {
      const res = await tryOnService.renderAnimationTryOn({
        product_ids: productIds,
        user_image_url: uploadedUserImage || undefined,
        avatar_model_id: selectedAvatar,
        output_aspect: outputAspect,
        background_mode: "studio",
      });

      if (
        res &&
        res.status === "completed" &&
        res.keyframes_sequence &&
        res.keyframes_sequence.length > 0
      ) {
        // Validate keyframes are real (not all identical, not fake)
        const successfulFrames = res.keyframes_sequence.filter(
          (kf: any) => !kf.failed,
        );
        if (successfulFrames.length === 0) {
          throw new Error(VTON_ERR.animatedAllFailed);
        }
        setAnimationResult(res);
        setMotionStatus("ready");
        setActivePreviewTab("animation");

        // Step-by-step keyframe playback with real timing
        if (res.keyframes_sequence.length > 0) {
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
        showToast(
          `Layer assembly sequence ready: ${successfulFrames.length} real keyframes generated via CatVTON.`,
          "info",
        );
      } else {
        throw new Error(VTON_ERR.animatedFailed);
      }
    } catch (err: any) {
      setAnimationResult(null);
      setMotionStatus("failed");
      let msg =
        err?.message || "Animated try-on rendering is unavailable right now.";
      try {
        if (err?.detail?.error?.message) msg = err.detail.error.message;
        if (err?.error?.message) msg = err.error.message;
        if (err?.response?.error?.message) msg = err.response.error.message;
      } catch {}
      setErrorMessage(msg);

      // Honest taxonomy toast
      if (msg.includes("VTON_ENGINE_UNAVAILABLE")) {
        showToast(
          "Animated try-on requires GPU worker: Set VTON_WORKER_URL for real per-layer CatVTON inference. No fake animation.",
          "error",
        );
      } else if (msg.includes(VTON_ERR.workerNotReady)) {
        showToast(
          "Animated try-on worker not ready. Please try again.",
          "error",
        );
      } else if (
        msg.includes(VTON_ERR.animatedFirstFrameFailed) ||
        msg.includes(VTON_ERR.animatedAllFailed)
      ) {
        showToast(
          "Animated try-on failed: first layer inference failed. No fake keyframes generated.",
          "error",
        );
      } else {
        showToast(msgKey('toast.animated_tryon_unavailable', { reason: detail(msg) }), "error");
      }
    }
  }, [
    appliedGarments,
    uploadedUserImage,
    selectedAvatar,
    outputAspect,
    ensureCapabilities,
    showToast,
  ]);

  // Add or Drag/Drop garment onto canvas
  const addGarmentToCanvas = useCallback(
    async (product: Product, overrideSlot?: string) => {
      const caps = await ensureCapabilities([product.id]);
      const cap = caps[product.id];
      if (!cap || cap.state !== "supported") {
        const msg = capabilityErrorMessage(
          cap || conservativeCapability(product.id),
        );
        setTryOnStatus("failed");
        setErrorMessage(msg);
        setCapabilityMessage(msg);
        showToast(msg, "error");
        return;
      }
      const targetSlot = overrideSlot || slotForProduct(product, cap);

      const next = { ...appliedGarments };

      // Conflict resolution:
      if (targetSlot === "dress") {
        delete next["upper_inner"];
        delete next["lower"];
        next["dress"] = product;
      } else if (targetSlot === "upper_inner" || targetSlot === "lower") {
        delete next["dress"];
        next[targetSlot] = product;
      } else {
        next[targetSlot] = product;
      }

      setHistory((prev) => [...prev, { ...appliedGarments }]);
      setAppliedGarments(next);
      setTryOnStatus("selected");
      triggerMultiRender(next);
      showToast(msgKey('toast.added_to_outfit', { title: product.title }), "info");
    },
    [
      appliedGarments,
      ensureCapabilities,
      triggerMultiRender,
      showToast,
      vtonCapabilities,
    ],
  );

  // Remove specific garment slot
  const removeGarmentFromCanvas = useCallback(
    (slot: string) => {
      setHistory((prev) => [...prev, { ...appliedGarments }]);
      setAppliedGarments((prev) => {
        const next = { ...prev };
        delete next[slot];
        if (Object.keys(next).length === 0) {
          setTryOnStatus("idle");
        } else {
          triggerMultiRender(next);
        }
        return next;
      });
    },
    [appliedGarments, triggerMultiRender],
  );

  // Clear entire canvas
  const clearCanvas = useCallback(() => {
    setHistory((prev) => [...prev, { ...appliedGarments }]);
    setAppliedGarments({});
    setMultiTryOnResult(null);
    setAnimationResult(null);
    setTryOnStatus("idle");
    setMotionStatus("idle");
  }, [appliedGarments]);

  // Undo last action
  const undoLastAction = useCallback(() => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setHistory((prev) => prev.slice(0, prev.length - 1));
    setAppliedGarments(previous);
    if (Object.keys(previous).length === 0) {
      setTryOnStatus("idle");
    } else {
      triggerMultiRender(previous);
    }
  }, [history, triggerMultiRender]);

  // Apply full outfit from stylist recommendation
  const applyFullOutfit = useCallback(
    async (items: Product[]) => {
      const caps = await ensureCapabilities(items.map((p) => p.id));
      const blocked = items.find((p) => caps[p.id]?.state !== "supported");
      if (blocked) {
        const msg = capabilityErrorMessage(
          caps[blocked.id] || conservativeCapability(blocked.id),
        );
        setTryOnStatus("failed");
        setErrorMessage(msg);
        setCapabilityMessage(msg);
        showToast(msg, "error");
        return;
      }

      setHistory((prev) => [...prev, { ...appliedGarments }]);
      const newGarments: Record<string, Product> = {};

      items.forEach((p) => {
        const slot = slotForProduct(p, caps[p.id]);
        if (slot === "dress") {
          delete newGarments["upper_inner"];
          delete newGarments["lower"];
          newGarments["dress"] = p;
        } else {
          newGarments[slot] = p;
        }
      });

      setAppliedGarments(newGarments);
      setTryOnStatus("selected");
      triggerMultiRender(newGarments);
      showToast(
        `Loaded ${items.length} backend-supported garment(s) into Try-On Studio!`,
        "success",
      );
    },
    [
      appliedGarments,
      ensureCapabilities,
      triggerMultiRender,
      showToast,
      vtonCapabilities,
    ],
  );

  // Add all currently dressed items to cart
  const addAllDressedToCart = useCallback(async () => {
    const items = Object.values(appliedGarments);
    if (items.length === 0) return;

    let added = 0;
    let skipped = 0;
    for (const p of items) {
      try {
        const detail = p.skus?.length
          ? p
          : await catalogService.getProductDetail(p.slug || String(p.id));
        const sku =
          detail.skus?.find((s) => s.is_in_stock && s.stock_level > 0) ??
          detail.skus?.[0];
        if (!sku) {
          skipped += 1;
          continue;
        }
        await addItem(sku.id, {
          id: detail.id,
          title: detail.title,
          category: detail.category_name,
          color: detail.color_family,
        });
        added += 1;
      } catch {
        skipped += 1;
      }
    }
    if (added === 0) {
      showToast(
        "No dressed item has a confirmed purchasable size yet.",
        "error",
      );
      return;
    }
    showToast(
      skipped > 0
        ? `Added ${added} dressed item(s) to bag. ${skipped} skipped because a purchasable SKU was unavailable.`
        : `Added ${added} dressed piece(s) to shopping bag!`,
      skipped > 0 ? "info" : "success",
    );
    openCart();
  }, [appliedGarments, addItem, openCart, showToast]);

  const runTryOn = useCallback(
    async (overrides?: {
      userImageUrl?: string | null;
      avatarId?: string | null;
    }) => {
      await triggerMultiRender(appliedGarments, overrides);
    },
    [triggerMultiRender, appliedGarments],
  );

  const totalPrice = Object.values(appliedGarments).reduce(
    (sum, p) => sum + (p.base_price || 0),
    0,
  );

  return {
    tryOnStatus,
    motionStatus,
    errorMessage,
    isRendering: tryOnStatus === "rendering",
    isAnimating: motionStatus === "generating",
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
    vtonCapabilities,
    capabilityLoading,
    capabilityMessage,
    checkTryOnCapabilities: ensureCapabilities,
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
    visualSearchError,
    visualSearchResult,
    runVisualSearch,
  };
}
