import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  SparkleIcon,
  OutfitBuilderIcon,
  TryOnIcon,
  FlameIcon,
  BagIcon,
  RulerIcon,
} from '../../components/icons/ConfitIcons';
import { useUIStore } from '../../stores/uiStore';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { FitScoreBadge, BNPLBadge, SkeletonCard } from '../../components/common/CommonComponents';
import { useCartStore } from '../../stores/cartStore';

export const HomeView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { openStylist, openTryOn, openRuler } = useUIStore();
  const { products, isLoading } = useCatalogViewModel();
  const { addItem } = useCartStore();

  const occasionCards = [
    { title: t('home.occasion_work'), tag: 'work', img: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=600&auto=format&fit=crop&q=80', desc: 'Modern Tailoring & Clean Lines' },
    { title: t('home.occasion_party'), tag: 'party', img: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600&auto=format&fit=crop&q=80', desc: 'Silks, Textures & Evening Luster' },
    { title: t('home.occasion_wedding'), tag: 'wedding', img: 'https://images.unsplash.com/photo-1519741497674-611481863552?w=600&auto=format&fit=crop&q=80', desc: 'Formal Refinement & Elegance' },
    { title: t('home.occasion_casual'), tag: 'casual', img: 'https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=600&auto=format&fit=crop&q=80', desc: 'Relaxed Cashmere & Neutral Chinos' },
  ];

  return (
    <div className="space-y-16 pb-24">
      {/* 1. Hero Luxury Banner with 3 Quick Action CTAs */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#0C0E1E] via-[#1B1F3B] to-[#14182E] text-white p-8 sm:p-14 lg:p-20 shadow-xl border border-slate-800/80">
        <div className="absolute -top-24 -right-24 w-96 h-96 bg-[#C5A059]/15 rounded-full blur-3xl pointer-events-none"></div>
        <div className="relative z-10 max-w-2xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#C5A059]/20 border border-[#C5A059]/40 text-[#E2BF70] text-xs font-semibold uppercase tracking-wider backdrop-blur-sm">
            <SparkleIcon size={14} color="#E2BF70" />
            <span>AI-Driven Precision Fashion Studio</span>
          </div>

          <h1 className="font-serif text-3xl sm:text-5xl lg:text-6xl font-bold leading-[1.12] text-white tracking-tight">
            {t('home.hero_title')}
          </h1>

          <p className="text-sm sm:text-base text-slate-300 leading-relaxed font-light">
            {t('home.hero_subtitle')}
          </p>

          {/* 3 Core Quick Action CTAs (PDF Spec) */}
          <div className="pt-2 flex flex-wrap gap-3 sm:gap-4">
            <button
              onClick={() => navigate('/builder')}
              className="px-6 py-3.5 rounded-xl bg-[#C5A059] hover:bg-[#A37E44] text-slate-950 font-bold text-xs sm:text-sm shadow-md hover:scale-[1.02] active:scale-98 transition-all flex items-center gap-2"
            >
              <OutfitBuilderIcon size={18} color="#0C0E1E" />
              <span>{t('home.cta_build_outfit')}</span>
            </button>

            <button
              onClick={() => navigate('/tryon-studio')}
              className="px-6 py-3.5 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold text-xs sm:text-sm backdrop-blur-md transition-all flex items-center gap-2"
            >
              <TryOnIcon size={18} color="#FFFFFF" isAi={true} />
              <span>{t('home.cta_try_on')}</span>
            </button>

            <button
              onClick={() => openStylist()}
              className="px-6 py-3.5 rounded-xl bg-white text-[#1B1F3B] hover:bg-slate-100 font-bold text-xs sm:text-sm shadow-md transition-all flex items-center gap-2"
            >
              <SparkleIcon size={18} color="#C5A059" />
              <span>{t('home.cta_find_style')}</span>
            </button>
          </div>
        </div>
      </section>

      {/* 2. Today's Style Picks (AI Curated Daily Outfits) */}
      <section className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 border-b border-slate-200/80 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <SparkleIcon size={20} color="#C5A059" />
              <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
                {t('home.todays_picks')}
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-1 font-light">
              {t('home.todays_picks_desc')}
            </p>
          </div>
          <button
            onClick={() => openStylist()}
            className="text-xs font-bold text-[#C5A059] hover:underline flex items-center gap-1"
          >
            <span>Ask Stylist for Alternatives</span>
            <span>→</span>
          </button>
        </div>

        {/* Curated Ensemble Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Ensemble 1 */}
          <div className="bg-white rounded-3xl border border-slate-200/80 shadow-sm p-6 flex flex-col justify-between group hover:shadow-md transition-all">
            <div>
              <div className="flex justify-between items-start mb-3">
                <div>
                  <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                    Executive Morning
                  </span>
                  <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                    The Italian Wool & Linen Layer
                  </h3>
                </div>
                <FitScoreBadge score={98} verdict="Optimal Proportions" />
              </div>
              <p className="text-xs text-slate-500 mb-4 font-light">
                Structured double-breasted navy blazer with crisp organic poplin and tailored sand chinos.
              </p>

              <div className="grid grid-cols-3 gap-3">
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80"
                    alt="Blazer"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/60 text-[9px] text-white">Massimo Dutti</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500&auto=format&fit=crop&q=80"
                    alt="Shirt"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/60 text-[9px] text-white">COS</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=500&auto=format&fit=crop&q=80"
                    alt="Chinos"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/60 text-[9px] text-white">Massimo Dutti</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-5 border-t border-slate-100 mt-6">
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Total Ensemble</span>
                <span className="text-base font-bold text-[#1B1F3B]">$529.00</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => openTryOn(products[0])}
                  className="px-4 py-2 rounded-xl border border-slate-200 hover:border-[#1B1F3B] text-xs font-semibold text-slate-700 transition-all flex items-center gap-1.5"
                >
                  <TryOnIcon size={14} color="#1B1F3B" />
                  <span>Try On Look</span>
                </button>
                <button
                  onClick={() => navigate('/builder')}
                  className="px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-2xs"
                >
                  <OutfitBuilderIcon size={14} color="#FFFFFF" />
                  <span>Open in Canvas</span>
                </button>
              </div>
            </div>
          </div>

          {/* Ensemble 2 */}
          <div className="bg-white rounded-3xl border border-slate-200/80 shadow-sm p-6 flex flex-col justify-between group hover:shadow-md transition-all">
            <div>
              <div className="flex justify-between items-start mb-3">
                <div>
                  <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                    Contemporary Evening
                  </span>
                  <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                    Silk Drape Column & Tailored Outerwear
                  </h3>
                </div>
                <FitScoreBadge score={96} verdict="Fluid Harmony" />
              </div>
              <p className="text-xs text-slate-500 mb-4 font-light">
                Mulberry silk champagne slip dress paired with structured wool tailoring and calfskin loafers.
              </p>

              <div className="grid grid-cols-3 gap-3">
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500&auto=format&fit=crop&q=80"
                    alt="Dress"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/60 text-[9px] text-white">Reiss</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80"
                    alt="Blazer"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/60 text-[9px] text-white">Massimo Dutti</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=500&auto=format&fit=crop&q=80"
                    alt="Loafers"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/60 text-[9px] text-white">Arket</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-5 border-t border-slate-100 mt-6">
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Total Ensemble</span>
                <span className="text-base font-bold text-[#1B1F3B]">$849.00</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => openTryOn(products[3] || products[0])}
                  className="px-4 py-2 rounded-xl border border-slate-200 hover:border-[#1B1F3B] text-xs font-semibold text-slate-700 transition-all flex items-center gap-1.5"
                >
                  <TryOnIcon size={14} color="#1B1F3B" />
                  <span>Try On Look</span>
                </button>
                <button
                  onClick={() => navigate('/builder')}
                  className="px-4 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-2xs"
                >
                  <OutfitBuilderIcon size={14} color="#FFFFFF" />
                  <span>Open in Canvas</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Occasion Shortcuts */}
      <section className="space-y-6">
        <div className="flex items-center justify-between border-b border-slate-200/80 pb-4">
          <div>
            <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
              {t('home.occasions')}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
              Tap any occasion to instantly generate complete shoppable styling options
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {occasionCards.map((occ) => (
            <button
              key={occ.tag}
              onClick={() => openStylist(occ.title)}
              className="group relative h-72 rounded-3xl overflow-hidden shadow-2xs hover:shadow-lg transition-all duration-300 text-left border border-slate-200/60"
            >
              <img
                src={occ.img}
                alt={occ.title}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 brightness-75 group-hover:brightness-90"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-transparent p-6 flex flex-col justify-end">
                <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider mb-1 flex items-center gap-1">
                  <SparkleIcon size={12} color="#C5A059" />
                  <span>Instant AI Stylist</span>
                </span>
                <h4 className="font-serif text-xl font-bold text-white mb-1">{occ.title}</h4>
                <p className="text-xs text-slate-300 line-clamp-1 font-light">{occ.desc}</p>
                <div className="mt-3 flex items-center gap-1 text-xs font-semibold text-[#C5A059] group-hover:translate-x-1 transition-transform">
                  <span>Style this occasion →</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* 4. Trending Silhouettes & New Drops from Brands */}
      <section className="space-y-6">
        <div className="flex items-center justify-between border-b border-slate-200/80 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <FlameIcon size={22} color="#C5A059" />
              <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
                {t('home.trending_title')}
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
              High-confidence silhouettes matching your style profile
            </p>
          </div>
          <button
            onClick={() => navigate('/discover')}
            className="text-xs font-bold text-[#1B1F3B] hover:text-[#C5A059] transition-colors"
          >
            View All Catalog ({products.length}) →
          </button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {products.slice(0, 4).map((p) => (
              <div
                key={p.id}
                className="bg-white rounded-3xl border border-slate-200/80 p-3.5 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="relative h-64 rounded-2xl overflow-hidden bg-slate-100 mb-3">
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
                        title="No-Photo Fit Sizing"
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
                  <h4
                    onClick={() => navigate(`/product/${p.slug}`)}
                    className="font-serif text-sm font-bold text-[#1B1F3B] line-clamp-1 hover:text-[#C5A059] cursor-pointer"
                  >
                    {p.title}
                  </h4>
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
                    className="flex-1 py-2.5 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white text-xs font-semibold text-slate-800 transition-all flex items-center justify-center gap-1.5"
                  >
                    <BagIcon size={14} color="currentColor" />
                    <span>Add to Bag</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
