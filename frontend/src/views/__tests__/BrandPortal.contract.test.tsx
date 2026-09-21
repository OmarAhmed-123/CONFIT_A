import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mocks = vi.hoisted(() => ({ vm: {} as any, auth: {} as any, create: vi.fn(), update: vi.fn(), request: vi.fn(), demo: vi.fn(), openAuth: vi.fn() }));
vi.mock('../../viewmodels/useBrandViewModel', () => ({ useBrandViewModel: () => mocks.vm }));
vi.mock('../../components/showcase/DesignShowcases', () => ({ CardStackShowcase: () => null, CircularGalleryShowcase: () => null }));
vi.mock('../../stores/authStore', () => ({ useAuthStore: () => mocks.auth }));
vi.mock('../../stores/uiStore', () => ({ useUIStore: () => ({ openAuthModal: mocks.openAuth }) }));
vi.mock('../../services/apiServices', () => ({ brandService: { requestDemo: mocks.demo } }));
vi.mock('../../services/apiClient', () => ({ request: mocks.request }));

import { BrandAnalyticsView } from '../b2b/BrandAnalyticsView';
import { BrandDashboardView } from '../b2b/BrandDashboardView';
import { BrandPlacementsView } from '../b2b/BrandPlacementsView';
import { BrandCatalogView } from '../b2b/BrandCatalogView';
import { BrandInventoryView } from '../b2b/BrandInventoryView';
import { RoleGuard } from '../../components/auth/RoleGuard';

beforeEach(() => {
  cleanup(); vi.clearAllMocks();
  mocks.vm = { analytics: null, profile: null, isLoading: false, loadFailed: false,
    fetchErrors: {analytics: 'Analytics request failed'}, refresh: vi.fn(), products: [], placements: [],
    createSponsoredSlot: mocks.create, updateSKUInventory: mocks.update, importJobs: [],
    uploadCatalogCSV: vi.fn(), isUploading: false };
});

describe('Partner operational contracts', () => {
  it('a single analytics failure is terminal, not an infinite loading state', () => {
    render(<BrandAnalyticsView />);
    expect(screen.getByText('Telemetry unavailable')).toBeTruthy();
    expect(screen.getByText('Retry')).toBeTruthy();
  });
  it('dashboard also offers retry for partial failure', () => {
    render(<BrandDashboardView />);
    expect(screen.getByText('B2B telemetry unavailable')).toBeTruthy();
  });
  it('failed placement create preserves the form and uses the actual first product ID', async () => {
    mocks.vm.products = [{id: 91, title: 'Real product', base_price: 20}];
    mocks.vm.fetchErrors = {};
    mocks.create.mockResolvedValue(false);
    render(<BrandPlacementsView />);
    fireEvent.click(screen.getByRole('button', {name: 'Create Placement'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save placement'}));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({productId:91})));
    expect(screen.getByRole('button', {name: 'Save placement'})).toBeTruthy();
  });
  it('failed SKU mutation does not dismiss editing controls', async () => {
    mocks.vm.products = [{id:9, title:'Coat', base_price:20, skus:[{id:11,sku_code:'REAL-SKU',size:'M',color:'Navy',stock_level:5,is_in_stock:true}]}];
    mocks.vm.fetchErrors = {};
    mocks.update.mockResolvedValue(false);
    render(<BrandCatalogView />);
    fireEvent.click(screen.getByText('Edit Stock'));
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    expect(screen.getByLabelText('Stock for REAL-SKU')).toBeTruthy();
  });
  it('authenticated consumer gets partnership request form, never protected content', () => {
    mocks.auth = { user: {role:'consumer',email:'shopper@example.test'}, isAuthenticated:true, hasAttemptedBootstrap:true };
    render(<MemoryRouter><RoleGuard allowedRoles={['brand_owner']} fallbackTitle="Brand Partner Portal"><p>Private catalog</p></RoleGuard></MemoryRouter>);
    expect(screen.getByRole('form', {name:'Request a partner demo'})).toBeTruthy();
    expect(screen.queryByText('Private catalog')).toBeNull();
    expect(screen.queryByText('Create partner account')).toBeNull();
  });
  it('store stock form submits actual store and SKU without warehouse mutation', async () => {
    mocks.request.mockImplementation((path: string) => Promise.resolve(path === '/partner/stores' ? [{id:2,name:'Giza',city:'Giza',country:'EG',address:'Test'}] : path === '/partner/inventory' ? [{product_id:9,title:'Coat',total_stock:5,skus:[{id:11,sku_code:'REAL-SKU',size:'M',color:'Navy',stock_level:5,store_inventories:[]}]}] : {}));
    render(<BrandInventoryView />);
    await screen.findByLabelText('Inventory store');
    fireEvent.change(screen.getByLabelText('Inventory store'), {target:{value:'2'}});
    fireEvent.change(screen.getByLabelText('Inventory SKU'), {target:{value:'11'}});
    fireEvent.change(screen.getByLabelText('Store on-hand quantity'), {target:{value:'7'}});
    fireEvent.submit(screen.getByRole('form', {name:'Set store inventory'}));
    await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('/partner/inventory', {method:'POST',body:JSON.stringify({store_id:2,sku_id:11,quantity:7})}));
    await screen.findByText('Store inventory saved. Warehouse stock was not changed.');
  });
});
