#!/usr/bin/env node
/**
 * apply-button-motion — assign a semantic motion intent to every functional
 * control in the app (Part 1 of the button-animation system).
 *
 * WHY A CODEMOD AND NOT 300 HAND EDITS
 * ------------------------------------
 * The system is opt-in per control via one attribute, `data-motion="<intent>"`.
 * Applying that by hand across ~310 buttons in 90 files is unreviewable: a
 * reviewer cannot tell a deliberate `neutral` from a forgotten default. So the
 * assignment is a *table* — the rules below, evaluated in order — and the tool
 * emits evidence: a per-control report (CSV) and a role × intent summary. The
 * table is the diff you review; the source edit is mechanical.
 *
 * RULES OF ENGAGEMENT
 * -------------------
 *   · Additive only. The tool inserts attributes into the opening tag; it
 *     never rewrites a className, a handler or a child.
 *   · Idempotent. A control that already declares `data-motion` is left alone,
 *     so the tool can be re-run after new controls land.
 *   · Nothing is silent. Every control is assigned, or is printed as skipped
 *     with its file and line.
 *   · Semantic signals only: the resolved English label (from en.json), the
 *     i18n key, the accessible name and the click handler. The file path is
 *     NOT part of the vocabulary haystack — that made every control in
 *     `CheckoutView.tsx` read as "checkout" — it is used only as a documented
 *     last-resort default by surface role.
 *   · Comments are masked before scanning. `<button>` appears inside this
 *     repo's docblocks ("...renders a real <Link> when `to` is given, else a
 *     <button>"), and a naive scan of those spans silently skipped real
 *     controls that followed them.
 *
 * Usage
 *   node scripts/apply-button-motion.mjs                 # dry run + summary
 *   node scripts/apply-button-motion.mjs --report a.csv  # dry run + CSV
 *   node scripts/apply-button-motion.mjs --write         # apply the edits
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'src');
const WRITE = process.argv.includes('--write');
const REPORT = (() => {
  const i = process.argv.indexOf('--report');
  return i > -1 ? process.argv[i + 1] : null;
})();
/* `--json <path>` exists so the contract test can use THIS tool as the single
   oracle for coverage: one parser, one rule table, no duplicated heuristics
   that can drift apart. */
const JSON_OUT = (() => {
  const i = process.argv.indexOf('--json');
  return i > -1 ? process.argv[i + 1] : null;
})();
const QUIET = process.argv.includes('--quiet');

/* ── locale resolution ─────────────────────────────────────────────────────
   `t('outfit_builder.save_outfit')` resolves to "Save outfit", which the
   intent rules can read. A raw dotted key never can. */
const EN = JSON.parse(fs.readFileSync(path.join(SRC, 'i18n/en.json'), 'utf8'));
const flat = (o, p = '') =>
  Object.entries(o).reduce((acc, [k, v]) => {
    const kk = p ? `${p}.${k}` : k;
    return typeof v === 'object' && v !== null
      ? { ...acc, ...flat(v, kk) }
      : { ...acc, [kk]: v };
  }, {});
const T = flat(EN);

/* ── attribute-first rules ─────────────────────────────────────────────────
   Facts a control publishes about itself beat any amount of vocabulary. */
const ATTRIBUTE_RULES = [
  [/aria-pressed/, 'filter', 'aria-pressed'],
  [/role="switch"/, 'filter', 'role=switch'],
  [/aria-checked/, 'filter', 'aria-checked'],
  [/aria-selected/, 'filter', 'aria-selected'],
  [/onClick=\{[^}]*\b(toggleSort|setSort|sortBy|setFilter|setFilters|setWindow|setPage|setTab|selectTab|setView|setActive|setSelected|setIndex|setCurrent)\b/, 'filter', 'sort/tab/selection handler'],
  [/onClick=\{[^}]*fileInputRef\.current\?\.click\(\)/, 'upload', 'file-input trigger'],
  [/onClick=\{[^}]*\.current\?\.click\(\)/, 'upload', 'file-input trigger'],
];

