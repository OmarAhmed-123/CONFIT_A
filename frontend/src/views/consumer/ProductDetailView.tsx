import React, { useState, useEffect, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { catalogService } from "../../services/apiServices";
import { Product, StoreInventoryLocation } from "../../models";
import { useUIStore } from "../../stores/uiStore";
import { formatMoney } from "../../i18n/format";
import { buildVariantOptions, skuForColour } from "../../lib/productVariants";
import { useCartStore } from "../../stores/cartStore";
import {
  TryOnIcon,
  RulerIcon,
  BagIcon,
  SparkleIcon,
  HeartIcon,
} from "../../components/icons/ConfitIcons";
import {
  FitScoreBadge,
  BNPLBadge,
  EmptyState,
} from "../../components/common/CommonComponents";
import { HonestProductImage } from "../../components/common/HonestProductImage";
import { Surface } from "../../components/common/Surface";
import {
  AsyncActionButton,
  WishlistToggle,
  classifyActionError,
} from "../../components/common/InteractionPrimitives";
import { useTranslation } from "react-i18next";
import { localizeApiError } from "../../i18n/apiErrors";
import { resolveMessage } from "../../i18n/messages";
import {
  useTryOnAvailability,
  TryOnAvailability,
  TryOnCtaKind,
} from "../../hooks/useTryOnAvailability";
import { useDeviceWishlist } from "../../hooks/useDeviceWishlist";
import { useRecentlyViewed } from "../../hooks/useRecentlyViewed";
import { setRouteTitleOverride } from "../../a11y/routes";

/** Server truth only: the amber urgency line appears at or under this
 *  remaining stock, straight from the SKU's stock_level. */
const LOW_STOCK_THRESHOLD = 3;

/* ------------------------------------------------------------------ */
/* PdpSkeleton — loading state shaped like the page it precedes        */
/* ------------------------------------------------------------------ */

/**
 * C03 pass 2: the loading state was a generic centred spinner on a blank
 * page — zero perceived performance, while the `.skeleton-shimmer` token
 * (home pass 3) already existed. This skeleton mirrors the REAL page
 * geometry (breadcrumb line, 7-col gallery at the gallery's own aspect,
 * thumb rail, 5-col buy column) so the content appears to develop in
 * place instead of popping in. The shimmer collapses to a static block
 * under prefers-reduced-motion via the global rule in index.css.
 *
 * Honesty is preserved: the cold-start message and the retry affordance
 * from the 2026-09-06 audit stay, as visible text — never aria-hidden.
 */
const PdpSkeleton: React.FC<{ slow: boolean; onRetry: () => void }> = ({
  slow,
  onRetry,
}) => {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-label={t("product.loading_details")}
      data-testid="pdp-skeleton"
      className="space-y-10 pb-24 max-w-6xl mx-auto"
    >
      <span className="sr-only">
        {slow ? t("product.loading_cold_start") : t("product.loading_details")}
      </span>
      {slow && (
        <div className="flex flex-col items-center gap-2 p-3 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/30">
          <p className="text-xs text-slate-600 text-center">
            {t("product.loading_cold_start")}
          </p>
          <button
            onClick={onRetry}
            className="min-h-11 px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:border-[#C5A059]"
          >
            {t("common.retry_now")}
          </button>
        </div>
      )}
      <div aria-hidden="true" className="space-y-10">
        <div className="h-4 w-56 max-w-full rounded-full bg-slate-100 skeleton-shimmer" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          <div className="lg:col-span-7 space-y-4">
            <div className="aspect-[3/4] sm:h-[540px] rounded-3xl bg-slate-100 skeleton-shimmer" />
            <div className="flex gap-3">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-20 h-24 rounded-2xl bg-slate-100 skeleton-shimmer"
                />
              ))}
            </div>
          </div>
          <div className="lg:col-span-5 space-y-6">
            <div className="space-y-3">
              <div className="h-3 w-24 rounded-full bg-slate-100 skeleton-shimmer" />
              <div className="h-7 w-4/5 rounded-xl bg-slate-100 skeleton-shimmer" />
              <div className="h-6 w-32 rounded-xl bg-slate-100 skeleton-shimmer" />
            </div>
            <div className="h-48 rounded-2xl bg-slate-100 skeleton-shimmer" />
            <div className="h-[52px] rounded-2xl bg-slate-100 skeleton-shimmer" />
            <div className="h-[46px] rounded-2xl bg-slate-100 skeleton-shimmer" />
          </div>
        </div>
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* TryOnCta — ONE source of truth for the try-on gate                  */
/* ------------------------------------------------------------------ */

/**
 * C03 pass 2 (DRY): this button existed twice — gallery overlay and buy
 * column — with the gate/disabled/title/label logic copy-pasted. A drift
 * in one copy (e.g. a new engine verdict) would have produced two
 * different stories on the same page. The availability HOOK is still
 * called once in the parent (it probes the engine); only the verdict is
 * passed down.
 */
