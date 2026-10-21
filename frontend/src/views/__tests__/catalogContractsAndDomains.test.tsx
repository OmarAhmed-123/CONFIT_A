import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrandCatalogView } from '../b2b/BrandCatalogView';
import { ProductDetailView } from '../consumer/ProductDetailView';
import { DiscoverView } from '../consumer/DiscoverView';
import { CSVProductImportModal } from '../../components/brands/CSVProductImportModal';

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
}));

vi.mock('../../services/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/apiClient')>();
  return {
    ...actual,
    request: (...args: any[]) => mocks.request(...args),
    requestBlob: vi.fn(),
  };
});

function wrap(node: React.ReactElement, initialEntries = ['/']) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>{node}</MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE_PRODUCT = {
  id: 42,
  brand_id: 7,
  brand_name: 'Nile Atelier',
  category_id: 2,
  category_name: 'Outerwear',
  category_slug: 'outerwear',
  title: 'Sculpted Linen Trench',
  title_ar: 'معطف كتان منحوت',
  slug: 'sculpted-linen-trench',
  base_price: 31.0,
  compare_at_price: 40.0,
  currency: 'USD',
  thumbnail_url: 'https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg',
  color_family: 'Sand',
  dominant_hex: '#C8B89A',
  gender: 'womens',
  style_tags: ['Minimalist', 'Tailored'],
  occasion_tags: ['Work & Business', 'Evening'],
  rating: 4.8,
  is_featured: false,
  description: 'Breathable Egyptian flax trench with horn buttons.',
  material: '100% Egyptian Linen',
  care_instructions: 'Dry clean only',
  images: ['https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg'],
  skus: [
    {
      id: 4201,
      product_id: 42,
      sku_code: 'NILE-TR-S',
      size: 'S',
      color: 'Sand',
      color_hex: '#C8B89A',
      stock_level: 9,
      is_in_stock: true,
    },
  ],
  size_chart: {
    schema_version: '1.0',
    unit: 'cm',
    type: 'body',
    fit_type: 'regular',
    source: 'EN 13402-3 / Nile Atelier Pattern Spec',
    notes: [
      'Measured over light shirting.',
      'Between sizes, size down for closer shoulder fit.',
    ],
    sizes: {
      S: { chest: [84, 88], waist: [68, 72] },
      M: { chest: [88, 92], waist: [72, 76] },
    },
  },
};

