import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Brand contract for SharedLookView and ShareCard.
 * Both must speak the Logo #3 white-first identity:
 * - No legacy gold (#C5A059, #C9A227, #6B4F1E, #B8935A)
 * - No legacy cream (#FAF9F6, #FDF8EE)
 * - No legacy dark navy (#1B1F3B, #0C0E1E)
 * - Uses brand charcoal (#252729), brand wash (#F7F6F3), brand muted, and hairline
 */
const sharedLookSrc = readFileSync(
  resolve(process.cwd(), 'src/views/public/SharedLookView.tsx'),
  'utf8'
);
const shareCardSrc = readFileSync(
  resolve(process.cwd(), 'src/components/outfit/ShareCard.tsx'),
  'utf8'
);

const LEGACY = [/1B1F3B/i, /0C0E1E/i, /C5A059/i, /E2BF70/i, /A37E44/i, /FAF9F6/i, /C9A227/i, /6B4F1E/i, /FDF8EE/i];

describe('SharedLookView and ShareCard brand contract', () => {
  it('SharedLookView carries no legacy navy, gold or cream tokens', () => {
    for (const re of LEGACY) {
      expect(sharedLookSrc, `SharedLookView still has ${re}`).not.toMatch(re);
    }
  });

  it('ShareCard carries no legacy navy, gold or cream tokens', () => {
    for (const re of LEGACY) {
      expect(shareCardSrc, `ShareCard still has ${re}`).not.toMatch(re);
    }
  });

  it('SharedLookView uses white background and brand-charcoal text', () => {
    expect(sharedLookSrc).toMatch(/bg-white/);
    expect(sharedLookSrc).toMatch(/text-brand-charcoal/);
  });

  it('ShareCard uses white card background with brand tokens', () => {
    expect(shareCardSrc).toMatch(/background:\s*'#FFFFFF'/);
    expect(shareCardSrc).toMatch(/color:\s*'#252729'/);
  });
});
