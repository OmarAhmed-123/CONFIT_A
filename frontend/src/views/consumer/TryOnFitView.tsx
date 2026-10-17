import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useCatalogViewModel } from "../../viewmodels/useCatalogViewModel";
import { useUIStore } from "../../stores/uiStore";
import {
  TryOnIcon,
  RulerIcon,
  VisualSearchIcon,
  SparkleIcon,
} from "../../components/icons/ConfitIcons";
import {
  FitScoreBadge,
  EmptyState,
} from "../../components/common/CommonComponents";
import { CameraScanModal } from "../../components/tryon/CameraScanModal";
import { TryOnEngineStatus } from "../../components/tryon/TryOnEngineStatus";
import { CircularGalleryShowcase } from "../../components/showcase/DesignShowcases";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { resolveMessage } from "../../i18n/messages";

export const TryOnFitView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    products,
    isLoading,
    error: catalogError,
    refresh: refreshCatalog,
  } = useCatalogViewModel();
  const { openTryOn, openRuler, openVisualSearch } = useUIStore();
  // The feature card below used to select the virtual-try-on tab unconditionally,
  // so a shopper landed on a studio that could not render (2026-09-22).
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);

  const [activeTab, setActiveTab] = useState<
    "vton" | "scan" | "ruler" | "visual"
  >("vton");
  const [isCameraScanOpen, setIsCameraScanOpen] = useState(false);
  const supportedTryOnCategories = [
    "outerwear",
    "tops",
    "top",
    "shirt",
    "dress",
    "bottom",
    "trouser",
    "pants",
    "skirt",
  ];
  const isTryOnSupported = (categoryName?: string) =>
    supportedTryOnCategories.some((category) =>
      (categoryName || "").toLowerCase().includes(category),
    );

  return (
    <div className="min-w-0 space-y-10 overflow-x-hidden pb-20">
      <CircularGalleryShowcase
        tone="tryon"
        compact
        /* Spec 11 §1: 3D is Discover-only — this page always gets the 2D list. */
        enabled={false}
        eyebrow={t('tryon.gallery_eyebrow')}
        title={t('tryon.contexts_caption')}
        description={t('tryon.gallery_description')}
      />
      {/* Header */}
      <div className="rounded-3xl border border-brand-hairline bg-white p-8 shadow-2xs sm:p-12">
        <div className="max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-hairline bg-brand-wash px-3 py-1 text-xs font-semibold uppercase tracking-wider text-brand-charcoal">
            <SparkleIcon size={14} color="currentColor" />
            <span>{t('tryon.studio_badge')}</span>
          </div>
          <h1 className="font-serif text-3xl font-bold leading-tight text-brand-charcoal sm:text-4xl">
            {t('tryon.studio_headline')}
          </h1>
          <p className="text-xs font-light leading-relaxed text-slate-600 sm:text-sm">
            {t('tryon.studio_lede')}
          </p>
        </div>
      </div>

      {/* Live engine verdict: the user learns whether try-on can actually
          render BEFORE uploading a photo, and gets the published timing.
          Added after the 2026-09-21 audit: production advertised try-on while
          the GPU worker was offline and every job failed. */}
      <TryOnEngineStatus />

      <section className="rounded-3xl border border-brand-hairline bg-white p-5 shadow-2xs">
        <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-brand-muted">
              {t('tryon.privacy_eyebrow')}
            </span>
            <h2 className="mt-1 font-serif text-2xl font-bold text-brand-charcoal">
              {t('tryon.privacy_title')}
            </h2>
            <p className="mt-2 text-sm font-light leading-relaxed text-brand-muted">
              {t('tryon.privacy_body')}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
            {[
              t('tryon.step_choose'),
              t('tryon.step_fit_info'),
              t('tryon.step_preview'),
              t('tryon.step_share'),
            ].map((step, index) => (
              <div
                key={step}
                className="rounded-2xl bg-brand-wash p-3 text-slate-700"
              >
                <span className="mb-1 block font-serif text-lg font-bold text-brand-charcoal">
                  {index + 1}
                </span>
                {step}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature Selector Cards (4 columns) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Virtual Try-On — routes to the working capability when the GPU
            cannot render, instead of selecting a tab that will fail. */}
        <div
          onClick={() =>
            setActiveTab(tryOnKind === "render" ? "vton" : "ruler")
          }
          aria-disabled={tryOnKind === "blocked"}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === "vton"
              ? "border-brand-charcoal bg-brand-wash shadow-md"
              : "border-slate-200 bg-white hover:border-slate-300"
          } ${tryOnKind === "blocked" ? "opacity-60" : ""}`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-brand-charcoal flex items-center justify-center text-white">
              {tryOnKind === "render" ? (
                <TryOnIcon size={22} color="currentColor" isAi={true} />
              ) : (
                <RulerIcon size={22} color="currentColor" />
              )}
            </div>
            <h3 className="font-serif text-base font-bold text-brand-charcoal">
              {t("nav.virtual_tryon")}
            </h3>
            <p className="text-xs text-slate-600 font-light">
              {tryOn.userMessage
                ? resolveMessage(tryOn.userMessage, t)
                : t("tryon.vton_card_caption")}
            </p>
          </div>
          <span className="text-xs font-bold text-brand-charcoal mt-4 block">
            {tryOnKind === "render"
              ? t("tryon.cta_try_on")
              : t("tryon.cta_fit_check")}{" "}
            →
          </span>
        </div>

        {/* 2. Live Body Scan */}
        <div
          onClick={() => {
            setActiveTab("scan");
            setIsCameraScanOpen(true);
          }}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === "scan"
              ? "border-brand-charcoal bg-brand-wash shadow-md"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-brand-charcoal text-white flex items-center justify-center shadow-xs">
              <SparkleIcon size={22} color="#FFFFFF" />
            </div>
            <h3 className="font-serif text-base font-bold text-brand-charcoal">
              {t('tryon.scan_feature_title')}
            </h3>
            <p className="text-xs text-brand-muted font-light">
              Browser camera or manual measurements for a self-reported size
              profile; raw video is not uploaded by this flow.
            </p>
          </div>
          <span className="mt-4 block text-xs font-bold text-brand-charcoal">
            {t('tryon.scan_feature_cta')} <span aria-hidden="true">→</span>
          </span>
        </div>

        {/* 3. No-Photo Fit Finder — navigates to the dedicated /fit engine */}
        <div
          onClick={() => navigate("/fit")}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === "ruler"
              ? "border-brand-charcoal bg-brand-wash shadow-md"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-900">
              <RulerIcon size={22} color="#252729" />
            </div>
            <h3 className="font-serif text-base font-bold text-brand-charcoal">
              {t("nav.no_photo_fit")}
            </h3>
            <p className="text-xs text-brand-muted font-light">
              Zero-photo measurement calculator using the backend fit contract
              where product data supports it.
            </p>
          </div>
          <span className="text-xs font-bold text-slate-800 mt-4 block">
            Open Fit Finder →
          </span>
        </div>

        {/* 4. Visual Search */}
        <div
          onClick={() => {
            setActiveTab("visual");
            openVisualSearch();
          }}
          className={`p-5 rounded-3xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
            activeTab === "visual"
              ? "border-brand-charcoal bg-brand-wash shadow-md"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-xl bg-brand-wash flex items-center justify-center text-brand-charcoal">
              <VisualSearchIcon size={22} color="currentColor" />
            </div>
            <h3 className="font-serif text-base font-bold text-brand-charcoal">
              {t("nav.visual_search")}
            </h3>
            <p className="text-xs text-brand-muted font-light">
              Upload a moodboard image to search matching real catalog pieces.
            </p>
          </div>
          <span className="text-xs font-bold text-brand-charcoal mt-4 block">
            Match Outfit →
          </span>
        </div>
      </div>

      {/* Selectable Garments for Try-On */}
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="font-serif text-xl font-bold text-brand-charcoal">
            {t('tryon.catalog_heading')}
          </h3>
          <span className="text-xs text-brand-muted font-light">
            {isLoading
              ? t('tryon.catalog_loading')
              : catalogError && products.length === 0
                ? t('tryon.catalog_unavailable')
                : t('tryon.catalog_showing', { count: products.length })}
          </span>
        </div>

        {catalogError && products.length === 0 ? (
          // N-1: a failed catalog fetch must surface as an explicit error with
          // a retry — never as fabricated try-on garments.
          <EmptyState
            title={t('tryon.catalog_error_title')}
            description={catalogError}
            actionText={t('common.retry')}
            onAction={refreshCatalog}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {products.map((p) => (
              <div
                key={p.id}
                className="bg-white rounded-3xl border border-slate-200 p-3.5 shadow-sm hover:shadow-lg transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="h-60 rounded-2xl overflow-hidden bg-slate-100 mb-3 relative">
                    <img
                      src={p.thumbnail_url}
                      alt={p.title}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute top-2 left-2 flex flex-col gap-1">
                      <FitScoreBadge
                        score={p.style_compatibility_score}
                        label={t('tryon.style_match')}
                        verdict={t('tryon.style_match_verdict')}
                      />
                      <span
                        className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                          isTryOnSupported(p.category_name) &&
                          tryOnKind === "render"
                            ? "bg-emerald-700 text-white"
                            : "bg-slate-950/80 text-slate-200"
                        }`}
                      >
                        {isTryOnSupported(p.category_name) &&
                        tryOnKind === "render"
                          ? t('tryon.chip_vton')
                          : t('tryon.chip_fit_only')}
                      </span>
                    </div>
                  </div>
                  <span className="text-[10px] font-bold text-brand-muted uppercase tracking-wider">
                    {p.brand_name}
                  </span>
                  <h4 className="font-serif text-sm font-bold text-brand-charcoal truncate">
                    {p.title}
                  </h4>
                  {/* Price stays LTR inside the Arabic page (§7). */}
                  <div className="text-sm font-bold text-brand-charcoal mt-1" dir="ltr">
                    ${p.base_price.toFixed(2)}
                  </div>
                </div>

                {/* Card CTAs: instant modal-open actions (the async "Run
                    try-on" CTA inside the modal is the unified ActionButton).
                    min-h-11 = 44px touch target (§7); labels are i18n text,
                    never icon-only. */}
                <div className="pt-3 border-t border-slate-100 mt-3 grid grid-cols-2 gap-2">
                  <button data-motion="progressive"
                    type="button"
                    onClick={() => openRuler(p)}
                    className="min-h-11 py-2 px-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-[11px] font-semibold text-slate-700 flex items-center justify-center gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
                  >
                    <RulerIcon size={13} />
                    <span>{t('tryon.ruler_button')}</span>
                  </button>
                  <button data-motion="creative" data-motion-tone="icon"
                    type="button"
                    onClick={tryOn.gate({
                      render: () =>
                        isTryOnSupported(p.category_name)
                          ? openTryOn(p)
                          : openRuler(p),
                      fitCheck: () => openRuler(p),
                    })}
                    aria-disabled={
                      !isTryOnSupported(p.category_name) ||
                      tryOnKind === "blocked"
                    }
                    className="min-h-11 py-2 px-2 rounded-xl bg-brand-charcoal hover:bg-black text-white text-[11px] font-semibold flex items-center justify-center gap-1 shadow-sm disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
                  >
                    {isTryOnSupported(p.category_name) &&
                    tryOnKind === "render" ? (
                      <TryOnIcon size={13} color="currentColor" />
                    ) : (
                      <RulerIcon size={13} color="currentColor" />
                    )}
                    <span>
                      {isTryOnSupported(p.category_name) &&
                      tryOnKind === "render"
                        ? t('tryon.cta_try_on')
                        : t('tryon.cta_fit_check')}
                    </span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Live Camera Scan Modal */}
      <CameraScanModal
        isOpen={isCameraScanOpen}
        onClose={() => setIsCameraScanOpen(false)}
        onApplyMeasurements={(measurements) => {
          // A body-size profile must target apparel, not whichever catalogue
          // item happens to sort first (production currently starts with an
          // accessory that has no meaningful body-size recommendation).
          const product = products.find((candidate) =>
            isTryOnSupported(candidate.category_name),
          );
          if (!product) return;
          // This handoff requires an affirmative live rendering verdict. The
          // shared CTA kind is intentionally optimistic while its probe is
          // unresolved, but Apply must not spend the user's completed profile
          // on an unverified renderer. False OR unknown falls back safely.
          if (tryOn.renderAvailable === true) {
            openTryOn(product);
          } else {
            openRuler(product, measurements);
          }
        }}
      />
    </div>
  );
};
