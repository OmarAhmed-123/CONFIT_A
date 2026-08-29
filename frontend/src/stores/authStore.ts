import { create } from 'zustand';
import { User } from '../models';
import { authService } from '../services/apiServices';
import { setAuthTokens, clearAuthTokens, getAuthToken } from '../services/apiClient';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: any) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.login(email, password);
      setAuthTokens(res.access_token, res.refresh_token);
      localStorage.setItem('confit_user', JSON.stringify(res.user));
      set({ user: res.user, isAuthenticated: true, isLoading: false, error: null });
    } catch (err: any) {
      // Honest failure — no fabricated session. (The old code minted a
      // client-side 'admin' for any email containing "admin" on ANY error,
      // including a wrong password: a real auth bypass.)
      clearAuthTokens();
      set({ user: null, isAuthenticated: false, isLoading: false, error: err?.message || 'Login failed' });
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
      clearAuthTokens();
      set({ user: null, isAuthenticated: false, isLoading: false, error: err?.message || 'Registration failed' });
      throw err;
    }
  },

  logout: () => {
    authService.logout().catch(() => {}); // clears the httpOnly cookie server-side
    clearAuthTokens();
    set({ user: null, isAuthenticated: false });
  },

  fetchMe: async () => {
    // The session cookie is httpOnly — JS cannot see it, so just ask the
    // backend; a live cookie yields the user, an absent/expired one 401s.
    try {
      const user = await authService.getMe();
      localStorage.setItem('confit_user', JSON.stringify(user));
      set({ user, isAuthenticated: true });
    } catch (err) {
      clearAuthTokens();
      set({ user: null, isAuthenticated: false });
    }
  },
}));
