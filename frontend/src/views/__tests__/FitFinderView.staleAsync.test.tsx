/**
 * P1-01 hardening regression: a late calculate response must never resurrect
 * a stale recommendation after the user edits the form mid-flight.
 *
 * Reproduces the live-preview race: click Calculate -> (request in flight) ->
 * edit height -> setResult(null) fires -> OLD response resolves -> pre-fix the
 * component called setResult(res) unconditionally and the recommendation for
 * the OLD measurements reappeared on screen.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, cleanup, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../i18n/i18n';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

const { calcMock, catalogMock } = vi.hoisted(() => ({
  calcMock: vi.fn(),
  catalogMock: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  tryOnService: { calculateNoPhotoFit: (...a: unknown[]) => calcMock(...a) },
}));
vi.mock('../../services/measurementService', () => ({
  measurementService: { status: vi.fn().mockResolvedValue({ has_profile: false }) },
}));
vi.mock('../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({
    products: [
      { id: 7, title: 'Audit Clutch', brand_name: 'Reiss', base_price: 150, slug: 'audit-clutch' },
    ],
    isLoading: false,
    error: null,
  }),
  __catalogMock: catalogMock,
}));

import { FitFinderView } from '../consumer/FitFinderView';

/**
 * A minimal but SHAPE-ACCURATE success payload for the current engine contract
 * (backend/app/schemas/tryon.py :: NoPhotoFitResponse). The previous version of
 * this test mocked a flat legacy object with `brand_sizing_tendency` as a bare
 * string; that shape can no longer come off the wire, so asserting against it
 * would have made this regression test pass without exercising the real render
 * path. The stale-async intent of the test is unchanged.
 */
function fitResponse(overrides: Record<string, unknown> = {}) {
  return {
    recommended: true,
    recommended_size: 'M',
    alternative_size: 'L',
    is_between_sizes: false,
    confidence_score: 78,
    confidence_factors: ['chest measured directly', 'brand-published chart'],
    is_estimated: false,
    fit_verdict: 'Should fit comfortably through the chest and waist.',
    fit_breakdown: { chest: 'just right', waist: 'slightly loose' },
    size_comparison_table: [
      {
        size: 'M',
        ranges_cm: { chest: [94, 102], waist: [79, 87] },
        fit_score: 92.4,
        fit_rating: 'best match',
        in_stock: true,
        stock_level: 7,
        is_recommended: true,
      },
    ],
    measurements_used: {
      height_cm: 175,
      weight_kg: 78,
      chest_cm: 98,
      estimated_fields: [],
      sections_scored: ['chest'],
    },
    size_chart_source: {
      source: 'brand_chart',
      label: 'BRAND TENDENCY chart',
      updated_at: '2026-04-02',
      standard: null,
      measurement_type: 'body',
      is_brand_published: true,
      notes: [],
    },
    garment: {
      garment_class: 'top',
      material: 'cotton',
      ease_targets_cm: { chest: 8 },
      category: 'Shirts',
    },
    brand_sizing_tendency: {
      summary: 'Reiss runs true to size on its published chart.',
      has_published_chart: true,
      chart_updated_at: '2026-04-02',
      return_rate_signal: null,
      known_size_bias: null,
      known_size_bias_note: null,
    },
    return_risk: { label: 'low', basis: 'measured chest inside the M range' },
    notes: [],
    engine_version: 'fit-engine/1.0.0',
    return_risk_score: 'low',
    ...overrides,
  };
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <FitFinderView />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

const VISIBLE_RESULT_MARK = 'BRAND TENDENCY';

function fillForm() {
  fireEvent.change(screen.getByLabelText(/height/i), { target: { value: '175' } });
  fireEvent.change(screen.getByLabelText(/weight/i), { target: { value: '78' } });
  const select = screen.getByLabelText(/garment to size/i) as HTMLSelectElement;
  fireEvent.change(select, { target: { value: '7' } });
}

describe('P1-01 stale-async guard (FitFinderView)', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('a late response does NOT repopulate the recommendation after an input change', async () => {
    let resolveLate!: (v: unknown) => void;
    calcMock.mockReturnValue(new Promise((r) => { resolveLate = r; }));
    renderView();

    await fillForm();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /calculate my size/i }));
    });

    // user edits height while the request is still in flight
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/height/i), { target: { value: '188' } });
    });

    // the OLD response finally resolves
    await act(async () => {
      resolveLate(fitResponse());
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(document.body.textContent ?? '').not.toContain(VISIBLE_RESULT_MARK);
    });
    expect(document.body.textContent ?? '').not.toMatch(/recommended size|your size is/i);
  });

  it('a fresh (non-superseded) response still renders normally', async () => {
    calcMock.mockResolvedValue(fitResponse());

    renderView();

    await fillForm();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /calculate my size/i }));
    });

    await waitFor(() => {
      expect(document.body.textContent ?? '').toContain(VISIBLE_RESULT_MARK);
    });
  });
});
