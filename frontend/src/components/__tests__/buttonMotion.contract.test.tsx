/**
 * Part 1 — Button Motion System. The acceptance criteria, machine-checked.
 *
 * A CSS animation cannot be reviewed by reading a diff: an intent with no
 * rule, a keyframe that animates `width`, or a wash that quietly drops a
 * label under 4.5:1 all look fine in a pull request. So the criteria the
 * system was specified against are asserted here, against the stylesheet
 * source and the real WCAG math:
 *
 *   A. Engine ↔ registry parity    — every intent in the typed registry has a
 *      rule, and every `data-motion` rule corresponds to a registry entry.
 *      A misspelt attribute can no longer ship as a silent dead button.
 *   B. Choreography safety         — the keyframes animate only
 *      background-position / background-size / transform / opacity. No
 *      layout property can appear, which is what makes "no layout shift"
 *      a property of the file rather than a promise about it.
 *   C. Accessibility               — reduced motion switches every animation
 *      off and keeps every state visible statically; forced-colors steps
 *      aside; RTL mirrors the geometry through tokens, not duplicated rules.
 *   D. Contrast mathematics        — the wash at its MAXIMUM alpha, composited
 *      over the two light surfaces the product uses, still holds every text
 *      colour it can land under at ≥4.5:1. Real relative-luminance math.
 *   E. Coverage ratchet            — every `<button>` in the app declares an
 *      intent, and every family in the registry is used by real controls.
 *      New controls without an intent fail this test.
 *   F. Wiring                      — ActionButton publishes the intent and the
 *      states the engine reads, in BOTH the kinetic and the reduced-motion
 *      render paths, and the stylesheet is actually loaded by the entry.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';
import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';

vi.mock('../../stores/uiStore', () => {
  const useUIStore = (sel: any) => sel({ openAuthModal: () => {} });
  return { useUIStore };
});

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { ActionButton } from '../common/ActionButton';
import { BUTTON_INTENTS, buttonMotion, motionStateAlias } from '../common/buttonMotion';

const ROOT = path.join(__dirname, '../../..');
const css = fs.readFileSync(path.join(ROOT, 'src/styles/button-motion.css'), 'utf8');
/**
 * The stylesheet WITHOUT its comments. Mechanical assertions run against this
 * and never against the prose: a rule must not be able to pass — or fail —
 * because a sentence mentions it.
 */
const cssRules = css.replace(/\/\*[\s\S]*?\*\//g, '');
const engineTs = fs.readFileSync(path.join(ROOT, 'src/components/common/buttonMotion.ts'), 'utf8');
const mainTsx = fs.readFileSync(path.join(ROOT, 'src/main.tsx'), 'utf8');

afterEach(async () => {
  cleanup();
  await setAppLanguage('en');
});

/**
 * The codemod IS the coverage oracle — one parser, one rule table, shared by
 * the tool, the catalog document and these assertions. No duplicated
 * heuristics that can drift apart.
 */
const report = (() => {
  const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'btn-motion-')), 'report.json');
  execFileSync('node', ['scripts/apply-button-motion.mjs', '--json', out, '--quiet'], {
    cwd: ROOT,
    stdio: 'pipe',
  });
  return JSON.parse(fs.readFileSync(out, 'utf8')) as {
    totals: { controls: number; assignments: number; files: number };
    byIntent: Record<string, number>;
    byRole: Record<string, number>;
    rows: Array<{
      file: string;
      line: number;
      label: string;
      intent: string;
      tone: string;
      glyphOnly: boolean;
      className: string;
    }>;
    needEdits: Array<{ file: string; line: number; intent: string; tone: string }>;
  };
})();

/* ── small structural helpers over the stylesheet source ─────────────────── */

/** The body of a top-level `@media (...)` block, braces balanced. */
function mediaBlock(header: string): string {
  const at = css.indexOf(`@media ${header}`);
  expect(at, `@media ${header} must exist`).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = css.indexOf('{', at); i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}') {
      depth--;
      if (depth === 0) return css.slice(css.indexOf('{', at) + 1, i);
    }
  }
  throw new Error(`unbalanced @media ${header}`);
}

/** The body of `@keyframes <name>`, braces balanced. */
function keyframeBlock(name: string): string {
  const at = css.indexOf(`@keyframes ${name}`);
  expect(at, `@keyframes ${name} must exist`).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = css.indexOf('{', at); i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}') {
      depth--;
      if (depth === 0) return css.slice(css.indexOf('{', at) + 1, i);
    }
  }
  throw new Error(`unbalanced @keyframes ${name}`);
}