const TryOnCta: React.FC<{
  product: Product;
  tryOn: TryOnAvailability;
  kind: TryOnCtaKind;
  variant: "overlay" | "panel";
}> = ({ product, tryOn, kind, variant }) => {
  const { t } = useTranslation();
  const { openTryOn, openRuler } = useUIStore();
  const blocked = kind === "blocked";
  const iconSize = variant === "overlay" ? 18 : 16;
  return (
    <button
      onClick={tryOn.gate({
        render: () => openTryOn(product),
        fitCheck: () => openRuler(product),
      })}
      disabled={blocked}
      title={
        blocked && tryOn.userMessage
          ? resolveMessage(tryOn.userMessage, t)
          : undefined
      }
      className={
        variant === "overlay"
          ? "surface-glass-dark absolute bottom-4 end-4 min-h-11 px-5 py-3 rounded-2xl hover:bg-[#C5A059] hover:text-slate-950 text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          : "w-full min-h-12 py-3.5 rounded-2xl bg-[#FDF8EE] hover:bg-[#C5A059] text-[#7A5C28] hover:text-white border border-[#C5A059]/40 font-bold text-xs shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      }
    >
      {kind === "render" ? (
        <TryOnIcon size={iconSize} color="currentColor" />
      ) : (
        <RulerIcon size={iconSize} color="currentColor" />
      )}
      <span>
        {t(kind === "render" ? "tryon.cta_try_on" : "tryon.cta_fit_check_instead")}
      </span>
    </button>
  );
};

/* ------------------------------------------------------------------ */
/* AccordionSection — ONE accordion row structure                      */
/* ------------------------------------------------------------------ */

/**
 * C03 pass 2 (DRY + two real defects): the three accordion rows were the
 * same structure pasted three times, and every pasted copy carried
 * `text-left` — which forces LEFT alignment inside the Arabic RTL page
 * (text-start follows the writing direction). The header row also sat at
 * ~40px; it is a primary disclosure control, so it now meets a 48px
 * target (min-h-12).
 */
const AccordionSection: React.FC<{
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}> = ({ title, open, onToggle, children }) => (
  <div className="py-1.5">
    {/* Pass 3: the full WAI-ARIA disclosure pattern — the button lives
        inside a heading, so screen-reader users can jump between the
        page's sections by heading navigation. Preflight zeroes the
        h3's own margin/size, so the visual stays identical. */}
    <h3>
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="w-full min-h-12 flex justify-between items-center font-bold text-slate-800 text-start"
      >
        <span>{title}</span>
        <span
          aria-hidden="true"
          className="text-[#C5A059] transition-transform duration-300 ease-luxury"
        >
          {open ? "−" : "+"}
        </span>
      </button>
    </h3>
    {open && <div className="pb-2 confit-fade-in">{children}</div>}
  </div>
);

export const ProductDetailView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();

  const [product, setProduct] = useState<Product | null>(null);
  const [selectedSkuId, setSelectedSkuId] = useState<number | null>(null);
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [bopisStores, setBopisStores] = useState<StoreInventoryLocation[]>([]);
  const [bopisStatus, setBopisStatus] = useState<
    "idle" | "loading" | "success" | "empty" | "error"
  >("idle");
  const [bopisError, setBopisError] = useState<string | null>(null);
  // C03: this heart was a bare useState(false) — it reset on every reload
  // and disagreed with the Discover grid. One shared device list now.
  const { toggleWishlist, isWishlisted: isInWishlist } = useDeviceWishlist();
  const [activeAccordion, setActiveAccordion] = useState<
    "materials" | "bopis" | "delivery" | null
  >("materials");
  const [isLoading, setIsLoading] = useState(true);
  const [isSlowLoad, setIsSlowLoad] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  // C03 pass 3: a dropped connection is not a server error. The failure
  // state names it honestly, and the page retries BY ITSELF the moment
  // the browser reports the connection back — the shopper never has to
  // understand what went wrong to recover.
  const [loadKind, setLoadKind] = useState<"error" | "offline" | null>(null);
  // C03 pass 4 — contextual zoom: the point the shopper clicked becomes
  // the transform origin, so the zoom inspects THAT detail (stitching,
  // texture), not the image centre. null = resting.
  const [zoomOrigin, setZoomOrigin] = useState<{ x: number; y: number } | null>(
    null,
  );

  // C03 pass 2 — mobile sticky buy bar. The bar renders ONLY while the
  // real CTA block is scrolled out of view (IntersectionObserver), only
  // under lg, and only for a purchasable SKU: a dead disabled bar pinned
  // to the viewport would be decoration, which this codebase bans.
  const ctaBlockRef = useRef<HTMLDivElement | null>(null);
  const [ctaInView, setCtaInView] = useState(true);
  // Single-flight guard shared by BOTH add-to-bag buttons. Each
  // AsyncActionButton guards its own double-click, but two buttons are
  // two independent state machines — without this ref a fast tap on the
  // main CTA followed by the sticky one would POST twice. The ref is the
  // atomic truth (state updates are async); the state only mirrors it so
  // the OTHER button visibly disables while one is in flight.
  const addInFlightRef = useRef(false);
  const [addBusy, setAddBusy] = useState(false);

  const { openTryOn, openRuler, showToast } = useUIStore();
  const { addItem } = useCartStore();
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  // Honest try-on gating: the label and the destination below are derived from
  // the live engine verdict, so a shopper is never sent into a render that
  // cannot happen (2026-09-22). `openRuler` is the working no-photo path.
  const tryOn = useTryOnAvailability();
  const tryOnKind = tryOn.ctaKind(true);
  // Device-local browse memory (wishlist precedent): records this piece,
  // returns the OTHERS for the rail below. No server, nothing invented.
  const recentlyViewed = useRecentlyViewed(product);

  // C6 FIX: BOPIS failure handling - differentiate no stores vs API failure vs network
  const fetchBopisStores = (skuId: number) => {
    setBopisStatus("loading");
    setBopisError(null);
    catalogService
      .getBopisStoresForSKU(skuId)
      .then((stores) => {
        setBopisStores(stores);
        setBopisStatus(stores.length === 0 ? "empty" : "success");
      })
      .catch((err: any) => {
        setBopisStores([]);
        setBopisStatus("error");
        const msg = err?.message || null;
        setBopisError(msg);
        // Don't show toast for BOPIS - it's secondary info, show inline error instead
      });
  };

  useEffect(() => {
    if (!slug) return;
    setIsLoading(true);
    setIsSlowLoad(false);
    setLoadError(null);
    setLoadKind(null);
    // Cold-start honesty: serverless first hits can take a while — tell the
    // user instead of showing an apparently frozen skeleton (2026-09-06 audit).
    const slowTimer = setTimeout(() => setIsSlowLoad(true), 8000);
    catalogService
      .getProductDetail(slug)
      .then((data) => {
        setProduct(data);
        const firstInStock =
          data.skus?.find((s) => s.is_in_stock) || data.skus?.[0];
        if (firstInStock) {
          setSelectedSkuId(firstInStock.id);
          fetchBopisStores(firstInStock.id);
        }
        setIsLoading(false);
      })
      .catch((err) => {
        setIsLoading(false);
        // Offline is diagnosed from the browser's own connectivity flag,
        // never guessed from error text.
        setLoadKind(
          typeof navigator !== "undefined" && navigator.onLine === false
            ? "offline"
            : "error",
        );
        // Keep the server's sentence when it sent one; otherwise let the
        // UI translate — "Product not found" hardcoded EN leaked into the
        // Arabic failure state (C03 test caught it).
        setLoadError(err?.message || null);
      })
      .finally(() => clearTimeout(slowTimer));
  }, [slug, reloadTick]);

  useEffect(() => {
    if (!selectedSkuId) return;
    fetchBopisStores(selectedSkuId);
  }, [selectedSkuId]);

  // Pass 4 — the tab tells the truth. /product/:slug matched the static
  // discover route meta, so every product tab read "Style & Discover":
  // five open tabs were indistinguishable during comparison shopping and
  // the title described the WRONG page (WCAG 2.4.2). The override is
  // registered when the real name arrives and cleared on unmount —
  // child cleanup runs before the route hook's parent effect, so the
  // next page can never inherit a product name.
  useEffect(() => {
    if (!product) return;
    setRouteTitleOverride(
      (lang === "ar" && product.title_ar) || product.title,
    );
    return () => setRouteTitleOverride(null);
  }, [product, lang]);

  // Pass 4 — schema.org/Product JSON-LD, from server data only. One
  // script tag per mounted product, removed on cleanup; availability is
  // the aggregate SKU truth, price is the server's base_price.
  useEffect(() => {
    if (!product) return;
    const el = document.createElement("script");
    el.type = "application/ld+json";
    el.setAttribute("data-testid", "pdp-jsonld");
    el.text = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Product",
      name: product.title,
      image: product.images?.length ? product.images : [product.thumbnail_url],
      brand: { "@type": "Brand", name: product.brand_name },
      offers: {
        "@type": "Offer",
        price: product.base_price,
        priceCurrency: product.currency || "USD",
        availability: product.skus?.some((s) => s.is_in_stock)
          ? "https://schema.org/InStock"
          : "https://schema.org/OutOfStock",
      },
    });
    document.head.appendChild(el);
    return () => {
      document.head.removeChild(el);
    };
  }, [product]);

  // A zoom targets ONE photograph; switching images resets to resting.
  useEffect(() => {
    setZoomOrigin(null);
  }, [activeImageIndex, product]);

  // Automatic recovery: while the failure is an OFFLINE failure, one
  // 'online' event refetches without any tap. Bound to the failure
  // state, not to mount, so a later dropout re-arms it.
  useEffect(() => {
    if (loadKind !== "offline") return;
    const retry = () => setReloadTick((n) => n + 1);
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [loadKind]);

  // Observe the real CTA block; the sticky bar exists only while it is
  // off-screen. Re-runs when the product arrives because the block only
  // mounts with the loaded page (same always-mounted-null lesson as
  // NoPhotoFitModal: bind to the OPEN signal, not to mount).
  useEffect(() => {
    const node = ctaBlockRef.current;
    if (!node || typeof window.IntersectionObserver !== "function") return;
    const io = new IntersectionObserver((entries) => {
      setCtaInView(entries[0]?.isIntersecting ?? true);
    });
    io.observe(node);
    return () => io.disconnect();
  }, [product]);

  if (isLoading) {
    return (
      <PdpSkeleton
        slow={isSlowLoad}
        onRetry={() => setReloadTick((n) => n + 1)}
      />
    );
  }

  if (loadKind || loadError || !product) {
    const offline = loadKind === "offline";
    return (
      <>
        <h1 className="sr-only">{t('product.unavailable_heading')}</h1>
        <EmptyState
          title={offline ? t('product.offline_title') : t('product.unavailable_title')}
          description={
            offline
              ? t('product.offline_desc')
              : loadError || t("product.load_failed_desc")
          }
          actionText={t("common.try_again")}
          onAction={() => setReloadTick((n) => n + 1)}
        />
      </>
    );
  }

  const currentSku =
    product.skus?.find((s) => s.id === selectedSkuId) || product.skus?.[0];

  // Variant rule lives in lib/productVariants so it can be tested against the
  // awkward shapes (two colourways, partial stock, missing hex, no SKUs)
  // without mounting this page.
  const skus = product.skus ?? [];
  const { colours, selectedColour, sizesForColour, totalStock } =
    buildVariantOptions(product, selectedSkuId);

  const images =
    product.images && product.images.length > 0
      ? product.images
      : [product.thumbnail_url];
  const bnpl = product.bnpl;
  const styleScore = product.style_compatibility_available
    ? product.style_compatibility_score
    : null;
  const fitScore = product.fit_available ? product.ai_fit_score : null;

  const skuPriceCents = Math.round(
    (currentSku?.price_override ?? product.base_price) * 100,
  );
  const skuPriceLabel = formatMoney(
    skuPriceCents,
    product.currency || "USD",
    lang,
  );

  // ONE add-to-bag flow shared by the main CTA and the sticky bar — the
  // honesty contract (no success before the server, duplicate-SKU dialog
  // claims nothing) is written once and cannot drift between the two.
  const handleAddToBag = async () => {
    if (!currentSku) return "unavailable" as const;
    if (addInFlightRef.current) return "handled" as const;
    addInFlightRef.current = true;
    setAddBusy(true);
    try {
      const res = await addItem(currentSku.id, {
        id: product.id,
        title: product.title,
        category: product.category_name,
        color: product.color_family,
      });
      // The duplicate-SKU dialog may have intercepted the add:
      // nothing is in the bag yet, so no success toast and no
      // "Added" state — the dialog finishes the flow.
      if (useCartStore.getState().pendingDuplicateAlert) {
        return "handled" as const;
      }
      // Spec §5: a re-added SKU says the MERGED quantity in words —
      // derived from the server's cart, never guessed locally.
      if (res?.merged) {
        showToast(
          t("toast.bag_quantity_merged", { count: res.quantity }),
          "success",
        );
      } else {
        showToast(t("toast.added_to_bag"), "success");
      }
      return "success" as const;
    } catch (err: any) {
      const kind = classifyActionError(err);
      if (kind === "error") {
        // Translated by code where possible; the honest server
        // text only as a last resort — never raw-EN-first.
        showToast(localizeApiError(err, t, "discover.add_to_bag_failed"), "error");
      }
      return kind;
    } finally {
      addInFlightRef.current = false;
      setAddBusy(false);
    }
  };

  return (
    <div className="space-y-10 pb-24 max-w-6xl mx-auto">
      {/* C03 redesign: the generic CardStackShowcase was REMOVED from this
          page. It sat above the product itself (first mobile viewport!),
          showed stock imagery unrelated to the item, and carried a
          hardcoded EN caption written for developers. A PDP is a purchase
          surface — the product opens the page; the REAL, API-driven
          "complete the look" section below keeps the styling story. */}
      <nav className="text-xs text-slate-500 flex items-center gap-2 font-light">
        <Link to="/discover" className="hover:text-[#1B1F3B] transition-colors">
          {t('product.breadcrumb_catalog')}
        </Link>
        <span>/</span>
        <Link
          /* category_id was sent to a SLUG-based filter — Discover ignored
             it silently. The detail payload now carries category_slug; an
             older cached payload degrades to the unfiltered catalogue
             rather than a filter that lies. */
          to={
            product.category_slug
              ? `/discover?category=${product.category_slug}`
              : "/discover"
          }
          className="hover:text-[#1B1F3B] transition-colors"
        >
          {product.category_name}
        </Link>
        <span>/</span>
        <span className="font-semibold text-slate-800 truncate max-w-xs">
          {product.title}
        </span>
      </nav>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        <div className="lg:col-span-7 space-y-4">
          <div className="aspect-[3/4] sm:h-[540px] rounded-3xl overflow-hidden bg-slate-100 border border-slate-200/80 relative group shadow-sm">
            {/* key= remounts on switch so each image enters with a quiet
                crossfade (confit-fade-in only touches opacity — safe for
                reduced motion and for jsdom's toBeVisible). The zoom is
                hover-only, 700ms on the luxury curve: media breathes,
                layout never moves.
                C03 pass 2: this hero IS the page's LCP element — it was
                loading="lazy", which told the browser to deprioritise the
                one image the shopper came to see. Eager + fetchpriority
                (lowercase: React 18 passes unknown lowercase attributes
                through; the camelCase prop would warn). Thumbnails and
                outfit tiles stay lazy. */}
            <HonestProductImage
              key={activeImageIndex}
              src={images[activeImageIndex] || product.thumbnail_url}
              alt={product.title}
              loading="eager"
              decoding="async"
              {...({ fetchpriority: "high" } as unknown as React.ImgHTMLAttributes<HTMLImageElement>)}
              className={`w-full h-full object-cover confit-fade-in transition-transform duration-700 ease-luxury ${
                zoomOrigin
                  ? "scale-[2]"
                  : "motion-safe:group-hover:scale-105"
              }`}
              style={
                zoomOrigin
                  ? { transformOrigin: `${zoomOrigin.x}% ${zoomOrigin.y}%` }
                  : undefined
              }
            />
            {/* Pass 4 — contextual zoom. A transparent full-bleed toggle
                UNDER the overlay controls (they are later siblings, so
                they stack above and keep their own clicks): the clicked
                point becomes the transform origin, so the shopper
                inspects THAT stitch, not the centre. Escape or a second
                activation rests it; switching images rests it. The
                700ms luxury transition collapses under reduced motion
                (user-initiated state change — an instant swap is the
                correct reduced-motion behaviour). */}
            <button
              type="button"
              aria-label={t("a11y.zoom_toggle")}
              aria-pressed={!!zoomOrigin}
              data-testid="pdp-zoom-toggle"
              onClick={(e) => {
                if (zoomOrigin) {
                  setZoomOrigin(null);
                  return;
                }
                const rect = e.currentTarget.getBoundingClientRect();
                // Keyboard activation reports (0,0) clientX/Y — fall back
                // to a centred zoom instead of the top-start corner.
                const hasPoint = e.clientX || e.clientY;
                setZoomOrigin(
                  hasPoint
                    ? {
                        x: Math.round(
                          ((e.clientX - rect.left) / rect.width) * 100,
                        ),
                        y: Math.round(
                          ((e.clientY - rect.top) / rect.height) * 100,
                        ),
                      }
                    : { x: 50, y: 50 },
                );
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape" && zoomOrigin) {
                  e.stopPropagation();
                  setZoomOrigin(null);
                }
              }}
              className={`absolute inset-0 w-full h-full ${
                zoomOrigin ? "cursor-zoom-out" : "cursor-zoom-in"
              }`}
            />
            <div className="absolute top-4 left-4 flex flex-col gap-2">
              {styleScore != null && (
                <FitScoreBadge
                  score={styleScore}
                  label={t('product.fit_match')}
                  verdict={
                    product.style_compatibility_reason ||
                    t("product.style_score_verdict")
                  }
                />
              )}
              {fitScore != null && (
                <FitScoreBadge
                  score={fitScore}
                  verdict={
                    product.recommended_size
                      ? product.recommended_size_available
                        ? t("product.recommended_badge", {
                            size: product.recommended_size,
                          })
                        : t("product.recommended_badge_unavailable", {
                            size: product.recommended_size,
                          })
                      : t("product.fit_score_verdict")
                  }
                />
              )}
            </div>

            <WishlistToggle
              isWishlisted={isInWishlist(product.id)}
              onToggle={() => toggleWishlist(product.id)}
              className="surface-glass-light absolute top-3 end-3 rounded-full hover:bg-white text-slate-800 transition-all"
            >
              <HeartIcon size={18} isLiked={isInWishlist(product.id)} />
            </WishlistToggle>

            <TryOnCta
              product={product}
              tryOn={tryOn}
              kind={tryOnKind}
              variant="overlay"
            />
          </div>

          {images.length > 1 && (
            <div className="flex gap-3 overflow-x-auto pb-1">
              {images.map((img, idx) => (
                <button
                  key={idx}
                  onClick={() => setActiveImageIndex(idx)}
                  aria-label={t('a11y.view_image', { index: idx + 1 })}
                  aria-pressed={activeImageIndex === idx}
                  className={`w-20 h-24 rounded-2xl overflow-hidden border-2 transition-all shrink-0 ${
                    activeImageIndex === idx
                      ? "border-[#C5A059] ring-2 ring-[#C5A059]/30"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <HonestProductImage
                    src={img}
                    alt={t('a11y.product_image_alt', { name: product.title, index: idx + 1 })}
                    loading="lazy"
                    className="w-full h-full object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Buy column stays in view while the gallery scrolls — the
            decision context (price, size, CTA) never leaves the screen. */}
        <div className="lg:col-span-5 space-y-6 lg:sticky lg:top-24 lg:self-start">
          <div>
            <span className="text-xs font-bold text-[#7A5C28] uppercase tracking-widest block mb-1">
              {product.brand_name}
            </span>
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[#1B1F3B] leading-tight">
              {product.title}
            </h1>
            <div className="flex items-baseline flex-wrap gap-x-3 gap-y-1 mt-2">
              <span className="text-2xl font-serif font-black text-[#1B1F3B]">
                {formatMoney(
                  Math.round(product.base_price * 100),
                  product.currency || "USD",
                  lang,
                )}
              </span>
              {/* Shown ONLY from a server-provided prior price. The client
                  never computes a "was" figure: a strike-through price that
                  was never charged is a false discount claim. */}
              {product.compare_at_price != null &&
                product.compare_at_price > product.base_price && (
                  <>
                    <span className="text-sm text-slate-400 line-through">
                      {formatMoney(
                        Math.round(product.compare_at_price * 100),
                        product.currency || "USD",
                        lang,
                      )}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-[#7A1F2B] text-white text-[11px] font-bold">
                      {t("product.percent_off", {
                        percent: Math.round(
                          ((product.compare_at_price - product.base_price) /
                            product.compare_at_price) *
                            100,
                        ),
                      })}
                    </span>
                    <span className="w-full text-[11px] font-semibold text-[#7A1F2B]">
                      {t("product.you_save", {
                        amount: formatMoney(
                          Math.round(
                            (product.compare_at_price - product.base_price) * 100,
                          ),
                          product.currency || "USD",
                          lang,
                        ),
                      })}
                    </span>
                  </>
                )}
            </div>

            {bnpl?.eligible && bnpl.installment_amount != null && (
              <div className="mt-3 p-3 rounded-2xl bg-[#FDF8EE] border border-[#C5A059]/30">
                <BNPLBadge
                  currency={product.currency || "USD"}
                  provider={bnpl.provider || undefined}
                  installmentAmount={bnpl.installment_amount}
                  isEstimate={bnpl.is_estimate !== false}
                  eligible
                />
              </div>
            )}
          </div>

          {/* C03 pass 2: p-4.5 is not a Tailwind class (not in the scale,
              not in the config) — this card rendered with NO padding from
              that token. p-5 is the nearest real step. */}
          <Surface variant="raised" reveal className="p-5 rounded-2xl space-y-3.5">
            <div className="flex justify-between items-center pb-2 border-b border-slate-100">
              <div className="flex items-center gap-1.5">
                <SparkleIcon size={16} color="#C5A059" />
                <span className="text-xs font-bold text-[#1B1F3B]">
                  {t('product.size_and_fit')}
                </span>
              </div>
              {/* Was a bare text link with a ~16px hit area — a primary
                  entry into the fit flow needs a real target (44px). */}
              <button
                onClick={() => openRuler(product)}
                className="min-h-11 px-2 -me-2 text-xs font-bold text-[#7A5C28] hover:underline flex items-center gap-1"
              >
                <RulerIcon size={14} color="#C5A059" />
                <span>{t('product.find_my_size')}</span>
              </button>
            </div>

            {product.fit_available ? (
              <p className="text-xs text-slate-600 leading-relaxed font-light">
                {/* The fallback was a hand-built English template literal,
                    which rendered untranslated Latin text inside the Arabic
                    RTL page whenever fit_reasoning was absent. */}
                {product.fit_reasoning ||
                  t("product.recommended_size_fallback", {
                    size: product.recommended_size,
                  })}
                {product.recommended_size_available === false && (
                  <span className="block mt-1 text-amber-700 font-medium">
                    {t('product.recommended_size_out_of_stock')}
                  </span>
                )}
              </p>
            ) : (
              <p className="text-xs text-slate-500 leading-relaxed font-light">
                {t('product.complete_profile_for_size')}
              </p>
            )}

            {/* Colour selection. Rendered as a chooser only when there is a
                choice to make; a single-colourway product states the colour
                instead of offering a pointless one-option control. */}
            {colours.length > 0 && (
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-xs font-bold text-slate-700">
                    {t("product.colour")}
                  </span>
                  <span className="text-[11px] text-slate-500 font-light">
                    {selectedColour}
                  </span>
                </div>
                {colours.length > 1 ? (
                  <div
                    className="flex gap-2 flex-wrap"
                    role="group"
                    aria-label={t("product.colour")}
                  >
                    {colours.map((c) => {
                      const active = c.color === selectedColour;
                      return (
                        <button
                          key={c.color}
                          onClick={() => {
                            const next = skuForColour(
                              skus,
                              c.color,
                              currentSku?.size,
                            );
                            if (next) setSelectedSkuId(next.id);
                          }}
                          disabled={!c.inStock}
                          aria-pressed={active}
                          title={c.color}
                          className={`h-9 pl-1.5 pr-3 rounded-xl border flex items-center gap-2 text-[11px] font-semibold transition-all ${
                            active
                              ? "border-[#1B1F3B] bg-[#1B1F3B] text-white"
                              : c.inStock
                                ? "border-slate-200 hover:border-slate-300 bg-white text-slate-800"
                                : "border-slate-100 bg-slate-50 text-slate-300 cursor-not-allowed line-through"
                          }`}
                        >
                          <span
                            aria-hidden="true"
                            className="w-5 h-5 rounded-lg border border-black/10 shrink-0"
                            style={{ backgroundColor: c.hex }}
                          />
                          <span>{c.color}</span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="w-5 h-5 rounded-lg border border-black/10"
                      style={{ backgroundColor: colours[0].hex }}
                    />
                    <span className="text-xs text-slate-700">
                      {colours[0].color}
                    </span>
                  </div>
                )}
              </div>
            )}

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-xs font-bold text-slate-700">
                  {t('product.available_sizes')}
                </span>
                {/* Was a hand-built English string, which rendered Latin text
                    and digits inside the Arabic RTL page.
                    Pass 4: product.low_stock_count existed in BOTH locales
                    and was wired to nothing — the designed urgency signal
                    never shipped. Server stock_level only, threshold 3.
                    aria-live: switching a size announces the new stock
                    truth instead of silently repainting it. */}
                <span
                  aria-live="polite"
                  data-testid="pdp-stock-line"
                  className={`text-[10px] font-semibold ${
                    currentSku?.is_in_stock &&
                    currentSku.stock_level <= LOW_STOCK_THRESHOLD
                      ? "text-amber-700"
                      : "text-slate-500"
                  }`}
                >
                  {currentSku?.is_in_stock
                    ? currentSku.stock_level <= LOW_STOCK_THRESHOLD
                      ? t('product.low_stock_count', { count: currentSku.stock_level })
                      : t('product.in_stock_count', { count: currentSku.stock_level })
                    : t('product.out_of_stock')}
                </span>
              </div>
              <div
                className="flex gap-2 flex-wrap"
                role="group"
                aria-label={t('a11y.select_size')}
              >
                {sizesForColour.map((sku) => (
                  <button
                    key={sku.id}
                    onClick={() => setSelectedSkuId(sku.id)}
                    disabled={!sku.is_in_stock}
                    aria-pressed={selectedSkuId === sku.id}
                    className={`min-w-[48px] h-11 px-3 rounded-xl border text-xs font-bold transition-all ${
                      selectedSkuId === sku.id
                        ? "border-[#1B1F3B] bg-[#1B1F3B] text-white shadow-sm"
                        : sku.is_in_stock
                          ? "border-slate-200 hover:border-slate-300 text-slate-800 bg-white"
                          : "border-slate-100 text-slate-300 bg-slate-50 cursor-not-allowed line-through"
                    }`}
                  >
                    {sku.size}
                  </button>
                ))}
              </div>

              {/* Total sellable units across every variant. Kept separate from
                  the per-store pickup quantities further down: those are a
                  different pool and adding them together would double-count. */}
              <p className="mt-2 text-[11px] text-slate-500">
                {/* "21 units available across 1 variants" — the raw counts
                    were interpolated with no grammatical number agreement
                    (production screenshot, 2026-10-07). Each count now picks
                    its own singular/plural phrase before composing. */}
                {totalStock > 0
                  ? t('product.total_units_available', {
                      units:
                        totalStock === 1
                          ? t('product.unit_count_one')
                          : t('product.unit_count_many', { count: totalStock }),
                      variants:
                        skus.length === 1
                          ? t('product.variant_count_one')
                          : t('product.variant_count_many', { count: skus.length }),
                    })
                  : t('product.out_of_stock')}
              </p>
            </div>
          </Surface>

          <div ref={ctaBlockRef} className="space-y-2.5">
            <AsyncActionButton
              disabled={!currentSku?.is_in_stock || addBusy}
              onAction={handleAddToBag}
              icon={<BagIcon size={16} color="#FFFFFF" />}
              idleLabel={
                !currentSku?.is_in_stock
                  ? t("product.out_of_stock")
                  : t("product.add_to_bag_price", { price: skuPriceLabel })
              }
              data-testid="pdp-add-to-bag"
              className="w-full py-4 rounded-2xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-50 text-white font-bold text-xs shadow-md"
            />

            <TryOnCta
              product={product}
              tryOn={tryOn}
              kind={tryOnKind}
              variant="panel"
            />
          </div>

          <div className="border-t border-slate-200/80 pt-2 divide-y divide-slate-100 text-xs">
            <AccordionSection
              title={t('product.fabric_care_details')}
              open={activeAccordion === "materials"}
              onToggle={() =>
                setActiveAccordion(
                  activeAccordion === "materials" ? null : "materials",
                )
              }
            >
              <div className="text-slate-500 space-y-1.5 font-light leading-relaxed">
                <div>
                  <strong>{t('product.composition_label')}</strong>{" "}
                  {product.material || t('product.not_specified')}
                </div>
                <div>
                  <strong>{t('product.care_label')}</strong>{" "}
                  {product.care_instructions || t('product.see_garment_label')}
                </div>
                {product.description && (
                  <p className="pt-1">{product.description}</p>
                )}
              </div>
            </AccordionSection>

            <AccordionSection
              title={t('product.bopis_title')}
              open={activeAccordion === "bopis"}
              onToggle={() =>
                setActiveAccordion(activeAccordion === "bopis" ? null : "bopis")
              }
            >
              <div className="space-y-2">
                {bopisStatus === "loading" && (
                  // Pass 3: shimmer shaped like the store card it precedes
                  // (same radius/height), not a bare sentence — the answer
                  // appears to develop in place. Text stays for SRs.
                  <div
                    role="status"
                    aria-label={t('product.bopis_checking')}
                    data-testid="bopis-skeleton"
                  >
                    <span className="sr-only">{t('product.bopis_checking')}</span>
                    <div
                      aria-hidden="true"
                      className="h-16 rounded-xl bg-slate-100 skeleton-shimmer"
                    />
                  </div>
                )}
                {bopisStatus === "error" && (
                  <div className="p-3 rounded-xl bg-rose-50 border border-rose-200">
                    <p className="text-[11px] font-bold text-rose-800">
                      {t('product.bopis_failed')}
                    </p>
                    <p className="text-[11px] text-rose-600 mt-1">
                      {/* BUG FIX: this fallback was the LITERAL text
                          "{t('product.bopis_unreachable')}" in quotes —
                          the raw code rendered on screen. */}
                      {bopisError || t("product.bopis_fallback_error")}
                    </p>
                    <button
                      onClick={() =>
                        selectedSkuId && fetchBopisStores(selectedSkuId)
                      }
                      className="mt-2 min-h-11 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50"
                    >
                      {t('common.retry')}
                    </button>
                  </div>
                )}
                {bopisStatus === "empty" && (
                  <p className="text-slate-500 font-light text-xs">
                    {t('product.bopis_no_store')}
                  </p>
                )}
                {bopisStatus === "success" &&
                  bopisStores.filter((s) => s.is_available_for_pickup)
                    .length === 0 && (
                    <p className="text-slate-500 font-light text-xs">
                      {t('product.bopis_no_store_stock')}
                    </p>
                  )}
                {bopisStatus === "success" &&
                  bopisStores.filter((s) => s.is_available_for_pickup)
                    .length > 0 && (
                    <>
                      {bopisStores
                        .filter((s) => s.is_available_for_pickup)
                        .map((store) => (
                          <div
                            key={store.store_id}
                            className="p-2.5 rounded-xl bg-[#FAF9F6] border border-slate-200/80 flex justify-between items-center gap-2"
                          >
                            <div>
                              <div className="font-bold text-slate-800 text-xs">
                                {store.store_name}
                              </div>
                              <div className="text-[11px] text-slate-500 font-light">
                                {store.address}
                              </div>
                              {store.latitude != null &&
                                store.longitude != null && (
                                  <a
                                    className="text-[11px] text-[#C5A059] font-semibold"
                                    href={`https://www.openstreetmap.org/?mlat=${store.latitude}&mlon=${store.longitude}#map=16/${store.latitude}/${store.longitude}`}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {t('product.open_map')}
                                  </a>
                                )}
                            </div>
                            {/* text-right forced LEFT-page alignment in RTL;
                                text-end follows the writing direction. */}
                            <div className="text-end">
                              <span className="text-[11px] font-bold text-emerald-600">
                                {store.quantity_available} {t('product.in_stock')}
                              </span>
                            </div>
                          </div>
                        ))}
                    </>
                  )}
              </div>
            </AccordionSection>

            <AccordionSection
              title={t('product.delivery_returns')}
              open={activeAccordion === "delivery"}
              onToggle={() =>
                setActiveAccordion(
                  activeAccordion === "delivery" ? null : "delivery",
                )
              }
            >
              <div className="text-slate-500 space-y-1.5 font-light leading-relaxed">
                <div>
                  {t('product.delivery_note')}
                </div>
                <div>
                  {t('product.returns_note')}
                </div>
              </div>
            </AccordionSection>
          </div>
        </div>
      </div>

      {product.related_outfits && product.related_outfits.length > 0 && (
        <section className="space-y-4">
          <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">
            {t('product.complete_the_look')}
          </h2>
          {/* C03 pass 2: the outfit cards sat on a symmetric 2-col grid with
              fixed-height (h-28) letterboxed images. Editorial 12-col rhythm
              now alternates 7/5 → 5/7 across rows (a single outfit takes the
              full row), and the tiles use the 4:5 fashion-portrait ratio with
              the same quiet 700ms hover zoom the gallery speaks — one motion
              language across the page. */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            {product.related_outfits.map((outfit, idx) => (
              <Surface
                variant="solid"
                reveal
                revealDelay={Math.min(idx * 0.06, 0.3)}
                key={`${outfit.title}-${idx}`}
                className={`rounded-3xl p-4 space-y-3 ${
                  product.related_outfits!.length === 1
                    ? "md:col-span-12"
                    : ["md:col-span-7", "md:col-span-5", "md:col-span-5", "md:col-span-7"][idx % 4]
                }`}
              >
                <h3 className="text-sm font-bold text-[#1B1F3B]">
                  {outfit.title}
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  {outfit.items.map((item) => (
                    <Link
                      key={item.product_id}
                      to={item.slug ? `/product/${item.slug}` : `/discover`}
                      className="group rounded-2xl border border-slate-100 p-2 hover:border-[#C5A059] transition-colors flex flex-col"
                    >
                      {item.image_url && (
                        <div className="overflow-hidden rounded-xl mb-2">
                          <HonestProductImage
                            src={item.image_url}
                            alt={item.product_title}
                            loading="lazy"
                            className="w-full aspect-[4/5] object-cover motion-safe:group-hover:scale-105 transition-transform duration-700 ease-luxury"
                          />
                        </div>
                      )}
                      <div className="text-[11px] font-bold text-slate-800 truncate">
                        {item.product_title}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {item.brand_name}
                      </div>
                      {item.price != null && (
                        <div className="text-[11px] font-semibold mt-auto pt-1">
                          {formatMoney(
                            Math.round(item.price * 100),
                            product.currency || 'USD',
                            lang,
                          )}
                        </div>
                      )}
                    </Link>
                  ))}
                </div>
              </Surface>
            ))}
          </div>
        </section>
      )}

      {/* Pass 4 — device-local browse memory. A horizontal scroll-snap
          rail (native scrolling: links stay tab-focusable, no translateX
          hijack, swipe is never the only way — spec 10). 4:5 portrait
          tiles, the gallery's own 700ms hover zoom. Renders NOTHING when
          the device has no other history: no dead section. */}
      {recentlyViewed.length > 0 && (
        <section className="space-y-4" data-testid="pdp-recently-viewed">
          <h2 className="font-serif text-xl font-bold text-[#1B1F3B]">
            {t('product.recently_viewed')}
          </h2>
          <div className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory">
            {recentlyViewed.map((item) => (
              <Link
                key={item.id}
                to={`/product/${item.slug}`}
                className="group snap-start shrink-0 w-32 sm:w-36 rounded-2xl border border-slate-100 p-2 hover:border-[#C5A059] transition-colors flex flex-col bg-white"
              >
                <div className="overflow-hidden rounded-xl mb-2">
                  <HonestProductImage
                    src={item.thumbnail_url}
                    alt={(lang === "ar" && item.title_ar) || item.title}
                    loading="lazy"
                    className="w-full aspect-[4/5] object-cover motion-safe:group-hover:scale-105 transition-transform duration-700 ease-luxury"
                  />
                </div>
                <div className="text-[11px] font-bold text-slate-800 truncate">
                  {(lang === "ar" && item.title_ar) || item.title}
                </div>
                <div className="text-[11px] font-semibold text-slate-600 mt-auto pt-0.5">
                  {formatMoney(
                    Math.round(item.base_price * 100),
                    item.currency || "USD",
                    lang,
                  )}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Mobile sticky buy bar — exists ONLY while the real CTA block is
          off-screen and the SKU is purchasable: no dead pinned controls.
          Solid surface (spec 09: no glass/blur behind text), entrance is
          the opacity-only confit-fade-in (reduced-motion safe). Shares
          handleAddToBag's single-flight guard with the main CTA, so the
          pair can never double-POST. */}
      {currentSku?.is_in_stock && !ctaInView && (
        <div
          role="region"
          aria-label={t("product.quick_buy_bar")}
          data-testid="pdp-sticky-bar"
          className="lg:hidden fixed bottom-0 inset-x-0 z-40 confit-slide-up border-t border-slate-200 bg-white shadow-[0_-8px_24px_rgb(12_14_30/0.08)]"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          <div className="max-w-6xl mx-auto px-4 py-2.5 flex items-center gap-3">
            <div
              aria-hidden="true"
              className="w-10 h-12 rounded-lg overflow-hidden bg-slate-100 shrink-0"
            >
              <HonestProductImage
                src={images[activeImageIndex] || product.thumbnail_url}
                alt=""
                loading="lazy"
                className="w-full h-full object-cover"
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-bold text-slate-800 truncate">
                {product.title}
              </div>
              <div className="text-sm font-serif font-black text-[#1B1F3B]">
                {skuPriceLabel}
              </div>
            </div>
            <AsyncActionButton
              disabled={addBusy}
              onAction={handleAddToBag}
              icon={<BagIcon size={14} color="#FFFFFF" />}
              idleLabel={t("product.add_to_bag")}
              data-testid="pdp-add-to-bag-sticky"
              className="shrink-0 min-h-12 px-5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] disabled:opacity-50 text-white font-bold text-xs"
            />
          </div>
        </div>
      )}
    </div>
  );
};
