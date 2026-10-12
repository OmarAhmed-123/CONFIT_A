/**
 * Logo #3 brand contract for the product detail page (light scheme only).
 *
 * Source-level checks: the legacy navy/gold/cream/slate chrome must not return.
 * Semantic status colours (rose, amber, emerald) stay, and the commerce path
 * keeps the light surface. Behaviour is covered by productDetailContract.test.tsx.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SRC = readFileSync(resolve(__dirname, '../consumer/ProductDetailView.tsx'), 'utf8');
// Comments may still name the old tokens (the contrast history); only code is checked.
const CODE = SRC
  .replace(/\/\*[\s\S]*?\*\//g, '') // block and JSX comments
  .split('\n')
  .filter((l) => !/^\s*\/\//.test(l)) // line comments
  .join('\n');

describe('ProductDetailView brand contract (Logo #3, light scheme)', () => {
  it('has no legacy navy, gold, cream, or burgundy chrome in code', () => {
    for (const legacy of ['#1B1F3B', '#0C0E1E', '#C5A059', '#7A5C28', '#FDF8EE', '#FAF9F6', '#7A1F2B', 'confit-navy', 'confit-gold']) {
      expect(CODE, legacy).not.toContain(legacy);
    }
  });

  it('keeps Tailwind slate neutrals out of code; brand neutrals are used instead', () => {
    expect(CODE).not.toMatch(/\bslate-\d{2,3}\b/);
    expect(CODE).toContain('bg-brand-charcoal');
    expect(CODE).toContain('text-brand-charcoal');
    expect(CODE).toContain('text-brand-muted');
  });

  it('overlay Try On uses light glass, not the dark commerce surface', () => {
    expect(CODE).toContain('surface-glass-light absolute bottom-4 end-4');
    expect(CODE).not.toContain('surface-glass-dark');
  });

  it('semantic status colours are kept (rose, amber, emerald)', () => {
    expect(CODE).toContain('text-amber-700');
    expect(CODE).toContain('text-emerald-700');
    expect(CODE).toMatch(/text-rose-/);
  });

  it('primary purchase CTAs (main + sticky) use a charcoal focus ring, not the gold global', () => {
    const ctas = CODE.match(/className="[^"]*bg-brand-charcoal[^"]*"/g) ?? [];
    const purchase = ctas.filter((c) => /min-h-12|py-4/.test(c));
    expect(purchase.length).toBe(2);
    for (const c of purchase) expect(c).toContain('focus-visible:outline-brand-charcoal');
  });

  it('primary purchase CTA is charcoal with a visible focus treatment', () => {
    expect(CODE).toMatch(/bg-brand-charcoal hover:bg-\[#1A1B1D\][^"]*disabled:opacity-50 text-white/);
  });
});
