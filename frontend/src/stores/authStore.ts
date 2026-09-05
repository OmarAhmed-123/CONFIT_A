import { create } from 'zustand';
import { User } from '../models';
import { authService } from '../services/apiServices';
import { setAuthTokens, clearAuthTokens } from '../services/apiClient';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  // Group 1 §11: two-step login. When a normal login response signals
  // MFA_REQUIRED, we flip this flag; the AuthModal renders the challenge
  // form and calls completeMfaLogin to finish.
  mfaRequired: boolean;
  login: (email: string, password: string) => Promise<void>;
  completeMfaLogin: (email: string, password: string, mfaCode: string) => Promise<void>;
  register: (payload: any) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
  resetError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  mfaRequired: false,

  resetError: () => set({ error: null }),

  login: async (email, password) => {
    set({ isLoading: true, error: null, mfaRequired: false });
    try {
      const res = await authService.login(email, password);
      setAuthTokens(res.access_token, res.refresh_token);
      localStorage.setItem('confit_user', JSON.stringify(res.user));
      set({ user: res.user, isAuthenticated: true, isLoading: false, error: null, mfaRequired: false });
    } catch (err: any) {
      // Server signals MFA_REQUIRED via ApiError.details.reason. That is
      // NOT an authentication failure — it's a pending state we resume
      // via completeMfaLogin. Keep the user logged-out until they verify.
      if (err?.details?.reason === 'MFA_REQUIRED') {
        set({ isLoading: false, mfaRequired: true, error: null });
        throw err;
      }
      // A failed login attempt does not invalidate any pre-existing
      // session: the server leaves the current confit_token cookie
      // untouched on login failure. Clearing local tokens here would
      // destroy a valid session's CSRF cookie and break its mutating
      // requests — so we only surface the error.
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        mfaRequired: false,
        error: err?.message || 'Login failed',
      });
      throw err;
    }
  },

  completeMfaLogin: async (email, password, mfaCode) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.login(email, password, mfaCode);
      setAuthTokens(res.access_token, res.refresh_token);
      localStorage.setItem('confit_user', JSON.stringify(res.user));
      set({ user: res.user, isAuthenticated: true, isLoading: false, error: null, mfaRequired: false });
    } catch (err: any) {
      set({
        isLoading: false,
        error: err?.message || 'MFA verification failed',
      });
      throw err;
    }
  },

  register: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.register(payload);
      setAuthTokens(res.access_token, res.refresh_token);
      localStorage.setItem('confit_user', JSON.stringify(res.user));
      set({ user: res.user, isAuthenticated: true, isLoading: false, error: null });
    } catch (err: any) {
      // Registration failure (taken email, rate limit, transient 5xx)
      // sets no session cookies server-side, and it must not destroy a
      // pre-existing valid session — see the note in `login`.
      set({ user: null, isAuthenticated: false, isLoading: false, error: err?.message || 'Registration failed' });
      throw err;
    }
  },

  logout: async () => {
    // Server-side revocation happens via /auth/logout; the response
    // clears the httpOnly cookie. Do NOT clear local state before the
    // network call — otherwise the CSRF header cannot be attached.
    try {
      await authService.logout();
    } catch {
      /* still fall through to local clear */
    }
    clearAuthTokens();
    set({ user: null, isAuthenticated: false, mfaRequired: false, error: null });
  },

  fetchMe: async () => {
    const attempt = async () => {
      const user = await authService.getMe();
      localStorage.setItem('confit_user', JSON.stringify(user));
      set({ user, isAuthenticated: true });
    };
    try {
      await attempt();
    } catch (err) {
      // Only an explicit 401 means "the server says this session is dead".
      // Transient failures (network hiccup, serverless cold-start 5xx,
      // timeouts) must NOT destroy the session: the httpOnly confit_token
      // cookie is still valid, and clearing the readable confit_csrf cookie
      // here would break every subsequent mutating request with
      // CSRF_TOKEN_MISMATCH while the session itself lived on.
      if (err?.status === 401) {
        clearAuthTokens();
        set({ user: null, isAuthenticated: false });
        return;
      }
      // One bounded retry: cold starts typically clear on the next attempt.
      try {
        await new Promise((r) => setTimeout(r, 750));
        await attempt();
      } catch {
        // Still failing: keep the session state intact — the cookie remains
        // authoritative and the next bootstrap re-verifies.
      }
    }
  },
}));

// Small helper exposed for callers that need to know if the current
// authenticated user has completed onboarding — used by AppRoutes to
// gate the first-run onboarding redirect (G1 §23).
export const selectHasProfile = (state: AuthState) => Boolean(state.user?.has_profile);
