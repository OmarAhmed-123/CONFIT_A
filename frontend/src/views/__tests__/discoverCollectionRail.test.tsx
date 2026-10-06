/**
 * Spec 10 — the Discover collection rail.
 *
 * `AccessibleCarousel` already has a full component suite
 * (carouselSlider.test.tsx). What was UNTESTED — and was the re-pass gap —
 * is the carousel's first REAL-data integration: the rail on /discover that
 * feeds the primitive from the live catalog query. These tests pin the
 * integration contract:
 *
 *   1. the rail renders real catalog products as real, actionable cards;
 *   2. the position indicator and prev/next controls are exposed;
 *   3. loading / error(+retry wired to the catalog refresh) / empty states
 *      come from the SAME query that drives the grid — no second fetch,
 *      no invented "trending" metric (§11);
 *   4. the Arabic shell labels the rail in Arabic (RTL handled by the
 *      primitive's own suite);
 *   5. the rail subtree passes axe in the populated state.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, screen, fireEvent, act, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { axe } from 'vitest-axe';
import i18n from '../../i18n/i18n';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';
import type { Product } from '../../models';

/* ------------------------------------------------------------------ mocks */

const { vmState, refreshMock } = vi.hoisted(() => ({
  vmState: {
    products: [] as unknown[],
    isLoading: false,
    error: null as string | null,
  },
  refreshMock: vi.fn(),
}));

vi.mock('../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({
    products: vmState.products,
    categories: [],
    selectedCategory: '',
    setSelectedCategory: vi.fn(),
    selectedOccasion: '',
    setSelectedOccasion: vi.fn(),
    searchQuery: '',
    setSearchQuery: vi.fn(),
    sortBy: 'newest',
    setSortBy: vi.fn(),
    isLoading: vmState.isLoading,
    error: vmState.error,
    refresh: refreshMock,
  }),
}));

// Capability + engine probes are backend calls; the rail must not depend on
// them, so both hooks are pinned to their honest "nothing is live" shapes.
vi.mock('../../hooks/useCapabilities', () => ({
  useCapabilities: () => ({
    capabilities: { bnpl_live: false, tryon_live: false },
    isLoading: false,
  }),
}));
vi.mock('../../hooks/useTryOnAvailability', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/useTryOnAvailability')>();
  return {
    ...actual,
    useTryOnAvailability: () => ({
      engineState: 'offline',
      renderAvailable: false,
      isProbing: false,
      retryAfterSeconds: 0,
      errorCode: null,
      userMessage: null,
      upstreamDetail: null,
      ctaKind: () => 'blocked' as const,
      gate: () => () => {},
    }),
  };
});

import { DiscoverView } from '../consumer/DiscoverView';

/* --------------------------------------------------------------- fixtures */

// Realistic catalogue shapes (slug/price/thumbnail are the fields the card
// actually renders); cast because the full Product model carries many more.
const CATALOG: Product[] = [1, 2, 3].map(
  (n) =>
    ({
      id: n,
      title: `Rail Product ${n}`,
      slug: `rail-product-${n}`,
      brand_name: 'Reiss',
      base_price: 100 + n,
      thumbnail_url: `https://img.example/p${n}.jpg`,
    }) as unknown as Product,
);

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <DiscoverView />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

const rail = () => screen.getByTestId('discover-collection-rail');

async function setAppLanguage(lang: string) {
  await act(async () => {
    await i18n.changeLanguage(lang);
  });
}

/* ------------------------------------------------------------------ tests */

describe('Discover collection rail — real-data AccessibleCarousel integration', () => {
  beforeEach(() => {
    cleanup();
    vmState.products = CATALOG;
    vmState.isLoading = false;
    vmState.error = null;
    refreshMock.mockReset();
  });
  afterEach(async () => {
    await setAppLanguage('en');
  });

  it('renders the live catalog as carousel slides with real product actions and a position indicator', () => {
    renderView();
    const region = rail();

    // The rail is a labelled carousel region fed by the SAME products the
    // grid uses — assert against the fixture catalogue, not copy.
    expect(within(region).getAllByTestId('product-card')).toHaveLength(3);
    expect(
      within(region).getByRole('button', { name: /view .*rail product 1/i }),
    ).toBeInTheDocument();

    // Position indicator text ("1 / 3") + prev/next controls ≥ labelled.
    expect(within(region).getByText(/1\s*\/\s*3/)).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: i18n.t('carousel.previous') })).toBeInTheDocument();
    expect(within(region).getByRole('button', { name: i18n.t('carousel.next') })).toBeInTheDocument();
  });

  it('shows the honest loading state while the catalog query is in flight', () => {
    vmState.products = [];
    vmState.isLoading = true;
    renderView();
    expect(within(rail()).getByText(i18n.t('carousel.loading'))).toBeInTheDocument();
    expect(within(rail()).queryAllByTestId('product-card')).toHaveLength(0);
  });

  it('surfaces a catalog failure with a retry wired to the SAME refresh as the grid', () => {
    vmState.products = [];
    vmState.error = 'NETWORK';
    renderView();
    const retry = within(rail()).getByRole('button', { name: i18n.t('carousel.retry') });
    fireEvent.click(retry);
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });

  it('does NOT show the rail error when the grid still has products (stale-while-error)', () => {
    // products present + background refresh error → the rail keeps showing
    // the real items instead of replacing them with an error card.
    vmState.error = 'NETWORK';
    renderView();
    expect(within(rail()).getAllByTestId('product-card')).toHaveLength(3);
    expect(
      within(rail()).queryByRole('button', { name: i18n.t('carousel.retry') }),
    ).not.toBeInTheDocument();
  });

  it('shows the empty state when the catalog is genuinely empty', () => {
    vmState.products = [];
    renderView();
    expect(within(rail()).getByText(i18n.t('carousel.empty'))).toBeInTheDocument();
  });

  it('labels the rail in Arabic under the AR shell', async () => {
    await setAppLanguage('ar');
    renderView();
    const region = rail();
    expect(region).toHaveAttribute('aria-label', i18n.t('discover.rail_label', { lng: 'ar' }));
    expect(screen.getByText(i18n.t('discover.rail_title', { lng: 'ar' }))).toBeInTheDocument();
  });

  /* ---- Spec 11 — depth gallery placement & perf budget on /discover ---- */

  it('spec 11: the depth gallery is the LAST section of /discover (can never be the LCP element)', () => {
    const { container } = renderView();
    const pageRoot = container.firstElementChild as HTMLElement;
    const last = pageRoot.lastElementChild as HTMLElement;
    // The closing mood/collection moment: the gallery region lives inside
    // the final section — below every conversion surface.
    expect(
      within(last).getByRole('region', { name: i18n.t('showcase.gallery_region') }),
    ).toBeInTheDocument();
  });

  it('spec 11 perf budget: at most ONE eager image inside the gallery section', () => {
    const { container } = renderView();
    const pageRoot = container.firstElementChild as HTMLElement;
    const last = pageRoot.lastElementChild as HTMLElement;
    const eager = Array.from(last.querySelectorAll('img')).filter(
      (img) => img.getAttribute('loading') !== 'lazy',
    );
    // 3D path: front item only is eager; 2D fallback: everything lazy.
    expect(eager.length).toBeLessThanOrEqual(1);
  });

  it('rail subtree passes axe in the populated state', async () => {
    renderView();
    // Same project convention as carouselSlider.test.tsx: assert the raw
    // violations array (color-contrast/target-size are jsdom-unmeasurable).
    const results = await axe(rail(), {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});
