import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { wardrobeService, type SavedWardrobeOutfit } from "../../services/apiServices";
import { ApiError } from "../../services/apiClient";
import { HonestProductImage } from "../common/HonestProductImage";
import { SparkleIcon } from "../icons/ConfitIcons";

/**
 * Saved wardrobe looks (GET /wardrobe/outfits — migration 0048).
 *
 * Distinct from catalog "saved looks" (GET /outfits): these are outfits the
 * AI stylist assembled ONLY from garments the user owns. Every photo is the
 * stored wardrobe photo for that id; garments binned since saving are not
 * rendered — the server omits them and we say how many were dropped.
 * Provenance is shown per look (model id or "rule-based") — a fallback is
 * never dressed up as AI (FR-14/FR-18).
 */
export const SAVED_WARDROBE_LOOKS_KEY = ["wardrobe", "saved-wardrobe-looks"] as const;

interface Props {
  isAuthenticated: boolean;
  onOpenStylist?: () => void;
}

export const SavedWardrobeLooks: React.FC<Props> = ({ isAuthenticated, onOpenStylist }) => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const query = useQuery<SavedWardrobeOutfit[]>({
    queryKey: SAVED_WARDROBE_LOOKS_KEY,
    queryFn: () => wardrobeService.listSavedOutfits(),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });

  const remove = async (id: number) => {
    if (busyId != null) return;
    setBusyId(id);
    setNotice(null);
    try {
      await wardrobeService.deleteSavedOutfit(id);
      queryClient.setQueryData<SavedWardrobeOutfit[]>(SAVED_WARDROBE_LOOKS_KEY, (prev) =>
        (prev ?? []).filter((o) => o.id !== id),
      );
      setNotice(t("wardrobe_stylist.saved_looks_deleted"));
    } catch (e) {
      const api = e instanceof ApiError ? e : null;
      // A 404 means it is already gone — reflect reality rather than claim failure.
      if (api?.status === 404) {
        queryClient.setQueryData<SavedWardrobeOutfit[]>(SAVED_WARDROBE_LOOKS_KEY, (prev) =>
          (prev ?? []).filter((o) => o.id !== id),
        );
        setNotice(t("wardrobe_stylist.saved_looks_deleted"));
      } else {
        setNotice(t("wardrobe_stylist.saved_looks_delete_failed"));
      }
    } finally {
      setBusyId(null);
    }
  };

  if (!isAuthenticated) return null;

  const looks = query.data ?? [];
  const dateFmt = new Intl.DateTimeFormat(i18n.language === "ar" ? "ar-EG" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <section
      className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm"
      aria-labelledby="saved-wardrobe-looks-heading"
      data-testid="saved-wardrobe-looks"
    >
      <div className="mb-4">
        <h3
          id="saved-wardrobe-looks-heading"
          className="font-serif text-lg font-bold text-brand-charcoal flex items-center gap-2"
        >
          <SparkleIcon size={18} color="#252729" />
          {t("wardrobe_stylist.saved_looks_title")}
        </h3>
        <p className="text-xs text-brand-muted">{t("wardrobe_stylist.saved_looks_subtitle")}</p>
      </div>

      <p role="status" aria-live="polite" className="min-h-[1rem] text-[11px] text-brand-muted">
        {notice ?? ""}
      </p>

      {query.isLoading ? (
        <p className="text-sm text-brand-muted" aria-busy="true">
          …
        </p>
      ) : query.isError ? (
        <p className="text-sm text-red-700" role="alert">
          {t("wardrobe_stylist.saved_looks_error")}
        </p>
      ) : looks.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-brand-hairline p-6 text-center">
          <p className="text-sm text-brand-muted">{t("wardrobe_stylist.saved_looks_empty")}</p>
          {onOpenStylist && (
            <button data-motion="creative"
              type="button"
              onClick={onOpenStylist}
              className="mt-3 min-h-11 rounded-2xl bg-brand-charcoal px-5 py-2.5 text-xs font-bold text-white hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2"
            >
              {t("wardrobe_stylist.tab")}
            </button>
          )}
        </div>
      ) : (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2" aria-label={t("wardrobe_stylist.saved_looks_title")}>
          {looks.map((look) => {
            const createdLabel = (() => {
              const d = new Date(look.created_at);
              return Number.isNaN(d.getTime()) ? look.created_at : dateFmt.format(d);
            })();
            return (
              <li
                key={look.id}
                className="rounded-2xl border border-brand-hairline p-4"
                data-testid="saved-wardrobe-look"
                data-source={look.source}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="font-serif text-base font-bold text-brand-charcoal truncate">{look.title}</h4>
                    <p className="text-[11px] text-brand-muted">
                      {look.occasion} · {t("wardrobe_stylist.saved_looks_saved_on", { date: createdLabel })}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      look.ai_generated ? "bg-brand-wash text-brand-charcoal" : "bg-amber-50 text-amber-900"
                    }`}
                    data-testid="saved-look-provenance"
                  >
                    {look.ai_generated
                      ? t("wardrobe_stylist.saved_looks_made_by", { model: look.model_id ?? "watsonx.ai" })
                      : t("wardrobe_stylist.saved_looks_made_by_rules")}
                  </span>
                </div>

                {look.summary && <p className="mt-2 text-xs text-brand-charcoal/80">{look.summary}</p>}

                <ul className="mt-3 grid grid-cols-3 gap-2" aria-label={look.title}>
                  {look.items.map((it) => (
                    <li key={it.wardrobe_item_id} className="text-center">
                      <div className="aspect-[3/4] overflow-hidden rounded-xl bg-brand-wash">
                        <HonestProductImage
                          src={it.image_url ?? undefined}
                          alt={`${it.title} — ${it.color_name}`}
                          className="h-full w-full object-cover"
                        />
                      </div>
                      <p className="mt-1 truncate text-[11px] font-semibold text-brand-charcoal">{it.title}</p>
                      <p className="text-[10px] text-brand-muted">{it.role}</p>
                    </li>
                  ))}
                </ul>

                {(look.dropped_item_count > 0 || !look.is_complete) && (
                  <p className="mt-2 text-[11px] text-amber-900" data-testid="saved-look-caveat">
                    {look.dropped_item_count > 0
                      ? t("wardrobe_stylist.saved_looks_dropped", { count: look.dropped_item_count })
                      : t("wardrobe_stylist.saved_looks_incomplete")}
                  </p>
                )}

                <div className="mt-3 flex justify-end">
                  <button data-motion="destructive"
                    type="button"
                    onClick={() => void remove(look.id)}
                    disabled={busyId === look.id}
                    aria-disabled={busyId === look.id}
                    className="min-h-9 rounded-xl border border-brand-hairline px-3 text-[11px] font-semibold text-brand-charcoal hover:bg-brand-wash disabled:opacity-60"
                  >
                    {t("wardrobe_stylist.saved_looks_delete")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};

export default SavedWardrobeLooks;
