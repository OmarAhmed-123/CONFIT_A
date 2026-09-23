/**
 * Admin dashboard style-heatmap contract + honesty regressions (G-01, G-04).
 *
 * Two client-side behaviours the audit could not see, because no admin account
 * existed to render the page:
 *
 *  1. Contract — the view reads `cell.share` and iterates `trending_colors`.
 *     The standalone backend endpoint emitted `{name, weight, count}` and
 *     `top_colors` objects instead, so the bars rendered `undefined%` and the
 *     colour row threw on `.map`. These tests pin the shape the view needs.
 *  2. Honesty — when the aggregate is suppressed the panel must say why. It
 *     used to be filled by the backend with four hardcoded aesthetics and four
 *     hardcoded colour chips inside a dashboard titled "Real Data".
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, cleanup, screen } from '@testing-library/react';
import React from 'react';

const { vmMock } = vi.hoisted(() => ({ vmMock: vi.fn() }));

vi.mock('../../viewmodels/useBrandViewModel', () => ({
  useBrandViewModel: () => vmMock(),
}));
vi.mock('../../components/showcase/DesignShowcases', () => ({
  CardStackShowcase: () => null,
}));
// The readiness banner has its own contract test (ReadinessBanner.contract.
// test.tsx) with all three verdicts; here it is pinned to "unknown" so the
// heatmap assertions stay independent of the health fetch.
vi.mock('../../hooks/usePlatformReadiness', () => ({
  usePlatformReadiness: () => ({ verdict: 'unknown', readiness: null, isLoading: true }),
}));

import { AdminAnalyticsView } from '../b2b/AdminAnalyticsView';

const BASE = {
  total_gmv: 0,
  total_orders: 0,
  total_users_count: 0,
  total_brands_count: 0,
  tryon_adoption_rate: 0,
  stylist_conversion_ratio: 0,
  platform_avg_return_rate: 0,
  return_rate_tryon_users: 0,
  return_rate_non_tryon_users: 0,
  revenue_attribution: {},
  top_performing_brands: [],
};

const FABRICATED = ['Quiet Luxury / Old Money', 'Modern Minimalist', '#1B1F3B (Navy)'];

describe('AdminAnalyticsView style heatmap', () => {
  beforeEach(() => {
    cleanup();
    vmMock.mockReset();
  });

  it('explains a suppressed aggregate instead of inventing one', () => {
    vmMock.mockReturnValue({
      adminAnalytics: {
        ...BASE,
        style_preference_heatmap: {
          region: 'Platform-wide',
          region_scope: 'platform_wide',
          sample_size: 0,
          min_sample_required: 10,
          data_available: false,
          top_aesthetics: [],
          trending_colors: [],
          top_occasions: [],
          limitations: ['Only 0 outfit(s) in scope; at least 10 are required.'],
        },
      },
      fetchErrors: {},
      loadFailed: false,
      isLoading: false,
      refresh: vi.fn(),
    });

    render(<AdminAnalyticsView />);

    expect(screen.getByText(/Not enough data to publish an aggregate/i)).toBeTruthy();
    expect(screen.getByText(/Nothing is simulated to fill this panel/i)).toBeTruthy();
    for (const fake of FABRICATED) {
      expect(screen.queryByText(new RegExp(fake, 'i'))).toBeNull();
    }
  });

  it('renders real cells with a share and a count, never undefined', () => {
    vmMock.mockReturnValue({
      adminAnalytics: {
        ...BASE,
        style_preference_heatmap: {
          region: 'Platform-wide',
          sample_size: 13,
          k_anonymity_floor: 5,
          data_available: true,
          top_aesthetics: [{ name: 'Quiet Luxury', raw_name: 'quiet_luxury', share: 61.5, count: 8 }],
          trending_colors: [{ name: '#AAAAAA', raw_name: '#AAAAAA', share: 42.5, count: 17 }],
          top_occasions: [{ name: 'Casual', raw_name: 'Casual', share: 100, count: 13 }],
          limitations: [],
        },
      },
      fetchErrors: {},
      loadFailed: false,
      isLoading: false,
      refresh: vi.fn(),
    });

    const { container } = render(<AdminAnalyticsView />);

    expect(screen.getByText('Quiet Luxury')).toBeTruthy();
    expect(screen.getByText('61.5% · 8 outfits')).toBeTruthy();
    expect(screen.getByText('42.5% · 17 outfits')).toBeTruthy();
    // The colour dimension is a list of cells, not bare strings — this is the
    // `.map` that used to throw.
    expect(screen.getByText('#AAAAAA')).toBeTruthy();
    expect(screen.getByText('Casual')).toBeTruthy();
    expect(container.textContent).not.toContain('undefined%');
    expect(container.textContent).not.toContain('NaN');
  });

  it('says when a dimension met no cell rather than showing an empty chart', () => {
    vmMock.mockReturnValue({
      adminAnalytics: {
        ...BASE,
        style_preference_heatmap: {
          region: 'Platform-wide',
          sample_size: 40,
          k_anonymity_floor: 5,
          data_available: true,
          top_aesthetics: [{ name: 'Tailored', raw_name: 'tailored', share: 100, count: 40 }],
          trending_colors: [],
          top_occasions: [],
          limitations: [],
        },
      },
      fetchErrors: {},
      loadFailed: false,
      isLoading: false,
      refresh: vi.fn(),
    });

    render(<AdminAnalyticsView />);
    expect(screen.getByText(/Trending colours/i)).toBeTruthy();
    expect(screen.getAllByText(/no cell met the k-anonymity floor in this window/i).length).toBe(2);
  });
});
