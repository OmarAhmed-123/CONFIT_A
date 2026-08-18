import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { useUIStore } from '../../stores/uiStore';
import { useCartStore } from '../../stores/cartStore';
import { catalogService } from '../../services/apiServices';
import { AutocompleteSuggestion, SearchResponse } from '../../models';
import { TryOnIcon, RulerIcon, BagIcon, VisualSearchIcon, SparkleIcon } from '../../components/icons/ConfitIcons';
import { FitScoreBadge, BNPLBadge, SkeletonCard, EmptyState } from '../../components/common/CommonComponents';

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
  } = useCatalogViewModel();

  const { openTryOn, openRuler, openVisualSearch } = useUIStore();
  const { addItem } = useCartStore();

  const [autocompleteSuggestions, setAutocompleteSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [didYouMean, setDidYouMean] = useState<string | null>(null);
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

  return (
    <div className="space-y-8 pb-24">
      {/* Header & Search Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/80 pb-6">
        <div>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
            {t('nav.style_discover')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
            Discover curated multi-brand garments calibrated with AI fit scoring and live boutique inventory.
          </p>
        </div>

        {/* Search & Visual Match Button */}
        <div className="flex items-center gap-2 max-w-md w-full relative">
          <div className="relative flex-1">
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => {
                if (autocompleteSuggestions.length > 0) setShowSuggestions(true);
              }}
              onBlur={() => {
                // Delay hiding so clicks register
                setTimeout(() => setShowSuggestions(false), 200);
              }}
              placeholder="Search blazers, shirts, dresses, colors..."
              className="w-full pl-4 pr-10 py-2.5 rounded-2xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059] bg-white shadow-2xs"
            />
            {searchQuery && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setShowSuggestions(false);
                }}
                className="absolute right-3 top-2.5 text-xs text-slate-400"
              >
                ✕
              </button>
            )}

            {/* Instant Autocomplete Dropdown */}
            {showSuggestions && autocompleteSuggestions.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1.5 bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden z-40 animate-in fade-in duration-100 divide-y divide-slate-100">
                <div className="p-2 bg-slate-50 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  Instant Suggestions
                </div>
                {autocompleteSuggestions.map((sug, idx) => (
                  <div
                    key={idx}
                    onMouseDown={() => {
                      if (sug.type === 'product') {
                        navigate(`/product/${sug.slug_or_query}`);
                      } else {
                        setSearchQuery(sug.title);
                        setShowSuggestions(false);
                      }
                    }}
                    className="p-2.5 hover:bg-[#FAF9F6] cursor-pointer flex items-center justify-between text-xs transition-colors"
                  >
                    <div className="flex items-center gap-2.5">
                      {sug.thumbnail_url ? (
                        <img src={sug.thumbnail_url} alt="" className="w-8 h-8 rounded-lg object-cover" />
                      ) : (
                        <div className="w-8 h-8 rounded-lg bg-[#FDF8EE] text-[#C5A059] flex items-center justify-center font-bold text-[10px]">
                          {sug.type === 'brand' ? '🏷️' : '📁'}
                        </div>
                      )}
                      <div>
                        <span className="font-bold text-[#1B1F3B] block">{sug.title}</span>
                        {sug.subtitle && <span className="text-[10px] text-slate-400 font-light">{sug.subtitle}</span>}
                      </div>
                    </div>
                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold uppercase">
                      {sug.type}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={openVisualSearch}
            className="px-4 py-2.5 rounded-2xl bg-[#FDF8EE] hover:bg-[#C5A059] hover:text-white border border-[#C5A059]/40 text-[#C5A059] text-xs font-semibold shadow-2xs transition-all flex items-center gap-1.5 shrink-0"
            title="Search by Photo"
          >
            <VisualSearchIcon size={16} color="currentColor" />
            <span className="hidden sm:inline">Style Match</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs & Occasion Pills */}
      <div className="space-y-3">
        {/* Category Tabs */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => setSelectedCategory('')}
            className={`px-4 py-2 rounded-full text-xs font-semibold transition-all shrink-0 ${
              selectedCategory === ''
                ? 'bg-[#1B1F3B] text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            All Collections
          </button>
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.slug)}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all shrink-0 ${
                selectedCategory === cat.slug
                  ? 'bg-[#1B1F3B] text-white shadow-xs'
                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {cat.name}
            </button>
          ))}
        </div>

        {/* Occasion & Sort Filters */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="flex items-center gap-2 overflow-x-auto">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Occasion:</span>
            {['', 'work', 'dinner', 'party', 'casual', 'formal'].map((occ) => (
              <button
                key={occ || 'all'}
                onClick={() => setSelectedOccasion(occ)}
                className={`px-3 py-1 rounded-lg text-xs font-medium capitalize transition-all ${
                  selectedOccasion === occ
                    ? 'bg-[#FDF8EE] text-[#C5A059] font-bold border border-[#C5A059]'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {occ || 'Any Occasion'}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-400">Sort by:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="text-xs font-semibold bg-white border border-slate-200 rounded-xl px-3 py-1.5 focus:outline-none focus:border-[#C5A059]"
            >
              <option value="recommended">CONFIT Recommended (Relevance)</option>
              <option value="price_asc">Price: Low to High</option>
              <option value="price_desc">Price: High to Low</option>
              <option value="rating">Customer Rating</option>
              <option value="newest">Newest Arrivals</option>
            </select>
          </div>
        </div>
      </div>

      {/* Product Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : products.length === 0 ? (
        <EmptyState
          title="No products matched your filters"
          description="Try broadening your search query or selecting a different occasion category."
          actionText="Reset Filters"
          onAction={() => {
            setSelectedCategory('');
            setSelectedOccasion('');
            setSearchQuery('');
          }}
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {products.map((p) => (
            <div
              key={p.id}
              className="bg-white rounded-3xl border border-slate-200/80 p-3.5 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="relative h-72 rounded-2xl overflow-hidden bg-slate-100 mb-3">
                  <img
                    src={p.thumbnail_url}
                    alt={p.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
                    onClick={() => navigate(`/product/${p.slug}`)}
                  />
                  <div className="absolute top-2.5 left-2.5 flex flex-col gap-1">
                    <FitScoreBadge score={p.style_compatibility_score} verdict="Color Match" />
                  </div>

                  <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5">
                    <button
                      onClick={() => openRuler(p)}
                      className="p-2 rounded-full bg-white/90 hover:bg-white text-slate-800 shadow-sm backdrop-blur-xs transition-all"
                      title="No-Photo Measurement Fit"
                    >
                      <RulerIcon size={14} color="#1B1F3B" />
                    </button>
                    <button
                      onClick={() => openTryOn(p)}
                      className="p-2 rounded-full bg-[#1B1F3B]/90 hover:bg-[#C5A059] text-white hover:text-slate-950 shadow-sm backdrop-blur-xs transition-all"
                      title="Virtual Try-On"
                    >
                      <TryOnIcon size={14} color="currentColor" />
                    </button>
                  </div>
                </div>

                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  {p.brand_name}
                </span>
                <h3
                  onClick={() => navigate(`/product/${p.slug}`)}
                  className="font-serif text-sm font-bold text-[#1B1F3B] line-clamp-1 hover:text-[#C5A059] cursor-pointer mt-0.5"
                >
                  {p.title}
                </h3>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-sm font-bold text-[#1B1F3B]">${p.base_price}</span>
                  <span className="text-xs text-slate-500 font-light">{p.color_family}</span>
                </div>
                <div className="mt-2">
                  <BNPLBadge price={p.base_price} provider="Tabby" />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 mt-3 flex items-center gap-2">
                <button
                  onClick={async () => {
                    const sku = p.skus?.[0];
                    if (sku) {
                      await addItem(sku.id, { id: p.id, title: p.title, category: p.category_name, color: p.color_family });
                    }
                  }}
                  className="flex-1 py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all shadow-2xs flex items-center justify-center gap-1.5"
                >
                  <BagIcon size={14} color="#FFFFFF" />
                  <span>Add to Bag</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
