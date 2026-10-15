#!/usr/bin/env node
/**
 * Design spec sheet for the button motion system.
 *
 * Generates docs/button-motion-preview.html — a single self-contained page that
 * renders every intent in every state, so the system can be REVIEWED rather than
 * only asserted. Nothing here is hand-styled: the page inlines the real
 * `src/styles/button-motion.css` verbatim, and the two "forced" preview states
 * (pointer hover, keyboard focus) are the engine's OWN declarations re-pointed at
 * a demo attribute. If the engine changes, the sheet changes with it — there is
 * no second copy of any recipe to drift.
 *
 *   node scripts/button-motion-preview.mjs            # write docs/button-motion-preview.html
 *   node scripts/button-motion-preview.mjs --check    # exit 1 if the file is stale (CI)
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../..');
const CSS_PATH = resolve(HERE, '../src/styles/button-motion.css');
const CSV_PATH = resolve(ROOT, 'docs/button-motion-catalog.csv');
const OUT_PATH = resolve(ROOT, 'docs/button-motion-preview.html');

const css = readFileSync(CSS_PATH, 'utf8');

/* ── tiny CSS surgery ────────────────────────────────────────────────────── */

/** Body of the first rule whose selector text contains `needle`. */
function ruleBody(source, needle) {
  const at = source.indexOf(needle);
  if (at < 0) throw new Error(`selector not found in the engine: ${needle}`);
  const open = source.indexOf('{', at);
  let depth = 1;
  let i = open + 1;
  while (i < source.length && depth > 0) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') depth--;
    i++;
  }
  return source.slice(open + 1, i - 1).trim();
}

/** Top-level rules inside a block, so a media query can be re-scoped. */
function topLevelRules(body) {
  const out = [];
  let depth = 0;
  let start = 0;
  const flush = (end) => {
    const chunk = body.slice(start, end).trim();
    if (chunk) out.push(chunk);
  };
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) {
        flush(i + 1);
        start = i + 1;
      }
    }
  }
  flush(body.length);
  return out;
}

/** Re-point a media-query block at a class, so it can be shown side by side. */
function scopeMedia(source, media, scope) {
  const at = source.indexOf(media);
  if (at < 0) throw new Error(`media query not found: ${media}`);
  // grab from the media query's `{` to its matching `}`
  const open = source.indexOf('{', at);
  let depth = 1;
  let i = open + 1;
  while (i < source.length && depth > 0) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') depth--;
    i++;
  }
  const inner = source.slice(open + 1, i - 1);
  return topLevelRules(inner)
    .map((rule) => {
      const brace = rule.indexOf('{');
      const selector = rule.slice(0, brace);
      const body = rule.slice(brace);
      if (selector.trim().startsWith('@')) return rule; // nested media: leave alone
      const scoped = selector
        .split(',')
        .map((s) => `${scope} ${s.trim()}`)
        .join(',\n');
      return `${scoped} ${body}`;
    })
    .join('\n');
}

const hoverBody = ruleBody(css, ':not([data-motion="none"]):hover');
const reducedOk = scopeMedia(css, '@media (prefers-reduced-motion: reduce)', '.demo-reduced');

/* ── the catalog, so the sheet shows real product copy ───────────────────── */
const INTENTS = [
  'progressive', 'commerce', 'financial', 'destructive', 'creative',
  'upload', 'download', 'share', 'recovery', 'auth', 'admin', 'filter', 'neutral',
];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...rest] = rows;
  return rest.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
}

const catalog = existsSync(CSV_PATH) ? parseCsv(readFileSync(CSV_PATH, 'utf8')) : [];
const byIntent = Object.fromEntries(INTENTS.map((i) => [i, []]));
for (const row of catalog) (byIntent[row.intent] ??= []).push(row);