/* ── vocabulary table ──────────────────────────────────────────────────────
   Ordered most-specific first; the first match wins. Read top to bottom as
   the precedence contract: money before everything, second chances before the
   verb they repeat, identity before the destructive words it borrows. */
const INTENTS = [
  ['financial', /\b(checkout|check out|place (the )?order|pay now|payment|purchase|buy now|confirm (order|payment)|top ?up|wallet|add funds|order total|proceed to checkout)\b/],
  ['recovery', /\b(retry|try again|re-?try|refresh( data)?|reload|resend|re-?send|undo|restore|resume|restart|start over)\b/],
  ['auth', /\b(sign ?-?in|sign ?-?up|log ?-?in|log ?-?out|register|verify( email| code| account| &| and)?|otp|mfa|two-factor|2fa|pass(word|phrase)|forgot|reset link|send code|email code|continue with|switch account|re-?authenticate|create (an )?account|create new account)\b/],
  ['upload', /\b(upload|import|attach|add (photo|image|picture)|choose (a )?(file|photo|image)|browse (files|images)|take photo|camera|capture|live scan|drag or press|drag (and|&) drop)\b/],
  ['download', /\b(download|export|invoice|receipt|report \(pdf\)|report pdf|pdf|save pdf|csv)\b/],
  ['creative', /\b(try ?-?on|virtual try|stylist|style (me|what i own|an outfit)|generate|regenerate|re-?generate|analy[sz]e|describe|suggest|recommend|complete the look|look ideas|photo match|fit check|visual(ly)? (search|similar)|with ai|auto-?tag|ask )\b/],
  ['share', /\b(share|invite|copy link|copy|refer|whatsapp|native share)\b/],
  ['commerce', /\b(add to (bag|cart|wardrobe|look)|wishlist|favourites?|favorites?|follow|unfollow|quantity|increase|decrease|apply (coupon|code|promo)|coupon|promo code|bag|cart|save piece|save item)\b/],
  ['destructive', /\b(delete|remove|revoke|archive|deactivate|disconnect|unlink|discard|withdraw|destroy|unpublish|suspend|clear (all|canvas|my|cache)|reset (all|data|account|everything))\b/],
  ['admin', /\b(approve|reject|publish|feature|unfeature|grant|promote|launch|bulk|placement|sponsored( slot)?|campaign|partner|store|brand|sku|stock|inventory|audit|governance|tags?|add product|create store|audit log|edit stock)\b/],
  ['filter', /\b(filters?|clear filters|sort by|sort|fit (preference|type)|unit|size|colour|color|occasion|category|all time|most recent|window|range|chips?|segment|per page)\b/],
  ['neutral', /\b(close|dismiss|cancel|back|next|previous|prev|skip|show more|show less|see more|load more|view more|expand|collapse|sidebar|paginate|page \d|first|last|step|ok|got it|no thanks|not now|maybe later)\b/],
  ['progressive', /\b(save|update|apply|confirm|submit|create|add|new|start|finish|complete|send|keep|allow|accept|agree|enable|activate|yes|proceed|explore|view (details|all|look|product)|continue|try|retake|retry)\b/],
];

/**
 * Which geometry the wash uses, from the control's OWN styling.
 *
 *   icon → the control has no label: the wash blooms from the centre (an icon
 *          is a graphic, and WCAG 1.4.11 asks 3:1 of it, which the tint holds).
 *   edge → the control's label is a medium-tone grey. A field tint behind
 *          slate-500 drops it to ~4.0:1 (measured); the wash becomes an edge
 *          stroke instead, where no label can sit. This is the one rule in
 *          this file that exists because a measurement failed.
 *          `brand-muted` is in the same class on purpose: it is the UI audit's
 *          AA-safe replacement for slate-400/500 (6.70:1 on white), so a
 *          migrated control keeps the geometry it was measured with instead of
 *          silently switching from an edge stroke to a field wash.
 *   auto → the field wash. Safe for the other two label classes by
 *          measurement: dark labels gain contrast as the surface darkens, and
 *          light labels sit on fills with a 15:1 budget.
 */
