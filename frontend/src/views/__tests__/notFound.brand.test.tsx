import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the honest 404 page (NotFoundView, catch-all route).
 *  - White page, charcoal primary CTA, charcoal focus rings (was gold #C5A059).
 *  - No navy, cream or gold chrome; no slate text (use brand-muted).
 */
const src = readFileSync(resolve(process.cwd(), 'src/views/public/NotFoundView.tsx'), 'utf8');

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /A37E44/i, /FDF8EE/i, /F3EBDD/i, /FAF9F6/i, /slate-\d+/];

describe('NotFoundView brand contract', () => {
  it('carries no legacy navy, gold, cream or slate tokens', () => {
    for (const re of LEGACY) expect(src, `still has ${re}`).not.toMatch(re);
  });

  it('page root is white', () => {
    expect(src).toMatch(/<main className="flex min-h-screen items-center justify-center bg-white/);
  });

  it('primary CTA is brand charcoal with white text', () => {
    expect(src).toMatch(/bg-brand-charcoal px-5 text-sm font-bold text-white hover:bg-\[#1A1B1D\]/);
  });

  it('focus rings are charcoal', () => {
    expect(src.match(/focus-visible:ring-brand-charcoal/g)?.length).toBe(3);
  });
});
