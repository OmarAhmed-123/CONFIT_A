import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../i18n/i18n';
import { BrandRegistrationView } from '../BrandRegistrationView';
import { BrandBranchesView } from '../BrandBranchesView';
import { BrandDashboardView } from '../BrandDashboardView';
import { brandService } from '../../../services/apiServices';

vi.mock('../../../services/apiServices', () => ({
  brandService: {
    registerBrand: vi.fn(),
    getStores: vi.fn(),
    createStore: vi.fn(),
    updateStore: vi.fn(),
    deleteStore: vi.fn(),
    getOnboardingStatus: vi.fn(),
    getProfile: vi.fn(),
    getAnalytics: vi.fn(),
  },
  authService: {
    getMe: vi.fn(),
  },
}));

vi.mock('../../../viewmodels/useBrandViewModel', () => ({
  useBrandViewModel: () => ({
    profile: {
      id: 1,
      brand_name: 'Atelier Noir',
      is_verified: true,
      tier: 'artisan',
      commission_rate: 15,
    },
    analytics: {
      total_products_count: 42,
      total_skus_count: 120,
      total_views: 1250,
      total_tryons: 450,
      total_purchases: 85,
      return_rate_before_vton: 32.5,
      return_rate_after_vton: 11.2,
      methodology: 'Verified against telemetry DB',
      outfit_appearance_rankings: [],
    },
    fetchErrors: {},
    isLoading: false,
    loadFailed: false,
    refresh: vi.fn(),
  }),
}));

const renderWithProviders = (ui: React.ReactElement, initialRoute = '/') => {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[initialRoute]}>
        {ui}
      </MemoryRouter>
    </I18nextProvider>
  );
};

describe('Automated Brand Registration Flow (BrandRegistrationView)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders registration form fields and Logo #3 header', () => {
    const { container } = renderWithProviders(<BrandRegistrationView />);
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(container.querySelector('input[name="brandName"]')).toBeInTheDocument();
    expect(container.querySelector('input[name="email"]')).toBeInTheDocument();
    expect(container.querySelector('input[name="password"]')).toBeInTheDocument();
    expect(container.querySelector('input[name="fullName"]')).toBeInTheDocument();
  });

  it('validates brand name and email client-side before submission', async () => {
    renderWithProviders(<BrandRegistrationView />);
    
    const submitBtn = screen.getByRole('button', { name: /Register Brand & Establish Workspace/i });
    fireEvent.click(submitBtn);

    expect(brandService.registerBrand).not.toHaveBeenCalled();
  });

  it('calls brandService.registerBrand on valid submission and displays success confirmation', async () => {
    vi.mocked(brandService.registerBrand).mockResolvedValueOnce({
      status: 'created',
      message: 'Brand registered successfully',
      access_token: 'mock-b2b-jwt-token',
      refresh_token: 'mock-refresh-token',
      token_type: 'bearer',
      next_step: '/b2b/onboarding',
      is_verified: false,
      brand: {
        id: 99,
        brand_name: 'Atelier Noir',
        slug: 'atelier-noir',
        user_id: 50,
        is_verified: false,
        publication_status: 'draft',
        commission_rate: 15,
        return_rate_benchmark: 25.0,
        current_return_rate: 12.0,
        created_at: '2026-01-01T00:00:00Z',
      },
    });

    const { container } = renderWithProviders(<BrandRegistrationView />);

    fireEvent.change(container.querySelector('input[name="brandName"]')!, {
      target: { value: 'Atelier Noir' },
    });
    fireEvent.change(container.querySelector('input[name="email"]')!, {
      target: { value: 'director@ateliernoir.com' },
    });
    fireEvent.change(container.querySelector('input[name="password"]')!, {
      target: { value: 'SecureLuxuryPassword2026!' },
    });
    fireEvent.change(container.querySelector('input[name="fullName"]')!, {
      target: { value: 'Jean-Luc Picard' },
    });
    fireEvent.change(container.querySelector('input[name="city"]')!, {
      target: { value: 'Cairo' },
    });

    const submitBtn = screen.getByRole('button', { name: /Register Brand & Establish Workspace/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(brandService.registerBrand).toHaveBeenCalledWith(
        expect.objectContaining({
          brand_name: 'Atelier Noir',
          email: 'director@ateliernoir.com',
          full_name: 'Jean-Luc Picard',
          city: 'Cairo',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/Brand Profile Created Successfully/i)).toBeInTheDocument();
      expect(screen.getByText(/Atelier Noir/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Complete Your Brand Setup/i })).toBeInTheDocument();
    });
  });
});

