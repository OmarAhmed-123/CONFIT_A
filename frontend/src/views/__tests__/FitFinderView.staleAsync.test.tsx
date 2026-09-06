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
      resolveLate({
        recommended_size: 'M',
        confidence_score: 90,
        brand_tendency: 'runs true to size',
        return_risk: 'low',
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(document.body.textContent ?? '').not.toContain(VISIBLE_RESULT_MARK);
    });
    expect(document.body.textContent ?? '').not.toMatch(/recommended size|your size is/i);
  });

  it('a fresh (non-superseded) response still renders normally', async () => {
    calcMock.mockResolvedValue({
      recommended_size: 'M',
      confidence_score: 90,
      brand_sizing_tendency: 'BRAND TENDENCY visible',
      return_risk_score: 'low',
      fit_breakdown: { chest: 'comfortable' },
      size_comparison_table: [
        { size: 'M', chest: '96-102', waist: '82-88', fit: 'Comfortable' },
      ],
    });
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
