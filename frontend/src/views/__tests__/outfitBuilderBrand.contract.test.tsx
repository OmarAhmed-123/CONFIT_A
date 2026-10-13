import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for OutfitBuilderView.
 * - No legacy navy, gold or cream tokens.
 * - Uses brand charcoal, brand wash, and proper focus ring.
 */
const src = readFileSync(
  resolve(process.cwd(), 'src/views/consumer/OutfitBuilderView.tsx'),
  'utf8'
);

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /C9A227/i, /B8935A/i, /FDF8EE/i];

describe('OutfitBuilderView brand contract', () => {
  it('carries no legacy navy, gold or cream tokens', () => {
    for (const re of LEGACY) {
      expect(src, `still has ${re}`).not.toMatch(re);
    }
  });

  it('uses brand focus ring token', () => {
    expect(src).toMatch(/focus-visible:ring-brand-charcoal/);
  });

  it('uses brand charcoal for headings and CTAs', () => {
    expect(src).toMatch(/text-brand-charcoal/);
    expect(src).toMatch(/bg-brand-charcoal/);
  });
});
