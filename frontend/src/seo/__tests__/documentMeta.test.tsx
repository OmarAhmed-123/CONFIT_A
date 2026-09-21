/**
 * Document-metadata contract tests (audit 2026-09-21).
 *
 * index.html carried a single <title> and nothing else in the head, which for a
 * single-page application means ONE head for every route, forever: a link to
 * /privacy previewed with the storefront title, and an Arabic user's tab,
 * bookmarks and share card all carried English metadata.
 *
 * The tests below pin three things that are easy to get subtly wrong:
 *   1. tags are UPDATED IN PLACE, not re-created on every navigation;
 *   2. the description is resolved from the SAME route table as the title, so
 *      title and description can never describe different pages;
 *   3. the Arabic metadata is Arabic — not the English string with an `ar`
 *      locale marker, which is the shape a fallback takes.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup, act, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { syncDocumentMeta } from '../documentMeta';
import { ROUTE_META, descriptionKeyForPath, titleKeyForPath, routeMetaForPath } from '../../a11y/routes';
import { RouteAnnouncer } from '../../hooks/useRouteAnnouncement';

function metaContent(selector: string): string | null {
  return document.head.querySelector(selector)?.getAttribute('content') ?? null;
}

beforeEach(() => {
  document.head.querySelectorAll('meta[property^="og:"], meta[name="description"], meta[name^="twitter:"]').forEach((n) => n.remove());
});
afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

describe('syncDocumentMeta writes the head a client-side route never touches', () => {
  it('creates the missing tags on first call', () => {
    syncDocumentMeta({ title: 'Test · CONFIT', description: 'A description.', lang: 'en' });
    expect(document.title).toBe('Test · CONFIT');
    expect(metaContent('meta[name="description"]')).toBe('A description.');
    expect(metaContent('meta[property="og:title"]')).toBe('Test · CONFIT');
    expect(metaContent('meta[property="og:description"]')).toBe('A description.');
    expect(metaContent('meta[name="twitter:title"]')).toBe('Test · CONFIT');
  });

  it('updates the existing tags IN PLACE rather than appending duplicates', () => {
    syncDocumentMeta({ title: 'One', description: 'First.', lang: 'en' });
    const node = document.head.querySelector('meta[name="description"]');
    syncDocumentMeta({ title: 'Two', description: 'Second.', lang: 'en' });
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1);
    expect(document.head.querySelector('meta[name="description"]')).toBe(node);
    expect(metaContent('meta[name="description"]')).toBe('Second.');
  });

  it('leaves the previous description in place when the route declares none', () => {
    // Stale-but-true beats a generic string that describes the wrong page.
    syncDocumentMeta({ title: 'One', description: 'Kept.', lang: 'en' });
    syncDocumentMeta({ title: 'Two', lang: 'en' });
    expect(metaContent('meta[name="description"]')).toBe('Kept.');
    expect(document.title).toBe('Two');
  });

  it('marks the locale so an Arabic share card is not labelled as English', () => {
    syncDocumentMeta({ title: 'تيست', lang: 'ar' });
    expect(metaContent('meta[property="og:locale"]')).toBe('ar_EG');
    syncDocumentMeta({ title: 'Test', lang: 'en' });
    expect(metaContent('meta[property="og:locale"]')).toBe('en_GB');
  });
});

describe('title and description come from one route table', () => {
  const cases: Array<[string, string]> = [
    ['/privacy', 'privacy'],
    ['/privacy-policy', 'privacy'],
    ['/terms', 'terms'],
    ['/gdpr', 'gdpr'],
    ['/orders', 'orders'],
    ['/product/silk-blazer', 'discover'],
    ['/fit-finder', 'fit'],
    ['/', 'home'],
  ];

  it.each(cases)('%s resolves both a title and a description (%s)', (path, slug) => {
    const meta = routeMetaForPath(path);
    expect(meta, `${path} matched no route`).toBeDefined();
    expect(meta!.titleKey).toBe(`meta.${slug}_title`);
    expect(meta!.descriptionKey).toBe(`meta.${slug}_description`);
    expect(titleKeyForPath(path)).toBe(`meta.${slug}_title`);
    expect(descriptionKeyForPath(path)).toBe(`meta.${slug}_description`);
  });

  it('every route in the table declares a resolvable description in both locales', () => {
    for (const route of ROUTE_META) {
      expect(route.descriptionKey, `${route.titleKey} has no descriptionKey`).toBeTruthy();
      for (const lang of ['en', 'ar'] as const) {
        const value = i18n.getFixedT(lang)(route.descriptionKey!);
        expect(value, `${lang}:${route.descriptionKey}`).not.toBe(route.descriptionKey);
        expect(value.length, `${lang}:${route.descriptionKey} is too short to be a description`).toBeGreaterThan(40);
        expect(value, `${lang}:${route.descriptionKey} leaks a placeholder`).not.toContain('{{');
      }
    }
  });

  it('the Arabic descriptions are Arabic, not the English strings', () => {
    for (const route of ROUTE_META) {
      const ar = i18n.getFixedT('ar')(route.descriptionKey!);
      const en = i18n.getFixedT('en')(route.descriptionKey!);
      expect(/[\u0600-\u06FF]/.test(ar), `${route.descriptionKey} is not Arabic`).toBe(true);
      expect(ar).not.toBe(en);
    }
  });

  it('an unmatched path still resolves a title rather than throwing', () => {
    expect(titleKeyForPath('/definitely-not-a-route')).toBe('meta.home_title');
    expect(routeMetaForPath('/definitely-not-a-route')).toBeDefined();
  });
});

describe('the route announcer drives the head in the real app', () => {
  function renderAnnouncer(route: string) {
    return render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[route]}>
          <RouteAnnouncer />
        </MemoryRouter>
      </I18nextProvider>,
    );
  }

  it.each(['/privacy', '/terms', '/gdpr', '/orders'])('writes route metadata for %s', async (route) => {
    renderAnnouncer(route);
    await waitFor(() => {
      expect(document.title).toContain(i18n.t(titleKeyForPath(route)));
    });
    expect(metaContent('meta[name="description"]')).toBe(i18n.t(descriptionKeyForPath(route)!));
  });

  it('re-writes the metadata when the language changes', async () => {
    renderAnnouncer('/privacy');
    await waitFor(() => expect(document.title).toContain(i18n.t('meta.privacy_title')));
    await act(async () => {
      setAppLanguage('ar');
    });
    await waitFor(() => {
      expect(document.title).toContain(i18n.getFixedT('ar')('meta.privacy_title'));
    });
    expect(metaContent('meta[property="og:locale"]')).toBe('ar_EG');
    const description = metaContent('meta[name="description"]')!;
    expect(/[\u0600-\u06FF]/.test(description)).toBe(true);
  });
});
