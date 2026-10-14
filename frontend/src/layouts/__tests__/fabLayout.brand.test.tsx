import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Floating AI Stylist control: mobile overlap contract.
 *  - Mobile footprint is a 48px icon-only circle (was 66x50 pill). The label stays in aria-label.
 *  - Default mobile position is bottom-4; the PDP sticky CTA raises it to bottom-5rem via :has().
 *  - The sticky CTA carries the data-sticky-cta marker the CSS depends on.
 *  - DesignShowcases (shared by Home, Discover, Orders, Admin, Profile, Try-on) carries no legacy tokens.
 * Layout is verified in a real browser separately (see coverage doc); these are source contracts.
 */
const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');
const layout = read('src/layouts/ConsumerLayout.tsx');
const css = read('src/styles/index.css');
const pdp = read('src/views/consumer/ProductDetailView.tsx');
const showcases = read('src/components/showcase/DesignShowcases.tsx');

describe('floating AI Stylist control: mobile overlap contract', () => {
  it('mobile footprint is an icon-only 48px circle; the pill returns at sm', () => {
    expect(layout).toMatch(/h-12 w-12[^"]*sm:h-auto sm:w-auto sm:px-5 sm:py-3/);
  });

  it('keeps the accessible name on the button', () => {
    expect(layout).toMatch(/aria-label=\{t\('layout\.ai_stylist_director'\)\}/);
  });

  it('anchor uses the position class the CSS rules target', () => {
    expect(layout).toContain('stylist-fab-anchor');
    expect(css).toMatch(/\.stylist-fab-anchor\s*\{\s*bottom:\s*1rem;\s*\}/);
  });

  it('PDP sticky CTA is marked and raises the control on mobile via :has()', () => {
    expect(pdp).toContain('data-sticky-cta');
    expect(css).toMatch(/body:has\(\[data-sticky-cta\]\)\s+\.stylist-fab-anchor\s*\{\s*bottom:\s*5rem;?\s*\}/);
  });

  it('shared showcase component carries no legacy gold, navy, cream or slate tokens', () => {
    for (const re of [/C5A059/i, /FDF8EE/i, /7A5C28/i, /1B1F3B/i, /A37E44/i, /slate-\d+/, /FAF9F6/i]) {
      expect(showcases, `DesignShowcases still has ${re}`).not.toMatch(re);
    }
  });
});
