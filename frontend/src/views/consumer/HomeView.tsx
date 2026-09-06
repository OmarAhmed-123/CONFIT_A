import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  SparkleIcon,
  OutfitBuilderIcon,
  TryOnIcon,
  FlameIcon,
  BagIcon,
  RulerIcon,
  ShieldIcon,
  BopisIcon,
  HeartIcon,
} from '../../components/icons/ConfitIcons';
import { useUIStore } from '../../stores/uiStore';
import { useCatalogViewModel } from '../../viewmodels/useCatalogViewModel';
import { FitScoreBadge, BNPLBadge, SkeletonCard } from '../../components/common/CommonComponents';
import { useCartStore } from '../../stores/cartStore';
import { CircularGallery, type GalleryItem } from '../../components/ui/circular-gallery';
import { CardStackShowcase } from '../../components/showcase/DesignShowcases';


const editorialGalleryData: GalleryItem[] = [
  {
    common: 'Tailored power suit',
    binomial: 'Executive wool tailoring',
    photo: {
      url: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80',
      text: 'person wearing a tailored suit in an editorial setting',
      pos: '50% 35%',
      by: 'Unsplash',
    },
  },
  {
    common: 'Champagne evening gown',
    binomial: 'Occasion-ready silk styling',
    photo: {
      url: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80',
      text: 'champagne evening dress on a model',
      pos: '50% 30%',
      by: 'Tamara Bellis',
    },
  },
  {
    common: 'Minimal capsule layers',
    binomial: 'Modern essentials wardrobe',
    photo: {
      url: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80',
      text: 'minimal wardrobe layers on a model',
      pos: '50% 40%',
      by: 'Hunters Race',
    },
  },
  {
    common: 'Streetwear utility edit',
    binomial: 'Casual smart outfit formula',
    photo: {
      url: 'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=80',
      text: 'fashion model wearing casual streetwear',
      pos: '50% 28%',
      by: 'Apostolos Vamvouras',
    },
  },
  {
    common: 'Runway black statement',
    binomial: 'Premium monochrome look',
    photo: {
      url: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?w=900&auto=format&fit=crop&q=80',
      text: 'woman in black fashion outfit posing outdoors',
      pos: '50% 20%',
      by: 'Laura Chouette',
    },
  },
  {
    common: 'Soft neutral tailoring',
    binomial: 'Quiet luxury daywear',
    photo: {
      url: 'https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=900&auto=format&fit=crop&q=80',
      text: 'neutral fashion outfit in soft daylight',
      pos: '50% 35%',
      by: 'Brooke Cagle',
    },
  },
  {
    common: 'Weekend denim uniform',
    binomial: 'Wardrobe foundation look',
    photo: {
      url: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=900&auto=format&fit=crop&q=80',
      text: 'fashion portrait with denim styling',
      pos: '50% 30%',
      by: 'Tamara Bellis',
    },
  },
  {
    common: 'Resort linen palette',
    binomial: 'Warm-weather capsule styling',
    photo: {
      url: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80',
      text: 'editorial model in resort-inspired fashion',
      pos: '50% 30%',
      by: 'Clem Onojeghuo',
    },
  },
];

