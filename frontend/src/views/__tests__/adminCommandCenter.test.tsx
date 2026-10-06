/**
 * Spec 12 — Admin command center (§10 test contract):
 *   contract honesty (missing ⇒ unavailable, NEVER 0 or a borrowed value)
 *   · asOf/source/freshness line · window filter in URL · sortable table
 *   (absent values sort last) · drill-down to the restricted catalog route
 *   · audit filters in URL (shareable, reload-proof) · permission denial
 *   shows the server's refusal · zod rejects a drifted payload · axe EN +
 *   AR/RTL · prices/numbers LTR inside the Arabic page.
 *
 * Measured defects this file pins (found in spec-12 recon):
 *   1. Brand table rendered `tryons ?? orders ?? 0` — a missing try-on
 *      count was silently replaced by the ORDER count, then by zero.
 *   2. Missing conversion_rate rendered as "-%".
 *   3. The server's time_range echo (backend TimeRange.describe()) was
 *      thrown away — numbers rendered with no window provenance.
 *   4. Audit filters lived in component state: an investigation URL could
 *      not be shared and did not survive reload.
 */
import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { setAppLanguage } from '../../i18n/i18n';

const { vmMock, requestMock } = vi.hoisted(() => ({
  vmMock: vi.fn(),
  requestMock: vi.fn(),
}));

vi.mock('../../viewmodels/useBrandViewModel', () => ({
  useBrandViewModel: (scope: string, options?: { analyticsDays?: number }) =>
    vmMock(scope, options),
}));
vi.mock('../../components/showcase/DesignShowcases', () => ({
  CardStackShowcase: () => null,
}));
vi.mock('../../hooks/usePlatformReadiness', () => ({
  usePlatformReadiness: () => ({ verdict: 'unknown', readiness: null, isLoading: true }),
}));
vi.mock('../../services/apiClient', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../../services/apiClient')>();
  return { ...mod, request: requestMock };
});

import { AdminAnalyticsView } from '../b2b/AdminAnalyticsView';
import { AdminAuditView } from '../b2b/AdminAuditView';

const ANALYTICS = {
  total_users_count: 42,
  total_brands_count: 3,
  total_orders: 120,
  total_gmv: 5000,
  currency: 'EGP',
  currency_status: 'single_currency' as const,
  gmv_by_currency: { EGP: 5000 },
  attribution_by_currency: {},
  tryon_adoption_rate: 12,
  stylist_conversion_ratio: 4,
  platform_avg_return_rate: 2,
  return_rate_tryon_users: 1,
  return_rate_non_tryon_users: 3,
  revenue_attribution: {},
  top_performing_brands: [
    // tryons/conversion_rate deliberately MISSING on Alpha (defect #1/#2)
    { brand_id: 5, brand: 'Alpha', orders: 10, tryon_rate: '3%', return_rate: '1%' },
    { brand_id: 7, brand: 'Beta', products: 4, views: 900, tryons: 55, orders: 30, conversion_rate: 3.3, tryon_rate: '9%', return_rate: '2%' },
  ],
  style_preference_heatmap: {
    region: 'EG',
    privacy_threshold: 'k>=10',
    data_available: false,
    sample_size: 2,
    min_sample_required: 10,
    top_aesthetics: [],
    trending_colors: [],
    top_occasions: [],
    limitations: [],
  },
  time_range: {
    source: 'days',
    date_from: '2026-09-01T00:00:00+00:00',
    date_to: '2026-10-01T00:00:00+00:00',
    date_to_inclusive: true,
    is_all_time: false,
  },
};

const vmValue = (overrides: Record<string, unknown> = {}) => ({
  adminAnalytics: ANALYTICS,
  fetchErrors: {},
  isLoading: false,
  refresh: vi.fn(),
  ...overrides,
});

const LocationProbe: React.FC = () => {
  const location = useLocation();
  return <output data-testid="probe">{location.search}</output>;
};

const renderAnalytics = (initialEntry = '/admin/analytics') =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/admin/analytics" element={<><AdminAnalyticsView /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(async () => {
  cleanup();
  vmMock.mockReset().mockReturnValue(vmValue());
  requestMock.mockReset();
  await act(async () => { await setAppLanguage('en'); });
});

