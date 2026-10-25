import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '../../../i18n/i18n';
import { useUIStore } from '../../../stores/uiStore';
import { VirtualTryOnModal } from '../VirtualTryOnModal';

/**
 * A refused upload has to be actionable, in the customer's language.
 *
 * The worker refuses a non-full-body photo with VTON_PERSON_FRAMING_INVALID and
 * writes an English, operator-grade message. Showing only that English string to
 * an Arabic shopper is how a correct backend decision still reads as a dead end,
 * so the UI pairs the code with the localised framing guidance it already ships
 * (tryon.person_framing_hint) — the same hint that sits under the uploader.
 */

const state = vi.hoisted(() => ({
  tryOnStatus: 'idle' as string,
  errorMessage: null as string | null,
}));

vi.mock('../../../privacy/usePhotoConsent', () => ({
  usePhotoConsent: () => ({ requestConsent: vi.fn(), consentDialog: null }),
}));

vi.mock('../../../viewmodels/useCatalogViewModel', () => ({
  useCatalogViewModel: () => ({ products: [] }),
}));

vi.mock('../../../viewmodels/useTryOnViewModel', () => ({
  useTryOnViewModel: () => ({
    tryOnStatus: state.tryOnStatus,
    errorMessage: state.errorMessage,
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
  title: 'Tailored Test Shirt',
  slug: 'tailored-test-shirt',
  category_name: 'Tops & Shirts',
  brand_name: 'Test Brand',
  base_price: 100,
  thumbnail_url: 'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
  skus: [],
} as any;

const FRAMING_MESSAGE =
  'VTON_PERSON_FRAMING_INVALID: this photo does not show the whole body. ' +
  'A try-on needs a full-length photo — head to feet, standing, arms slightly ' +
  'away from your body. Please upload a full-body photo.';

beforeEach(async () => {
  await i18n.changeLanguage('en');
  state.tryOnStatus = 'idle';
  state.errorMessage = null;
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

describe('a refused non-full-body upload', () => {
  it('shows the guided framing hint in English', async () => {
    state.tryOnStatus = 'failed';
    state.errorMessage = FRAMING_MESSAGE;
    open();

    const notice = await screen.findByTestId('tryon-framing-refusal');
    expect(notice).toBeVisible();
    expect(notice.textContent).toMatch(/full-body photo/i);
  });

  it('shows the guided framing hint in Arabic, not just the English worker text', async () => {
    await i18n.changeLanguage('ar');
    state.tryOnStatus = 'failed';
    state.errorMessage = FRAMING_MESSAGE;
    open();

    const notice = await screen.findByTestId('tryon-framing-refusal');
    // The Arabic hint ships in ar.json; a raw English worker string here would
    // leave an Arabic shopper with an unactionable error.
    expect(notice.textContent).toMatch(/صورة كاملة الجسم/);
    expect(notice.textContent).not.toMatch(/this photo does not show the whole body/i);
  });

  it('does not show the framing notice for an unrelated failure', async () => {
    state.tryOnStatus = 'failed';
    state.errorMessage = 'GPU_WORKER_ERROR: worker unreachable';
    open();

    await screen.findByRole('dialog', { name: /virtual try-on studio/i });
    expect(screen.queryByTestId('tryon-framing-refusal')).toBeNull();
  });
});
