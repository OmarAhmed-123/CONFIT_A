/**
 * C02 passes — Discover URL state, data-driven occasion pills, APG
 * combobox autocomplete, persistent wishlist.
 *
 *   1. Deep-link hydration: ?palette/?q/?sort validate on mount;
 *      ?occasion validates against the LIVE vocabulary (async, like
 *      ?category) and normalises case. Junk is ignored, never applied.
 *   2. Write-back at interaction time: category/occasion pills rewrite
 *      the URL (replace); clear-filters empties it.
 *   3. Occasion pills are DATA: they render from /catalog/occasions, so
 *      the UI can never advertise a filter with zero matching products
 *      (the old hardcoded list included "Evening"/"Everyday" which exist
 *      on NO product — permanently empty results).
 *   4. Autocomplete is a real APG combobox: role=combobox input,
 *      role=option rows, ArrowDown/ArrowUp + Enter driven via
 *      aria-activedescendant, Escape closes. No emoji fallbacks.
 *   5. The wishlist heart survives a remount (localStorage).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, screen, within, fireEvent, waitFor } from '@testing-library/react';
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
    occasions: [] as { value: string; count: number }[],
    searchQuery: '',
    selectedColor: '',
    isLoading: false,
    error: null as string | null,
  },
  setters: {
    setSelectedCategory: vi.fn(),
    setSelectedOccasion: vi.fn(),
    setSelectedColor: vi.fn(),
    setSearchQuery: vi.fn(),
    setSortBy: vi.fn(),
  },
}));

vi.mock('../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({
    products: vmState.products,
    categories: vmState.categories,
    occasions: vmState.occasions,
    selectedCategory: '',
    setSelectedCategory: setters.setSelectedCategory,
    selectedOccasion: '',
    setSelectedOccasion: setters.setSelectedOccasion,
    selectedColor: vmState.selectedColor,
    setSelectedColor: setters.setSelectedColor,
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
      occasion_tags: ['work'],
      thumbnail_url: `https://img.example/p${n}.jpg`,
    }) as unknown as Product,
);

// Shape of GET /catalog/occasions — lowercase canonical tokens + counts,
// most-stocked first (mirrors the live production vocabulary).
const OCCASIONS = [
  { value: 'wedding', count: 9 },
  { value: 'dinner', count: 9 },
  { value: 'work', count: 8 },
  { value: 'party', count: 5 },
  { value: 'black_tie', count: 1 },
];

let lastSearch = '';
let lastPath = '';
const LocationProbe: React.FC = () => {
  const loc = useLocation();
  lastSearch = loc.search;
  lastPath = loc.pathname;
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
  vmState.occasions = OCCASIONS;
  vmState.searchQuery = '';
  vmState.selectedColor = '';
  vmState.isLoading = false;
  vmState.error = null;
  Object.values(setters).forEach((fn) => fn.mockReset());
  mockedAutocomplete.mockReset().mockResolvedValue({ suggestions: [] });
});
afterEach(() => cleanup());

/* ------------------------------------------------------------------ tests */

describe('1. deep-link hydration with validation', () => {
  it('applies palette/q/sort on mount and occasion once the vocabulary arrives', async () => {
    renderAt('/discover?occasion=WORK&palette=Navy%20Blue&q=silk&sort=newest');
    await waitFor(() => {
      // Occasion validates against the live vocabulary and NORMALISES
      // case — the capitalized token killed the filter in production.
      expect(setters.setSelectedOccasion).toHaveBeenCalledWith('work');
      expect(setters.setSelectedColor).toHaveBeenCalledWith('Navy Blue');
      expect(setters.setSearchQuery).toHaveBeenCalledWith('silk');
      expect(setters.setSortBy).toHaveBeenCalledWith('newest');
    });
  });

  it('ignores junk values instead of applying them', async () => {
    renderAt('/discover?occasion=nonexistent_tag&palette=Hotpink&sort=hack');
    await new Promise((r) => setTimeout(r, 20));
    expect(setters.setSelectedOccasion).not.toHaveBeenCalled();
    expect(setters.setSelectedColor).not.toHaveBeenCalled();
    expect(setters.setSortBy).not.toHaveBeenCalled();
  });

  it('does not hydrate occasion before the vocabulary exists', async () => {
    vmState.occasions = [];
    renderAt('/discover?occasion=work');
    await new Promise((r) => setTimeout(r, 20));
    expect(setters.setSelectedOccasion).not.toHaveBeenCalled();
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
    vmState.searchQuery = 'silk';
    renderAt('/discover?q=silk');
    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('discover.clear_filters') }),
    );
    expect(lastSearch).not.toContain('q=');
  });
});