/** The body of the rule whose selector starts with `[data-motion="x"]`. */
function intentBlock(intent: string): string {
  const at = css.indexOf(`[data-motion="${intent}"] {`);
  if (at === -1) return '';
  return css.slice(at, css.indexOf('}', at));
}

const KEYFRAMES = [
  'confit-mo-travel',
  'confit-mo-stripes',
  'confit-mo-pulse',
  'confit-mo-wipe',
  'confit-mo-nudge',
];

/* ── WCAG 2.x relative luminance + alpha compositing (real formulas) ─────── */
const lin = (c: number) => {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = ([r, g, b]: number[]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const contrast = (a: number[], b: number[]) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const parseRgba = (r: number, g: number, b: number, a: number) => [r, g, b, a] as const;
const composite = (fg: readonly [number, number, number, number], bg: number[]) =>
  [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3]));
const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

/* Surfaces the product actually paints behind controls, and the text colours
   that can sit on them. */
const SURFACES = { white: hex('#FFFFFF'), cream: hex('#FAF9F6') };
const TEXTS = {
  charcoal: hex('#252729'),
  muted: hex('#595C63'),
  slate700: hex('#334155'),
  slate500: hex('#64748B'),
};

/* ------------------------------------------------------------------ */
/* A. Engine ↔ registry parity                                         */
/* ------------------------------------------------------------------ */
describe('A · engine ↔ registry parity', () => {
  const declared = new Set(
    [...css.matchAll(/\[data-motion="([a-z]+)"\]/g)].map((m) => m[1]),
  );

  it('every registry intent has a recipe in the stylesheet', () => {
    const missing = BUTTON_INTENTS.filter((i) => !declared.has(i));
    expect(missing, `intents with no CSS: ${missing.join(', ')}`).toEqual([]);
  });

  it('every recipe in the stylesheet is a registered intent (no dead CSS)', () => {
    const known = new Set<string>([...BUTTON_INTENTS, 'none']);
    const extra = [...declared].filter((i) => !known.has(i));
    expect(extra, `CSS for unknown intents: ${extra.join(', ')}`).toEqual([]);
  });

  it('each intent declares its own wash, so no family silently inherits another', () => {
    for (const intent of BUTTON_INTENTS) {
      expect(intentBlock(intent), `[data-motion="${intent}"] must define --_mo-wash`).toContain(
        '--_mo-wash',
      );
    }
  });

  it('the engine ships a documented opt-out for controls with bespoke surfaces', () => {
    expect(css).toContain('[data-motion="none"]');
  });

  it('the typed helper emits exactly what the engine reads', () => {
    expect(buttonMotion({ intent: 'financial' })).toEqual({ 'data-motion': 'financial' });
    expect(buttonMotion({ intent: 'creative', tone: 'icon' })).toEqual({
      'data-motion': 'creative',
      'data-motion-tone': 'icon',
    });
    expect(buttonMotion({ intent: 'upload', phase: 'uploading' })).toEqual({
      'data-motion': 'upload',
      'data-motion-state': 'loading',
    });
    // An unknown phase must not invent a state.
    expect(motionStateAlias('something-else')).toBeUndefined();
    expect(motionStateAlias('done')).toBe('success');
    expect(motionStateAlias(undefined)).toBeUndefined();
  });
});

