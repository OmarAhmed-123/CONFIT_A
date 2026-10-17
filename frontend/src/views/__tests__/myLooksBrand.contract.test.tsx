/**
 * Logo #3 brand contract for My Looks (/my-looks, /outfits).
 *
 * Source-level checks, same style as productDetailBrand.contract.test.tsx.
 * Semantic status colours stay: amber (partial look, missing slots), rose (delete).
 * Behaviour is covered by useMyLooksViewModel.test.tsx and tryOnGateCoverage.test.tsx.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import i18n, { setAppLanguage } from '../../i18n/i18n';

const read = (rel: string) => readFileSync(resolve(__dirname, rel), 'utf8');
const strip = (src: string) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((l) => !/^\s*\/\//.test(l))
    .join('\n');

const VIEW = strip(read('../consumer/MyLooksView.tsx'));
const TRYON = strip(read('../../components/product/TryOnButton.tsx'));

describe('MyLooksView brand contract (Logo #3)', () => {
  it('has no legacy navy, gold, cream, or slate chrome in code', () => {
    for (const legacy of ['#1B1F3B', '#0C0E1E', '#C5A059', '#A37E44', '#7A5C28', '#FDF8EE', 'text-slate-950']) {
      expect(VIEW, legacy).not.toContain(legacy);
    }
    expect(VIEW).not.toMatch(/\bslate-\d{2,3}\b/);
  });

  it('primary CTAs are charcoal with a charcoal focus ring', () => {
    expect(VIEW).toContain('bg-brand-charcoal hover:bg-[#1A1B1D] text-white font-bold text-xs flex items-center gap-1.5 focus-visible:outline-brand-charcoal');
    expect(VIEW).toContain('bg-brand-charcoal hover:bg-[#1A1B1D] text-white text-xs font-bold transition-all focus-visible:outline-brand-charcoal');
  });

  it('semantic statuses are kept (amber partial look, rose delete)', () => {
    expect(VIEW).toContain('text-amber-700');
    expect(VIEW).toMatch(/text-rose-700/);
  });
});

describe('TryOnButton brand contract (shared primitive)', () => {
  it('no legacy navy, gold, or cream in code', () => {
    for (const legacy of ['#1B1F3B', '#C5A059', '#7A5C28', '#FDF8EE', 'text-slate-950']) {
      expect(TRYON, legacy).not.toContain(legacy);
    }
  });

  it('overlay and outline variants use charcoal and white', () => {
    expect(TRYON).toContain('bg-brand-charcoal/90');
    expect(TRYON).toContain('text-brand-charcoal hover:bg-brand-charcoal hover:text-white');
  });
});

describe('My Looks piece count is pluralised per locale', () => {
  it('EN: 1 piece, 2 pieces', async () => {
    await setAppLanguage('en');
    expect(i18n.t('my_looks.pieces', { count: 1 })).toBe('piece');
    expect(i18n.t('my_looks.pieces', { count: 2 })).toBe('pieces');
  });

  it('AR: one, two, and few forms are distinct', async () => {
    await setAppLanguage('ar');
    expect(i18n.t('my_looks.pieces', { count: 1 })).toBe('قطعة');
    expect(i18n.t('my_looks.pieces', { count: 2 })).toBe('قطعتان');
    expect(i18n.t('my_looks.pieces', { count: 5 })).toBe('قطع');
    await setAppLanguage('en');
  });
});
