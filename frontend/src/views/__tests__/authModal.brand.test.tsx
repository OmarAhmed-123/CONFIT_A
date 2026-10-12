import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the auth surface (Logo #3 rollout, page 1 of auth/account).
 *  - No legacy navy / gold / cream / slate-950 tokens remain in the modal or
 *    in the shared auth field/button styles used by the public auth views.
 *  - Primary action is charcoal (#252729) with white text (14.99:1).
 *  - Interactive text links are charcoal and underlined by default, not gold
 *    (gold #C5A059 on white is 2.46:1, below the 4.5:1 text minimum).
 *  - The banner uses the official mark on a white surface (theme="dark").
 *  - Brand tokens exist in tailwind.config.js and match the reference colours.
 */

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');

const modal = read('src/views/auth/AuthModal.tsx');
const styles = read('src/components/auth/authStyles.ts');
const tailwind = read('tailwind.config.js');

const LEGACY = [/C5A059/i, /1B1F3B/i, /FDF8EE/i, /FAF9F6/i, /0C0E1E/i, /slate-950/, /backdrop-blur/];

describe('AuthModal brand contract', () => {
  it('carries no legacy navy/gold/cream tokens', () => {
    for (const re of LEGACY) expect(modal, `modal still has ${re}`).not.toMatch(re);
  });

  it('shared auth styles are charcoal-based with no legacy tokens', () => {
    for (const re of LEGACY) expect(styles, `authStyles still has ${re}`).not.toMatch(re);
    expect(styles).toMatch(/bg-brand-charcoal/);
    expect(styles).toMatch(/border-brand-field/);
  });

  it('primary action is charcoal with a visible focus ring', () => {
    expect(styles).toMatch(/bg-brand-charcoal px-5 text-sm font-bold text-white/);
    expect(styles).toMatch(/focus-visible:ring-brand-charcoal/);
  });

  it('interactive text links are charcoal and underlined by default', () => {
    const links = modal.match(/text-brand-charcoal font-bold underline underline-offset-4/g) ?? [];
    expect(links.length).toBe(4);
  });

  it('banner uses the official mark on white, not on navy', () => {
    expect(modal).toMatch(/bg-white flex justify-between items-center border-b border-brand-hairline/);
    expect(modal).toMatch(/<ConfitLogo variant="compact" theme="dark" size="md" \/>/);
  });

  it('keeps the auth logic surface: heading, live region and dialog semantics', () => {
    expect(modal).toMatch(/role="dialog"/);
    expect(modal).toMatch(/aria-modal="true"/);
    expect(modal).toMatch(/id="auth-modal-heading"/);
    expect(modal).toMatch(/role="status"\s+aria-live="polite"/);
  });
});

describe('Brand tokens', () => {
  it('defines the official reference colours and documents the text-contrast rule', () => {
    expect(tailwind).toMatch(/coral: '#EF826D'/);
    expect(tailwind).toMatch(/lilac: '#A99AD6'/);
    expect(tailwind).toMatch(/mint: '#89B799'/);
    expect(tailwind).toMatch(/charcoal: '#252729'/);
    expect(tailwind).toMatch(/field: '#8A8D93'/);
    expect(tailwind).toMatch(/Accents[\s\S]*fills and indicators only/);
  });
});
