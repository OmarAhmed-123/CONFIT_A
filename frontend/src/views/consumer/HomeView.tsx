import React from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
} from "../../components/icons/ConfitIcons";
import { useUIStore } from "../../stores/uiStore";
import { useCatalogViewModel } from "../../viewmodels/useCatalogViewModel";
import { useCapabilities } from "../../hooks/useCapabilities";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import {
  FitScoreBadge,
  BNPLBadge,
  SkeletonCard,
  EmptyState,
} from "../../components/common/CommonComponents";
import { HonestProductImage } from "../../components/common/HonestProductImage";
import { useCartStore } from "../../stores/cartStore";
import { resolvePurchasableSku } from "../../lib/catalogSku";
import { formatAmount, formatMoney, formatNumber } from "../../i18n/format";
import {
  CircularGallery,
  type GalleryItem,
} from "../../components/ui/circular-gallery";
import { CardStackShowcase } from "../../components/showcase/DesignShowcases";

const editorialGalleryData: GalleryItem[] = [
  {
    common: "Tailored power suit",
    binomial: "Executive wool tailoring",
    photo: {
      url: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80",
      text: "person wearing a tailored suit in an editorial setting",
      pos: "50% 35%",
      by: "Unsplash",
    },
  },
  {
    common: "Champagne evening gown",
    binomial: "Occasion-ready silk styling",
    photo: {
      url: "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=900&auto=format&fit=crop&q=80",
      text: "champagne evening dress on a model",
      pos: "50% 30%",
      by: "Tamara Bellis",
    },
  },
  {
    common: "Minimal capsule layers",
    binomial: "Modern essentials wardrobe",
    photo: {
      url: "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=900&auto=format&fit=crop&q=80",
      text: "minimal wardrobe layers on a model",
      pos: "50% 40%",
      by: "Hunters Race",
    },
  },
  {
    common: "Streetwear utility edit",
    binomial: "Casual smart outfit formula",
    photo: {
      url: "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=80",
      text: "fashion model wearing casual streetwear",
      pos: "50% 28%",
      by: "Apostolos Vamvouras",
    },
  },
  {
    common: "Runway black statement",
    binomial: "Premium monochrome look",
    photo: {
      url: "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=900&auto=format&fit=crop&q=80",
      text: "woman in black fashion outfit posing outdoors",
      pos: "50% 20%",
      by: "Laura Chouette",
    },
  },
  {
    common: "Soft neutral tailoring",
    binomial: "Quiet luxury daywear",
    photo: {
      url: "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=900&auto=format&fit=crop&q=80",
      text: "neutral fashion outfit in soft daylight",
      pos: "50% 35%",
      by: "Brooke Cagle",
    },
  },
  {
    common: "Weekend denim uniform",
    binomial: "Wardrobe foundation look",
    photo: {
      url: "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=900&auto=format&fit=crop&q=80",
      text: "fashion portrait with denim styling",
      pos: "50% 30%",
      by: "Tamara Bellis",
    },
  },
  {
    common: "Resort linen palette",
    binomial: "Warm-weather capsule styling",
    photo: {
      url: "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=900&auto=format&fit=crop&q=80",
      text: "editorial model in resort-inspired fashion",
      pos: "50% 30%",
      by: "Clem Onojeghuo",
    },
  },
];

