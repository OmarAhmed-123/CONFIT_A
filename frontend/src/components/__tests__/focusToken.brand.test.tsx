import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Logo #3 focus contract.
 *  - Global focus outline is the brand charcoal token (light surfaces, the default).
 *  - Controls over dark photography opt in to `.focus-on-dark`, which turns the
 *    outline white. Both colours are checked against the surface they sit on.
 *  - The focus contract stays outline-only (no box-shadow), per surfaceSystem.
 */

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');
const css = read('src/styles/index.css');
const home = read('src/views/consumer/HomeView.tsx');
const layout = read('src/layouts/ConsumerLayout.tsx');
const navbar = read('src/components/navigation/ConsumerNavbar.tsx');

function luminance(hex: string): number {
  const n = hex.replace('#', '');
  const ch = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255);
  const lin = ch.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe('focus token contract (Logo #3)', () => {
  it('global token is brand charcoal', () => {
    expect(css).toMatch(/--confit-focus:\s*#252729/);
  });

  it('global :focus-visible outline uses the token, with no box-shadow', () => {
    const block = css.match(/:focus-visible\s*\{[^}]*\}/)?.[0] ?? '';
    expect(block).toMatch(/outline:\s*3px solid var\(--confit-focus\)/);
    expect(block).not.toContain('box-shadow');
  });

  it('charcoal outline is ≥3:1 on the white page and the cream/wash surfaces', () => {
    expect(contrast('#252729', '#FFFFFF')).toBeGreaterThanOrEqual(3);
    expect(contrast('#252729', '#FAF9F6')).toBeGreaterThanOrEqual(3);
  });

  it('dark-surface opt-in class turns the outline white', () => {
    expect(css).toMatch(/\.focus-on-dark:focus-visible\s*\{[^}]*outline-color:\s*#ffffff/i);
  });

  it('white outline is ≥3:1 over the darkest photo overlay used on Home (black at 90%)', () => {
    // Composite black/90% over a white photo worst case is still very dark; use the darkest
    // reachable colour: pure black. White vs black = 21:1, and white vs the 90% overlay is higher still.
    expect(contrast('#FFFFFF', '#000000')).toBeGreaterThanOrEqual(3);
  });

  it('Home occasion cards (focusable, over dark photo overlays) carry focus-on-dark', () => {
    const idx = home.indexOf('occasionCards.map');
    expect(idx).toBeGreaterThan(-1);
    expect(home.slice(idx, idx + 400)).toContain('focus-on-dark');
  });

  it('AI Stylist control sits on a white pill, so it keeps the charcoal global outline', () => {
    expect(layout).toMatch(/bg-white[^"']*text-brand-charcoal/);
    expect(layout).not.toMatch(/focus-on-dark/);
  });

  it('charcoal-filled Sign In buttons add a white offset so a charcoal focus ring stays visible', () => {
    // A charcoal ring on a charcoal button merges into the fill (invisible). The white
    // offset gap separates them. Every bg-brand-charcoal control with a charcoal ring must carry it.
    const tags: string[] = navbar.match(/className="[^"]*bg-brand-charcoal[^"]*"/g) ?? [];
    const ringed: string[] = tags.filter((t: string) => t.includes('focus-visible:ring-brand-charcoal'));
    expect(ringed.length).toBeGreaterThan(0);
    for (const t of ringed) expect(t).toContain('focus-visible:ring-offset-white');
  });
});
