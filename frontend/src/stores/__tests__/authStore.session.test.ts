/**
 * Session-preservation contract for useAuthStore.
 *
 * Background (production incident, 2026-09-05): the browser session is an
 * httpOnly confit_token cookie plus a readable confit_csrf cookie (double-
 * submit CSRF). clearAuthTokens() can delete only the readable one. The
 * old fetchMe() catch block cleared tokens on ANY error, so a single
 * transient GET /auth/me failure (serverless cold-start 5xx) destroyed the
 * CSRF cookie while the session itself lived on — every subsequent mutating
 * request then failed with 403 CSRF_TOKEN_MISMATCH.
 *
 * Contract under test:
 *   - an explicit 401 (server: session dead)  -> clear tokens
 *   - a transient error (5xx / network)       -> never clear tokens
 *   - a failed login/registration attempt     -> never clear tokens
 *     (the server leaves any pre-existing session cookie untouched on
 *     failed credential checks)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { clearAuthTokensMock, getMeMock, loginMock, registerMock } = vi.hoisted(() => ({
  clearAuthTokensMock: vi.fn(),
  getMeMock: vi.fn(),
  loginMock: vi.fn(),
  registerMock: vi.fn(),
}));

vi.mock('../../services/apiClient', () => ({
  setAuthTokens: vi.fn(),
  clearAuthTokens: (...args: unknown[]) => clearAuthTokensMock(...args),
}));

vi.mock('../../services/apiServices', () => ({
  authService: {
    getMe: (...args: unknown[]) => getMeMock(...args),
    login: (...args: unknown[]) => loginMock(...args),
    register: (...args: unknown[]) => registerMock(...args),
    logout: vi.fn(),
  },
}));

import { useAuthStore } from '../authStore';

class ApiError401 extends Error {
  status = 401;
  constructor() {
    super('unauthorized');
  }
}
class ApiError500 extends Error {
  status = 500;
  constructor() {
    super('internal error');
  }
}

describe('authStore.fetchMe — session preservation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, error: null });
    // OBS-01: fetchMe now skips the network call entirely when no session
    // evidence exists (cached confit_user profile or the confit_csrf cookie).
    // These tests describe the WITH-session paths, so seed evidence first —
    // exactly what a returning real user has.
    localStorage.setItem('confit_user', JSON.stringify({ id: 1, has_profile: true }));
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('sets the user state on success', async () => {
    getMeMock.mockResolvedValue({ id: 1, has_profile: true });
    await useAuthStore.getState().fetchMe();
    expect(getMeMock).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user?.id).toBe(1);
    expect(clearAuthTokensMock).not.toHaveBeenCalled();
  });

  it('clears the session ONLY on an explicit 401', async () => {
    getMeMock.mockRejectedValue(new ApiError401());
    await useAuthStore.getState().fetchMe();
    expect(clearAuthTokensMock).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('recovers via the bounded retry when the first attempt 500s', async () => {
    getMeMock
      .mockRejectedValueOnce(new ApiError500())
      .mockResolvedValueOnce({ id: 2, has_profile: true });
    await useAuthStore.getState().fetchMe();
    expect(getMeMock).toHaveBeenCalledTimes(2);
    expect(clearAuthTokensMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user?.id).toBe(2);
  });

  it('never clears the session when a transient 500 persists', async () => {
    getMeMock.mockRejectedValue(new ApiError500());
    await useAuthStore.getState().fetchMe();
    expect(getMeMock).toHaveBeenCalledTimes(2); // initial + one bounded retry
    // The readable confit_csrf cookie is deleted ONLY by clearAuthTokens;
    // asserting it was never called is the contract that keeps the session
    // usable after a transient bootstrap failure.
    expect(clearAuthTokensMock).not.toHaveBeenCalled();
  });

  it('treats a plain network error (no status) as transient, not auth death', async () => {
    getMeMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await useAuthStore.getState().fetchMe();
    expect(clearAuthTokensMock).not.toHaveBeenCalled();
  });
});

describe('authStore.login/register — failed attempts must not destroy a pre-existing session', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, error: null });
  });

  it('a failed login does not clear the existing session tokens', async () => {
    // A valid session exists (e.g. the user was already logged in).
    useAuthStore.setState({ user: { id: 9 } as never, isAuthenticated: true });
    loginMock.mockRejectedValue(new ApiError401());
    await expect(useAuthStore.getState().login('new@user.io', 'wrong-pw')).rejects.toBeDefined();
    expect(clearAuthTokensMock).not.toHaveBeenCalled();
  });

  it('a failed registration does not clear the existing session tokens', async () => {
    useAuthStore.setState({ user: { id: 9 } as never, isAuthenticated: true });
    registerMock.mockRejectedValue(Object.assign(new Error('email exists'), { status: 409 }));
    await expect(useAuthStore.getState().register({ email: 'a@b.c' })).rejects.toBeDefined();
    expect(clearAuthTokensMock).not.toHaveBeenCalled();
  });
});
