/**
 * Route → accessible-name mapping for the SPA.
 *
 * WHY THIS EXISTS (audit 2026-09-21: "لم يتحقق الفحص من RTL، focus order،
 * contrast، labels، error announcements، أو عمل كل زر دون mouse"):
 *
 * Two WCAG failures shared one root cause — the app is a single page, and
 * nothing told assistive technology that the page had changed:
 *
 *   · **2.4.2 Page Titled** — `document.title` was set once in index.html and
 *     never updated. Every route, from the privacy policy to a product page,
 *     announced the same title in the browser tab, the window switcher and the
 *     screen-reader page summary.
 *   · **4.1.3 Status Messages / 2.4.3 Focus Order** — a client-side navigation
 *     replaces the whole content region without moving focus or announcing
 *     anything. A keyboard or screen-reader user pressed Enter on a link and
 *     received silence; the next Tab started from wherever focus already was.
 *
 * The tables below are data, not code, so a new route is a one-line addition
 * and a missing one degrades to the app name instead of crashing.
 */

import type { AppLanguage } from '../i18n/i18n';

export interface RouteMeta {
  /** i18n key under `meta.*` resolving to the document title. */
  titleKey: string;
  /**
   * Patterns matched against `location.pathname`, most specific first. Supports
   * a single trailing `:param` segment; dynamic segments are matched by prefix
   * so `/product/silk-blazer` resolves without a route table lookup.
   */
  patterns: string[];
}

/**
 * Ordered most-specific-first: `/fit-finder` must be tested before `/fit`
 * would swallow it by prefix, and `/privacy-policy` before `/privacy`.
 */
export const ROUTE_META: readonly RouteMeta[] = [
  { titleKey: 'meta.privacy_title', patterns: ['/privacy', '/privacy-policy'] },
  { titleKey: 'meta.terms_title', patterns: ['/terms', '/terms-of-service'] },
  { titleKey: 'meta.gdpr_title', patterns: ['/gdpr'] },
  { titleKey: 'meta.profile_title', patterns: ['/profile', '/settings', '/onboarding'] },
  { titleKey: 'meta.orders_title', patterns: ['/orders'] },
  { titleKey: 'meta.checkout_title', patterns: ['/checkout', '/cart'] },
  { titleKey: 'meta.wardrobe_title', patterns: ['/wardrobe', '/my-looks'] },
  { titleKey: 'meta.fit_title', patterns: ['/fit-finder', '/fit'] },
  { titleKey: 'meta.tryon_title', patterns: ['/tryon-studio', '/try-on', '/visual-search'] },
  { titleKey: 'meta.builder_title', patterns: ['/builder', '/outfits'] },
  { titleKey: 'meta.brand_portal_title', patterns: ['/b2b', '/partner', '/admin'] },
  { titleKey: 'meta.discover_title', patterns: ['/discover', '/products', '/product', '/stylist'] },
  { titleKey: 'meta.home_title', patterns: ['/'] },
];

/** Longest-prefix match wins, so `/product/x` beats `/`. */
export function titleKeyForPath(pathname: string): string {
  const clean = pathname.split('?')[0].split('#')[0];
  let best: { key: string; len: number } | null = null;
  for (const route of ROUTE_META) {
    for (const pattern of route.patterns) {
      const matches = pattern === '/' ? clean === '/' || clean === '' : clean === pattern || clean.startsWith(`${pattern}/`);
      if (matches && (!best || pattern.length > best.len)) {
        best = { key: route.titleKey, len: pattern.length };
      }
    }
  }
  return best?.key ?? 'meta.home_title';
}

/**
 * Compose a document title: "<page> · CONFIT". The brand suffix keeps the tab
 * identifiable when many tabs are open, and `document.title` is what a screen
 * reader announces first on load.
 */
export function composeTitle(pageTitle: string, brand = 'CONFIT'): string {
  const clean = (pageTitle ?? '').trim();
  if (!clean) return brand;
  // The localized titles already carry a "· CONFIT" suffix in some locales;
  // avoid doubling it.
  return clean.includes(brand) ? clean : `${clean} · ${brand}`;
}

/** Locale used for the announcement, so screen-reader speech matches the UI. */
export type RouteAnnouncement = { title: string; language: AppLanguage };