const MEDIUM_TONE_LABEL = /text-(slate-(300|400|500)|brand-muted)\b/;

function toneFor(control) {
  if (control.isIconOnly) return 'icon';
  if (MEDIUM_TONE_LABEL.test(control.className)) return 'edge';
  return 'auto';
}

/** Last resort: the role of the surface the control lives on. */
function roleDefault(file) {
  if (/components\/tryon\/|components\/stylist\/|components\/outfit\//.test(file)) {
    return ['creative', 'role-default(generative surfaces)'];
  }
  if (/views\/b2b\/|components\/admin\//.test(file)) {
    return ['admin', 'role-default(brand/admin console)'];
  }
  if (/views\/auth\//.test(file)) return ['auth', 'role-default(auth surface)'];
  if (/views\/consumer\/|components\/(commerce|product|wardrobe)\//.test(file)) {
    return ['progressive', 'role-default(consumer surface)'];
  }
  return ['neutral', 'role-default(shared chrome)'];
}

function intentFor(control) {
  // A control that already declares an intent keeps it, and the report keeps
  // reporting it: the tool is a coverage oracle for CI, so a second run must
  // still describe the whole catalog, not just the diff.
  const declared = control.attrs.match(/\bdata-motion="([a-z]+)"/);
  if (declared) return { intent: declared[1], reason: 'already-set', alreadySet: true };

  // "Back to sign in" is navigation, however many auth words follow it.
  if (/^(back|next|previous|prev|close|cancel|dismiss|skip|continue)\b/i.test(control.label.trim())) {
    return { intent: 'neutral', reason: 'leading navigation verb' };
  }
  if (control.isIconOnly && /close|dismiss|cancel|remove/i.test(control.ariaText)) {
    return { intent: control.ariaText === '' ? 'neutral' : 'neutral', reason: 'icon-only dismiss' };
  }
  for (const [re, intent, reason] of ATTRIBUTE_RULES) {
    if (re.test(control.attrs)) return { intent, reason, alreadySet: false };
  }
  for (const [intent, re] of INTENTS) {
    const m = control.hay.match(re);
    if (m) return { intent, reason: `“${m[0].trim()}”`, alreadySet: false };
  }
  const [intent, reason] = roleDefault(control.file);
  return { intent, reason, alreadySet: false };
}

/* ── source scanning ───────────────────────────────────────────────────────
   Comments and string literals are replaced by spaces (same length, so every
   index still points at the original source) before anything is searched:
     · this repo documents elements in docblocks — "<button>", "<ActionButton>"
     · a className or a regex in source can contain ">" or "<button" too.
   Scanning the mask but editing the original keeps both properties: no false
   positives, byte-accurate edits. */
function mask(src) {
  // Only `/* … */` spans are masked. This repo documents elements inside
  // docblocks and JSX comments, and both are block comments. Strings are
  // deliberately NOT masked: a first attempt did, and an apostrophe in JSX
  // text ("we don't") opened a phantom string that swallowed 13 real controls
  // in three files. An over-eager masker hid work; a narrow one cannot.
  const isCommentStart = (i) => {
    if (src[i] !== '/' || src[i + 1] !== '*') return false;
    // A comment OPENS after whitespace, `{`, `(`, `,`, `;`, `:` or at the
    // start of the file. It does NOT open inside a string — `accept="image/*"`
    // is a MIME wildcard, and treating it as a comment swallowed nine real
    // controls in VisualSearchModal.
    const prev = src[i - 1];
    const next = src[i + 2] ?? ' ';
    if (prev !== undefined && !/[\s{(*,;:=]/.test(prev)) return false;
    return next !== '"' && next !== "'" && next !== '/';
  };
  const out = src.split('');
  let i = 0;
  while (i < src.length) {
    if (isCommentStart(i)) {
      let j = src.indexOf('*/', i + 2);
      if (j === -1) j = src.length - 2;
      for (let k = i; k < j + 2 && k < out.length; k++) if (out[k] !== '\n') out[k] = ' ';
      i = j + 2;
      continue;
    }
    i++;
  }
  return out.join('');
}

function scanElements(src) {
  const m = mask(src);
  const out = [];
  const skipped = [];
  let i = 0;

  /**
   * Finds the index of the `>` that closes the tag opened at `from`.
   * A token-level walk, not a regex: attribute values legitimately contain
   * `>`, `{`, `}` and `${}` — `onClick={() => x > 1}` and
   * `className={`… ${cond ? 'a' : 'b'}`}` both occur in this codebase, and a
   * brace-depth counter alone reads the `${` inside a template literal as a
   * JSX expression and loses every `>` after it.
   */
  function tagEnd(from) {
    let depth = 0;
    let mode = 'code'; // code | sq | dq | tpl
    const stack = []; // template literals we are currently inside of
    for (let j = from; j < m.length; j++) {
      const c = m[j];
      const prev = m[j - 1];
      if (mode === 'sq' || mode === 'dq') {
        if (c === (mode === 'sq' ? "'" : '"') && prev !== '\\') mode = 'code';
        continue;
      }
      if (mode === 'tpl') {
        if (c === '\\') { j++; continue; }
        if (c === '`') { mode = 'code'; continue; }
        // `${` opens a nested expression: remember the mode AND the brace
        // depth we came from, or the `}` that closes the expression is read
        // as closing the attribute block and the tag end is missed.
        if (c === '$' && m[j + 1] === '{') { stack.push([mode, depth]); mode = 'code'; depth = 0; j++; continue; }
        continue;
      }
      // A line comment inside an attribute value (they are common in this
      // repo's handler bodies) must be skipped as a whole: the apostrophe in
      // a comment like "A swipe's trailing click…" otherwise opens a phantom
      // string and the lexer loses the tag end entirely.
      if (c === '/' && m[j + 1] === '/') {
        const nl = m.indexOf('\n', j);
        if (nl === -1) break;
        j = nl;
        continue;
      }
      if (c === "'") { mode = 'sq'; continue; }
      if (c === '"') { mode = 'dq'; continue; }
      if (c === '`') { mode = 'tpl'; continue; }
      if (c === '{') { depth++; continue; }
      if (c === '}') {
        if (depth === 0 && stack.length) { [mode, depth] = stack.pop(); continue; }
        depth--;
        continue;
      }
      if (c === '>' && depth === 0) return j;
    }
    return -1;
  }

  while ((i = m.indexOf('<button', i)) !== -1) {
    const j = tagEnd(i + '<button'.length);
    if (j === -1) {
      skipped.push({ line: src.slice(0, i).split('\n').length, why: 'unterminated tag' });
      break;
    }
    // `<button … />` is real here (the try-on keyframe scrubber, the PDP zoom
    // surface) and has no closing tag; requiring one made the scanner swallow
    // the NEXT real control into the previous element's span.
    const selfClosing = m[j - 1] === '/';
    const attrsEnd = selfClosing ? j - 1 : j;
    const closeAt = selfClosing ? j : m.indexOf('</button>', j);
    if (
      closeAt === -1 ||
      (!selfClosing && closeAt - j > 6000) ||
      !/[={]/.test(m.slice(i, attrsEnd))
    ) {
      // The only thing this rejects in practice is prose ABOUT a button
      // (docblocks) — reported, never silent.
      skipped.push({ line: src.slice(0, i).split('\n').length, why: 'not an element' });
      i = j;
      continue;
    }
    out.push({
      start: i,
      attrs: src.slice(i + '<button'.length, attrsEnd),
      inner: selfClosing ? '' : src.slice(j + 1, closeAt),
      selfClosing,
      line: src.slice(0, i).split('\n').length,
    });
    i = closeAt;
  }
  return { elements: out, skipped };
}

/* ── describe one control ──────────────────────────────────────────────── */
const stripComments = (s) => s.replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ');

const text = (s) =>
  stripComments(s)
    .replace(/<[^>]+>/g, ' ')
    .replace(/\{\s*t\(\s*['"]([^'"]+)['"]\s*\)\s*\}/g, (_, k) => T[k] ?? k)
    .replace(/\{[^{}]*\}/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

function describe(rel, el) {
  const { attrs, inner } = el;
  const keys = [...(inner + attrs).matchAll(/t\(\s*['"]([a-z0-9_.\-:]+)['"]/gi)].map((mm) => mm[1]);
  const resolved = keys.map((k) => T[k] ?? k.replace(/[._]/g, ' '));
  const aria = (attrs.match(/aria-label=\{?t\(\s*['"]([^'"]+)['"]/) || attrs.match(/aria-label=\{?['"]([^'"]+)['"]/) || [])[1];
  const ariaText = aria ? T[aria] ?? aria.replace(/[._]/g, ' ') : '';
  const handler = (attrs.match(/onClick=\{([^}]{0,90})/) || [])[1] || '';
  const bare = text(inner);
  // A label made only of symbols (✕, +, −, ↩, ⬇) is a glyph, not copy: it
  // gets the icon geometry, because there is no text for a field tint to
  // cost contrast against. Anything with a letter or a digit is a label.
  const isIconOnly = bare.length === 0 || !/[\p{L}\p{N}]/u.test(bare);
  // The control's own className — the tone rule reads the label colour from
  // it. Both the static and the template-literal form are captured.
  const className = (attrs.match(/className="([^"]*)"/) || attrs.match(/className=\{`([^`]*)`/) || [])[1] ?? '';
  const label = bare || resolved.join(' · ') || ariaText || '(icon-only)';
  const hay = [bare, resolved.join(' '), ariaText, handler].filter(Boolean).join(' ').toLowerCase();
  return { label, keys, ariaText, handler, isIconOnly, hay, className, attrs, file: rel };
}

/* ── walk the source tree ──────────────────────────────────────────────── */
function sources(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === '__tests__' || e.name === 'node_modules') continue;
      out.push(...sources(p));
    } else if (e.name.endsWith('.tsx') && !e.name.includes('.test.')) {
      out.push(p);
    }
  }
  return out;
}

const roleOf = (rel) => {
  if (rel.includes('/views/consumer/')) return 'Consumer';
  if (rel.includes('/views/b2b/')) return 'Brand / Admin console';
  if (rel.includes('/views/auth/')) return 'Auth';
  if (rel.includes('/views/public/') || rel.includes('/views/legal/')) return 'Public / Legal';
  if (rel.includes('/components/tryon/') || rel.includes('/components/commerce/') || rel.includes('/components/product/')) return 'Consumer (shared components)';
  if (rel.includes('/components/admin/')) return 'Admin (components)';
  if (rel.includes('/components/stylist/') || rel.includes('/components/outfit/')) return 'AI Stylist / Outfit';
  return 'Shared UI';
};

const rows = [];
const allSkipped = [];
let edited = 0;
let touched = 0;
const files = sources(SRC).sort();

for (const file of files) {
  const rel = path.relative(ROOT, file);
  const src = fs.readFileSync(file, 'utf8');
  const { elements, skipped } = scanElements(src);
  for (const s of skipped) allSkipped.push({ file: rel, line: s.line });
  if (!elements.length) continue;

  let next = src;
  let shifted = 0;
  let fileEdits = 0;

  for (const el of elements) {
    const c = describe(rel, el);
    const { intent, reason, alreadySet } = intentFor(c);
    const tone = toneFor(c);
    const toneDeclared = (c.attrs.match(/data-motion-tone="([a-z]+)"/) || [])[1] ?? 'auto';
    // Two independent things can be missing: the intent, and the geometry the
    // intent needs. A control that declares an intent but the wrong geometry is
    // just as unmeasured as one with no intent at all.
    const needsEdit = !alreadySet || toneDeclared !== tone;
    rows.push({
      role: roleOf(rel), file: rel, line: el.line, label: c.label.replace(/\s+/g, ' ').slice(0, 90),
      intent, reason, alreadySet: !needsEdit, tone, glyphOnly: c.isIconOnly,
      className: c.className.slice(0, 160),
      handler: c.handler.replace(/\s+/g, ' ').slice(0, 60),
    });
    if (!needsEdit) continue;
    // Insert ONLY what is missing. A tone repair on a control that already
    // declares its intent must not restate `data-motion` — JSX rejects a
    // duplicated attribute, and the earlier version of this line did exactly
    // that across 26 controls (caught by `tsc`, then fixed here).
    const missing = [
      ...(alreadySet ? [] : [`data-motion="${intent}"`]),
      ...(tone !== 'auto' && toneDeclared !== tone ? [`data-motion-tone="${tone}"`] : []),
    ];
    if (tone === 'auto' && toneDeclared !== 'auto') {
      // Stale geometry: the control no longer needs a variant at all.
      next = next.replace(
        new RegExp(` data-motion-tone="${toneDeclared}"`),
        '',
      );
    }
    const insert = missing.length ? ` ${missing.join(' ')}` : '';
    if (!insert) continue;
    const at = el.start + '<button'.length + shifted;
    next = next.slice(0, at) + insert + next.slice(at);
    shifted += insert.length;
    fileEdits++;
  }

  if (fileEdits) {
    touched++;
    edited += fileEdits;
    if (WRITE) fs.writeFileSync(file, next);
  }
}

/* ── evidence ───────────────────────────────────────────────────────────── */
const byIntent = rows.reduce((a, r) => ({ ...a, [r.intent]: (a[r.intent] ?? 0) + 1 }), {});
const alreadySet = rows.filter((r) => r.alreadySet).length;
const byRole = rows.reduce((a, r) => ({ ...a, [r.role]: (a[r.role] ?? 0) + 1 }), {});
const byReason = rows.reduce((a, r) => ({ ...a, [r.reason]: (a[r.reason] ?? 0) + 1 }), {});
const needEdits = rows.filter((r) => !r.alreadySet);

console.log(`\n${WRITE ? 'APPLIED' : 'DRY RUN'} · ${rows.length} controls · ${edited} assignments · ${touched} files edited`);
console.log(`coverage: ${rows.length - needEdits.length}/${rows.length} controls already declare an intent\n`);
console.log('intent            count');
for (const [k, v] of Object.entries(byIntent).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${k.padEnd(16)} ${String(v).padStart(4)}`);
}
console.log('\nrole                          count');
for (const [k, v] of Object.entries(byRole).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${k.padEnd(28)} ${String(v).padStart(4)}`);
}
console.log('\nhow each control was decided');
for (const [k, v] of Object.entries(byReason).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${String(v).padStart(4)}  ${k}`);
}
if (needEdits.length) {
  console.log(`\nstill needing an intent: ${needEdits.length}`);
  for (const r of needEdits.slice(0, 20)) console.log(`  ${r.file}:${r.line}  → ${r.intent}  (${r.reason})`);
  if (needEdits.length > 20) console.log(`  … +${needEdits.length - 20}`);
}

if (allSkipped.length) {
  console.log(`\nskipped (not a real element — prose about a <button>): ${allSkipped.length}`);
  for (const s of allSkipped) console.log(`  ${s.file}:${s.line}`);
}

if (JSON_OUT) {
  fs.writeFileSync(
    JSON_OUT,
    JSON.stringify(
      {
        totals: { controls: rows.length, assignments: edited, files: touched },
        byIntent,
        byRole,
        byReason,
        skipped: allSkipped,
        // The controls that still need an intent are exactly the ones the tool
        // would have to edit — this is what the contract test asserts is zero.
        needEdits: rows.filter((r) => !r.alreadySet),
        rows,
      },
      null,
      1,
    ),
  );
}

if (REPORT) {
  const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
  fs.writeFileSync(
    REPORT,
    'role,file,line,intent,tone,label,reason,handler\n' +
      rows.map((r) => [r.role, r.file, r.line, r.intent, r.tone, r.label, r.reason, r.handler].map(esc).join(',')).join('\n') +
      '\n',
  );
  console.log(`\nreport → ${REPORT}`);
}
if (!WRITE && !QUIET) console.log('\n(dry run — pass --write to apply)\n');
