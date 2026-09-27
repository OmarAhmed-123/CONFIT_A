import { describe, it, expect } from "vitest";
import { buildVariantOptions, skuForColour } from "../productVariants";
import type { ProductSKU } from "../../models";

/**
 * The defect under test is SILENT: with two colourways the product page
 * rendered duplicate size buttons and selecting one could add a colour the
 * shopper never chose. Nothing throws, so only assertions catch it.
 */

const sku = (over: Partial<ProductSKU> & { id: number }): ProductSKU =>
  ({
    sku_code: `SKU-${over.id}`,
    size: "M",
    color: "Navy",
    color_hex: "#1B1F3B",
    price_override: null,
    stock_level: 5,
    is_in_stock: true,
    ...over,
  }) as ProductSKU;

const product = (skus: ProductSKU[], dominant = "#000000") =>
  ({ skus, dominant_hex: dominant }) as any;

describe("buildVariantOptions", () => {
  it("separates colourways instead of listing duplicate sizes", () => {
    const skus = [
      sku({ id: 1, size: "S", color: "Navy" }),
      sku({ id: 2, size: "M", color: "Navy" }),
      sku({ id: 3, size: "S", color: "Black" }),
      sku({ id: 4, size: "M", color: "Black" }),
    ];
    const v = buildVariantOptions(product(skus), 1);

    expect(v.colours.map((c) => c.color)).toEqual(["Navy", "Black"]);
    // This is the bug: the old view rendered all four, i.e. S, M, S, M.
    expect(v.sizesForColour.map((s) => s.size)).toEqual(["S", "M"]);
    expect(v.sizesForColour.every((s) => s.color === "Navy")).toBe(true);
  });

  it("follows the selected SKU into its own colourway", () => {
    const skus = [
      sku({ id: 1, size: "S", color: "Navy" }),
      sku({ id: 2, size: "M", color: "Black" }),
    ];
    const v = buildVariantOptions(product(skus), 2);
    expect(v.selectedColour).toBe("Black");
    expect(v.sizesForColour.map((s) => s.id)).toEqual([2]);
  });

  it("marks a colourway in stock when ANY of its sizes is", () => {
    const skus = [
      sku({ id: 1, color: "Navy", size: "S", is_in_stock: false }),
      sku({ id: 2, color: "Navy", size: "M", is_in_stock: true }),
      sku({ id: 3, color: "Rust", size: "S", is_in_stock: false }),
    ];
    const v = buildVariantOptions(product(skus), 1);
    expect(v.colours.find((c) => c.color === "Navy")!.inStock).toBe(true);
    expect(v.colours.find((c) => c.color === "Rust")!.inStock).toBe(false);
  });

  it("preserves first-seen colour order so swatches do not jump", () => {
    const skus = [
      sku({ id: 1, color: "Zinc" }),
      sku({ id: 2, color: "Amber" }),
      sku({ id: 3, color: "Zinc" }),
    ];
    expect(
      buildVariantOptions(product(skus), 1).colours.map((c) => c.color),
    ).toEqual(["Zinc", "Amber"]);
  });

  it("falls back for a missing swatch hex rather than rendering nothing", () => {
    const skus = [sku({ id: 1, color: "Navy", color_hex: null as any })];
    expect(buildVariantOptions(product(skus), 1).colours[0].hex).toBe("#000000");
    // and finally to the house navy when the product has no dominant hex
    expect(
      buildVariantOptions({ skus, dominant_hex: null } as any, 1).colours[0].hex,
    ).toBe("#1B1F3B");
  });

  it("sums stock across every variant, not just the selected one", () => {
    const skus = [
      sku({ id: 1, color: "Navy", stock_level: 3 }),
      sku({ id: 2, color: "Black", stock_level: 4 }),
    ];
    expect(buildVariantOptions(product(skus), 1).totalStock).toBe(7);
  });

  it("treats a missing stock level as zero, never NaN", () => {
    const skus = [
      sku({ id: 1, stock_level: null as any }),
      sku({ id: 2, stock_level: 2 }),
    ];
    const total = buildVariantOptions(product(skus), 1).totalStock;
    expect(Number.isNaN(total)).toBe(false);
    expect(total).toBe(2);
  });

  it("handles a product with no SKUs without throwing", () => {
    const v = buildVariantOptions(product([]), null);
    expect(v.colours).toEqual([]);
    expect(v.selectedColour).toBeNull();
    expect(v.sizesForColour).toEqual([]);
    expect(v.totalStock).toBe(0);
  });

  it("still resolves when the selected id is stale", () => {
    const skus = [sku({ id: 1, color: "Navy" })];
    expect(buildVariantOptions(product(skus), 999).selectedColour).toBe("Navy");
  });
});

describe("skuForColour", () => {
  const skus = [
    sku({ id: 1, size: "S", color: "Navy" }),
    sku({ id: 2, size: "M", color: "Navy" }),
    sku({ id: 3, size: "S", color: "Black", is_in_stock: false }),
    sku({ id: 4, size: "M", color: "Black" }),
  ];

  it("keeps the size the shopper was already looking at", () => {
    expect(skuForColour(skus, "Black", "M")!.id).toBe(4);
  });

  it("falls back to the first purchasable size in that colour", () => {
    // S/Black is out of stock, so asking for S must not return it.
    expect(skuForColour(skus, "Black", "S")!.id).toBe(4);
  });

  it("returns an out-of-stock SKU rather than nothing, so the UI responds", () => {
    const allOut = [sku({ id: 9, color: "Rust", is_in_stock: false })];
    expect(skuForColour(allOut, "Rust", "M")!.id).toBe(9);
  });

  it("returns undefined for a colour that does not exist", () => {
    expect(skuForColour(skus, "Chartreuse", "M")).toBeUndefined();
  });
});
