import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => ({
  brands: vi.fn(), snapshot: vi.fn(), create: vi.fn(), update: vi.fn(),
  deactivate: vi.fn(), reactivate: vi.fn(), updateSku: vi.fn(), addSku: vi.fn(),
  toast: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  adminService: {
    getCatalogBrands: mocks.brands,
    getCatalogSnapshot: mocks.snapshot,
    createCatalogProduct: mocks.create,
    updateCatalogProduct: mocks.update,
    deactivateCatalogProduct: mocks.deactivate,
    reactivateCatalogProduct: mocks.reactivate,
    updateCatalogSKU: mocks.updateSku,
    addCatalogSKU: mocks.addSku,
  },
}));
vi.mock('../../stores/uiStore', () => ({ useUIStore: () => ({ showToast: mocks.toast }) }));

import { AdminCatalogView } from '../b2b/AdminCatalogView';

const brand = {
  id: 7, brand_name: 'Verified Atelier', slug: 'verified-atelier', is_verified: true,
  product_count: 1, active_product_count: 1, sku_count: 1, store_count: 1,
  placement_count: 1,
};
const product = {
  id: 91, brand_id: 7, brand_name: 'Verified Atelier', category_id: 3,
  category_name: 'Outerwear', category_slug: 'outerwear', title: 'Structured Coat',
  title_ar: 'معطف منظم', slug: 'structured-coat', description: 'Wool coat',
  description_ar: 'معطف صوف', base_price: 2400, currency: 'EGP', material: 'Wool',
  care_instructions: 'Dry clean', color_family: 'Navy', dominant_hex: '#1B1F3B',
  thumbnail_url: 'https://example.test/coat.jpg', images: [], style_tags: ['minimal'],
  occasion_tags: ['work'], is_featured: false, is_active: true,
  created_at: '2026-09-26T00:00:00Z',
  skus: [{ id: 301, product_id: 91, sku_code: 'COAT-NVY-M', size: 'M', color: 'Navy', color_hex: '#1B1F3B', price_override: null, stock_level: 9, is_in_stock: true }],
};
const snapshot = {
  brand, products: [product],
  inventory: [{ product_id: 91, title: 'Structured Coat', thumbnail_url: product.thumbnail_url, is_active: true, total_stock: 9, skus: [{ ...product.skus[0], store_inventories: [{ id: 1, store_id: 8, store_name: 'Giza Flagship', quantity: 7, reserved: 1, available: 6 }] }] }],
  placements: [{ id: 11, product_id: 91, product_title: 'Structured Coat', status: 'active', daily_budget: 200, clicks: 4, conversions: 1 }],
  stores: [{ id: 8, name: 'Giza Flagship' }], imports: [],
  categories: [{ id: 3, name: 'Outerwear', name_ar: 'ملابس خارجية', slug: 'outerwear' }],
  generated_at: '2026-09-26T00:00:00Z',
};

const renderView = () => render(<MemoryRouter><AdminCatalogView /></MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.brands.mockResolvedValue([brand]);
  mocks.snapshot.mockResolvedValue(snapshot);
  mocks.update.mockResolvedValue({ status: 'updated', product_id: 91, brand_id: 7 });
  mocks.deactivate.mockResolvedValue({ status: 'deactivated', product_id: 91, placements_cancelled: 1 });
  mocks.updateSku.mockResolvedValue({ status: 'updated', sku_id: 301, stock_level: 12 });
});

describe('explicit admin catalog', () => {
  it('loads a selected brand snapshot and exposes real operational sections', async () => {
    renderView();
    expect(await screen.findByText('Structured Coat')).toBeTruthy();
    expect(mocks.brands).toHaveBeenCalledTimes(1);
    expect(mocks.snapshot).toHaveBeenCalledWith(7);
    expect(screen.getByRole('tab', { name: /Products/ })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /Inventory/ })).toBeTruthy();
    expect(screen.queryByText(/Telemetry unavailable/)).toBeNull();
  });

  it('edits product metadata through the explicit brand-scoped admin API', async () => {
    renderView();
    await screen.findByText('Structured Coat');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('English title'), { target: { value: 'Structured Coat Revised' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(
      7, 91, expect.objectContaining({ title: 'Structured Coat Revised', base_price: 2400 }),
    ));
    expect(mocks.toast).toHaveBeenCalledWith('Product details saved.', 'success');
  });

  it('uses reversible deactivation instead of fabricating a hard-delete success', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderView();
    await screen.findByText('Structured Coat');
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(mocks.deactivate).toHaveBeenCalledWith(7, 91));
    expect(mocks.toast).toHaveBeenCalledWith(
      'Product deactivated; historical data was retained.', 'success',
    );
  });

  it('updates SKU stock from the same database-backed snapshot', async () => {
    renderView();
    await screen.findByText('Structured Coat');
    fireEvent.click(screen.getByRole('tab', { name: /Inventory/ }));
    fireEvent.change(screen.getByLabelText('Stock for COAT-NVY-M'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(mocks.updateSku).toHaveBeenCalledWith(
      7, 301, { stock_level: 12, price_override: null },
    ));
  });
});
