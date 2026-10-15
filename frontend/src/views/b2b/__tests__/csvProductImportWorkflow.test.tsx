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
    exportImportErrors: vi.fn().mockResolvedValue('Row Number,Field,Submitted Value,Error Reason,Corrective Action\n4,base_price,-20.00,Price must be positive,Enter a positive price'),
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

  it('renders the "Import Products from CSV" action in the catalog header', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <BrandCatalogView />
        </MemoryRouter>
      </I18nextProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Import Products from CSV/i)).toBeInTheDocument();
    });
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
});
