/**
 * Presentation currency — the client half of the backend's single money
 * authority (`backend/app/services/pricing_presentation.py`).
 *
 * DESIGN RULE: the browser NEVER converts money. It sends the chosen currency
 * code and renders whatever amounts and `currency` label the API returns. Two
 * FX implementations — one in Python, one in TypeScript — is how a storefront
 * ends up showing a price the checkout disagrees with, and the backend already
 * owns the rate table that settlement uses.
 *
 * So this module holds exactly three responsibilities:
 *   1. remember the shopper's choice across reloads,
 *   2. put it on every request as `X-Currency` (read by
 *      `get_presentation_currency` in backend/app/core/dependencies.py),
 *   3. tell the app when it changed so cached prices are refetched rather
 *      than left stale in the old currency.
 */

const STORAGE_KEY = 'confit_currency';

/** Fired on the window after a successful change. The app listens once and
 *  invalidates the query cache — a price cached in EGP must not survive a
 *  switch to SAR. */
export const CURRENCY_CHANGED_EVENT = 'confit:currency-changed';

export interface CurrencyOption {
  currency: string;
  markets: string[];
  is_pricing_currency: boolean;
  rate_from_pricing_currency: string | null;
  /** False when the platform has no configured rate: the option is shown as
   *  unavailable rather than silently served at 1:1. */
  available: boolean;
}

export interface ActiveCurrency {
  currency: string;
  pricing_currency: string;
  rate_from_pricing_currency: string;
  converted: boolean;
  reason: string;
  requested_currency: string | null;
  /** False when the backend could not honour the request — the UI must say so
   *  instead of pretending the switch worked. */
  honoured: boolean;
}

export interface CurrencyCatalog {
  active: ActiveCurrency;
  supported: CurrencyOption[];
}

/** Display metadata only — never a rate. Rates live server-side. */
export const CURRENCY_LABELS: Record<string, { en: string; ar: string }> = {
  USD: { en: 'US Dollar', ar: 'دولار أمريكي' },
  EGP: { en: 'Egyptian Pound', ar: 'جنيه مصري' },
  SAR: { en: 'Saudi Riyal', ar: 'ريال سعودي' },
  AED: { en: 'UAE Dirham', ar: 'درهم إماراتي' },
  QAR: { en: 'Qatari Riyal', ar: 'ريال قطري' },
  KWD: { en: 'Kuwaiti Dinar', ar: 'دينار كويتي' },
  BHD: { en: 'Bahraini Dinar', ar: 'دينار بحريني' },
  OMR: { en: 'Omani Rial', ar: 'ريال عماني' },
};

function isPlausibleCode(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Z]{3}$/.test(value);
}

/**
 * The stored choice, or `null` for "let the market decide".
 *
 * `null` is meaningful and is NOT the same as defaulting to USD: with no
 * stored choice the backend resolves the market's own currency, which is the
 * right answer for a first-time Egyptian visitor.
 */
export function getPreferredCurrency(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isPlausibleCode(raw) ? raw : null;
  } catch {
    // Private mode / disabled storage must not break the storefront.
    return null;
  }
}

export function setPreferredCurrency(code: string | null): void {
  try {
    if (code === null) localStorage.removeItem(STORAGE_KEY);
    else if (isPlausibleCode(code)) localStorage.setItem(STORAGE_KEY, code);
    else return;
  } catch {
    /* storage unavailable — the in-memory switch below still applies */
  }
  try {
    window.dispatchEvent(new CustomEvent(CURRENCY_CHANGED_EVENT, { detail: { currency: code } }));
  } catch {
    /* non-DOM environment (SSR/tests) */
  }
}

/** Header pair for `apiClient`, empty when the shopper has expressed no
 *  preference so the server-side market default still applies. */
export function currencyHeaders(): Record<string, string> {
  const code = getPreferredCurrency();
  return code ? { 'X-Currency': code } : {};
}
