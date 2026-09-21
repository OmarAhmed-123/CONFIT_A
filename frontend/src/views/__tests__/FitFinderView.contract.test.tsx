/**
 * Fit Finder client-contract regressions.
 *
 * These cover the two client-side behaviours the audit called unverified:
 *
 *  1. Refusal handling — when the engine returns `recommended: false` the UI
 *     must show the reason and the missing inputs, and must NOT print a size.
 *     (The pre-rewrite client had no refusal branch at all; a refusal rendered
 *     as "Size undefined".)
 *  2. Unit handling — the client must send the numbers the user typed plus an
 *     explicit `units` tag, and must never convert before sending. Conversion
 *     happens exactly once, on the server. Toggling cm -> in must re-express
 *     the same body rather than reinterpret the digits.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, cleanup, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../i18n/i18n';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

const { calcMock } = vi.hoisted(() => ({ calcMock: vi.fn() }));

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

function fillForm() {
  fireEvent.change(screen.getByLabelText(/height/i), { target: { value: '175' } });
  fireEvent.change(screen.getByLabelText(/weight/i), { target: { value: '78' } });
  fireEvent.change(screen.getByLabelText(/garment to size/i), { target: { value: '7' } });
}

async function submit() {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /calculate my size/i }));
  });
}

describe('FitFinderView — engine contract', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders a refusal with its reason and missing inputs, and names no size', async () => {
    calcMock.mockResolvedValue({
      recommended: false,
      reason_code: 'no_size_chart',
      missing: ['chest_cm', 'size_chart'],
      confidence_disclosure:
        'This brand has not published a size chart for this garment, so we cannot map your measurements to a size.',
      engine_version: 'fit-engine/1.0.0',
    });

    renderView();
    fillForm();
    await submit();

    await waitFor(() => {
      expect(document.body.textContent ?? '').toContain('has not published a size chart');
    });
    // The refusal must not be dressed up as a recommendation.
    expect(document.body.textContent ?? '').not.toMatch(/size undefined|size null/i);
    expect(screen.queryByText(/^Recommended size$/i)).toBeNull();
    // and it should tell the user what would unblock it
    expect(document.body.textContent ?? '').toMatch(/chest/i);
  });

  it('sends the typed numbers unconverted, tagged with the active unit system', async () => {
    calcMock.mockResolvedValue({
      recommended: false,
      reason_code: 'insufficient_measurements',
      missing: ['chest_cm'],
      confidence_disclosure: 'Not enough measurements.',
      engine_version: 'fit-engine/1.0.0',
    });

    renderView();
    fillForm();
    await submit();

    expect(calcMock).toHaveBeenCalledTimes(1);
    const payload = calcMock.mock.calls[0][0];
    expect(payload.units).toBe('metric');
    expect(payload.height).toBe(175); // exactly what was typed — no cm->in math
    expect(payload.weight).toBe(78);
    expect(payload.product_id).toBe(7);
  });

  it('switching to imperial re-expresses the same body and tags the new units', async () => {
    calcMock.mockResolvedValue({
      recommended: false,
      reason_code: 'insufficient_measurements',
      missing: ['chest_cm'],
      confidence_disclosure: 'Not enough measurements.',
      engine_version: 'fit-engine/1.0.0',
    });

    renderView();
    fillForm();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'in / lbs' }));
    });

    // 175 cm -> ~68.9 in, 78 kg -> ~172 lb. The digits must change, because the
    // body did not: this is the bug class where "175" silently became 175 in.
    const height = Number((screen.getByLabelText(/height/i) as HTMLInputElement).value);
    const weight = Number((screen.getByLabelText(/weight/i) as HTMLInputElement).value);
    expect(height).toBeGreaterThan(68);
    expect(height).toBeLessThan(70);
    expect(weight).toBeGreaterThan(170);
    expect(weight).toBeLessThan(174);

    await submit();
    const payload = calcMock.mock.calls[0][0];
    expect(payload.units).toBe('imperial');
    expect(payload.height).toBe(height); // still unconverted on the wire
    expect(payload.weight).toBe(weight);
  });

  it('round-trips metric -> imperial -> metric without drifting the body', async () => {
    calcMock.mockResolvedValue({
      recommended: false,
      reason_code: 'insufficient_measurements',
      missing: ['chest_cm'],
      confidence_disclosure: 'Not enough measurements.',
      engine_version: 'fit-engine/1.0.0',
    });

    renderView();
    fillForm();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'in / lbs' }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'cm / kg' }));
    });

    const height = Number((screen.getByLabelText(/height/i) as HTMLInputElement).value);
    const weight = Number((screen.getByLabelText(/weight/i) as HTMLInputElement).value);
    // One decimal place of display rounding each way => allow 0.2 of slack.
    expect(Math.abs(height - 175)).toBeLessThanOrEqual(0.2);
    expect(Math.abs(weight - 78)).toBeLessThanOrEqual(0.3);
  });
});