export const HomeView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { openStylist, openTryOn, openRuler, openVisualSearch } = useUIStore();
  const { products, isLoading } = useCatalogViewModel();
  const { addItem } = useCartStore();

  const brandShowcase = [
    {
      name: 'Massimo Dutti',
      origin: 'Barcelona / Italian Fabrics',
      aesthetic: 'Quiet Luxury & Tailored Architecture',
      slug: 'massimo-dutti',
      image: 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600&auto=format&fit=crop&q=80',
      badge: '100% Virgin Wool & Cashmere',
    },
    {
      name: 'COS',
      origin: 'London / Modern Classics',
      aesthetic: 'Sculptural Minimalism & Organic Poplin',
      slug: 'cos',
      image: 'https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=600&auto=format&fit=crop&q=80',
      badge: 'Sustainable Organic Cotton',
    },
    {
      name: 'Reiss',
      origin: 'London / Heritage Modern',
      aesthetic: 'Evening Glamour & Mulberry Silks',
      slug: 'reiss',
      image: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600&auto=format&fit=crop&q=80',
      badge: 'Pure Mulberry Silk',
    },
    {
      name: 'Arket',
      origin: 'Stockholm / Nordic Essentials',
      aesthetic: 'Durable Foundations & Structured Linens',
      slug: 'arket',
      image: 'https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=600&auto=format&fit=crop&q=80',
      badge: 'Nordic Circular Tailoring',
    },
  ];

  const occasionCards = [
    {
      title: t('home.occasion_wedding'),
      tag: 'wedding',
      img: 'https://images.unsplash.com/photo-1519741497674-611481863552?w=700&auto=format&fit=crop&q=80',
      desc: 'Champagne Silk Gowns & Tuxedo Tailoring',
      palette: ['#D4AF37', '#111111', '#FAF9F6'],
    },
    {
      title: t('home.occasion_work'),
      tag: 'work',
      img: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80',
      desc: 'Executive Virgin Wool Double-Breasted Layers',
      palette: ['#1B1F3B', '#FAF9F6', '#64748B'],
    },
    {
      title: t('home.occasion_party'),
      tag: 'party',
      img: 'https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80',
      desc: 'Fluid Cowl Necklines & Strappy Metallic Heels',
      palette: ['#D4AF37', '#C5A059', '#1B1F3B'],
    },
    {
      title: t('home.occasion_casual'),
      tag: 'casual',
      img: 'https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=700&auto=format&fit=crop&q=80',
      desc: 'Relaxed Organic Poplin & Tapered Chinos',
      palette: ['#FAF9F6', '#D8C7B5', '#1B1F3B'],
    },
  ];

  return (
    <div className="space-y-16 sm:space-y-24 pb-24">
      {/* 1. Hero Luxury Editorial Banner */}
      <section className="relative overflow-hidden rounded-3xl sm:rounded-[36px] bg-gradient-to-br from-[#0C0E1E] via-[#1B1F3B] to-[#0A0C18] text-white p-6 sm:p-12 lg:p-20 shadow-2xl border border-slate-800/80">
        <div className="absolute -top-32 -right-32 w-[500px] h-[500px] bg-[#C5A059]/15 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-[400px] h-[400px] bg-[#3D5296]/20 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-2xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#C5A059]/15 border border-[#C5A059]/30 text-[#E2BF70] text-[11px] font-semibold uppercase tracking-widest backdrop-blur-md">
            <SparkleIcon size={13} color="#E2BF70" />
            <span>CONFIT Fashion Tech · Where Style Meets Character</span>
          </div>

          <h1 className="font-serif text-3xl sm:text-5xl lg:text-6xl font-bold leading-[1.1] text-white tracking-tight">
            {t('home.hero_title')}
          </h1>

          <p className="text-xs sm:text-sm sm:leading-relaxed text-slate-300 font-light max-w-xl">
            {t('home.hero_subtitle')}
          </p>

          {/* Core Action CTAs */}
          <div className="pt-2 flex flex-wrap items-center gap-3 sm:gap-4">
            <button
              onClick={() => openStylist()}
              className="px-6 py-3.5 rounded-2xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs sm:text-sm tracking-wide shadow-lg hover:shadow-[#C5A059]/20 transition-all flex items-center gap-2 active:scale-98"
            >
              <SparkleIcon size={16} color="#0C0E1E" />
              <span>{t('home.cta_find_style')}</span>
            </button>

            <button
              onClick={() => navigate('/tryon-studio')}
              className="px-6 py-3.5 rounded-2xl bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold text-xs sm:text-sm backdrop-blur-md transition-all flex items-center gap-2 active:scale-98"
            >
              <TryOnIcon size={16} color="#FFFFFF" isAi={true} />
              <span>{t('home.cta_try_on')}</span>
            </button>

            <button
              onClick={() => navigate('/builder')}
              className="px-5 py-3.5 rounded-2xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700 text-slate-200 font-semibold text-xs sm:text-sm transition-all flex items-center gap-2"
            >
              <OutfitBuilderIcon size={16} color="#C5A059" />
              <span>{t('home.cta_build_outfit')}</span>
            </button>
          </div>
        </div>
      </section>



      {/* 2. Scroll-Driven 3D Editorial Gallery */}
      <section className="relative -mx-4 overflow-hidden rounded-[36px] border border-[#C5A059]/25 bg-gradient-to-b from-[#FAF9F6] via-white to-[#F0F2F8] py-10 shadow-2xs sm:-mx-6 lg:-mx-8">
        <div className="relative z-10 mx-auto mb-6 max-w-2xl px-6 text-center">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[#C5A059]">
            Scroll-Activated Lookbook
          </span>
          <h2 className="mt-2 font-serif text-3xl font-bold text-[#1B1F3B] sm:text-4xl">
            Rotate through CONFIT editorial styling stories
          </h2>
          <p className="mt-3 text-sm font-light leading-relaxed text-slate-500">
            A shadcn-compatible circular gallery component showcases premium outfit moods while the page scroll controls the 3D rotation.
          </p>
        </div>
        <div className="relative h-[520px] overflow-hidden sm:h-[620px]">
          <CircularGallery
            items={editorialGalleryData}
            radius={typeof window !== 'undefined' && window.innerWidth < 768 ? 360 : 560}
            autoRotateSpeed={0.015}
          />
        </div>
      </section>

      <CardStackShowcase
        tone="consumer"
        eyebrow="Swipeable Style Stack"
        title="Explore curated fashion stories in a tactile animated stack"
        description="Drag, tap, or use keyboard arrows to browse real editorial outfit moods before moving into brand collections and product cards."
      />

      {/* 2. Luxury Brand Pavilion */}
      <section className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 border-b border-slate-200/80 pb-4">
          <div>
            <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-widest block">
              Curated European & Scandinavian Houses
            </span>
            <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
              Multi-Brand Boutique Partners
            </h2>
          </div>
          <Link
            to="/discover"
            className="text-xs font-semibold text-[#1B1F3B] hover:text-[#C5A059] transition-colors flex items-center gap-1"
          >
            <span>Explore All 4 Brand Catalogs</span>
            <span>→</span>
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {brandShowcase.map((brand) => (
            <div
              key={brand.slug}
              onClick={() => navigate(`/discover`)}
              className="group relative rounded-3xl overflow-hidden bg-white border border-slate-200/80 shadow-2xs hover:shadow-lg transition-all duration-300 cursor-pointer flex flex-col justify-between p-5"
            >
              <div className="relative h-44 rounded-2xl overflow-hidden bg-slate-100 mb-4">
                <img
                  src={brand.image}
                  alt={brand.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
                <span className="absolute top-2.5 right-2.5 px-2.5 py-1 rounded-full bg-slate-950/80 backdrop-blur-md text-[9px] font-medium text-[#C5A059] border border-[#C5A059]/30">
                  {brand.badge}
                </span>
              </div>

              <div>
                <h3 className="font-serif text-base font-bold text-[#1B1F3B] group-hover:text-[#C5A059] transition-colors">
                  {brand.name}
                </h3>
                <span className="text-[11px] text-slate-400 font-light block">{brand.origin}</span>
                <p className="text-xs text-slate-600 font-light mt-1.5 line-clamp-2">{brand.aesthetic}</p>
              </div>

              <div className="pt-4 border-t border-slate-100 mt-4 flex items-center justify-between text-xs font-semibold text-[#1B1F3B] group-hover:text-[#C5A059]">
                <span>Browse Collection</span>
                <span>→</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 3. Today's AI Curated Daily Ensembles (Grounded & Multi-Brand) */}
      <section className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 border-b border-slate-200/80 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <SparkleIcon size={20} color="#C5A059" />
              <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
                {t('home.todays_picks')}
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
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
          {/* Ensemble 1: Executive Tailored */}
          <div className="bg-white rounded-3xl border border-slate-200/80 shadow-2xs p-6 flex flex-col justify-between group hover:shadow-md transition-all">
            <div>
              <div className="flex justify-between items-start mb-3">
                <div>
                  <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                    Executive Metropolitan Look
                  </span>
                  <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                    Italian Virgin Wool & Organic Poplin
                  </h3>
                </div>
                <FitScoreBadge score={98} verdict="Optimal Proportions" />
              </div>
              <p className="text-xs text-slate-500 mb-4 font-light">
                Tailored Italian wool double-breasted blazer by Massimo Dutti paired with crisp organic poplin by COS and pleated wool trousers.
              </p>

              <div className="grid grid-cols-3 gap-3">
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80"
                    alt="Blazer"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">Massimo Dutti</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500&auto=format&fit=crop&q=80"
                    alt="Shirt"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">COS</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=500&auto=format&fit=crop&q=80"
                    alt="Trousers"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">Massimo Dutti</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-5 border-t border-slate-100 mt-6">
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Total Look (3 Pieces)</span>
                <span className="text-base font-bold text-[#1B1F3B]">$549.00</span>
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

          {/* Ensemble 2: Evening Silk */}
          <div className="bg-white rounded-3xl border border-slate-200/80 shadow-2xs p-6 flex flex-col justify-between group hover:shadow-md transition-all">
            <div>
              <div className="flex justify-between items-start mb-3">
                <div>
                  <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider">
                    Contemporary Gala & Evening
                  </span>
                  <h3 className="font-serif text-lg font-bold text-[#1B1F3B]">
                    Silk Slip Column & Metallic Accessories
                  </h3>
                </div>
                <FitScoreBadge score={97} verdict="Fluid Harmony" />
              </div>
              <p className="text-xs text-slate-500 mb-4 font-light">
                Mulberry silk champagne slip column maxi dress by Reiss with metallic leather heeled sandals and box clutch.
              </p>

              <div className="grid grid-cols-3 gap-3">
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=500&auto=format&fit=crop&q=80"
                    alt="Dress"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">Reiss</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=500&auto=format&fit=crop&q=80"
                    alt="Sandals"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">Reiss</span>
                </div>
                <div className="h-44 rounded-2xl overflow-hidden bg-slate-100 relative">
                  <img
                    src="https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=500&auto=format&fit=crop&q=80"
                    alt="Clutch"
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">Reiss</span>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-5 border-t border-slate-100 mt-6">
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Total Look (3 Pieces)</span>
                <span className="text-base font-bold text-[#1B1F3B]">$770.00</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => openTryOn(products[4] || products[0])}
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

      {/* 4. Occasion Portals */}
      <section className="space-y-6">
        <div className="flex items-center justify-between border-b border-slate-200/80 pb-4">
          <div>
            <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
              {t('home.occasions')}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
              Tap any occasion to activate instant grounded stylist recommendations
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {occasionCards.map((occ) => (
            <button
              key={occ.tag}
              onClick={() => openStylist(occ.title)}
              className="group relative h-80 rounded-3xl overflow-hidden shadow-2xs hover:shadow-xl transition-all duration-300 text-left border border-slate-200/60"
            >
              <img
                src={occ.img}
                alt={occ.title}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 brightness-75 group-hover:brightness-90"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/35 to-transparent p-6 flex flex-col justify-end">
                <span className="text-[10px] font-bold text-[#C5A059] uppercase tracking-wider mb-1 flex items-center gap-1">
                  <SparkleIcon size={12} color="#C5A059" />
                  <span>Instant AI Stylist</span>
                </span>
                <h4 className="font-serif text-xl font-bold text-white mb-1">{occ.title}</h4>
                <p className="text-xs text-slate-300 line-clamp-1 font-light mb-2">{occ.desc}</p>
                <div className="flex gap-1.5 mb-3">
                  {occ.palette.map((c, idx) => (
                    <span
                      key={idx}
                      className="w-3 h-3 rounded-full border border-white/40"
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-1 text-xs font-semibold text-[#C5A059] group-hover:translate-x-1 transition-transform">
                  <span>Style this occasion →</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* 5. Trending Catalog Silhouettes */}
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
              High-confidence garments available across regional boutique stores
            </p>
          </div>
          <button
            onClick={() => navigate('/discover')}
            className="text-xs font-bold text-[#1B1F3B] hover:text-[#C5A059] transition-colors"
          >
            View All Catalog{isLoading ? '' : ` (${products.length})`} →
          </button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
            {products.slice(0, 4).map((p) => (
              <div
                key={p.id}
                className="bg-white rounded-3xl border border-slate-200/80 p-3 sm:p-4 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="relative aspect-[3/4] rounded-2xl overflow-hidden bg-slate-100 mb-3">
                    <img
                      src={p.thumbnail_url}
                      alt={p.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
                      onClick={() => navigate(`/product/${p.slug}`)}
                    />
                    <div className="absolute top-2 left-2 flex flex-col gap-1">
                      <FitScoreBadge score={p.style_compatibility_score} verdict="Color Harmony" />
                    </div>

                    <div className="absolute bottom-2 right-2 flex items-center gap-1.5">
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
                  <h4
                    onClick={() => navigate(`/product/${p.slug}`)}
                    className="font-serif text-xs sm:text-sm font-bold text-[#1B1F3B] line-clamp-1 hover:text-[#C5A059] cursor-pointer mt-0.5"
                  >
                    {p.title}
                  </h4>
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
                    className="w-full py-2.5 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white text-xs font-semibold text-slate-800 transition-all flex items-center justify-center gap-1.5"
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

      {/* 6. Precision Luxury Technology Reassurance */}
      <section className="rounded-3xl bg-[#FAF9F6] border border-[#C5A059]/30 p-6 sm:p-10 shadow-2xs">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 text-center sm:text-left">
          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <SparkleIcon size={20} color="#C5A059" />
            </div>
            <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">On-Device Biometric Vision</h4>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              Camera frames are analyzed locally in browser memory with zero permanent server photo retention.
            </p>
          </div>

          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <BopisIcon size={20} color="#C5A059" />
            </div>
            <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">2-Hour BOPIS Boutique Pickup</h4>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              Collect your tailored garments in 2 hours with dedicated fitting suites in Dubai & Riyadh.
            </p>
          </div>

          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <ShieldIcon size={20} color="#C5A059" />
            </div>
            <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">30-Day Zero-Fee Returns</h4>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              Virtual try-on reduces sizing mismatch by 71%. If not fully satisfied, enjoy instant courier collection.
            </p>
          </div>

          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <BagIcon size={20} color="#C5A059" />
            </div>
            <h4 className="font-serif text-sm font-bold text-[#1B1F3B]">0% Interest BNPL Payments</h4>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              Split any luxury ensemble into 4 monthly payments with Tabby or Tamara at zero added cost.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};
