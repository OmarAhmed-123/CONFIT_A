import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useUIStore } from '../../../stores/uiStore';
import { VirtualTryOnModal } from '../VirtualTryOnModal';

const mocks = vi.hoisted(() => ({
  checkTryOnCapabilities: vi.fn(),
  runTryOn: vi.fn(),
  runAnimatedTryOn: vi.fn(),
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
    vtonCapabilities: null,
    checkTryOnCapabilities: mocks.checkTryOnCapabilities,
    addGarmentToCanvas: vi.fn(),
    removeGarmentFromCanvas: vi.fn(),
    clearCanvas: vi.fn(),
    undoLastAction: vi.fn(),
    addAllDressedToCart: vi.fn(),
    runTryOn: mocks.runTryOn,
    runAnimatedTryOn: mocks.runAnimatedTryOn,
  }),
}));

const PRODUCT = {
  id: 1,
  title: 'Tailored Test Shirt',
  slug: 'tailored-test-shirt',
  category_name: 'Tops & Shirts',
  brand_name: 'Test Brand',
  base_price: 100,
  thumbnail_url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
  skus: [],
} as any;

beforeEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ tryOnProduct: null, rulerProduct: null, rulerMeasurements: null });
});

afterEach(() => {
  cleanup();
  useUIStore.setState({ tryOnProduct: null, rulerProduct: null, rulerMeasurements: null });
});

describe('VirtualTryOnModal hook-order regression', () => {
  it('can transition from globally mounted/closed to open without React invariant #310', async () => {
    render(
      <MemoryRouter>
        <VirtualTryOnModal />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('dialog', { name: /virtual try-on studio/i })).toBeNull();

    act(() => useUIStore.getState().openTryOn(PRODUCT));

    expect(await screen.findByRole('dialog', { name: /virtual try-on studio/i })).toBeVisible();
    expect(screen.getByText(/dynamic virtual dressing studio/i)).toBeVisible();
  });

  it('closes and can open again without changing its hook count', async () => {
    render(
      <MemoryRouter>
        <VirtualTryOnModal />
      </MemoryRouter>,
    );

    act(() => useUIStore.getState().openTryOn(PRODUCT));
    await screen.findByRole('dialog', { name: /virtual try-on studio/i });
    fireEvent.click(screen.getByRole('button', { name: '✕' }));
    expect(screen.queryByRole('dialog', { name: /virtual try-on studio/i })).toBeNull();

    act(() => useUIStore.getState().openTryOn(PRODUCT));
    expect(await screen.findByRole('dialog', { name: /virtual try-on studio/i })).toBeVisible();
  });
});
