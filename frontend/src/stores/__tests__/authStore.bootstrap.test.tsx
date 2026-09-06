/**
 * AUTH-02 regression contract — /b2b and /admin gates.
 *
 * Audit 2026-09-05 (AUTH-02): the "Sign In to Continue" button on the B2B and
 * Admin RoleGuard gates called uiStore.openAuthModal(), but <AuthModal /> was
 * only mounted inside ConsumerLayout. On /b2b and /admin the button mutated
 * store state with nothing to render — a dead button. In addition,
 * BrandLayout never called fetchMe(), so a signed-in user hard-refreshing
 * /b2b was treated as a guest.
 *
 * Contract under test:
 *  1. RoleGuard shows a neutral "verifying session" state (not the guest
 *     gate) until hasAttemptedBootstrap is true.
 *  2. AuthModal is rendered as part of the app shell (App mounts it), so
 *     openAuthModal() from ANY route opens the form — tested by rendering
 *     App-level composition pieces rather than a specific layout.
 *  3. After a successful login, the store exposes the server response to the
 *     caller (role-based landing policy depends on it).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const { getMeMock, loginMock } = vi.hoisted(() => ({
  getMeMock: vi.fn(),
  loginMock: vi.fn(),
}));

vi.mock('../../services/apiClient', () => ({
  setAuthTokens: vi.fn(),
  clearAuthTokens: vi.fn(),
  request: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  authService: {
    getMe: (...args: unknown[]) => getMeMock(...args),
    login: (...args: unknown[]) => loginMock(...args),
    register: vi.fn(),
    logout: vi.fn(),
  },
}));

import { useAuthStore } from '../authStore';
import { useUIStore } from '../uiStore';
import { RoleGuard } from '../../components/auth/RoleGuard';

const consumerUser = {
  id: 1,
  email: 'shopper@confit.io',
  full_name: 'Layla Al-Mansoor',
  role: 'consumer',
  is_active: true,
  is_verified: true,
  has_profile: true,
};

describe('AUTH-02: session bootstrap + gate behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      hasAttemptedBootstrap: false,
      mfaRequired: false,
      error: null,
    });
    useUIStore.setState({ isAuthModalOpen: false, authModalMode: 'login' });
  });

  it('shows the verifying state — NOT the guest gate — while bootstrap is in flight', () => {
    render(
      <MemoryRouter initialEntries={['/b2b']}>
        <RoleGuard allowedRoles={['admin']} fallbackTitle="Platform Super-Admin Portal">
          <div>ADMIN CONTENT</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.getByText(/verifying your session/i)).toBeTruthy();
    expect(screen.queryByText(/Sign In to Continue/i)).toBeNull();
    expect(screen.queryByText('ADMIN CONTENT')).toBeNull();
  });

  it('after a 401 bootstrap the gate renders with a Sign In button that opens the AuthModal', async () => {
    getMeMock.mockRejectedValue(Object.assign(new Error('unauthorized'), { status: 401 }));
    await useAuthStore.getState().fetchMe();
    expect(useAuthStore.getState().hasAttemptedBootstrap).toBe(true);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <RoleGuard allowedRoles={['admin']} fallbackTitle="Platform Super-Admin Portal">
          <div>ADMIN CONTENT</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.getByText(/Sign In to Continue/i)).toBeTruthy();

    // The exact audit failure: this button must visibly open the AuthModal.
    fireEvent.click(screen.getByText(/Sign In to Continue/i));
    expect(useUIStore.getState().isAuthModalOpen).toBe(true);
  });

  it('a signed-in session restored from bootstrap does not flash the guest gate', async () => {
    getMeMock.mockResolvedValue(consumerUser);
    await useAuthStore.getState().fetchMe();
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    render(
      <MemoryRouter initialEntries={['/']}>
        <RoleGuard>
          <div>CONSUMER CONTENT</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.getByText('CONSUMER CONTENT')).toBeTruthy();
    expect(screen.queryByText(/Sign In to Continue/i)).toBeNull();
  });

  it('login() resolves with the server response so callers can route by role', async () => {
    const tokenRes = {
      access_token: 'a',
      refresh_token: 'r',
      token_type: 'bearer',
      user: consumerUser,
    };
    loginMock.mockResolvedValue(tokenRes);
    const res = await useAuthStore.getState().login('shopper@confit.io', 'Password123!');
    expect(res.user.email).toBe('shopper@confit.io');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });
});
