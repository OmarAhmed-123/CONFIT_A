import { describe, expect, it, vi } from 'vitest';
import { getPurchasableSkuFromProduct, resolvePurchasableSku } from '../catalogSku';
import { catalogService } from '../../services/apiServices';
import type { Product } from '../../models';

vi.mock('../../services/apiServices', () => ({
  catalogService: {
    getProductDetail: vi.fn(),
  },
}));

const product = (overrides: Partial<Product> = {}): Product => ({
  id: 1,
  brand_id: 1,
  brand_name: 'Brand',
  category_id: 1,
  category_name: 'Outerwear',
  title: 'Real product',
  title_ar: 'Real product',
  slug: 'real-product',
  base_price: 100,
  currency: 'USD',
  thumbnail_url: 'https://example.test/image.jpg',
  color_family: 'Navy',
  dominant_hex: '#1B1F3B',
  style_tags: [],
  occasion_tags: [],
  rating: 4.5,
  is_featured: false,
  ...overrides,
});

describe('catalog SKU resolution', () => {
  it('uses an inline in-stock SKU when the product detail already carries real SKU data', () => {
    const sku = getPurchasableSkuFromProduct(
      product({
        skus: [
          { id: 10, product_id: 1, sku_code: 'OOS', size: 'S', color: 'Navy', color_hex: '#1B1F3B', stock_level: 0, is_in_stock: false },
          { id: 11, product_id: 1, sku_code: 'INSTOCK', size: 'M', color: 'Navy', color_hex: '#1B1F3B', stock_level: 2, is_in_stock: true },
        ],
      })
    );
    expect(sku?.id).toBe(11);
  });

  it('fetches product detail for catalog-list products instead of fabricating a SKU id', async () => {
    vi.mocked(catalogService.getProductDetail).mockResolvedValueOnce(
      product({
        skus: [{ id: 99, product_id: 1, sku_code: 'REAL', size: 'M', color: 'Navy', color_hex: '#1B1F3B', stock_level: 3, is_in_stock: true }],
      })
    );

    const sku = await resolvePurchasableSku(product({ skus: undefined }));
    expect(catalogService.getProductDetail).toHaveBeenCalledWith('real-product');
    expect(sku?.id).toBe(99);
  });
});
