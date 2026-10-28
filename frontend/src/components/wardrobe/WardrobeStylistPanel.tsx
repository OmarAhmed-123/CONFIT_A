import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  wardrobeService,
  toSaveWardrobeOutfitRequest,
  type OutfitRecommendation,
  type OutfitRecommendationRequest,
  type StylistSeason,
  type StylistTimeOfDay,
} from "../../services/apiServices";
import { ApiError } from "../../services/apiClient";
import { HonestProductImage } from "../../components/common/HonestProductImage";
import { SparkleIcon } from "../../components/icons/ConfitIcons";

/**
 * IBM Granite stylist workspace (wardrobe → outfit).
 *
 * One component owns the whole journey the IBM tutorial describes: pick the
 * occasion / time of day / season / location (+ optional preferences), ask
 * for ONE outfit built from the user's analysed pieces, review the chosen
 * photographs with a reason per garment, then refine or ask for another.
 *
 * Honesty contract (FR-18): the result header always states whether a
 * language model produced the selection (`ai_generated`) or the rule-based
 * fallback did, and names the model id. The panel never shows "AI" copy for
 * a fallback result.
 */

const OCCASIONS = [
  "Casual",
  "Smart Casual",
  "Work & Business",
  "Business Formal",
  "Formal",
  "Cocktail",
  "Evening",
  "Active",
] as const;
const TIMES: StylistTimeOfDay[] = ["morning", "afternoon", "evening", "night"];
const SEASONS: StylistSeason[] = ["spring", "summer", "autumn", "winter"];

type Phase = "idle" | "loading" | "success" | "error";
type SavePhase = "idle" | "saving" | "saved" | "error";

interface Props {
  isAuthenticated: boolean;
  /** Number of READY items the closet query knows about (for the empty state). */
  readyItemCount: number;
  onOpenUpload: () => void;
  onSignIn: () => void;
  /** Called after a look was really persisted (201) so parents can refresh. */
  onSaved?: (savedId: number) => void;
}

/**
 * The API appends "No <category> in your wardrobe to complete this look." to
 * `limitations` for API-only clients. The panel renders the same fact as a
 * localized callout from `missing_categories`, so the English sentence is
 * filtered here to avoid saying it twice (observed live 2026-10-26).
 */
const isServerMissingCategoryNote = (note: string): boolean =>
  /^No .+ in your wardrobe to complete this look\.$/i.test(note.trim());