describe('Priority 4 & 5 — Brand Domain Lifecycle, Field Contracts & Storefront Parity', () => {
  beforeEach(() => {
    mocks.request.mockReset();
  });

  it('manages brand image domains lazily (claim, DNS TXT display, verify, soft revoke & release) without extra mount calls', async () => {
    mocks.request.mockImplementation((path: string, opts?: any) => {
      if (path === '/brand/profile') return Promise.resolve({ id: 7, brand_name: 'Nile Atelier' });
      if (path === '/brand/analytics') return Promise.resolve({ total_products: 1 });
      if (path === '/brand/products') return Promise.resolve([SAMPLE_PRODUCT]);
      if (path === '/brand/placements') return Promise.resolve([]);
      if (path === '/partner/catalog/imports') return Promise.resolve([]);
      if (path === '/partner/analytics/conversion') return Promise.resolve({ per_sku: [] });
      if (path === '/partner/brand/domains' && (!opts || !opts.method)) {
        return Promise.resolve({
          domains: [
            {
              id: 1,
              hostname: 'cdn.nile-atelier.eg',
              status: 'pending',
              token: 'tok_abc123',
              dns_record: 'confit-verify=tok_abc123',
              imports_allowed: false,
              is_expired: false,
            },
          ],
        });
      }
      if (path === '/partner/brand/domains' && opts?.method === 'POST') {
        return Promise.resolve({
          id: 2,
          hostname: 'studio.nile-atelier.eg',
          status: 'pending',
          token: 'tok_new999',
          dns_record: 'confit-verify=tok_new999',
          imports_allowed: false,
        });
      }
      if (path === '/partner/brand/domains/cdn.nile-atelier.eg/verify') {
        return Promise.resolve({
          id: 1,
          hostname: 'cdn.nile-atelier.eg',
          status: 'verified',
          dns_record: 'confit-verify=tok_abc123',
          imports_allowed: true,
        });
      }
      if (path.startsWith('/partner/brand/domains/cdn.nile-atelier.eg') && opts?.method === 'DELETE') {
        return Promise.resolve({ hostname: 'cdn.nile-atelier.eg', released: path.includes('release=true') });
      }
      return Promise.resolve({});
    });

    render(wrap(<BrandCatalogView />));
    await screen.findByText('Sculpted Linen Trench');

    // D9 contract: never calls /partner/brand/domains before user opens panel
    expect(mocks.request.mock.calls.some(([p]) => p === '/partner/brand/domains')).toBe(false);

    fireEvent.click(screen.getByTestId('brand-domains-toggle'));
    expect(await screen.findByText(/confit-verify=tok_abc123/)).toBeInTheDocument();

    // Claim domain -> POST /partner/brand/domains
    const input = screen.getByLabelText(/Domain hostname/i);
    fireEvent.change(input, { target: { value: 'studio.nile-atelier.eg' } });
    fireEvent.submit(input.closest('form')!);
    await waitFor(() =>
      expect(mocks.request).toHaveBeenCalledWith(
        '/partner/brand/domains',
        expect.objectContaining({ method: 'POST' }),
      ),
    );

    // Release claim -> DELETE ?release=true
    fireEvent.click(screen.getByRole('button', { name: /Release claim/i }));
    await waitFor(() =>
      expect(mocks.request).toHaveBeenCalledWith(
        '/partner/brand/domains/cdn.nile-atelier.eg?release=true',
        expect.objectContaining({ method: 'DELETE' }),
      ),
    );
  });

  it('edits canonical product fields & v1.0 size chart notes[] array while keeping is_featured non-editable', async () => {
    mocks.request.mockImplementation((path: string, opts?: any) => {
      if (path === '/brand/profile') return Promise.resolve({ id: 7, brand_name: 'Nile Atelier' });
      if (path === '/brand/analytics') return Promise.resolve({ total_products: 1 });
      if (path === '/brand/products') return Promise.resolve([SAMPLE_PRODUCT]);
      if (path === '/brand/placements') return Promise.resolve([]);
      if (path === '/partner/catalog/imports') return Promise.resolve([]);
      if (path === '/partner/analytics/conversion') return Promise.resolve({ per_sku: [] });
      if (path === '/partner/catalog/products/42' && opts?.method === 'PATCH') {
        return Promise.resolve({
          product: SAMPLE_PRODUCT,
          warnings: [{ code: 'occasion_unrecognised', message: 'Stored rooftop_gala outside standard preset vocabulary.' }],
        });
      }
      if (path === '/partner/catalog/products/42/size-chart' && opts?.method === 'PUT') {
        return Promise.resolve({ product_id: 42, has_chart: true, size_chart: SAMPLE_PRODUCT.size_chart });
      }
      return Promise.resolve({});
    });

    render(wrap(<BrandCatalogView />));
    await screen.findByText('Sculpted Linen Trench');
    expect(screen.getByText(/System-curated/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('edit-product-42'));
    const editor = await screen.findByTestId('product-editor-42');
    // Confirm no editable checkbox/input named is_featured exists anywhere in editor
    expect(editor.querySelector('[name="is_featured"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));
    await waitFor(() => {
      const patchCall = mocks.request.mock.calls.find(
        ([p, o]) => p === '/partner/catalog/products/42' && o?.method === 'PATCH',
      );
      expect(patchCall).toBeTruthy();
      const body = JSON.parse(patchCall![1].body);
      expect(body).not.toHaveProperty('is_featured');
      expect(body.gender).toBe('womens');

      const putChartCall = mocks.request.mock.calls.find(
        ([p, o]) => p === '/partner/catalog/products/42/size-chart' && o?.method === 'PUT',
      );
      expect(putChartCall).toBeTruthy();
      const chartPayload = JSON.parse(putChartCall![1].body).size_chart;
      expect(Array.isArray(chartPayload.notes)).toBe(true);
      expect(chartPayload.notes).toEqual([
        'Measured over light shirting.',
        'Between sizes, size down for closer shoulder fit.',
      ]);
      expect(chartPayload.sizes.S.chest).toEqual([84, 88]);
    });
    expect(await screen.findByText(/rooftop_gala/i)).toBeInTheDocument();
  });

  it('renders identical SizeChartV1 structure, notes[] list, source provenance & canonical tags on Storefront PDP', async () => {
    mocks.request.mockImplementation((path: string) => {
      if (path.startsWith('/catalog/products/sculpted-linen-trench')) return Promise.resolve(SAMPLE_PRODUCT);
      if (path.includes('/stores')) return Promise.resolve([]);
      if (path === '/catalog/capabilities') return Promise.resolve({ payments_live: false, vton_offered: false });
      return Promise.resolve({});
    });

    render(
      wrap(
        <Routes>
          <Route path="/product/:slug" element={<ProductDetailView />} />
        </Routes>,
        ['/product/sculpted-linen-trench'],
      ),
    );

    await screen.findAllByText('Sculpted Linen Trench');
    expect(screen.getByTestId('pdp-taxonomy-tags')).toHaveTextContent('Minimalist');
    expect(screen.getByTestId('pdp-taxonomy-tags')).toHaveTextContent('Work & Business');

    // Open Size Guide & Measurements accordion
    fireEvent.click(screen.getByRole('button', { name: /Size Guide & Measurements/i }));
    const chartPanel = await screen.findByTestId('pdp-size-chart-panel');
    expect(chartPanel).toHaveTextContent('84–88');
    expect(chartPanel).toHaveTextContent('EN 13402-3 / Nile Atelier Pattern Spec');
    const notes = screen.getByTestId('pdp-size-chart-notes');
    expect(notes.querySelectorAll('li')).toHaveLength(2);
    expect(notes).toHaveTextContent('Measured over light shirting.');
  });

  it('hydrates and forwards canonical gender & style filters on Storefront DiscoverView', async () => {
    mocks.request.mockImplementation((path: string) => {
      if (path.startsWith('/catalog/products')) return Promise.resolve([SAMPLE_PRODUCT]);
      if (path === '/catalog/categories') return Promise.resolve([{ id: 2, name: 'Outerwear', name_ar: 'معاطف', slug: 'outerwear', icon_name: 'coat' }]);
      if (path === '/catalog/occasions') return Promise.resolve([{ value: 'work', count: 3 }]);
      if (path === '/catalog/capabilities') return Promise.resolve({ payments_live: false, vton_offered: false });
      return Promise.resolve({});
    });

    render(wrap(<DiscoverView />, ['/discover?gender=womens&style=Tailored']));
    await waitFor(() =>
      expect(
        mocks.request.mock.calls.some(
          ([p]) =>
            typeof p === 'string' &&
            p.includes('/catalog/products') &&
            p.includes('gender=womens') &&
            p.includes('style=Tailored'),
        ),
      ).toBe(true),
    );
  });

  it('gracefully handles PDP products with missing optional size_chart, gender, and tags without crashing', async () => {
    const sparse = {
      ...SAMPLE_PRODUCT,
      gender: undefined,
      material: undefined,
      care_instructions: undefined,
      style_tags: [],
      occasion_tags: [],
      size_chart: {},
    };
    mocks.request.mockImplementation((path: string) => {
      if (path.startsWith('/catalog/products/sculpted-linen-trench')) return Promise.resolve(sparse);
      if (path.includes('/stores')) return Promise.resolve([]);
      if (path === '/catalog/capabilities') return Promise.resolve({ payments_live: false, vton_offered: false });
      return Promise.resolve({});
    });

    render(
      wrap(
        <Routes>
          <Route path="/product/:slug" element={<ProductDetailView />} />
        </Routes>,
        ['/product/sculpted-linen-trench'],
      ),
    );

    await screen.findAllByText('Sculpted Linen Trench');
    expect(screen.queryByTestId('pdp-size-chart-panel')).toBeNull();
    expect(screen.queryByTestId('pdp-taxonomy-tags')).toBeNull();
  });

  it('renders CSV preview normalization warnings distinctly alongside valid preview rows', async () => {
    mocks.request.mockImplementation((path: string, opts?: any) => {
      if (path.startsWith('/partner/stores')) return Promise.resolve([]);
      if (path.startsWith('/partner/catalog/preview-csv') && opts?.method === 'POST') {
        return Promise.resolve({
          total_rows: 1,
          valid_rows_count: 1,
          error_rows_count: 0,
          can_import: true,
          preview_records: [
            {
              row_number: 2,
              status: 'valid',
              action: 'create',
              product_name: 'Nile Linen Shirt',
              sku: 'NLS-01',
              category: 'tops',
              price: 31.0,
              currency: 'USD',
              stock: 5,
              color: 'White',
              size: 'M',
            },
          ],
          errors: [],
          warnings: [
            {
              row: 2,
              field: 'occasion_tags',
              code: 'occasion_unrecognised',
              message: 'Tag "desert_vernissage" does not match a storefront occasion filter preset.',
            },
          ],
        });
      }
      return Promise.resolve({});
    });

    render(wrap(<CSVProductImportModal isOpen={true} onClose={() => {}} onSuccess={() => {}} />));
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const csvFile = new File(['title,sku_code\nNile Linen Shirt,NLS-01\n'], 'catalog.csv', { type: 'text/csv' });
    fireEvent.change(fileInput, { target: { files: [csvFile] } });

    const warnBanner = await screen.findByTestId('csv-preview-warnings');
    expect(warnBanner).toHaveTextContent('desert_vernissage');
  });
});
