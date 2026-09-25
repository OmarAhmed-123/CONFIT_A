/** Admin Audit Trail mobile + keyboard + semantics contracts.
 *
 * Regression covered: rows were expanded only by <tr onClick>, which is not
 * keyboard focusable and gives a screen reader no control name. The view also
 * inherited near-white text from a light BrandLayout background.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));
vi.mock('../../services/apiClient', () => ({ request: requestMock }));

import { AdminAuditView } from '../b2b/AdminAuditView';

const ROW = {
  id: 77,
  timestamp: '2026-09-24T10:00:00Z',
  action: 'ADMIN_ORDER_TRANSITION',
  actor: 'admin@confit.test',
  actor_role: 'admin',
  resource_type: 'Order',
  resource_id: 'CONF-VERY-LONG-RESOURCE-ID-1234567890',
  changed_fields: ['status'],
  request_id: 'request-long-1234567890',
  ip_address: '203.0.113.1',
  before: { status: 'placed' },
  after: { status: 'processing' },
  details: 'approved transition',
};

const TRAIL = {
  items: [ROW],
  meta: { total: 1, page: 1, page_size: 25, total_pages: 1,
          has_previous: false, has_next: false },
  facets: { actions: [], resource_types: [] },
};

const INTEGRITY = {
  checked_rows: 1,
  window_days: 30,
  sampled_rows: 1,
  violations: [],
  unresolved_actors: 0,
  redaction_markers: 0,
  rows_with_before_after: 1,
  rows_with_request_id: 1,
  rows_with_ip: 1,
  distinct_actors: 1,
  verdict: 'ok',
  tamper_evident: true,
  coverage: {
    mode: 'window_sample', window_days: 30, sample_limit: 500,
    sampled_rows: 1, rows_in_window: 1,
    window_anchored_to_predecessor: true, full_history: false,
  },
  chain: {
    chained_rows: 1, unchained_rows: 0, bypass_suspected_rows: 0,
    breaks: [], head_hash: 'a'.repeat(64), key_version: 1,
    canonical_version: 1,
  },
  verification_runs: {
    coverage_mode: 'tail_window', sample_limit: 100, sampled_rows: 2,
    signed_rows: 2, unsigned_rows: 0, first_signed_run_id: 1,
    forgery_suspected_rows: 0, breaks: [], intact: true,
    head_hash: 'b'.repeat(64), canonical_version: 1,
    anchor: { audit_row_id: 88, run_id: 2, verdict: 'anchored' },
  },
  limitations: ['Window sample only.'],
};

beforeEach(() => {
  requestMock.mockReset();
  requestMock.mockImplementation((url: string) =>
    Promise.resolve(url.includes('/integrity') ? INTEGRITY : TRAIL));
  Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true });
});

describe('AdminAuditView accessible interaction', () => {
  it('uses a named native button, not a mouse-only clickable row', async () => {
    const { container } = render(<AdminAuditView />);
    const button = await screen.findByRole('button', { name: /details.*77/i });
    expect(button.tagName).toBe('BUTTON');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(button.className).toContain('min-h-11');
    expect(await screen.findByText(/verification runs: 2 signed.*tail anchor: anchored/i)).toBeTruthy();
    expect(button.className).toContain('focus-visible:ring-2');
    expect(container.querySelector('tr[aria-expanded]')).toBeNull();

    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(document.getElementById('audit-row-details-77')).toBeTruthy();
    expect(screen.getByText('approved transition')).toBeTruthy();
  });

  it('keeps the wide table in a named keyboard-scrollable region at 390px', async () => {
    const { container } = render(<AdminAuditView />);
    await screen.findByText('ADMIN_ORDER_TRANSITION');
    const region = screen.getByRole('region', { name: /audit trail entries/i });
    expect(region.getAttribute('tabindex')).toBe('0');
    expect(region.className).toContain('overflow-x-auto');
    expect(region.className).toContain('focus-visible:ring-2');
    expect(region.querySelector('table')?.className).toContain('min-w-[980px]');
    expect(container.querySelectorAll('th[scope="col"]').length).toBe(8);
  });

  it('has no serious/critical axe semantic violation after data loads', async () => {
    const { container } = render(<AdminAuditView />);
    await screen.findByText('ADMIN_ORDER_TRANSITION');
    await waitFor(() => expect(requestMock).toHaveBeenCalledTimes(2));
    const result = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(result.violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([]);
  });
});
