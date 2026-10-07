import { translatableFrom, resolveMessage, type TranslatableMessage } from "../../i18n/messages";
import React, { useState } from "react";
import { useModalFocus } from "../../hooks/useModalFocus";
import { compressImageToDataUrl } from "../../lib/imageUpload";
import { usePhotoConsent } from "../../privacy/usePhotoConsent";
import { useTranslation } from "react-i18next";
import { useUIStore } from "../../stores/uiStore";
import { useTryOnViewModel } from "../../viewmodels/useTryOnViewModel";
import { VisualSearchIcon, SparkleIcon } from "../icons/ConfitIcons";
import { catalogService } from "../../services/apiServices";
import { HonestProductImage } from "../common/HonestProductImage";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { formatMoney } from '../../i18n/format';
import { StatusIcon } from '../common/InteractionPrimitives';

export const VisualSearchModal: React.FC = () => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? 'en';
  const { isVisualSearchOpen, closeVisualSearch, openTryOn, openRuler, showToast } =
    useUIStore();
  // Every try-on entry point goes through this gate. Without it this modal
  // promised "Try On This Match" even when the engine had already reported it
  // could not render — the shopper picked a match, waited, and got nothing.
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);

  const panelRef = useModalFocus<HTMLDivElement>(
    closeVisualSearch,
    isVisualSearchOpen,
  );
  const {
    visualSearchLoading,
    visualSearchResult,
    visualSearchError,
    runVisualSearch,
  } = useTryOnViewModel();

  const [inputUrl, setInputUrl] = useState("");
  const [selectedSample, setSelectedSample] = useState("");
  // Upload-your-own-photo path (audit: the modal previously offered only
  // samples and a URL — no way to search with the user's own image).
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<TranslatableMessage | null>(null);
  const [isCompressing, setIsCompressing] = useState(false);
  const [openingMatchId, setOpeningMatchId] = useState<number | null>(null);

  // Consent for the photo searched against the catalog. A search image is
  // still personal data: it can contain the user, their home, their body.
  const { requestConsent, consentDialog } = usePhotoConsent('visual_search');

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    // GDPR Art.7 explicit consent — captured BEFORE any bytes leave the
    // device. Previously this flow asserted `consentGranted: true` on the
    // user's behalf (see src/privacy/consentStore.ts); a default is not consent.
    if (!(await requestConsent())) return;
    // P0-03 fix: the old 8 MB raw ceiling still exceeded the serverless
    // gateway body limit (~4.5 MB) — uploads died with HTTP 413. Photos now
    // go through the shared validate + compress pipeline before upload.
    setUploadError(null);
    setIsCompressing(true);
    try {
      const { dataUrl } = await compressImageToDataUrl(file);
      setUploadedImage(dataUrl);
      setSelectedSample("");
      runVisualSearch({ imageBase64: dataUrl });
    } catch (err) {
      setUploadError(translatableFrom(err));
    } finally {
      setIsCompressing(false);
    }
  };

  if (!isVisualSearchOpen) return null;

  const samples = [
    {
      label: t("tryon.vs_sample_blazer"),
      url: "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80",
    },
    {
      label: t("tryon.vs_sample_dress"),
      url: "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500&auto=format&fit=crop&q=80",
    },
    {
      label: t("tryon.vs_sample_shirt"),
      url: "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500&auto=format&fit=crop&q=80",
    },
  ];

  // The backend labels matches with EN display strings
  // ("Exact Match"…). Translate the three known values; an unknown new
  // value still renders readably instead of vanishing (same fallback
  // philosophy as occasionLabel on DiscoverView).
  const matchTypeLabel = (value: string) => {
    const key = {
      "Exact Match": "tryon.vs_match_type_exact",
      "Silhouette Match": "tryon.vs_match_type_silhouette",
      "Complementary Alternative": "tryon.vs_match_type_complementary",
    }[value];
    return key ? t(key) : value;
  };

  const openMatchInTryOn = async (productId: number) => {
    if (tryOnKind === "blocked") return;
    setOpeningMatchId(productId);
    try {
      const detail = await catalogService.getProductDetail(String(productId));
      closeVisualSearch();
      // Degrade to the measurement path rather than opening a studio that
      // cannot render; the label below already says which one this is.
      if (tryOnKind === "fit_check") {
        openRuler(detail);
      } else {
        openTryOn(detail);
      }
    } catch (err: any) {
      showToast(
        err?.message || t("tryon.vs_detail_error"),
        "error",
      );
    } finally {
      setOpeningMatchId(null);
    }
  };

  const handleSearch = (imgUrl?: string) => {
    if (uploadedImage) {
      runVisualSearch({ imageBase64: uploadedImage });
      return;
    }
    const target = imgUrl || inputUrl || samples[0].url;
    runVisualSearch(target);
  };

  return (
    <>
    {consentDialog}
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-150">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('tryon.visual_search')}
        tabIndex={-1}
        className="w-full max-w-4xl bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden max-h-[92vh] flex flex-col"
      >
        {/* Header */}
        <div className="p-4 sm:p-6 border-b border-slate-100 bg-[#1B1F3B] text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#B8935A] flex items-center justify-center text-slate-950">
              <VisualSearchIcon size={22} color="#1B1F3B" />
            </div>
            <div>
              <h3 className="font-serif text-lg font-bold text-white">
                {t("tryon.visual_search_title")}
              </h3>
              <p className="text-xs text-slate-300">
                {t("tryon.visual_search_desc")}
              </p>
            </div>
          </div>
          <button
            onClick={closeVisualSearch}
            type="button"
            aria-label={t("a11y.close_dialog")}
            className="min-h-11 min-w-11 rounded-full bg-slate-800 text-slate-300 hover:text-white flex items-center justify-center transition-colors"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Top Input & Sample Inspiration */}
          <div className="space-y-3">
            <label className="text-xs font-bold text-slate-800 block">
              {t("tryon.vs_step1_label")}
            </label>

            {/* Upload your own photo — visible labelled trigger (the VTON-02
                lesson: a file input is only usable with a real, visible
                trigger; sr-only input inside a styled <label> is the
                accessible pattern). The uploaded photo is sent to the same
                real /tryon/visual-search endpoint via image_base64. */}
            <div className="flex items-center gap-3">
              <label
                htmlFor="vs-photo-upload"
                className="cursor-pointer inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#FDF8EE] border border-[#B8935A]/50 text-[#A37E44] hover:bg-[#C5A059] hover:text-slate-950 text-xs font-bold transition-all"
              >
                <span aria-hidden="true">📷</span>
                <span>{t('tryon.upload_your_photo')}</span>
              </label>
              <input
                id="vs-photo-upload"
                type="file"
                accept="image/*"
                onChange={handleFileSelected}
                className="sr-only"
              />
              {uploadedImage && (
                <div className="flex items-center gap-2">
                  <img
                    src={uploadedImage}
                    alt={t("tryon.vs_uploaded_alt")}
                    className="w-10 h-10 rounded-lg object-cover border border-[#B8935A]"
                  />
                  <span className="text-[11px] text-slate-500 font-semibold">
                    {t("tryon.vs_searching_with_photo")}
                  </span>
                </div>
              )}
            </div>
            {uploadError && (
              <p
                className="text-[11px] text-rose-600 font-semibold"
                role="alert"
              >
                {resolveMessage(uploadError, t)}
              </p>
            )}

            <div className="grid grid-cols-3 gap-3">
              {samples.map((s) => (
                <button
                  key={s.label}
                  onClick={() => {
                    setUploadedImage(null);
                    setSelectedSample(s.url);
                    handleSearch(s.url);
                  }}
                  className={`flex items-center gap-2.5 p-2 rounded-xl border text-left transition-all ${
                    selectedSample === s.url
                      ? "border-[#B8935A] bg-[#FDF8EE] ring-1 ring-[#B8935A]"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <img
                    src={s.url}
                    alt={s.label}
                    className="w-10 h-10 rounded-lg object-cover"
                  />
                  <span className="text-xs font-semibold text-slate-800 line-clamp-1">
                    {s.label}
                  </span>
                </button>
              ))}
            </div>

            <div className="flex gap-2 pt-1">
              <input
                type="text"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                placeholder={t('tryon.paste_image_url')}
                className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-[#B8935A]"
              />
              {/* aria-busy, NOT disabled: `disabled` drops focus to <body>
                  mid-search, and useModalFocus then ignores Escape (its
                  top-most-modal guard requires focus inside the panel) —
                  the shopper could no longer close the dialog from the
                  keyboard. Found by the C02 goal E2E (G10). */}
              <button
                onClick={() => {
                  if (!visualSearchLoading) handleSearch();
                }}
                aria-busy={visualSearchLoading}
                aria-disabled={visualSearchLoading}
                className={`px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#2A3C78] text-white text-xs font-semibold shadow-sm transition-all ${
                  visualSearchLoading ? "opacity-60 cursor-wait" : ""
                }`}
              >
                {visualSearchLoading ? t("tryon.vs_analyzing") : t("tryon.vs_search_style")}
              </button>
            </div>
          </div>

          {/* SEARCH-01: explicit error terminal state — the modal must never
              sit silently after a failed/timed-out analysis. */}
          {visualSearchError && !visualSearchLoading && (
            <div
              className="space-y-3 pt-2 border-t border-slate-100"
              role="alert"
            >
              <div className="flex items-start gap-2 bg-rose-50 border border-rose-200 p-3 rounded-xl text-xs text-rose-700">
                <StatusIcon status="error" size={14} className="mt-0.5 shrink-0" />
                <span>{visualSearchError}</span>
              </div>
              <button
                onClick={() => handleSearch(selectedSample || undefined)}
                className="px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold"
              >
                {t("tryon.vs_try_again")}
              </button>
            </div>
          )}

          {!visualSearchResult &&
            !visualSearchError &&
            !visualSearchLoading && (
              <div className="pt-4 border-t border-slate-100 text-center text-xs text-slate-500 font-light">
                {t("tryon.vs_empty_hint", { cta: t("tryon.vs_search_style") })}
              </div>
            )}

          {/* Vision Detection Result */}
          {visualSearchResult && (
            <div className="space-y-4 pt-2 border-t border-slate-100">
              {visualSearchResult.analysis_available ? (
                <div className="flex items-center gap-2 bg-[#FDF8EE] border border-[#B8935A]/30 p-3 rounded-xl text-xs text-slate-800">
                  <SparkleIcon size={16} color="#B8935A" />
                  <span>
                    {t("tryon.vs_detected", {
                      category: visualSearchResult.detected_category,
                      color: visualSearchResult.detected_color,
                      style: visualSearchResult.detected_style,
                    })}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 p-3 rounded-xl text-xs text-slate-600">
                  <SparkleIcon size={16} color="#94A3B8" />
                  <span>{t("tryon.vs_analysis_unavailable")}</span>
                </div>
              )}

              {/* Match Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {visualSearchResult.matches.map((match) => (
                  <div
                    key={match.product_id}
                    className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm hover:shadow-md transition-all flex flex-col justify-between group"
                  >
                    <div>
                      <div className="h-44 rounded-xl overflow-hidden bg-slate-100 mb-2 relative">
                        <HonestProductImage
                          src={match.image_url}
                          alt={match.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        />
                        <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-[#1B1F3B]/80 backdrop-blur-sm text-[10px] font-bold text-[#B8935A]">
                          {t("tryon.vs_match_score", { score: match.similarity_score })}
                        </span>
                        <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-white/90 text-[10px] font-bold text-slate-800">
                          {matchTypeLabel(match.match_type)}
                        </span>
                      </div>
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                        {match.brand_name}
                      </span>
                      <h5 className="text-xs font-bold text-[#1B1F3B] line-clamp-1 mb-1">
                        {match.title}
                      </h5>
                      <span className="text-sm font-bold text-[#1B1F3B]">
                        {formatMoney(Math.round(match.price * 100), match.currency || 'USD', lang)}
                      </span>
                    </div>

                    <button
                      onClick={() => openMatchInTryOn(match.product_id)}
                      disabled={
                        openingMatchId === match.product_id ||
                        tryOnKind === "blocked"
                      }
                      title={
                        tryOnKind === "blocked" && tryOn.userMessage
                          ? resolveMessage(tryOn.userMessage, t)
                          : undefined
                      }
                      className="mt-3 w-full py-2 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white disabled:opacity-50 text-xs font-semibold text-slate-800 transition-all flex items-center justify-center gap-1.5"
                    >
                      <span>
                        {openingMatchId === match.product_id
                          ? t("tryon.loading_product")
                          : t(
                              tryOnKind === "render"
                                ? "tryon.cta_try_on"
                                : "tryon.cta_fit_check",
                            )}
                      </span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
    </>
  );
};
