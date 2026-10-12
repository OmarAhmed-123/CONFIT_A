import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for Discover (/discover, /products, /stylist) and the shared
 * ProductCard (Home, Discover, Wardrobe, MyLooks, try-on). Logo #3 rollout.
 *  - No legacy navy / gold / cream tokens in component chrome.
 *  - No slate text colours (slate-500 on brand-wash is 4.4:1; use brand-muted).
 *  - Colour-name swatch hex values in DiscoverView (Navy Blue, Optic White,
 *    Champagne Gold) are product data, not chrome, and are allowed.
 */

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');

const DISCOVER = read('src/views/consumer/DiscoverView.tsx');
const PRODUCT_CARD = read('src/components/product/ProductCard.tsx');

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FDF8EE/i, /7A5C28/i, /FAF9F6/i, /slate-950/, /backdrop-blur-xl/];

describe('Discover brand contract', () => {
  it('carries no legacy navy/gold/cream chrome tokens outside colour data', () => {
    const chrome = DISCOVER.split('\n')
      .filter((line) => !/labelKey: "discover\.color_/.test(line))
      .join('\n');
    for (const re of LEGACY) expect(chrome, `DiscoverView still has ${re}`).not.toMatch(re);
  });

  it('uses no slate text colours', () => {
    expect(DISCOVER).not.toMatch(/text-slate-\d+/);
  });

  it('eyebrow labels use brand-muted, not the legacy gold-dark tone', () => {
    expect(DISCOVER).toMatch(/uppercase tracking-widest text-brand-muted/);
  });

  it('search focus uses charcoal, not gold', () => {
    expect(DISCOVER).toMatch(/focus:border-brand-charcoal/);
    expect(DISCOVER).not.toMatch(/focus:border-\[#C5A059\]/);
  });
});

describe('ProductCard brand contract', () => {
  it('carries no legacy tokens', () => {
    for (const re of LEGACY) expect(PRODUCT_CARD, `ProductCard still has ${re}`).not.toMatch(re);
  });

  it('uses no slate text colours', () => {
    expect(PRODUCT_CARD).not.toMatch(/text-slate-\d+/);
  });
});
