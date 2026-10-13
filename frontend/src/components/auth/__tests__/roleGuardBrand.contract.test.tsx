import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for RoleGuard.
 * Must speak the Logo #3 white-first identity:
 * - No legacy gold (#C5A059, #C9A227, #6B4F1E, #B8935A, #E2BF70)
 * - No legacy cream (#FAF9F6, #FDF8EE)
 * - No legacy dark navy (#1B1F3B, #0C0E1E)
 * - White card background with brand charcoal text and CTAs
 */
const src = readFileSync(
  resolve(process.cwd(), 'src/components/auth/RoleGuard.tsx'),
  'utf8'
);

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /C9A227/i, /B8935A/i, /FDF8EE/i];

describe('RoleGuard brand contract', () => {
  it('carries no legacy navy, gold or cream tokens', () => {
    for (const re of LEGACY) {
      expect(src, `RoleGuard still has ${re}`).not.toMatch(re);
    }
  });

  it('uses white card surface and brand charcoal text and CTA', () => {
    expect(src).toMatch(/bg-white text-brand-charcoal/);
    expect(src).toMatch(/bg-brand-charcoal hover:bg-black text-white/);
  });
});
