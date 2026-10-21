import { CardStackShowcase, CircularGalleryShowcase } from "../../components/showcase/DesignShowcases";
import { HeroSection, HeroLightCard } from "../../components/common/HeroSection";
import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCatalogViewModel } from "../../viewmodels/useCatalogViewModel";
import { useUIStore } from "../../stores/uiStore";
import { useCartStore } from "../../stores/cartStore";
import { catalogService } from "../../services/apiServices";
import { AutocompleteSuggestion } from "../../models";
import { VisualSearchIcon } from "../../components/icons/ConfitIcons";
import {
  SkeletonCard,
  EmptyState,
} from "../../components/common/CommonComponents";
import { useCapabilities } from "../../hooks/useCapabilities";
import { resolvePurchasableSku } from "../../lib/catalogSku";
import { ProductCard } from "../../components/product/ProductCard";
import { AccessibleCarousel } from "../../components/common/AccessibleCarousel";
import { Surface } from "../../components/common/Surface";
import { useDeviceWishlist } from "../../hooks/useDeviceWishlist";
import {
  classifyActionError,
  type ActionOutcome,
} from "../../components/common/InteractionPrimitives";

// `value` is the catalogue token each control is matched against; the
// label key is what the shopper reads. These arrays are ALSO the URL
// validation whitelist — one source of truth for pills and deep links.
const COLOR_SWATCHES = [
  { value: "", labelKey: "discover.filter_all", hex: "transparent" },
  { value: "Navy Blue", labelKey: "discover.color_navy_blue", hex: "#1B1F3B" },
  { value: "Midnight Black", labelKey: "discover.color_midnight_black", hex: "#111111" },
  { value: "Optic White", labelKey: "discover.color_optic_white", hex: "#FAF9F6" },
  { value: "Champagne Gold", labelKey: "discover.color_champagne_gold", hex: "#D4AF37" },
  { value: "Emerald Green", labelKey: "discover.color_emerald_green", hex: "#2D4A3E" },
];
const COLOR_VALUES = COLOR_SWATCHES.map((c) => c.value).filter(Boolean);
// How many occasion pills to surface before the row gets noisy; the
// vocabulary endpoint already orders by product count descending.
const MAX_OCCASION_PILLS = 6;
const SORT_VALUES = ["recommended", "price_asc", "price_desc", "rating", "newest"];
const GENDER_OPTIONS = [
  { value: "Women", labelKey: "discover.gender_womens" },
  { value: "Men", labelKey: "discover.gender_mens" },
  { value: "Unisex", labelKey: "discover.gender_unisex" },
];
const GENDER_URL_MAP: Record<string, string> = {
  womens: "womens",
  women: "Women",
  mens: "mens",
  men: "Men",
  unisex: "Unisex",
};

/** One pill, one contract: 44px floor, aria-pressed state, luxury easing.
 *  Previously this styling was hand-rolled FIVE times in this file. */
