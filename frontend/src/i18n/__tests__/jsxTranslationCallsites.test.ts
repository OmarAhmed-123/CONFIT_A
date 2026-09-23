/**
 * A translation call inside a quoted JSX attribute renders as TEXT.
 *
 * The defect this file prevents (found 2026-09-23, in my own earlier patch)
 * ------------------------------------------------------------------------
 * A scripted edit rewrote four JSX attributes as
 *
 *     eyebrow="{t('discover.mood_stack_title')}"     // ← a STRING literal
 *
 * instead of
 *
 *     eyebrow={t('discover.mood_stack_title')}       // ← an expression container
 *
 * React does not interpolate inside a quoted attribute: it renders the braces
 * and the call as literal characters. The Discover mood stack and the product
 * "complete the look" stack therefore displayed
 * `{t('discover.mood_stack_title')}` to shoppers.
 *
 * Why nothing else caught it
 * --------------------------
 *   * TypeScript: the file is valid JSX, and a string is a valid value for a
 *     `string` prop. `tsc` is silent.
 *   * The i18n key-parity gate: the key DOES exist in both locales. It checks
 *     that every referenced key is present, not that the reference is executed.
 *   * The browser probe DID see the placeholder text — but reported it as
 *     untranslated copy, so a self-inflicted regression was filed as technical
 *     debt. (The probe now has a dedicated `_raw_key_probe` for the shape, which
 *     was verified to detect a deliberate re-introduction.)
 *
 * This test is the cheap, always-on guard: no browser, no rendering.
 */
// Runs under the shared jsdom setup (vitest.setup.ts imports i18n, which needs a DOM).
import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SOURCE_ROOT = path.resolve(__dirname, '../../');

/** Every .ts/.tsx file under src, excluding tests. */
function sourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      sourceFiles(full, acc);
    } else if (/\.tsx?$/.test(entry.name)) {
      acc.push(full);
    }
  }
  return acc;
}

describe('JSX translation call sites are executed, not printed', () => {
  const files = sourceFiles(SOURCE_ROOT);

  it('has files to scan (a scan of nothing proves nothing)', () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it('never places a t() call inside a quoted JSX attribute value', () => {
    // attribute="… t('…') …"  →  the call is text, not code.
    const offenders: string[] = [];
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf-8');
      source.split('\n').forEach((line, i) => {
        if (/\w+="[^"]*\bt\(['"`]/.test(line) || /\w+='[^']*\bt\(['"`]/.test(line)) {
          offenders.push(`${path.relative(SOURCE_ROOT, file)}:${i + 1}: ${line.trim().slice(0, 110)}`);
        }
      });
    }
    expect(offenders, [
      'A translation call sits inside a quoted JSX attribute, so React renders',
      'the call itself as text ("{t(\'key\')}") instead of the translated string.',
      'Use an expression container: attr={t(\'key\')}.',
      ...offenders,
    ].join('\n')).toEqual([]);
  });

  it('never leaves an unresolved placeholder marker in JSX source', () => {
    // Catches the same family: a template that never got its value.
    const offenders: string[] = [];
    for (const file of files) {
      const source = fs.readFileSync(file, 'utf-8');
      for (const token of ['{{', '}}']) {
        // `{{` is legitimate in inline style objects (`style={{...}}`), so the
        // check is narrowed to the text-position shape `>{{` / `}}<`.
        const re = new RegExp(token === '{{' ? '>\\{\\{' : '\\}\\}<');
        const idx = source.search(re);
        if (idx !== -1) {
          const line = source.slice(0, idx).split('\n').length;
          offenders.push(`${path.relative(SOURCE_ROOT, file)}:${line}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
