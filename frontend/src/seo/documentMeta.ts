/**
 * Document metadata for the SPA — the head tags a client-side route never
 * touches on its own.
 *
 * WHY THIS EXISTS (audit 2026-09-21: the review flagged that the pages shipped
 * a static title and nothing else in the head):
 *
 * index.html carries one `<title>` and no `description`, no Open Graph tags and
 * no per-route metadata. A single-page app therefore has exactly one head, for
 * every route, forever. Two consequences that are visible outside the app:
 *
 *   · A link to /privacy shared into WhatsApp, Slack, LinkedIn or X renders the
 *     generic storefront title and no description, because the crawler reads
 *     og:* from the HTML it fetched and never runs the router.
 *   · An Arabic user's browser tab, bookmarks and share cards all carry English
 *     metadata even though the page itself is Arabic.
 *
 * SCOPE — what this does and does not claim:
 *   This updates the tags AT RUNTIME in the browser. That fixes the tab, the
 *   bookmark, the client-side history and anything that reads the DOM after
 *   hydration. It does NOT make the app properly indexable: a crawler that does
 *   not execute JavaScript still sees index.html only. Server-side rendering or
 *   prerendering is the real fix for that, and it is NOT done here — stating
 *   otherwise would be the kind of over-claim this whole remediation is about.
 *   index.html carries sensible static defaults so the non-JS fetch is at least
 *   accurate rather than wrong.
 */
import type { AppLanguage } from '../i18n/i18n';

export interface DocumentMeta {
  title: string;
  description?: string;
  /** Current UI language, used for `og:locale`. */
  lang: AppLanguage;
}

/** `en` → `en_GB`, `ar` → `ar_EG`. */
const OG_LOCALE: Record<string, string> = { en: 'en_GB', ar: 'ar_EG' };

function upsert(selector: string, attr: 'name' | 'property', key: string, content: string): void {
  if (typeof document === 'undefined') return;
  let el = document.head.querySelector<HTMLMetaElement>(selector);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  if (el.getAttribute('content') !== content) {
    el.setAttribute('content', content);
  }
}

/**
 * Idempotent: called on every route and language change. Tags are updated in
 * place rather than re-created, so a crawler or a test that holds a reference
 * sees the current value instead of a detached node.
 */
export function syncDocumentMeta({ title, description, lang }: DocumentMeta): void {
  if (typeof document === 'undefined') return;

  document.title = title;
  upsert('meta[property="og:title"]', 'property', 'og:title', title);
  upsert('meta[name="twitter:title"]', 'name', 'twitter:title', title);
  upsert('meta[property="og:locale"]', 'property', 'og:locale', OG_LOCALE[lang] ?? OG_LOCALE.en);

  if (description) {
    upsert('meta[name="description"]', 'name', 'description', description);
    upsert('meta[property="og:description"]', 'property', 'og:description', description);
    upsert('meta[name="twitter:description"]', 'name', 'twitter:description', description);
  }
}
