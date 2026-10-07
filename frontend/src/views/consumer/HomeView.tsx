import React from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import {
  SparkleIcon,
  TryOnIcon,
  FlameIcon,
  BagIcon,
  RulerIcon,
  ShieldIcon,
  BopisIcon,
} from "../../components/icons/ConfitIcons";
import { useUIStore } from "../../stores/uiStore";
import { useCatalogViewModel } from "../../viewmodels/useCatalogViewModel";
import { useCapabilities } from "../../hooks/useCapabilities";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { ProductCard } from "../../components/product/ProductCard";
import { SkeletonCard } from "../../components/common/CommonComponents";
import { useCartStore } from "../../stores/cartStore";
import { resolvePurchasableSku } from "../../lib/catalogSku";
import {
  classifyActionError,
  type ActionOutcome,
} from "../../components/common/InteractionPrimitives";
import { formatAmount, formatNumber } from "../../i18n/format";
import {
  CircularGallery,
  type GalleryItem,
} from "../../components/ui/circular-gallery";
import { CardStackShowcase } from "../../components/showcase/DesignShowcases";
import { HeroSection, HeroMedia, HeroLightCard } from "../../components/common/HeroSection";
import { usePrefersReducedMotion } from "../../components/common/InteractionPrimitives";
import { CollectionRail } from "../../components/home/CollectionRail";
import { HonestProductImage } from "../../components/common/HonestProductImage";
import { catalogService } from "../../services/apiServices";
import { queryKeys } from "../../lib/queryClient";
import type { Product } from "../../models";

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
  const { openStylist, showToast } =
    useUIStore();
  const {
    products,
    categories,
    isLoading,
    error: catalogError,
    refresh: refreshCatalog,
  } = useCatalogViewModel();

  // "New in" is its own server question (sort_by=newest), not a re-slice of
  // the recommended list — the two sections previously showed the SAME first
  // products twice on one page. Separate query key, same 5-min cache policy
  // as the view model.
  const newInQuery = useQuery({
    queryKey: queryKeys.catalog.products({ sort_by: "newest", limit: 8 }),
    queryFn: () => catalogService.getProducts({ sort_by: "newest", limit: 8 }),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
  });
  const newArrivals: Product[] = newInQuery.data ?? [];

  // Today's picks own the first six recommended slots; the sale section
  // excludes them so one product never fills two curated sections.
  const pickIds = React.useMemo(
    () => new Set(products.slice(0, 6).map((p) => p.id)),
    [products],
  );
  // Only REAL markdowns: compare_at_price is server-sourced and absent when
  // no prior price genuinely existed (see models/index.ts). No sale items →
  // the section does not render. No fake urgency, ever.
  const saleItems = React.useMemo(
    () =>
      products
        .filter(
          (p) =>
            p.compare_at_price != null &&
            p.compare_at_price > p.base_price &&
            !pickIds.has(p.id),
        )
        .slice(0, 4),
    [products, pickIds],
  );

  // The brand pavilion previously showed four HARDCODED brand tiles with
  // stock photos of unrelated content. It now derives the maisons from the
  // live catalogue: real names, real piece counts, real product imagery.
  const brandSpotlights = React.useMemo(() => {
    const byBrand = new Map<string, { name: string; items: Product[] }>();
    for (const p of products) {
      if (!p.brand_name) continue;
      const entry = byBrand.get(p.brand_name) ?? { name: p.brand_name, items: [] };
      entry.items.push(p);
      byBrand.set(p.brand_name, entry);
    }
    return [...byBrand.values()]
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 4);
  }, [products]);
  // J-01: trust badges render what the platform can ACTUALLY do right now.
  const { capabilities } = useCapabilities();
  // Try-on CTAs (three on this page) bind to the live engine verdict, so none
  // of them promises a render the GPU cannot deliver (2026-09-22).
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);
  const reduceMotion = usePrefersReducedMotion();
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

  // Returns the real outcome so the card's button state machine never claims
  // "Added" for an add that did not happen (see InteractionPrimitives).
  const addCatalogProductToBag = async (prod: any): Promise<ActionOutcome> => {
    const sku = await resolvePurchasableSku(prod).catch(() => null);
    if (!sku) {
      showToast(t("commerce.no_purchasable_size"), "error");
      return "unavailable";
    }
    try {
      await addItem(sku.id, {
        id: prod.id,
        title: prod.title,
        category: prod.category_name,
        color: prod.color_family,
      });
      // Duplicate-SKU dialog intercepted the add — nothing is in the bag yet.
      if (useCartStore.getState().pendingDuplicateAlert) {
        return "handled";
      }
      showToast(t("toast.added_to_bag"), "success");
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

  const occasionCards = [
    {
      title: t("home.occasion_wedding"),
      tag: "wedding",
      img: "https://images.unsplash.com/photo-1519741497674-611481863552?w=700&auto=format&fit=crop&q=80",
      desc: t("home.occasion_wedding_desc"),
      palette: ["#D4AF37", "#111111", "#FAF9F6"],
    },
    {
      title: t("home.occasion_work"),
      tag: "work",
      img: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80",
      desc: t("home.occasion_work_desc"),
      palette: ["#1B1F3B", "#FAF9F6", "#64748B"],
    },
    {
      title: t("home.occasion_party"),
      tag: "party",
      img: "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80",
      desc: t("home.occasion_party_desc"),
      palette: ["#D4AF37", "#C5A059", "#1B1F3B"],
    },
    {
      title: t("home.occasion_casual"),
      tag: "casual",
      img: "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=700&auto=format&fit=crop&q=80",
      desc: t("home.occasion_casual_desc"),
      palette: ["#FAF9F6", "#D8C7B5", "#1B1F3B"],
    },
  ];

  return (
    <div className="space-y-16 sm:space-y-24 pb-24">
      {/* 1. Hero — reusable dark editorial panel + light structured card
          (spec 07). All copy sits on the solid dark gradient, never on a
          bare photograph; the aside card is ONE keyboard-focusable link to
          the real /builder route; the editorial image is lazy, responsive
          and failure-proof via HeroMedia/HonestProductImage. */}
      <HeroSection
        eyebrow={
          <div className="surface-glass-dark inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border-[#C5A059]/30 !text-[#E2BF70] text-[11px] font-semibold uppercase tracking-widest">
            <span aria-hidden="true"><SparkleIcon size={13} color="#E2BF70" /></span>
            <span>{t('home.hero_badge')}</span>
          </div>
        }
        title={t("home.hero_title")}
        lede={t('home.stylist_flow_cta_body')}
        support={t("home.hero_subtitle")}
        actions={
          <>
            <button
              onClick={() =>
                document
                  .getElementById("guided-first-look")
                  ?.scrollIntoView({
                    // Smooth scroll is motion: honor the OS preference (§7).
                    behavior: reduceMotion ? "auto" : "smooth",
                    block: "start",
                  })
              }
              type="button"
              className="min-h-11 px-7 py-3.5 rounded-2xl bg-[#C5A059] hover:bg-[#E2BF70] text-[#0C0E1E] font-bold text-xs sm:text-sm tracking-wide shadow-lg hover:shadow-[#C5A059]/20 transition-all flex items-center gap-2 active:scale-98 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              <span aria-hidden="true"><SparkleIcon size={16} color="#0C0E1E" /></span>
              <span>{t('home.get_first_look')}</span>
            </button>

            <button
              onClick={() =>
                // The studio still opens: it hosts the no-photo fit check too.
                // Only the *label* changes, and only when a render is off the
                // table, so the hero never advertises a broken capability.
                navigate(tryOnKind === "render" ? "/tryon-studio" : "/fit-finder")
              }
              type="button"
              className="min-h-11 px-5 py-3.5 rounded-2xl bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold text-xs sm:text-sm backdrop-blur-md transition-all flex items-center gap-2 active:scale-98 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              <span aria-hidden="true">
                {tryOnKind === "render" ? (
                  <TryOnIcon size={16} color="#FFFFFF" isAi={true} />
                ) : (
                  <RulerIcon size={16} color="#FFFFFF" />
                )}
              </span>
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
              className="inline-flex min-h-11 items-center px-4 py-3.5 rounded-2xl text-slate-300 hover:text-[#E2BF70] font-semibold text-xs sm:text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              {t('home.shop_catalog_cta')}
            </Link>
          </>
        }
        facts={
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 max-w-2xl pt-2">
            {[
              t('home.fact_no_account'),
              t('home.fact_photo_optional'),
              t('home.fact_privacy'),
            ].map((item) => (
              <div
                key={item}
                className="surface-glass-dark rounded-2xl border-white/10 px-3 py-2 text-[11px] !text-slate-300"
              >
                {item}
              </div>
            ))}
          </div>
        }
        aside={
          <div className="hidden lg:block">
            <HeroLightCard to="/builder" label={t('home.example_card_label')}>
              <HeroMedia
                src="https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=900&auto=format&fit=crop&q=80"
                alt={t('home.example_look_alt')}
                unavailableLabel={t('common.image_unavailable')}
                caption={
                  <>
                    <span className="rounded-full bg-[#C5A059] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#0C0E1E]">
                      {t('home.example_result')}
                    </span>
                    <h2 className="mt-3 font-serif text-2xl font-bold">
                      {t('home.example_look_title')}
                    </h2>
                    <p className="mt-1 text-xs text-slate-200">
                      {t('home.example_look_body')}
                    </p>
                  </>
                }
              />
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
            </HeroLightCard>
          </div>
        }
      />

      {/* 1b. Collection navigation — the page's primary wayfinding, placed
          directly under the hero and ABOVE every curated section (Baymard:
          navigation must outrank promotional content). Real categories, real
          deep links into the filtered Discover view. */}
      <CollectionRail categories={categories} isLoading={isLoading} />

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
          />
        </div>
      </section>

      <CardStackShowcase
        tone="consumer"
        eyebrow={t("home.stack_eyebrow")}
        title={t("home.stack_title")}
        description={t("home.stack_description")}
      />

      {/* 2b. New in — the newest pieces by the server's own ordering
          (sort_by=newest), presented as a horizontal snap rail so it reads
          differently from the curated grids around it. Honest states: real
          skeletons while loading, a retryable error line on failure, and the
          whole section disappears when the catalogue has nothing new. */}
      {(newInQuery.isLoading || newInQuery.isError || newArrivals.length > 0) && (
        <section aria-labelledby="home-new-in-title" className="space-y-6">
          <div className="flex flex-col justify-between gap-2 border-b border-slate-200/80 pb-4 sm:flex-row sm:items-end">
            <div>
              <span className="block text-[10px] font-bold uppercase tracking-widest text-[#7A5C28]">
                {t("home.new_in_eyebrow")}
              </span>
              <h2
                id="home-new-in-title"
                className="mt-1 font-serif text-2xl font-bold text-[#1B1F3B]"
              >
                {t("home.new_in_title")}
              </h2>
            </div>
            <Link
              to="/discover"
              className="flex items-center gap-1 text-xs font-semibold text-[#1B1F3B] transition-colors hover:text-[#C5A059]"
            >
              <span>{t("home.view_all_catalog")}</span>
              <span aria-hidden="true">→</span>
            </Link>
          </div>

          {newInQuery.isLoading && (
            <div
              className="flex gap-4 overflow-hidden"
              aria-busy="true"
            >
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="w-64 shrink-0">
                  <SkeletonCard />
                </div>
              ))}
            </div>
          )}
          {newInQuery.isError && (
            <div className="space-y-3 rounded-3xl border border-rose-200 bg-white p-6 text-center">
              <p className="text-xs font-semibold text-rose-600">
                {t("home.new_in_error")}
              </p>
              <button
                type="button"
                onClick={() => newInQuery.refetch()}
                className="rounded-xl bg-[#1B1F3B] px-4 py-2 text-xs font-bold text-white"
              >
                {t("common.retry")}
              </button>
            </div>
          )}
          {!newInQuery.isLoading && !newInQuery.isError && newArrivals.length > 0 && (
            <ul className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:px-0">
              {newArrivals.map((p) => (
                <li key={p.id} className="w-64 shrink-0 snap-start">
                  <ProductCard product={p} />
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

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

        {/* Honest-data remediation (home re-pass, 2026-10-08): these tiles
            were four HARDCODED brands with Unsplash stock photos of
            unrelated garments. Every tile below is derived from the live
            catalogue — real maison name, real piece count, the brand's own
            product imagery. */}
        {isLoading ? (
          <div
            className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4"
            aria-busy="true"
          >
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-72 animate-pulse rounded-3xl border border-slate-200/60 bg-slate-100"
              />
            ))}
          </div>
        ) : brandSpotlights.length >= 2 ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {brandSpotlights.map((brand) => (
              <Link
                key={brand.name}
                to="/discover"
                className="group flex flex-col justify-between rounded-3xl border border-slate-200/80 bg-white p-5 shadow-2xs transition-all duration-300 hover:border-[#C5A059]/50 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
              >
                <div className="mb-4 grid h-44 grid-cols-2 gap-2">
                  {brand.items.slice(0, 2).map((item) => (
                    <div
                      key={item.id}
                      className="overflow-hidden rounded-2xl bg-slate-100"
                    >
                      <HonestProductImage
                        src={item.thumbnail_url}
                        alt={item.title}
                        loading="lazy"
                        unavailableLabel={t("common.image_unavailable")}
                        className="h-full w-full object-cover transition-transform duration-500 motion-safe:group-hover:scale-105"
                      />
                    </div>
                  ))}
                </div>

                <div>
                  <h3 className="font-serif text-base font-bold text-[#1B1F3B] transition-colors group-hover:text-[#C5A059]">
                    {brand.name}
                  </h3>
                  <span className="block text-[11px] font-light text-slate-500">
                    {brand.items.length === 1
                      ? t("home.brand_pieces_one")
                      : t("home.brand_pieces_many", {
                          count: brand.items.length,
                        })}
                  </span>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-xs font-semibold text-[#1B1F3B] group-hover:text-[#C5A059]">
                  <span>{t("home.open_catalog")}</span>
                  <span aria-hidden="true">→</span>
                </div>
              </Link>
            ))}
          </div>
        ) : null}
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
              <ProductCard
                key={prod.id}
                product={prod}
                priority
              />
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

      {/* 5. On sale now — replaces the old "Trending" grid, which re-rendered
          the SAME first products the "Today's picks" grid had already shown
          (both sliced one recommended query). This section only exists when
          the live catalogue holds REAL markdowns (server-sourced
          compare_at_price) that are not already on the page — no fake
          urgency, no duplicated merchandise, and it disappears entirely
          rather than padding itself with full-price items. */}
      {saleItems.length > 0 && (
        <section aria-labelledby="home-sale-title" className="space-y-6">
          <div className="flex items-center justify-between border-b border-slate-200/80 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <FlameIcon size={22} color="#C5A059" />
                <h2
                  id="home-sale-title"
                  className="font-serif text-2xl font-bold text-[#1B1F3B]"
                >
                  {t("home.sale_title")}
                </h2>
              </div>
              <p className="mt-0.5 text-xs font-light text-slate-500 sm:text-sm">
                {t("home.sale_hint")}
              </p>
            </div>
            <button
              onClick={() => navigate("/discover")}
              className="text-xs font-bold text-[#1B1F3B] transition-colors hover:text-[#C5A059]"
            >
              {t("home.view_all_catalog")}
              {products.length > 0 ? ` (${formatNumber(products.length, lang)})` : ""} →
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 sm:gap-6">
            {saleItems.map((p) => (
              <ProductCard
                key={p.id}
                product={p}
                onAddToBag={addCatalogProductToBag}
                footerSlot={
                  capabilities.bnpl_live ? (
                    // bnpl_live is measured, but the LIST payload carries no
                    // instalment figure and no provider: a non-numeric line
                    // states the true fact; the real figure
                    // (server-computed, currency-converted) appears on the
                    // product page and in the cart.
                    <span className="text-[11px] text-slate-600">
                      {t('commerce.bnpl_available_checkout')}
                    </span>
                  ) : (
                    <span className="text-[11px] text-slate-500">
                      {t('commerce.bnpl_not_live')}
                    </span>
                  )
                }
              />
            ))}
          </div>
        </section>
      )}

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
