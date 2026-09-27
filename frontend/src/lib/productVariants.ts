import { Product, ProductSKU } from "../models";

/**
 * Variant selection for a product page.
 *
 * WHY THIS IS A MODULE AND NOT INLINE VIEW CODE
 * ---------------------------------------------
 * A SKU is a (size x colour) pair, but `ProductDetailView` rendered only
 * `size`. With one colourway per product that is indistinguishable from
 * correct. The moment a product carries two colourways it renders DUPLICATE
 * size buttons — "M", "M" — with no way to tell them apart, and clicking one
 * selects whichever SKU happened to sort first. The shopper would then add a
 * colour they did not choose to the bag.
 *
 * Seed data currently has exactly one colour per product (verified against
 * production: 0 of 12 products have more than one), so this is a LATENT
 * defect, not a visible one. It is fixed here because the schema already
 * permits the case and the brand catalogue import can create it at any time —
 * and because the failure is silent: nothing throws, the page just sells the
 * wrong variant.
 *
 * Keeping the rule here rather than in the view means it can be tested
 * against the awkward shapes (missing hex, partial stock, one colour, no
 * SKUs) without mounting a page and stubbing a catalogue request.
 */

export interface ColourOption {
  color: string;
  /** Swatch colour. Falls back to the product's dominant hex, then navy. */
  hex: string;
  /** True when at least one size in this colourway is purchasable. */
  inStock: boolean;
}

export interface VariantOptions {
  colours: ColourOption[];
  /** The colour of the currently selected SKU, or the first colour. */
  selectedColour: string | null;
  /** Sizes belonging to `selectedColour` only, in SKU order. */
  sizesForColour: ProductSKU[];
  /** Sellable units summed across EVERY SKU, not just the selected one. */
  totalStock: number;
}

const DEFAULT_HEX = "#1B1F3B";

/**
 * Derive the colour/size options for a product.
 *
 * @param product Product carrying the SKU list (may be empty or absent).
 * @param selectedSkuId Currently selected SKU, if any.
 */
export function buildVariantOptions(
  product: Pick<Product, "skus" | "dominant_hex">,
  selectedSkuId: number | null,
): VariantOptions {
  const skus = product.skus ?? [];

  // Insertion-ordered so the UI is stable between renders: a Map preserves
  // first-seen order, which sorting by name would not (and re-ordering
  // swatches under the pointer is its own bug).
  const byColour = new Map<string, ColourOption>();
  for (const sku of skus) {
    const existing = byColour.get(sku.color);
    if (existing) {
      // A colourway counts as in stock if ANY of its sizes is.
      existing.inStock = existing.inStock || Boolean(sku.is_in_stock);
      continue;
    }
    byColour.set(sku.color, {
      color: sku.color,
      hex: sku.color_hex || product.dominant_hex || DEFAULT_HEX,
      inStock: Boolean(sku.is_in_stock),
    });
  }
  const colours = Array.from(byColour.values());

  const current = skus.find((s) => s.id === selectedSkuId) ?? skus[0];
  const selectedColour = current?.color ?? colours[0]?.color ?? null;

  return {
    colours,
    selectedColour,
    sizesForColour:
      selectedColour === null
        ? []
        : skus.filter((s) => s.color === selectedColour),
    // `stock_level` is nullable in practice (bulk imports, SQL backfills), so
    // it is coerced rather than trusted. A missing level contributes 0 —
    // never NaN, which would render as "NaN units available".
    totalStock: skus.reduce((n, s) => n + (Number(s.stock_level) || 0), 0),
  };
}

/**
 * The SKU to select when the shopper picks a different colour.
 *
 * Preference order: keep the size they were already looking at, else the
 * first purchasable size in that colour, else anything in that colour so the
 * swatch still responds and the out-of-stock state is visible. Silently
 * ignoring the click would look broken.
 */
export function skuForColour(
  skus: ProductSKU[],
  colour: string,
  currentSize?: string,
): ProductSKU | undefined {
  return (
    skus.find(
      (s) => s.color === colour && s.size === currentSize && s.is_in_stock,
    ) ??
    skus.find((s) => s.color === colour && s.is_in_stock) ??
    skus.find((s) => s.color === colour)
  );
}
