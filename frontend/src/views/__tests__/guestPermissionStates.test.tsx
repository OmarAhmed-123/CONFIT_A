import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * UI/UX audit 2026-10-17 — permission-denied states for signed-out visitors.
 *
 * Before: a guest on /outfits fired GET /outfits (a guaranteed 401), then saw
 * the generic error state with a "Try again" button that could never succeed.
 * Fixed: no request is made without a session, and the page renders a
 * permission state whose only action is signing in.
 */

const getSavedOutfitsMock = vi.fn();
const openAuthModalMock = vi.fn();
const authState = { isAuthenticated: false, user: null as null | { id: number } };

vi.mock('../../services/apiServices', () => ({
  stylistService: {
    getSavedOutfits: (...a: unknown[]) => getSavedOutfitsMock(...a),
    shareOutfit: vi.fn(),
    revokeShare: vi.fn(),
    getShareState: vi.fn(),
    deleteOutfit: vi.fn(),
    updateOutfit: vi.fn(),
  },
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: vi.fn(), openAuthModal: openAuthModalMock }),
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: () => authState,
}));

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import i18n from '../../i18n/i18n';
import { MyLooksView } from '../consumer/MyLooksView';

const renderView = () =>
  render(
    <MemoryRouter>
      <MyLooksView />
    </MemoryRouter>,
  );

describe('MyLooksView — guest permission state', () => {
  beforeEach(() => {
    getSavedOutfitsMock.mockReset();
    openAuthModalMock.mockReset();
    authState.isAuthenticated = false;
    authState.user = null;
  });

  it('never requests saved looks without a session', async () => {
    renderView();
    // Give any effect a chance to run before asserting the absence of a call.
    await waitFor(() => expect(screen.getByText(i18n.t('my_looks.signin_title'))).toBeInTheDocument());
    expect(getSavedOutfitsMock).not.toHaveBeenCalled();
  });

  it('offers sign-in, not a retry that cannot succeed', () => {
    renderView();
    expect(screen.queryByText(i18n.t('my_looks.try_again'))).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.sign_in') }));
    expect(openAuthModalMock).toHaveBeenCalledWith('login');
  });

  it('a signed-in shopper still loads their looks', async () => {
    authState.isAuthenticated = true;
    authState.user = { id: 1 };
    getSavedOutfitsMock.mockResolvedValue([]);
    renderView();
    await waitFor(() => expect(getSavedOutfitsMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(i18n.t('my_looks.empty_title'))).toBeInTheDocument();
  });
});
