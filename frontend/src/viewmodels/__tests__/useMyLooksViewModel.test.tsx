import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * OUTFIT-03/04 — My Looks + share-link management.
 *
 * These assert the behaviours the audit called out as unproven or missing:
 *  - saved looks are actually listed (the route used to render the wardrobe);
 *  - a look is shown as "shared" ONLY when the server reports a live token;
 *  - revoke really calls the revoke endpoint and clears the link from state,
 *    so the UI cannot keep advertising a dead link;
 *  - a failed revoke does NOT optimistically pretend the link is gone.
 */

const getSavedOutfitsMock = vi.fn();
const shareOutfitMock = vi.fn();
const revokeShareMock = vi.fn();
const getShareStateMock = vi.fn();
const deleteOutfitMock = vi.fn();
const updateOutfitMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../../services/apiServices', () => ({
  stylistService: {
    getSavedOutfits: (...a: unknown[]) => getSavedOutfitsMock(...a),
    shareOutfit: (...a: unknown[]) => shareOutfitMock(...a),
    revokeShare: (...a: unknown[]) => revokeShareMock(...a),
    getShareState: (...a: unknown[]) => getShareStateMock(...a),
    deleteOutfit: (...a: unknown[]) => deleteOutfitMock(...a),
    updateOutfit: (...a: unknown[]) => updateOutfitMock(...a),
  },
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: showToastMock }),
}));

import { renderHook, act, waitFor } from '@testing-library/react';
import { useMyLooksViewModel } from '../useMyLooksViewModel';

const look = (over: Record<string, unknown> = {}) => ({
  id: 1,
  title: 'Boardroom',
  occasion: 'Work',
  total_price: 900,
  compatibility_score: 88,
  color_palette: [],
  style_tags: [],
  is_saved: true,
  is_system_curated: false,
  items: [],
  created_at: '2026-09-01T00:00:00Z',
  is_shared: false,
  share_url: null,
  share_expires_at: null,
  share_view_count: 0,
  ...over,
});

describe('MY LOOKS: saved outfits and share-link lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSavedOutfitsMock.mockResolvedValue([look()]);
  });

  it('lists the saved looks returned by the real endpoint', async () => {
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    expect(result.current.looks).toHaveLength(1);
    expect(result.current.looks[0].title).toBe('Boardroom');
  });

  it('surfaces a load failure instead of showing an empty collection', async () => {
    getSavedOutfitsMock.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('error'));
    // An empty list would falsely imply "you have no looks".
    expect(result.current.looks).toHaveLength(0);
    expect(result.current.error).toContain('network down');
  });

  it('shows no share link until the server confirms a live one', async () => {
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    expect(result.current.shareLinks[1]).toBeUndefined();
  });

  it('seeds an active link from the list payload without an extra request', async () => {
    getSavedOutfitsMock.mockResolvedValue([
      look({
        is_shared: true,
        share_url: '/looks/look_abc123',
        share_expires_at: '2026-10-21T00:00:00Z',
        share_view_count: 4,
      }),
    ]);
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    expect(result.current.shareLinks[1].is_active).toBe(true);
    expect(result.current.shareLinks[1].view_count).toBe(4);
    expect(getShareStateMock).not.toHaveBeenCalled();
  });

  it('creating a link stores the REAL server response, not an assumption', async () => {
    shareOutfitMock.mockResolvedValue({
      outfit_id: 1,
      share_token: 'look_xyz',
      share_url: '/looks/look_xyz',
      expires_at: '2026-10-21T00:00:00Z',
      is_active: true,
      view_count: 0,
    });
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    await act(async () => {
      await result.current.share(1);
    });
    expect(shareOutfitMock).toHaveBeenCalledWith(1, undefined);
    expect(result.current.shareLinks[1].share_url).toBe('/looks/look_xyz');
    expect(result.current.looks[0].is_shared).toBe(true);
  });

  it('revoking calls the endpoint and stops advertising the link', async () => {
    getSavedOutfitsMock.mockResolvedValue([
      look({ is_shared: true, share_url: '/looks/look_abc123' }),
    ]);
    revokeShareMock.mockResolvedValue({
      outfit_id: 1,
      revoked: true,
      was_active: true,
      is_active: false,
    });
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    await act(async () => {
      await result.current.revoke(1);
    });
    expect(revokeShareMock).toHaveBeenCalledWith(1);
    expect(result.current.shareLinks[1]).toBeUndefined();
    expect(result.current.looks[0].is_shared).toBe(false);
    expect(result.current.looks[0].share_url).toBeNull();
  });

  it('a FAILED revoke never pretends the link was removed', async () => {
    getSavedOutfitsMock.mockResolvedValue([
      look({ is_shared: true, share_url: '/looks/look_abc123' }),
    ]);
    revokeShareMock.mockRejectedValue(new Error('server error'));
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    await act(async () => {
      await result.current.revoke(1);
    });
    // The link is still advertised, because it is still live on the server.
    expect(result.current.shareLinks[1]?.is_active).toBe(true);
    expect(result.current.looks[0].is_shared).toBe(true);
    expect(showToastMock).toHaveBeenCalledWith(
      expect.stringContaining('Could not revoke'),
      'error',
    );
  });

  it('rotating requests a new link and replaces the old one', async () => {
    shareOutfitMock.mockResolvedValue({
      outfit_id: 1,
      share_token: 'look_new',
      share_url: '/looks/look_new',
      expires_at: null,
      is_active: true,
      view_count: 0,
    });
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    await act(async () => {
      await result.current.share(1, { rotate: true });
    });
    expect(shareOutfitMock).toHaveBeenCalledWith(1, { rotate: true });
    expect(result.current.shareLinks[1].share_url).toBe('/looks/look_new');
  });

  it('deleting removes the look only after the server confirms', async () => {
    deleteOutfitMock.mockRejectedValueOnce(new Error('nope'));
    const { result } = renderHook(() => useMyLooksViewModel());
    await waitFor(() => expect(result.current.state).toBe('ready'));
    await act(async () => {
      await result.current.remove(1);
    });
    expect(result.current.looks).toHaveLength(1); // failure => nothing removed

    deleteOutfitMock.mockResolvedValueOnce({ status: 'success' });
    await act(async () => {
      await result.current.remove(1);
    });
    expect(result.current.looks).toHaveLength(0);
  });
});
