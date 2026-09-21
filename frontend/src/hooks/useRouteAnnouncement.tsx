import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { SKIP_TARGET_ID } from '../components/common/SkipLink';
import { composeTitle, descriptionKeyForPath, titleKeyForPath } from '../a11y/routes';
import { syncDocumentMeta } from '../seo/documentMeta';

/**
 * useRouteAnnouncement — makes a client-side navigation perceivable.
 *
 * WHY THIS EXISTS (audit 2026-09-21: "لم يتحقق الفحص من … focus order …"),
 * and the SPA-specific WCAG failures behind it:
 *
 *   · 2.4.2 Page Titled — `document.title` was written once in index.html and
 *     never again. Screen readers announce the title on load; with a static
 *     title, every route after the first is announced as "CONFIT — Where Style
 *     Meets Your Character", including the privacy policy.
 *   · 2.4.3 Focus Order / 4.1.3 Status Messages — React Router swaps the page
 *     content in place. Nothing moves focus, nothing is announced, so a
 *     keyboard user presses Enter on "Orders" and the next Tab continues from
 *     the nav they were already in, with no indication the content changed.
 *
 * WHAT IT DOES, ON EVERY PATHNAME CHANGE:
 *   1. writes a localized `document.title`;
 *   2. moves focus to the `<main>` region (which is `tabIndex={-1}`), so the
 *      NEXT Tab starts at the new page's first control;
 *   3. publishes a polite announcement for screen readers.
 *
 * WHAT IT DELIBERATELY DOES NOT DO — each of these is a way the naive version
 * of this hook breaks the app for the people it is meant to help:
 *   · It does not run on the initial mount. Focus on first paint belongs to the
 *     browser; stealing it interrupts a screen reader's own page-load reading.
 *   · It does not steal focus while a modal owns it. Modals use
 *     `aria-modal="true"` and trap Tab; moving focus to `<main>` behind the
 *     panel would silently eject the user from the dialog.
 *   · It does not steal focus from a field the user is typing in. Several
 *     routes re-render on query-string changes mid-form; yanking focus out of
 *     an input is worse than a missing announcement.
 *   · It does not re-announce when only the search string changes (`?q=`), to
 *     avoid a live region that fires on every keystroke.
 */
export function useRouteAnnouncement(): string {
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const [announcement, setAnnouncement] = useState('');
  const isFirstRender = useRef(true);
  const lastPath = useRef(location.pathname);

  useEffect(() => {
    const titleKey = titleKeyForPath(location.pathname);
    const pageTitle = t(titleKey);
    const fullTitle = composeTitle(pageTitle);

    // Title + description + Open Graph, from the SAME route table and the same
    // language, in one place. They share a trigger (route or language change)
    // and must never disagree, so they are written together rather than by two
    // effects that would drift.
    const descriptionKey = descriptionKeyForPath(location.pathname);
    syncDocumentMeta({
      title: fullTitle,
      description: descriptionKey ? t(descriptionKey) : undefined,
      lang: (i18n.language as 'en' | 'ar') ?? 'en',
    });

    // Initial mount: title yes (so the tab is right immediately), focus no.
    if (isFirstRender.current) {
      isFirstRender.current = false;
      lastPath.current = location.pathname;
      return;
    }

    // Query-only change: nothing navigational happened.
    if (lastPath.current === location.pathname) return;
    lastPath.current = location.pathname;

    const active = document.activeElement as HTMLElement | null;
    const insideDialog = !!active?.closest('[role="dialog"],[aria-modal="true"]');
    const isTextEntry =
      !!active &&
      (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable);

    if (!insideDialog && !isTextEntry) {
      const main = document.getElementById(SKIP_TARGET_ID);
      // preventScroll:false — the new page should start at the top; the browser
      // scrolls the focused region into view and `scroll-margin-block-start`
      // (index.css) keeps it clear of the sticky header (WCAG 2.4.12).
      main?.focus();
    }

    setAnnouncement(`${pageTitle} — ${t('a11y.navigated_to', { page: pageTitle })}`);
  }, [location.pathname, t, i18n.resolvedLanguage]);

  // Re-title when the language changes without a navigation, so the tab and the
  // announcement never lag the visible UI.
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.title = composeTitle(t(titleKeyForPath(location.pathname)));
    }
  }, [i18n.resolvedLanguage, location.pathname, t]);

  return announcement;
}

/**
 * Mounted once, at the app root, alongside the router. The live region lives
 * OUTSIDE the routed tree on purpose: a region that is unmounted and remounted
 * by the very navigation it is reporting will frequently miss its own update.
 */
export const RouteAnnouncer: React.FC = () => {
  const announcement = useRouteAnnouncement();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="route-announcer"
      className="sr-only"
    >
      {announcement}
    </div>
  );
};
