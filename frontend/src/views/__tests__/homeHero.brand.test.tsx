import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the homepage hero (Logo #3 rollout, HomeView + shared HeroSection).
 *  - HeroSection (shared with DiscoverView) is a white-first panel: no navy,
 *    gold, cream or white-on-dark text tokens. The photo overlay in HeroMedia
 *    keeps white text on its black scrim, which is allowed.
 *  - HomeView carries no legacy tokens outside the photo-palette metadata arrays,
 *    which describe image colours and are not UI styling.
 *  - Primary hero action is charcoal with white text (14.99:1).
 *  - Focus rings are charcoal, not gold (gold #C5A059 on white is 2.46:1).
 */

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');

const hero = read('src/components/common/HeroSection.tsx');
const home = read('src/views/consumer/HomeView.tsx');

const LEGACY = [/C5A059/i, /1B1F3B/i, /0C0E1E/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /slate-950/, /backdrop-blur/];

// Strip the photo-palette metadata arrays: they hold image colours, not UI styling.
const homeUi = home
  .split('\n')
  .filter((line) => !/^\s*palette:/.test(line))
  .join('\n');

describe('HeroSection brand contract (shared hero)', () => {
  it('carries no legacy navy/gold/cream tokens', () => {
    for (const re of LEGACY) expect(hero, `HeroSection still has ${re}`).not.toMatch(re);
  });

  it('panel surface is white with a charcoal heading', () => {
    expect(hero).toMatch(/bg-white text-brand-charcoal border border-brand-hairline/);
    expect(hero).toMatch(/text-brand-charcoal/);
  });
});

describe('HomeView brand contract', () => {
  it('has no legacy tokens outside palette metadata', () => {
    for (const re of LEGACY) expect(homeUi, `HomeView still has ${re}`).not.toMatch(re);
  });

  it('primary hero action is charcoal with white text', () => {
    expect(home).toMatch(/bg-brand-charcoal hover:bg-\[#1A1B1D\] text-white font-bold/);
  });

  it('no legacy slate text remains (slate-500 is 4.4:1 on brand-wash and fails AA)', () => {
    expect(home).not.toMatch(/text-slate-\d+/);
  });

  it('photo-overlay labels are light text, not charcoal (charcoal on the black scrim is illegible)', () => {
    expect(home).toMatch(/text-white uppercase tracking-wider mb-1 flex items-center gap-1/);
    expect(home).toMatch(/text-xs font-semibold text-white motion-safe:group-hover:translate-x-1/);
    expect(home).not.toMatch(/text-brand-charcoal uppercase tracking-wider mb-1 flex items-center gap-1/);
  });

  it('no focus ring is white on the white page', () => {
    expect(home).not.toMatch(/focus-visible:ring-white/);
  });

  it('focus rings are charcoal, not gold', () => {
    expect(home).not.toMatch(/focus-visible:ring-\[#C5A059\]/);
    expect(home).toMatch(/focus-visible:ring-brand-charcoal/);
  });
});