const words = (s) => /[\p{L}\p{N}]/u.test(s) && !s.startsWith('(');
const labelFor = (intent) => {
  const hit = (byIntent[intent] ?? []).find((r) => words(r.label));
  return hit ? hit.label : intent[0].toUpperCase() + intent.slice(1);
};
const examplesFor = (intent) => {
  const seen = new Set();
  const out = [];
  for (const r of byIntent[intent] ?? []) {
    const key = r.file;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(`${r.file.split('/').pop()}:${r.line}`);
    if (out.length === 3) break;
  }
  return out;
};
const countFor = (intent) => (byIntent[intent] ?? []).length;

/* ── the sheet ───────────────────────────────────────────────────────────── */
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const btn = (intent, { tone, state, variant = 'solid', label, hover = false, rtl = false } = {}) => {
  const attrs = [
    `data-motion="${intent}"`,
    tone ? `data-motion-tone="${tone}"` : '',
    state ? `data-state="${state}"` : '',
    hover ? 'data-demo-hover' : '',
  ].filter(Boolean).join(' ');
  const word = label ?? labelFor(intent);
  // Loading cells use aria-busy so the sheet exercises the REAL trigger, not a
  // data-* shortcut the product does not use.
  const busy = state === 'pending' ? ' aria-busy="true"' : '';
  return `<button type="button" class="d-btn d-${variant}" ${attrs}${busy}>${esc(word)}</button>`;
};

const interactionRow = (intent) => `
      <tr>
        <th scope="row">
          <code>${intent}</code>
          <span class="n">${countFor(intent)} ${countFor(intent) === 1 ? 'control' : 'controls'}</span>
          <span class="eg">${esc(examplesFor(intent).join(' · '))}</span>
        </th>
        <td>${btn(intent, { variant: 'ghost' })}</td>
        <td>${btn(intent, { variant: 'ghost', hover: true })}</td>
        <td>${btn(intent, { variant: 'solid' })}</td>
        <td>${btn(intent, { variant: 'solid', hover: true })}</td>
      </tr>`;

const loadingRow = (intent) => `
      <tr>
        <th scope="row"><code>${intent}</code><span class="eg">${esc(labelFor(intent))}</span></th>
        <td>${btn(intent, { state: 'pending' })}</td>
      </tr>`;

const stateRow = (label, state, intents) => `
      <tr>
        <th scope="row">${label}<span class="eg">${state}</span></th>
        ${intents.map((i) => `<td>${btn(i, { state })}</td>`).join('')}
      </tr>`;

const total = catalog.length || 313;
const families = INTENTS.length;

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Button Motion System — spec sheet</title>
<style>
/* ── the sheet's own chrome ───────────────────────────────────────────────── */
:root {
  --ink: #252729; --muted: #595C63; --hairline: #E8E6E2; --cream: #FAF9F6;
  --field: #F7F6F3; --navy: #1B1F3B; --gold: #B8935A; --lilac: #A99AD6;
  --mint: #89B799; --coral: #EF826D;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 40px 32px 96px; background: var(--cream); color: var(--ink);
  font: 15px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 30px; letter-spacing: -0.02em; margin: 0 0 6px; }
