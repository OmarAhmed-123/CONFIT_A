import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  kind: 'fitCheck' as 'render' | 'fitCheck' | 'blocked',
  renderAvailable: false as boolean | null,
  openTryOn: vi.fn(),
  openRuler: vi.fn(),
  openVisualSearch: vi.fn(),
  accessory: {
    id: 10,
    title: 'Catalogue-First Clutch',
    slug: 'catalogue-first-clutch',
    category_name: 'Accessories',
    brand_name: 'Test Brand',
    color_family: 'Gold',
    base_price: 95,
    thumbnail_url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
    style_compatibility_score: 80,
    skus: [],
  } as any,
  product: {
    id: 11,
    title: 'Tailored Handoff Shirt',
    slug: 'tailored-handoff-shirt',
    category_name: 'Tops & Shirts',
    brand_name: 'Test Brand',
    color_family: 'Navy',
    base_price: 125,
    thumbnail_url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
    style_compatibility_score: 80,
    skus: [],
  } as any,
  measurements: {
    height_cm: 183,
    weight_kg: 79,
    body_shape: 'Athletic V-Taper',
    chest_cm: 104,
    waist_cm: 86,
    shoulder_cm: 48,
    hip_cm: 99,
    confidence_score: 80,
  },
}));

const PRODUCT = mocks.product;
const MEASUREMENTS = mocks.measurements;

vi.mock('../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({
    products: [mocks.accessory, mocks.product],
    isLoading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({
    openTryOn: mocks.openTryOn,
    openRuler: mocks.openRuler,
    openVisualSearch: mocks.openVisualSearch,
  }),
}));

vi.mock('../../hooks/useTryOnAvailability', () => ({
  useTryOnAvailability: () => ({
    ctaKind: () => mocks.kind,
    renderAvailable: mocks.renderAvailable,
    userMessage: null,
    gate: (handlers: { render: () => void; fitCheck: () => void }) => () =>
      mocks.kind === 'render' ? handlers.render() : handlers.fitCheck(),
  }),
}));

vi.mock('../../components/showcase/DesignShowcases', () => ({
  CircularGalleryShowcase: () => null,
}));

vi.mock('../../components/tryon/TryOnEngineStatus', () => ({
  TryOnEngineStatus: () => null,
}));

vi.mock('../../components/tryon/CameraScanModal', () => ({
  CameraScanModal: ({ isOpen, onApplyMeasurements }: any) =>
    isOpen ? (
      <button type="button" onClick={() => onApplyMeasurements(mocks.measurements)}>
        Apply measured profile
      </button>
    ) : null,
}));

import { TryOnFitView } from '../consumer/TryOnFitView';

function renderView() {
  return render(
    <MemoryRouter>
      <TryOnFitView />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.kind = 'fitCheck';
  mocks.renderAvailable = false;
  vi.clearAllMocks();
});

afterEach(() => cleanup());

describe('TryOnFitView measurement apply flow', () => {
  it('uses the fit engine with the same measurements when GPU rendering is offline', () => {
    renderView();
    fireEvent.click(screen.getByText(/camera-assisted size profile/i));
    fireEvent.click(screen.getByRole('button', { name: /apply measured profile/i }));

    expect(mocks.openRuler).toHaveBeenCalledWith(PRODUCT, MEASUREMENTS);
    expect(mocks.openTryOn).not.toHaveBeenCalled();
  });

  it('opens visual try-on only when the live capability gate says it can render', () => {
    mocks.kind = 'render';
    mocks.renderAvailable = true;
    renderView();
    fireEvent.click(screen.getByText(/camera-assisted size profile/i));
    fireEvent.click(screen.getByRole('button', { name: /apply measured profile/i }));

    expect(mocks.openTryOn).toHaveBeenCalledWith(PRODUCT);
    expect(mocks.openRuler).not.toHaveBeenCalled();
  });

  it('uses fit instead of treating an unresolved capability probe as render permission', () => {
    mocks.kind = 'render';
    mocks.renderAvailable = null;
    renderView();
    fireEvent.click(screen.getByText(/camera-assisted size profile/i));
    fireEvent.click(screen.getByRole('button', { name: /apply measured profile/i }));

    expect(mocks.openRuler).toHaveBeenCalledWith(PRODUCT, MEASUREMENTS);
    expect(mocks.openTryOn).not.toHaveBeenCalled();
  });
});
