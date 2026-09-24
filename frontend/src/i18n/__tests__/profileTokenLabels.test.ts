/**
 * Profile data-token contract (style quiz + stored chips).
 *
 * WHY THIS TEST EXISTS
 * --------------------
 * The style quiz's option lists are not copy: every `value` is written into the
 * shopper's profile through the API (`style_archetypes`, `preferred_colors`,
 * `avoided_colors`, `fashion_aesthetics`, `blacklisted_brands`,
 * `occasion_weights`, `fit_preference`, `body_attributes.body_shape`) and is what
 * the recommender matches on. The 2026-09 localization batch split each option
 * into `{ value: <token>, labelKey: <i18n key> }`.
 *
 * The failure this pins down is silent in every other gate:
 *   * translating a value does not throw;
 *   * it does not fail TypeScript (both are strings);
 *   * it does not fail the i18n parity gate;
 *   * it does not fail an English-only test run.
 * It would simply write Arabic into a matched field, and existing English
 * profiles would stop matching. So both directions are asserted here: the token
 * stays English, and the label is genuinely Arabic.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import en from '../en.json';
import ar from '../ar.json';

const SRC = path.resolve(__dirname, '../..');
const VIEW = fs.readFileSync(path.join(SRC, 'views/consumer/UserProfileView.tsx'), 'utf8');

const ARABIC = /[\u0600-\u06FF]/;

/**
 * The option table is declared at module scope in the view itself, so this test
 * reads the SHIPPED source and has no dependency on any scratch file.
 * (`{ value: 'X', labelKey: 'profile.y' }`.)
 */
if (!VIEW.includes('export const PROFILE_OPTIONS')) {
  throw new Error('PROFILE_OPTIONS not found in UserProfileView.tsx — the table moved');
}
const raw = VIEW.slice(VIEW.indexOf('export const PROFILE_OPTIONS'), VIEW.indexOf('export const UserProfileView'));

type Pair = { value: string; labelKey: string };
const PAIRS: Pair[] = [...raw.matchAll(/\{\s*value:\s*'([^']*)',\s*labelKey:\s*'([^']+)'\s*\}/g)].map(
  (m) => ({ value: m[1], labelKey: m[2] }),
);

function leaf(bundle: unknown, key: string): string | undefined {
  return key.split('.').reduce<any>((node, part) => node?.[part], bundle) as string | undefined;
}

describe('style-quiz option values stay English while their labels localize', () => {
  it('finds every token/label pair (guards against regex rot)', () => {
    // 6 archetypes + 9 colours + 6 avoid + 10 aesthetics + 6 shapes + 4 fits
    // + 6 occasions + 4 blacklist = 51
    expect(PAIRS).toHaveLength(51);
  });

  it.each(PAIRS)('$labelKey: en label is byte-identical to the stored token', ({ value, labelKey }) => {
    expect(leaf(en, labelKey)).toBe(value);
  });

  it.each(PAIRS)('$labelKey: the stored value is never Arabic', ({ value }) => {
    expect(ARABIC.test(value)).toBe(false);
  });

  it.each(PAIRS)('$labelKey: the Arabic label exists and is a real translation', ({ labelKey, value }) => {
    const arabic = leaf(ar, labelKey);
    expect(arabic, `${labelKey} missing from ar.json`).toBeTruthy();
    expect(ARABIC.test(arabic as string)).toBe(true);
    expect(arabic).not.toBe(value);
  });

  it('every option is rendered through labelKey, never the raw token', () => {
    for (const expr of [
      '{t(arch.labelKey)}',
      '{t(col.labelKey)}',
      '{t(a.labelKey)}',
      '{t(f.labelKey)}',
      '{t(occ.labelKey)}',
      '{t(b.labelKey)}',
      '{t(s.labelKey)}',
    ]) {
      expect(VIEW).toContain(expr);
    }
  });

  it('selection state carries the TOKEN, so saved profiles keep matching', () => {
    expect(VIEW).toContain('setArchetypes([...archetypes, arch.value])');
    expect(VIEW).toContain('setColors([...colors, col.value])');
    expect(VIEW).toContain('setAvoidedColors');
    expect(VIEW).toContain('avoidedColors.includes(col.value)');
    expect(VIEW).toContain('setAesthetics(aesthetics.includes(a.value)');
    expect(VIEW).toContain('setFitPref(f.value)');
    expect(VIEW).toContain('fitPref === f.value');
    expect(VIEW).toContain('setOccasionWeights({ ...occasionWeights, [occ.value]');
    expect(VIEW).toContain('setBlacklistedBrands');
  });

  it('the shape <option> keeps an English value with a localized label', () => {
    expect(VIEW).toContain('<option key={s.value} value={s.value}>{t(s.labelKey)}</option>');
  });

  it('stored chips resolve a label but fall back to the raw token', () => {
    // An unknown or free-form stored value must still render, never blank.
    expect(VIEW).toContain("labelKeyFor('archetypes', a)");
    expect(VIEW).toContain("labelKeyFor('colors', c)");
    expect(VIEW).toContain("labelKeyFor('shapes', usp.body_shape_tag)");
    expect(VIEW).toContain("labelKeyFor('fits', usp.fit_preference)");
  });

  it('HONESTY: no fabricated body values when the shopper never entered them', () => {
    // The card used to render `{...?.height_cm || 178} cm` — "178 cm" for a
    // shopper who entered nothing. The view's own onboarding rule forbids
    // fabricated body data, so the fallback must be an explicit not-set label.
    //
    // The first version of this assertion listed the three exact old strings and
    // let a mutation through: re-adding `|| 'Athletic'` to the *new* expression
    // passed, because it is not the old text. The rule is therefore stated as a
    // PATTERN over the whole body-attributes region: no `|| '<literal>'` default
    // for a body value may appear there at all.
    const region = VIEW.slice(VIEW.indexOf("profile.height_weight"), VIEW.indexOf("profile.delete_my_measurements"));
    expect(region.length).toBeGreaterThan(200);          // the slice must be real
    expect(region).not.toMatch(/\|\|\s*['"][^'"]+['"]/);  // no literal default
    expect(region).toContain("t('profile.not_set')");     // and an explicit one
  });

  it('money on this screen goes through the locale formatter', () => {
    expect(VIEW).not.toMatch(/\$\{usp\.budget/);
    expect(VIEW).not.toMatch(/\$\{budgetMonthlyMin/);
    expect(VIEW).toContain('formatMoney(');
  });
});