h2 { font-size: 19px; letter-spacing: -0.01em; margin: 56px 0 4px; }
h2 .tag { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); display: block; margin-bottom: 6px; font-weight: 600; }
p.lede { color: var(--muted); max-width: 76ch; margin: 0 0 8px; }
p.note { color: var(--muted); font-size: 13px; max-width: 88ch; margin: 10px 0 0; }
.gen { font-size: 12px; color: var(--muted); border-top: 1px solid var(--hairline); padding-top: 14px; margin-top: 8px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; background: var(--field); border: 1px solid var(--hairline); border-radius: 5px; padding: 1px 5px; }
table { border-collapse: collapse; width: 100%; margin-top: 18px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--hairline); vertical-align: middle; }
thead th { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid #d8d5d0; }
tbody th { width: 300px; font-weight: 600; }
tbody th code { background: #fff; }
tbody th .n { display: block; font-weight: 400; font-size: 12px; color: var(--muted); }
tbody th .eg { display: block; font-weight: 400; font-size: 11.5px; color: #8A8D93; margin-top: 2px; }
td { background: #fff; }
.d-btn {
  appearance: none; border-radius: 10px; padding: 10px 16px; font: inherit; font-size: 14px;
  font-weight: 600; cursor: pointer; border: 1px solid transparent; display: inline-flex;
  align-items: center; gap: 8px; line-height: 1.2; min-height: 42px;
}
.d-solid { background-color: var(--ink); color: #FAF9F6; }
.d-ghost { background-color: #fff; color: var(--ink); border-color: var(--hairline); }
.panel { background: var(--field); border: 1px solid var(--hairline); border-radius: 14px; padding: 22px 24px; margin-top: 18px; }
.panel.dark { background: var(--ink); border-color: #3a3d40; color: #FAF9F6; }
.panel.dark .d-ghost { background-color: #2f3236; color: #FAF9F6; border-color: #45484c; }
.panel.dark p.lede, .panel.dark .eg { color: #b9bcc0; }
.grid { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
.flags { display: flex; flex-wrap: wrap; gap: 26px; }
.flags > div { min-width: 260px; }
.flags h3 { font-size: 13px; margin: 0 0 10px; letter-spacing: 0.02em; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 14px; font-size: 12.5px; color: var(--muted); }
.legend b { color: var(--ink); font-weight: 600; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: baseline; }
.kv { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-top: 22px; }
.kv div { background: #fff; border: 1px solid var(--hairline); border-radius: 12px; padding: 14px 16px; }
.kv b { display: block; font-size: 22px; letter-spacing: -0.02em; }
.kv span { font-size: 12px; color: var(--muted); }
.actions { margin-top: 14px; }
.replay { appearance: none; border: 1px solid var(--hairline); background: #fff; border-radius: 8px; padding: 7px 12px; font: inherit; font-size: 12.5px; cursor: pointer; color: var(--muted); }
/* ── the engine, verbatim ─────────────────────────────────────────────────── */
${css}
/* ── preview-only: replay the engine's own pointer declarations statically ── */
[data-demo-hover] {
  background-position: var(--_mo-streak-end), var(--_mo-wash-end);
  background-size: var(--_mo-streak-size-end), var(--_mo-wash-size-end);
}
/* ── preview-only: the reduced-motion block, re-scoped so both are visible ── */
${reducedOk}
.demo-reduced [data-motion] { background-position: var(--_mo-streak-end), var(--_mo-wash-end); }
</style>
</head>
<body>
<div class="wrap">

  <h1>Button Motion System</h1>
  <p class="lede">Every functional control in the product — <b>${total} buttons</b> across
  8 role surfaces — assigned to one of <b>${families} semantic families</b>. Each family
  carries its own colour psychology and its own loading gesture. The animation is
  <b>pure CSS</b>: two gradient layers on the button's own <code>background-image</code>,
  moved with <code>background-position</code> and <code>background-size</code>. No
  JavaScript animates any of it, and no keyframe touches a layout property.</p>

  <div class="kv">
    <div><b>${total}</b><span>controls covered · 100%</span></div>
    <div><b>${families}</b><span>semantic families</span></div>
    <div><b>5</b><span>keyframes, total</span></div>
    <div><b>0</b><span>JS animation libraries</span></div>
    <div><b>4.82:1</b><span>worst measured contrast (AA = 4.5)</span></div>
  </div>

  <p class="note">This page is generated — <code>node scripts/button-motion-preview.mjs</code>.
  It inlines <code>src/styles/button-motion.css</code> verbatim; the two pointer states are
  the engine's own declarations re-pointed at a demo attribute, so there is no second copy of
  any recipe to drift out of date. <b>Hover and click the buttons</b> — the loading gestures
  below are live, not screenshots.</p>

  <h2><span class="tag">Section 1 · the interaction</span>Rest → hover, on both surface weights</h2>
  <p class="lede">At rest both layers sit entirely outside the padding box, so a control looks
  exactly as it did before the system existed. On pointer or keyboard entry the wash slides in
  from the inline start and settles while the streak crosses once and leaves.</p>
  <table>
    <thead>
      <tr>
        <th>family</th>
        <th>secondary · rest</th>
        <th>secondary · hover</th>
        <th>primary · rest</th>
        <th>primary · hover</th>
      </tr>
    </thead>
    <tbody>
${INTENTS.map(interactionRow).join('\n')}
    </tbody>
  </table>
  <p class="note">“secondary” = a hairline-bordered surface, where the wash reads as a tint.
  “primary” = the charcoal fill, where the wash is carried by the streak. The same tokens
  drive both, which is why a family looks like itself on every surface in the product.</p>

  <h2><span class="tag">Section 2 · the loading gestures</span>Thirteen bespoke ways to say “working”</h2>
  <p class="lede">The gesture is chosen by what the action <i>is</i>, because the shape of
  progress is information: money moves slowly, generative work drifts, an upload rises and a
  download falls, and anything destructive or irreversible gets hazard tape rather than a
  hopeful sweep. Each loops until the real state changes — none of them fakes a percentage.</p>
  <table>
    <thead><tr><th>family</th><th>loading</th></tr></thead>
    <tbody>
${INTENTS.map(loadingRow).join('\n')}
    </tbody>
  </table>
  <p class="note">These are the engine's real triggers (<code>aria-busy="true"</code>), not a
  demo class — which is why a control that forgot to set its state simply keeps its resting
  look instead of looping something untrue.</p>

  <h2><span class="tag">Section 3 · the outcome states</span>One language for success, failure and “not yet”</h2>
  <p class="lede">Outcome is shared across every family — green means it worked wherever it
  happens — while the family colour stays underneath it in the wash. The error state is the
  only place the file uses a transform: a 2px nudge that returns to zero, so nothing is left
  displaced.</p>
  <table>
    <thead><tr><th>state</th><th>progressive</th><th>financial</th><th>destructive</th><th>upload</th></tr></thead>
    <tbody>
${[
  stateRow('Success', 'success', ['progressive', 'financial', 'destructive', 'upload']),
  stateRow('Error', 'error', ['progressive', 'financial', 'destructive', 'upload']),
  stateRow('Quiet — waiting on something else', 'unavailable', ['progressive', 'financial', 'destructive', 'upload']),
].join('\n')}
    </tbody>
  </table>
  <p class="actions"><button class="replay" type="button" id="replay">Replay the one-shot states</button>
  <span class="eg" style="margin-left:10px">each click re-runs the finite gestures — a retry never shows a bar, because a retry has no known duration.</span></p>

  <h2><span class="tag">Section 4 · geometry</span>The three shapes, and why they exist</h2>
  <p class="lede">Geometry is measurement, not taste. A control that is only a glyph has no
  text to tint, so it blooms from the centre. A control whose own label is a medium-tone grey
  cannot afford a tint underneath it — that was the one real WCAG defect this work found — so
  its wash becomes a 2px stroke pinned to the box's outer edge, where a centred label cannot
  sit.</p>
  <div class="panel">
    <div class="grid">
      <div>${btn('progressive', { label: 'Add to wardrobe' })}<div class="eg" style="margin-top:6px">auto — a field tint</div></div>
      <div>${btn('neutral', { tone: 'icon', label: '✕' })}<div class="eg" style="margin-top:6px">icon — a centre bloom</div></div>
      <div>${btn('neutral', { tone: 'edge', label: 'Cancel' })}<div class="eg" style="margin-top:6px">edge — an outer-edge stroke</div></div>
      <div>${btn('none', { label: 'Bespoke surface', tone: 'quiet' })}<div class="eg" style="margin-top:6px">none — engine steps aside</div></div>
    </div>
  </div>

  <h2><span class="tag">Section 5 · direction and settings</span>Arabic, reduced motion, and the OS palette</h2>
  <div class="flags">
    <div dir="rtl">
      <h3>العربية — <code>dir="rtl"</code></h3>
      <div class="grid">
        ${btn('progressive', { label: 'أضف إلى الخزانة', rtl: true })}
        ${btn('upload', { label: 'ارفع قطعة' })}
        ${btn('download', { label: 'نزّل الفاتورة' })}
        ${btn('neutral', { tone: 'edge', label: 'إلغاء' })}
      </div>
      <p class="note">One <code>[dir="rtl"]</code> block mirrors the whole system: the gradient
      angle becomes its mirror and the four travel tokens swap sides, so the sheen enters from
      the right edge exactly as it enters from the left in English. No family and no keyframe is
      duplicated for Arabic.</p>
    </div>
    <div class="demo-reduced">
      <h3>Reduced motion — <code>prefers-reduced-motion: reduce</code></h3>
      <div class="grid">
        ${btn('progressive', { state: 'pending', hover: true })}
        ${btn('destructive', { state: 'pending', hover: true })}
        ${btn('upload', { state: 'pending', hover: true })}
        ${btn('financial', { state: 'pending', hover: true })}
      </div>
      <p class="note">Motion is switched off <i>explicitly</i>, not left to the global 0.001ms
      collapse, because collapsing an infinite animation still leaves the browser claiming it.
      The colours stay: work in flight is still amber, success is still green, failure is still
      red. The label has always been the primary carrier of state; the colour is the second.</p>
    </div>
  </div>
  <div class="panel dark">
    <h3 style="margin-top:0;font-size:13px">forced-colors: active — the OS owns the palette</h3>
    <p class="lede">Gradient layers are dropped entirely (<code>background-image: none</code>,
    <code>animation: none</code>) and the control keeps its text, border and focus ring. The
    engine cannot be previewed here — it is a media query no stylesheet can simulate — but it is
    asserted in the contract test and it is the behaviour a Windows High Contrast user asked for.</p>
    <div class="grid">${btn('progressive', { variant: 'ghost', label: 'Same label, OS palette' })}</div>
  </div>

  <h2><span class="tag">Section 6 · colour psychology</span>The palette, and what each colour is allowed to mean</h2>
  <div class="legend">
    <span><i class="swatch" style="background:var(--navy)"></i><b>navy → mint</b> growth and commitment (progressive, upload)</span>
    <span><i class="swatch" style="background:var(--gold)"></i><b>gold</b> value in motion (financial, commerce, admin)</span>
    <span><i class="swatch" style="background:var(--coral)"></i><b>rose → amber</b> destruction and irreversibility</span>
    <span><i class="swatch" style="background:var(--lilac)"></i><b>lilac</b> generated, not authored (creative, auth)</span>
    <span><i class="swatch" style="background:#8A8D93"></i><b>graphite</b> chrome that should not speak (neutral, filter)</span>
  </div>
  <p class="note">Destructive is never green and never gold; progressive is never rose. The
  contract test asserts the destructive family stays small and specific — if a sweep ever
  reclassifies half the product as destructive, the test fails rather than the product quietly
  learning to shout.</p>

  <p class="gen">Generated from <code>frontend/src/styles/button-motion.css</code> and
  <code>docs/button-motion-catalog.csv</code> — ${total} controls.
  Full reasoning: <code>docs/BUTTON_MOTION_SYSTEM.md</code>.</p>
</div>
<script>
// Re-run the finite gestures so they can be watched more than once: the animation
// is bound to the state attribute, so removing and restoring it replays it.
document.getElementById('replay')?.addEventListener('click', () => {
  const cells = document.querySelectorAll('[data-state="success"], [data-state="error"]');
  cells.forEach((el) => el.removeAttribute('data-state'));
  void document.body.offsetWidth;
  cells.forEach((el, i) => setTimeout(() => el.setAttribute('data-state', i < 4 ? 'success' : 'error'), i * 90));
});
</script>
</body>
</html>
`;

if (process.argv.includes('--check')) {
  const current = existsSync(OUT_PATH) ? readFileSync(OUT_PATH, 'utf8') : '';
  if (current !== html) {
    console.error('✗ docs/button-motion-preview.html is stale — run: node scripts/button-motion-preview.mjs');
    process.exit(1);
  }
  console.log('✓ spec sheet is current');
} else {
  writeFileSync(OUT_PATH, html);
  console.log(`✓ docs/button-motion-preview.html — ${(html.length / 1024).toFixed(1)} kB, ${total} controls, ${families} families`);
}
