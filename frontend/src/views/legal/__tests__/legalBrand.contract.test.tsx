import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the legal pages (Privacy, Terms, GDPR) in LegalViews.
 *  - Hero is brand charcoal with white text (no navy-to-black gradient, no gold chip).
 *  - Active tab is charcoal; inactive tabs use brand-field boundaries and brand-muted text.
 *  - Body and table-header text is brand-muted (slate-400 on white fails AA).
 *  - Neutral slate dividers and borders are allowed.
 */
const src = readFileSync(resolve(process.cwd(), 'src/views/legal/LegalViews.tsx'), 'utf8');

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /C9A227/i, /slate-(300|400|500|600|700)/];

describe('legal pages brand contract', () => {
  it('carries no legacy navy, gold or cream tokens', () => {
    for (const re of LEGACY) expect(src, `still has ${re}`).not.toMatch(re);
  });

  it('hero is brand charcoal with white text', () => {
    expect(src).toMatch(/bg-brand-charcoal rounded-3xl text-white/);
  });

  it('active tab is brand charcoal; inactive tabs use brand-field boundary', () => {
    expect(src).toMatch(/\? 'bg-brand-charcoal text-white shadow-2xs'/);
    expect(src).toMatch(/'bg-white border border-brand-field text-brand-muted hover:border-brand-charcoal'/);
  });

  it('table headers and body text use brand-muted', () => {
    expect(src).toMatch(/\[&_th\]:text-brand-muted/);
    expect(src).toMatch(/\[&_p\]:text-brand-muted/);
  });
});