export const HomeView: React.FC = () => {
  const { t, i18n } = useTranslation();
  // The active UI language drives number/currency formatting; the guide
  // option values sent to the stylist stay English tokens.
  const lang = i18n.resolvedLanguage ?? "en";
  const navigate = useNavigate();
  const { openStylist, openTryOn, openRuler, openVisualSearch, showToast } =
    useUIStore();
  const {
    products,
    isLoading,
    error: catalogError,
    refresh: refreshCatalog,
  } = useCatalogViewModel();
  // J-01: trust badges render what the platform can ACTUALLY do right now.
  const { capabilities } = useCapabilities();
  // Try-on CTAs (three on this page) bind to the live engine verdict, so none
  // of them promises a render the GPU cannot deliver (2026-09-22).
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);
  const { addItem } = useCartStore();
  const [guideOccasion, setGuideOccasion] = React.useState("Work");
  const [guideBudget, setGuideBudget] = React.useState("450");
  const [guidePalette, setGuidePalette] = React.useState("Navy / neutral");
  const [guideFit, setGuideFit] = React.useState("No preference");

  // `value` is the literal sent to the stylist request (`occasion=`); only the
  // label is localized. See startGuidedLook below.
  const guideOccasions = [
    { value: "Work", labelKey: "home.guide_occasion_work" },
    { value: "Wedding", labelKey: "home.guide_occasion_wedding" },
    { value: "Evening", labelKey: "home.guide_occasion_evening" },
    { value: "Travel", labelKey: "home.guide_occasion_travel" },
    { value: "Everyday", labelKey: "home.guide_occasion_everyday" },
    { value: "Exploring", labelKey: "home.guide_occasion_exploring" },
  ];
  const guideBudgets = ["300", "450", "650", "900"];
  // `value` is the key looked up by paletteMap below (-> structured catalog-colour
  // constraint), so it must not be translated.
  const guidePalettes = [
    { value: "Navy / neutral", labelKey: "home.guide_palette_navy_neutral" },
    { value: "Warm ivory", labelKey: "home.guide_palette_warm_ivory" },
    { value: "Black / metallic", labelKey: "home.guide_palette_black_metallic" },
    { value: "No preference", labelKey: "home.no_preference" },
  ];
  // `value` is the key looked up by fitMap below, so it must not be translated.
  const guideFits = [
    { value: "No preference", labelKey: "home.no_preference" },
    { value: "Tailored", labelKey: "home.guide_fit_tailored" },
    { value: "Relaxed", labelKey: "home.guide_fit_relaxed" },
    { value: "Modest coverage", labelKey: "home.guide_fit_modest" },
  ];

  const startGuidedLook = () => {
    const budget = Number(guideBudget);
    const paletteMap: Record<string, string | undefined> = {
      "Navy / neutral": "navy",
      "Warm ivory": "white",
      "Black / metallic": "black",
      "No preference": undefined,
    };
    const fitMap: Record<string, string | undefined> = {
      Tailored: "slim",
      Relaxed: "relaxed",
      "No preference": undefined,
      "Modest coverage": "regular",
    };
    openStylist({
      occasion: guideOccasion,
      budget: Number.isFinite(budget) ? budget : undefined,
      recommendation_constraints: {
        palette: paletteMap[guidePalette],
        preferred_fit: fitMap[guideFit],
      },
      prompt: `First-look request: occasion=${guideOccasion}; budget=${guideBudget ? `$${guideBudget}` : "open"}; palette=${guidePalette}; fit preference=${guideFit}. Recommend only real catalog products. Palette is sent as a structured catalog-color constraint; fit preference uses saved/requested sizes only when available.`,
    });
  };

  const addCatalogProductToBag = async (prod: any) => {
    try {
      const sku = await resolvePurchasableSku(prod);
      if (!sku) {
        showToast(
          "No purchasable size is available for this item right now.",
          "error",
        );
        return;
      }
      await addItem(sku.id, {
        id: prod.id,
        title: prod.title,
        category: prod.category_name,
        color: prod.color_family,
      });
      showToast("Added to bag", "success");
    } catch (err: any) {
      showToast(err?.message || "Could not add this item to bag.", "error");
    }
  };

  const brandShowcase = [
    {
      name: "Massimo Dutti",
      origin: "Barcelona / Italian Fabrics",
      aesthetic: "Quiet Luxury & Tailored Architecture",
      slug: "massimo-dutti",
      image:
        "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600&auto=format&fit=crop&q=80",
      badge: "100% Virgin Wool & Cashmere",
    },
    {
      name: "COS",
      origin: "London / Modern Classics",
      aesthetic: "Sculptural Minimalism & Organic Poplin",
      slug: "cos",
      image:
        "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=600&auto=format&fit=crop&q=80",
      badge: "Sustainable Organic Cotton",
    },
    {
      name: "Reiss",
      origin: "London / Heritage Modern",
      aesthetic: "Evening Glamour & Mulberry Silks",
      slug: "reiss",
      image:
        "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600&auto=format&fit=crop&q=80",
      badge: "Pure Mulberry Silk",
    },
    {
      name: "Arket",
      origin: "Stockholm / Nordic Essentials",
      aesthetic: "Durable Foundations & Structured Linens",
      slug: "arket",
      image:
        "https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=600&auto=format&fit=crop&q=80",
      badge: "Nordic Circular Tailoring",
    },
  ];

  const occasionCards = [
    {
      title: t("home.occasion_wedding"),
      tag: "wedding",
      img: "https://images.unsplash.com/photo-1519741497674-611481863552?w=700&auto=format&fit=crop&q=80",
      desc: "Champagne Silk Gowns & Tuxedo Tailoring",
      palette: ["#D4AF37", "#111111", "#FAF9F6"],
    },
    {
      title: t("home.occasion_work"),
      tag: "work",
      img: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80",
      desc: "Executive Virgin Wool Double-Breasted Layers",
      palette: ["#1B1F3B", "#FAF9F6", "#64748B"],
    },
    {
      title: t("home.occasion_party"),
      tag: "party",
      img: "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80",
      desc: "Fluid Cowl Necklines & Strappy Metallic Heels",
      palette: ["#D4AF37", "#C5A059", "#1B1F3B"],
    },
    {
      title: t("home.occasion_casual"),
      tag: "casual",
      img: "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=700&auto=format&fit=crop&q=80",
      desc: "Relaxed Organic Poplin & Tapered Chinos",
      palette: ["#FAF9F6", "#D8C7B5", "#1B1F3B"],
    },
  ];

  return (
    <div className="space-y-16 sm:space-y-24 pb-24">
      {/* 1. Hero Luxury Editorial Banner */}
      <section className="relative overflow-hidden rounded-3xl sm:rounded-[36px] bg-gradient-to-br from-[#0C0E1E] via-[#1B1F3B] to-[#0A0C18] text-white p-6 sm:p-12 lg:p-20 shadow-2xl border border-slate-800/80">
        <div className="absolute -top-32 -right-32 w-[500px] h-[500px] bg-[#C5A059]/15 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-[400px] h-[400px] bg-[#3D5296]/20 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="max-w-2xl space-y-6">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#C5A059]/15 border border-[#C5A059]/30 text-[#E2BF70] text-[11px] font-semibold uppercase tracking-widest backdrop-blur-md">
              <SparkleIcon size={13} color="#E2BF70" />
              <span>{t('home.hero_badge')}</span>
            </div>

            <h1 className="font-serif text-3xl sm:text-5xl lg:text-6xl font-bold leading-[1.1] text-white tracking-tight">
              {t("home.hero_title")}
            </h1>

            <p className="text-sm sm:leading-relaxed text-slate-200 font-light max-w-xl">
              {t('home.stylist_flow_cta_body')}
            </p>
            <p className="text-xs sm:text-sm sm:leading-relaxed text-slate-400 font-light max-w-xl">
              {t("home.hero_subtitle")}
            </p>

            {/* Guided CTA hierarchy */}
            <div className="pt-2 flex flex-wrap items-center gap-3 sm:gap-4">
              <button
                onClick={() =>
                  document
                    .getElementById("guided-first-look")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" })
                }
                className="px-7 py-3.5 rounded-2xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs sm:text-sm tracking-wide shadow-lg hover:shadow-[#C5A059]/20 transition-all flex items-center gap-2 active:scale-98"
              >
                <SparkleIcon size={16} color="#0C0E1E" />
                <span>{t('home.get_first_look')}</span>
              </button>

              <button
                onClick={() =>
                  // The studio still opens: it hosts the no-photo fit check too.
                  // Only the *label* changes, and only when a render is off the
                  // table, so the hero never advertises a broken capability.
                  navigate(tryOnKind === "render" ? "/tryon-studio" : "/fit-finder")
                }
                className="px-5 py-3.5 rounded-2xl bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold text-xs sm:text-sm backdrop-blur-md transition-all flex items-center gap-2 active:scale-98"
              >
                {tryOnKind === "render" ? (
                  <TryOnIcon size={16} color="#FFFFFF" isAi={true} />
                ) : (
                  <RulerIcon size={16} color="#FFFFFF" />
                )}
                <span>
                  {t(
                    tryOnKind === "render"
                      ? "tryon.cta_try_on"
                      : "tryon.cta_fit_check",
                  )}
                </span>
              </button>

              <Link
                to="/discover"
                className="px-4 py-3.5 rounded-2xl text-slate-300 hover:text-[#E2BF70] font-semibold text-xs sm:text-sm transition-all"
              >
                {t('home.shop_catalog_cta')}
              </Link>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 max-w-2xl pt-2">
              {[
                t('home.fact_no_account'),
                t('home.fact_photo_optional'),
                t('home.fact_privacy'),
              ].map((item) => (
                <div
                  key={item}
                  className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-[11px] text-slate-300 backdrop-blur"
                >
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="hidden lg:block">
            <div className="rounded-[32px] border border-[#C5A059]/30 bg-white/10 p-4 shadow-2xl backdrop-blur-xl">
              <div className="relative h-72 overflow-hidden rounded-3xl bg-slate-900">
                <img
                  src="https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80"
                  alt={t('home.example_look_alt')}
                  className="h-full w-full object-cover opacity-90"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />
                <div className="absolute bottom-0 left-0 right-0 p-5 text-white">
                  <span className="rounded-full bg-[#C5A059] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#0C0E1E]">
                    {t('home.example_result')}
                  </span>
                  <h2 className="mt-3 font-serif text-2xl font-bold">
                    {t('home.example_look_title')}
                  </h2>
                  <p className="mt-1 text-xs text-slate-200">
                    {t('home.example_look_body')}
                  </p>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-2xl bg-white/90 p-3 text-[#1B1F3B]">
                  <span className="block text-[10px] font-bold uppercase tracking-wider text-[#A37E44]">
                    {t('home.why_this_works')}
                  </span>
                  {t('home.why_this_works_body')}
                </div>
                <div className="rounded-2xl bg-[#0C0E1E]/90 p-3 text-white">
                  <span className="block text-[10px] font-bold uppercase tracking-wider text-[#C5A059]">
                    {t('home.fit_next_step')}
                  </span>
                  {t('home.fit_next_step_body')}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        id="guided-first-look"
        className="rounded-[32px] border border-[#C5A059]/25 bg-white p-6 shadow-2xs sm:p-8"
      >
        <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
              {t('home.guided_eyebrow')}
            </span>
            <h2 className="mt-2 font-serif text-3xl font-bold text-[#1B1F3B]">
              {t('home.guided_title')}
            </h2>
            <p className="mt-3 text-sm font-light leading-relaxed text-slate-500">
              {t('home.guided_body')}
            </p>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                {t('home.intent_question')}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {guideOccasions.map((occasion) => (
                  <button
                  key={occasion.value}
                    type="button"
                  aria-pressed={guideOccasion === occasion.value}
                  onClick={() => setGuideOccasion(occasion.value)}
                    className={`rounded-full px-3 py-2 text-xs font-semibold transition ${guideOccasion === occasion.value ? "bg-[#1B1F3B] text-white" : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}
                  >
                    {t(occasion.labelKey)}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <label className="space-y-2 text-xs font-semibold text-slate-600">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  {t('home.budget_guide')}
                </span>
                <select
                  value={guideBudget}
                  onChange={(event) => setGuideBudget(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm text-[#1B1F3B] focus:border-[#C5A059] focus:outline-none"
                >
                  {guideBudgets.map((budget) => (
                    <option key={budget} value={budget}>
                      {t('home.budget_under', { amount: formatAmount(Number(budget), lang, 0) })}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-2 text-xs font-semibold text-slate-600">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  {t('home.palette_preference')}
                </span>
                <select
                  value={guidePalette}
                  onChange={(event) => setGuidePalette(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm text-[#1B1F3B] focus:border-[#C5A059] focus:outline-none"
                >
                  {guidePalettes.map((palette) => (
                    <option key={palette.value} value={palette.value}>
                      {t(palette.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-2 text-xs font-semibold text-slate-600">
                <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  {t('home.fit_preference')}
                </span>
                <select
                  value={guideFit}
                  onChange={(event) => setGuideFit(event.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm text-[#1B1F3B] focus:border-[#C5A059] focus:outline-none"
                >
                  {guideFits.map((fit) => (
                    <option key={fit.value} value={fit.value}>
                      {t(fit.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={startGuidedLook}
                className="rounded-2xl bg-[#1B1F3B] px-5 py-3 text-xs font-bold text-white transition hover:bg-[#C5A059] hover:text-[#0C0E1E]"
              >
                {t('home.ask_stylist_cta')}
              </button>
              <p className="text-xs text-slate-500">
                {t('home.guest_friendly')}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Scroll-Driven 3D Editorial Gallery */}
      <section className="relative -mx-4 overflow-hidden rounded-[36px] border border-[#C5A059]/25 bg-gradient-to-b from-[#FAF9F6] via-white to-[#F0F2F8] py-10 shadow-2xs sm:-mx-6 lg:-mx-8">
        <div className="relative z-10 mx-auto mb-6 max-w-2xl px-6 text-center">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
            {t('home.lookbook_eyebrow')}
          </span>
          <h2 className="mt-2 font-serif text-3xl font-bold text-[#1B1F3B] sm:text-4xl">
            {t('home.lookbook_title')}
          </h2>
          <p className="mt-3 text-sm font-light leading-relaxed text-slate-500">
            {t('home.lookbook_body')}
          </p>
        </div>
        <div className="relative h-[520px] overflow-hidden sm:h-[620px]">
          <CircularGallery
            items={editorialGalleryData}
            radius={
              typeof window !== "undefined" && window.innerWidth < 768
                ? 360
                : 560
            }
            autoRotateSpeed={0.015}
          />
        </div>
      </section>

      <CardStackShowcase
        tone="consumer"
        eyebrow={t("home.stack_eyebrow")}
        title={t("home.stack_title")}
        description={t("home.stack_description")}
      />

      {/* 2. Luxury Brand Pavilion */}
      <section className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 border-b border-slate-200/80 pb-4">
          <div>
            <span className="text-[10px] font-bold text-[#7A5C28] uppercase tracking-widest block">
              {t('home.brands_eyebrow')}
            </span>
            <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
              {t('home.brands_title')}
            </h2>
          </div>
          <Link
            to="/discover"
            className="text-xs font-semibold text-[#1B1F3B] hover:text-[#C5A059] transition-colors flex items-center gap-1"
          >
            <span>{t('home.brands_cta')}</span>
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
                <span className="text-[11px] text-slate-500 font-light block">
                  {brand.origin}
                </span>
                <p className="text-xs text-slate-600 font-light mt-1.5 line-clamp-2">
                  {brand.aesthetic}
                </p>
              </div>

              <div className="pt-4 border-t border-slate-100 mt-4 flex items-center justify-between text-xs font-semibold text-[#1B1F3B] group-hover:text-[#C5A059]">
                <span>{t('home.browse_collection')}</span>
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
                {t("home.todays_picks")}
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
              {t("home.todays_picks_desc")}
            </p>
          </div>
          <button
            onClick={() => openStylist()}
            className="text-xs font-bold text-[#7A5C28] hover:underline flex items-center gap-1"
          >
            <span>{t('home.ask_stylist_alt')}</span>
            <span>→</span>
          </button>
        </div>

        {/* Honest-data remediation (2026-09-06 audit, J-01): this section
            previously rendered two HARDCODED ensembles ("Executive
            Metropolitan Look — $549.00", "Contemporary Gala — $770.00") that
            could contradict the live catalogue. It now renders REAL products
            from the same catalogue query Discover uses, with honest loading /
            empty / error states — no fabricated data. */}
        {isLoading && (
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5"
            aria-busy="true"
          >
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="bg-white rounded-3xl border border-slate-200/80 p-4 shadow-2xs animate-pulse space-y-3"
              >
                <div className="h-56 rounded-2xl bg-slate-100"></div>
                <div className="h-3 w-20 bg-slate-100 rounded"></div>
                <div className="h-4 w-3/4 bg-slate-200 rounded"></div>
                <div className="h-3 w-1/3 bg-slate-100 rounded"></div>
              </div>
            ))}
          </div>
        )}
        {!isLoading && catalogError && (
          <div className="bg-white rounded-3xl border border-rose-200 p-6 text-center space-y-3">
            <p className="text-xs text-rose-600 font-semibold">
              {t('home.picks_error')}
            </p>
            <button
              onClick={refreshCatalog}
              className="px-4 py-2 rounded-xl bg-[#1B1F3B] text-white text-xs font-bold"
            >
              {t('my_looks.try_again')}
            </button>
          </div>
        )}
        {!isLoading && !catalogError && products.length === 0 && (
          <div className="bg-white rounded-3xl border border-slate-200/80 p-8 text-center">
            <p className="text-xs text-slate-500">
              {t('home.picks_empty')}
            </p>
          </div>
        )}
        {!isLoading && !catalogError && products.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {products.slice(0, 6).map((prod) => (
              <article
                key={prod.id}
                className="bg-white rounded-3xl border border-slate-200/80 shadow-2xs overflow-hidden group hover:shadow-md transition-all flex flex-col"
              >
                <button
                  onClick={() => navigate(`/product/${prod.slug}`)}
                  className="relative h-56 overflow-hidden bg-slate-100 cursor-pointer text-left"
                  aria-label={t('a11y.view_product', { name: prod.title })}
                >
                  <HonestProductImage
                    src={prod.thumbnail_url}
                    alt={prod.title}
                    loading="lazy"
                    decoding="async"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-[9px] text-white">
                    {prod.brand_name}
                  </span>
                </button>
                <div className="p-4 flex flex-col flex-1 justify-between gap-3">
                  <div>
                    <span className="text-[10px] font-bold text-[#7A5C28] uppercase tracking-wide">
                      {prod.category_name}
                    </span>
                    <h3 className="font-serif text-sm font-bold text-[#1B1F3B] leading-snug mt-0.5">
                      {prod.title}
                    </h3>
                    <span className="text-sm font-bold text-[#1B1F3B] block mt-1">
                      {formatMoney(Math.round(prod.base_price * 100), prod.currency, lang)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={tryOn.gate({
                        render: () => openTryOn(prod),
                        fitCheck: () => openRuler(prod),
                      })}
                      disabled={tryOnKind === "blocked"}
                      className="flex-1 px-3 py-2 rounded-xl border border-slate-200 hover:border-[#1B1F3B] text-xs font-semibold text-slate-700 transition-all flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {tryOnKind === "render" ? (
                        <TryOnIcon size={14} color="#1B1F3B" />
                      ) : (
                        <RulerIcon size={14} color="#1B1F3B" />
                      )}
                      <span>
                        {t(
                          tryOnKind === "render"
                            ? "tryon.cta_try_on"
                            : "tryon.cta_fit_check",
                        )}
                      </span>
                    </button>
                    <button
                      onClick={() => navigate(`/product/${prod.slug}`)}
                      className="flex-1 px-3 py-2 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all"
                    >
                      {t('home.view_piece')}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* 4. Occasion Portals */}
      <section className="space-y-6">
        <div className="flex items-center justify-between border-b border-slate-200/80 pb-4">
          <div>
            <h2 className="font-serif text-2xl font-bold text-[#1B1F3B]">
              {t("home.occasions")}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
              {t('home.occasions_hint')}
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
                  <span>{t('home.instant_ai_stylist')}</span>
                </span>
                <h2 className="font-serif text-xl font-bold text-white mb-1">
                  {occ.title}
                </h2>
                <p className="text-xs text-slate-300 line-clamp-1 font-light mb-2">
                  {occ.desc}
                </p>
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
                  <span>{t('home.style_occasion_cta')}</span>
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
                {t("home.trending_title")}
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5 font-light">
              {t('home.trending_hint')}
            </p>
          </div>
          <button
            onClick={() => navigate("/discover")}
            className="text-xs font-bold text-[#1B1F3B] hover:text-[#C5A059] transition-colors"
          >
            {t('home.view_all_catalog')}
            {!isLoading && products.length > 0 ? ` (${formatNumber(products.length, lang)})` : ""} →
          </button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : catalogError && products.length === 0 ? (
          // N-1: honest failure state — no fabricated trending products when
          // the catalog API is down (the client-side fallback was removed).
          <EmptyState
            title={t('home.trending_error_title')}
            description={catalogError}
            actionText={t('common.retry')}
            onAction={refreshCatalog}
          />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
            {products.slice(0, 4).map((p) => (
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
                      aria-label={t('a11y.view_product', { name: p.title })}
                    >
                      <HonestProductImage
                        src={p.thumbnail_url}
                        alt={p.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
                      />
                    </button>
                    <div className="absolute top-2 left-2 flex flex-col gap-1">
                      <FitScoreBadge
                        score={p.style_compatibility_score}
                        label={t('product.fit_match')}
                        verdict={t('product.fit_color_harmony')}
                      />
                    </div>

                    <div className="absolute bottom-2 right-2 flex items-center gap-1.5">
                      <button
                        onClick={() => openRuler(p)}
                        className="p-2 rounded-full bg-white/90 hover:bg-white text-slate-800 shadow-sm backdrop-blur-xs transition-all"
                        title={t('a11y.no_photo_fit')}
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
                  <h4
                    onClick={() => navigate(`/product/${p.slug}`)}
                    className="font-serif text-xs sm:text-sm font-bold text-[#1B1F3B] line-clamp-1 hover:text-[#C5A059] cursor-pointer mt-0.5"
                  >
                    {p.title}
                  </h4>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs sm:text-sm font-bold text-[#1B1F3B]">
                      {formatMoney(Math.round(p.base_price * 100), p.currency || "USD", lang)}
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
                </div>

                <div className="pt-3 border-t border-slate-100 mt-3">
                  <button
                    onClick={() => addCatalogProductToBag(p)}
                    className="w-full py-2.5 rounded-xl bg-slate-100 hover:bg-[#1B1F3B] hover:text-white text-xs font-semibold text-slate-800 transition-all flex items-center justify-center gap-1.5"
                  >
                    <BagIcon size={14} color="currentColor" />
                    <span>{t('commerce.add_to_cart')}</span>
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
            <h2 className="font-serif text-sm font-bold text-[#1B1F3B]">
              {t('home.fit_studio_title')}
            </h2>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              {t('home.fit_studio_body')}
            </p>
          </div>

          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <BopisIcon size={20} color="#C5A059" />
            </div>
            <h2 className="font-serif text-sm font-bold text-[#1B1F3B]">
              {t('home.bopis_feature_title')}
            </h2>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              {capabilities.bopis_live
                ? capabilities.bopis_store_count === 1
                  ? t('home.bopis_live_single')
                  : t('home.bopis_live_count', { stores: capabilities.bopis_store_count })
                : t('home.bopis_soon')}
            </p>
          </div>

          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <ShieldIcon size={20} color="#C5A059" />
            </div>
            <h2 className="font-serif text-sm font-bold text-[#1B1F3B]">
              {t('home.returns_title')}
            </h2>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              {t('home.returns_body')}
            </p>
          </div>

          <div className="space-y-2">
            <div className="w-10 h-10 rounded-2xl bg-[#1B1F3B] text-[#C5A059] flex items-center justify-center font-bold shadow-xs mx-auto sm:mx-0">
              <BagIcon size={20} color="#C5A059" />
            </div>
            <h2 className="font-serif text-sm font-bold text-[#1B1F3B]">
              {t('home.bnpl_title')}
            </h2>
            <p className="text-xs text-slate-500 font-light leading-relaxed">
              {t('home.bnpl_body')}
              {!capabilities.bnpl_live && (
                <span className="block mt-1 text-[10px] font-bold text-amber-700">
                  {t('home.bnpl_demo_note')}
                </span>
              )}
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};