export const WardrobeStylistPanel: React.FC<Props> = ({
  isAuthenticated,
  readyItemCount,
  onOpenUpload,
  onSignIn,
  onSaved,
}) => {
  const { t, i18n } = useTranslation();
  const uid = useId();
  const queryClient = useQueryClient();

  const [occasion, setOccasion] = useState<string>("Smart Casual");
  const [timeOfDay, setTimeOfDay] = useState<StylistTimeOfDay | "">("");
  const [season, setSeason] = useState<StylistSeason | "">("");
  const [location, setLocation] = useState("");
  const [styleText, setStyleText] = useState("");
  const [colorText, setColorText] = useState("");
  const [excludedColorText, setExcludedColorText] = useState("");
  const [comfort, setComfort] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [excludedIds, setExcludedIds] = useState<number[]>([]);

  const [phase, setPhase] = useState<Phase>("idle");
  const [savePhase, setSavePhase] = useState<SavePhase>("idle");
  const [savedId, setSavedId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [result, setResult] = useState<OutfitRecommendation | null>(null);
  const [error, setError] = useState<{ message: string; code?: string; retryable: boolean } | null>(null);

  const statusQuery = useQuery({
    queryKey: ["wardrobe", "stylist-status"],
    queryFn: () => wardrobeService.getStylistStatus(),
    enabled: isAuthenticated,
    staleTime: 60_000,
  });
  const status = statusQuery.data;

  const splitList = (text: string) =>
    text
      .split(/[,\n،]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 8);

  const buildPayload = useCallback(
    (previous?: OutfitRecommendation | null): OutfitRecommendationRequest => ({
      occasion,
      time_of_day: timeOfDay || undefined,
      season: season || undefined,
      location: location.trim() || undefined,
      style_preferences: splitList(styleText),
      color_preferences: splitList(colorText),
      excluded_colors: splitList(excludedColorText),
      comfort_needs: comfort.trim() || undefined,
      exclusions: exclusions.trim() || undefined,
      excluded_item_ids: excludedIds,
      previous_item_ids: previous ? previous.items.map((i) => i.wardrobe_item_id) : [],
      language: i18n.language?.startsWith("ar") ? "ar" : "en",
    }),
    [occasion, timeOfDay, season, location, styleText, colorText, excludedColorText, comfort, exclusions, excludedIds],
  );

  const run = useCallback(
    async (previous?: OutfitRecommendation | null) => {
      setPhase("loading");
      setError(null);
      try {
        const rec = await wardrobeService.recommendOutfit(buildPayload(previous));
        setResult(rec);
        setSavePhase("idle");
        setSavedId(null);
        setSaveError(null);
        setPhase("success");
      } catch (e) {
        const api = e instanceof ApiError ? e : null;
        const code = api?.code;
        let message = api?.message || t("wardrobe_stylist.error_generic");
        if (code === "FEATURE_NOT_CONFIGURED") message = t("wardrobe_stylist.error_not_configured");
        else if (code === "PROVIDER_ERROR") message = t("wardrobe_stylist.error_provider");
        else if (api?.status === 422) message = api.message;
        else if (api?.status === 429) message = t("wardrobe_stylist.error_rate_limited");
        setError({
          message,
          code,
          retryable: code === "PROVIDER_ERROR" || api?.status === 429 || !api,
        });
        setPhase("error");
      }
    },
    [buildPayload, t],
  );

  // Focus management: move focus to the result heading when a result lands
  // so screen-reader users hear it (WCAG 2.4.3 / 4.1.3).
  const resultHeadingRef = React.useRef<HTMLHeadingElement | null>(null);
  useEffect(() => {
    if (phase === "success" && resultHeadingRef.current) resultHeadingRef.current.focus();
  }, [phase, result?.outfit_id]);

  // "Save this look": only report success once the server answered 201 with
  // an id. Rejected references (binned/foreign ids) are surfaced, not hidden.
  const saveLook = useCallback(async () => {
    if (!result || savePhase === "saving" || savePhase === "saved") return;
    setSavePhase("saving");
    setSaveError(null);
    try {
      const saved = await wardrobeService.saveOutfit(toSaveWardrobeOutfitRequest(result));
      if (!saved || typeof saved.id !== "number") throw new ApiError(t("wardrobe_stylist.save_failed"), "SAVE_UNCONFIRMED", 0, {});
      setSavedId(saved.id);
      setSavePhase("saved");
      void queryClient.invalidateQueries({ queryKey: ["wardrobe", "saved-wardrobe-looks"] });
      onSaved?.(saved.id);
    } catch (e) {
      const api = e instanceof ApiError ? e : null;
      setSaveError(
        api?.status === 422 && api.message
          ? api.message
          : api?.status === 429
            ? t("wardrobe_stylist.error_rate_limited")
            : t("wardrobe_stylist.save_failed"),
      );
      setSavePhase("error");
    }
  }, [result, savePhase, queryClient, onSaved, t]);

  const excludeItem = (id: number) => {
    setExcludedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
  };

  const sourceLabel = useMemo(() => {
    if (!result) return "";
    return result.ai_generated
      ? t("wardrobe_stylist.source_model", { model: result.model_id ?? "watsonx.ai" })
      : t("wardrobe_stylist.source_fallback");
  }, [result, t]);

  if (!isAuthenticated) {
    return (
      <section
        aria-labelledby={`${uid}-signin`}
        className="rounded-[32px] border border-brand-hairline bg-white p-8 text-center shadow-2xs"
      >
        <h2 id={`${uid}-signin`} className="font-serif text-2xl font-bold text-brand-charcoal">
          {t("wardrobe_stylist.signin_title")}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm font-light leading-relaxed text-brand-muted">
          {t("wardrobe_stylist.signin_body")}
        </p>
        <button data-motion="auth"
          type="button"
          onClick={onSignIn}
          className="mt-6 inline-flex min-h-11 items-center rounded-2xl bg-brand-charcoal px-5 py-2.5 text-xs font-bold text-white transition-colors hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
        >
          {t("auth.sign_in")}
        </button>
      </section>
    );
  }

  const fieldClass =
    "mt-1 block w-full min-h-11 rounded-2xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-brand-charcoal placeholder:text-slate-400 focus:border-brand-charcoal focus:outline-none focus:ring-2 focus:ring-brand-charcoal/20";
  const labelClass = "block text-[11px] font-bold uppercase tracking-widest text-brand-charcoal";

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
      {/* ── Preferences ─────────────────────────────────────────── */}
      <section
        aria-labelledby={`${uid}-prefs`}
        className="rounded-[32px] border border-brand-hairline bg-white p-6 shadow-2xs lg:sticky lg:top-24 lg:self-start"
      >
        <div className="flex items-center gap-2">
          <SparkleIcon size={18} color="#252729" />
          <h2 id={`${uid}-prefs`} className="font-serif text-xl font-bold text-brand-charcoal">
            {t("wardrobe_stylist.prefs_title")}
          </h2>
        </div>
        <p className="mt-1 text-xs font-light leading-relaxed text-brand-muted">
          {t("wardrobe_stylist.prefs_subtitle")}
        </p>

        {/* Service status — set expectations before the first call. */}
        {status && (
          <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-700" role="status">
            {status.watsonx_configured
              ? t("wardrobe_stylist.status_ready", {
                  model: status.reasoning_model_id,
                  count: status.ready_items,
                })
              : t("wardrobe_stylist.status_fallback_only", { count: status.ready_items })}
          </p>
        )}

        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(null);
          }}
          noValidate
        >
          <div>
            <label htmlFor={`${uid}-occasion`} className={labelClass}>
              {t("wardrobe_stylist.occasion")}
            </label>
            <select
              id={`${uid}-occasion`}
              value={occasion}
              onChange={(e) => setOccasion(e.target.value)}
              className={fieldClass}
            >
              {OCCASIONS.map((o) => (
                <option key={o} value={o}>
                  {t(`wardrobe_stylist.occasions.${o}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor={`${uid}-time`} className={labelClass}>
                {t("wardrobe_stylist.time_of_day")}
              </label>
              <select
                id={`${uid}-time`}
                value={timeOfDay}
                onChange={(e) => setTimeOfDay(e.target.value as StylistTimeOfDay | "")}
                className={fieldClass}
              >
                <option value="">{t("wardrobe_stylist.any")}</option>
                {TIMES.map((v) => (
                  <option key={v} value={v}>
                    {t(`wardrobe_stylist.times.${v}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`${uid}-season`} className={labelClass}>
                {t("wardrobe_stylist.season")}
              </label>
              <select
                id={`${uid}-season`}
                value={season}
                onChange={(e) => setSeason(e.target.value as StylistSeason | "")}
                className={fieldClass}
              >
                <option value="">{t("wardrobe_stylist.any")}</option>
                {SEASONS.map((v) => (
                  <option key={v} value={v}>
                    {t(`wardrobe_stylist.seasons.${v}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label htmlFor={`${uid}-location`} className={labelClass}>
              {t("wardrobe_stylist.location")}
            </label>
            <input
              id={`${uid}-location`}
              type="text"
              maxLength={120}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder={t("wardrobe_stylist.location_placeholder")}
              className={fieldClass}
            />
          </div>

          <details className="group rounded-2xl border border-slate-200 p-3">
            <summary className="cursor-pointer select-none text-xs font-semibold text-brand-charcoal">
              {t("wardrobe_stylist.more_prefs")}
            </summary>
            <div className="mt-3 space-y-3">
              <div>
                <label htmlFor={`${uid}-style`} className={labelClass}>
                  {t("wardrobe_stylist.style_prefs")}
                </label>
                <input
                  id={`${uid}-style`}
                  type="text"
                  value={styleText}
                  onChange={(e) => setStyleText(e.target.value)}
                  placeholder={t("wardrobe_stylist.style_prefs_placeholder")}
                  aria-describedby={`${uid}-style-help`}
                  className={fieldClass}
                />
                <p id={`${uid}-style-help`} className="mt-1 text-[11px] text-brand-muted">
                  {t("wardrobe_stylist.comma_help")}
                </p>
              </div>
              <div>
                <label htmlFor={`${uid}-colors`} className={labelClass}>
                  {t("wardrobe_stylist.color_prefs")}
                </label>
                <input
                  id={`${uid}-colors`}
                  type="text"
                  value={colorText}
                  onChange={(e) => setColorText(e.target.value)}
                  placeholder={t("wardrobe_stylist.color_prefs_placeholder")}
                  className={fieldClass}
                />
              </div>
              <div>
                <label htmlFor={`${uid}-excluded-colors`} className={labelClass}>
                  {t("wardrobe_stylist.excluded_colors")}
                </label>
                <input
                  id={`${uid}-excluded-colors`}
                  type="text"
                  value={excludedColorText}
                  onChange={(e) => setExcludedColorText(e.target.value)}
                  placeholder={t("wardrobe_stylist.excluded_colors_placeholder")}
                  aria-describedby={`${uid}-excluded-colors-hint`}
                  className={fieldClass}
                />
                <p id={`${uid}-excluded-colors-hint`} className="mt-1 text-xs text-slate-500">
                  {t("wardrobe_stylist.excluded_colors_hint")}
                </p>
              </div>
              <div>
                <label htmlFor={`${uid}-comfort`} className={labelClass}>
                  {t("wardrobe_stylist.comfort")}
                </label>
                <input
                  id={`${uid}-comfort`}
                  type="text"
                  maxLength={200}
                  value={comfort}
                  onChange={(e) => setComfort(e.target.value)}
                  placeholder={t("wardrobe_stylist.comfort_placeholder")}
                  className={fieldClass}
                />
              </div>
              <div>
                <label htmlFor={`${uid}-exclusions`} className={labelClass}>
                  {t("wardrobe_stylist.exclusions")}
                </label>
                <input
                  id={`${uid}-exclusions`}
                  type="text"
                  maxLength={200}
                  value={exclusions}
                  onChange={(e) => setExclusions(e.target.value)}
                  placeholder={t("wardrobe_stylist.exclusions_placeholder")}
                  className={fieldClass}
                />
              </div>
            </div>
          </details>

          {excludedIds.length > 0 && (
            <p className="text-[11px] text-brand-muted">
              {t("wardrobe_stylist.excluded_count", { count: excludedIds.length })}{" "}
              <button data-motion="filter"
                type="button"
                onClick={() => setExcludedIds([])}
                className="font-semibold text-brand-charcoal underline-offset-2 hover:underline"
              >
                {t("wardrobe_stylist.clear_excluded")}
              </button>
            </p>
          )}

          <button data-motion-tone="icon" data-motion="creative"
            type="submit"
            disabled={phase === "loading"}
            aria-busy={phase === "loading"}
            className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-2xl bg-brand-charcoal px-5 py-3 text-xs font-bold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
          >
            {phase === "loading" ? t("wardrobe_stylist.generating") : t("wardrobe_stylist.generate")}
          </button>
          <p className="text-[11px] leading-relaxed text-brand-muted">{t("wardrobe_stylist.privacy_note")}</p>
        </form>
      </section>

      {/* ── Recommendation workspace ───────────────────────────── */}
      <section aria-labelledby={`${uid}-result`} aria-live="polite" className="min-w-0">
        <h2 id={`${uid}-result`} className="sr-only">
          {t("wardrobe_stylist.result_region")}
        </h2>

        {phase === "idle" && (
          <div className="rounded-[32px] border border-dashed border-slate-300 bg-white/60 p-8 text-center">
            <p className="font-serif text-2xl font-bold text-brand-charcoal">
              {readyItemCount === 0 ? t("wardrobe_stylist.empty_title") : t("wardrobe_stylist.idle_title")}
            </p>
            <p className="mx-auto mt-2 max-w-md text-sm font-light leading-relaxed text-brand-muted">
              {readyItemCount === 0 ? t("wardrobe_stylist.empty_body") : t("wardrobe_stylist.idle_body")}
            </p>
            {readyItemCount === 0 && (
              <button data-motion="upload"
                type="button"
                onClick={onOpenUpload}
                className="mt-6 inline-flex min-h-11 items-center rounded-2xl border border-brand-charcoal px-5 py-2.5 text-xs font-bold text-brand-charcoal transition-colors hover:bg-brand-charcoal hover:text-white"
              >
                {t("wardrobe.upload_piece")}
              </button>
            )}
          </div>
        )}

        {phase === "loading" && (
          <div
            role="status"
            className="rounded-[32px] border border-brand-hairline bg-white p-8 text-center shadow-2xs"
          >
            <div className="mx-auto h-8 w-8 motion-safe:animate-spin rounded-full border-2 border-slate-200 border-t-brand-charcoal" aria-hidden="true" />
            <p className="mt-4 text-sm font-semibold text-brand-charcoal">{t("wardrobe_stylist.loading_title")}</p>
            <p className="mt-1 text-xs text-brand-muted">{t("wardrobe_stylist.loading_body")}</p>
          </div>
        )}

        {phase === "error" && error && (
          <div role="alert" className="rounded-[32px] border border-rose-200 bg-rose-50 p-6">
            <p className="text-sm font-semibold text-rose-800">{t("wardrobe_stylist.error_title")}</p>
            <p className="mt-1 text-xs leading-relaxed text-rose-700">{error.message}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {error.retryable && (
                <button data-motion="recovery"
                  type="button"
                  onClick={() => void run(null)}
                  className="min-h-11 rounded-2xl bg-brand-charcoal px-5 py-2.5 text-xs font-bold text-white hover:bg-black"
                >
                  {t("common.try_again")}
                </button>
              )}
              {error.code === "VALIDATION_ERROR" && (
                <button data-motion="upload"
                  type="button"
                  onClick={onOpenUpload}
                  className="min-h-11 rounded-2xl border border-brand-charcoal px-5 py-2.5 text-xs font-bold text-brand-charcoal"
                >
                  {t("wardrobe.upload_piece")}
                </button>
              )}
            </div>
          </div>
        )}

        {phase === "success" && result && (
          <article className="space-y-5" data-testid="stylist-result" data-source={result.source}>
            <header className="rounded-[32px] border border-brand-hairline bg-white p-6 shadow-2xs">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${
                      result.ai_generated ? "bg-brand-charcoal text-white" : "bg-amber-100 text-amber-900"
                    }`}
                    data-testid="stylist-source-badge"
                  >
                    {sourceLabel}
                  </span>
                  <h3
                    ref={resultHeadingRef}
                    tabIndex={-1}
                    dir="auto" className="mt-3 font-serif text-2xl font-bold text-brand-charcoal outline-none"
                  >
                    {result.title}
                  </h3>
                  <p dir="auto" className="mt-1 text-sm font-light leading-relaxed text-brand-muted">{result.summary}</p>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-3 py-1 text-[11px] font-semibold ${
                    result.fit_status === "unsuitable"
                      ? "border-rose-200 bg-rose-50 text-rose-900"
                      : result.is_complete && result.fit_status !== "partial"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                        : "border-amber-200 bg-amber-50 text-amber-900"
                  }`}
                >
                  {result.fit_status === "unsuitable"
                    ? t("wardrobe_stylist.fit_unsuitable")
                    : result.fit_status === "partial"
                      ? t("wardrobe_stylist.fit_partial")
                      : result.is_complete
                        ? t("wardrobe_stylist.complete")
                        : t("wardrobe_stylist.partial")}
                </span>
              </div>
            </header>

            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label={t("wardrobe_stylist.items_label")}>
              {result.items.map((item) => (
                <li
                  key={item.wardrobe_item_id}
                  className="flex flex-col overflow-hidden rounded-[28px] border border-brand-hairline bg-white shadow-2xs"
                >
                  <div className="relative aspect-[4/5] bg-slate-100">
                    <HonestProductImage
                      src={item.image_url}
                      alt={`${item.title} — ${item.color_name} ${item.category}`}
                      className="h-full w-full object-cover"
                      unavailableLabel={t("wardrobe_stylist.image_unavailable")}
                    />
                    <span className="absolute start-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-brand-charcoal">
                      {t(`wardrobe_stylist.roles.${item.role}`)}
                    </span>
                    {item.selected_by === "rule_matcher" && (
                      <span
                        data-testid="stylist-item-rule-matched"
                        className="absolute end-3 top-3 rounded-full border border-amber-200 bg-amber-50/95 px-2.5 py-1 text-[10px] font-semibold text-amber-900"
                        title={t("wardrobe_stylist.rule_matched_hint")}
                      >
                        {t("wardrobe_stylist.rule_matched")}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-1 flex-col p-4">
                    <p className="font-serif text-base font-bold text-brand-charcoal">{item.title}</p>
                    <p className="text-[11px] text-brand-muted">
                      {[item.subcategory, item.color_name, item.category].filter(Boolean).join(" · ")}
                    </p>
                    <p dir="auto" className="mt-2 flex-1 text-sm leading-relaxed text-slate-700">{item.reason}</p>
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <span className="truncate text-[10px] text-brand-muted" title={item.analysis_source ?? undefined}>
                        {item.analysis_source
                          ? item.analysis_source === "manual" || item.analysis_source.startsWith("manual")
                            ? t("wardrobe_stylist.tagged_manually")
                            : t("wardrobe_stylist.tagged_by", { model: item.analysis_source })
                          : t("wardrobe_stylist.tagged_unknown")}
                      </span>
                      <button data-motion="filter"
                        type="button"
                        aria-label={t("wardrobe_stylist.swap_out_item", { item: item.title })}
                        onClick={() => excludeItem(item.wardrobe_item_id)}
                        className="min-h-9 rounded-xl border border-slate-200 px-3 text-[11px] font-semibold text-brand-charcoal hover:bg-slate-50"
                      >
                        {t("wardrobe_stylist.swap_out")}
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>

            {(result.styling_notes.length > 0 ||
              result.limitations.length > 0 ||
              result.missing_categories.length > 0 ||
              result.assumptions.length > 0) && (
              <div className="grid gap-4 md:grid-cols-2">
                {result.styling_notes.length > 0 && (
                  <section className="rounded-[28px] border border-brand-hairline bg-white p-5">
                    <h4 className="text-[11px] font-bold uppercase tracking-widest text-brand-charcoal">
                      {t("wardrobe_stylist.styling_notes")}
                    </h4>
                    <ul className="mt-2 list-disc space-y-1 ps-4 text-sm text-slate-700">
                      {result.styling_notes.map((n, i) => (
                        <li key={i} dir="auto">{n}</li>
                      ))}
                    </ul>
                  </section>
                )}
                {(result.limitations.length > 0 || result.missing_categories.length > 0 || result.assumptions.length > 0) && (
                  <section className="rounded-[28px] border border-amber-200 bg-amber-50 p-5">
                    <h4 className="text-[11px] font-bold uppercase tracking-widest text-amber-900">
                      {t("wardrobe_stylist.limitations")}
                    </h4>
                    <ul className="mt-2 list-disc space-y-1 ps-4 text-sm text-amber-900">
                      {result.missing_categories.length > 0 && (
                        <li>
                          {t("wardrobe_stylist.missing_categories", {
                            list: result.missing_categories.map((c) => t(`wardrobe_stylist.categories.${c}`, { defaultValue: c })).join(", "),
                          })}
                        </li>
                      )}
                      {result.limitations.filter((n) => !isServerMissingCategoryNote(n)).map((n, i) => (
                        <li key={`l${i}`} dir="auto">{n}</li>
                      ))}
                      {result.assumptions.map((n, i) => (
                        <li key={`a${i}`}>
                          {t("wardrobe_stylist.assumption_prefix")} {n}
                        </li>
                      ))}
                    </ul>
                    {result.missing_categories.length > 0 && (
                      <button data-motion="upload"
                        type="button"
                        onClick={onOpenUpload}
                        className="mt-3 min-h-9 rounded-xl border border-amber-900/30 px-3 text-[11px] font-semibold text-amber-900 hover:bg-amber-100"
                      >
                        {t("wardrobe.upload_piece")}
                      </button>
                    )}
                  </section>
                )}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <button data-motion="creative"
                type="button"
                onClick={() => void run(result)}
                className="min-h-11 rounded-2xl bg-brand-charcoal px-5 py-2.5 text-xs font-bold text-white hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
              >
                {t("wardrobe_stylist.another")}
              </button>
              <button data-motion="progressive"
                data-motion-state={savePhase === "saving" ? "pending" : savePhase === "saved" ? "done" : savePhase === "error" ? "failed" : undefined}
                type="button"
                onClick={() => void saveLook()}
                disabled={savePhase === "saving" || savePhase === "saved" || result.items.length === 0}
                aria-disabled={savePhase === "saving" || savePhase === "saved" || result.items.length === 0}
                aria-busy={savePhase === "saving"}
                aria-describedby={`${uid}-save-status`}
                data-testid="stylist-save-look"
                data-save-state={savePhase}
                className="min-h-11 rounded-2xl border border-brand-charcoal px-5 py-2.5 text-xs font-bold text-brand-charcoal hover:bg-brand-charcoal hover:text-white disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
              >
                {t("wardrobe_stylist.save_look")}
              </button>
              <p className="text-[11px] text-brand-muted">
                {result.latency_seconds != null && result.ai_generated
                  ? t("wardrobe_stylist.footer_model", {
                      seconds: result.latency_seconds.toFixed(1),
                      version: result.prompt_version ?? "",
                    })
                  : t("wardrobe_stylist.footer_fallback")}
              </p>
            </div>
            <p id={`${uid}-save-status`} role="status" aria-live="polite" className="text-[11px] text-brand-muted" data-testid="stylist-save-status">
              {savePhase === "saving"
                ? t("wardrobe_stylist.saving")
                : savePhase === "saved" && savedId != null
                  ? t("wardrobe_stylist.saved_detail", { id: savedId })
                  : savePhase === "error" && saveError
                    ? saveError
                    : ""}
            </p>
          </article>
        )}
      </section>
    </div>
  );
};

export default WardrobeStylistPanel;
