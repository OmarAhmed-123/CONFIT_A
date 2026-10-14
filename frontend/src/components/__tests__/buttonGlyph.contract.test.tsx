/**
 * Functional glyph motion — contract.
 *
 * Part 3's acceptance criteria, as assertions rather than intentions:
 *
 *   · the glyph layer and the background layer must agree on what "busy",
 *     "success" and "failure" mean — one product, one state vocabulary;
 *   · nothing in the glyph keyframes may touch layout (the same ban the
 *     background layer is held to);
 *   · every verb must have motion in at least one state and NONE at rest — an
 *     animation that plays while nothing is happening is the definition of
 *     animation for its own sake;
 *   · destructive verbs never celebrate;
 *   · reduced motion keeps the state and drops the movement;
 *   · the state must be read from an ancestor selector, never from a custom
 *     property (a `[style*='--g-state: 1']` selector can never match — that
 *     mistake was made while writing this file and is guarded below).
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(__dirname, '../../../');

function readSource(relative: string): string {
  return readFileSync(resolve(ROOT, relative), 'utf8');
}

/** Comments describe the design; they are not the design. Every mechanical
 *  assertion below runs against the stylesheet with its prose removed. */
const rules = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');

const GLYPH_CSS = readSource('src/styles/button-glyph-motion.css');
const BG_CSS = readSource('src/styles/button-motion.css');
const ICONS = readSource('src/components/icons/ConfitIcons.tsx');
const MAIN = readSource('src/main.tsx');

const glyphRules = rules(GLYPH_CSS);

/** The slice of the stylesheet that belongs to one verb: from its first mention
 *  to the next verb's first mention. Naive `split().slice(1).join('')` would run
 *  to end-of-file and make an assertion about `trash` pass or fail on the rules
 *  of whatever verb happens to follow it. */
function verbSection(css: string, verb: string): string {
  const start = css.indexOf(`.confit-glyph--${verb}`);
  if (start < 0) return '';
  const others = VERBS.filter((v) => v !== verb)
    .map((v) => css.indexOf(`.confit-glyph--${v}`, start + 1))
    .filter((i) => i > start);
  return css.slice(start, others.length ? Math.min(...others) : css.length);
}

/** One `@media (…) { … }` block, matched by braces rather than by a lazy regex
 *  that stops at the first inner `}`. */
function mediaBlock(css: string, query: string): string {
  const at = css.indexOf(`@media (${query})`);
  if (at < 0) return '';
  let depth = 0;
  let i = css.indexOf('{', at);
  const open = i;
  for (; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}') {
      depth--;
      if (depth === 0) break;
    }
  }
  return css.slice(open + 1, i);
}

/** Everything in the file except its media queries — they are conditional, so
 *  they cannot be what runs at rest. */
const glyphBaseRules = glyphRules.replace(/@media[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}/g, '');

const VERBS = [
  'upload', 'download', 'send', 'retry', 'trash', 'bookmark', 'playpause', 'share', 'check',
] as const;

