/**
 * Stale-closure regression: photo upload / avatar pick must render with the
 * FRESH values.
 *
 * Root cause (2026-09-05, found via real browser E2E): the modal's
 * handlePhotoUpload called `setUploadedUserImage(dataUrl)` and then
 * `runTryOn()` in the same tick. React state setters are async, so the
 * closure captured by triggerMultiRender still held the PREVIOUS
 * `uploadedUserImage` (null) — the render request went out WITHOUT the
 * photo the user had just uploaded, and the production result was a
 * byte-identical avatar render instead of the user's person.
 * Live evidence: two multi-render calls (avatar run, then photo run)
 * returned identical 817,506-char data URLs.
 *
 * The fix adds an explicit `overrides` parameter; these tests pin the
 * contract: when the modal passes fresh values, the request MUST carry
 * them even though the hook's committed state is still the old one.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  multiRenderTryOn: vi.fn(),
  showToast: vi.fn(),
  addItem: vi.fn(),
  openCart: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  tryOnService: { multiRenderTryOn: mocks.multiRenderTryOn },
}));
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: mocks.showToast }),
}));
vi.mock('../../stores/cartStore', () => ({
  useCartStore: () => ({ addItem: mocks.addItem, openCart: mocks.openCart }),
}));

import { useTryOnViewModel } from '../useTryOnViewModel';

const PRODUCT = {
  id: 3,
  title: 'Relaxed Organic Poplin Oxford Shirt',
  category_name: 'Tops & Shirts',
  base_price: 95,
  thumbnail_url: 'https://img.example/3.jpg',
} as any;

const OK_RESPONSE = {
  session_id: 1,
  status: 'completed',
  user_reference_image: 'ref',
  rendered_result_url: 'data:image/png;base64,QUJD',
  applied_items: [],
  total_price: 95,
  fit_confidence_score: 95,
  body_fit_verdict: 'Optimal',
  recommended_sizes: {},
  ai_disclosure: 'test',
  traceability_hash: 'T',
  layering_order: ['upper_inner'],
};

function payloadOf(callIndex: number) {
  return mocks.multiRenderTryOn.mock.calls[callIndex][0];
}

describe('same-tick render after state change (stale-closure regression)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.multiRenderTryOn.mockResolvedValue(OK_RESPONSE);
  });

  it('photo upload renders with the FRESH photo even when state is still null', async () => {
    const { result } = renderHook(() => useTryOnViewModel(PRODUCT));

    // initial auto-render (avatar, no photo yet)
    await waitFor(() => expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(1));
    expect(payloadOf(0)).toMatchObject({ user_image_url: undefined });

    // The modal's upload handler, tick-for-tick: setState, then render.
    // Inside this act, the hook's COMMITTED state is still null — exactly
    // the stale-closure window the bug lived in.
    await act(async () => {
      result.current.setUploadedUserImage('data:image/jpeg;base64,WHATEVER_WAS_BEFORE');
      result.current.runTryOn({ userImageUrl: 'data:image/jpeg;base64,JUST_UPLOADED' });
    });
    await waitFor(() => expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(2));

    // Under the old code this assertion FAILS: the request carried
    // user_image_url: undefined (the stale closure) and the render used
    // the avatar instead of the user's photo.
    expect(payloadOf(1)).toMatchObject({
      user_image_url: 'data:image/jpeg;base64,JUST_UPLOADED',
    });
  });

  it('avatar pick renders with the NEW avatar and a CLEARED photo in the same tick', async () => {
    const { result } = renderHook(() => useTryOnViewModel(PRODUCT));
    await waitFor(() => expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(1));

    // user had previously uploaded a photo (committed state)
    await act(async () => {
      result.current.setUploadedUserImage('data:image/jpeg;base64,OLDPHOTO');
    });

    // user clicks a different avatar: the modal clears the photo and
    // re-renders with the new avatar in the same tick.
    await act(async () => {
      result.current.setSelectedAvatar('avatar_slim_f');
      result.current.setUploadedUserImage(null);
      result.current.runTryOn({ userImageUrl: null, avatarId: 'avatar_slim_f' });
    });
    await waitFor(() => expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(2));

    expect(payloadOf(1)).toMatchObject({
      user_image_url: undefined, // photo cleared — avatar is the reference
      avatar_model_id: 'avatar_slim_f', // the NEW avatar, not the stale one
    });
  });

  it('no-override render still uses committed state (camera-scan path unaffected)', async () => {
    const { result } = renderHook(() => useTryOnViewModel(PRODUCT));
    await waitFor(() => expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(1));

    await act(async () => {
      result.current.setUploadedUserImage('data:image/jpeg;base64,COMMITTED');
    });
    expect(result.current.uploadedUserImage).toBe('data:image/jpeg;base64,COMMITTED');

    // camera-scan apply: no state change in this tick → plain runTryOn()
    await act(async () => {
      result.current.runTryOn();
    });
    await waitFor(() => expect(mocks.multiRenderTryOn).toHaveBeenCalledTimes(2));
    expect(payloadOf(1)).toMatchObject({
      user_image_url: 'data:image/jpeg;base64,COMMITTED',
      avatar_model_id: 'avatar_athletic_m',
    });
  });
});