describe('3. occasion pills come from the live vocabulary', () => {
  it('renders a pill per real tag with its translated label', () => {
    renderAt('/discover');
    // 'work' has a translation; 'black_tie' falls back to a humanised token.
    expect(
      screen.getByRole('button', { name: i18n.t('discover.occasion_work') }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: i18n.t('discover.occasion_party') }),
    ).toBeInTheDocument();
  });

  it('never renders the invented legacy pills with zero products', () => {
    renderAt('/discover');
    // "Evening"/"Everyday" existed on NO product — the data-driven row
    // must not resurrect them.
    expect(
      screen.queryByRole('button', { name: i18n.t('discover.occasion_evening') }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: i18n.t('discover.occasion_everyday') }),
    ).not.toBeInTheDocument();
  });

  it('clicking a pill applies the lowercase canonical token and writes the URL', () => {
    renderAt('/discover');
    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('discover.occasion_work') }),
    );
    expect(setters.setSelectedOccasion).toHaveBeenCalledWith('work');
    expect(lastSearch).toContain('occasion=work');
  });
});

describe('4. APG combobox autocomplete', () => {
  const SUGGESTIONS = [
    { type: 'product', title: 'Silk Blouse', slug_or_query: 'piece-1' },
    { type: 'brand', title: 'Maison Silk', subtitle: '4 pieces' },
  ];

  async function openWithSuggestions() {
    vmState.searchQuery = 'silk';
    mockedAutocomplete.mockResolvedValue({ suggestions: SUGGESTIONS });
    renderAt('/discover');
    await screen.findByRole('listbox');
  }

  const searchBox = () =>
    screen.getByRole('combobox', { name: i18n.t('discover.search_label') });
  const listboxOptions = () =>
    within(screen.getByRole('listbox')).getAllByRole('option');

  it('renders role=option rows inside a listbox, no emoji fallback', async () => {
    await openWithSuggestions();
    const options = listboxOptions();
    expect(options).toHaveLength(2);
    expect(options[1].textContent).toContain('Maison Silk');
    expect(options[1].textContent).toContain(
      i18n.t('discover.sug_type_brand') as string,
    );
    // Monogram fallback, never an emoji glyph:
    expect(options[1].textContent).not.toMatch(/\u{1F3F7}|\u{1F4C1}/u);
  });

  it('ArrowDown moves aria-activedescendant and Enter selects the option', async () => {
    await openWithSuggestions();
    const input = searchBox();
    expect(input.getAttribute('aria-expanded')).toBe('true');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input.getAttribute('aria-activedescendant')).toBe('discover-sug-0');
    expect(listboxOptions()[0].getAttribute('aria-selected')).toBe('true');

    // Enter on a product suggestion navigates to its PDP.
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(lastPath).toBe('/product/piece-1');
  });

  it('ArrowUp wraps to the last option and Escape closes the listbox', async () => {
    await openWithSuggestions();
    const input = searchBox();
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input.getAttribute('aria-activedescendant')).toBe('discover-sug-1');

    fireEvent.keyDown(input, { key: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    );
    expect(input.getAttribute('aria-expanded')).toBe('false');
  });

  it('clicking a non-product suggestion fills the query and syncs the URL', async () => {
    await openWithSuggestions();
    fireEvent.click(listboxOptions()[1]);
    expect(setters.setSearchQuery).toHaveBeenCalledWith('Maison Silk');
    expect(lastSearch).toContain('q=Maison+Silk');
  });
});

describe('5. wishlist persistence', () => {
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
