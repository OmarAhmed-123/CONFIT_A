/**
 * B02 — Partner Command Center, re-pass (docs/B02_PARTNER_DASHBOARD_REDESIGN.md).
 *
 * Each test closes a measured defect in the previous build:
 *   · D9  loading was a full-page spinner        → geometry skeleton, role="status"
 *   · D10 partial/all failure were one bucket     → distinct terminal vs retry states
 *   · honesty contract: null rates render N/A / "Not enough data", never 0%
 *   · D1  the page bypassed i18n                  → AR locale renders Arabic copy
 *   · D13 no refresh affordance                   → refresh button re-fetches
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';

import i18n from '../../i18n/i18n';

const mocks = vi.hoisted(() => ({ vm: {} as any }));
vi.mock('../../viewmodels/useBrandViewModel', () => ({
  useBrandViewModel: () => mocks.vm,
}));

import { BrandDashboardView } from '../b2b/BrandDashboardView';

const analyticsFixture = (over: Record<string, unknown> = {}) => ({
  data_source: 'db',
  methodology: 'Counts are computed from retained event records.',
  return_cohorts: { methodology: 'Observational cohorts; opened returns.' },
  brand_name: 'Test Label',
  total_products_count: 12,
  total_skus_count: 34,
  total_views: 1000,
  total_tryons: 250,
  total_add_to_carts: 120,
  total_purchases: 80,
  funnel_conversion_rate: 8,
  return_rate_before_vton: 22,
  return_rate_after_vton: 9,
  return_reduction_percentage: 13,
  outfit_appearance_rankings: [],
  bopis_store_fulfillment_rate: null,
  ad_spend_total: 40,
  ad_revenue_total: 90,
  ...over,
});

const baseVm = (over: Record<string, unknown> = {}) => ({
  profile: { brand_name: 'Test Label', is_verified: false, commission_rate: 10 },
  analytics: analyticsFixture(),
  products: [],
  placements: [],
  importJobs: [],
  conversionPerSku: [],
  fetchErrors: {},
  fetchErrorMeta: {},
  loadFailed: false,
  isLoading: false,
  isUploading: false,
  refresh: vi.fn(),
  ...over,
});

beforeEach(() => {
  cleanup();
  mocks.vm = baseVm();
  return i18n.changeLanguage('en');
});
afterEach(() => i18n.changeLanguage('en'));

const ui = () => (
  <I18nextProvider i18n={i18n}>
    <BrandDashboardView />
  </I18nextProvider>
);

describe('B02 partner command center', () => {
  it('D9: loading renders a geometry skeleton announced politely, not a bare spinner', async () => {
    mocks.vm = baseVm({ isLoading: true });
    const { container } = render(ui());
    const status = container.querySelector('[role="status"]');
    expect(status).toBeTruthy();
    expect(status!.querySelector('.skeleton-shimmer')).toBeTruthy();
    expect(screen.getByText(i18n.t('b2b.dash.loading'))).toBeTruthy();
  });

  it('D10: a single analytics failure is terminal-with-retry and surfaces the raw error', () => {
    mocks.vm = baseVm({ analytics: null, fetchErrors: { analytics: 'Analytics request failed' } });
    render(ui());
    expect(screen.getByText('B2B telemetry unavailable')).toBeTruthy();
    expect(screen.getByText('Analytics request failed')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(mocks.vm.refresh).toHaveBeenCalled();
  });

  it('D10: all-sources failure renders the terminal portal state, not the single-source one', () => {
    mocks.vm = baseVm({
      analytics: null,
      profile: null,
      loadFailed: true,
      fetchErrors: { analytics: 'boom' },
    });
    render(ui());
    expect(screen.getByText('The partner portal could not be reached')).toBeTruthy();
    expect(screen.queryByText('B2B telemetry unavailable')).toBeNull();
  });

  it('honesty: null conversion renders N/A and null rates render the not-enough-data phrase, never 0%', () => {
    mocks.vm = baseVm({
      analytics: analyticsFixture({
        funnel_conversion_rate: null,
        return_rate_before_vton: null,
        return_rate_after_vton: null,
        return_reduction_percentage: null,
        bopis_store_fulfillment_rate: null,
        total_views: 0,
        total_purchases: 0,
        total_tryons: 0,
      }),
    });
    render(ui());
    expect(screen.getByText('N/A')).toBeTruthy();
    expect(screen.getAllByText('Not enough data').length).toBeGreaterThan(1);
    expect(screen.queryByText('0%')).toBeNull();
    expect(screen.getByText(i18n.t('b2b.dash.kpi_ratio_na'))).toBeTruthy();
  });

  it('D13: refresh button re-fetches and the as-of stamp renders after data lands', () => {
    render(ui());
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(mocks.vm.refresh).toHaveBeenCalled();
    expect(screen.getByText(/Updated/)).toBeTruthy();
  });

  it('D1: the Arabic locale renders Arabic copy, not English fallback', async () => {
    await i18n.changeLanguage('ar');
    render(ui());
    expect(screen.getByText(i18n.t('b2b.dash.eyebrow'))).toBeTruthy();
    expect(screen.getByText('قياسات الشريك')).toBeTruthy();
    expect(screen.getByText('الأكثر تنسيقًا في الإطلالات')).toBeTruthy();
    expect(screen.queryByText('Most styled items')).toBeNull();
  });

  it('renders the ledger, cohort comparison and catalog strip from the real payload', () => {
    render(ui());
    expect(screen.getByText('1,000')).toBeTruthy();
    expect(screen.getByText('250')).toBeTruthy();
    expect(screen.getByText('8%')).toBeTruthy();
    expect(screen.getByText(i18n.t('b2b.dash.cohort_title'))).toBeTruthy();
    expect(screen.getByText(i18n.t('b2b.dash.catalog_products'))).toBeTruthy();
    expect(screen.getByText(i18n.t('b2b.dash.pending'))).toBeTruthy();
  });
});
