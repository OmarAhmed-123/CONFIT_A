import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Product } from "../../models";
import { useUIStore } from "../../stores/uiStore";
import { useTryOnAvailability } from "../../hooks/useTryOnAvailability";
import { HonestProductImage } from "../common/HonestProductImage";
import { FitScoreBadge } from "../common/CommonComponents";
import {
  AsyncActionButton,
  WishlistToggle,
  type ActionOutcome,
} from "../common/InteractionPrimitives";
import { RulerIcon, BagIcon, HeartIcon } from "../icons/ConfitIcons";
import { TryOnButton } from "./TryOnButton";
import { formatMoney } from "../../i18n/format";

/**
 * The ONE product card.
 *
 * WHY THIS EXISTS
 * ---------------
 * A product card was re-implemented inline on every surface that showed one:
 * `HomeView` twice, `DiscoverView` twice, and then not at all on `FitFinderView`
 * or `OutfitBuilderView`, which rendered products with no Try-On control
 * whatsoever. Four copies of the same markup meant four places to keep the
 * try-on gate, the price formatting and the accessibility labels in step — and
 * they had already drifted: the Home card omitted the fit badge, the Discover
 * card omitted the discount (because nothing rendered one anywhere), and the
 * two surfaces that most needed try-on did not offer it.
 *
 * This is the same duplication the codebase already fixed once for the try-on
 * *rule* (see `useTryOnAvailability`, which exists precisely because eight call
 * sites each decided for themselves whether try-on worked). Fixing the rule
 * while leaving four copies of the markup that consumes it only moved the
 * problem, so the card itself now lives here, once.
 *
 * HONESTY CONTRACT
 * ----------------
 * Inherited wholesale from `useTryOnAvailability`, never re-derived:
 *   - `render`    -> the button says Try On and opens the studio.
 *   - `fit_check` -> the button RELABELS to the fit-check wording and opens
 *                    the ruler flow. It never says "Try On" when it will not.
 *   - `blocked`   -> the control is disabled and titled with the reason.
 *
 * A discount badge is shown ONLY when the server sends a real
 * `compare_at_price` above the selling price. The card never computes a
 * "was" price, because an invented strike-through is a false claim about a
 * price that was never charged.
 */

export type ProductCardVariant = "grid" | "compact";

export interface ProductCardProps {
  product: Product;
  /** `grid` = full card with actions. `compact` = image, title, price, try-on. */
  variant?: ProductCardVariant;
  /** Wishlist state and toggle. Omit to hide the control entirely. */
  isWishlisted?: boolean;
  onToggleWishlist?: (productId: number) => void;
  /**
   * Add-to-bag handler. Omit to hide the button (e.g. in the outfit builder).
   * The resolved `ActionOutcome` drives the button's state machine:
   * "success" | void → Added; "handled" → another surface continues (e.g. the
   * duplicate dialog), no success claim; "unavailable" | "error" | throw →
   * failure state, button stays actionable. See InteractionPrimitives.
   */
  onAddToBag?: (product: Product) => Promise<ActionOutcome | void> | ActionOutcome | void;
  /** Rendered under the price — e.g. a BNPL badge or a fit hint. */
  footerSlot?: React.ReactNode;
  /** Overrides navigation to the product page. */
  onOpenDetails?: (product: Product) => void;
  className?: string;
  /** Set on the first screenful only; lazy-loads everything below. */
  priority?: boolean;
}

/** Discount, derived only from server-provided fields. */
function useDiscount(product: Product) {
  const compareAt = product.compare_at_price;
  const price = product.base_price;
  if (compareAt == null || !(compareAt > price)) {
    return null;
  }
  const amount = compareAt - price;
  return {
    compareAt,
    amount,
    percent: Math.round((amount / compareAt) * 100),
  };
}