/* ------------------------------------------------------------------ */
/* A. Honesty: missing metric ⇒ unavailable, never 0 / borrowed        */
/* ------------------------------------------------------------------ */
describe('brand table honesty (§2)', () => {
  it('missing tryons renders N/A — NOT the orders count, NOT 0', () => {
    renderAnalytics();
    const alphaRow = screen.getByText('Alpha').closest('tr')!;
    const cells = Array.from(alphaRow.querySelectorAll('td')).map((td) => td.textContent);
    // products, views, tryons, conversion all absent on Alpha:
    expect(cells.filter((c) => c === 'N/A').length).toBeGreaterThanOrEqual(4);
    // the old fabricated values must be gone:
    expect(alphaRow.textContent).not.toContain('-%');
    const tryonsCell = alphaRow.querySelectorAll('td')[3];
    expect(tryonsCell.textContent).toBe('N/A'); // not "10" (orders), not "0"
  });

  it('present metrics still render as real values', () => {
    renderAnalytics();
    const betaRow = screen.getByText('Beta').closest('tr')!;
    expect(betaRow.textContent).toContain('55');
    expect(betaRow.textContent).toContain('3.3%');
  });
});

/* ------------------------------------------------------------------ */
/* B. Source & freshness (§6.2)                                        */
/* ------------------------------------------------------------------ */
describe('asOf / source / freshness', () => {
  it("renders the SERVER's window echo + the measured fetch time as polite text", () => {
    renderAnalytics();
    const status = screen
      .getAllByRole('status')
      .find((el) => el.textContent?.includes('2026-09-01'));
    expect(status).toBeTruthy();
    expect(status!.textContent).toContain('2026-10-01');
    expect(status!.textContent).toMatch(/fetched at/);
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('all-time windows say all-time; a server without the echo says unreported — never a guessed range', () => {
    vmMock.mockReturnValue(vmValue({
      adminAnalytics: { ...ANALYTICS, time_range: { source: 'all', date_from: null, date_to: null, is_all_time: true } },
    }));
    renderAnalytics();
    expect(screen.getByText(/all recorded history/)).toBeInTheDocument();

    cleanup();
    vmMock.mockReturnValue(vmValue({
      adminAnalytics: { ...ANALYTICS, time_range: undefined },
    }));
    renderAnalytics();
    expect(screen.getByText(/not reported by this server version/)).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* C. Window filter lives in the URL (§6.3)                            */
/* ------------------------------------------------------------------ */
describe('analysis window in URL', () => {
  it('selecting 30 days writes ?days=30 and the viewmodel refetches with it', () => {
    renderAnalytics();
    fireEvent.click(screen.getByRole('button', { name: 'Last 30 days' }));
    expect(screen.getByTestId('probe').textContent).toBe('?days=30');
    expect(vmMock).toHaveBeenLastCalledWith('admin', { analyticsDays: 30 });
  });

  it('?days=90 in the entry URL initialises the window (reload-proof)', () => {
    renderAnalytics('/admin/analytics?days=90');
    expect(vmMock).toHaveBeenCalledWith('admin', { analyticsDays: 90 });
    expect(screen.getByRole('button', { name: 'Last 90 days' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('a junk ?days=13 falls back to all-time — the UI never sends an unvetted window', () => {
    renderAnalytics('/admin/analytics?days=13');
    expect(vmMock).toHaveBeenCalledWith('admin', { analyticsDays: undefined });
    expect(screen.getByRole('button', { name: 'All time' })).toHaveAttribute('aria-pressed', 'true');
  });
});

/* ------------------------------------------------------------------ */
/* D. Sorting + drill-down (§6.4/§6.5)                                 */
/* ------------------------------------------------------------------ */
describe('brand table sorting and drill-down', () => {
  it('sorts by orders desc by default, toggles to asc, aria-sort follows', () => {
    renderAnalytics();
    const rows = () => screen.getAllByRole('row').slice(1).map((r) => r.textContent ?? '');
    expect(rows()[0]).toContain('Beta'); // 30 > 10
    const ordersHeader = screen.getByRole('button', { name: /Orders/ });
    fireEvent.click(ordersHeader);
    expect(rows()[0]).toContain('Alpha');
    expect(ordersHeader.closest('th')).toHaveAttribute('aria-sort', 'ascending');
  });

  it('missing values sort LAST in both directions — absence is not a ranking', () => {
    renderAnalytics();
    const convHeader = screen.getByRole('button', { name: /Conversion/ });
    fireEvent.click(convHeader); // sort by conversion desc
    let rows = screen.getAllByRole('row').slice(1);
    expect(rows[0].textContent).toContain('Beta'); // Alpha has no conversion
    fireEvent.click(convHeader); // asc
    rows = screen.getAllByRole('row').slice(1);
    expect(rows[0].textContent).toContain('Beta'); // Alpha STILL last
  });

  it('brand name links into the restricted catalog route with brand_id', () => {
    renderAnalytics();
    const link = screen.getByRole('link', { name: 'Open catalog governance for Alpha' });
    expect(link).toHaveAttribute('href', '/admin/catalog?brand_id=5');
  });
});

/* ------------------------------------------------------------------ */
/* E. Permission denied + API failure stay honest (§5/§8)              */
/* ------------------------------------------------------------------ */
describe('denial and failure states', () => {
  it("permission denial shows the server's refusal and a retry — no cached numbers", () => {
    const refresh = vi.fn();
    vmMock.mockReturnValue(vmValue({
      adminAnalytics: null,
      fetchErrors: { adminAnalytics: 'Admin role required for platform analytics.' },
      refresh,
    }));
    renderAnalytics();
    expect(screen.getByText('Admin role required for platform analytics.')).toBeInTheDocument();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Retry|Try again/i }));
    expect(refresh).toHaveBeenCalled();
  });

  it('zod guards the wire: a drifted payload REJECTS instead of rendering garbage', async () => {
    // Real service path (not the vm mock): currency_status outside the
    // tri-state must throw before any component can trust it.
    const { adminService } = await import('../../services/apiServices');
    requestMock.mockResolvedValueOnce({ ...ANALYTICS, currency_status: 'maybe' });
    await expect(adminService.getPlatformAnalytics()).rejects.toThrow();
  });

  it('getPlatformAnalytics sends the window as ?days= and omits it for all-time', async () => {
    const { adminService } = await import('../../services/apiServices');
    requestMock.mockResolvedValue(ANALYTICS);
    await adminService.getPlatformAnalytics({ days: 30 });
    expect(requestMock).toHaveBeenLastCalledWith('/admin/analytics?days=30');
    await adminService.getPlatformAnalytics();
    expect(requestMock).toHaveBeenLastCalledWith('/admin/analytics');
  });
});

/* ------------------------------------------------------------------ */
/* F. Audit view: filters in the URL (§6.3)                            */
/* ------------------------------------------------------------------ */
describe('AdminAuditView URL filters', () => {
  const AUDIT_PAGE = {
    items: [],
    meta: { page: 1, page_size: 25, total: 0, total_pages: 0 },
    facets: null,
  };
  const INTEGRITY = {
    verdict: 'ok',
    window_days: 30,
    checked_rows: 10,
    violations: [],
    unresolved_actors: 0,
    redaction_markers: 0,
    rows_with_before_after: 10,
    rows_with_request_id: 10,
    rows_with_ip: 10,
    tamper_evident: false,
    limitations: ['append-only table; no cryptographic chain yet'],
    chain: { breaks: [] },
    verification_runs: { breaks: [] },
  };

  const renderAudit = (entry = '/admin/audit') =>
    render(
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/admin/audit" element={<><AdminAuditView /><LocationProbe /></>} />
        </Routes>
      </MemoryRouter>,
    );

  beforeEach(() => {
    requestMock.mockImplementation((url: string) =>
      url.includes('integrity') ? Promise.resolve(INTEGRITY) : Promise.resolve(AUDIT_PAGE),
    );
  });

  it('an investigation URL initialises filters AND the query sent to the API', async () => {
    renderAudit('/admin/audit?action=product.update&page=3&only_admin_actions=true');
    await waitFor(() => {
      const trailCall = requestMock.mock.calls.find(([u]) => u.includes('/admin/audit?'));
      expect(trailCall).toBeTruthy();
      expect(trailCall![0]).toContain('action=product.update');
      expect(trailCall![0]).toContain('page=3');
      expect(trailCall![0]).toContain('only_admin_actions=true');
    });
  });

  it('Apply writes the draft to the URL and resets page; Reset clears it', async () => {
    renderAudit('/admin/audit?page=4');
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/Action/i), { target: { value: 'sku.update' } });
    fireEvent.click(screen.getByRole('button', { name: /Apply/i }));
    await waitFor(() => {
      expect(screen.getByTestId('probe').textContent).toContain('action=sku.update');
      expect(screen.getByTestId('probe').textContent).not.toContain('page=4');
    });
    fireEvent.click(screen.getByRole('button', { name: /Reset/i }));
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe(''));
  });
});

/* ------------------------------------------------------------------ */
/* G. axe + Arabic                                                     */
/* ------------------------------------------------------------------ */
describe('axe + AR', () => {
  it('analytics EN: no violations', async () => {
    const { container } = renderAnalytics();
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it('AR/RTL: window controls translated; money and numeric cells stay LTR', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    const { container } = renderAnalytics();
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByRole('button', { name: 'آخر 30 يومًا' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'تحديث البيانات' })).toBeInTheDocument();
    // §7: prices/codes LTR inside the Arabic page
    const betaRow = screen.getByText('Beta').closest('tr')!;
    const numericCells = Array.from(betaRow.querySelectorAll('td[dir="ltr"]'));
    expect(numericCells.length).toBeGreaterThanOrEqual(6);
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* H. Spec 12 re-pass — 401/403 is a ROLE verdict, not an outage (§5)  */
/* ------------------------------------------------------------------ */
describe('permission refusal — localized, no futile retry', () => {
  it('403 on analytics renders the localized refusal and NO retry button', () => {
    vmMock.mockReturnValue(vmValue({
      adminAnalytics: null,
      fetchErrors: { adminAnalytics: 'Admin role required for platform analytics.' },
      fetchErrorMeta: { adminAnalytics: { status: 403, message: 'Admin role required for platform analytics.' } },
    }));
    renderAnalytics();
    expect(screen.getByText('Access refused by the server')).toBeInTheDocument();
    // A refusal is not flaky data: retrying cannot change the role verdict.
    expect(screen.queryByRole('button', { name: /Retry|Try again/i })).not.toBeInTheDocument();
    // And no cached numbers leak around the refusal.
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
  });

  it('the Arabic shell shows the refusal in Arabic — not the raw EN server string', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    vmMock.mockReturnValue(vmValue({
      adminAnalytics: null,
      fetchErrors: { adminAnalytics: 'Admin role required for platform analytics.' },
      fetchErrorMeta: { adminAnalytics: { status: 403, message: 'Admin role required for platform analytics.' } },
    }));
    renderAnalytics();
    expect(screen.getByText('السيرفر رفض الوصول')).toBeInTheDocument();
    expect(screen.queryByText('Admin role required for platform analytics.')).not.toBeInTheDocument();
    await act(async () => { await setAppLanguage('en'); });
  });

  it('a plain outage (no status / 500) keeps the generic error WITH retry — regression', () => {
    const refresh = vi.fn();
    vmMock.mockReturnValue(vmValue({
      adminAnalytics: null,
      fetchErrors: { adminAnalytics: 'upstream exploded' },
      fetchErrorMeta: { adminAnalytics: { status: 500, message: 'upstream exploded' } },
      refresh,
    }));
    renderAnalytics();
    expect(screen.getByText('upstream exploded')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Retry|Try again/i }));
    expect(refresh).toHaveBeenCalled();
  });

  it('403 on the audit trail renders the localized refusal and NO retry', async () => {
    requestMock.mockRejectedValue(
      Object.assign(new Error('Admin role required.'), { status: 403 }),
    );
    render(
      <MemoryRouter initialEntries={['/admin/audit']}>
        <Routes>
          <Route path="/admin/audit" element={<AdminAuditView />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText('Access refused by the server')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Retry|Try again/i })).not.toBeInTheDocument();
  });
});
