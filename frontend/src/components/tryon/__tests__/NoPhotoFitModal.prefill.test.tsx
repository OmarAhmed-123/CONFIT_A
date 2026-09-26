import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useUIStore, type FitMeasurementPrefill } from '../../../stores/uiStore';
import { NoPhotoFitModal } from '../NoPhotoFitModal';

const mocks = vi.hoisted(() => ({
  runNoPhotoFit: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../../viewmodels/useTryOnViewModel', () => ({
  useTryOnViewModel: () => ({
    rulerLoading: false,
    noPhotoResult: null,
    runNoPhotoFit: mocks.runNoPhotoFit,
  }),
}));

vi.mock('../../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: vi.fn(), openCart: vi.fn() }),
}));

vi.mock('../../../privacy/usePhotoConsent', () => ({
  usePhotoConsent: () => ({ requestConsent: vi.fn(), consentDialog: null }),
}));

const PRODUCT = {
  id: 7,
  title: 'Fit Profile Shirt',
  category_name: 'Tops & Shirts',
  brand_name: 'Test Brand',
  base_price: 120,
  skus: [],
} as any;

const MEASUREMENTS: FitMeasurementPrefill = {
  height_cm: 183,
  weight_kg: 79,
  body_shape: 'Athletic V-Taper',
  chest_cm: 104,
  waist_cm: 86,
  shoulder_cm: 48,
  hip_cm: 99,
  confidence_score: 80,
};

beforeEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ tryOnProduct: null, rulerProduct: null, rulerMeasurements: null });
});

afterEach(() => {
  cleanup();
  useUIStore.setState({ tryOnProduct: null, rulerProduct: null, rulerMeasurements: null });
});

describe('NoPhotoFitModal camera-profile handoff', () => {
  it('preserves the applied measurements and immediately runs the real fit contract', async () => {
    act(() => useUIStore.getState().openRuler(PRODUCT, MEASUREMENTS));
    render(
      <MemoryRouter>
        <NoPhotoFitModal />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mocks.runNoPhotoFit).toHaveBeenCalledWith({
        ...MEASUREMENTS,
        preferred_fit: 'regular',
      }),
    );
    const sliders = screen.getAllByRole('slider');
    expect(sliders[0]).toHaveValue(String(MEASUREMENTS.height_cm));
    expect(sliders[1]).toHaveValue(String(MEASUREMENTS.weight_kg));
    expect(screen.getByText(`Height: ${MEASUREMENTS.height_cm} cm`)).toBeVisible();
    expect(screen.getByText(`Weight: ${MEASUREMENTS.weight_kg} kg`)).toBeVisible();
  });

  it('clears the prefill when the fit modal closes', () => {
    act(() => useUIStore.getState().openRuler(PRODUCT, MEASUREMENTS));
    render(
      <MemoryRouter>
        <NoPhotoFitModal />
      </MemoryRouter>,
    );

    act(() => useUIStore.getState().closeRuler());
    expect(useUIStore.getState().rulerProduct).toBeNull();
    expect(useUIStore.getState().rulerMeasurements).toBeNull();
    expect(screen.queryByText('Fit Profile Shirt')).toBeNull();
  });
});