export const ProductCard: React.FC<ProductCardProps> = ({
  product,
  variant = "grid",
  isWishlisted = false,
  onToggleWishlist,
  onAddToBag,
  footerSlot,
  onOpenDetails,
  className = "",
  priority = false,
}) => {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  const navigate = useNavigate();
  const { openTryOn, openRuler } = useUIStore();
  const tryOn = useTryOnAvailability();
  // `true`: this card always offers the ruler fallback, so a non-rendering
  // engine degrades to fit-check rather than to a dead control.
  const tryOnKind = tryOn.ctaKind(true);

  const discount = useDiscount(product);
  const detailsHref = `/product/${product.slug}`;
  const openDetails = () =>
    onOpenDetails ? onOpenDetails(product) : navigate(detailsHref);
  // C02 Goal-E2E finding (2026-10-07): the card navigated ONLY via onClick —
  // no real <a>, so middle-click/new-tab/copy-link were impossible and the
  // title was mouse-only. The three detail entries are now true links when
  // the card navigates (the optional onOpenDetails modal override keeps its
  // button semantics).


  const isCompact = variant === "compact";

  return (
    <article
      className={[
        "bg-white rounded-3xl border border-slate-200/80 shadow-2xs",
        "overflow-hidden group hover:shadow-md transition-all flex flex-col",
        className,
      ].join(" ")}
      data-testid="product-card"
      data-product-id={product.id}
    >
      <div className="relative overflow-hidden bg-slate-100">
        {onOpenDetails ? (
          <button
            onClick={openDetails}
            className={`block w-full text-left cursor-pointer ${
              isCompact ? "h-44" : "h-56"
            }`}
            aria-label={t("a11y.view_product", { name: product.title })}
          >
            <HonestProductImage
              src={product.thumbnail_url}
              alt={product.title}
              loading={priority ? "eager" : "lazy"}
              decoding="async"
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          </button>
        ) : (
          <Link
            to={detailsHref}
            className={`block w-full text-left cursor-pointer ${
              isCompact ? "h-44" : "h-56"
            }`}
            aria-label={t("a11y.view_product", { name: product.title })}
          >
            <HonestProductImage
              src={product.thumbnail_url}
              alt={product.title}
              loading={priority ? "eager" : "lazy"}
              decoding="async"
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          </Link>
        )}

        <div className="absolute top-2.5 left-2.5 flex flex-col items-start gap-1">
          {discount && (
            <span
              className="px-2 py-0.5 rounded-full bg-[#7A1F2B] text-white text-[10px] font-bold tracking-wide shadow-sm"
              data-testid="product-card-discount"
            >
              {t("product.percent_off", { percent: discount.percent })}
            </span>
          )}
          {product.style_compatibility_score != null && (
            <FitScoreBadge
              score={product.style_compatibility_score}
              label={t("product.fit_match")}
              verdict={t("product.fit_color_harmony")}
            />
          )}
        </div>

        {onToggleWishlist && (
          <WishlistToggle
            isWishlisted={isWishlisted}
            onToggle={() => onToggleWishlist(product.id)}
            className="absolute top-1 end-1 rounded-full bg-white/90 hover:bg-white text-slate-700 shadow-sm backdrop-blur-xs transition-all"
          >
            <HeartIcon size={15} isLiked={isWishlisted} />
          </WishlistToggle>
        )}

        {/* Quick try-on, always present on the image itself. */}
        <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5">
          <button
            onClick={() => openRuler(product)}
            className="p-2 rounded-full bg-white/90 hover:bg-white text-slate-800 shadow-sm backdrop-blur-xs transition-all"
            title={t("a11y.no_photo_fit")}
            aria-label={t("a11y.no_photo_fit")}
          >
            <RulerIcon size={14} color="#1B1F3B" />
          </button>
          <TryOnButton product={product} variant="icon" />
        </div>
      </div>

      <div className="p-4 flex flex-col flex-1 gap-2">
        <div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            {product.brand_name}
          </span>
          <h3 className="font-serif text-xs sm:text-sm font-bold text-[#1B1F3B] line-clamp-1 mt-0.5">
            {onOpenDetails ? (
              <button
                onClick={openDetails}
                className="text-left hover:text-[#C5A059] cursor-pointer"
              >
                {product.title}
              </button>
            ) : (
              <Link to={detailsHref} className="hover:text-[#C5A059]">
                {product.title}
              </Link>
            )}
          </h3>

          <div className="flex items-center justify-between mt-1 gap-2">
            <span className="flex items-baseline gap-1.5 min-w-0">
              <span className="text-xs sm:text-sm font-bold text-[#1B1F3B]">
                {formatMoney(
                  Math.round(product.base_price * 100),
                  product.currency || "USD",
                  lang,
                )}
              </span>
              {discount && (
                <span className="text-[11px] text-slate-400 line-through shrink-0">
                  {formatMoney(
                    Math.round(discount.compareAt * 100),
                    product.currency || "USD",
                    lang,
                  )}
                </span>
              )}
            </span>
            {product.color_family && (
              <span className="text-[11px] text-slate-500 font-light truncate max-w-[80px]">
                {product.color_family}
              </span>
            )}
          </div>
        </div>

        {footerSlot}

        <div className="mt-auto pt-3 border-t border-slate-100 grid grid-cols-2 gap-2">
          {onOpenDetails ? (
            <button
              onClick={openDetails}
              className="py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all shadow-2xs"
            >
              {t("discover.view_details")}
            </button>
          ) : (
            <Link
              to={detailsHref}
              className="inline-flex items-center justify-center py-2.5 rounded-xl bg-[#1B1F3B] hover:bg-[#0C0E1E] text-white text-xs font-semibold transition-all shadow-2xs"
            >
              {t("discover.view_details")}
            </Link>
          )}
          <TryOnButton product={product} variant="full" className="w-full" />

          {onAddToBag && (
            <AsyncActionButton
              onAction={() => onAddToBag(product)}
              idleLabel={t("commerce.add_to_cart")}
              icon={<BagIcon size={14} color="currentColor" />}
              data-testid="product-card-add-to-bag"
              className="col-span-2 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 disabled:opacity-60 text-slate-800 text-xs font-semibold"
            />
          )}
        </div>
      </div>
    </article>
  );
};

export default ProductCard;
