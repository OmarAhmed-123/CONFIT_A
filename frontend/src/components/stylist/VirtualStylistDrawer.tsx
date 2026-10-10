import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useModalFocus } from "../../hooks/useModalFocus";
import { useTranslation } from "react-i18next";
import { resolveMessage } from "../../i18n/messages";
import { STYLIST_PROMPT_MAX_CHARS } from "../../i18n/promptBounds";
import { formatMoney, formatNumber } from '../../i18n/format';
import { useUIStore } from "../../stores/uiStore";
import { useStylistViewModel } from "../../viewmodels/useStylistViewModel";
import { stylistService } from "../../services/apiServices";
import { ApiError } from "../../services/apiClient";
import {
  StylistIcon,
  SparkleIcon,
  BagIcon,
  TryOnIcon,
  MicIcon,
} from "../icons/ConfitIcons";
import { HonestProductImage } from "../common/HonestProductImage";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { StatusIcon } from '../common/InteractionPrimitives';

/** House luxury curve + unified focus ring — single source for this drawer. */
const COMPOSER_MAX_HEIGHT_PX = 160;

const LUX = "motion-safe:transition-all motion-safe:duration-300 ease-[cubic-bezier(0.25,1,0.5,1)]";
const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059] focus-visible:ring-offset-2";

const getResolvedOutfitItems = (outfit: any) => {
  if (outfit.items && outfit.items.length > 0) {
    return outfit.items;
  }

  // Evidence-first UX: do not backfill AI stylist responses with static product
  // placeholders. Empty responses should remain visibly empty so the user knows
  // the endpoint did not return verified catalog item lines.
  return [];
};


/**
 * Quick-prompt occasions.
 *
 * `value` is a CONTRACT VALUE: `sendPrompt(prompt, occ.value)` sends it to
 * `POST /api/v1/stylist/chat` as the occasion hint, and the backend matches
 * English keywords ("work", "office", "wedding", "gala"…). Translating it would
 * make every Arabic request fall back to the default occasion — silently, with
 * no error. `labelKey` is the only translatable unit here.
 *
 * Same rule as the style quiz (PROFILE_OPTIONS): value = stable token,
 * label = localized copy.
 */
const OCCASION_PROMPTS = [
  { value: "Formal & Wedding", labelKey: "stylist.occasion_formal" },
  { value: "Work & Business", labelKey: "stylist.occasion_work" },
  { value: "Evening & Party", labelKey: "stylist.occasion_evening" },
  { value: "Casual Weekend", labelKey: "stylist.occasion_casual" },
] as const;

/** Slot → i18n key. One token map, zero duplicated badge logic (DRY). */
const SLOT_LABEL_KEYS: Record<string, string> = {
  outerwear: "stylist.position_outerwear",
  top: "stylist.position_top",
  bottom: "stylist.position_bottom",
  shoes: "stylist.position_footwear",
  footwear: "stylist.position_footwear",
  accessory: "stylist.position_accessory",
  dress: "stylist.position_gown",
};

/**
 * Hairline score meter — renders ONLY when the API actually sent the metric.
 * Replaces the pass-1 badge that stamped a static "Color Harmony" verdict on
 * every look regardless of data: these are the real color_harmony_score /
 * formality_score fields the endpoint already returns.
 */
const ScoreMeter: React.FC<{
  label: string;
  value?: number | null;
  lang: string;
  testid?: string;
}> = ({ label, value, lang, testid }) => {
  if (value == null) return null;
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2" data-testid={testid}>
      <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-400 w-24 shrink-0 truncate">
        {label}
      </span>
      <div className="h-px flex-1 bg-slate-200 relative overflow-visible" aria-hidden="true">
        <div
          className="absolute inset-y-0 start-0 h-[3px] -top-[1px] rounded-full bg-[#C5A059] motion-safe:transition-[width] motion-safe:duration-700 ease-[cubic-bezier(0.25,1,0.5,1)]"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="text-[10px] font-bold text-[#1B1F3B] tabular-nums" dir="ltr">
        {formatNumber(clamped, lang)}%
      </span>
    </div>
  );
};

