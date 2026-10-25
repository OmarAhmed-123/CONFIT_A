import { ActionButton } from "../common/ActionButton";
import { translatableFrom } from "../../i18n/messages";
import React, { useEffect, useState, useRef } from "react";
import { useModalFocus } from "../../hooks/useModalFocus";
import { useTranslation } from "react-i18next";
import { useUIStore } from "../../stores/uiStore";
import { useTryOnViewModel } from "../../viewmodels/useTryOnViewModel";
import { useCatalogViewModel } from "../../viewmodels/useCatalogViewModel";
import { Product } from "../../models";
import {
  TryOnIcon,
  SparkleIcon,
  BagIcon,
  OutfitBuilderIcon,
  ShieldIcon,
  LockIcon,
} from "../icons/ConfitIcons";
import { FitScoreBadge } from "../common/CommonComponents";
import { CameraScanModal } from "./CameraScanModal";
import { compressImageToDataUrl } from "../../lib/imageUpload";
import { usePhotoConsent } from "../../privacy/usePhotoConsent";
import { formatMoney } from '../../i18n/format';
import { StatusIcon } from '../common/InteractionPrimitives';
import { HonestProductImage } from '../common/HonestProductImage';

export const VirtualTryOnModal: React.FC = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  const { tryOnProduct, closeTryOn, showToast } = useUIStore();
  const tryOnPanelRef = useModalFocus<HTMLDivElement>(
    closeTryOn,
    !!tryOnProduct,
  );
  const { products } = useCatalogViewModel();

  const {
    tryOnStatus,
    errorMessage,
    motionStatus,
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
    selectedAvatar,
    setSelectedAvatar,
    uploadedUserImage,
    setUploadedUserImage,
    appliedGarments,
    isBeforeAfterActive,
    setIsBeforeAfterActive,
    splitSliderPosition,
    setSplitSliderPosition,
    totalPrice,
    dynamicFitScore,
    capabilityLoading,
    capabilityMessage,
    vtonCapabilities,
    checkTryOnCapabilities,
    addGarmentToCanvas,
    removeGarmentFromCanvas,
    clearCanvas,
    undoLastAction,
    addAllDressedToCart,
    runTryOn,
    runAnimatedTryOn,
  } = useTryOnViewModel(tryOnProduct);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // This hook must run on EVERY render. The modal stays mounted globally and
  // returns null while no product is selected; placing it below that early
  // return changed the hook count when a product opened and crashed React with
  // invariant #310 (the production white screen reported on 2026-09-26).
  const { requestConsent, consentDialog } = usePhotoConsent('try_on');
  const [isCameraScanOpen, setIsCameraScanOpen] = useState(false);
  const [activeCategoryFilter, setActiveCategoryFilter] =
    useState<string>("All");
  const [isDragOver, setIsDragOver] = useState(false);
  const [isCompressing, setIsCompressing] = useState(false);

  // 2026-10-25 — these were four Unsplash head-and-shoulders PORTRAITS, so the
  // picker offered faces and the render put a garment on a face. They are now
  // AI-generated full-body studio figures (head to feet, portrait 2:3, light
  // neutral base so any garment colour produces a visible change), bundled in
  // public/vton-avatars and mirrored in the backend registry
  // (VTON_AVATARS / VTON_AVATAR_FRAMING). The ids are unchanged so a stale
  // bundle keeps working against the corrected assets.
  const avatars = [
    {
      id: "avatar_athletic_m",
      name: t("tryon.avatar_athletic_m"),
      img: "/vton-avatars/avatar_athletic_m.jpg",
      gender: "male",
    },
    {
      id: "avatar_hourglass_f",
      name: t("tryon.avatar_hourglass_f"),
      img: "/vton-avatars/avatar_hourglass_f.jpg",
      gender: "female",
    },
    {
      id: "avatar_curvy_f",
      name: t("tryon.avatar_curvy_f"),
      img: "/vton-avatars/avatar_curvy_f.jpg",
      gender: "female",
    },
    {
      id: "avatar_tall_m",
      name: t("tryon.avatar_tall_structured"),
      img: "/vton-avatars/avatar_tall_m.jpg",
      gender: "male",
    },
  ];

  const currentAvatarObj =
    avatars.find((a) => a.id === selectedAvatar) || avatars[0];
  const activeBaseImage = uploadedUserImage || currentAvatarObj.img;
  const appliedList = Object.entries(appliedGarments);
  const renderedResultImage = multiTryOnResult?.rendered_result_url || null;
  const activeDisplayImage =
    appliedList.length > 0 && renderedResultImage
      ? renderedResultImage
      : activeBaseImage;

  // Temporary delivery (product requirement): the generated try-on image is
  // returned in the authenticated response (data URL) and is NOT stored by
  // the server. The download is performed client-side (Blob) so no durable
  // copy is ever created — the bytes exist only in the user's browser.
  const handleDownloadRenderedResult = async () => {
    const src = renderedResultImage || activeDisplayImage;
    if (!src) return;
    try {
      let href = src;
      if (src.startsWith("data:")) {
        const res = await fetch(src);
        const blob = await res.blob();
        href = URL.createObjectURL(blob);
      }
      const ext = src.includes("image/jpeg")
        ? "jpg"
        : src.includes("image/webp")
          ? "webp"
          : "png";
      const a = document.createElement("a");
      a.href = href;
      a.download = `confit-try-on-${Date.now()}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (href.startsWith("blob:")) URL.revokeObjectURL(href);
    } catch (err) {
      console.warn("Try-on result download failed", err);
    }
  };

  // Filter shelf products
  const filteredProducts = products.filter((p) => {
    if (activeCategoryFilter === "All") return true;
    const cat = (p.category_name || "").toLowerCase();
    const title = (p.title || "").toLowerCase();
    if (activeCategoryFilter === "Outerwear")
      return (
        cat.includes("outer") ||
        title.includes("blazer") ||
        title.includes("jacket") ||
        title.includes("coat")
      );
    if (activeCategoryFilter === "Tops")
      return (
        cat.includes("top") ||
        cat.includes("shirt") ||
        title.includes("sweater") ||
        title.includes("knit")
      );
    if (activeCategoryFilter === "Bottoms")
      return (
        cat.includes("bottom") ||
        title.includes("trouser") ||
        title.includes("chino") ||
        title.includes("denim")
      );
    if (activeCategoryFilter === "Dresses")
      return cat.includes("dress") || title.includes("gown");
    if (activeCategoryFilter === "Footwear")
      return (
        cat.includes("footwear") ||
        cat.includes("shoe") ||
        title.includes("oxford") ||
        title.includes("loafer") ||
        title.includes("sandal") ||
        title.includes("sneaker")
      );
    if (activeCategoryFilter === "Accessories")
      return (
        cat.includes("access") ||
        title.includes("tie") ||
        title.includes("pocket") ||
        title.includes("belt") ||
        title.includes("clutch") ||
        title.includes("watch")
      );
    return true;
  });

  const filteredProductIds = filteredProducts.map((p) => p.id).join(",");
  useEffect(() => {
    if (!tryOnProduct || !filteredProductIds) return;
    checkTryOnCapabilities(filteredProducts.map((p) => p.id));
  }, [tryOnProduct, filteredProductIds, checkTryOnCapabilities]);

  if (!tryOnProduct) return null;

  const handleDragStart = (e: React.DragEvent, p: Product) => {
    e.dataTransfer.setData("application/json", JSON.stringify(p));
    e.dataTransfer.effectAllowed = "copy";
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDropOnCanvas = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    try {
      const dataStr = e.dataTransfer.getData("application/json");
      if (dataStr) {
        const prod = JSON.parse(dataStr) as Product;
        addGarmentToCanvas(prod);
      }
    } catch (err) {
      console.warn("Drop error:", err);
    }
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file after an error
    if (!file) return;
    // GDPR Art.7 explicit consent — captured BEFORE any bytes leave the
    // device. Previously this flow asserted `consentGranted: true` on the
    // user's behalf (see src/privacy/consentStore.ts); a default is not consent.
    if (!(await requestConsent())) return;
    // P0-02/P0-03 fix (2026-09-06 audit): raw phone photos (3–8 MB) exceeded
    // the serverless gateway body limit and died with an opaque HTTP 413.
    // Every person photo is now validated + compressed client-side before
    // it leaves the browser (see lib/imageUpload.ts).
    setIsCompressing(true);
    try {
      const { dataUrl } = await compressImageToDataUrl(file);
      setUploadedUserImage(dataUrl);
      // Pass the fresh data URL explicitly: state above is not committed
      // yet in this tick, and the render must use the photo the user just
      // uploaded — never the previous reference (avatar or older photo).
      runTryOn({ userImageUrl: dataUrl });
    } catch (err) {
      // translatableFrom() unwraps a LocalizedError into its key+params; any
      // other throw becomes the honest generic message with the real detail
      // interpolated, so nothing is swallowed and nothing is invented.
      showToast(translatableFrom(err), "error");
    } finally {
      setIsCompressing(false);
    }
  };

  // Primary active garment for rendering
  const primaryGarment = appliedList.length > 0 ? appliedList[0][1] : null;

  return (
    <>
      {consentDialog}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/40 backdrop-blur-sm animate-in fade-in duration-150">
        <div
          ref={tryOnPanelRef}
          role="dialog"
          aria-modal="true"
          aria-label={t('tryon.studio_aria')}
          tabIndex={-1}
          className="w-full max-w-6xl bg-white rounded-3xl shadow-2xl border border-brand-hairline overflow-hidden max-h-[96vh] flex flex-col"
        >
          {/* Header */}
          <div className="p-4 sm:p-5 bg-white text-brand-charcoal flex justify-between items-center border-b border-brand-hairline shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-wash border border-brand-hairline flex items-center justify-center text-brand-charcoal shadow-xs">
                <TryOnIcon size={22} color="#252729" isAi={true} />
              </div>
              <div>
                <h3 className="font-serif text-base sm:text-lg font-bold text-brand-charcoal flex items-center gap-2">
                  <span>{t('tryon.studio_title')}</span>
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-brand-wash border border-brand-hairline text-brand-charcoal font-sans font-semibold">
                    {t("tryon.multi_layer_title")}
                  </span>
                </h3>
                <p className="text-xs text-slate-500 font-light hidden sm:block">
                  {t("tryon.multi_layer_desc")}
                </p>
              </div>
            </div>
            <button data-motion="creative" data-motion-tone="icon"
              onClick={closeTryOn}
              className="w-8 h-8 rounded-full bg-slate-100 text-slate-600 hover:text-brand-charcoal hover:bg-slate-200 flex items-center justify-center transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Main 2-Column Split */}
          <div className="flex-1 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-slate-200">
            {/* LEFT: Dynamic Dressing Canvas & Controls (7 cols) */}
            <div className="lg:col-span-7 p-4 sm:p-6 bg-brand-wash flex flex-col justify-between space-y-4">
              {/* Top Bar: Subject Selector & Mode Switchers */}
              <div className="space-y-3">
                <div className="flex flex-wrap justify-between items-center gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-brand-charcoal">
                      {t("tryon.person_reference")}
                    </span>
                    <button data-motion="upload" data-motion-tone="icon"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isCompressing}
                      aria-label={
                        isCompressing ? t("tryon.processing_photo") : t("tryon.upload_your_photo")
                      }
                      className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 hover:border-brand-hairline text-slate-700 text-xs font-semibold flex items-center gap-1 shadow-2xs transition-all disabled:opacity-60"
                    >
                      <span>
                        {isCompressing
                          ? `⏳ ${t("tryon.processing_photo")}…`
                          : `📸 ${t("tryon.upload_photo")}`}
                      </span>
                    </button>
                    <button data-motion="upload"
                      onClick={() => setIsCameraScanOpen(true)}
                      className="px-3 py-1.5 rounded-xl bg-brand-wash border border-brand-hairline/40 hover:bg-brand-charcoal hover:text-white text-brand-charcoal text-xs font-semibold flex items-center gap-1 shadow-2xs transition-all"
                    >
                      <span>🎥 {t("tryon.live_scan")}</span>
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handlePhotoUpload}
                      className="hidden"
                    />
                  </div>

                  {/* Mode Selector Tabs: Static / Layer Assembly / Compare */}
                  <div className="flex items-center bg-white p-1 rounded-xl border border-slate-200 text-xs font-bold shadow-2xs">
                    <button data-motion="creative"
                      onClick={() => {
                        setActivePreviewTab("static");
                        setIsBeforeAfterActive(false);
                      }}
                      className={`px-3 py-1 rounded-lg transition-all ${
                        activePreviewTab === "static" && !isBeforeAfterActive
                          ? "bg-brand-charcoal text-white shadow-xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      {t("tryon.dressing_canvas")}
                    </button>
                    <button data-motion="creative"
                      onClick={() => {
                        setActivePreviewTab("animation");
                        setIsBeforeAfterActive(false);
                        if (!animationResult) runAnimatedTryOn();
                      }}
                      className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1 ${
                        activePreviewTab === "animation" && !isBeforeAfterActive
                          ? "bg-brand-charcoal text-white shadow-xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      <SparkleIcon size={12} color="currentColor" />
                      <span>{t('tryon.layer_assembly')}</span>
                    </button>
                    <button data-motion="creative"
                      onClick={() => {
                        setIsBeforeAfterActive(!isBeforeAfterActive);
                        setActivePreviewTab("static");
                      }}
                      className={`px-3 py-1 rounded-lg transition-all ${
                        isBeforeAfterActive
                          ? "bg-brand-charcoal text-white shadow-xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      {t("tryon.before_after_split")}
                    </button>
                  </div>
                </div>

                {/* A refusal the WORKER made, after seeing the real photo.
                    It carries VTON_PERSON_FRAMING_INVALID plus an English,
                    operator-grade message; showing only that would leave a
                    shopper — especially an Arabic one — with an error they
                    cannot act on. Pair the code with the localised framing
                    guidance the studio already ships. */}
                {tryOnStatus === 'failed' &&
                  typeof errorMessage === 'string' &&
                  errorMessage.includes('VTON_PERSON_FRAMING_INVALID') && (
                    <p
                      data-testid="tryon-framing-refusal"
                      role="alert"
                      className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] leading-snug font-medium text-amber-900"
                    >
                      {t("tryon.person_framing_hint")}
                    </p>
                  )}

                {/* Framing hint. The backend refuses a person reference it
                    KNOWS is a portrait (VTON_PERSON_FRAMING_INVALID). For an
                    upload it cannot tell — measured pixel heuristics rejected
                    legitimate photos — so the guidance is given here instead
                    of guessed at. */}
                <p
                  data-testid="tryon-framing-hint"
                  className="text-[11px] leading-snug text-slate-500"
                >
                  {t("tryon.person_framing_hint")}
                </p>
                <p
                  data-testid="tryon-avatar-disclosure"
                  className="text-[10px] leading-snug text-slate-400"
                >
                  {t("tryon.avatar_demo_disclosure")}
                </p>
                {/* The garment side of the same honesty. Products whose
                    try-on asset is a `generated-demo` flat-lay render a
                    stand-in, not the catalogue photograph: the shopper is
                    looking at a different garment than the one they may buy.
                    Driven by the backend's per-product provenance, never by a
                    blanket label — that would become false the day real
                    photography lands. */}
                {vtonCapabilities?.[tryOnProduct.id]?.garment_asset_provenance ===
                  "generated-demo" && (
                  <p
                    data-testid="tryon-garment-demo-disclosure"
                    className="text-[10px] leading-snug font-medium text-amber-700"
                  >
                    {t("tryon.garment_demo_disclosure")}
                  </p>
                )}

                {/* Avatar Strip */}
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {avatars.map((av) => (
                    <button data-motion="creative" data-motion-tone="icon"
                      key={av.id}
                      onClick={() => {
                        setSelectedAvatar(av.id);
                        setUploadedUserImage(null);
                        // Fresh values for the same-tick render: the new
                        // avatar and the cleared photo (see overrides
                        // contract on runTryOn in useTryOnViewModel).
                        runTryOn({ userImageUrl: null, avatarId: av.id });
                      }}
                      className={`flex items-center gap-2 p-1.5 pr-3 rounded-xl border text-left transition-all shrink-0 ${
                        selectedAvatar === av.id && !uploadedUserImage
                          ? "border-brand-hairline bg-white ring-2 ring-brand-charcoal/30 shadow-2xs"
                          : "border-slate-200 bg-white/70 hover:bg-white text-slate-600"
                      }`}
                    >
                      <img
                        src={av.img}
                        alt={av.name}
                        className="w-7 h-7 rounded-lg object-cover"
                      />
                      <span className="text-[11px] font-semibold">
                        {av.name}
                      </span>
                    </button>
                  ))}
                  {uploadedUserImage && (
                    <div className="flex items-center gap-2 p-1.5 pr-3 rounded-xl border border-brand-hairline bg-brand-wash text-brand-charcoal text-[11px] font-bold shrink-0 shadow-2xs">
                      <img
                        src={uploadedUserImage}
                        alt="User"
                        className="w-7 h-7 rounded-lg object-cover"
                      />
                      <span>{t('tryon.custom_photo_active')}</span>
                      <button data-motion="destructive" data-motion-tone="icon"
                        onClick={() => setUploadedUserImage(null)}
                        className="text-xs hover:text-rose-600 ml-1 min-w-[44px] min-h-[44px] flex items-center justify-center"
                        title={t('tryon.remove_photo')}
                        aria-label={t('tryon.remove_photo')}
                      >
                        <span aria-hidden="true">✕</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Main Interactive Stage / Person Canvas */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDropOnCanvas}
                className={`relative h-[400px] sm:h-[480px] rounded-3xl overflow-hidden bg-slate-950 border-2 transition-all flex items-center justify-center shadow-inner ${
                  isDragOver
                    ? "border-brand-hairline ring-4 ring-brand-charcoal/30 bg-slate-900"
                    : "border-slate-300"
                }`}
              >
                {/* 1. Before / After Split Slider Mode */}
                {isBeforeAfterActive ? (
                  <div className="relative w-full h-full">
                    {/* Underlying Dressed State (AI-Generated Image) */}
                    <div className="relative w-full h-full">
                      <img
                        src={activeDisplayImage}
                        alt="Dressed State"
                        className="w-full h-full object-cover select-none"
                      />
                    </div>

                    {/* Left Clipped Original Image (Undressed Reference) */}
                    <div
                      className="absolute inset-0 overflow-hidden"
                      style={{
                        clipPath: `polygon(0 0, ${splitSliderPosition}% 0, ${splitSliderPosition}% 100%, 0 100%)`,
                      }}
                    >
                      <img
                        src={activeBaseImage}
                        alt="Original Reference"
                        className="w-full h-full object-cover select-none"
                      />
                    </div>

                    {/* Divider Line & Draggable Handle */}
                    <div
                      className="absolute top-0 bottom-0 w-1 bg-brand-charcoal shadow-[0_0_12px_#242526] cursor-ew-resize flex items-center justify-center pointer-events-none"
                      style={{ left: `${splitSliderPosition}%` }}
                    >
                      <div className="w-7 h-7 rounded-full bg-brand-charcoal text-white text-xs font-black flex items-center justify-center shadow-xl border-2 border-white">
                        ↔
                      </div>
                    </div>

                    {/* Interactive Slider Input */}
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={splitSliderPosition}
                      onChange={(e) =>
                        setSplitSliderPosition(Number(e.target.value))
                      }
                      className="absolute inset-x-4 bottom-4 opacity-80 hover:opacity-100 accent-brand-charcoal z-20 cursor-ew-resize"
                    />

                    <span className="absolute top-3 left-3 px-3 py-1 rounded-full bg-slate-950/85 backdrop-blur-md text-white text-[10px] font-bold border border-white/20 z-10">
                      {t("tryon.split_original", { pos: splitSliderPosition, rest: 100 - splitSliderPosition })}
                    </span>
                  </div>
                ) : activePreviewTab === "animation" && animationResult ? (
                  /* 2. Layer Assembly Sequence Player — honest placeholder on failure */
                  <div className="relative w-full h-full flex flex-col justify-between p-4 bg-slate-950">
                    <HonestProductImage
                      src={
                        animationResult.keyframes_sequence[activeKeyframeIndex]
                          ?.image_url || activeDisplayImage
                      }
                      alt="Animation Frame"
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-black/40 pointer-events-none" />

                    {/* Top Aspect & Animation Status */}
                    <div className="relative z-10 flex justify-between items-center">
                      <span className="px-2.5 py-1 rounded-full bg-brand-charcoal text-white text-[10px] font-bold">
                        🎬 Layer Assembly Sequence
                      </span>
                      <div className="flex gap-1 bg-black/60 p-0.5 rounded-lg border border-white/10 text-[9px] text-white">
                        {(["9:16", "4:5", "1:1"] as const).map((asp) => (
                          <button data-motion="creative" data-motion-tone="icon"
                            key={asp}
                            onClick={() => setOutputAspect(asp)}
                            className={`px-1.5 py-0.5 rounded ${outputAspect === asp ? "bg-brand-charcoal text-white font-bold" : "hover:bg-white/20"}`}
                          >
                            {asp}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Bottom Step-by-Step Motion Timeline */}
                    <div className="relative z-10 space-y-2 bg-black/75 backdrop-blur-md p-3 rounded-2xl border border-white/10">
                      <div className="flex justify-between items-center text-xs text-white">
                        <span className="font-bold text-white">
                          {t("tryon.step_label")} {activeKeyframeIndex + 1} of{" "}
                          {animationResult.keyframes_sequence.length}:
                        </span>
                        <span className="text-[11px] text-slate-300">
                          {
                            animationResult.keyframes_sequence[
                              activeKeyframeIndex
                            ]?.status
                          }
                        </span>
                      </div>
                      <div className="flex gap-1.5">
                        {animationResult.keyframes_sequence.map((kf, idx) => (
                          <button data-motion="creative" data-motion-tone="icon"
                            key={kf.step}
                            onClick={() => setActiveKeyframeIndex(idx)}
                            className={`flex-1 h-1.5 rounded-full transition-all ${
                              activeKeyframeIndex === idx
                                ? "bg-brand-charcoal"
                                : "bg-white/20 hover:bg-white/40"
                            }`}
                            title={kf.product_title}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  /* 3. Static High-Fidelity Generative Try-On Stage — honest placeholder on failure */
                  <div className="relative w-full h-full flex items-center justify-center">
                    <HonestProductImage
                      src={activeDisplayImage}
                      alt="Try-On Canvas"
                      className="w-full h-full object-cover select-none"
                    />

                    {/* Top Status (Honest labels) — the badge is a catalog
                        style-compatibility heuristic, NOT a drape measurement:
                        the audit's "92% Fit - Style Compatibility" was this
                        number wearing a misleading "% Fit" label. It is hidden
                        entirely when nothing is applied, and explicitly marked
                        "engine verification pending" while a render is in
                        flight (only the engine's verify gate — PR #59 —
                        confirms a layer was actually applied). */}
                    <div className="absolute top-3 left-3 flex flex-col gap-1.5 pointer-events-none">
                      {appliedList.length > 0 && (
                        <FitScoreBadge
                          score={dynamicFitScore}
                          label={t("tryon.fit_badge_label")}
                          verdict={
                            isRendering
                              ? t("tryon.fit_badge_pending")
                              : t("tryon.fit_badge_heuristic")
                          }
                        />
                      )}
                      <span className="px-2.5 py-0.5 rounded-full bg-slate-950/75 backdrop-blur-md text-[9px] font-medium text-slate-300 border border-white/10 w-fit">
                        {appliedList.length === 0
                          ? t("tryon.base_silhouette")
                          : isRendering
                            ? t(appliedList.length === 1 ? "tryon.rendering_layers" : "tryon.rendering_layers_plural", { count: appliedList.length })
                            : t(appliedList.length === 1 ? "tryon.dressed_with_layers" : "tryon.dressed_with_layers_plural", { count: appliedList.length })}
                      </span>
                    </div>

                    {/* Download — the server retains no copy of the generated
                        image (temporary delivery); this saves it client-side */}
                    {renderedResultImage && !isRendering && (
                      <>
                        <button data-motion="download"
                          onClick={handleDownloadRenderedResult}
                          className="absolute bottom-3 right-3 px-3 py-1.5 rounded-full bg-brand-charcoal text-white text-[11px] font-bold shadow-lg hover:brightness-110 active:scale-95 transition-all"
                        >
                          ⬇ {t("tryon.download_result")}
                        </button>
                        <span className="absolute bottom-3 left-3 px-2.5 py-1 rounded-full bg-slate-950/75 text-white text-[9px] font-semibold border border-white/15">
                          {t("tryon.temporary_render_note")}
                        </span>
                      </>
                    )}

                    {/* Ghost-hands remediation (P0): the render result must
                        surface the engine's per-layer verification instead of
                        presenting any image as a clean success. */}
                    {multiTryOnResult?.verification &&
                      multiTryOnResult.verification.all_layers_verified === false &&
                      !isRendering && (
                        <div className="absolute inset-x-3 bottom-14 rounded-2xl border border-red-300/60 bg-red-50/95 p-3 text-[11px] font-semibold text-red-900 shadow-lg">
                          Quality gate: the engine did NOT verify every garment
                          layer in this render — it may be incomplete or show
                          artifacts from the catalog photo. Treat it as a
                          preview, not a final fit.
                        </div>
                      )}

                    {capabilityMessage && !isRendering && (
                      <div
                        className={`absolute inset-x-3 rounded-2xl border border-amber-300/50 bg-amber-50/95 p-3 text-[11px] font-semibold text-amber-900 shadow-lg ${
                          multiTryOnResult?.verification?.all_layers_verified === false
                            ? "bottom-32"
                            : "bottom-14"
                        }`}
                      >
                        {capabilityMessage}
                      </div>
                    )}

                    {/* Active Rendering Overlay */}
                    {isRendering && (
                      <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center p-6 text-center space-y-3 animate-in fade-in duration-150">
                        <div className="w-10 h-10 border-3 border-brand-hairline border-t-transparent rounded-full motion-safe:animate-spin"></div>
                        <div>
                          <h4 className="font-serif text-sm font-bold text-white">
                            {t("tryon.synthesizing_layer")}
                          </h4>
                          <p className="text-[11px] text-slate-300 font-light mt-0.5">
                            Draping the garment onto your photo —
                            identity-preserving compositing.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Dressed Layers Strip & Reorder List */}
              <div className="space-y-2 bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs">
                <div className="flex justify-between items-center pb-1 border-b border-slate-100">
                  <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                    {t("tryon.dressed_layers", { count: appliedList.length })}
                  </span>
                  <div className="flex items-center gap-2">
                    {/* Spec 08: explicit Run try-on CTA with trust state —
                        CONTROLLED by the viewmodel's real workflow status.
                        "failed" relabels to an actionable retry; pending is
                        click-guarded (the engine never gets two renders from
                        one control) and announced as text, not only by the
                        overlay animation. */}
                    {appliedList.length > 0 && (
                      <ActionButton
                        intent="creative"
                        state={
                          isRendering
                            ? 'pending'
                            : tryOnStatus === 'failed'
                              ? 'error'
                              : 'idle'
                        }
                        onPress={() => runTryOn()}
                        labels={{
                          idle: t('tryon.run_try_on'),
                          pending: t('tryon.rendering'),
                          error: t('tryon.retry_render'),
                        }}
                        data-testid="run-tryon-cta"
                        className="px-3 rounded-xl bg-brand-charcoal hover:bg-brand-charcoal text-white text-[11px] font-bold transition-all"
                      />
                    )}
                    <button data-motion="recovery" data-motion-tone="edge"
                      onClick={undoLastAction}
                      className="inline-flex min-h-6 items-center text-[11px] font-semibold text-slate-500 hover:text-slate-900"
                    >
                      ↩ {t("tryon.btn_undo")}
                    </button>
                    <button data-motion="destructive"
                      onClick={clearCanvas}
                      className="inline-flex min-h-6 items-center text-[11px] font-semibold text-rose-700 hover:underline"
                    >
                      {t("tryon.clear_all")}
                    </button>
                  </div>
                </div>

                {appliedList.length === 0 ? (
                  <p className="text-xs text-slate-400 font-light py-1 text-center">
                    Drag any garment from the right catalog shelf or tap "+
                    Dress" to style this person.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {appliedList.map(([slot, item]) => (
                      <div
                        key={slot}
                        className="inline-flex items-center gap-2 bg-brand-wash border border-slate-200 rounded-xl px-2.5 py-1 text-xs"
                      >
                        <HonestProductImage
                          src={item.thumbnail_url}
                          alt={item.title}
                          className="w-5 h-5 rounded object-cover"
                        />
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                          {slot.replace("_", " ")}
                        </span>
                        <span className="font-semibold text-slate-800 line-clamp-1 max-w-[120px]">
                          {item.title}
                        </span>
                        <span className="font-bold text-brand-charcoal">
                          {formatMoney(Math.round(item.base_price * 100), item.currency || 'USD', lang)}
                        </span>
                        <button data-motion="destructive" data-motion-tone="icon"
                          onClick={() => removeGarmentFromCanvas(slot)}
                          className="w-4 h-4 rounded-full bg-slate-200 hover:bg-rose-500 hover:text-white text-slate-600 flex items-center justify-center text-[9px] transition-colors min-w-[44px] min-h-[44px]"
                          title={t('tryon.remove_item')}
                          aria-label={t('tryon.remove_item')}
                        >
                          <span aria-hidden="true">✕</span>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Bottom Action Footer */}
              <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-2">
                <div>
                  <span className="text-[10px] text-slate-400 block">
                    {t("tryon.total_dressed_look")}
                  </span>
                  <span className="font-serif text-lg font-black text-brand-charcoal">
                    ${totalPrice.toFixed(2)}
                  </span>
                </div>
                <div className="flex gap-2 w-full sm:w-auto">
                  <button data-motion="creative" data-motion-tone="icon"
                    onClick={runAnimatedTryOn}
                    disabled={isAnimating || appliedList.length === 0}
                    className="flex-1 sm:flex-none px-4 py-2.5 rounded-xl bg-brand-charcoal hover:bg-brand-charcoal disabled:opacity-40 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
                  >
                    <SparkleIcon size={14} color="currentColor" />
                    <span>
                      {isAnimating ? t("tryon.btn_synthesizing") : t("tryon.btn_play_sequence")}
                    </span>
                  </button>
                  <button data-motion="commerce"
                    onClick={addAllDressedToCart}
                    disabled={appliedList.length === 0}
                    className="flex-1 sm:flex-none px-6 py-2.5 rounded-xl bg-brand-charcoal hover:bg-black disabled:opacity-40 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-1.5"
                  >
                    <BagIcon size={14} color="#FFFFFF" />
                    <span>{t("tryon.add_items_to_bag", { count: appliedList.length })}</span>
                  </button>
                </div>
              </div>
            </div>

            {/* RIGHT: Multi-Brand Draggable Catalog Shelf (5 cols) */}
            <div className="lg:col-span-5 p-4 sm:p-6 bg-white flex flex-col justify-between space-y-4">
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1.5">
                    <OutfitBuilderIcon size={18} color="#242526" />
                    <h4 className="font-serif text-sm sm:text-base font-bold text-brand-charcoal">
                      {t("tryon.catalog_shelf_title")}
                    </h4>
                  </div>
                  <span className="text-[10px] text-slate-400 font-light">
                    {t("tryon.catalog_shelf_hint")}
                  </span>
                </div>

                {/* Category Tabs */}
                <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
                  {[
                    "All",
                    "Outerwear",
                    "Tops",
                    "Bottoms",
                    "Dresses",
                    "Footwear",
                    "Accessories",
                  ].map((cat) => (
                    <button data-motion="creative" data-motion-tone="icon"
                      key={cat}
                      onClick={() => setActiveCategoryFilter(cat)}
                      className={`px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                        activeCategoryFilter === cat
                          ? "bg-brand-charcoal text-white shadow-2xs"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>

                {/* Product Card Grid */}
                <div className="grid grid-cols-2 gap-3 max-h-[500px] overflow-y-auto pr-1">
                  {filteredProducts.map((p) => {
                    const isAlreadyDressed = Object.values(
                      appliedGarments,
                    ).some((g) => g.id === p.id);
                    const capability = vtonCapabilities[p.id];
                    const canDragForTryOn = capability?.state === "supported";
                    return (
                      <div
                        key={p.id}
                        draggable={canDragForTryOn}
                        onDragStart={(e) => {
                          if (canDragForTryOn) handleDragStart(e, p);
                        }}
                        className={`p-3 rounded-2xl border transition-all flex flex-col justify-between ${canDragForTryOn ? "cursor-grab active:cursor-grabbing" : "cursor-default"} group select-none ${
                          isAlreadyDressed
                            ? "border-brand-hairline bg-brand-wash ring-1 ring-brand-charcoal"
                            : "border-slate-200 bg-brand-wash hover:border-brand-hairline hover:shadow-sm"
                        }`}
                      >
                        <div>
                          <div className="aspect-[3/4] rounded-xl overflow-hidden bg-white mb-2 relative shadow-2xs">
                            <HonestProductImage
                              src={p.thumbnail_url}
                              alt={p.title}
                              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            />
                            <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/60 text-[9px] text-white font-medium capitalize">
                              {p.category_name}
                            </span>
                            {isAlreadyDressed && (
                              <span className="absolute bottom-1 right-1 px-2 py-0.5 rounded-full bg-emerald-600 text-[9px] text-white font-bold shadow-xs">
                                <StatusIcon status="success" size={9} className="me-0.5 align-middle" /> {t("tryon.in_outfit")}
                              </span>
                            )}
                          </div>
                          <span className="text-[9px] text-slate-400 font-bold uppercase tracking-wider block truncate">
                            {p.brand_name}
                          </span>
                          <h5 className="font-serif text-xs font-bold text-brand-charcoal line-clamp-1 mt-0.5">
                            {p.title}
                          </h5>
                          <span className="text-xs font-bold text-brand-charcoal mt-0.5 block">
                            {formatMoney(Math.round(p.base_price * 100), p.currency || 'USD', lang)}
                          </span>
                        </div>

                        {(() => {
                          const capability = vtonCapabilities[p.id];
                          const supportUnknown = !capability;
                          const isSupported = capability?.state === "supported";
                          const disabled =
                            !isAlreadyDressed &&
                            (capabilityLoading ||
                              supportUnknown ||
                              !isSupported);
                          // Spec 14 §8: words carry the state — no unicode
                          // glyph as a status channel (the button's disabled
                          // state + title explain the rest).
                          const label = isAlreadyDressed
                            ? t("tryon.btn_remove")
                            : capabilityLoading || supportUnknown
                              ? t("tryon.btn_checking_support")
                              : isSupported
                                ? t("tryon.btn_dress_on_body")
                                : t("tryon.btn_not_in_vton");
                          const title =
                            capability?.message ||
                            t("tryon.capability_title_fallback");
                          return (
                            <button data-motion="creative" data-motion-tone="icon"
                              type="button"
                              disabled={disabled}
                              title={title}
                              onClick={() => {
                                if (isAlreadyDressed) {
                                  const slot = Object.keys(
                                    appliedGarments,
                                  ).find((k) => appliedGarments[k].id === p.id);
                                  if (slot) removeGarmentFromCanvas(slot);
                                } else {
                                  addGarmentToCanvas(p);
                                }
                              }}
                              className={`mt-2.5 w-full py-1.5 rounded-xl text-[11px] font-bold transition-all flex items-center justify-center gap-1 ${
                                isAlreadyDressed
                                  ? "bg-slate-200 text-slate-700 hover:bg-rose-100 hover:text-rose-700"
                                  : disabled
                                    ? "bg-slate-100 text-slate-600 cursor-not-allowed"
                                    : "bg-white border border-slate-300 hover:bg-brand-charcoal hover:text-white text-slate-800 shadow-2xs"
                              }`}
                            >
                              {label}
                            </button>
                          );
                        })()}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Privacy Footer Notice */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-[10px] text-slate-500 font-light leading-relaxed">
                🔒 <strong>{t("tryon.privacy_note_label")}</strong> {
                  t("tryon.privacy_note_body")
                }
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Live Camera Scan Modal */}
      <CameraScanModal
        isOpen={isCameraScanOpen}
        onClose={() => setIsCameraScanOpen(false)}
        onApplyMeasurements={() => {
          runTryOn();
        }}
      />
    </>
  );
};
