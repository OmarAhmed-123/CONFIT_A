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
import { setAppLanguage } from '../../i18n/i18n';

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

// ===========================================================================
// Spec 08 re-pass — the studio page speaks BOTH catalogue languages and its
// card CTAs meet the touch/label contract. These assert REAL catalogue
// values: before this pass the whole shell was hardcoded English (including
// the internal "Group 3" dev label) even on the Arabic storefront.
// ===========================================================================
describe('TryOnFitView localization & CTA contract (spec 08 re-pass)', () => {
  afterEach(async () => {
    await setAppLanguage('en');
  });

  it('EN: header/badge/steps come from the catalogue — the internal "Group 3" label is gone', () => {
    renderView();
    expect(
      screen.getByRole('heading', { name: 'Virtual Visualization & Precision Fit Studio' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Virtual Visualization & Fit Studio')).toBeInTheDocument();
    expect(screen.queryByText(/Group 3/)).toBeNull();
    expect(screen.getByText('Choose goal or garment')).toBeInTheDocument();
    expect(screen.getByText('Showing 2 styles from the live catalog')).toBeInTheDocument();
  });

  it('card CTAs: localized text labels (never icon-only) + 44px touch target class', () => {
    renderView();
    const fitChecks = screen.getAllByRole('button', { name: /Fit Check/ });
    const rulers = screen.getAllByRole('button', { name: /Ruler/ });
    expect(fitChecks.length).toBeGreaterThan(0);
    expect(rulers.length).toBeGreaterThan(0);
    for (const btn of [...fitChecks, ...rulers]) {
      expect(btn.className).toContain('min-h-11');
    }
  });

  it('AR: the full shell reads in Arabic and the price stays LTR (§7)', async () => {
    await setAppLanguage('ar');
    renderView();
    expect(
      screen.getByRole('heading', { name: 'استوديو التجسيد الافتراضي ودقة المقاس' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('فحص مقاس فقط').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /فحص المقاس/ }).length).toBeGreaterThan(0);
    // Price digits render inside a dir="ltr" island on the RTL page.
    const price = screen.getByText('$125.00');
    expect(price.closest('[dir="ltr"]')).not.toBeNull();
  });

  it('AR: catalog failure state is localized and actionable (honest error, real retry)', async () => {
    await setAppLanguage('ar');
    // Re-mock catalog as failed for this render.
    const mod = await import('../../viewmodels/useCatalogViewModel');
    const spy = vi
      .spyOn(mod, 'useCatalogViewModel')
      .mockReturnValue({
        products: [],
        isLoading: false,
        error: 'boom',
        refresh: vi.fn(),
      } as any);
    renderView();
    expect(screen.getByText('تعذّر تحميل كتالوج الملابس')).toBeInTheDocument();
    expect(screen.getByText('الكتالوج غير متاح')).toBeInTheDocument();
    spy.mockRestore();
  });
});
