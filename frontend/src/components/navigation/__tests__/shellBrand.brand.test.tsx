import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the shared consumer shell (Logo #3 rollout).
 * ConsumerLayout, ConsumerNavbar and TrustFooter render on every consumer page.
 *  - No legacy navy / gold / cream / dark-glass tokens remain.
 *  - No slate text colours (slate-500 on brand-wash is 4.4:1 and fails AA; text
 *    uses brand-muted / brand-charcoal). Neutral slate surface fills are allowed.
 *  - The AI Stylist pill is white with a charcoal icon chip, not navy with gold text.
 *  - The FAB keeps its logical end-6 placement (RTL contract in accessibility.rtl).
 *  - Semantic status colours (emerald) are kept in TrustFooter.
 */

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');

const FILES = {
  layout: read('src/layouts/ConsumerLayout.tsx'),
  navbar: read('src/components/navigation/ConsumerNavbar.tsx'),
  trust: read('src/components/commerce/TrustFooter.tsx'),
};

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FDF8EE/i, /7A5C28/i, /FAF9F6/i, /slate-950/, /backdrop-blur-xl/];

describe('consumer shell brand contract', () => {
  for (const [name, src] of Object.entries(FILES)) {
    it(`${name} carries no legacy navy/gold/cream tokens`, () => {
      for (const re of LEGACY) expect(src, `${name} still has ${re}`).not.toMatch(re);
    });

    it(`${name} uses no slate text colours`, () => {
      expect(src, `${name} has slate text`).not.toMatch(/text-slate-\d+/);
    });
  }

  it('layout root is white with charcoal ink', () => {
    expect(FILES.layout).toMatch(/min-h-screen flex flex-col bg-white text-brand-charcoal/);
  });

  it('AI Stylist pill is white with a charcoal icon chip and charcoal label', () => {
    expect(FILES.layout).toMatch(/rounded-full bg-white hover:bg-brand-wash text-brand-charcoal shadow-lg/);
    expect(FILES.layout).toMatch(/bg-brand-charcoal flex items-center justify-center text-white/);
    expect(FILES.layout).toMatch(/font-serif font-bold text-xs tracking-wider text-brand-charcoal/);
  });

  it('AI Stylist pill keeps logical end placement (RTL)', () => {
    expect(FILES.layout).toMatch(/fixed bottom-20 lg:bottom-8 end-6 z-40/);
  });

  it('TrustFooter keeps semantic emerald status for live items', () => {
    expect(FILES.trust).toMatch(/bg-emerald-50 text-emerald-700/);
  });
});

/**
 * Logo #3 shell regressions added with the navigation-rule pass.
 *  - The register accent under the header is brand charcoal (was gold #C9A227).
 *  - Body text selection uses charcoal, not the legacy bronze/navy pair.
 *  - The floating AI Stylist button's accessible name contains its visible
 *    label (WCAG 2.5.3 Label in Name). Visible label: layout.ai_stylist_director.
 */
describe('shell navigation rule, selection and FAB name', () => {
  const indexHtml = read('index.html');
  const registers = read('src/design/registers.ts');
  const en = JSON.parse(read('src/i18n/en.json'));
  const ar = JSON.parse(read('src/i18n/ar.json'));

  it('editorial register accent (navigation rule under the header) is brand charcoal', () => {
    expect(registers).toMatch(/editorial: \{\s*id: "editorial",\s*accent: "#252729"/);
    expect(registers).not.toMatch(/accent: "#C9A227"/);
  });

  it('body selection colours are charcoal, with no legacy bronze or navy', () => {
    expect(indexHtml).not.toMatch(/selection:bg-\[#B8935A\]/);
    expect(indexHtml).not.toMatch(/selection:text-\[#1B1F3B\]/);
    expect(indexHtml).toMatch(/selection:text-\[#252729\]/);
  });

  it('AI Stylist button uses the visible label as its accessible name', () => {
    expect(FILES.layout).toMatch(/aria-label=\{t\('layout\.ai_stylist_director'\)\}/);
    expect(FILES.layout).not.toMatch(/aria-label=\{t\('layout\.open_ai_stylist'\)\}/);
    expect(en.layout.ai_stylist_director).toBe('AI Stylist Director');
    expect(ar.layout.ai_stylist_director.length).toBeGreaterThan(0);
  });
});
