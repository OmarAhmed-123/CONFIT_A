import { Product, ProductSKU } from "../models";
import { catalogService } from "../services/apiServices";

export function getPurchasableSkuFromProduct(
  product: Product,
): ProductSKU | null {
  const skus = product.skus ?? [];
  return (
    skus.find((sku) => sku.is_in_stock && sku.stock_level > 0) ??
    skus[0] ??
    null
  );
}

/**
 * Catalog list rows intentionally omit SKU arrays. Any cart path that starts
 * from a list card must resolve the product detail first and use a real SKU
 * from the backend. This helper centralizes that rule so UI code never invents
 * SKU ids or silently treats a SKU-less card as addable.
 */
export async function resolvePurchasableSku(
  product: Product,
): Promise<ProductSKU | null> {
  const inline = getPurchasableSkuFromProduct(product);
  if (inline) return inline;

  const detail = await catalogService.getProductDetail(product.slug);
  return getPurchasableSkuFromProduct(detail);
}
