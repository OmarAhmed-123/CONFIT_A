/**
 * API error localization contract (2026-09-23).
 *
 * `localizeApiError` decides what a shopper reads when something goes wrong.
 * Two failure modes matter and are both asserted here:
 *
 *   1. a known code must resolve to a localized sentence, and the Arabic must
 *      not be the English source text (an English fallback in an RTL UI is the
 *      defect this project keeps finding);
 *   2. an UNKNOWN code must keep the server's own message — a vague "something
 *      went wrong" would hide a specific, actionable failure, and inventing a
 *      translation for an unknown code would be a guess presented as copy.
 */
import { describe, it, expect } from 'vitest';

import en from '../en.json';
import ar from '../ar.json';
import i18n, { setAppLanguage } from '../i18n';
import { API_ERROR_KEYS, localizeApiError } from '../apiErrors';

type Tree = Record<string, unknown>;
const lookup = (tree: Tree, dotted: string): unknown =>
  dotted.split('.').reduce<unknown>((n, p) => (n && typeof n === 'object' ? (n as Tree)[p] : undefined), tree);

const t = ((key: string) => i18n.t(key)) as unknown as (k: string) => string;

describe('every mapped error code resolves to localized copy', () => {
  it('has an entry in both locales, and the Arabic is a real translation', () => {
    for (const [code, key] of Object.entries(API_ERROR_KEYS)) {
      const enValue = lookup(en as Tree, key);
      const arValue = lookup(ar as Tree, key);
      expect(typeof enValue, `${code} -> ${key} (en)`).toBe('string');
      expect(typeof arValue, `${code} -> ${key} (ar)`).toBe('string');
      expect((enValue as string).trim()).not.toBe('');
      expect(arValue, `${key} is still English in the Arabic bundle`).not.toBe(enValue);
    }
  });

  it('returns the localized sentence for a known code', () => {
    setAppLanguage('en');
    const message = localizeApiError({ code: 'IDEMPOTENCY_KEY_CONFLICT' }, t);
    expect(message).toContain('conflicts with an order');

    setAppLanguage('ar');
    const arabic = localizeApiError({ code: 'IDEMPOTENCY_KEY_CONFLICT' }, t);
    expect(arabic).toMatch(/[\u0600-\u06FF]/);
    expect(arabic).not.toContain('conflicts with an order');

    setAppLanguage('en');
  });

  it('keeps the server message for an unmapped code instead of hiding it', () => {
    const message = localizeApiError(
      { code: 'SOME_FUTURE_CODE', message: 'Warehouse rejected the release.' },
      t,
    );
    expect(message).toBe('Warehouse rejected the release.');
  });

  it('never returns an empty string, even with nothing to go on', () => {
    setAppLanguage('en');
    expect(localizeApiError({}, t).trim()).not.toBe('');
    expect(localizeApiError(null, t).trim()).not.toBe('');
  });

  it('falls back to the server message when the key is missing from the bundle', () => {
    // Simulates a code whose key was forgotten: i18next returns the key path.
    // Showing "errors.some_key" to a shopper would be worse than the server's
    // own wording, so the helper must detect it.
    const tEcho = (k: string) => k;
    expect(localizeApiError({ code: 'IDEMPOTENCY_KEY_CONFLICT', message: 'Server said no.' }, tEcho))
      .toBe('Server said no.');
  });
});
