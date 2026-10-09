/**
 * B03 — Catalog & SKU Management re-pass (docs/B03_CATALOG_MANAGEMENT_REDESIGN.md).
 *
 *   · D3  window.alert() file validation      → inline role="alert", alert never called
 *   · D8  fire-and-forget import jobs         → non-terminal job is polled to a terminal
 *                                                state and the list is refreshed
 *   · D9  tagging backend never exposed       → dry-run preview (confidence + unresolved
 *                                                axes) then explicit apply; 429 honest
 *   · contracts preserved: Edit Stock / Save / Stock for {sku} / {n} units
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';

import i18n from '../../i18n/i18n';

const mocks = vi.hoisted(() => ({ vm: {} as any, request: vi.fn() }));
vi.mock('../../viewmodels/useBrandViewModel', () => ({ useBrandViewModel: () => mocks.vm }));
vi.mock('../../services/apiClient', () => ({ request: (...a: unknown[]) => mocks.request(...a) }));

import { BrandCatalogView } from '../b2b/BrandCatalogView';

const product = {
  id: 9, title: 'Coat', category_name: 'Outerwear', currency: 'USD', base_price: 20,
  thumbnail_url: 'https://example.com/coat.jpg',
  skus: [{ id: 11, sku_code: 'REAL-SKU', size: 'M', color: 'Navy', color_hex: '#000080', stock_level: 5, price_override: null, is_in_stock: true }],
};

const baseVm = (over: Record<string, unknown> = {}) => ({
  profile: null,
  analytics: null,
  products: [product],
  placements: [],
  importJobs: [],
  conversionPerSku: [],
  fetchErrors: {},
  fetchErrorMeta: {},
  loadFailed: false,
  isLoading: false,
  isUploading: false,
  refresh: vi.fn(),
  updateSKUInventory: vi.fn().mockResolvedValue(true),
  uploadCatalogCSV: vi.fn(),
  getImportJobStatus: vi.fn(),
  ...over,
});

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.vm = baseVm();
  return i18n.changeLanguage('en');
});
afterEach(() => i18n.changeLanguage('en'));

const ui = () => (
  <I18nextProvider i18n={i18n}>
    <BrandCatalogView />
  </I18nextProvider>
);

describe('B03 catalog management', () => {
  it('D3: a non-CSV file renders an inline alert; window.alert is never used', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Bulk CSV Import' }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['x'], 'catalog.txt', { type: 'text/plain' });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });
    expect(alertSpy).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByText('File must be CSV')).toBeTruthy();
    alertSpy.mockRestore();
  });

  it('D8: a non-terminal upload job is polled until terminal, then the data refreshes', async () => {
    let polls = 0;
    mocks.vm.uploadCatalogCSV.mockResolvedValue({ job_id: 5, status: 'processing', total_rows: 1, accepted_rows: 0, rejected_rows: 0, duplicate_rows: 0 });
    mocks.vm.getImportJobStatus.mockImplementation(async () => {
      polls += 1;
      return { job_id: 5, status: polls > 1 ? 'completed' : 'processing', total_rows: 1, accepted_rows: 1, rejected_rows: 0, duplicate_rows: 0 };
    });
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Bulk CSV Import' }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['a,b\n1,2'], 'catalog.csv', { type: 'text/csv' });
    await act(async () => { fireEvent.change(input, { target: { files: [file] } }); });
    // the poller runs on a real 2.5s cadence: first poll still processing,
    // second poll terminal -> refresh.
    await waitFor(() => expect(polls).toBeGreaterThan(1), { timeout: 8000 });
    await waitFor(() => expect(mocks.vm.refresh).toHaveBeenCalled(), { timeout: 8000 });
    expect(screen.getByText(/Last import: Completed/)).toBeTruthy();
  }, 12000);

  it('D9: auto-tag dry-run previews confidence and unresolved axes; apply writes for real', async () => {
    mocks.request.mockResolvedValueOnce({
      status: 'success', dry_run: true, quality: 'good', models: ['FashionCLIP', 'GLiNER2'],
      tags: [{ axis: 'color_family', value: 'Navy', confidence: 0.91 }],
      axes_unresolved: [{ axis: 'material', reason: 'below threshold' }],
      disclaimer: 'AI suggestions, review before applying.',
    });
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Auto-tag with AI' }));
    await screen.findByText(/91% confidence/);
    expect(screen.getByText(/material \(below threshold\)/)).toBeTruthy();
    mocks.request.mockResolvedValueOnce({
      status: 'success', dry_run: false, quality: 'good', models: [],
      tags: [], axes_unresolved: [], applied: [{ field: 'color_family' }], skipped: [{ field: 'material' }],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply tags' }));
    await screen.findByText(/Applied/);
    expect(mocks.request).toHaveBeenLastCalledWith('/brand/products/9/auto-tag?dry_run=false', { method: 'POST' });
  });

  it('D9: a 429 on auto-tag renders the throttled copy, not a generic crash', async () => {
    mocks.request.mockRejectedValueOnce({ status: 429, message: 'rate limited' });
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Auto-tag with AI' }));
    await screen.findByText(i18n.t('b2b.cat.tag_throttled'));
  });

  it('loading renders the geometry skeleton with role=status', () => {
    mocks.vm = baseVm({ isLoading: true });
    const { container } = render(ui());
    expect(container.querySelector('[role="status"] .skeleton-shimmer')).toBeTruthy();
  });

  it('contracts: Edit Stock / Save / Stock-for labels / units copy preserved', async () => {
    render(ui());
    fireEvent.click(screen.getByText('Edit Stock'));
    expect(screen.getByLabelText('Stock for REAL-SKU')).toBeTruthy();
    expect(screen.getByLabelText('Price override for REAL-SKU')).toBeTruthy();
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(mocks.vm.updateSKUInventory).toHaveBeenCalledWith(11, 5, null));
  });

  it('stock renders as "{n} units" outside edit mode', () => {
    render(ui());
    expect(screen.getByText('5 units')).toBeTruthy();
  });
});
