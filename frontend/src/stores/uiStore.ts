import { create } from 'zustand';
import { Product } from '../models';
import { setAppLanguage } from '../i18n/i18n';

interface UIState {
  // Modal states
  tryOnProduct: Product | null;
  rulerProduct: Product | null;
  isVisualSearchOpen: boolean;
  isStylistDrawerOpen: boolean;
  stylistPrefillOccasion: string | null;
  isAuthModalOpen: boolean;
  authModalMode: 'login' | 'register';

  // Toast
  toast: { message: string; type: 'success' | 'error' | 'info'; id: string } | null;

  // Language
  language: 'en' | 'ar';

  // Actions
  openTryOn: (product: Product) => void;
  closeTryOn: () => void;
  openRuler: (product: Product) => void;
  closeRuler: () => void;
  openVisualSearch: () => void;
  closeVisualSearch: () => void;
  openStylist: (occasion?: string) => void;
  closeStylist: () => void;
  openAuthModal: (mode?: 'login' | 'register') => void;
  closeAuthModal: () => void;
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  hideToast: () => void;
  setLanguage: (lang: 'en' | 'ar') => void;
}

let toastTimer: any = null;
let lastToastMessage = '';
let lastToastTime = 0;

export const useUIStore = create<UIState>((set) => ({
  tryOnProduct: null,
  rulerProduct: null,
  isVisualSearchOpen: false,
  isStylistDrawerOpen: false,
  stylistPrefillOccasion: null,
  isAuthModalOpen: false,
  authModalMode: 'login',
  toast: null,
  language: (localStorage.getItem('confit_lang') as 'en' | 'ar') || 'en',

  openTryOn: (product) => set({ tryOnProduct: product }),
  closeTryOn: () => set({ tryOnProduct: null }),

  openRuler: (product) => set({ rulerProduct: product }),
  closeRuler: () => set({ rulerProduct: null }),

  openVisualSearch: () => set({ isVisualSearchOpen: true }),
  closeVisualSearch: () => set({ isVisualSearchOpen: false }),

  openStylist: (occasion) => set({ isStylistDrawerOpen: true, stylistPrefillOccasion: occasion || null }),
  closeStylist: () => set({ isStylistDrawerOpen: false, stylistPrefillOccasion: null }),

  openAuthModal: (mode = 'login') => set({ isAuthModalOpen: true, authModalMode: mode }),
  closeAuthModal: () => set({ isAuthModalOpen: false }),

  showToast: (message, type = 'info') => {
    const now = Date.now();
    // Debounce duplicate messages within 1.5 seconds
    if (message === lastToastMessage && now - lastToastTime < 1500) {
      return;
    }
    lastToastMessage = message;
    lastToastTime = now;

    if (toastTimer) clearTimeout(toastTimer);

    const toastId = `toast_${now}_${Math.random().toString(36).substring(2, 7)}`;
    set({ toast: { message, type, id: toastId } });

    toastTimer = setTimeout(() => {
      set({ toast: null });
      toastTimer = null;
    }, 4000);
  },

  hideToast: () => {
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = null;
    set({ toast: null });
  },

  setLanguage: (lang) => {
    setAppLanguage(lang);
    set({ language: lang });
  },
}));
