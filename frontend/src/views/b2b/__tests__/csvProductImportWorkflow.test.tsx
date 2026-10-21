import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../i18n/i18n';
import { BrandCatalogView } from '../BrandCatalogView';
import { CSVProductImportModal } from '../../../components/brands/CSVProductImportModal';
import { brandService } from '../../../services/apiServices';

vi.mock('../../../services/apiServices', () => ({
  brandService: {
    getProfile: vi.fn().mockResolvedValue({ id: 1, brand_name: 'Massimo Dutti' }),
    getAnalytics: vi.fn().mockResolvedValue({ total_products_count: 2 }),
    getProducts: vi.fn().mockResolvedValue([
      {
        id: 101,
        title: 'Tailored Wool Coat',
        category_name: 'Outerwear',
        base_price: 2450,
        currency: 'EGP',
        thumbnail_url: 'https://images.pexels.com/photos/1342609/coat.jpg',
        skus: [
          { id: 201, sku_code: 'SKU-COAT-001', size: 'M', color: 'Navy', stock_level: 15, is_in_stock: true, price_override: null },
        ],
      },
    ]),
    getPlacements: vi.fn().mockResolvedValue([]),
    getStores: vi.fn().mockResolvedValue([
      { id: 1, name: 'Zamalek Flagship Boutique', city: 'Cairo', country: 'Egypt' },
      { id: 2, name: 'Mall of Arabia Boutique', city: 'Giza', country: 'Egypt' },
    ]),
    previewCatalogCSV: vi.fn().mockResolvedValue({
      total_rows: 3,
      valid_rows_count: 2,
      error_rows_count: 1,
      warning_rows_count: 0,
      duplicate_rows_count: 0,
      can_import: true,
      preview_records: [
        {
          row_number: 2,
          status: 'valid',
          action: 'create',
          product_name: 'Classic Linen Shirt',
          sku: 'SKU-SHIRT-001',
          category: 'shirts',
          price: '850.00',
          currency: 'EGP',
          stock: 25,
          size: 'M',
          color: 'White',
        },
        {
          row_number: 3,
          status: 'valid',
          action: 'create',
          product_name: 'Summer Chino Trousers',
          sku: 'SKU-CHINO-002',
          category: 'trousers',
          price: '1100.00',
          currency: 'EGP',
          stock: 14,
          size: 'L',
          color: 'Beige',
        },
        {
          row_number: 4,
          status: 'error',
          action: 'error',
          product_name: 'Invalid Garment',
          sku: 'SKU-ERR-003',
          category: 'unknown_cat',
          price: '-20.00',
          currency: 'EGP',
          stock: 0,
          size: 'M',
          color: 'Red',
          error_message: 'base_price: Price must be positive',
        },
      ],
      errors: [
        { row: 4, field: 'base_price', message: 'Price must be positive', value: '-20.00', suggestion: 'Enter a positive price' },
      ],
      warnings: [],
    }),
    confirmCatalogImport: vi.fn().mockResolvedValue({
      job_id: 88,
      status: 'completed',
      total_rows: 3,
      accepted_rows: 2,
      rejected_rows: 1,
      duplicate_rows: 0,
      notifications_queued: 12,
      notification_recipients_count: 12,
      errors: [],
    }),
    // The API answers text/csv; the client returns a blob plus the server's
    // filename, so the mock must have that shape or the test would be asserting
    // against a contract that no longer exists.
    exportImportErrors: vi.fn().mockResolvedValue({
      blob: new Blob(['Row Number,Field,Submitted Value,Error Reason,Corrective Action\n4,base_price,-20.00,Price must be positive,Enter a positive price'], { type: 'text/csv' }),
      filename: 'confit-import-errors.csv',
    }),
    downloadCatalogTemplate: vi.fn().mockResolvedValue({
      blob: new Blob(['product_name,sku,description,category'], { type: 'text/csv' }),
      filename: 'confit-catalog-template.csv',
    }),
    updateSKU: vi.fn().mockResolvedValue({ status: 'ok' }),
  },
  adminService: {
    getPlatformAnalytics: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('../../../services/apiClient', () => ({
  request: vi.fn().mockImplementation((url: string) => {
    if (url.includes('/partner/catalog/imports')) {
      return Promise.resolve([
        {
          job_id: 88,
          file_name: 'ss26_collection.csv',
          status: 'completed',
          total_rows: 3,
          accepted_rows: 2,
          rejected_rows: 1,
          duplicate_rows: 0,
          created_at: '2026-10-14T20:00:00Z',
        },
      ]);
    }
    if (url.includes('/partner/analytics/conversion')) return Promise.resolve({ per_sku: [] });
    if (url.includes('/brand/products')) return Promise.resolve([]);
    if (url.includes('/partner/stores')) return Promise.resolve([]);
    return Promise.resolve({});
  }),
}));

describe('CSV Product Import, Inventory Management & Notifications (B03)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders exactly one import entry point in the catalog header', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <BrandCatalogView />
        </MemoryRouter>
      </I18nextProvider>
    );

    // The header CTA keeps its established B03 name; the modal it opens is
    // titled "Import Products from CSV". What matters here is that there is ONE
    // entry point — the second button that POSTed straight to the commit
    // endpoint (skipping preview) is gone.
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /Bulk CSV Import/i })).toHaveLength(1);
    });
    expect(screen.queryByRole('button', { name: /Import Products from CSV/i })).toBeNull();
  });

  it('opens CSVProductImportModal and displays upload area with template download link', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CSVProductImportModal
            isOpen={true}
            onClose={vi.fn()}
            onSuccess={vi.fn()}
          />
        </MemoryRouter>
      </I18nextProvider>
    );

    expect(screen.getByText(/Drop CSV catalog file here or click to browse/i)).toBeInTheDocument();
    expect(screen.getByText(/Download template/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Target Boutique Branch/i)).toBeInTheDocument();
    });
  });

  it('progresses to preview step when a valid CSV file is parsed', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CSVProductImportModal
            isOpen={true}
            onClose={vi.fn()}
            onSuccess={vi.fn()}
          />
        </MemoryRouter>
      </I18nextProvider>
    );

    const file = new File(
      ['product_name,sku,category,price,currency,stock_quantity\nShirt,SKU-1,shirts,850,EGP,20'],
      'test_catalog.csv',
      { type: 'text/csv' }
    );

    const input = screen.getByLabelText(/Drop CSV catalog file here or click to browse/i).querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(brandService.previewCatalogCSV).toHaveBeenCalled();
      expect(screen.getByText(/Data Validation & Pre-Import Review/i)).toBeInTheDocument();
      expect(screen.getByText(/Classic Linen Shirt/i)).toBeInTheDocument();
      expect(screen.getByText(/SKU-SHIRT-001/i)).toBeInTheDocument();
      expect(screen.getByText(/850.00 EGP/i)).toBeInTheDocument();
    });
  });

  it('confirms import with notifications and shows completed summary', async () => {
    const handleSuccess = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CSVProductImportModal
            isOpen={true}
            onClose={vi.fn()}
            onSuccess={handleSuccess}
          />
        </MemoryRouter>
      </I18nextProvider>
    );

    const file = new File(['mock content'], 'test.csv', { type: 'text/csv' });
    const input = screen.getByLabelText(/Drop CSV catalog file here or click to browse/i).querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/Confirm & Import/i)).toBeInTheDocument();
    });

    const confirmBtn = screen.getByText(/Confirm & Import/i);
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(brandService.confirmCatalogImport).toHaveBeenCalled();
      expect(screen.getByText(/Import Operation Completed/i)).toBeInTheDocument();
      expect(screen.getByText(/12/i)).toBeInTheDocument(); // Notifications queued
    });

    const doneBtn = screen.getByText(/View in Catalog Table/i);
    fireEvent.click(doneBtn);
    expect(handleSuccess).toHaveBeenCalled();
  });

  /**
   * The behaviours below all guard against the same failure: a modal that tells
   * the brand owner everything is fine while the API disagreed, or a control
   * that silently does nothing.
   */
  const renderModal = (onSuccess = vi.fn()) =>
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CSVProductImportModal isOpen={true} onClose={vi.fn()} onSuccess={onSuccess} />
        </MemoryRouter>
      </I18nextProvider>
    );

  const dropFile = (name = 'catalog.csv') => {
    const file = new File(['mock'], name, { type: 'text/csv' });
    const input = screen
      .getByLabelText(/Drop CSV catalog file here or click to browse/i)
      .querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
  };

  it('does not opt the customer base into emails by default', async () => {
    const { container } = renderModal();
    dropFile();
    await waitFor(() => expect(screen.getByText(/Confirm & Import/i)).toBeInTheDocument());

    const checkbox = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(checkbox).not.toBeNull();
    // The API made notifications an explicit opt-in because a 1,000-row load
    // would otherwise mail every customer on one click.
    expect(checkbox.checked).toBe(false);
  });

  it('surfaces the warnings the server actually reported', async () => {
    (brandService.previewCatalogCSV as any).mockResolvedValueOnce({
      total_rows: 1,
      valid_rows_count: 1,
      error_rows_count: 0,
      warning_rows_count: 1,
      duplicate_rows_count: 0,
      can_import: true,
      preview_records: [
        {
          row_number: 2, status: 'valid', action: 'create', product_name: 'Silk Maxi Dress',
          sku: 'QA-1', category: 'dresses', price: '97.00', currency: 'USD',
          stock: 0, size: 'S', color: 'Crimson', gender: 'womens',
        },
      ],
      errors: [],
      warnings: [
        { row: 2, field: 'stock_level', message: 'Stock is 0, so the storefront hides this product until it is stocked' },
        { row: 1, field: 'materiel', message: 'Column "materiel" is not part of the import contract and will be ignored' },
      ],
    });

    renderModal();
    dropFile();

    await waitFor(() => {
      expect(screen.getByText(/2 warnings/i)).toBeInTheDocument();
      expect(screen.getByText(/storefront hides this product/i)).toBeInTheDocument();
      expect(screen.getByText(/will be ignored/i)).toBeInTheDocument();
    });
  });

  it('refuses to offer confirmation when the server reports a blocker', async () => {
    (brandService.previewCatalogCSV as any).mockResolvedValueOnce({
      total_rows: 1,
      valid_rows_count: 1,
      error_rows_count: 0,
      warning_rows_count: 0,
      duplicate_rows_count: 0,
      can_import: false,
      blocked_reasons: ['Object storage is not configured on this deployment, so no image can be registered'],
      preview_records: [
        {
          row_number: 2, status: 'valid', action: 'create', product_name: 'Shirt',
          sku: 'QA-2', category: 'tops', price: '27.00', currency: 'USD',
          stock: 5, size: 'M', color: 'White',
        },
      ],
      errors: [],
      warnings: [],
    });

    renderModal();
    dropFile();

    await waitFor(() => {
      expect(screen.getByText(/Nothing can be imported yet/i)).toBeInTheDocument();
      expect(screen.getByText(/Object storage is not configured/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Confirm & Import/i).closest('button')).toBeDisabled();
  });

  it('downloads the row errors after an import that rejected rows', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock');
    const revokeObjectURL = vi.fn();
    // jsdom implements neither.
    (URL as any).createObjectURL = createObjectURL;
    (URL as any).revokeObjectURL = revokeObjectURL;

    (brandService.confirmCatalogImport as any).mockResolvedValueOnce({
      job_id: 99,
      status: 'partially_completed',
      total_rows: 2,
      accepted_rows: 1,
      rejected_rows: 1,
      duplicate_rows: 0,
      notifications_queued: 0,
      media_rows_registered: 10,
      rows_missing_title_ar: 0,
      rows_gender_inferred: 0,
      errors: [{ row: 3, field: 'row', message: 'product "Bad Row" was refused: no image_url was supplied' }],
    });

    renderModal();
    dropFile();
    await waitFor(() => expect(screen.getByText(/Confirm & Import/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Confirm & Import/i));

    await waitFor(() => {
      expect(screen.getByText(/1 row\(s\) were not imported/i)).toBeInTheDocument();
      expect(screen.getByText(/no image_url was supplied/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Download Error Report/i));
    await waitFor(() => {
      expect(brandService.exportImportErrors).toHaveBeenCalledWith([
        expect.objectContaining({ row: 3 }),
      ]);
      // A blob URL is the only path that works: the endpoint is POST-only, so
      // the old `window.open(url)` fallback was a guaranteed 405.
      expect(createObjectURL).toHaveBeenCalled();
    });
  });
});
