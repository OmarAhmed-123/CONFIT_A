/**
 * i18n contract tests — the measurement the 2026-09-21 audit said was missing.
 *
 * The audit's own words: "HTTP 200 للمسار لا يثبت أن النص القانوني كامل أو
 * محدث أو أن العربية ترجمة متكافئة". A route returning 200 says nothing about
 * whether Arabic is a real translation. These tests answer that question
 * directly, and they run in CI on every push.
 *
 * Three layers:
 *   1. STATIC  — bundle parity and code↔bundle agreement, over the real files.
 *   2. RUNTIME — the translator actually produces Arabic for user-visible
 *      surfaces (legal pages, toasts produced outside React).
 *   3. DOM     — switching language updates <html lang> and <html dir>.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { render, screen, cleanup, act } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import i18n, {
  setAppLanguage,
  clearMissingTranslations,
  getMissingTranslations,
  SUPPORTED_LANGUAGES,
  directionFor,
  isSupportedLanguage,
  LANGUAGE_STORAGE_KEY,
} from '../i18n';
import { resolveMessage, msg, detail, LocalizedError, translatableFrom } from '../messages';
import { formatNumber, formatDate, formatMoney, formatPercent, languageDisplayName } from '../format';
import en from '../en.json';
import ar from '../ar.json';

const I18N_DIR = path.resolve(__dirname, '..');
const SRC_DIR = path.resolve(__dirname, '../..');

/* ─────────────────────────── static analysis helpers ─────────────────────────── */

function flatten(obj: Record<string, unknown>, prefix = '', out: Record<string, string> = {}) {
  for (const [key, value] of Object.entries(obj)) {
    const keyPath = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object') flatten(value as Record<string, unknown>, keyPath, out);
    else out[keyPath] = String(value);
  }
  return out;
}

function collectSources(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      collectSources(full, acc);
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name)) {
      acc.push(full);
    }
  }
  return acc;
}

const KEY_CALL_RE = /(?<![A-Za-z0-9_$.])(?:i18n\.)?t\(\s*['"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"]/g;

function keysReferencedInSource(): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const file of collectSources(SRC_DIR)) {
    const text = fs.readFileSync(file, 'utf8');
    let m: RegExpExecArray | null;
    KEY_CALL_RE.lastIndex = 0;
    while ((m = KEY_CALL_RE.exec(text)) !== null) {
      const rel = path.relative(SRC_DIR, file);
      found.set(m[1], [...(found.get(m[1]) ?? []), rel]);
    }
  }
  return found;
}

const flatEn = flatten(en as Record<string, unknown>);
const flatAr = flatten(ar as Record<string, unknown>);

/** Brand names and format tokens legitimately identical across locales. */
const NON_TRANSLATABLE = new Set<string>([]);

/* ─────────────────────────── 1. static ─────────────────────────── */

