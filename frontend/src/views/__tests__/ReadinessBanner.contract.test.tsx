/**
 * P1 closure (2026-09-22 admin audit): "readiness غير موحد مع واجهة الإدارة".
 *
 * `/health` reported ready=false (virtual_try_on blocking) while the admin
 * dashboard rendered KPI cards with no blocker in sight. These tests pin the
 * three honest states of the banner:
 *
 *  1. ready=false  → role="alert" banner NAMING the blocking + degraded
 *                    capabilities exactly as the backend published them;
 *  2. ready=true   → quiet confirmation, still listing degraded capabilities;
 *  3. fetch failed → "unknown" wording — NEVER green-by-default. A banner
 *                    that assumes readiness on error is the same defect class
 *                    the audit flagged, one level up.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, cleanup, screen } from '@testing-library/react';
import React from 'react';

const { readinessMock } = vi.hoisted(() => ({ readinessMock: vi.fn() }));

vi.mock('../../hooks/usePlatformReadiness', () => ({
  usePlatformReadiness: () => readinessMock(),
}));

import { ReadinessBanner } from '../../components/admin/ReadinessBanner';

describe('ReadinessBanner (admin readiness honesty)', () => {
  beforeEach(() => {
    cleanup();
    readinessMock.mockReset();
  });

  it('renders a prominent alert naming blocking and degraded capabilities when ready=false', () => {
    readinessMock.mockReturnValue({
      verdict: 'not_ready',
      isLoading: false,
      readiness: {
        status: 'healthy',
        ready: false,
        blocking_capabilities: ['virtual_try_on'],
        degraded_capabilities: ['payments', 'buy_now_pay_later'],
      },
    });
    render(<ReadinessBanner />);
    const banner = screen.getByTestId('readiness-banner-blocked');
    expect(banner.getAttribute('role')).toBe('alert');
    expect(screen.getByTestId('readiness-blocking-list').textContent).toContain('virtual_try_on');
    const degraded = screen.getByTestId('readiness-degraded-list').textContent ?? '';
    expect(degraded).toContain('payments');
    expect(degraded).toContain('buy_now_pay_later');
  });

  it('renders a quiet status when ready=true, still listing degraded capabilities', () => {
    readinessMock.mockReturnValue({
      verdict: 'ready',
      isLoading: false,
      readiness: {
        status: 'healthy',
        ready: true,
        blocking_capabilities: [],
        degraded_capabilities: ['buy_now_pay_later'],
      },
    });
    render(<ReadinessBanner />);
    const banner = screen.getByTestId('readiness-banner-ready');
    expect(banner.getAttribute('role')).toBe('status');
    expect(screen.getByTestId('readiness-degraded-list').textContent).toContain(
      'buy_now_pay_later'
    );
  });

  it('says "unknown" when /health is unreachable — never green by default', () => {
    readinessMock.mockReturnValue({ verdict: 'unknown', isLoading: false, readiness: null });
    render(<ReadinessBanner />);
    expect(screen.getByTestId('readiness-banner-unknown')).toBeTruthy();
    expect(screen.queryByTestId('readiness-banner-ready')).toBeNull();
    expect(screen.queryByTestId('readiness-banner-blocked')).toBeNull();
  });

  it('renders nothing while the first fetch is in flight (no premature verdict)', () => {
    readinessMock.mockReturnValue({ verdict: 'unknown', isLoading: true, readiness: null });
    const { container } = render(<ReadinessBanner />);
    expect(container.firstChild).toBeNull();
  });
});
