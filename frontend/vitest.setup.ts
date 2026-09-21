import '@testing-library/jest-dom/vitest';

/**
 * Global i18n bootstrap for the test environment.
 *
 * WHY (2026-09-21): components resolve their copy through `useTranslation()`
 * now, so a test that renders a component WITHOUT importing the i18n module
 * gets `t()` returning the raw key — the aria-label becomes "partner.form_label"
 * and an accessible-name assertion fails for a reason that has nothing to do
 * with the component under test.
 *
 * Previously this only worked because components carried literal English and
 * never called `t()`. Initialising the real instance once, globally, means
 * every test renders the same English strings a user sees, and a test that
 * wants Arabic calls `setAppLanguage('ar')` explicitly (see
 * src/i18n/__tests__/i18nParity.test.tsx).
 */
import i18n from './src/i18n/i18n';

// Deterministic source locale: localStorage is cleared per test file in most
// suites, but a leftover 'ar' from a prior file in the same worker must not
// silently change what every other assertion is comparing against.
if (i18n.resolvedLanguage !== 'en') {
  await i18n.changeLanguage('en');
}
i18n.options.interpolation = { ...(i18n.options.interpolation ?? {}), escapeValue: false };

// jsdom has no matchMedia; several animation-aware components read it.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
