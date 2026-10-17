import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for the email-landing account pages (VerifyEmail, ResetPassword,
 * EmailUnsubscribe) and their shared AuthPageShell. Source-level checks: the
 * behaviour of these pages is covered by accountRecoveryPages.test.tsx.
 *  - No legacy cream/navy/gold tokens remain on these pages or the shell.
 *  - White-first page surface; charcoal headings and labels.
 *  - Interactive text links are charcoal and underlined by default (gold-dark
 *    #A37E44 was 3.73:1 on white and gold #C5A059 2.46:1, both below 4.5:1 for text).
 *  - Semantic colours (emerald success, rose error) are preserved.
 */

const root = process.cwd();
const read = (p: string) => readFileSync(resolve(root, p), 'utf8');
const FILES = [
  'src/components/auth/AuthPageShell.tsx',
  'src/views/public/VerifyEmailView.tsx',
  'src/views/public/ResetPasswordView.tsx',
  'src/views/public/EmailUnsubscribeView.tsx',
];
const LEGACY = [/C5A059/i, /1B1F3B/i, /FDF8EE/i, /A37E44/i, /FAF9F6/i];

describe('account pages brand contract', () => {
  for (const f of FILES) {
    it(`${f} has no legacy navy/gold/cream tokens`, () => {
      const s = read(f);
      for (const re of LEGACY) expect(s, `${f} still has ${re}`).not.toMatch(re);
    });
  }

  it('AuthPageShell is white-first with a hairline card', () => {
    const s = read('src/components/auth/AuthPageShell.tsx');
    expect(s).toMatch(/<main className="min-h-screen bg-white px-4 py-14">/);
    expect(s).toMatch(/border-brand-hairline/);
  });

  it('page headings are charcoal', () => {
    for (const f of FILES.slice(1)) {
      const s = read(f);
      const h1 = s.match(/<h1 className="([^"]+)"/g) ?? [];
      expect(h1.length, `${f} has h1`).toBeGreaterThan(0);
      for (const h of h1) expect(h).toMatch(/text-brand-charcoal/);
    }
  });

  it('text links are charcoal and underlined by default', () => {
    const s = read('src/views/public/ResetPasswordView.tsx') + read('src/views/public/EmailUnsubscribeView.tsx');
    const links = s.match(/font-bold text-brand-charcoal underline underline-offset-4 decoration-brand-field/g) ?? [];
    expect(links.length).toBe(2);
  });

  it('semantic success and error colours are preserved', () => {
    expect(read('src/views/public/VerifyEmailView.tsx')).toMatch(/text-emerald-700/);
    expect(read('src/views/public/VerifyEmailView.tsx')).toMatch(/text-rose-600/);
    expect(read('src/views/public/ResetPasswordView.tsx')).toMatch(/bg-emerald-50/);
  });
});
