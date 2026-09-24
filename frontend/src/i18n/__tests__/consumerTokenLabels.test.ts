/**
 * Data-token vs display-label contract (consumer Home + Discover).
 *
 * WHY THIS TEST EXISTS
 * --------------------
 * DiscoverView's palette swatches and occasion chips, and HomeView's guided-look
 * options, are not ordinary strings. Each one is a *data token*:
 *
 *   - `product.color_family` is matched by `includes(col.value)`     (Discover)
 *   - `product.occasion_tags` is matched by `includes(o.value)`      (Discover)
 *   - `occasion=` / `palette` / `preferred_fit` are sent to the       (Home)
 *     stylist endpoint, after being looked up in paletteMap/fitMap
 *
 * So the same literal serves two masters: what the shopper READS (translatable)
 * and what the code MATCHES/SENDS (must stay the English catalogue token). The
 * 2026-09 localization pass split them into `{ value, labelKey }`.
 *
 * The failure mode this pins down is silent: translating `value` would not throw,
 * would not fail TypeScript, and would not fail the i18n parity gate — it would
 * simply return zero products for Arabic shoppers, and would send an Arabic
 * occasion string to an API that expects `Work`.
 *
 * These assertions are deliberately strict about the pair shape. If someone
 * "helpfully" translates a value, `en[labelKey] === value` breaks here.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import en from '../en.json';
import ar from '../ar.json';

const SRC = path.resolve(__dirname, '../..');
const FILES = {
  discover: fs.readFileSync(path.join(SRC, 'views/consumer/DiscoverView.tsx'), 'utf8'),
  home: fs.readFileSync(path.join(SRC, 'views/consumer/HomeView.tsx'), 'utf8'),
};

type Pair = { file: string; value: string; labelKey: string };

  /**
 * `{ value: "Work", labelKey: "discover.occasion_work" }` — and the palette
 * entries, which carry a trailing `hex: "…"` field, so the closing brace is
 * deliberately not part of the pattern (the first version of this regex found
 * 19 of 25 pairs and failed the count check instead of passing vacuously).
 */
function readPairs(name: string, source: string): Pair[] {
  const re = /\{\s*value:\s*"([^"]*)",\s*labelKey:\s*"([^"]+)"/g;
  return [...source.matchAll(re)].map((m) => ({ file: name, value: m[1], labelKey: m[2] }));
}

const PAIRS = [...readPairs('discover', FILES.discover), ...readPairs('home', FILES.home)];

const ARABIC = /[\u0600-\u06FF]/;

function leaf(bundle: unknown, key: string): string | undefined {
  return key.split('.').reduce<any>((node, part) => node?.[part], bundle) as string | undefined;
}

describe('consumer data tokens stay English while their labels localize', () => {
  it('finds the full set of token/label pairs (guards against regex rot)', () => {
    // 6 palette + 5 occasion in Discover; 6 occasion + 4 palette + 4 fit in Home.
    expect(PAIRS).toHaveLength(25);
  });

  it.each(PAIRS.filter((p) => p.value !== ''))(
    '$labelKey: en value is byte-identical to the token it labels',
    ({ labelKey, value }) => {
      // English copy is frozen: the label shown in English IS the token. Any copy
      // edit that changes one without the other lands here.
      expect(leaf(en, labelKey)).toBe(value);
    },
  );

  it('the empty-value sentinel is exactly one entry, and it is the "All" chip', () => {
    // `{ value: "" }` is the no-filter sentinel: DiscoverView treats "" as
    // "no palette constraint" (falsy check), so the English label is not the
    // value here. Pinned so it stays a documented exception, not a hole.
    const empties = PAIRS.filter((p) => p.value === '');
    expect(empties).toHaveLength(1);
    expect(empties[0].labelKey).toBe('discover.filter_all');
    expect(leaf(en, 'discover.filter_all')).toBe('All');
    expect(leaf(ar, 'discover.filter_all')).toBe('الكل');
  });

  it.each(PAIRS)('$labelKey: the value is an English catalogue token, never Arabic', ({ value }) => {
    // The sharp end of the guard: a translated `value` would break filtering
    // (silently, for Arabic shoppers only) and would send Arabic to the API.
    expect(ARABIC.test(value)).toBe(false);
    expect(value.trim()).toBe(value);
  });

  it.each(PAIRS)('$labelKey: Arabic label exists and is a real translation', ({ labelKey, value }) => {
    const arabic = leaf(ar, labelKey);
    expect(arabic, `${labelKey} missing from ar.json`).toBeTruthy();
    expect(ARABIC.test(arabic as string)).toBe(true);
    // Not a copy of the English token: the shopper must not read English here.
    expect(arabic).not.toBe(value);
  });

  it('Display: every render path goes through labelKey, never the raw token', () => {
    expect(FILES.discover).toContain('{t(col.labelKey)}');
    expect(FILES.discover).toContain('{t(occasion.labelKey)}');
    expect(FILES.home).toContain('{t(palette.labelKey)}');
    expect(FILES.home).toContain('{t(fit.labelKey)}');
    expect(FILES.home).toContain('{t(occasion.labelKey)}');
    // the pre-split forms must be gone
    expect(FILES.discover).not.toContain('{col.label}');
    expect(FILES.discover).not.toContain('{occasion}');
  });

  it('Matching: selected state carries the TOKEN, so filters keep working in Arabic', () => {
    expect(FILES.discover).toContain('setSelectedColor(col.value)');
    expect(FILES.discover).toContain('selectedColor === col.value');
    expect(FILES.discover).toContain('setSelectedOccasion(occasion.value)');
    expect(FILES.discover).toContain('selectedOccasion === occasion.value');
    expect(FILES.home).toContain('setGuideOccasion(occasion.value)');
    expect(FILES.home).toContain('guideOccasion === occasion.value ?');
    // the comparison must not fall back to the array element (the bug shape)
    expect(FILES.home).not.toMatch(/guideOccasion === occasion\b(?!\.value)/);
  });

  it('Taxonomy: Arabic category names come from the API field, once the UI is Arabic', () => {
    // The categories endpoint already shipped `name_ar`; the screen ignored it.
    expect(FILES.discover).toContain('cat.name_ar');
    expect(FILES.discover).toContain('{categoryLabel(cat)}');
    expect(FILES.discover).toContain('isArabic && cat.name_ar ? cat.name_ar : cat.name');
  });

  it('Money and numbers go through the locale formatters, not hand-built strings', () => {
    // `${p.base_price}` / `{prod.currency} {price.toFixed(2)}` rendered Latin
    // digits and a bare "$" inside the Arabic RTL page.
    expect(FILES.discover).not.toMatch(/\$\{p\.base_price\}/);
    expect(FILES.home).not.toMatch(/\$\{p\.base_price\}/);
    expect(FILES.home).not.toContain('{prod.currency} {prod.base_price.toFixed(2)}');
    expect(FILES.discover).toContain('formatMoney(');
    expect(FILES.home).toContain('formatMoney(');
  });
});