/** The state attributes each layer listens to. */
function statesUsed(css: string): Set<string> {
  const found = new Set<string>();
  for (const match of css.matchAll(/\[(aria-busy|data-state|data-motion-state)=['"]([\w-]+)['"]\]/g)) {
    found.add(`${match[1]}:${match[2]}`);
  }
  return found;
}

describe('A · one state vocabulary across both motion layers', () => {
  // Both layers must agree on what moves. The glyph layer reads a deliberate
  // SUBSET of the background states: everything except the three "quiet" ones,
  // because a control waiting on a precondition has nothing for a verb glyph to
  // say — the arrow must not fly for a form that has not been submitted.
  const QUIET = ['data-motion-state:quiet', 'data-state:unauthorized', 'data-state:unavailable'];

  it('reads the same async states as the background engine, minus the quiet ones', () => {
    const glyph = statesUsed(glyphRules);
    const background = statesUsed(rules(BG_CSS));
    const moving = (set: Set<string>) => [...set].filter((s) => !QUIET.includes(s)).sort();

    expect(glyph.size).toBeGreaterThan(0);
    for (const state of glyph) {
      expect(background, `the glyph layer reads ${state}, the background layer does not`).toContain(state);
    }
    // Equal, not merely a subset: a state the background animates and the glyph
    // silently ignores would be a control whose two halves disagree.
    expect(moving(glyph)).toEqual(moving(background));
  });

  it('leaves the quiet states motionless in the glyph layer on purpose', () => {
    const glyph = statesUsed(glyphRules);
    for (const quiet of QUIET) {
      expect(glyph, `${quiet} must not animate a verb glyph`).not.toContain(quiet);
    }
    // ...and the background layer does define them, so the omission is a choice
    // about motion, not a gap in either file.
    const background = statesUsed(rules(BG_CSS));
    for (const quiet of QUIET) expect(background).toContain(quiet);
  });

  it('takes its state from an ancestor control, never from a custom property', () => {
    // A custom property cannot be queried by a selector: `[style*='--g: 1']`
    // only ever matches an inline style attribute, and the state is applied by
    // CSS here. This guard exists because that exact dead selector was written
    // into this file first and caught in review.
    expect(glyphRules).not.toMatch(/\[style\*=['"]--g-state/);
    expect(glyphRules).not.toContain('--g-state');

    const ancestors = glyphRules.match(/^:is\(button, a, \[role='button'\]\)/gm) ?? [];
    expect(ancestors.length).toBeGreaterThanOrEqual(20);
  });

  it('covers all five states the product publishes', () => {
    for (const selector of ['aria-busy', "data-state='pending'", "data-state='success'", "data-state='error'", ':hover', ':focus-visible', ':disabled']) {
      expect(glyphRules, `${selector} is not handled`).toContain(selector);
    }
  });
});

describe('B · no layout shift, by construction', () => {
  const LAYOUT_PROPERTIES = [
    'width', 'height', 'padding', 'margin', 'inset', 'top', 'right', 'bottom', 'left',
    'font-size', 'line-height', 'letter-spacing', 'border-width', 'gap', 'flex', 'grid',
  ];

  it('animates only transform and opacity across all twelve keyframes', () => {
    const blocks = [...glyphRules.matchAll(/@keyframes\s[\w-]+\s*\{([\s\S]*?)\n\}/g)].map((m) => m[1]);
    expect(blocks.length).toBeGreaterThanOrEqual(10);

    for (const block of blocks) {
      const properties = [...block.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]);
      for (const property of properties) {
        expect(
          ['transform', 'opacity', 'stroke-dashoffset', 'fill-opacity'],
          `keyframe animates ${property}, which can change layout`,
        ).toContain(property);
      }
      for (const banned of LAYOUT_PROPERTIES) {
        expect(block).not.toMatch(new RegExp(`(^|[\\s;{])${banned}\\s*:`));
      }
    }
  });

  it('pins the glyph box so a travelling glyph cannot push its label', () => {
    expect(glyphRules).toMatch(/\.confit-glyph\s*\{[^}]*contain:\s*layout/);
    expect(glyphRules).toMatch(/\.confit-glyph\s*\{[^}]*flex-shrink:\s*0/);
    expect(rules(ICONS)).toContain('shrink-0');
  });
});

describe('C · every verb earns its animation', () => {
  it('declares all nine verbs in the stylesheet', () => {
    for (const verb of VERBS) {
      expect(glyphRules, `${verb} has no rules`).toContain(`.confit-glyph--${verb}`);
    }
  });

  it('gives every verb motion in at least one non-rest state', () => {
    for (const verb of VERBS) {
      const block = glyphRules.split(`.confit-glyph--${verb}`).slice(1).join('');
      const hasMotion = /animation:|transform:\s*(?!none)|stroke-dashoffset:\s*0/.test(block);
      expect(hasMotion, `${verb} never animates`).toBe(true);
    }
  });

  it('never animates at rest — every rule is bound to a state or a pointer', () => {
    // A declaration that applies to the bare class would run on page load.
    const bareRules = [...glyphBaseRules.matchAll(/^([^\n{}]*\.confit-glyph[a-z-]*[^\n{}]*)\{([^}]*)\}/gm)];
    for (const [, selector, body] of bareRules) {
      const isBare = !/:(hover|focus-visible|active|disabled)|aria-|data-|dir=|prefers-reduced|forced-colors|keyframes/.test(selector);
      if (!isBare) continue;
      expect(body, `${selector.trim()} animates unconditionally`).not.toMatch(/(^|[;\s])animation\s*:/);
    }
  });

  it('keeps destructive verbs restrained: no celebration on deletion', () => {
    const trash = verbSection(glyphRules, 'trash');
    expect(trash).not.toMatch(/scale\(1\.[1-9]/); // no bounce
    expect(trash).not.toMatch(/confit-glyph-pop/); // the success pop belongs to save
    expect(trash).toMatch(/opacity:\s*0/); // it retracts instead
  });

  it('never draws progress for a retry, which has no known duration', () => {
    const retry = verbSection(glyphRules, 'retry');
    expect(retry).toMatch(/confit-glyph-turn/); // it turns...
    expect(retry).not.toMatch(/width|scaleX|clip-path/); // ...it does not fill
  });

  it('drives the play/pause morph and the bookmark fill from aria-pressed', () => {
    expect(glyphRules).toMatch(/aria-pressed='true'\]\s*>\s*\.confit-glyph--playpause/);
    expect(rules(ICONS)).toMatch(/isPlaying = false/);
    expect(rules(ICONS)).toMatch(/isSaved = false/);
  });
});

describe('D · accessibility', () => {
  it('removes movement but keeps state under reduced motion', () => {
    const body = mediaBlock(glyphRules, 'prefers-reduced-motion: reduce');
    expect(body, 'no reduced-motion block').not.toBe('');
    expect(body).toContain('animation: none !important');
    // The states that are expressed as a transform must be re-stated, or the
    // outcome would be invisible to a user who asked for less motion.
    expect(body).toMatch(/--check\b/);
    expect(body).toMatch(/stroke-dashoffset:\s*0/);
    expect(body).toMatch(/--playpause/);
  });

  it('hands the palette to the OS in forced-colors mode', () => {
    const body = mediaBlock(glyphRules, 'forced-colors: active');
    expect(body).not.toBe('');
    expect(body).toContain('animation: none !important');
    expect(body).toMatch(/CanvasText|currentColor/);
  });

  it('mirrors only the two directional gestures for Arabic', () => {
    const rtlStart = glyphRules.indexOf("[dir='rtl']");
    const rtl = glyphRules.slice(rtlStart, glyphRules.indexOf('@media', rtlStart) === -1 ? undefined : glyphRules.indexOf('@media', rtlStart));
    expect(rtl).toContain('.confit-glyph--send');
    expect(rtl).toContain('.confit-glyph--share');
    // an upload arrow rises in Arabic too: vertical verbs keep their keyframes
    expect(rtl).not.toContain('.confit-glyph--upload');
    expect(rtl).not.toContain('.confit-glyph--download');
    expect(rules(GLYPH_CSS)).toContain('confit-glyph-fly-rtl');
  });

  it('keeps verb glyphs decorative so a labelled control is not read twice', () => {
    expect(ICONS).toContain("aria-hidden': 'true'");
    expect(ICONS).toMatch(/label \? \{ role: 'img'/);
  });

  it('loads after the background engine, which loads after the Tailwind entry', () => {
    const order = MAIN.indexOf('styles/index.css');
    const background = MAIN.indexOf('styles/button-motion.css');
    const glyph = MAIN.indexOf('styles/button-glyph-motion.css');
    expect(order).toBeGreaterThan(-1);
    expect(background).toBeGreaterThan(order);
    expect(glyph).toBeGreaterThan(background);
  });
});

describe('E · the app actually uses the vocabulary', () => {
  it('ships a verb glyph for every animated verb', () => {
    for (const [verb, component] of [
      ['upload', 'UploadIcon'], ['download', 'DownloadIcon'], ['send', 'SendIcon'],
      ['retry', 'RetryIcon'], ['trash', 'TrashIcon'], ['bookmark', 'BookmarkIcon'],
      ['playpause', 'PlayPauseIcon'], ['share', 'ShareGlyph'], ['check', 'CheckIcon'],
    ] as const) {
      expect(rules(ICONS), `${verb} has no component`).toContain(`export const ${component}`);
      expect(rules(ICONS)).toContain(`glyph="${verb}"`);
    }
  });

  it('carries each moving part class the stylesheet selects on', () => {
    for (const part of ['tray', 'shaft', 'head', 'body', 'lid', 'fill', 'ring', 'node', 'link', 'play', 'pause', 'check']) {
      expect(glyphRules, `stylesheet animates .confit-glyph-${part} but no glyph declares it`)
        .toContain(`.confit-glyph-${part}`);
      expect(rules(ICONS), `no glyph declares confit-glyph-${part}`).toContain(`confit-glyph-${part}`);
    }
  });

  it('wired the verbs the brief names into real controls', () => {
    const used = (path: string, needle: string) =>
      expect(readSource(path), `${path} lost its ${needle}`).toContain(needle);

    used('src/components/admin/BrandReportDownloadButton.tsx', '<DownloadIcon');
    used('src/components/stylist/VirtualStylistDrawer.tsx', '<SendIcon');
    used('src/views/b2b/BrandCatalogView.tsx', '<UploadIcon');
    used('src/views/consumer/OutfitBuilderView.tsx', '<BookmarkIcon');
  });

  it('keeps every verb glyph free of hard-coded colours that fight the surface', () => {
    const verbs = rules(ICONS).split('FUNCTIONAL VERB GLYPHS').pop() ?? '';
    // The whole point of `color || 'currentColor'` is that a glyph inherits the
    // label's colour. A literal here is how the previous submit icon ended up
    // near-invisible on a charcoal fill.
    const literals = verbs.match(/color = "#[0-9A-Fa-f]{3,6}"/g) ?? [];
    expect(literals).toEqual([]);
  });
});
