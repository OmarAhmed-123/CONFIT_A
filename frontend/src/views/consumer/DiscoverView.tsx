import { CardStackShowcase } from '../../components/showcase/DesignShowcases';
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { useUIStore } from '../../stores/uiStore';
import { useCartStore } from '../../stores/cartStore';
import { catalogService } from '../../services/apiServices';
import { AutocompleteSuggestion } from '../../models';
import {
  TryOnIcon,
  RulerIcon,
  BagIcon,
  VisualSearchIcon,
  SparkleIcon,
  HeartIcon,
} from '../../components/icons/ConfitIcons';
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
  const [selectedColor, setSelectedColor] = useState<string>('');
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

  const toggleWishlist = (productId: number) => {
    setWishlist((prev) =>
      prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId]
    );
  };

  const filteredProducts = products.filter((p) => {
    if (selectedColor && !p.color_family.toLowerCase().includes(selectedColor.toLowerCase())) {
      return false;
    }
    return true;
  });

  const colorSwatches = [
    { label: 'All', hex: 'transparent' },
    { label: 'Navy Blue', hex: '#1B1F3B' },
    { label: 'Midnight Black', hex: '#111111' },
    { label: 'Optic White', hex: '#FAF9F6' },
    { label: 'Champagne Gold', hex: '#D4AF37' },
    { label: 'Emerald Green', hex: '#2D4A3E' },
  ];

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
          <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-widest block">
            Luxury Multi-Brand Catalog
          </span>
          <h1 className="font-serif text-3xl font-bold text-[#1B1F3B] tracking-tight">
            {t('nav.style_discover')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
            Curated European tailoring, sculptural classics, and silk evening silhouettes.
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
                setTimeout(() => setShowSuggestions(false), 200);
              }}
              placeholder="Search blazers, oxford shirts, silk dresses..."
              className="w-full pl-4 pr-10 py-3 rounded-2xl border border-slate-200 text-xs focus:outline-none focus:border-[#C5A059] bg-white shadow-2xs placeholder:text-slate-400"
            />
            {searchQuery && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setShowSuggestions(false);
                }}
                className="absolute right-3 top-3 text-xs text-slate-400 hover:text-slate-700"
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
                      if (sug.type === 'product') {
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
                        <img src={sug.thumbnail_url} alt="" className="w-9 h-9 rounded-xl object-cover border border-slate-100" />
                      ) : (
                        <div className="w-9 h-9 rounded-xl bg-[#FDF8EE] text-[#C5A059] flex items-center justify-center font-bold text-xs">
                          {sug.type === 'brand' ? '🏷️' : '📁'}
                        </div>
                      )}
                      <div>
                        <span className="font-bold text-[#1B1F3B] block">{sug.title}</span>
                        {sug.subtitle && <span className="text-[10px] text-slate-400 font-light">{sug.subtitle}</span>}
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
            className="px-4 py-3 rounded-2xl bg-[#FDF8EE] hover:bg-[#C5A059] hover:text-white border border-[#C5A059]/40 text-[#C5A059] text-xs font-semibold shadow-2xs transition-all flex items-center gap-1.5 shrink-0"
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
            onClick={() => setSelectedCategory('')}
            className={`px-4 py-2.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
              selectedCategory === ''
                ? 'bg-[#1B1F3B] text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
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
                  ? 'bg-[#1B1F3B] text-white shadow-xs'
                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {cat.name}
            </button>
          ))}
        </div>

        {/* Color Palette & Occasion & Sort Filters */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          {/* Color Swatch Filters */}
          <div className="flex items-center gap-2 overflow-x-auto">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Palette:</span>
            {colorSwatches.map((col) => (
              <button
                key={col.label}
                onClick={() => setSelectedColor(col.label === 'All' ? '' : col.label)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-medium transition-all ${
                  (selectedColor === '' && col.label === 'All') || selectedColor === col.label
                    ? 'bg-[#1B1F3B] text-white'
                    : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                }`}
              >
                {col.hex !== 'transparent' && (
                  <span className="w-2.5 h-2.5 rounded-full border border-white/40" style={{ backgroundColor: col.hex }} />
                )}
                <span>{col.label}</span>
              </button>
            ))}
          </div>

          {/* Sort Selector */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-400">Sort by:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="text-xs font-semibold bg-white border border-slate-200 rounded-xl px-3 py-2 focus:outline-none focus:border-[#C5A059]"
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
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : filteredProducts.length === 0 ? (
        <EmptyState
          title="No luxury garments match your criteria"
          description="Try selecting a broader palette, clearing search terms, or exploring another collection."
          actionText="Reset All Filters"
          onAction={() => {
            setSelectedCategory('');
            setSelectedOccasion('');
            setSelectedColor('');
            setSearchQuery('');
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
                    <img
                      src={p.thumbnail_url}
                      alt={p.title}
                      loading="lazy"
                      decoding="async"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
                      onClick={() => navigate(`/product/${p.slug}`)}
                      onError={(e) => {
                        const target = e.currentTarget as HTMLImageElement;
                        if (!target.dataset.fallback) {
                          target.dataset.fallback = 'true';
                          target.src = `https://placehold.co/400x500/1B1F3B/FFFFFF?text=${encodeURIComponent(p.title.slice(0,20))}`;
                        }
                      }}
                    />
                    <div className="absolute top-2.5 left-2.5 flex flex-col gap-1">
                      <FitScoreBadge score={p.style_compatibility_score} verdict="Color Harmony" />
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
                    className="font-serif text-xs sm:text-sm font-bold text-[#1B1F3B] line-clamp-1 hover:text-[#C5A059] cursor-pointer mt-0.5"
                  >
                    {p.title}
                  </h3>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs sm:text-sm font-bold text-[#1B1F3B]">${p.base_price}</span>
                    <span className="text-[11px] text-slate-500 font-light truncate max-w-[80px]">{p.color_family}</span>
                  </div>
                  <div className="mt-1.5">
                    <BNPLBadge price={p.base_price} provider="Tabby" />
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-100 mt-3">
                  <button
                    onClick={async () => {
                      const sku = p.skus?.[0];
                      if (sku) {
                        await addItem(sku.id, { id: p.id, title: p.title, category: p.category_name, color: p.color_family });
                      }
                    }}
                    className="w-full py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all shadow-2xs flex items-center justify-center gap-1.5"
                  >
                    <BagIcon size={14} color="#FFFFFF" />
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