export const VirtualStylistDrawer: React.FC = () => {
  const { t, i18n } = useTranslation();
  // Active UI language drives number/currency rendering.
  const lang = i18n.resolvedLanguage ?? 'en';
  const {
    isStylistDrawerOpen,
    closeStylist,
    stylistPrefillOccasion,
    openTryOn,
    openRuler,
  } = useUIStore();
  const panelRef = useModalFocus<HTMLDivElement>(
    closeStylist,
    isStylistDrawerOpen,
  );
  // The stylist recommends garments, so its "try it" control is a try-on
  // entry point like any other and must obey the same availability gate.
  // Without it the drawer opened the studio unconditionally, and a shopper
  // acting on a recommendation hit a render that could not happen.
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);
  const {
    messages,
    inputPrompt,
    setInputPrompt,
    isTyping,
    isRecording,
    error,
    errorRetryable,
    isAddingLook,
    sendPrompt,
    pendingImages,
    attachError,
    addImages,
    removeImage,
    startVoiceInput,
    addCompleteLookToCart,
  } = useStylistViewModel();

  // Save-as-look state per outfit id (Mode A looks only). Terminal "saved" hides the button.
  const [saveStates, setSaveStates] = useState<Record<number, "saving" | "saved" | "signin" | "failed">>({});

  const saveLook = async (outfit: any) => {
    const productIds: number[] = Array.from(
      new Set<number>(
        getResolvedOutfitItems(outfit)
          .map((i: any) => Number(i.product_id))
          .filter((id: number) => Number.isFinite(id) && id > 0),
      ),
    );
    if (productIds.length === 0) return;
    setSaveStates((s) => ({ ...s, [outfit.id]: "saving" }));
    try {
      await stylistService.saveOutfit({
        title: outfit.title,
        occasion: outfit.occasion ?? "",
        product_ids: productIds,
      });
      setSaveStates((s) => ({ ...s, [outfit.id]: "saved" }));
    } catch (err: any) {
      const unauthenticated = err instanceof ApiError && err.status === 401;
      setSaveStates((s) => ({ ...s, [outfit.id]: unauthenticated ? "signin" : "failed" }));
    }
  };

  // Prefill occasion or guided-first-look intent if opened with a shortcut.
  // Composer: a multiline textarea. Grows with its text up to a bounded height,
  // then scrolls. Height is recalculated on every change, including the reset
  // after a send, so a long draft never leaves a stale tall box behind.
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  useLayoutEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`;
  }, [inputPrompt]);

  useEffect(() => {
    if (
      isStylistDrawerOpen &&
      stylistPrefillOccasion &&
      messages.length === 0
    ) {
      if (typeof stylistPrefillOccasion === "string") {
        sendPrompt(
          `Style a complete outfit for ${stylistPrefillOccasion}`,
          stylistPrefillOccasion,
        );
      } else {
        sendPrompt(
          stylistPrefillOccasion.prompt,
          stylistPrefillOccasion.occasion,
          stylistPrefillOccasion.budget,
          stylistPrefillOccasion.recommendation_constraints,
        );
      }
    }
  }, [
    isStylistDrawerOpen,
    stylistPrefillOccasion,
    messages.length,
    sendPrompt,
  ]);

  if (!isStylistDrawerOpen) return null;

  // Every slot label is a KEY (the old switch hard-coded English words into
  // the Arabic transcript) and every slot shares ONE token pair: the pass-1
  // six-colour badge rainbow (indigo/amber/emerald/slate…) read as a toy, not
  // a luxury house. Statement slots (dress) carry the gold accent; everything
  // else is quiet navy. Restraint IS the design system.
  const slotLabel = (pos: string): string => {
    const key = SLOT_LABEL_KEYS[pos?.toLowerCase?.() ?? ""];
    return key ? t(key) : pos || t("stylist.position_garment");
  };
  const slotTone = (pos: string) =>
    pos?.toLowerCase?.() === "dress"
      ? "bg-[#C5A059] text-slate-950 font-bold border border-[#C5A059]"
      : "bg-[#0C0E1E]/85 text-[#E2BF70] border border-[#C5A059]/30";

  // Money honesty: render ONLY the currency the server declared for this
  // item/look. No declared currency (legacy persisted messages) -> an honest
  // em-dash, never an assumed "$" — same contract as the outfit builder.
  const itemMoney = (price: number, currency?: string | null) =>
    currency ? formatMoney(Math.round(price * 100), currency, lang) : "\u2014";

  // The four quick-prompt occasions are contract values with localized
  // labels; when a recommendation's occasion matches one, show the label.
  const occasionLabel = (occ: string) => {
    const hit = OCCASION_PROMPTS.find((o) => o.value === occ);
    return hit ? t(hit.labelKey) : occ;
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/60 backdrop-blur-sm confit-fade-in">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-6 sm:pl-10">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label={t("stylist.dialog_label")}
          tabIndex={-1}
          className="w-screen max-w-2xl bg-white shadow-2xl flex flex-col border-l border-slate-200 confit-drawer-in"
        >
          {/* Drawer Header */}
          <div className="p-4 sm:p-6 border-b border-slate-800 bg-[#0C0E1E] text-white flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#C5A059] flex items-center justify-center text-slate-950 shadow-xs">
                <StylistIcon size={22} color="#0C0E1E" />
              </div>
              <div>
                <h2 className="font-serif text-lg font-bold text-white flex items-center gap-2">
                  <span>{t("stylist.title")}</span>
                  {/* The old static badge claimed "Rules-Grounded Engine" on
                      every reply — false whenever a live provider answered
                      (per-message attribution is the engine truth). The one
                      claim true in BOTH paths: verified catalogue pieces. */}
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#C5A059]/20 text-[#E2BF70] font-sans font-semibold">
                    {t("stylist.catalogue_badge")}
                  </span>
                </h2>
                <p className="text-xs text-slate-400 font-light">
                  {t("stylist.subtitle")}
                </p>
              </div>
            </div>
            <button
              onClick={closeStylist}
              aria-label={t("common.close")}
              className={`w-11 h-11 rounded-full bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 flex items-center justify-center ${LUX} ${RING}`}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {/* Occasion Quick Chips */}
          <div className="px-4 py-2.5 bg-[#FAF9F6] border-b border-slate-200/80 flex items-center gap-2 overflow-x-auto">
            <span className="text-[10px] font-bold text-[#8A6A34] uppercase tracking-wider shrink-0">
              {t("stylist.style_prompts")}
            </span>
            {/* CONTRACT VALUES: `value` is sent to the API as the occasion hint and
                the backend matches ENGLISH keywords, so it is never translated.
                Only the label is localized (see the module docstring). */}
            {OCCASION_PROMPTS.map((occ) => (
              <button
                key={occ.value}
                onClick={() =>
                  sendPrompt(`Style an outfit for ${occ.value}`, occ.value, undefined,
                             undefined, t(occ.labelKey))
                }
                className={`px-3 py-2.5 min-h-[44px] rounded-full bg-white border border-slate-200 text-[11px] font-medium text-slate-700 hover:border-[#C5A059] hover:bg-[#FDF8EE] shrink-0 shadow-2xs ${LUX} ${RING}`}
              >
                {t(occ.labelKey)}
              </button>
            ))}
          </div>

          {/* Messages & Recommendations Feed */}
          <div data-conversation
               className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 bg-[#FAF9F6]">
            {messages.length === 0 && (
              <div className="confit-fade-in">
                {/* Editorial intro — start-aligned, not a centered widget. */}
                <div className="pt-6 pb-5">
                  <div className="w-10 h-px bg-[#C5A059] mb-4" aria-hidden="true" />
                  <h4 className="font-serif text-2xl font-bold text-[#1B1F3B] leading-snug max-w-xs">
                    {t("stylist.empty_title")}
                  </h4>
                  <p className="text-xs text-slate-600 max-w-sm mt-2 font-light leading-relaxed">
                    {t("stylist.empty_body")}
                  </p>
                </div>
                {/* Numbered suggestion rows — index numerals as the only
                    ornament; the whole row is one 48px+ touch target. */}
                <div className="divide-y divide-slate-200/80 border-y border-slate-200/80">
                  {[
                    {
                      prompt:
                        // The PROMPT stays English on purpose: the backend
                        // parses English occasion/material keywords, so Arabic
                        // text here would silently downgrade every Arabic
                        // request to the default occasion. Labels localize.
                        "I need a formal wedding outfit with navy suit and green tie under 500",
                      occasion: "Formal & Wedding",
                      budget: 500,
                      labelKey: "stylist.example_formal_wedding",
                    },
                    {
                      prompt: "Find me a champagne silk dress for an evening gala",
                      occasion: "Evening & Party",
                      budget: 600,
                      labelKey: "stylist.example_evening_gala",
                    },
                  ].map((ex, i) => (
                    <button
                      key={ex.labelKey}
                      onClick={() =>
                        sendPrompt(ex.prompt, ex.occasion, ex.budget, undefined, t(ex.labelKey))
                      }
                      className={`group w-full min-h-[56px] py-4 flex items-center gap-4 text-start hover:bg-white ${LUX} ${RING}`}
                    >
                      <span
                        className="font-serif text-lg font-black text-[#8A6A34] group-hover:text-[#1B1F3B] tabular-nums shrink-0 w-8"
                        aria-hidden="true"
                        dir="ltr"
                      >
                        0{i + 1}
                      </span>
                      <span className="text-xs font-medium text-slate-800 flex-1">
                        {t(ex.labelKey)}
                      </span>
                      <span
                        className={`text-[#C5A059] opacity-0 group-hover:opacity-100 motion-safe:group-hover:translate-x-0 motion-safe:-translate-x-1 rtl:rotate-180 ${LUX}`}
                        aria-hidden="true"
                      >
                        →
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
              >
                <div
                  className={`max-w-[92%] rounded-2xl p-4 text-xs sm:text-sm shadow-2xs leading-relaxed ${
                    msg.sender === "user"
                      ? "bg-[#1B1F3B] text-white rounded-br-none"
                      : "bg-white border border-slate-200/80 text-slate-800 rounded-bl-none shadow-sm"
                  }`}
                >
                  <div
                    className={`flex items-center gap-2 mb-1 text-[10px] font-bold uppercase tracking-wider ${
                      msg.sender === "user" ? "text-[#E2BF70]/80" : "text-slate-400"
                    }`}
                  >
                    <span>
                      {msg.sender === "user"
                        ? t("stylist.you_label")
                        : t("stylist.assistant_label")}
                    </span>
                  </div>
                  {/* WCAG fix: this paragraph used to force text-slate-800
                      inside the navy user bubble — the shopper's own words
                      were near-invisible dark-on-dark. */}
                  <p
                    className={`font-light leading-relaxed ${
                      msg.sender === "user" ? "text-white" : "text-slate-800"
                    }`}
                  >
                    {msg.content}
                  </p>
                  {/* Which engine answered, stated in the message itself. The
                      bubble used to claim "AI Stylist" unconditionally, so a
                      deterministic fallback answer (every provider down) was
                      presented as a live model reply. The API now reports the
                      engine; this renders it. */}
                  {msg.sender === "assistant" && msg.engine && (
                    <p
                      className="mt-2 pt-2 border-t border-slate-100 text-[10px] text-slate-500"
                      data-engine={msg.engine}
                    >
                      {msg.engine === "none"
                        ? t("stylist.engine_none")
                        : msg.answer_source === "grounding_rejected"
                          ? t("stylist.engine_rejected")
                          : String(msg.engine).includes("Grounded Styling Engine")
                            ? t("stylist.engine_grounded")
                            : t("stylist.engine_provider", { engine: msg.engine })}
                    </p>
                  )}
                  {/* Photos were attached but this reply could not use them. The
                      reason is stated in the shopper's language, not the API's English. */}
                  {msg.sender === "assistant" && msg.fallback_reason && (
                    <p
                      role="status"
                      data-testid="stylist-mode-note"
                      className="mt-2 text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
                    >
                      {t("stylist.mode_fallback_note")}
                    </p>
                  )}
                </div>

                {/* Render Recommended Outfits */}
                {msg.recommendations && msg.recommendations.length > 0 && (
                  <div className="w-full mt-3 space-y-4">
                    {msg.recommendations.map((outfit) => (
                      <div
                        key={outfit.id}
                        className="bg-white border border-slate-200 rounded-3xl p-5 shadow-md overflow-hidden space-y-4"
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-[10px] font-bold text-[#8A6A34] uppercase tracking-wider">
                                {occasionLabel(outfit.occasion)}
                              </span>
                              <span
                                className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                                  outfit.is_complete !== false
                                    ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                                    : "bg-amber-100 text-amber-800 border border-amber-300"
                                }`}
                              >
                                {/* Translate from the STABLE status token.
                                    The free-text completeness_label is
                                    English prose from the engine and used to
                                    override the Arabic bundle ("COMPLETE
                                    ENSEMBLE" leaked into the RTL drawer —
                                    caught in the pass-1 visual review). */}
                                {outfit.is_complete !== false ||
                                outfit.completeness_status === "complete_look"
                                  ? t("stylist.complete_look")
                                  : t("stylist.core_look")}
                              </span>
                            </div>
                            <h4 className="font-serif font-bold text-base text-[#1B1F3B]">
                              {outfit.title}
                            </h4>
                            {/* Real palette from the API — colour dots, zero
                                words. aria-label carries the count for SRs. */}
                            {outfit.color_palette && outfit.color_palette.length > 0 && (
                              <div
                                className="flex items-center gap-1 mt-1.5"
                                data-testid="stylist-palette"
                                role="img"
                                aria-label={t("stylist.palette_label", {
                                  count: outfit.color_palette.length,
                                })}
                              >
                                {outfit.color_palette.slice(0, 6).map((hex: string, i: number) => (
                                  <span
                                    key={`${hex}-${i}`}
                                    className="w-3 h-3 rounded-full border border-slate-200 shadow-2xs"
                                    style={{ backgroundColor: hex }}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                          {/* Hero numeral replaces the pass-1 badge that
                              stamped a static "Color Harmony" verdict on every
                              look. The meters below it are the REAL
                              color_harmony_score / formality_score fields. */}
                          <div className="text-end shrink-0 ps-3">
                            <div className="font-serif font-black text-3xl leading-none text-[#1B1F3B]" dir="ltr">
                              {formatNumber(outfit.compatibility_score, lang)}
                              <span className="text-sm text-[#C5A059] align-super">%</span>
                            </div>
                            <div className="text-[9px] font-bold uppercase tracking-widest text-[#8A6A34] mt-0.5">
                              {t("stylist.match")}
                            </div>
                          </div>
                        </div>
                        <div className="space-y-1.5 pt-1" data-testid="stylist-harmony-meters">
                          <ScoreMeter
                            label={t("stylist.color_harmony")}
                            value={outfit.color_harmony_score}
                            lang={lang}
                            testid="stylist-meter-color"
                          />
                          <ScoreMeter
                            label={t("stylist.formality")}
                            value={outfit.formality_score}
                            lang={lang}
                            testid="stylist-meter-formality"
                          />
                        </div>

                        {/* Garment tier — editorial asymmetry: the anchor
                            garment (first slot) carries a 4:5 fashion
                            portrait spanning two rows; supporting pieces sit
                            in the standard grid. One look reads as a curated
                            composition, not a uniform thumbnail strip. */}
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 sm:[grid-auto-rows:minmax(0,auto)]">
                          {getResolvedOutfitItems(outfit).map((item: any, itemIdx: number) => {
                            const isAnchor = itemIdx === 0 && getResolvedOutfitItems(outfit).length > 2;
                            return (
                              <div
                                key={item.id}
                                className={`group relative bg-[#FAF9F6] border border-slate-200/80 rounded-2xl p-2.5 flex flex-col justify-between confit-fade-in ${isAnchor ? "sm:row-span-2" : ""}`}
                                style={{ animationDelay: `${Math.min(itemIdx, 5) * 70}ms` }}
                              >
                                <div>
                                  <div className={`${isAnchor ? "sm:aspect-[4/5] sm:h-auto h-32" : "h-32"} w-full rounded-xl overflow-hidden bg-white mb-2 relative shadow-2xs`}>
                                    <HonestProductImage
                                      src={item.image_url}
                                      alt={item.product_title}
                                      unavailableLabel={t("common.image_unavailable")}
                                      className={`w-full h-full object-cover motion-safe:group-hover:scale-105 ${LUX}`}
                                    />
                                    <span
                                      className={`absolute top-1.5 start-1.5 px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider backdrop-blur-xs ${slotTone(item.position)}`}
                                    >
                                      {slotLabel(item.position)}
                                    </span>
                                  </div>
                                  <div className="flex items-center justify-between gap-1">
                                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block truncate">
                                      {item.brand_name}
                                    </span>
                                    {item.color_family && (
                                      <span className="text-[9px] text-slate-500 font-light truncate">
                                        {item.color_family}
                                      </span>
                                    )}
                                  </div>
                                  <span className="text-xs font-bold text-[#1B1F3B] line-clamp-1 block mt-0.5">
                                    {item.product_title}
                                  </span>
                                  {item.role_in_outfit && (
                                    <span className="text-[9px] text-slate-400 block font-light line-clamp-1 mt-0.5">
                                      {item.role_in_outfit}
                                    </span>
                                  )}
                                </div>

                                <div className="flex items-center justify-between pt-2 border-t border-slate-100 mt-2">
                                  <span className="text-xs font-bold text-[#1B1F3B]" dir="ltr">
                                    {itemMoney(item.price, item.currency)}
                                  </span>
                                  <button
                                    disabled={tryOnKind === "blocked"}
                                    onClick={() =>
                                      (tryOnKind === "fit_check"
                                        ? openRuler
                                        : openTryOn)({
                                        id: item.product_id,
                                        title: item.product_title,
                                        brand_name: item.brand_name,
                                        thumbnail_url: item.image_url,
                                        base_price: item.price,
                                        category_name: item.category_name,
                                        color_family:
                                          item.color_family || "Coordinated",
                                        style_compatibility_score:
                                          outfit.compatibility_score,
                                      } as any)
                                    }
                                    className={`px-2 py-2 min-h-[36px] rounded-lg bg-white border border-slate-200 hover:border-[#C5A059] disabled:opacity-50 disabled:cursor-not-allowed text-[10px] font-semibold text-slate-700 flex items-center gap-1 shadow-2xs ${LUX} ${RING}`}
                                    title={
                                      tryOnKind === "blocked" && tryOn.userMessage
                                        ? resolveMessage(tryOn.userMessage, t)
                                        : t("stylist.try_item")
                                    }
                                  >
                                    <TryOnIcon size={11} color="#C5A059" />
                                    <span>{t("stylist.try")}</span>
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        {outfit.is_complete === false &&
                          outfit.missing_slots &&
                          outfit.missing_slots.length > 0 && (
                            <div
                              className="flex items-center gap-1.5 flex-wrap text-[10px] text-slate-500"
                              data-testid="stylist-missing-slots"
                            >
                              <span className="font-semibold uppercase tracking-wider text-amber-700">
                                {t("stylist.missing_slots_label")}
                              </span>
                              {outfit.missing_slots.map((slot: string) => (
                                <span
                                  key={slot}
                                  className="px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-800 font-medium"
                                >
                                  {slotLabel(slot)}
                                </span>
                              ))}
                            </div>
                          )}
                        {getResolvedOutfitItems(outfit).length === 0 && (
                          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                            {t("stylist.no_verified_items")}
                          </div>
                        )}

                        {/* C15 FIX: Budget honesty - show within/over budget and note */}
                        {outfit.budget_limit != null && (
                          <div
                            className={`p-2.5 rounded-xl border text-[11px] ${outfit.within_budget ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-amber-50 border-amber-300 text-amber-800"}`}
                          >
                            <div className="flex items-center gap-1.5 font-bold">
                              {/* Spec 14: semantic shape instead of the old
                                  check/warn unicode glyphs that lived in the
                                  locale strings — words + shape, colour third. */}
                              <StatusIcon
                                status={outfit.within_budget ? "success" : "warning"}
                                size={12}
                                className="text-current"
                              />
                              <span>
                                {outfit.within_budget
                                  ? t("stylist.within_budget")
                                  : t("stylist.budget_exceeded")}
                              </span>
                              <span className="font-normal">
                                — {t("stylist.budget_target")}
                                {outfit.budget_limit != null
                                  ? itemMoney(outfit.budget_limit, outfit.currency)
                                  : ""}
                                , {t("stylist.budget_total")}
                                {itemMoney(outfit.total_price, outfit.currency)}
                              </span>
                            </div>
                            {outfit.budget_note && (
                              <p className="mt-1 font-light leading-relaxed">
                                {outfit.budget_note}
                              </p>
                            )}
                          </div>
                        )}
                        {/* Total and Action Buttons */}
                        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                          <div>
                            <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">
                              {t("stylist.ensemble_total")} (
                              {formatNumber(getResolvedOutfitItems(outfit).length, lang)}{" "}
                              {t("stylist.items_count")}):
                            </span>
                            <div className="text-base font-serif font-black text-[#1B1F3B]" dir="ltr" data-testid="stylist-ensemble-total">
                              {itemMoney(outfit.total_price, outfit.currency)}
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                          {msg.mode === "A" && saveStates[outfit.id] !== "saved" && (
                            <button
                              type="button"
                              onClick={() => saveLook(outfit)}
                              aria-busy={saveStates[outfit.id] === "saving"}
                              disabled={saveStates[outfit.id] === "saving" || getResolvedOutfitItems(outfit).length === 0}
                              className={`inline-flex items-center gap-2 px-4 py-2.5 min-h-[44px] rounded-xl border border-[#C5A059] text-[#1B1F3B] bg-white hover:bg-[#FDF8EE] text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50 ${LUX} ${RING}`}
                            >
                              <span>
                                {saveStates[outfit.id] === "saving" ? t("stylist.saving_look") : t("stylist.save_look")}
                              </span>
                            </button>
                          )}
                          {msg.mode === "A" && saveStates[outfit.id] === "saved" && (
                            <span role="status" aria-label={t("stylist.look_saved")} className="text-[11px] font-bold text-emerald-700">
                              {t("stylist.look_saved")}
                            </span>
                          )}
                          {msg.mode === "A" && saveStates[outfit.id] === "signin" && (
                            <span role="alert" className="text-[11px] text-rose-700">{t("stylist.save_look_signin")}</span>
                          )}
                          {msg.mode === "A" && saveStates[outfit.id] === "failed" && (
                            <span role="alert" className="text-[11px] text-rose-700">{t("stylist.save_look_failed")}</span>
                          )}
                          <button
                            onClick={() => addCompleteLookToCart(outfit)}
                            aria-busy={isAddingLook}
                            disabled={
                              getResolvedOutfitItems(outfit).length === 0
                            }
                            className={`inline-flex items-center gap-2 px-5 py-3 min-h-[48px] rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-bold shadow-md disabled:cursor-not-allowed disabled:opacity-50 ${LUX} ${RING}`}
                          >
                            <BagIcon size={14} color="#FFFFFF" />
                            <span>
                              {isAddingLook
                                ? t("stylist.adding_to_bag")
                                : outfit.is_complete !== false
                                  ? t("stylist.add_complete_to_bag")
                                  : t("stylist.add_core_to_bag")}
                            </span>
                          </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {isTyping && (
              <div role="status" aria-label={t("stylist.thinking")} className="space-y-3 confit-fade-in" data-testid="stylist-thinking">
                <div className="flex items-center gap-2 p-3.5 bg-white border border-slate-200 rounded-2xl w-32 shadow-2xs">
                  <span className="w-2 h-2 rounded-full bg-[#C5A059] motion-safe:animate-bounce"></span>
                  <span className="w-2 h-2 rounded-full bg-[#C5A059] motion-safe:animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-2 h-2 rounded-full bg-[#C5A059] motion-safe:animate-bounce [animation-delay:0.4s]"></span>
                  <span className="text-[10px] font-bold text-slate-400 ms-1">
                    {t("stylist.thinking")}
                  </span>
                </div>
                {/* Skeleton matched to the recommendation card's real
                    geometry (header row, asymmetric garment tier, total
                    row) — the answer arrives into the silhouette it will
                    occupy, not after a generic spinner. */}
                <div className="bg-white border border-slate-200 rounded-3xl p-5 space-y-4" aria-hidden="true">
                  <div className="flex justify-between items-start">
                    <div className="space-y-2">
                      <div className="h-3 w-24 rounded bg-slate-100 skeleton-shimmer" />
                      <div className="h-4 w-44 rounded bg-slate-100 skeleton-shimmer" />
                    </div>
                    <div className="h-10 w-16 rounded-xl bg-slate-100 skeleton-shimmer" />
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    <div className="sm:row-span-2 sm:aspect-[4/5] h-32 sm:h-auto rounded-2xl bg-slate-100 skeleton-shimmer" />
                    <div className="h-32 rounded-2xl bg-slate-100 skeleton-shimmer" />
                    <div className="h-32 rounded-2xl bg-slate-100 skeleton-shimmer" />
                  </div>
                  <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                    <div className="h-5 w-28 rounded bg-slate-100 skeleton-shimmer" />
                    <div className="h-11 w-40 rounded-xl bg-slate-100 skeleton-shimmer" />
                  </div>
                </div>
              </div>
            )}

          </div>

          {/* The failure banner sits OUTSIDE the transcript scroll area, directly
              above the input: inside it, the very message telling the shopper the
              request failed could be scrolled out of view while they stare at an
              unchanged conversation. It is interface furniture, not a message. */}
          {error && (
            <div className="px-4 pt-3">
              <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-700 flex justify-between items-center">
                <span>{resolveMessage(error, t)}</span>
                {/* Retry only where retrying can change the outcome: a validation
                    rejection cannot be fixed by pressing the same button again. */}
                {errorRetryable && (
                  <button
                    onClick={() => sendPrompt()}
                    className="text-xs font-bold underline ml-2"
                  >
                    {t("stylist.retry")}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Drawer Footer Input */}
          <div className="p-4 border-t border-slate-200 bg-white">
            {(pendingImages.length > 0 || attachError) && (
              <div className="mb-2 flex flex-wrap items-center gap-2" aria-live="polite">
                {pendingImages.map((src, index) => (
                  <div key={index} className="relative">
                    <img
                      src={src}
                      alt={t("stylist.photos_attached", { count: pendingImages.length })}
                      className="h-14 w-14 rounded-xl object-cover border border-slate-200"
                    />
                    <button
                      type="button"
                      onClick={() => removeImage(index)}
                      aria-label={t("stylist.remove_photo", { n: index + 1 })}
                      className={`absolute -top-1.5 -right-1.5 h-6 w-6 min-h-[24px] min-w-[24px] rounded-full bg-slate-900 text-white text-xs ${RING}`}
                    >
                      ×
                    </button>
                  </div>
                ))}
                {attachError && (
                  <p role="alert" className="text-[11px] text-rose-700">
                    {t(`stylist.attach_error_${attachError}`)}
                  </p>
                )}
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendPrompt();
              }}
              className="flex items-center gap-2"
            >
              <label
                title={t("stylist.attach_photo_hint")}
                className={`p-3 min-h-[48px] min-w-[48px] flex items-center justify-center rounded-2xl border cursor-pointer focus-within:ring-2 focus-within:ring-[#C5A059]/40 bg-slate-50 border-slate-200 text-slate-600 hover:text-[#C5A059] hover:bg-[#FDF8EE] focus-within:ring-2 focus-within:ring-[#C5A059]/40 ${LUX}`}
              >
                <span className="sr-only">{t("stylist.attach_photo")}</span>
                <span aria-hidden="true" className="text-lg leading-none">＋</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  className="sr-only"
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    e.target.value = "";
                    if (files.length) void addImages(files);
                  }}
                />
              </label>

              <button
                type="button"
                onClick={startVoiceInput}
                aria-label={isRecording ? t("stylist.voice_stop") : t("stylist.hold_voice")}
                aria-pressed={isRecording}
                className={`p-3 min-h-[48px] min-w-[48px] flex items-center justify-center rounded-2xl border ${LUX} ${RING} ${
                  isRecording
                    ? "bg-rose-500 text-white border-rose-600 motion-safe:animate-pulse"
                    : "bg-slate-50 border-slate-200 text-slate-600 hover:text-[#C5A059] hover:bg-[#FDF8EE]"
                }`}
                title={t("stylist.hold_voice")}
              >
                <MicIcon size={18} color="currentColor" />
              </button>

              <textarea
                ref={composerRef}
                rows={1}
                dir="auto"
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                onKeyDown={(e) => {
                  // Enter inserts a line (multi-paragraph requests). Ctrl+Enter, or
                  // Cmd+Enter on Mac, sends. IME composition is never interrupted.
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (inputPrompt.trim() && !isTyping) sendPrompt();
                  }
                }}
                maxLength={STYLIST_PROMPT_MAX_CHARS}
                aria-describedby={[
                  "stylist-composer-hint",
                  inputPrompt.length > STYLIST_PROMPT_MAX_CHARS * 0.9 ? "stylist-prompt-limit" : null,
                ].filter(Boolean).join(" ")}
                aria-label={t("stylist.input_label")}
                placeholder={t("stylist.input_placeholder")}
                className={`flex-1 resize-none overflow-y-auto whitespace-pre-wrap break-words px-4 py-3 min-h-[48px] rounded-2xl border border-slate-200 focus:outline-none focus:border-[#C5A059] focus-visible:ring-2 focus-visible:ring-[#C5A059]/40 text-xs sm:text-sm leading-relaxed bg-[#FAF9F6] ${LUX}`}
              />

              <button
                type="submit"
                disabled={!inputPrompt.trim() || isTyping}
                aria-busy={isTyping}
                className={`px-6 py-3 min-h-[48px] rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold shadow-md flex items-center gap-1.5 ${LUX} ${RING}`}
              >
                <SparkleIcon size={14} color="#C5A059" />
                <span>{isTyping ? t("stylist.sending") : t("stylist.submit")}</span>
              </button>
            </form>
            <p id="stylist-composer-hint" className="mt-1.5 text-[10px] text-slate-500 text-center">
              {t("stylist.composer_hint")}
            </p>
            {inputPrompt.length > STYLIST_PROMPT_MAX_CHARS * 0.9 && (
              <p id="stylist-prompt-limit"
                 className="mt-1.5 text-[10px] text-slate-500 text-center"
                 role="status">
                {t("stylist.prompt_limit_hint", {
                  remaining: STYLIST_PROMPT_MAX_CHARS - inputPrompt.length,
                })}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