const FilterPill: React.FC<{
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ selected, onClick, children }) => (
  <button data-motion="filter" data-motion-tone="icon"
    type="button"
    aria-pressed={selected}
    onClick={onClick}
    className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full px-4 text-xs font-semibold transition-all duration-300 ease-luxury focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white ${
      selected
        ? "bg-brand-charcoal text-white shadow-xs"
        : "bg-white border border-slate-200 text-brand-charcoal hover:bg-brand-wash"
    }`}
  >
    {children}
  </button>
);

export const DiscoverView: React.FC = () => {
  const { t, i18n } = useTranslation();
  // The active UI language drives number/currency formatting; the data
  // tokens in the filter arrays below stay English regardless.
  const lang = i18n.resolvedLanguage ?? "en";
  const isArabic = lang.startsWith("ar");
  const navigate = useNavigate();
  const {
    products,
    categories,
    occasions = [],
    selectedCategory,
    setSelectedCategory,
    selectedGender = "",
    setSelectedGender = () => {},
    selectedStyle = "",
    setSelectedStyle = () => {},
    selectedOccasion,
    setSelectedOccasion,
    selectedColor,
    setSelectedColor,
    searchQuery,
    setSearchQuery,
    sortBy,
    setSortBy,
    isLoading,
    error: catalogError,
    refresh: refreshCatalog,
  } = useCatalogViewModel();

  const { openVisualSearch, showToast } = useUIStore();

  // Deep link: /discover?category=<slug> (the home page's collection rail
  // links here). Applied once per param value, and only for a slug the
  // categories API actually returned — an unknown slug is ignored instead of
  // silently emptying the whole catalogue.
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedCategory = searchParams.get("category");
  const appliedCategoryRef = useRef<string | null>(null);
  useEffect(() => {
    if (!requestedCategory || categories.length === 0) return;
    if (appliedCategoryRef.current === requestedCategory) return;
    if (categories.some((c) => c.slug === requestedCategory)) {
      appliedCategoryRef.current = requestedCategory;
      setSelectedCategory(requestedCategory);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedCategory, categories]);

  // C02 pass (2026-10-07): the URL was a READ-ONLY deep link — filters,
  // search and sort lived in memory only, so refresh/share/Back lost the
  // shopper's place. State now writes back at INTERACTION time (never from
  // a mount effect, so hydration can't clobber an incoming link), with
  // replace:true so typing never floods the history stack.
  const syncParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setSearchParams(next, { replace: true });
  };

  // Hydrate the NON-category params once on mount. Every value is
  // validated against the tokens this screen actually understands —
  // junk in the URL is ignored, never applied, never echoed back.
  const hydratedRef = useRef(false);
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    const pal = searchParams.get("palette");
    if (pal && COLOR_VALUES.includes(pal)) setSelectedColor(pal);
    const gen = (searchParams.get("gender") || "").trim().toLowerCase();
    if (gen && GENDER_URL_MAP[gen]) setSelectedGender(GENDER_URL_MAP[gen]);
    const sty = (searchParams.get("style") || "").trim();
    if (sty) setSelectedStyle(sty);
    const q = searchParams.get("q");
    if (q) setSearchQuery(q);
    const sort = searchParams.get("sort");
    if (sort && SORT_VALUES.includes(sort)) setSortBy(sort);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ?occasion= validates against the LIVE vocabulary (which loads async),
  // so it hydrates once that data exists — same contract as ?category=.
  // Tokens are normalised to lowercase; junk is ignored, never applied.
  const appliedOccasionRef = useRef<string | null>(null);
  const requestedOccasion = searchParams.get("occasion");
  useEffect(() => {
    if (!requestedOccasion || occasions.length === 0) return;
    if (appliedOccasionRef.current === requestedOccasion) return;
    const token = requestedOccasion.trim().toLowerCase();
    if (occasions.some((o) => o.value === token)) {
      appliedOccasionRef.current = requestedOccasion;
      setSelectedOccasion(token);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedOccasion, occasions]);
  // Try-on CTAs bind to the live engine verdict (2026-09-22): when the GPU
  // cannot render, these route to the no-photo fit check instead of failing.
  const { capabilities } = useCapabilities();
  const { addItem } = useCartStore();

  const [autocompleteSuggestions, setAutocompleteSuggestions] = useState<
    AutocompleteSuggestion[]
  >([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  // Which suggestion the arrow keys have reached (-1 = none). Focus never
  // leaves the input — the APG combobox pattern.
  const [activeSugIdx, setActiveSugIdx] = useState(-1);
  // Device-side saved list — shared single source (C03: the PDP heart used
  // a bare useState and disagreed with this grid; see useDeviceWishlist).
  const { wishlist, toggleWishlist } = useDeviceWishlist();
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const selectSuggestion = (sug: AutocompleteSuggestion) => {
    if (sug.type === "product") {
      navigate(`/product/${sug.slug_or_query}`);
    } else {
      setSearchQuery(sug.title);
      syncParams({ q: sug.title });
    }
    setShowSuggestions(false);
    setActiveSugIdx(-1);
  };

  // Live Autocomplete
  useEffect(() => {
    if (searchQuery.trim().length >= 2) {
      catalogService
        .autocompleteCatalog(searchQuery.trim())
        .then((res) => {
          setAutocompleteSuggestions(res.suggestions || []);
          setShowSuggestions((res.suggestions || []).length > 0);
          setActiveSugIdx(-1);
        })
        .catch(() => setAutocompleteSuggestions([]));
    } else {
      setAutocompleteSuggestions([]);
      setShowSuggestions(false);
    }
  }, [searchQuery]);

  // Returns the real outcome so the card's button state machine never claims
  // "Added" for an add that did not happen (see InteractionPrimitives).
  const addCatalogCardToBag = async (p: any): Promise<ActionOutcome> => {
    const sku = await resolvePurchasableSku(p).catch(() => null);
    if (!sku) {
      showToast(t("commerce.no_purchasable_size"), "error");
      return "unavailable";
    }
    try {
      const res = await addItem(sku.id, {
        id: p.id,
        title: p.title,
        category: p.category_name,
        color: p.color_family,
      });
      // addItem resolves without adding when the duplicate-SKU dialog takes
      // over; the dialog is now the surface that finishes (or abandons) the
      // add, so the button must not say "Added".
      if (useCartStore.getState().pendingDuplicateAlert) {
        return "handled";
      }
      // Spec §5: a duplicate SKU surfaces the MERGED quantity as text,
      // derived from the server's own cart response.
      if (res?.merged) {
        showToast(t("toast.bag_quantity_merged", { count: res.quantity }), "success");
      } else {
        showToast(t("discover.added_to_bag"), "success");
      }
      return "success";
    } catch (err: any) {
      // 401 -> auth modal (context kept); offline -> named as such on the
      // control. Only a real server failure earns the generic error toast.
      const kind = classifyActionError(err);
      if (kind === "error") {
        showToast(err?.message || t("discover.add_to_bag_failed"), "error");
      }
      return kind;
    }
  };

  // No client-side re-filtering: category, occasion, palette and search all
  // filter SERVER-side through the view model's query. Filtering the API's
  // answer a second time hid products whenever the two implementations
  // disagreed (and the server is the one that is actually right).

  // Category names ship from the API in both spellings (`name`, `name_ar`);
  // the Arabic one was previously ignored on this screen.
  const categoryLabel = (cat: { name: string; name_ar?: string }) =>
    isArabic && cat.name_ar ? cat.name_ar : cat.name;
  // Known tags get a real translation; an unknown tag added by
  // merchandising tomorrow still renders readably ("black_tie" → "black
  // tie") instead of leaking a raw token or vanishing.
  const occasionLabel = (value: string) => {
    const key = `discover.occasion_${value}`;
    return i18n.exists(key) ? t(key) : value.replace(/_/g, " ");
  };
  const activeCategory = categories.find(
    (cat) => cat.slug === selectedCategory,
  );
  const activeFilters = [
    activeCategory
      ? t('discover.active_category', { name: categoryLabel(activeCategory) })
      : null,
    selectedGender
      ? t('discover.active_gender', {
          name: t(
            GENDER_OPTIONS.find((g) => g.value.toLowerCase() === selectedGender.toLowerCase())?.labelKey ??
              `discover.gender_${selectedGender.toLowerCase()}`,
          ),
        })
      : null,
    selectedStyle
      ? t('discover.active_style', { name: selectedStyle })
      : null,
    selectedOccasion
      ? t('discover.active_occasion', { name: occasionLabel(selectedOccasion) })
      : null,
    selectedColor
      ? t('discover.active_palette', {
          name: t(
            COLOR_SWATCHES.find((c) => c.value === selectedColor)?.labelKey ??
              selectedColor,
          ),
        })
      : null,
    searchQuery ? t('discover.active_search', { query: searchQuery }) : null,
  ].filter(Boolean);

  return (
    <div className="space-y-8 pb-24">
      <CardStackShowcase
        tone="consumer"
        compact
        eyebrow={t('discover.mood_stack_title')}
        title={t('discover.mood_stack_body')}
        description={t('discover.stack_description')}
      />
      {/* Header & Search — spec 07: compact dark editorial hero; the search
          cluster is the structured LIGHT card inside it. All text sits on
          the solid gradient, never on an image. */}
      <HeroSection
        compact
        headingLevel="h1"
        eyebrow={
          <span className="inline-flex rounded-full border border-brand-hairline bg-brand-wash px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-brand-charcoal">
            {t('discover.badge_multi_brand')}
          </span>
        }
        title={t("nav.style_discover")}
        /* lg: the search card moves under the title (left column). In the right
           column it sat inside the fixed AI Stylist footprint at 1024-1280
           (y 762-812 at 844 high); no width clears x 811+ at 1024. */
        asideClassName="lg:col-start-1 lg:row-start-2"
        lede={t('discover.subtitle')}
        aside={
          <HeroLightCard className="w-full lg:max-w-md lg:justify-self-start bg-white border-brand-hairline">
            <div className="flex items-center gap-2 relative" data-search-cluster>
          <div className="relative flex-1">
            {/* A placeholder is not an accessible name: it disappears as soon
                as the user types and is not reliably announced. Measured
                2026-09-23 with axe in a real browser — this shared search
                control had no accessible name on /discover and /stylist. */}
            <input
              ref={searchInputRef}
              type="text"
              role="combobox"
              aria-expanded={showSuggestions && autocompleteSuggestions.length > 0}
              aria-controls="discover-suggestions"
              aria-autocomplete="list"
              aria-activedescendant={
                showSuggestions && activeSugIdx >= 0
                  ? `discover-sug-${activeSugIdx}`
                  : undefined
              }
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setActiveSugIdx(-1);
                syncParams({ q: e.target.value.trim() || null });
              }}
              onKeyDown={(e) => {
                if (!showSuggestions || autocompleteSuggestions.length === 0) {
                  if (e.key === "Escape") setShowSuggestions(false);
                  return;
                }
                const last = autocompleteSuggestions.length - 1;
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActiveSugIdx((i) => (i >= last ? 0 : i + 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActiveSugIdx((i) => (i <= 0 ? last : i - 1));
                } else if (e.key === "Enter" && activeSugIdx >= 0) {
                  e.preventDefault();
                  selectSuggestion(autocompleteSuggestions[activeSugIdx]);
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setShowSuggestions(false);
                  setActiveSugIdx(-1);
                }
              }}
              onFocus={() => {
                if (autocompleteSuggestions.length > 0)
                  setShowSuggestions(true);
              }}
              onBlur={(e) => {
                // Close only when focus truly LEAVES the search cluster —
                // the old 200ms timeout hid the list under a keyboard
                // user's feet while they tabbed into it.
                const wrap = e.currentTarget.closest('[data-search-cluster]');
                if (!wrap?.contains(e.relatedTarget as Node)) {
                  setShowSuggestions(false);
                }
              }}
              aria-label={t('discover.search_label')}
              placeholder={t('discover.search_placeholder')}
              className="w-full ps-4 pe-10 py-3 rounded-2xl border border-slate-200 text-xs focus:outline-none focus:border-brand-charcoal focus:ring-2 focus:ring-brand-charcoal focus:ring-offset-2 focus:ring-offset-white bg-white shadow-2xs placeholder:text-brand-muted"
            />
            {searchQuery && (
              <button data-motion="progressive" data-motion-tone="icon"
                type="button"
                aria-label={t('discover.clear_search')}
                onClick={() => {
                  setSearchQuery("");
                  setShowSuggestions(false);
                  syncParams({ q: null });
                }}
                className="absolute end-2 top-1/2 -translate-y-1/2 inline-flex h-8 w-8 items-center justify-center rounded-lg text-xs text-brand-muted transition-colors duration-300 ease-luxury hover:text-brand-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal"
              >
                <span aria-hidden="true">✕</span>
              </button>
            )}

            {/* Instant Autocomplete Dropdown */}
            {showSuggestions && autocompleteSuggestions.length > 0 && (
              <div className="absolute top-full start-0 end-0 mt-2 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-50 animate-in fade-in duration-100 divide-y divide-slate-100">
                <div className="p-2.5 bg-brand-wash text-[10px] font-bold text-brand-charcoal uppercase tracking-wider">
                  {t('discover.suggested_matches')}
                </div>
                {/* Screen readers hear how many matches arrived without
                    leaving the input. */}
                <div role="status" className="sr-only">
                  {t('discover.suggestions_status', {
                    count: autocompleteSuggestions.length,
                  })}
                </div>
                <div
                  id="discover-suggestions"
                  role="listbox"
                  aria-label={t('discover.suggested_matches')}
                  className="divide-y divide-slate-100"
                >
                {autocompleteSuggestions.map((sug, idx) => (
                  /* APG combobox: options are NOT tab stops — focus stays in
                     the input and ArrowDown/ArrowUp + Enter drive selection
                     via aria-activedescendant. onMouseDown preventDefault
                     keeps a mouse click from blurring the input (which
                     would close the list before the click registered). */
                  <div
                    key={idx}
                    id={`discover-sug-${idx}`}
                    role="option"
                    aria-selected={activeSugIdx === idx}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectSuggestion(sug)}
                    onMouseEnter={() => setActiveSugIdx(idx)}
                    className={`w-full p-3 cursor-pointer flex items-center justify-between gap-2 text-xs text-start transition-colors duration-300 ease-luxury ${
                      activeSugIdx === idx
                        ? "bg-brand-wash ring-2 ring-inset ring-brand-charcoal"
                        : "hover:bg-brand-wash"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {sug.thumbnail_url ? (
                        <img
                          src={sug.thumbnail_url}
                          alt=""
                          className="w-9 h-9 rounded-xl object-cover border border-slate-100"
                        />
                      ) : (
                        <span
                          aria-hidden="true"
                          className="w-9 h-9 rounded-xl bg-brand-wash text-brand-charcoal flex items-center justify-center font-serif font-bold text-sm"
                        >
                          {(sug.title || "?").charAt(0).toUpperCase()}
                        </span>
                      )}
                      <span>
                        <span className="font-bold text-brand-charcoal block">
                          {sug.title}
                        </span>
                        {sug.subtitle && (
                          <span className="text-[10px] text-brand-muted font-light">
                            {sug.subtitle}
                          </span>
                        )}
                      </span>
                    </div>
                    <span className="text-[9px] px-2.5 py-0.5 rounded-full bg-brand-wash text-brand-muted font-semibold uppercase shrink-0">
                      {t(
                        sug.type === "product"
                          ? 'discover.sug_type_product'
                          : sug.type === "brand"
                            ? 'discover.sug_type_brand'
                            : 'discover.sug_type_category',
                      )}
                    </span>
                  </div>
                ))}
                </div>
              </div>
            )}
          </div>

          {/* The accessible name must CONTAIN the visible words (WCAG 2.5.3):
              a speech user saying "Photo match" has to hit this control, and
              an aria-label that replaced the visible text made that fail. The
              sr-only span keeps a name when the visible label is hidden on
              narrow viewports, where there is no visible text to match. */}
          <button data-motion="creative"
            onClick={openVisualSearch}
            type="button"
            className="min-h-11 px-4 py-3 rounded-2xl bg-brand-wash hover:bg-brand-charcoal hover:text-white border border-brand-field text-brand-charcoal text-xs font-semibold shadow-2xs transition-all flex items-center gap-1.5 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal focus-visible:ring-offset-2 focus-visible:ring-offset-white"
          >
            <span aria-hidden="true"><VisualSearchIcon size={16} color="currentColor" /></span>
            <span className="hidden sm:inline">{t('discover.photo_match')}</span>
            <span className="sr-only">{t('discover.search_by_photo')}</span>
          </button>
            </div>
          </HeroLightCard>
        }
      />

      {/* Spec 10 — REAL-data collection rail: the AccessibleCarousel wired
          to the live catalog query (same fetch as the grid — no new API,
          no invented "trending" metric §11). Keyboard arrows + Home/End,
          RTL-correct, no autoplay, honest loading/error/empty states. */}
      <Surface as="section" variant="raised" reveal className="space-y-3 rounded-2xl p-4 sm:p-6">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-widest text-brand-muted">
            {t('discover.rail_eyebrow')}
          </span>
          <h2 className="mt-1 font-serif text-2xl font-bold text-brand-charcoal">
            {t('discover.rail_title')}
          </h2>
        </div>
        <AccessibleCarousel
          items={products.slice(0, 10)}
          getKey={(p) => p.id}
          label={t('discover.rail_label')}
          isLoading={isLoading}
          error={products.length === 0 ? catalogError : null}
          onRetry={refreshCatalog}
          data-testid="discover-collection-rail"
          renderItem={(p) => (
            <ProductCard
              product={p}
              variant="compact"
              isWishlisted={wishlist.includes(p.id)}
              onToggleWishlist={toggleWishlist}
            />
          )}
        />
      </Surface>

      {/* Filter Tabs & Occasion Pills */}
      <div className="space-y-4">
        {/* Category Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <FilterPill
            selected={selectedCategory === ""}
            onClick={() => {
              setSelectedCategory("");
              syncParams({ category: null });
            }}
          >
            {t('discover.all_categories')}
          </FilterPill>
          {categories.map((cat) => (
            <FilterPill
              key={cat.id}
              selected={selectedCategory === cat.slug}
              onClick={() => {
                setSelectedCategory(cat.slug);
                syncParams({ category: cat.slug });
              }}
            >
              {categoryLabel(cat)}
            </FilterPill>
          ))}
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-bold text-brand-muted uppercase tracking-wider shrink-0">
            {t('discover.gender_label')}
          </span>
          <FilterPill
            selected={selectedGender === ""}
            onClick={() => {
              setSelectedGender("");
              syncParams({ gender: null });
            }}
          >
            {t('discover.filter_all')}
          </FilterPill>
          {GENDER_OPTIONS.map((opt) => (
            <FilterPill
              key={opt.labelKey}
              selected={selectedGender.toLowerCase() === opt.value.toLowerCase()}
              onClick={() => {
                const token = opt.value.toLowerCase() === 'women' ? 'womens' : opt.value.toLowerCase() === 'men' ? 'mens' : 'unisex';
                setSelectedGender(token);
                syncParams({ gender: token });
              }}
            >
              {t(opt.labelKey)}
            </FilterPill>
          ))}
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-bold text-brand-muted uppercase tracking-wider shrink-0">
            {t('discover.occasion_label')}
          </span>
          <FilterPill
            selected={selectedOccasion === ""}
            onClick={() => {
              setSelectedOccasion("");
              syncParams({ occasion: null });
            }}
          >
            {t('discover.filter_all')}
          </FilterPill>
          {occasions.slice(0, MAX_OCCASION_PILLS).map((occasion) => (
            <FilterPill
              key={occasion.value}
              selected={selectedOccasion === occasion.value}
              onClick={() => {
                setSelectedOccasion(occasion.value);
                syncParams({ occasion: occasion.value });
              }}
            >
              <span className="capitalize">{occasionLabel(occasion.value)}</span>
            </FilterPill>
          ))}
        </div>

        {/* Color Palette & Occasion & Sort Filters */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          {/* Color Swatch Filters */}
          <div className="flex items-center gap-2 overflow-x-auto">
            <span className="text-[11px] font-bold text-brand-muted uppercase tracking-wider">
              {t('discover.palette_label')}
            </span>
            {COLOR_SWATCHES.map((col) => (
              <FilterPill
                key={col.labelKey}
                selected={
                  (selectedColor === "" && col.value === "") ||
                  selectedColor === col.value
                }
                onClick={() => {
                  setSelectedColor(col.value);
                  syncParams({ palette: col.value || null });
                }}
              >
                {col.hex !== "transparent" && (
                  <span
                    aria-hidden="true"
                    className="w-2.5 h-2.5 rounded-full border border-white/40"
                    style={{ backgroundColor: col.hex }}
                  />
                )}
                <span>{t(col.labelKey)}</span>
              </FilterPill>
            ))}
          </div>

          {/* Sort Selector */}
          <div className="flex items-center gap-2">
            <span
              className="text-[11px] text-brand-muted"
              title={t('discover.sort_hint')}
            >
              {t('discover.sort_label')}
            </span>
            <select
              aria-label={t('a11y.sort_products')}
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                syncParams({
                  sort: e.target.value === "recommended" ? null : e.target.value,
                });
              }}
              className="min-h-11 text-xs font-semibold bg-white border border-slate-200 rounded-xl px-3 py-2 transition-colors duration-300 ease-luxury focus:outline-none focus:border-brand-charcoal focus:ring-2 focus:ring-brand-charcoal focus:ring-offset-2 focus:ring-offset-white"
            >
              <option value="recommended">{t('discover.sort_recommended')}</option>
              <option value="price_asc">{t('discover.sort_price_asc')}</option>
              <option value="price_desc">{t('discover.sort_price_desc')}</option>
              <option value="rating">{t('discover.sort_rating')}</option>
              <option value="newest">{t('discover.sort_newest')}</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-2xs">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-bold text-brand-muted uppercase tracking-wider">
            {t('discover.browsing_prefix')}
          </span>
          {activeFilters.length > 0 ? (
            activeFilters.map((filter) => (
              <span
                key={filter}
                className="rounded-full bg-brand-wash px-3 py-1 font-semibold text-brand-charcoal"
              >
                {filter}
              </span>
            ))
          ) : (
            <span className="text-brand-muted">
              {t('discover.browsing_all')}
            </span>
          )}
        </div>
        {activeFilters.length > 0 && (
          <button data-motion="filter"
            onClick={() => {
              setSelectedCategory("");
              setSelectedGender("");
              setSelectedStyle("");
              setSelectedOccasion("");
              setSelectedColor("");
              setSearchQuery("");
              syncParams({ category: null, gender: null, style: null, occasion: null, palette: null, q: null });
            }}
            className="inline-flex min-h-11 items-center text-xs font-bold text-brand-charcoal underline underline-offset-4 transition-colors duration-300 ease-luxury hover:text-brand-charcoal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-charcoal rounded-lg"
          >
            {t('discover.clear_filters')}
          </button>
        )}
      </div>

      {/* Product Grid */}
      {isLoading ? (
        <div
          className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6"
          aria-busy="true"
        >
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : catalogError && products.length === 0 ? (
        // N-1: the old client-side catalog fallback used to fabricate products
        // here on any backend failure. An unreachable catalog must render as an
        // explicit error with a retry — never as a stocked store.
        <EmptyState
          title={t('discover.catalog_error_title')}
          description={catalogError}
          actionText={t('common.retry')}
          onAction={refreshCatalog}
        />
      ) : products.length === 0 ? (
        <EmptyState
          title={t('discover.empty_title')}
          description={t('discover.empty_body')}
          actionText={t('discover.reset_filters')}
          onAction={() => {
            setSelectedCategory("");
            setSelectedGender("");
            setSelectedStyle("");
            setSelectedOccasion("");
            setSelectedColor("");
            setSearchQuery("");
            syncParams({ category: null, gender: null, style: null, occasion: null, palette: null, q: null });
          }}
        />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
          {products.map((p) => (
            <ProductCard
              key={p.id}
              product={p}
              isWishlisted={wishlist.includes(p.id)}
              onToggleWishlist={toggleWishlist}
              onAddToBag={addCatalogCardToBag}
              footerSlot={
                <>
                  <div>
                    {capabilities.bnpl_live ? (
                      // bnpl_live is measured, but the LIST payload carries no
                      // instalment figure and no provider: the old badge here
                      // hardcoded "Tabby" and divided the price by 4 in the
                      // browser — claims the API never made. The real figure
                      // (server-computed, currency-converted) lives on the
                      // product page and in the cart.
                      <span className="text-[11px] text-brand-muted">
                        {t('commerce.bnpl_available_checkout')}
                      </span>
                    ) : (
                      <span className="text-[11px] text-brand-muted">
                        {t('commerce.bnpl_not_live')}
                      </span>
                    )}
                  </div>
                  <div className="rounded-2xl bg-brand-wash px-3 py-2 text-[11px] text-brand-muted">
                    {p.fit_available && p.recommended_size
                      ? t('discover.likely_fit', { size: p.recommended_size })
                      : t('discover.set_measurements')}
                  </div>
                </>
              }
            />
          ))}
        </div>
      )}

      {/* Spec 11: optional depth gallery as the closing mood/collection
          moment — flag-gated, capability-gated, 2D fallback inside. Last
          in the page so it can never become the LCP element. */}
      <CircularGalleryShowcase tone="consumer" compact />
    </div>
  );
};
