import React, { useEffect } from "react";
import { useModalFocus } from "../../hooks/useModalFocus";
import { useTranslation } from "react-i18next";
import { resolveMessage } from "../../i18n/messages";
import { STYLIST_PROMPT_MAX_CHARS } from "../../i18n/promptBounds";
import { formatMoney, formatNumber } from '../../i18n/format';
import { useUIStore } from "../../stores/uiStore";
import { useStylistViewModel } from "../../viewmodels/useStylistViewModel";
import {
  StylistIcon,
  SparkleIcon,
  BagIcon,
  TryOnIcon,
} from "../icons/ConfitIcons";
import { FitScoreBadge } from "../common/CommonComponents";

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

export const VirtualStylistDrawer: React.FC = () => {
  const { t, i18n } = useTranslation();
  // Active UI language drives number/currency rendering.
  const lang = i18n.resolvedLanguage ?? 'en';
  const {
    isStylistDrawerOpen,
    closeStylist,
    stylistPrefillOccasion,
    openTryOn,
  } = useUIStore();
  const panelRef = useModalFocus<HTMLDivElement>(
    closeStylist,
    isStylistDrawerOpen,
  );
  const {
    messages,
    inputPrompt,
    setInputPrompt,
    isTyping,
    isRecording,
    error,
    errorRetryable,
    sendPrompt,
    startVoiceInput,
    addCompleteLookToCart,
  } = useStylistViewModel();

  // Prefill occasion or guided-first-look intent if opened with a shortcut.
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

  const getPositionBadge = (pos: string) => {
    switch (pos?.toLowerCase()) {
      case "outerwear":
        return {
          label: "Outerwear",
          bg: "bg-[#1B1F3B] text-[#E2BF70] border border-[#C5A059]/40",
        };
      case "top":
        return {
          label: t("stylist.position_top"),
          bg: "bg-indigo-950 text-indigo-200 border border-indigo-700/40",
        };
      case "bottom":
        return {
          label: "Trousers",
          bg: "bg-slate-900 text-slate-200 border border-slate-700/40",
        };
      case "footwear":
        return {
          label: "Footwear",
          bg: "bg-amber-950 text-amber-200 border border-amber-700/40",
        };
      case "accessory":
        return {
          label: "Accessory",
          bg: "bg-emerald-950 text-emerald-200 border border-emerald-700/40",
        };
      case "dress":
        return {
          label: t("stylist.position_gown"),
          bg: "bg-[#C5A059] text-slate-950 font-bold border border-[#C5A059]",
        };
      default:
        return { label: pos || t("stylist.position_garment"), bg: "bg-black/70 text-white" };
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-6 sm:pl-10">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label={t("stylist.dialog_label")}
          tabIndex={-1}
          className="w-screen max-w-2xl bg-white shadow-2xl flex flex-col border-l border-slate-200"
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
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-[#C5A059]/20 text-[#E2BF70] font-sans font-semibold">
                    {t("stylist.engine_badge")}
                  </span>
                </h2>
                <p className="text-xs text-slate-400 font-light">
                  {t("stylist.subtitle")}
                </p>
              </div>
            </div>
            <button
              onClick={closeStylist}
              className="w-8 h-8 rounded-full bg-slate-800 text-slate-300 hover:text-white flex items-center justify-center transition-colors"
            >
              ✕
            </button>
          </div>

          {/* Occasion Quick Chips */}
          <div className="px-4 py-2.5 bg-[#FAF9F6] border-b border-slate-200/80 flex items-center gap-2 overflow-x-auto">
            <span className="text-[10px] font-bold text-[#A37E44] uppercase tracking-wider shrink-0">
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
                className="px-3 py-1 rounded-full bg-white border border-slate-200 text-[11px] font-medium text-slate-700 hover:border-[#C5A059] hover:bg-[#FDF8EE] transition-all shrink-0 shadow-2xs"
              >
                {t(occ.labelKey)}
              </button>
            ))}
          </div>

          {/* Messages & Recommendations Feed */}
          <div data-conversation
               className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 bg-[#FAF9F6]">
            {messages.length === 0 && (
              <div className="text-center py-12 px-4 bg-white rounded-3xl border border-slate-200/80 shadow-2xs">
                <div className="w-14 h-14 rounded-2xl bg-[#FDF8EE] text-[#C5A059] mx-auto flex items-center justify-center mb-3 shadow-xs">
                  <SparkleIcon size={28} color="#C5A059" />
                </div>
                <h4 className="font-serif text-lg font-bold text-[#1B1F3B] mb-1">
                  {t("stylist.empty_title")}
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mb-5 font-light leading-relaxed">
                  {t("stylist.empty_body")}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
                  <button
                    onClick={() =>
                      sendPrompt(
                        // The PROMPT stays English on purpose: the backend parses
                        // English occasion/material keywords, so sending Arabic text
                        // here would silently downgrade every Arabic request to the
                        // default occasion. The label above it is localized.
                        "I need a formal wedding outfit with navy suit and green tie under 500",
                        "Formal & Wedding",
                        500,
                        undefined,
                        t("stylist.example_formal_wedding"),
                      )
                    }
                    className="p-3.5 rounded-2xl border border-slate-200 hover:border-[#C5A059] bg-[#FAF9F6] hover:bg-[#FDF8EE] text-xs font-medium text-slate-800 transition-all"
                  >
                    {t("stylist.example_formal_wedding")}
                  </button>
                  <button
                    onClick={() =>
                      sendPrompt(
                        "Find me a champagne silk dress for an evening gala",
                        "Evening & Party",
                        600,
                        undefined,
                        t("stylist.example_evening_gala"),
                      )
                    }
                    className="p-3.5 rounded-2xl border border-slate-200 hover:border-[#C5A059] bg-[#FAF9F6] hover:bg-[#FDF8EE] text-xs font-medium text-slate-800 transition-all"
                  >
                    {t("stylist.example_evening_gala")}
                  </button>
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
                  <div className="flex items-center gap-2 mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <span>
                      {msg.sender === "user"
                        ? t("stylist.you_label")
                        : t("stylist.assistant_label")}
                    </span>
                  </div>
                  <p className="text-slate-800 font-light leading-relaxed">
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
                        : String(msg.engine).includes("Grounded Styling Engine")
                          ? t("stylist.engine_grounded")
                          : t("stylist.engine_provider", { engine: msg.engine })}
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
                              <span className="text-[10px] font-bold text-[#A37E44] uppercase tracking-wider">
                                {outfit.occasion}
                              </span>
                              <span
                                className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                                  outfit.is_complete !== false
                                    ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                                    : "bg-amber-100 text-amber-800 border border-amber-300"
                                }`}
                              >
                                {outfit.completeness_label ||
                                  (outfit.is_complete !== false
                                    ? t("stylist.complete_look")
                                    : t("stylist.core_look"))}
                              </span>
                            </div>
                            <h4 className="font-serif font-bold text-base text-[#1B1F3B]">
                              {outfit.title}
                            </h4>
                          </div>
                          <FitScoreBadge
                            score={outfit.compatibility_score}
                            label={t("stylist.match")}
                            verdict={t("stylist.color_harmony")}
                          />
                        </div>

                        {/* Garment Grid (Strict Slots) */}
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                          {getResolvedOutfitItems(outfit).map((item: any) => {
                            const badge = getPositionBadge(item.position);
                            return (
                              <div
                                key={item.id}
                                className="group relative bg-[#FAF9F6] border border-slate-200/80 rounded-2xl p-2.5 flex flex-col justify-between"
                              >
                                <div>
                                  <div className="h-32 w-full rounded-xl overflow-hidden bg-white mb-2 relative shadow-2xs">
                                    <img
                                      src={item.image_url}
                                      alt={item.product_title}
                                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                                    />
                                    <span
                                      className={`absolute top-1.5 left-1.5 px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider backdrop-blur-xs ${badge.bg}`}
                                    >
                                      {badge.label}
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
                                  <span className="text-xs font-bold text-[#1B1F3B]">
                                    ${item.price.toFixed(2)}
                                  </span>
                                  <button
                                    onClick={() =>
                                      openTryOn({
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
                                    className="px-2 py-1 rounded-lg bg-white border border-slate-200 hover:border-[#C5A059] text-[10px] font-semibold text-slate-700 flex items-center gap-1 shadow-2xs"
                                    title={t("stylist.try_item")}
                                  >
                                    <TryOnIcon size={11} color="#C5A059" />
                                    <span>{t("stylist.try")}</span>
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        {getResolvedOutfitItems(outfit).length === 0 && (
                          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                            This stylist response did not include verified
                            catalog items, so CONFIT is not showing placeholder
                            products or enabling bag actions for this look.
                          </div>
                        )}

                        {/* C15 FIX: Budget honesty - show within/over budget and note */}
                        {outfit.budget_limit != null && (
                          <div
                            className={`p-2.5 rounded-xl border text-[11px] ${outfit.within_budget ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-amber-50 border-amber-300 text-amber-800"}`}
                          >
                            <div className="flex items-center gap-1.5 font-bold">
                              <span>
                                {outfit.within_budget
                                  ? t("stylist.within_budget")
                                  : t("stylist.budget_exceeded")}
                              </span>
                              <span className="font-normal">
                                — {t("stylist.budget_target")}
                                {outfit.budget_limit != null
                                  ? formatMoney(Math.round(outfit.budget_limit * 100), "USD", lang)
                                  : ""}
                                , {t("stylist.budget_total")}
                                {formatMoney(Math.round(outfit.total_price * 100), "USD", lang)}
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
                            <div className="text-base font-serif font-black text-[#1B1F3B]" dir="ltr">
                              {formatMoney(Math.round(outfit.total_price * 100), "USD", lang)}
                            </div>
                          </div>
                          <button
                            onClick={() => addCompleteLookToCart(outfit)}
                            disabled={
                              getResolvedOutfitItems(outfit).length === 0
                            }
                            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-bold shadow-md transition-all disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <BagIcon size={14} color="#FFFFFF" />
                            <span>
                              {outfit.is_complete !== false
                                ? t("stylist.add_complete_to_bag")
                                : t("stylist.add_core_to_bag")}
                            </span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {isTyping && (
              <div className="flex items-center gap-2 p-3.5 bg-white border border-slate-200 rounded-2xl w-32 shadow-2xs">
                <span className="w-2 h-2 rounded-full bg-[#C5A059] animate-bounce"></span>
                <span className="w-2 h-2 rounded-full bg-[#C5A059] animate-bounce [animation-delay:0.2s]"></span>
                <span className="w-2 h-2 rounded-full bg-[#C5A059] animate-bounce [animation-delay:0.4s]"></span>
                <span className="text-[10px] font-bold text-slate-400 ml-1">
                  {t("stylist.thinking")}
                </span>
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
            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendPrompt();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={startVoiceInput}
                className={`p-3 rounded-2xl border transition-all ${
                  isRecording
                    ? "bg-rose-500 text-white border-rose-600 animate-pulse"
                    : "bg-slate-50 border-slate-200 text-slate-600 hover:text-[#C5A059] hover:bg-[#FDF8EE]"
                }`}
                title={t("stylist.hold_voice")}
              >
                🎙️
              </button>

              <input
                type="text"
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                maxLength={STYLIST_PROMPT_MAX_CHARS}
                aria-describedby={inputPrompt.length > STYLIST_PROMPT_MAX_CHARS * 0.9 ? "stylist-prompt-limit" : undefined}
                placeholder={t("stylist.input_placeholder")}
                className="flex-1 px-4 py-3 rounded-2xl border border-slate-200 focus:outline-none focus:border-[#C5A059] text-xs sm:text-sm bg-[#FAF9F6]"
              />

              <button
                type="submit"
                disabled={!inputPrompt.trim() || isTyping}
                className="px-6 py-3 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-40 text-white text-xs font-bold transition-all shadow-md flex items-center gap-1.5"
              >
                <SparkleIcon size={14} color="#C5A059" />
                <span>{t("stylist.submit")}</span>
              </button>
            </form>
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