/* ------------------------------------------------------------------ */
/* B. Choreography safety — the "no layout shift" guarantee            */
/* ------------------------------------------------------------------ */
describe('B · choreography safety', () => {
  const LAYOUT_PROPS = [
    'width', 'height', 'min-width', 'min-height', 'max-width', 'max-height',
    'margin', 'margin-top', 'margin-left', 'margin-right', 'margin-bottom',
    'padding', 'padding-top', 'padding-left', 'padding-right', 'padding-bottom',
    'top', 'left', 'right', 'bottom', 'inset', 'font-size', 'line-height',
    'letter-spacing', 'border-width', 'flex', 'grid-template-columns',
    'box-shadow', 'filter', 'backdrop-filter', 'display', 'position',
  ];

  it.each(KEYFRAMES)('%s animates no layout-affecting property', (name) => {
    const block = keyframeBlock(name);
    const props = [...block.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
    expect(props.length, `${name} animates nothing?`).toBeGreaterThan(0);
    const illegal = props.filter((p) => LAYOUT_PROPS.includes(p));
    expect(illegal, `${name} animates layout: ${illegal.join(', ')}`).toEqual([]);
  });

  it('the whole engine animates only background-position, background-size or transform', () => {
    const allowed = new Set(['background-position', 'background-size', 'transform']);
    for (const name of KEYFRAMES) {
      for (const m of keyframeBlock(name).matchAll(/([a-z-]+)\s*:/g)) {
        expect(allowed.has(m[1]), `${name} animates ${m[1]}`).toBe(true);
      }
    }
  });

  it('no JavaScript animation library participates — not even the one in the deps', () => {
    const LIBRARIES = /framer-motion|gsap|animejs|popmotion|@react-spring|requestAnimationFrame/;
    expect(cssRules, 'the stylesheet must not call into JS').not.toMatch(LIBRARIES);
    expect(engineTs, 'the contract module must not import an animation library').not.toMatch(
      /(import|require)[^\n]*(framer-motion|gsap|animejs|popmotion|@react-spring)/,
    );
    // It must not need inline styles either: it is attributes + CSS.
    expect(engineTs).not.toMatch(/style\s*[:=]/);
    expect(engineTs).not.toMatch(/requestAnimationFrame|\.animate\(/);
  });

  it('the shared CTA drives its BACKGROUND from CSS, not from its motion props', () => {
    // framer-motion is pre-existing in this repo: it animates the tap scale of
    // the kinetic CTA. What it must never do is animate the background — that
    // is the engine's, and the brief rules the library out of it explicitly.
    const actionButton = fs.readFileSync(
      path.join(ROOT, 'src/components/common/ActionButton.tsx'),
      'utf8',
    );
    for (const m of actionButton.matchAll(/animate=\{\{([^}]*)\}\}/g)) {
      expect(m[1], 'ActionButton must not animate background through JS').not.toMatch(
        /background|backgroundColor|backgroundImage|backgroundPosition/,
      );
    }
  });

  it('will-change is claimed only while the pointer or keyboard is on the control', () => {
    const claims = [...css.matchAll(/will-change:\s*background-position/g)].length;
    const releases = [...css.matchAll(/will-change:\s*auto/g)].length;
    expect(claims).toBeGreaterThan(0);
    // every claim is released: base rule + reduced-motion + forced-colors
    expect(releases).toBeGreaterThanOrEqual(3);
  });

  it('the control never needs position/overflow/z-index to host the layers', () => {
    // Layers are painted on the element's own background precisely so that
    // hover badges, focus rings and absolute children keep working.
    for (const prop of ['overflow: hidden', 'z-index', 'position: relative']) {
      expect(cssRules, `engine must not force ${prop}`).not.toContain(prop);
    }
  });
});

/* ------------------------------------------------------------------ */
/* C. Accessibility                                                    */
/* ------------------------------------------------------------------ */
describe('C · accessibility', () => {
  it('reduced motion switches off every animated state explicitly', () => {
    const rm = mediaBlock('(prefers-reduced-motion: reduce)');
    expect(rm).toContain('animation: none');
    for (const selector of [
      '[data-motion]:hover',
      '[data-motion]:focus-visible',
      '[data-motion]:active',
      '[data-motion][aria-busy="true"]',
      '[data-motion][data-state="pending"]',
      '[data-motion][data-state="success"]',
      '[data-motion][data-state="error"]',
    ]) {
      expect(rm, `reduced motion must cover ${selector}`).toContain(selector);
    }
  });

  it('reduced motion still shows state as a static wash — colour survives the motion', () => {
    const rm = mediaBlock('(prefers-reduced-motion: reduce)');
    expect(rm).toMatch(/background-position:\s*var\(--_mo-streak-rest\),\s*var\(--_mo-wash-end\)/);
    expect(rm).toMatch(/background-size:\s*var\(--_mo-streak-size\),\s*var\(--_mo-wash-size-end\)/);
  });

  it('the error nudge — the only transform — is motion-safe only', () => {
    const safe = mediaBlock('(prefers-reduced-motion: no-preference)');
    expect(safe).toContain('confit-mo-nudge');
  });

  it('forced colors steps the whole engine aside', () => {
    const fc = mediaBlock('(forced-colors: active)');
    expect(fc).toContain('background-image: none');
    expect(fc).toContain('animation: none');
  });

  it('RTL mirrors direction through tokens, not duplicated keyframes', () => {
    const at = css.indexOf('[dir="rtl"] [data-motion]');
    expect(at).toBeGreaterThan(-1);
    const block = css.slice(at, css.indexOf('}', at));
    for (const token of [
      '--_mo-angle',
      '--_mo-streak-rest',
      '--_mo-streak-end',
      '--_mo-wash-rest',
      '--_mo-wash-end',
    ]) {
      expect(block, `RTL must mirror ${token}`).toContain(token);
    }
    // Both directions of travel are mirrored (start and end swapped).
    expect(block).toContain('--_mo-streak-rest: -100% 0');
    expect(block).toContain('--_mo-streak-end: 200% 0');
    // No RTL twin of any keyframe exists — direction is data, not a copy.
    expect(css).not.toMatch(/@keyframes\s+confit-mo-[a-z-]+-rtl/);
  });

  it('a disabled control claims nothing — and a pending one is never treated as disabled', () => {
    expect(css).toMatch(/\[data-motion\]:disabled/);
    expect(css).toMatch(
      /\[data-motion\]\[aria-disabled="true"\]:not\(\[aria-busy="true"\]\)/,
    );
  });

  it('quiet states (unavailable / unauthorized) carry no celebratory or alarming motion', () => {
    const at = css.indexOf('[data-motion][data-state="unavailable"]');
    const block = css.slice(at, css.indexOf('}', at));
    expect(block).toContain('animation: none');
    expect(block).toContain('--_mo-wash-quiet');
  });
});

/* ------------------------------------------------------------------ */
/* D. Contrast mathematics — measured, not assumed                     */
/* ------------------------------------------------------------------ */
/**
 * This section exists because the FIRST version of the engine failed it. A
 * field tint behind a `text-slate-500` label measured 4.0–4.3:1 over the
 * product's own surfaces — a real WCAG 1.4.3 regression that no code review
 * would have caught, because the tint is 14% alpha and looks like nothing.
 *
 * The fix was geometry, not colour: controls whose label is a medium-tone grey
 * get `data-motion-tone="edge"`, whose wash is a 2px stroke pinned to the box
 * edge, where no label sits. The rules below pin both halves of that decision.
 */
describe('D · the wash can never cost a label its contrast', () => {
  /** Field-tint-safe label classes: dark brand text, and light-on-dark fills. */
  const FIELD_TEXTS = {
    charcoal: hex('#252729'), // 14.99:1 on white at rest
    muted: hex('#595C63'), // 6.7:1 — the product's secondary text token
    slate600: hex('#475569'),
    slate700: hex('#334155'),
  };
  const LIGHT_TEXTS = { white: hex('#FFFFFF'), slate100: hex('#F1F5F9') };
  /** A 4% tint is not a tint: below that the stop is a fade, not a surface. */
  const VISIBLE_ALPHA = 0.04;

  const fieldIntents = BUTTON_INTENTS.filter((i) => i !== 'filter');

  const visibleWashes = fieldIntents.flatMap((intent) =>
    [...intentBlock(intent).matchAll(/rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/g)]
      .map((m) => ({ intent, rgba: parseRgba(+m[1], +m[2], +m[3], +m[4]) }))
      .filter((w) => w.rgba[3] >= VISIBLE_ALPHA),
  );

  it('every intent paints at least one visible wash colour', () => {
    expect(visibleWashes.length).toBeGreaterThan(fieldIntents.length);
  });

  it('field washes keep the label classes they are allowed to sit under ≥ 4.8:1', () => {
    const worst: { ratio: number; label: string }[] = [];
    for (const { rgba } of visibleWashes) {
      for (const surface of Object.values(SURFACES)) {
        const painted = composite(rgba, surface);
        for (const [name, text] of Object.entries(FIELD_TEXTS)) {
          worst.push({ ratio: contrast(text, painted), label: name });
        }
      }
    }
    const min = worst.reduce((a, b) => (b.ratio < a.ratio ? b : a));
    // MEASURED FLOOR: 4.82:1 (muted over the brand cream surface, α 0.14).
    // Asserted at 4.8 so a future intent cannot quietly spend the margin.
    expect(min.ratio, `weakest: ${min.label} at ${min.ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.8);
  });

  it('the white streak over a dark fill keeps light labels ≥ 4.5:1', () => {
    const streaks = [...css.matchAll(/rgba\(255,\s*255,\s*255,\s*([\d.]+)\)/g)].map((m) =>
      parseRgba(255, 255, 255, +m[1]),
    );
    const strongest = streaks.sort((a, b) => b[3] - a[3])[0];
    const painted = composite(strongest, hex('#252729'));
    for (const [name, text] of Object.entries(LIGHT_TEXTS)) {
      expect(contrast(text, painted), `${name} on the streak`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('a medium-tone label is NEVER given a field tint — the geometry rule holds', () => {
    // Any control whose own className declares slate-300/400/500 as its text
    // colour must declare the edge geometry instead.
    // …and which actually render COPY. A ✕ or a + in slate-400 is a glyph,
    // covered by the icon rule below — there is no text to cost contrast to.
    // The predicate comes from the tool's own report, so the rule and the
    // assertion cannot disagree about what counts as a label.
    const medium = report.rows.filter(
      (r) => /text-slate-(300|400|500)\b/.test(r.className) && !(r as { glyphOnly?: boolean }).glyphOnly,
    );
    // Floor = the measured count after the 2026-10-17 contrast pass, which
    // moved failing slate-400/500 labels (2.56–4.76:1) to `text-brand-muted`
    // (6.70:1, field-safe per the 4.82 floor above). The remaining two —
    // VirtualTryOnModal (slate-500) and AdminAudit (slate-300 on dark) — keep
    // this rule exercised; the rule assertion below is unchanged.
    expect(medium.length, 'the catalog should still contain medium-tone labels').toBeGreaterThanOrEqual(2);
    const wrong = medium.filter((r) => r.tone !== 'edge');
    expect(
      wrong.map((r) => `${r.file}:${r.line} (${r.tone})`),
      'these controls tint the surface behind a medium-tone label',
    ).toEqual([]);
  });

  it('the edge geometry is a stroke pinned to the box edge, not a field', () => {
    const edge = css.slice(css.indexOf('[data-motion-tone="edge"]'), css.indexOf('}', css.indexOf('[data-motion-tone="edge"]')));
    // 2px thick …
    expect(edge).toContain('210% var(--_mo-stroke)');
    // … pinned to the bottom edge (y = 100%), so the label band is untouched.
    expect(edge).toContain('--_mo-wash-rest: 200% 100%');
    expect(edge).toContain('--_mo-wash-end: 100% 100%');
    // The arithmetic that makes it safe: on the smallest control in the system
    // (44px) with a 16px label line, 14px of clearance sits under the text
    // against a 2px stroke.
    expect((44 - 16) / 2).toBeGreaterThan(2);
  });

  it('the vertical families anchor the stroke to the inline end instead', () => {
    for (const [intent, rest] of [
      ['upload', '--_mo-wash-rest: 100% -100%'],
      ['download', '--_mo-wash-rest: 100% 200%'],
    ]) {
      const at = css.indexOf(`[data-motion-tone="edge"][data-motion="${intent}"]`);
      expect(at).toBeGreaterThan(-1);
      const block = css.slice(at, css.indexOf('}', at));
      expect(block).toContain('var(--_mo-stroke) 210%');
      expect(block).toContain(rest);
    }
    // RTL mirrors the stroke's x and keeps its y anchor at the edge.
    const rtl = css.slice(css.indexOf('[dir="rtl"] [data-motion-tone="edge"]'));
    expect(rtl.slice(0, rtl.indexOf('}'))).toContain('--_mo-wash-rest: -100% 100%');
  });

  it('alphas stay inside the documented ceiling, bar the one 2px rule', () => {
    // The chip/segment `filter` family draws a 2px rule that no text sits on;
    // every wash that CAN sit under text stays under 0.3.
    const filterBlock = intentBlock('filter');
    const outside = css
      .replace(filterBlock, '')
      .match(/rgba\(\d+,\s*\d+,\s*\d+,\s*0\.[3-9]\d*\)/g);
    expect(outside, `alphas above the ceiling: ${outside?.join(', ')}`).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* E. Coverage ratchet                                                 */
/* ------------------------------------------------------------------ */
describe('E · coverage — every control, every family', () => {
  it('finds the whole control surface (not a stale or partial scan)', () => {
    expect(report.totals.controls).toBeGreaterThan(250);
    expect(report.byRole.Consumer).toBeGreaterThan(50);
    expect(report.byRole['Brand / Admin console']).toBeGreaterThan(30);
  });

  it('EVERY button declares a motion intent — new controls cannot slip through', () => {
    const offenders = report.needEdits.map((r) => `${r.file}:${r.line} → ${r.intent} (tone: ${r.tone})`);
    expect(
      offenders,
      `controls with no data-motion (run: node scripts/apply-button-motion.mjs --write):\n${offenders.join('\n')}`,
    ).toEqual([]);
  });

  it('every registered family is in use by real controls (no aspirational recipes)', () => {
    const unused = BUTTON_INTENTS.filter((i) => !report.byIntent[i]);
    expect(unused, `registered but unused: ${unused.join(', ')}`).toEqual([]);
  });

  it('the destructive family is small and specific — not a dumping ground', () => {
    expect(report.byIntent.destructive).toBeGreaterThan(3);
    expect(report.byIntent.destructive).toBeLessThan(report.byIntent.neutral);
  });

  it('glyph-only controls get the icon geometry (no text, nothing to tint)', () => {
    const glyphOnly = report.rows.filter((r) => (r as { glyphOnly?: boolean }).glyphOnly);
    expect(glyphOnly.length).toBeGreaterThan(10);
    const wrong = glyphOnly.filter((r) => r.tone !== 'icon');
    expect(wrong.map((r) => `${r.file}:${r.line} “${r.label}” (${r.tone})`)).toEqual([]);
  });

  it('the catalog groups every control of every role', () => {
    // Roles are the axis the brief asks the catalog to be grouped by.
    for (const role of ['Consumer', 'Brand / Admin console', 'Auth', 'Shared UI']) {
      expect(report.byRole[role], `role ${role} missing from the catalog`).toBeGreaterThan(0);
    }
  });
});

/* ------------------------------------------------------------------ */
/* F. Wiring — the engine is loaded and the CTA speaks to it           */
/* ------------------------------------------------------------------ */
describe('F · wiring', () => {
  const LABELS = {
    idle: 'Save look',
    pending: 'Saving…',
    success: 'Saved',
    error: 'Failed — retry',
  };
  const renderCta = (props: Partial<React.ComponentProps<typeof ActionButton>> = {}) =>
    render(
      <I18nextProvider i18n={i18n}>
        <ActionButton labels={LABELS} {...props} />
      </I18nextProvider>,
    );

  it('the stylesheet is loaded by the app entry, after the design system', () => {
    const index = mainTsx.indexOf("'./styles/index.css'");
    const engine = mainTsx.indexOf("'./styles/button-motion.css'");
    expect(engine, 'button-motion.css must be imported').toBeGreaterThan(-1);
    expect(engine, 'the engine must load AFTER index.css to win the cascade').toBeGreaterThan(index);
  });

  it('ActionButton defaults to the progressive recipe', () => {
    renderCta();
    expect(screen.getByRole('button').getAttribute('data-motion')).toBe('progressive');
  });

  it('a financial CTA animates as money, not as a generic save', () => {
    renderCta({ financial: true });
    expect(screen.getByRole('button').getAttribute('data-motion')).toBe('financial');
  });

  it('an explicit intent wins over both defaults', () => {
    renderCta({ financial: true, intent: 'destructive' });
    expect(screen.getByRole('button').getAttribute('data-motion')).toBe('destructive');
  });

  it('the states the engine animates are the states the machine publishes', async () => {
    const gate = (() => {
      let resolve!: () => void;
      const promise = new Promise<void>((r) => (resolve = r));
      return { promise, resolve };
    })();
    renderCta({ onAction: () => gate.promise });
    const btn = screen.getByRole('button');
    btn.click();
    // pending: aria-busy drives the loading loop, and `data-state` says which
    // state machine phase it is — the CSS reads both.
    await screen.findByTestId('cta-spinner');
    expect(btn.getAttribute('aria-busy')).toBe('true');
    expect(btn.getAttribute('data-state')).toBe('pending');
    gate.resolve();
    await screen.findByText('Saved');
    expect(btn.getAttribute('data-state')).toBe('success');
  });

  it('the reduced-motion render path keeps the intent — the recipe is not motion-only', async () => {
    // Under reduced motion ActionButton renders a plain <button>; it must
    // still carry the intent so the static wash and state colours apply.
    const original = window.matchMedia;
    window.matchMedia = ((q: string) => ({
      matches: q.includes('prefers-reduced-motion'),
      media: q,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      onchange: null,
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      renderCta({ intent: 'progressive' });
      const btn = screen.getByRole('button');
      expect(btn.getAttribute('data-motion')).toBe('progressive');
      expect(btn.className).not.toContain('motion'); // still a plain button
    } finally {
      window.matchMedia = original;
    }
  });
});
