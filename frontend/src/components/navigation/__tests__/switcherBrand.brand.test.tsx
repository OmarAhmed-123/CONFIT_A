import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the header language and currency switchers (shared consumer shell).
 *  - The active language pill is brand charcoal, not navy #1B1F3B.
 *  - Hover and focus use brand neutrals and charcoal, not the gold-brown #7A5C28 / #FDF8EE.
 */
const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');
const lang = read('src/components/navigation/LanguageSwitcher.tsx');
const currency = read('src/components/navigation/CurrencySwitcher.tsx');
const LEGACY = [/1B1F3B/i, /7A5C28/i, /FDF8EE/i, /C5A059/i, /A37E44/i];

describe('switcher brand contract', () => {
  for (const [name, src] of Object.entries({ lang, currency })) {
    it(`${name} carries no legacy navy/gold tokens`, () => {
      for (const re of LEGACY) expect(src, `${name} still has ${re}`).not.toMatch(re);
    });
  }
  it('active language pill is brand charcoal with white text', () => {
    expect(lang).toMatch(/bg-brand-charcoal text-white/);
  });
  it('currency focus ring is charcoal', () => {
    expect(currency).toMatch(/focus-visible:ring-brand-charcoal/);
    expect(currency).not.toMatch(/focus:ring-\[/);
  });
});