describe('i18n bundle — static parity', () => {
  it('ships exactly the supported locales', () => {
    expect(Object.keys(i18n.options.resources ?? {}).sort()).toEqual([...SUPPORTED_LANGUAGES].sort());
  });

  it('ar.json is NOT a copy of en.json (a real translation, not a fallback)', () => {
    const identical = Object.keys(flatEn).filter(
      (k) => flatEn[k] === flatAr[k] && !NON_TRANSLATABLE.has(k) && /[A-Za-z]/.test(flatEn[k]),
    );
    expect(identical).toEqual([]);
  });

  it('every key in en.json exists in ar.json and vice versa (no drift either way)', () => {
    const enKeys = Object.keys(flatEn).sort();
    const arKeys = Object.keys(flatAr).sort();
    expect(arKeys.filter((k) => !(k in flatEn))).toEqual([]);
    expect(enKeys.filter((k) => !(k in flatAr))).toEqual([]);
    expect(enKeys.length).toBeGreaterThan(400);
  });

  it('no locale leaf is empty, whitespace-only, or a raw dotted key', () => {
    for (const [locale, flat] of [
      ['en', flatEn],
      ['ar', flatAr],
    ] as const) {
      for (const [key, value] of Object.entries(flat)) {
        expect(value.trim(), `${locale}:${key} is empty`).not.toBe('');
        expect(
          /^[a-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$/.test(value.trim()),
          `${locale}:${key} renders a raw key`,
        ).toBe(false);
      }
    }
  });

  it('interpolation placeholders match between locales', () => {
    const ph = (s: string) => (s.match(/\{\{\s*\w+\s*\}\}/g) ?? []).map((p) => p.replace(/[{}\s]/g, '')).sort();
    for (const key of Object.keys(flatEn)) {
      expect(ph(flatAr[key] ?? ''), `placeholder mismatch at ${key}`).toEqual(ph(flatEn[key]));
    }
  });

  it('every literal t() key used in source exists in en.json', () => {
    const orphaned = [...keysReferencedInSource().keys()].filter((k) => !(k in flatEn));
    expect(orphaned).toEqual([]);
  });

  it('every legal clause is a translation key, not hard-coded English', () => {
    // The audit's core doubt: are the legal pages actually translatable?
    const legalSource = fs.readFileSync(path.join(SRC_DIR, 'views/legal/LegalViews.tsx'), 'utf8');
    // No bare English JSX text ('>Sentence with spaces<') may remain.
    const bareJsxText = [...legalSource.matchAll(/>\s*([A-Z][A-Za-z][A-Za-z ,'’\-]{10,}[a-z.!?])\s*</g)];
    expect(bareJsxText.map((m) => m[1])).toEqual([]);
  });
});

/* ─────────────────────────── 2. runtime ─────────────────────────── */

describe('i18n runtime — translation actually happens', () => {
  beforeEach(async () => {
    clearMissingTranslations();
    await setAppLanguage('en');
  });

  it('resolves a user-visible key to real Arabic after switching', async () => {
    await setAppLanguage('ar');
    expect(i18n.t('legal.tab_privacy')).toMatch(/[\u0600-\u06FF]/);
    expect(i18n.t('toast.item_removed')).toMatch(/[\u0600-\u06FF]/);
    expect(i18n.t('a11y.skip_to_content')).toMatch(/[\u0600-\u06FF]/);
  });

  it('interpolates params in both locales', async () => {
    await setAppLanguage('en');
    expect(i18n.t('footer.returns_available', { days: 30 })).toContain('30');
    await setAppLanguage('ar');
    const arabic = i18n.t('footer.returns_available', { days: 30 });
    expect(arabic).toMatch(/[\u0600-\u06FF]/);
    expect(arabic).toContain('30');
  });

  it('records a missing key instead of silently shipping English', () => {
    clearMissingTranslations();
    const result = i18n.t('this.key.does.not.exist');
    // ...and never renders the raw dotted key to the user.
    expect(result).not.toBe('this.key.does.not.exist');
    expect(result).toBe('Exist');
    expect(getMissingTranslations()).toHaveProperty('en:this.key.does.not.exist');
  });
});

describe('TranslatableMessage — strings produced outside React', () => {
  beforeEach(async () => {
    await setAppLanguage('en');
  });

  it('resolves a store-emitted descriptor in the ACTIVE language', async () => {
    const descriptor = msg('toast.no_purchasable_size_for', { title: 'Silk Blazer' });
    expect(resolveMessage(descriptor, i18n.t.bind(i18n))).toBe('No purchasable size found for Silk Blazer');

    await setAppLanguage('ar');
    const arabic = resolveMessage(descriptor, i18n.t.bind(i18n));
    expect(arabic).toMatch(/[\u0600-\u06FF]/);
    expect(arabic).toContain('Silk Blazer'); // brand/product names stay verbatim
  });

  it('passes a legacy plain string through untouched', () => {
    expect(resolveMessage('already translated', i18n.t.bind(i18n))).toBe('already translated');
  });

  it('unwraps a LocalizedError into its descriptor and never loses the detail', () => {
    const err = new LocalizedError(msg('errors.image_corrupt'));
    expect(translatableFrom(err)).toEqual({ key: 'errors.image_corrupt' });

    const wrapped = translatableFrom(new Error('upstream said 503'));
    expect(wrapped).toEqual({ key: 'errors.generic', params: { reason: 'upstream said 503' } });
  });

  it('truncates runaway upstream detail so a toast is not a stack trace', () => {
    expect(detail('x'.repeat(500)).length).toBeLessThanOrEqual(160);
    expect(detail(new Error('  multi\n  line  '))).toBe('multi line');
    expect(detail(null)).toBe('');
  });
});

describe('format.ts — numbers follow the app language, not the browser', () => {
  it('formats digits in Arabic for ar and Latin for en', () => {
    expect(formatNumber(1234.5, 'en')).toBe('1,234.5');
    expect(formatNumber(1234.5, 'ar')).toMatch(/[\u0660-\u0669]/); // Arabic-Indic digits
  });

  it('formats money from minor units with the right currency', () => {
    expect(formatMoney(123450, 'USD', 'en')).toContain('1,234.50');
    expect(formatMoney(123450, 'USD', 'ar')).toMatch(/[\u0660-\u0669\u066B\u066C]/);
  });

  it('formats dates with Arabic month names', () => {
    const iso = '2026-09-21';
    expect(formatDate(iso, 'en')).toContain('September');
    expect(formatDate(iso, 'ar')).toMatch(/[\u0600-\u06FF]/);
  });

  it('formats percentages from whole numbers', () => {
    expect(formatPercent(45, 'en')).toBe('45%');
    expect(formatPercent(0.45, 'en')).toBe('45%');
  });

  it('returns empty string rather than NaN for absent values', () => {
    expect(formatNumber(null, 'en')).toBe('');
    expect(formatMoney(undefined, 'USD', 'en')).toBe('');
    expect(formatDate('not-a-date', 'en')).toBe('');
    expect(formatPercent(NaN, 'en')).toBe('');
  });

  it('names each language in its own language, without a region qualifier', () => {
    expect(languageDisplayName('ar')).toMatch(/[\u0600-\u06FF]/);
    expect(languageDisplayName('en')).toMatch(/English/i);
    // REGRESSION 2026-09-23: the switcher used to label the English option
    // "American English" / "العربية (مصر)" because the name was resolved from
    // the en-US / ar-EG FORMATTING tag. That leaked a regional variant into a
    // language selector on every page of a Cairo-market product. Assert the
    // exact base names so resolving from INTL_LOCALE again kills this test.
    expect(languageDisplayName('en')).toBe('English');
    expect(languageDisplayName('ar')).toBe('العربية');
    for (const name of [languageDisplayName('en'), languageDisplayName('ar')]) {
      expect(name).not.toMatch(/American|United States|مصر|Egypt/i);
    }
  });

  it('is immune to region-qualified tags and to the browser locale', () => {
    // Research note (MDN `Intl.DisplayNames`, tc39 proposal-intl-displaynames-v2
    // §1.3.1): `languageDisplay` defaults to "dialect", which is what renders
    // "en-US" as "American English" and "ar-EG" as "العربية (مصر)". The helper
    // must not depend on a default it does not control, and it must not leak a
    // region qualifier into a language switcher.
    //
    // Each of these is a tag a caller could plausibly pass — a future locale
    // picker, a URL parameter, a browser language — so each is asserted
    // against the BASE language name rather than left to chance.
    for (const tag of ['en', 'en-US', 'en-GB', 'en-AU', 'EN', 'en-us']) {
      expect(languageDisplayName(tag)).toBe('English');
    }
    for (const tag of ['ar', 'ar-EG', 'ar-SA', 'AR', 'ar-eg']) {
      expect(languageDisplayName(tag)).toBe('العربية');
    }
    // The regression in plain terms: none of the region spellings may reappear.
    const names = ['en', 'en-US', 'en-GB', 'ar', 'ar-EG'].map((t) => languageDisplayName(t));
    for (const name of names) {
      expect(name).not.toMatch(/American|British|United States|United Kingdom|مصر|السعودية|Egypt|Saudi/i);
    }
  });

  it('resolves the name in the requested UI language even for a region tag', () => {
    // The live-region announcement path: an English UI user switching to an
    // Arabic-region tag should hear the Arabic name AS WRITTEN IN ENGLISH.
    expect(languageDisplayName('ar-EG', 'en')).toMatch(/Arabic/i);
    expect(languageDisplayName('en-US', 'ar')).toMatch(/[\u0600-\u06FF]/);
  });

  it('names the target language in the language the user is reading, for speech', () => {
    // The visible control shows self-names; the live-region announcement must
    // stay in the active UI language so screen readers do not switch script
    // mid-sentence.
    expect(languageDisplayName('en', 'ar')).toMatch(/[\u0600-\u06FF]/);
    expect(languageDisplayName('ar', 'en')).toMatch(/Arabic/i);
  });
});

/* ─────────────────────────── 3. DOM ─────────────────────────── */

describe('language application to the document', () => {
  beforeEach(async () => {
    await setAppLanguage('en');
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    document.documentElement.removeAttribute('data-lang');
  });

  it('sets lang, dir and the Arabic typeface class', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    expect(document.documentElement.getAttribute('lang')).toBe('ar');
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    expect(document.documentElement.getAttribute('data-dir')).toBe('rtl');
    expect(document.body.classList.contains('font-arabic')).toBe(true);
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('ar');

    await act(async () => {
      await setAppLanguage('en');
    });
    expect(document.documentElement.getAttribute('dir')).toBe('ltr');
    expect(document.body.classList.contains('font-arabic')).toBe(false);
  });

  it('directionFor maps every supported language', () => {
    expect(directionFor('ar')).toBe('rtl');
    expect(directionFor('en')).toBe('ltr');
  });

  it('rejects an unsupported language instead of half-applying it', async () => {
    expect(isSupportedLanguage('fr')).toBe(false);
    await act(async () => {
      await setAppLanguage('fr' as never);
    });
    expect(document.documentElement.getAttribute('lang')).toBe('en');
  });
});

describe('legal pages render translated content', () => {
  const renderRoute = (node: React.ReactNode) => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>{node}</MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );
  };

  afterEach(cleanup);

  it('Privacy renders Arabic headings and body when the app is in Arabic', async () => {
    const { PrivacyPolicyView } = await import('../../views/legal/LegalViews');
    await act(async () => {
      await setAppLanguage('ar');
    });
    renderRoute(<PrivacyPolicyView />);
    // A real clause, not just the tab label.
    expect(screen.getByRole('heading', { name: '١. البيانات التي نعالجها' })).toBeTruthy();
    // The tab set is translated too — not just the body.
    expect(screen.getAllByText('سياسة الخصوصية').length).toBeGreaterThan(0);
    expect(screen.queryByText('Privacy Policy')).toBeNull();
    cleanup();
    await act(async () => {
      await setAppLanguage('en');
    });
  });

  it('Privacy renders English headings when the app is in English', async () => {
    const { PrivacyPolicyView } = await import('../../views/legal/LegalViews');
    await act(async () => {
      await setAppLanguage('en');
    });
    renderRoute(<PrivacyPolicyView />);
    expect(screen.getByText('1. Data we process')).toBeTruthy();
  });

  it('never claims on-device biometric processing anywhere in the legal body', async () => {
    const { GdprView, PrivacyPolicyView } = await import('../../views/legal/LegalViews');
    await act(async () => {
      await setAppLanguage('en');
    });
    renderRoute(
      <>
        <PrivacyPolicyView />
        <GdprView />
      </>,
    );
    const body = (document.body.textContent ?? '').toLowerCase();
    // The withdrawn claim must be gone as a phrase AND as a concept: the
    // product performs no local inference, so it may not imply any.
    expect(body).not.toContain('on-device biometric');
    expect(body).not.toContain('on-device');
    // The measure of honesty is the positive statement, not just the absence.
    expect(document.body.textContent).toContain('We do not perform face recognition');
    // ...and it must not promise a controller mailbox it cannot show.
    expect(document.body.textContent).not.toContain('privacy@confit.io');
  });
});
