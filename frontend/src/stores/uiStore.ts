import { create } from "zustand";
import { Product } from "../models";
import i18n, { isSupportedLanguage, setAppLanguage, type AppLanguage } from "../i18n/i18n";
import type { TranslatableMessage } from "../i18n/messages";

type StylistPrefill =
  | {
      prompt: string;
      occasion?: string;
      budget?: number;
      recommendation_constraints?: {
        palette?: string;
        avoid_palette?: string;
        preferred_fit?: string;
        size_tops?: string;
        size_bottoms?: string;
        size_shoes?: string;
      };
    }
  | string;

interface UIState {
  // Modal states
  tryOnProduct: Product | null;
  rulerProduct: Product | null;
  isVisualSearchOpen: boolean;
  isStylistDrawerOpen: boolean;
  stylistPrefillOccasion: StylistPrefill | null;
  isAuthModalOpen: boolean;
  authModalMode: "login" | "register";

  // Toast
  toast: {
    // TranslatableMessage, not string: a store has no t(), so it must emit a
    // key + params and let the Toast component resolve it in the ACTIVE
    // language. Previously every toast was a concatenated English sentence,
    // so Arabic users read English failure messages.
    message: TranslatableMessage;
    type: "success" | "error" | "info";
    id: string;
  } | null;

  // Language — MIRROR of the i18next instance, never a second source of
  // truth. Kept in the store only so components can subscribe reactively;
  // it is written exclusively by the i18n 'languageChanged' listener below.
  language: AppLanguage;

  // Actions
  openTryOn: (product: Product) => void;
  closeTryOn: () => void;
  openRuler: (product: Product) => void;
  closeRuler: () => void;
  openVisualSearch: () => void;
  closeVisualSearch: () => void;
  openStylist: (prefill?: StylistPrefill) => void;
  closeStylist: () => void;
  openAuthModal: (mode?: "login" | "register") => void;
  closeAuthModal: () => void;
  showToast: (message: TranslatableMessage, type?: "success" | "error" | "info") => void;
  hideToast: () => void;
  setLanguage: (lang: AppLanguage) => void;
}

let toastTimer: ReturnType<typeof setTimeout> | null = null;
let lastToastKey = "";
let lastToastTime = 0;

/** Stable identity for a TranslatableMessage, used to debounce duplicates. */
const toastIdentity = (message: TranslatableMessage): string =>
  typeof message === "string"
    ? message
    : `${message.key}|${JSON.stringify(message.params ?? {})}`;

export const useUIStore = create<UIState>((set) => ({
  tryOnProduct: null,
  rulerProduct: null,
  isVisualSearchOpen: false,
  isStylistDrawerOpen: false,
  stylistPrefillOccasion: null,
  isAuthModalOpen: false,
  authModalMode: "login",
  toast: null,
  language: (i18n.resolvedLanguage as AppLanguage) ?? "en",

  openTryOn: (product) => set({ tryOnProduct: product }),
  closeTryOn: () => set({ tryOnProduct: null }),

  openRuler: (product) => set({ rulerProduct: product }),
  closeRuler: () => set({ rulerProduct: null }),

  openVisualSearch: () => set({ isVisualSearchOpen: true }),
  closeVisualSearch: () => set({ isVisualSearchOpen: false }),

  openStylist: (prefill) =>
    set({ isStylistDrawerOpen: true, stylistPrefillOccasion: prefill || null }),
  closeStylist: () =>
    set({ isStylistDrawerOpen: false, stylistPrefillOccasion: null }),

  openAuthModal: (mode = "login") =>
    set({ isAuthModalOpen: true, authModalMode: mode }),
  closeAuthModal: () => set({ isAuthModalOpen: false }),

  showToast: (message, type = "info") => {
    const now = Date.now();
    // Debounce duplicate messages within 1.5 seconds. Identity is the
    // key+params pair, so the same key with different values still shows.
    const identity = toastIdentity(message);
    if (identity === lastToastKey && now - lastToastTime < 1500) {
      return;
    }
    lastToastKey = identity;
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
    // Fire-and-forget is safe: i18next applies the bundle synchronously from
    // in-memory resources, and the 'languageChanged' listener (registered
    // below) is what writes `language` back into this store. Calling set()
    // here as well would re-create the duplicated-state bug this replaced.
    if (!isSupportedLanguage(lang)) return;
    void setAppLanguage(lang);
  },
}));

/**
 * Single-source-of-truth wiring: the store mirrors i18next, never the
 * reverse. Any language change — from the switcher, from a deep link, from a
 * test, or from a future locale detector — reaches the UI through this one
 * path, so `dir`, `<html lang>`, the Arabic font class and the store value
 * can never disagree.
 */
i18n.on("languageChanged", (lang) => {
  if (!isSupportedLanguage(lang)) return;
  const current = useUIStore.getState().language;
  if (current !== lang) {
    useUIStore.setState({ language: lang });
  }
});
