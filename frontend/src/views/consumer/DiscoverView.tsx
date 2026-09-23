import { CardStackShowcase } from "../../components/showcase/DesignShowcases";
import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCatalogViewModel } from "../../viewmodels/useCatalogViewModel";
import { useUIStore } from "../../stores/uiStore";
import { useCartStore } from "../../stores/cartStore";
import { catalogService } from "../../services/apiServices";
import { AutocompleteSuggestion } from "../../models";
import {
  TryOnIcon,
  RulerIcon,
  BagIcon,
  VisualSearchIcon,
  SparkleIcon,
  HeartIcon,
} from "../../components/icons/ConfitIcons";
import {
  FitScoreBadge,
  BNPLBadge,
  SkeletonCard,
  EmptyState,
} from "../../components/common/CommonComponents";
import { HonestProductImage } from "../../components/common/HonestProductImage";
import { useCapabilities } from "../../hooks/useCapabilities";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { resolvePurchasableSku } from "../../lib/catalogSku";

export const DiscoverView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    products,
    categories,
    selectedCategory,
    setSelectedCategory,
    selectedOccasion,
    setSelectedOccasion,
    searchQuery,
    setSearchQuery,
    sortBy,
    setSortBy,
    isLoading,
    error: catalogError,
    refresh: refreshCatalog,
  } = useCatalogViewModel();

  const { openTryOn, openRuler, openVisualSearch, showToast } = useUIStore();
  // Try-on CTAs bind to the live engine verdict (2026-09-22): when the GPU
  // cannot render, these route to the no-photo fit check instead of failing.
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);
  const { capabilities } = useCapabilities();
  const { addItem } = useCartStore();

  const [autocompleteSuggestions, setAutocompleteSuggestions] = useState<
    AutocompleteSuggestion[]
  >([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedColor, setSelectedColor] = useState<string>("");
  const [wishlist, setWishlist] = useState<number[]>([]);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  // Live Autocomplete
  useEffect(() => {
    if (searchQuery.trim().length >= 2) {
      catalogService
        .autocompleteCatalog(searchQuery.trim())
        .then((res) => {
          setAutocompleteSuggestions(res.suggestions || []);
          setShowSuggestions((res.suggestions || []).length > 0);
        })
        .catch(() => setAutocompleteSuggestions([]));
    } else {
      setAutocompleteSuggestions([]);
      setShowSuggestions(false);
    }
  }, [searchQuery]);

  const addCatalogCardToBag = async (p: any) => {
    try {
      const sku = await resolvePurchasableSku(p);
      if (!sku) {
        showToast(
          "No purchasable size is available for this item right now.",
          "error",
        );
        return;
      }
      await addItem(sku.id, {
        id: p.id,
        title: p.title,
        category: p.category_name,
        color: p.color_family,
      });
      showToast("Added to bag", "success");
    } catch (err: any) {
      showToast(err?.message || "Could not add this item to bag.", "error");
    }
  };

  const toggleWishlist = (productId: number) => {
    setWishlist((prev) =>
      prev.includes(productId)
        ? prev.filter((id) => id !== productId)
        : [...prev, productId],
    );
  };

  const filteredProducts = products.filter((p) => {
    if (
      selectedColor &&
      !p.color_family.toLowerCase().includes(selectedColor.toLowerCase())
    ) {
      return false;
    }
    if (
      selectedOccasion &&
      !(p.occasion_tags || []).some((tag) =>
        tag.toLowerCase().includes(selectedOccasion.toLowerCase()),
      )
    ) {
      return false;
    }
    return true;
  });

  const colorSwatches = [
    { label: "All", hex: "transparent" },
    { label: "Navy Blue", hex: "#1B1F3B" },
    { label: "Midnight Black", hex: "#111111" },
    { label: "Optic White", hex: "#FAF9F6" },
    { label: "Champagne Gold", hex: "#D4AF37" },
    { label: "Emerald Green", hex: "#2D4A3E" },
  ];

  const occasionFilters = ["Work", "Wedding", "Evening", "Travel", "Everyday"];
  const activeCategoryName = categories.find(
    (cat) => cat.slug === selectedCategory,
  )?.name;
  const activeFilters = [
    activeCategoryName ? `Category: ${activeCategoryName}` : null,
    selectedOccasion ? `Occasion: ${selectedOccasion}` : null,
    selectedColor ? `Palette: ${selectedColor}` : null,
    searchQuery ? `Search: ${searchQuery}` : null,
  ].filter(Boolean);

  return (
    <div className="space-y-8 pb-24">
      <CardStackShowcase
        tone="consumer"
        compact
        eyebrow="Discovery Mood Stack"
        title="Browse by real outfit direction, not only filters"
        description="The animated stack introduces tactile editorial browsing before customers refine by category, occasion, brand, and size."
      />
      {/* Header & Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/80 pb-6">
        <div>
          <span className="text-[10px] font-bold text-[#7A5C28] uppercase tracking-widest block">
            Luxury Multi-Brand Catalog
          </span>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
            {t("nav.style_discover")}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
            Curated European tailoring, sculptural classics, and silk evening
            silhouettes.
          </p>
        </div>

        {/* Search & Visual Match Button */}
        <div className="flex items-center gap-2 max-w-md w-full relative">
          <div className="relative flex-1">
            {/* A placeholder is not an accessible name: it disappears as soon
                as the user types and is not reliably announced. Measured
                2026-09-23 with axe in a real browser — this shared search
                control had no accessible name on /discover and /stylist. */}
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => {
                if (autocompleteSuggestions.length > 0)
                  setShowSuggestions(true);
              }}
              onBlur={() => {
                setTimeout(() => setShowSuggestions(false), 200);
              }}
              aria-label={t('discover.search_label')}
              placeholder={t('discover.search_placeholder')}
              className="w-full pl-4 pr-10 py-3 rounded-2xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059] bg-white shadow-2xs placeholder:text-slate-500"
            />
            {searchQuery && (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setShowSuggestions(false);
                }}
                className="absolute right-3 top-3 text-xs text-slate-500 hover:text-slate-700"
              >
                ✕
              </button>
            )}

            {/* Instant Autocomplete Dropdown */}
            {showSuggestions && autocompleteSuggestions.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-50 animate-in fade-in duration-100 divide-y divide-slate-100">
                <div className="p-2.5 bg-[#FAF9F6] text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                  Instant Suggested Matches
                </div>
                {autocompleteSuggestions.map((sug, idx) => (
                  <div
                    key={idx}
                    onMouseDown={() => {
                      if (sug.type === "product") {
                        navigate(`/product/${sug.slug_or_query}`);
                      } else {
                        setSearchQuery(sug.title);
                        setShowSuggestions(false);
                      }
                    }}
                    className="p-3 hover:bg-[#FAF9F6] cursor-pointer flex items-center justify-between text-xs transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {sug.thumbnail_url ? (
                        <img
                          src={sug.thumbnail_url}
                          alt=""
                          className="w-9 h-9 rounded-xl object-cover border border-slate-100"
                        />
                      ) : (
                        <div className="w-9 h-9 rounded-xl bg-[#FDF8EE] text-[#C5A059] flex items-center justify-center font-bold text-xs">
                          {sug.type === "brand" ? "🏷️" : "📁"}
                        </div>
                      )}
                      <div>
                        <span className="font-bold text-[#1B1F3B] block">
                          {sug.title}
                        </span>
                        {sug.subtitle && (
                          <span className="text-[10px] text-slate-500 font-light">
                            {sug.subtitle}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-[9px] px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold uppercase">
                      {sug.type}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={openVisualSearch}
            className="px-4 py-3 rounded-2xl bg-[#FDF8EE] hover:bg-[#C5A059] hover:text-white border border-[#C5A059]/40 text-[#7A5C28] text-xs font-semibold shadow-2xs transition-all flex items-center gap-1.5 shrink-0"
            title="Search by Photo"
          >
            <VisualSearchIcon size={16} color="currentColor" />
            <span className="hidden sm:inline">Photo Match</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs & Occasion Pills */}
      <div className="space-y-4">
        {/* Category Pills */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => setSelectedCategory("")}
            className={`px-4 py-2.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
              selectedCategory === ""
                ? "bg-[#1B1F3B] text-white shadow-xs"
                : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
            }`}
          >
            All Categories
          </button>
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.slug)}
              className={`px-4 py-2.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
                selectedCategory === cat.slug
                  ? "bg-[#1B1F3B] text-white shadow-xs"
                  : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              {cat.name}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-bold text-slate-600 uppercase tracking-wider shrink-0">
            Occasion:
          </span>
          <button
            onClick={() => setSelectedOccasion("")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
              selectedOccasion === ""
                ? "bg-[#1B1F3B] text-white"
                : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
            }`}
          >
            All
          </button>
          {occasionFilters.map((occasion) => (
            <button
              key={occasion}
              onClick={() => setSelectedOccasion(occasion)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
                selectedOccasion === occasion
                  ? "bg-[#1B1F3B] text-white"
                  : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              {occasion}
            </button>
          ))}
        </div>

        {/* Color Palette & Occasion & Sort Filters */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          {/* Color Swatch Filters */}
          <div className="flex items-center gap-2 overflow-x-auto">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Palette:
            </span>
            {colorSwatches.map((col) => (
              <button
                key={col.label}
                onClick={() =>
                  setSelectedColor(col.label === "All" ? "" : col.label)
                }
                className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-medium transition-all ${
                  (selectedColor === "" && col.label === "All") ||
                  selectedColor === col.label
                    ? "bg-[#1B1F3B] text-white"
                    : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50"
                }`}
              >
                {col.hex !== "transparent" && (
                  <span
                    className="w-2.5 h-2.5 rounded-full border border-white/40"
                    style={{ backgroundColor: col.hex }}
                  />
                )}
                <span>{col.label}</span>
              </button>
            ))}
          </div>

          {/* Sort Selector */}
          <div className="flex items-center gap-2">
            <span
              className="text-[11px] text-slate-500"
              title="Recommended order uses the catalog ranking returned by the API for the selected filters."
            >
              Sort by:
            </span>
            <select
              aria-label="Sort products"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="text-xs font-semibold bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-[#C5A059]"
            >
              <option value="recommended">Top rated catalog order</option>
              <option value="price_asc">Price: Low to High</option>
              <option value="price_desc">Price: High to Low</option>
              <option value="rating">Customer Rating</option>
              <option value="newest">Newest Arrivals</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-2xs">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-bold text-slate-500 uppercase tracking-wider">
            You are browsing:
          </span>
          {activeFilters.length > 0 ? (
            activeFilters.map((filter) => (
              <span
                key={filter}
                className="rounded-full bg-[#FDF8EE] px-3 py-1 font-semibold text-[#7A5C28]"
              >
                {filter}
              </span>
            ))
          ) : (
            <span className="text-slate-500">
              All live catalog products, ordered by rating and catalog recency.
            </span>
          )}
        </div>
        {activeFilters.length > 0 && (
          <button
            onClick={() => {
              setSelectedCategory("");
              setSelectedOccasion("");
              setSelectedColor("");
              setSearchQuery("");
            }}
            className="text-xs font-bold text-[#1B1F3B] hover:text-[#C5A059]"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Product Grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : catalogError && products.length === 0 ? (
        // N-1: the old client-side catalog fallback used to fabricate products
        // here on any backend failure. An unreachable catalog must render as an
        // explicit error with a retry — never as a stocked store.
        <EmptyState
          title="The catalog couldn't be loaded"
          description={catalogError}
          actionText="Retry"
          onAction={refreshCatalog}
        />
      ) : filteredProducts.length === 0 ? (
        <EmptyState
          title="No luxury garments match your criteria"
          description="Try selecting a broader palette, clearing search terms, or exploring another collection."
          actionText="Reset All Filters"
          onAction={() => {
            setSelectedCategory("");
            setSelectedOccasion("");
            setSelectedColor("");
            setSearchQuery("");
          }}
        />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
          {filteredProducts.map((p) => {
            const isLiked = wishlist.includes(p.id);
            return (
              <div
                key={p.id}
                className="bg-white rounded-3xl border border-slate-200/80 p-3 sm:p-4 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="relative aspect-[3/4] rounded-2xl overflow-hidden bg-slate-100 mb-3">
                    <button
                      type="button"
                      onClick={() => navigate(`/product/${p.slug}`)}
                      className="h-full w-full text-left"
                      aria-label={`View ${p.title}`}
                    >
                      <HonestProductImage
                        src={p.thumbnail_url}
                        alt={p.title}
                        loading="lazy"
                        decoding="async"
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
                      />
                    </button>
                    <div className="absolute top-2.5 left-2.5 flex flex-col gap-1">
                      <FitScoreBadge
                        score={p.style_compatibility_score}
                        label="Match"
                        verdict="Color Harmony"
                      />
                    </div>

                    <button
                      onClick={() => toggleWishlist(p.id)}
                      className="absolute top-2.5 right-2.5 p-2 rounded-full bg-white/90 hover:bg-white text-slate-700 shadow-sm backdrop-blur-xs transition-all"
                      aria-label="Toggle Wishlist"
                    >
                      <HeartIcon size={15} isLiked={isLiked} />
                    </button>

                    <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5">
                      <button
                        onClick={() => openRuler(p)}
                        className="p-2 rounded-full bg-white/90 hover:bg-white text-slate-800 shadow-sm backdrop-blur-xs transition-all"
                        title="No-Photo Measurement Fit"
                      >
                        <RulerIcon size={14} color="#1B1F3B" />
                      </button>
                      <button
                        onClick={tryOn.gate({
                          render: () => openTryOn(p),
                          fitCheck: () => openRuler(p),
                        })}
                        disabled={tryOnKind === "blocked"}
                        className="p-2 rounded-full bg-[#1B1F3B]/90 hover:bg-[#C5A059] text-white hover:text-slate-950 shadow-sm backdrop-blur-xs transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        title={t(
                          tryOnKind === "render"
                            ? "tryon.cta_try_on"
                            : "tryon.cta_fit_check",
                        )}
                      >
                        {tryOnKind === "render" ? (
                          <TryOnIcon size={14} color="currentColor" />
                        ) : (
                          <RulerIcon size={14} color="currentColor" />
                        )}
                      </button>
                    </div>
                  </div>

                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                    {p.brand_name}
                  </span>
                  <h3
                    onClick={() => navigate(`/product/${p.slug}`)}
                    className="font-serif text-xs sm:text-sm font-bold text-[#1B1F3B] line-clamp-1 hover:text-[#C5A059] cursor-pointer mt-0.5"
                  >
                    {p.title}
                  </h3>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs sm:text-sm font-bold text-[#1B1F3B]">
                      ${p.base_price}
                    </span>
                    <span className="text-[11px] text-slate-500 font-light truncate max-w-[80px]">
                      {p.color_family}
                    </span>
                  </div>
                  <div className="mt-1.5">
                    {capabilities.bnpl_live ? (
                      // bnpl_live is the measured flag (live PSP adapter + key +
                      // live mode), so a badge shown here IS an offer.
                      <BNPLBadge price={p.base_price} provider="Tabby" isEstimate={false} />
                    ) : (
                      <span className="text-[11px] text-slate-500">
                        {t('commerce.bnpl_not_live')}
                      </span>
                    )}
                  </div>
                  <div className="mt-2 rounded-2xl bg-[#FAF9F6] px-3 py-2 text-[11px] text-slate-600">
                    {p.fit_available && p.recommended_size
                      ? `Likely fit: ${p.recommended_size}`
                      : "Set measurements for fit confidence"}
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-100 mt-3 grid grid-cols-2 gap-2">
                  <button
                    onClick={() => navigate(`/product/${p.slug}`)}
                    className="py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all shadow-2xs"
                  >
                    View details
                  </button>
                  <button
                    onClick={tryOn.gate({
                      render: () => openTryOn(p),
                      fitCheck: () => openRuler(p),
                    })}
                    disabled={tryOnKind === "blocked"}
                    className="py-2.5 rounded-xl border border-[#7A5C28]/40 bg-[#FDF8EE] text-[#7A5C28] hover:bg-[#7A5C28] hover:text-white text-xs font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {t(
                      tryOnKind === "render"
                        ? "tryon.cta_try_on"
                        : "tryon.cta_fit_check",
                    )}
                  </button>
                  <button
                    onClick={() => addCatalogCardToBag(p)}
                    className="col-span-2 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-all flex items-center justify-center gap-1.5"
                  >
                    <BagIcon size={14} color="currentColor" />
                    <span>Add to Bag</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
