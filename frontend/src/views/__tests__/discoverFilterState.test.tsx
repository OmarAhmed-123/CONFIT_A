/**
 * C02 pass — Discover URL state + a11y/honesty fixes.
 *
 *   1. Deep-link hydration: ?occasion/?palette/?q/?sort apply ONCE, each
 *      validated against the tokens the screen understands; junk values
 *      are ignored (never applied, never echoed).
 *   2. Write-back at interaction time: picking a category/pill rewrites
 *      the URL (replace), clearing filters empties it — refresh/share/Back
 *      keep the shopper's place.
 *   3. Autocomplete suggestions are REAL buttons (keyboard-reachable) with
 *      a translated type pill and a monogram — not emoji — fallback.
 *   4. The wishlist heart survives a remount (localStorage), honestly
 *      scoped as a device-side list.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../i18n/i18n';
import { MemoryRouter, useLocation } from 'react-router-dom';
import React from 'react';
import type { Product } from '../../models';

/* ------------------------------------------------------------------ mocks */

const { vmState, setters } = vi.hoisted(() => ({
  vmState: {
    products: [] as unknown[],
    categories: [] as unknown[],
    searchQuery: '',
    isLoading: false,
    error: null as string | null,
  },
  setters: {
    setSelectedCategory: vi.fn(),
    setSelectedOccasion: vi.fn(),
    setSearchQuery: vi.fn(),
    setSortBy: vi.fn(),
  },
}));

vi.mock('../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({
    products: vmState.products,
    categories: vmState.categories,
    selectedCategory: '',
    setSelectedCategory: setters.setSelectedCategory,
    selectedOccasion: '',
    setSelectedOccasion: setters.setSelectedOccasion,
    searchQuery: vmState.searchQuery,
    setSearchQuery: setters.setSearchQuery,
    sortBy: 'recommended',
    setSortBy: setters.setSortBy,
    isLoading: vmState.isLoading,
    error: vmState.error,
    refresh: vi.fn(),
  }),
}));

vi.mock('../../hooks/useCapabilities', () => ({
  useCapabilities: () => ({
    capabilities: { bnpl_live: false, tryon_live: false },
    isLoading: false,
  }),
}));
vi.mock('../../hooks/useTryOnAvailability', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../hooks/useTryOnAvailability')>();
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
vi.mock('../../services/apiServices', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('../../services/apiServices')>();
  return {
    ...original,
    catalogService: {
      ...original.catalogService,
      autocompleteCatalog: vi.fn().mockResolvedValue({ suggestions: [] }),
    },
  };
});

import { DiscoverView } from '../consumer/DiscoverView';
import { catalogService } from '../../services/apiServices';

const mockedAutocomplete = catalogService.autocompleteCatalog as ReturnType<
  typeof vi.fn
>;

/* --------------------------------------------------------------- fixtures */

const CATALOG: Product[] = [1, 2].map(
  (n) =>
    ({
      id: n,
      title: `Piece ${n}`,
      slug: `piece-${n}`,
      brand_name: 'Reiss',
      base_price: 100 + n,
      color_family: 'Navy Blue',
      occasion_tags: ['Work'],
      thumbnail_url: `https://img.example/p${n}.jpg`,
    }) as unknown as Product,
);

let lastSearch = '';
const LocationProbe: React.FC = () => {
  lastSearch = useLocation().search;
  return null;
};

function renderAt(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[url]}>
          <DiscoverView />
          <LocationProbe />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  window.localStorage.clear();
  vmState.products = CATALOG;
  vmState.categories = [{ id: 1, name: 'Dresses', slug: 'dresses' }];
  vmState.searchQuery = '';
  vmState.isLoading = false;
  vmState.error = null;
  Object.values(setters).forEach((fn) => fn.mockReset());
  mockedAutocomplete.mockReset().mockResolvedValue({ suggestions: [] });
});
afterEach(() => cleanup());

/* ------------------------------------------------------------------ tests */

describe('1. deep-link hydration with validation', () => {
  it('applies known occasion/q/sort tokens once and shows the palette chip', async () => {
    renderAt('/discover?occasion=Work&palette=Navy%20Blue&q=silk&sort=newest');
    await waitFor(() => {
      expect(setters.setSelectedOccasion).toHaveBeenCalledWith('Work');
      expect(setters.setSearchQuery).toHaveBeenCalledWith('silk');
      expect(setters.setSortBy).toHaveBeenCalledWith('newest');
    });
    // Palette is view-local state: its application is visible as the
    // active-filter chip carrying the TRANSLATED swatch name.
    expect(
      screen.getByText(
        i18n.t('discover.active_palette', {
          name: i18n.t('discover.color_navy_blue'),
        }) as string,
      ),
    ).toBeInTheDocument();
  });

  it('ignores junk values instead of applying them', async () => {
    renderAt('/discover?occasion=Nonsense&palette=Hotpink&sort=hack');
    // Give the mount effects a tick.
    await new Promise((r) => setTimeout(r, 20));
    expect(setters.setSelectedOccasion).not.toHaveBeenCalled();
    expect(setters.setSortBy).not.toHaveBeenCalled();
  });
});

describe('2. interaction-time write-back', () => {
  it('selecting a category writes ?category= to the URL', () => {
    renderAt('/discover');
    fireEvent.click(screen.getByRole('button', { name: 'Dresses' }));
    expect(setters.setSelectedCategory).toHaveBeenCalledWith('dresses');
    expect(lastSearch).toContain('category=dresses');
  });

  it('clear-filters empties the tracked params', () => {
    vmState.searchQuery = 'silk'; // makes the active-filter bar render
    renderAt('/discover?q=silk');
    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('discover.clear_filters') }),
    );
    expect(lastSearch).not.toContain('q=');
  });
});

describe('3. autocomplete is keyboard-real and emoji-free', () => {
  it('renders suggestions as buttons with a translated type pill and monogram fallback', async () => {
    vmState.searchQuery = 'silk';
    mockedAutocomplete.mockResolvedValue({
      suggestions: [
        { type: 'brand', title: 'Maison Silk', subtitle: '4 pieces' },
      ],
    });
    renderAt('/discover');
    const sug = await screen.findByRole('button', { name: /Maison Silk/ });
    expect(sug).toBeInTheDocument();
    // Translated type pill, not the raw API token:
    expect(sug.textContent).toContain(i18n.t('discover.sug_type_brand'));
    // Monogram fallback — the first letter, never an emoji glyph:
    expect(sug.textContent).toContain('M');
    expect(sug.textContent).not.toMatch(/\u{1F3F7}|\u{1F4C1}/u);
  });
});

describe('4. wishlist persistence', () => {
  it('a toggled heart survives a full remount via localStorage', async () => {
    const first = renderAt('/discover');
    const hearts = screen.getAllByRole('button', {
      name: i18n.t('a11y.toggle_wishlist'),
    });
    fireEvent.click(hearts[0]);
    await waitFor(() =>
      expect(
        JSON.parse(window.localStorage.getItem('confit.wishlist.v1') ?? '[]'),
      ).toContain(1),
    );
    first.unmount();

    renderAt('/discover');
    const heartsAgain = screen.getAllByRole('button', {
      name: i18n.t('a11y.toggle_wishlist'),
    });
    expect(heartsAgain[0].getAttribute('aria-pressed')).toBe('true');
    expect(heartsAgain[1].getAttribute('aria-pressed')).toBe('false');
  });
});