describe('Branch Management Hub (BrandBranchesView)', () => {
  const mockStores = [
    {
      id: 1,
      brand_id: 1,
      name: 'Zamalek Flagship Boutique',
      name_ar: 'بوتيك الزمالك الرئيسي',
      store_code: 'ZAM-01',
      address: '15 Brazil Street',
      city: 'Cairo',
      state: 'Cairo Governorate',
      postal_code: '11211',
      country: 'Egypt',
      latitude: 30.0561,
      longitude: 31.2215,
      phone: '+20 2 2735 0000',
      email: 'zamalek@ateliernoir.com',
      google_maps_url: 'https://www.google.com/maps/search/?api=1&query=30.0561,31.2215',
      is_bopis_enabled: true,
      is_active: true,
      is_location_verified: true,
      inventory_items_count: 14,
      total_stock_units: 82,
      pickup_instructions: 'Proceed to concierge desk on ground floor with verification code.',
      created_at: '2026-01-01T00:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(brandService.getStores).mockResolvedValue(mockStores);
  });

  it('renders branch list and KPI cards', async () => {
    renderWithProviders(<BrandBranchesView />);

    await waitFor(() => {
      expect(screen.getByText('Zamalek Flagship Boutique')).toBeInTheDocument();
      expect(screen.getByText(/15 Brazil Street/i)).toBeInTheDocument();
      expect(screen.getByText('BOPIS Ready')).toBeInTheDocument();
    });

    // Check Google Maps link
    const mapsLink = screen.getByRole('link', { name: /Google Maps/i });
    expect(mapsLink).toHaveAttribute('href', expect.stringContaining('google.com/maps'));
    expect(mapsLink).toHaveAttribute('href', expect.stringContaining('30.0561,31.2215'));
  });

  it('validates coordinate range (-90 to 90, -180 to 180)', async () => {
    const { container } = renderWithProviders(<BrandBranchesView />);

    await waitFor(() => {
      expect(screen.getByText('Zamalek Flagship Boutique')).toBeInTheDocument();
    });

    // Open Add Branch modal
    fireEvent.click(screen.getByRole('button', { name: /Add New Boutique Branch/i }));

    expect(screen.getByText(/Add Physical Boutique Branch/i)).toBeInTheDocument();

    // Fill valid store name and address
    fireEvent.change(container.querySelector('input[name="name"]')!, {
      target: { value: 'Downtown Boutique' },
    });
    fireEvent.change(container.querySelector('input[name="address"]')!, {
      target: { value: 'Tahrir Square' },
    });

    // Invalid latitude (> 90)
    const latInput = container.querySelector('input[name="latitude"]') as HTMLInputElement;
    fireEvent.change(latInput, { target: { value: '95.5' } });

    fireEvent.click(screen.getByRole('button', { name: /Save Branch Location/i }));

    await waitFor(() => {
      expect(screen.getByText(/Latitude must be between -90 and 90/i)).toBeInTheDocument();
    });

    expect(brandService.createStore).not.toHaveBeenCalled();
  });
});

describe('Owner Dashboard Guided Onboarding (BrandDashboardView)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(brandService.getOnboardingStatus).mockResolvedValue({
      brand_id: 1,
      brand_name: 'Atelier Noir',
      is_verified: true,
      is_published: true,
      publication_status: 'active',
      completion_percentage: 86,
      total_steps_count: 7,
      completed_steps_count: 6,
      stores_count: 1,
      products_count: 42,
      active_promotions_count: 2,
      welcome_message: 'Welcome back! Your brand is registered and visible to customers.',
      primary_cta_label: 'Manage Catalog & Availability',
      primary_cta_url: '/b2b/catalog',
      steps: [
        {
          key: 'brand_profile',
          title: 'Brand Profile Identity',
          description: 'Official brand name, logo, aesthetic bio, and contact.',
          is_completed: true,
          action_url: '/b2b/profile',
        },
        {
          key: 'first_branch',
          title: 'First Physical Branch Location',
          description: 'Store location with verified street address and GPS coordinates.',
          is_completed: true,
          action_url: '/b2b/branches',
        },
        {
          key: 'bopis_readiness',
          title: 'BOPIS Click & Collect Setup',
          description: 'In-store pickup instructions and estimated fulfillment lead time.',
          is_completed: true,
          action_url: '/b2b/branches',
        },
        {
          key: 'product_catalog',
          title: 'Product Catalog Ingestion',
          description: 'At least one verified product in the brand catalog.',
          is_completed: true,
          action_url: '/b2b/catalog',
        },
        {
          key: 'branch_inventory',
          title: 'Branch Inventory Availability',
          description: 'Stock levels synced to physical branch boutiques.',
          is_completed: true,
          action_url: '/b2b/inventory',
        },
        {
          key: 'sponsored_placements',
          title: 'Discovery & Sponsored Placements',
          description: 'Promotional campaigns or verified artisan showcase.',
          is_completed: true,
          action_url: '/b2b/placements',
        },
        {
          key: 'publication_review',
          title: 'Customer Discovery Publication',
          description: 'Verified status approved by platform moderation.',
          is_completed: true,
          action_url: '/brands/atelier-noir',
        },
      ],
    });
  });

  it('renders guided onboarding checklist with steps and progress percentage', async () => {
    renderWithProviders(<BrandDashboardView />);

    await waitFor(() => {
      expect(screen.getByText(/Brand Onboarding & Setup/i)).toBeInTheDocument();
      expect(screen.getByText(/86%/i)).toBeInTheDocument();
      expect(screen.getByText(/Setup Checklist \(6 of 7 completed\)/i)).toBeInTheDocument();
      expect(screen.getByText(/First Physical Branch Location/i)).toBeInTheDocument();
    });
  });
});
