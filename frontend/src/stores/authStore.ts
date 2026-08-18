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
  isAuthenticated: !!getAuthToken(),
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.login(email, password);
      setAuthTokens(res.access_token, res.refresh_token);
      set({ user: res.user, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Login failed', isLoading: false });
      throw err;
    }
  },

  register: async (payload) => {
    set({ isLoading: true, error: null });
    try {
      const res = await authService.register(payload);
      setAuthTokens(res.access_token, res.refresh_token);
      set({ user: res.user, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Registration failed', isLoading: false });
      throw err;
    }
  },

  logout: () => {
    clearAuthTokens();
    set({ user: null, isAuthenticated: false });
  },

  fetchMe: async () => {
    if (!getAuthToken()) return;
    try {
      const user = await authService.getMe();
      set({ user, isAuthenticated: true });
    } catch (err) {
      clearAuthTokens();
      set({ user: null, isAuthenticated: false });
    }
  },
}));
