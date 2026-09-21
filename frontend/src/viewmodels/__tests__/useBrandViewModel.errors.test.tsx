/**
 * B2B silent-fallback regressions (2026-09-04).
 *
 * The B2B view-model and BrandInventoryView used to launder fetch failures
 * into empty arrays (catch-return-empty-array) or swallow them in bare catch
 * blocks — the exact error-laundering class prohibited by the remediation
 * contract.
 * A backend outage was then indistinguishable from a brand that genuinely has
 * zero import jobs / zero stores / zero inventory — exactly the error-
 * laundering class the remediation program prohibits ("never hide backend
 * failures behind empty arrays or fake success states").
 *
 * These tests drive the REAL view-model: when every B2B request rejects they
 * assert an explicit, non-empty error is exposed per request key plus a
 * terminal `loadFailed` verdict (never an infinite spinner), and when only
 * the imports/conversion requests reject they assert the error is recorded
 * while the successful slices still update. Under the old `.catch(() => [])`
 * code these assertions fail — that is the regression gate.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  getProfile: vi.fn(),
  getAnalytics: vi.fn(),
  getProducts: vi.fn(),
  getPlacements: vi.fn(),
  getPlatformAnalytics: vi.fn(),
  request: vi.fn(),
  showToast: vi.fn(),
  updateSKU: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  brandService: {
    getProfile: mocks.getProfile,
    getAnalytics: mocks.getAnalytics,
    getProducts: mocks.getProducts,
    getPlacements: mocks.getPlacements,
    updateSKU: mocks.updateSKU,
    createPlacement: vi.fn(),
  },
  adminService: { getPlatformAnalytics: mocks.getPlatformAnalytics },
}));

vi.mock('../../services/apiClient', () => ({ request: mocks.request }));
vi.mock('../../stores/uiStore', () => ({ useUIStore: () => ({ showToast: mocks.showToast }) }));

import { useBrandViewModel } from '../useBrandViewModel';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useBrandViewModel — honest error propagation', () => {
  it('records every failed request and a terminal loadFailed when all fail', async () => {
    const fail = (name: string) => Promise.reject(new Error(`500 ${name}`));
    mocks.getProfile.mockImplementation(() => fail('profile'));
    mocks.getAnalytics.mockImplementation(() => fail('analytics'));
    mocks.getProducts.mockImplementation(() => fail('products'));
    mocks.getPlacements.mockImplementation(() => fail('placements'));
    mocks.getPlatformAnalytics.mockImplementation(() => fail('admin'));
    mocks.request.mockImplementation(() => fail('rest'));

    const { result } = renderHook(() => useBrandViewModel());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.loadFailed).toBe(true);
    // The error object is keyed by request — a consumer view can render a
    // real, actionable message per section (never "no data").
    expect(Object.keys(result.current.fetchErrors).sort()).toEqual(
      ['analytics', 'conversion', 'imports', 'placements', 'products', 'profile'].sort(),
    );
    expect(result.current.fetchErrors.imports).toContain('500 rest');
    // No fake data materialised from the wreckage.
    expect(result.current.importJobs).toEqual([]);
    expect(result.current.conversionPerSku).toEqual([]);
  });

  it('surfaces a failed imports fetch while successful data still updates', async () => {
    mocks.getProfile.mockResolvedValue({ id: 1, name: 'Brand X' });
    mocks.getAnalytics.mockResolvedValue({ total_views: 3 });
    mocks.getProducts.mockResolvedValue([{ id: 9 }]);
    mocks.getPlacements.mockResolvedValue([]);
    mocks.getPlatformAnalytics.mockResolvedValue({ total_orders: 0 });
    mocks.request.mockImplementation((path: string) => {
      if (path === '/partner/catalog/imports') return Promise.reject(new Error('boom-imports'));
      return Promise.resolve({ per_sku: [] });
    });

    const { result } = renderHook(() => useBrandViewModel());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.fetchErrors.imports).toContain('boom-imports');
    expect(result.current.loadFailed).toBe(false); // partial failure is not "everything down"
    expect(result.current.products).toHaveLength(1); // successful slice still applied
  });

  it('clean fetch produces no error entries (empty is only shown when truly empty)', async () => {
    mocks.getProfile.mockResolvedValue({ id: 1, name: 'Brand X' });
    mocks.getAnalytics.mockResolvedValue({ total_views: 3 });
    mocks.getProducts.mockResolvedValue([{ id: 9 }]);
    mocks.getPlacements.mockResolvedValue([]);
    mocks.getPlatformAnalytics.mockResolvedValue({ total_orders: 0 });
    mocks.request.mockImplementation((path: string) =>
      Promise.resolve(path === '/partner/catalog/imports' ? [] : { per_sku: [] }),
    );

    const { result } = renderHook(() => useBrandViewModel());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.fetchErrors).toEqual({});
    expect(result.current.loadFailed).toBe(false);
    expect(result.current.importJobs).toEqual([]);
  });

});


describe('useBrandViewModel scope and mutation contracts', () => {
  beforeEach(() => {
    mocks.getProfile.mockResolvedValue({id: 1});
    mocks.getAnalytics.mockResolvedValue({total_views: 0});
    mocks.getProducts.mockResolvedValue([]);
    mocks.getPlacements.mockResolvedValue([]);
    mocks.request.mockResolvedValue([]);
  });
  it('never requests platform analytics for a partner screen', async () => {
    const {result} = renderHook(() => useBrandViewModel());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mocks.getPlatformAnalytics).not.toHaveBeenCalled();
  });
  it('admin scope requests only the admin endpoint', async () => {
    mocks.getPlatformAnalytics.mockResolvedValue({total_orders: 0});
    const {result} = renderHook(() => useBrandViewModel('admin'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mocks.getProfile).not.toHaveBeenCalled();
    expect(mocks.request).not.toHaveBeenCalled();
    expect(result.current.adminAnalytics).toEqual({total_orders: 0});
  });
  it('failed refresh clears old analytics instead of presenting stale data as current', async () => {
    const {result} = renderHook(() => useBrandViewModel());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    mocks.getAnalytics.mockRejectedValue(new Error('unavailable'));
    await act(async () => { await result.current.refresh(); });
    expect(result.current.analytics).toBeNull();
    expect(result.current.fetchErrors.analytics).toContain('unavailable');
  });
  it('mutation rejection is observable and never produces success toast', async () => {
    mocks.updateSKU.mockRejectedValue(new Error('not saved'));
    const {result} = renderHook(() => useBrandViewModel());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let saved: unknown;
    await act(async () => { saved = await result.current.updateSKUInventory(1, 7); });
    expect(saved).toBe(false);
    expect(mocks.showToast).not.toHaveBeenCalledWith(expect.any(String), 'success');
  });
});
