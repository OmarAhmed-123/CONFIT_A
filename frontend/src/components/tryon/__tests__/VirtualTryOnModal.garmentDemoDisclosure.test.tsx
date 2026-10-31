import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '../../../i18n/i18n';
import { useUIStore } from '../../../stores/uiStore';
import { VirtualTryOnModal } from '../VirtualTryOnModal';

/**
 * Products 1-4 render from AI-generated "generated-demo" garment assets: the
 * flat-lay dressed onto the model is NOT the catalogue photograph. The avatar
 * strip already discloses that demo models are not customers; the garment has
 * the same obligation, and it has to be said in the shopper's language.
 *
 * The disclosure is driven by the backend's per-product provenance — not by a
 * blanket "everything is a demo" label, which would become a lie the day real
 * photography lands.
 */

const state = vi.hoisted(() => ({
  provenance: 'generated-demo' as string | null,
}));

vi.mock('../../../privacy/usePhotoConsent', () => ({
  usePhotoConsent: () => ({ requestConsent: vi.fn(), consentDialog: null }),
}));

vi.mock('../../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({ products: [] }),
}));

vi.mock('../../../viewmodels/useTryOnViewModel', () => ({
  useTryOnViewModel: () => ({
    tryOnStatus: 'idle',
    errorMessage: null,
    motionStatus: 'idle',
    isRendering: false,
    isAnimating: false,
    multiTryOnResult: null,
    animationResult: null,
    activeKeyframeIndex: 0,
    setActiveKeyframeIndex: vi.fn(),
    outputAspect: 'portrait',
    setOutputAspect: vi.fn(),
    activePreviewTab: 'static',
    setActivePreviewTab: vi.fn(),
    selectedAvatar: 'avatar_athletic_m',
    setSelectedAvatar: vi.fn(),
    uploadedUserImage: null,
    setUploadedUserImage: vi.fn(),
    appliedGarments: {},
    isBeforeAfterActive: false,
    setIsBeforeAfterActive: vi.fn(),
    splitSliderPosition: 50,
    setSplitSliderPosition: vi.fn(),
    totalPrice: 0,
    dynamicFitScore: 0,
    capabilityLoading: false,
    capabilityMessage: null,
    vtonCapabilities: {
      1: {
        product_id: 1,
        state: 'supported',
        reason_code: 'SUPPORTED',
        message: 'ok',
        provider: 'fashn_vton_segfee',
        garment_asset_provenance: state.provenance,
      },
    },
    checkTryOnCapabilities: vi.fn(),
    addGarmentToCanvas: vi.fn(),
    removeGarmentFromCanvas: vi.fn(),
    clearCanvas: vi.fn(),
    undoLastAction: vi.fn(),
    addAllDressedToCart: vi.fn(),
    runTryOn: vi.fn(),
    runAnimatedTryOn: vi.fn(),
  }),
}));

const PRODUCT = {
  id: 1,
  title: 'Tailored Test Blazer',
  slug: 'tailored-test-blazer',
  category_name: 'Tops & Shirts',
  brand_name: 'Test Brand',
  base_price: 100,
  thumbnail_url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
  skus: [],
} as any;

beforeEach(async () => {
  await i18n.changeLanguage('en');
  state.provenance = 'generated-demo';
  useUIStore.setState({ tryOnProduct: null, rulerProduct: null, rulerMeasurements: null });
});

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('en');
  useUIStore.setState({ tryOnProduct: null, rulerProduct: null, rulerMeasurements: null });
});

function open() {
  render(
    <MemoryRouter>
      <VirtualTryOnModal />
    </MemoryRouter>,
  );
  act(() => useUIStore.getState().openTryOn(PRODUCT));
}

describe('demo garment assets', () => {
  it('are disclosed in English', async () => {
    open();
    const notice = await screen.findByTestId('tryon-garment-demo-disclosure');
    expect(notice).toBeVisible();
    expect(notice.textContent).toMatch(/AI-generated demo/i);
  });

  it('are disclosed in Arabic', async () => {
    await i18n.changeLanguage('ar');
    open();
    const notice = await screen.findByTestId('tryon-garment-demo-disclosure');
    // Must be the Arabic copy, not the English string carried through.
    expect(notice.textContent).not.toMatch(/AI-generated demo/i);
    expect(notice.textContent).toMatch(/[؀-ۿ]/);
  });

  it('are NOT disclosed for a real product photograph', async () => {
    state.provenance = 'real-photo';
    open();
    await screen.findByRole('dialog', { name: /virtual try-on studio/i });
    expect(screen.queryByTestId('tryon-garment-demo-disclosure')).toBeNull();
  });

  it('are NOT silently treated as real when the provenance is unknown', async () => {
    state.provenance = null;
    open();
    await screen.findByRole('dialog', { name: /virtual try-on studio/i });
    expect(screen.queryByTestId('tryon-garment-demo-disclosure')).toBeNull();
  });
});
