#!/usr/bin/env node
/**
 * i18n gate — static completeness + parity verification for every locale.
 *
 * WHY THIS EXISTS (audit 2026-09-21, finding "العربية غير متكافئة" / i18n parity):
 *   The report could not tell whether the Arabic bundle was a real translation
 *   or an English fallback, because nothing in the repository measured it. The
 *   frontend used 261 distinct t() keys while en.json only defined 173, and no
 *   gate compared the two locale files at all. `parseMissingKeyHandler`
 *   papered over the gap by humanizing the key, so a missing Arabic string
 *   shipped as English text with a green CI.
 *
 *   A translation that cannot be measured is a claim, not a feature. This
 *   script is the measurement. It is deterministic, dependency-free (Node
 *   stdlib only) and runs in CI on every push/PR.
 *
 * CONTRACT (each check fails the build):
 *   1. Every literal t('a.b.c') / i18n.t('a.b.c') key referenced anywhere in
 *      frontend/src must exist in en.json. A key in code but not in the
 *      source-of-truth bundle is a guaranteed runtime fallback.
 *   2. en.json and ar.json must have EXACTLY the same flattened key set.
 *      Extra keys in a locale are drift too, not just missing ones.
 *   3. No leaf value may be empty, whitespace-only, or still equal to its
 *      English counterpart in a non-English locale unless it is listed as an
 *      intentional loanword in NON_TRANSLATABLE below.
 *   4. No leaf value may be a raw dotted key (the "nav.wardrobe on screen"
 *      failure class) and no value may contain unfilled {{placeholders}}
 *      that the English source does not also declare.
 *   5. RATCHET — a user-facing string that bypasses i18n entirely
 *      (`showToast('Added to bag')`, `message: 'A name is required.'`,
 *      `new Error('...')`, a hard-coded `aria-label="Close"`) fails the build
 *      unless it is already recorded in i18n-baseline.json. The baseline is a
 *      debt register, not an allowlist: it may only ever SHRINK. Removing an
 *      entry requires fixing the call site; adding one requires a reviewer to
 *      accept new untranslated UI copy in a bilingual product.
 *
 * Usage:  node scripts/check_i18n.mjs [--json] [--update-baseline]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(HERE, '..');
const SRC_DIR = path.join(FRONTEND_ROOT, 'src');
const I18N_DIR = path.join(SRC_DIR, 'i18n');
const SOURCE_LOCALE = 'en';

/**
 * Leaf values that are legitimately identical across locales: brand names,
 * format codes and technical tokens. Anything added here is an explicit,
 * reviewable decision — never a silent skip.
 */
const NON_TRANSLATABLE = new Set([
  'nav.bopis_pickup',
  'commerce.bopis',
  'commerce.bnpl_tabby',
  'commerce.bnpl_tamara',
  'commerce.apple_pay',
  'commerce.cod',
  'footer.bnpl_brand_name',
  'common.email',
  'common.password',
]);

const problems = [];
const notes = [];

function fail(check, message, detail) {
  problems.push({ check, message, ...(detail ? { detail } : {}) });
}

function flatten(obj, prefix = '', out = {}) {
  for (const [key, value] of Object.entries(obj)) {
    const keyPath = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value, keyPath, out);
    } else {
      out[keyPath] = value;
    }
  }
  return out;
}

function readJson(file) {
  const raw = fs.readFileSync(file, 'utf8');
  try {
    return JSON.parse(raw);
  } catch (err) {
    fail('json', `${path.relative(FRONTEND_ROOT, file)} is not valid JSON`, err.message);
    return null;
  }
}

/** Recursively collect every .ts/.tsx file under src, excluding tests. */
function collectSources(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      collectSources(full, acc);
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name)) {
      acc.push(full);
    }
  }
  return acc;
}

/**
 * Extract literal translation keys from source.
 *
 * Matches:  t('a.b')  t("a.b")  i18n.t('a.b')  t('a.b', {...})
 * Uses a namespace-or-dotted-identifier shape so that `t(` in other call
 * sites (e.g. a local function named `t`) cannot produce false positives
 * without at least one dot — every key in this project is namespaced.
 */
const KEY_CALL_RE = /(?<![A-Za-z0-9_$.])(?:i18n\.)?t\(\s*['"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"]/g;

function extractKeys() {
  const found = new Map(); // key -> Set(relative file)
  for (const file of collectSources(SRC_DIR)) {
    const text = fs.readFileSync(file, 'utf8');
    let m;
    while ((m = KEY_CALL_RE.exec(text)) !== null) {
      const key = m[1];
      if (!found.has(key)) found.set(key, new Set());
      found.get(key).add(path.relative(FRONTEND_ROOT, file));
    }
  }
  return found;
}

/** Keys passed through i18n at runtime (computed) — counted, not verified. */
const DYNAMIC_PATTERNS = [
  /t\(\s*`([^`]+)`/g, // template literals
];

function main() {
  const asJson = process.argv.includes('--json');

  const localeFiles = fs
    .readdirSync(I18N_DIR)
    .filter((f) => f.endsWith('.json'))
    .sort();
  const locales = Object.fromEntries(
    localeFiles.map((f) => [path.basename(f, '.json'), readJson(path.join(I18N_DIR, f))]),
  );

  if (!locales[SOURCE_LOCALE]) {
    fail('locales', `source locale ${SOURCE_LOCALE}.json is missing from ${path.relative(FRONTEND_ROOT, I18N_DIR)}`);
    return report(asJson, {}, {}, []);
  }

  const flat = Object.fromEntries(
    Object.entries(locales).map(([name, json]) => [name, json ? flatten(json) : {}]),
  );
  const sourceKeys = Object.keys(flat[SOURCE_LOCALE]).sort();

  // ---- Check 1: every key used in code exists in the source locale ----
  const usedKeys = extractKeys();
  const usedButUndefined = [];
  for (const [key, files] of [...usedKeys].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (!(key in flat[SOURCE_LOCALE])) {
      usedButUndefined.push({ key, files: [...files] });
    }
  }
  for (const { key, files } of usedButUndefined) {
    fail('used-not-defined', `t('${key}') is used in code but missing from ${SOURCE_LOCALE}.json`, files.join(', '));
  }

  // ---- Check 2: locale parity (missing AND extra) ----
  for (const [name, leaves] of Object.entries(flat)) {
    if (name === SOURCE_LOCALE) continue;
    const keys = new Set(Object.keys(leaves));
    const missing = sourceKeys.filter((k) => !keys.has(k));
    const extra = [...keys].filter((k) => !(k in flat[SOURCE_LOCALE])).sort();
    if (missing.length) {
      fail('parity', `${name}.json is missing ${missing.length} key(s) present in ${SOURCE_LOCALE}.json`, missing.slice(0, 20).join(', ') + (missing.length > 20 ? ` … +${missing.length - 20}` : ''));
    }
    if (extra.length) {
      fail('parity', `${name}.json has ${extra.length} key(s) not present in ${SOURCE_LOCALE}.json (drift)`, extra.slice(0, 20).join(', ') + (extra.length > 20 ? ` … +${extra.length - 20}` : ''));
    }
  }

  // ---- Check 3: no empty / raw-key / untranslated leaves ----
  for (const [name, leaves] of Object.entries(flat)) {
    for (const [key, value] of Object.entries(leaves)) {
      if (typeof value !== 'string') {
        fail('type', `${name}.json → ${key} is not a string (${typeof value})`);
        continue;
      }
      if (value.trim() === '') {
        fail('empty', `${name}.json → ${key} is empty`);
        continue;
      }
      // A value that looks like the key itself means the fallback leaked in.
      if (value === key || /^[a-z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$/.test(value.trim())) {
        fail('raw-key', `${name}.json → ${key} renders a raw dotted key ("${value}") instead of human text`);
        continue;
      }
      if (
        name !== SOURCE_LOCALE &&
        value === flat[SOURCE_LOCALE][key] &&
        !NON_TRANSLATABLE.has(key) &&
        /[A-Za-z]/.test(value)
      ) {
        fail('untranslated', `${name}.json → ${key} is still the English source text ("${value}") — translate it or add it to NON_TRANSLATABLE`);
      }
    }
  }

  // ---- Check 4: interpolation placeholders match the source locale ----
  const placeholder = (s) => (s.match(/\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g) || []).map((p) => p.replace(/[{}\s]/g, '')).sort().join(',');
  for (const [name, leaves] of Object.entries(flat)) {
    if (name === SOURCE_LOCALE) continue;
    for (const [key, value] of Object.entries(leaves)) {
      const src = flat[SOURCE_LOCALE][key];
      if (typeof src !== 'string' || typeof value !== 'string') continue;
      if (placeholder(src) !== placeholder(value)) {
        fail('placeholder', `${name}.json → ${key} placeholders [${placeholder(value)}] do not match ${SOURCE_LOCALE} [${placeholder(src)}]`);
      }
    }
  }

  // ---- Check 5: dead keys (defined but never referenced) — reported, not fatal ----
  const dead = sourceKeys.filter((k) => !usedKeys.has(k));
  if (dead.length) notes.push({ kind: 'dead-keys', message: `${dead.length} key(s) defined but never referenced via a literal t('…') call`, keys: dead });

  // ---- Check 6: the ratchet against new untranslated user-facing copy ----
  const untranslatedAdded = checkRatchet();

  return report(
    asJson,
    flat,
    { usedCount: usedKeys.size, sourceCount: sourceKeys.length, untranslatedAdded },
    dead,
  );
}


/* ───────────────────────── i18n ratchet ───────────────────────── */
/**
 * Slots whose value is shown to a human, by call shape:
 *
 * grep for these constructs rather than parsing with a real AST — a heuristic
 * that occasionally over-reports is acceptable here because the baseline makes
 * over-reporting a one-time, reviewable cost, whereas under-reporting would
 * silently let new English copy through. Every false positive is visible in
 * i18n-baseline.json.
 */
const USER_FACING_SLOTS = [
  { id: 'showToast', re: /showToast\(\s*(['"])([^'"`]{8,})\1/g, group: 2 },
  { id: 'aria-label', re: /aria-label=(['"])([^'"{}]{3,})\1/g, group: 2 },
  { id: 'placeholder', re: /placeholder=(['"])([^'"{}]{3,})\1/g, group: 2 },
  { id: 'title-attr', re: /\btitle=(['"])([^'"{}]{3,})\1/g, group: 2 },
  { id: 'message-field', re: /\bmessage:\s*(['"])([^'"`]{8,})\1/g, group: 2 },
  { id: 'new-Error', re: /new (?:Error|LocalizedError)\(\s*(['"])([^'"`]{8,})\1/g, group: 2 },
  // JSX text nodes. The pattern demands a capitalised, multi-word sentence
  // between tags so that TypeScript generics (Array<T>), comparisons (a > b)
  // and single-word enums do not register. Over-reporting here is cheap — the
  // baseline records it once — whereas missing it would hide most of the UI.
  { id: 'jsx-text', re: />\s*([A-Z][A-Za-z][A-Za-z''’\-]*(?:\s+[A-Za-z''’\-,.&]+){1,12}[.!?]?)\s*</g, group: 1 },
];

/** Latin words only — a translated string is recognised by its script. */
const LATIN_PROSE = /[A-Za-z]{3,}(\s+[A-Za-z]{2,})+/;

const BASELINE_PATH = path.join(FRONTEND_ROOT, 'i18n-baseline.json');

/** Stable identity that survives line-number churn and reformatting. */
function ratchetId(relFile, text) {
  return `${relFile}::${text.trim().replace(/\s+/g, ' ')}`;
}

function collectUntranslated() {
  const found = new Map();
  for (const file of collectSources(SRC_DIR)) {
    const rel = path.relative(FRONTEND_ROOT, file).split(path.sep).join('/');
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return;
      for (const slot of USER_FACING_SLOTS) {
        slot.re.lastIndex = 0;
        let m;
        while ((m = slot.re.exec(line)) !== null) {
          const text = m[slot.group];
          if (!text || !LATIN_PROSE.test(text)) continue;
          const id = ratchetId(rel, text);
          if (!found.has(id)) found.set(id, { id, file: rel, line: i + 1, slot: slot.id, text: text.trim() });
        }
      }
    });
  }
  return found;
}

function readBaseline() {
  if (!fs.existsSync(BASELINE_PATH)) return { allow: new Set(), raw: null };
  try {
    const parsed = JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf8'));
    return { allow: new Set(parsed.allow ?? []), raw: parsed };
  } catch (err) {
    fail('baseline', 'i18n-baseline.json is not valid JSON', err.message);
    return { allow: new Set(), raw: null };
  }
}

function writeBaseline(found) {
  const entries = [...found.keys()].sort();
  const payload = {
    $comment:
      'Debt register for user-facing copy that still bypasses i18n. This file may only SHRINK. ' +
      'Fix a call site (move the string into src/i18n/<locale>.json and use t()/msg()), then remove ' +
      'its entry here — run `npm run i18n:baseline` to regenerate after the fix. Adding an entry means ' +
      'accepting new untranslated UI copy in a bilingual product and must be justified in review.',
    $generated: new Date().toISOString().slice(0, 10),
    count: entries.length,
    allow: entries,
  };
  fs.writeFileSync(BASELINE_PATH, JSON.stringify(payload, null, 2) + '\n');
}

function checkRatchet() {
  const found = collectUntranslated();
  const { allow } = readBaseline();

  if (process.argv.includes('--update-baseline')) {
    writeBaseline(found);
    console.log(`i18n ratchet — baseline written with ${found.size} entr(ies).`);
    notes.push({ kind: 'ratchet-baseline-written', count: found.size });
    return found.size;
  }

  const added = [...found.values()].filter((f) => !allow.has(f.id));
  for (const item of added) {
    fail(
      'untranslated',
      `${item.slot} carries English copy that never passes through i18n: "${item.text}"`,
      `${item.file}:${item.line} — move the string into src/i18n/en.json (+ ar.json) and use t() or msg()`,
    );
  }

  const fixed = [...allow].filter((id) => !found.has(id));
  notes.push({ kind: 'ratchet', remaining: found.size, baselined: allow.size, newlyFixed: fixed.length, new: added.length });
  return added.length;
}

function report(asJson, flat, counts, dead) {
  const ok = problems.length === 0;
  if (asJson) {
    process.stdout.write(JSON.stringify({ ok, problems, notes, counts, deadKeys: dead }, null, 2) + '\n');
  } else {
    const localeNames = Object.keys(flat).sort().join(', ') || '(none)';
    console.log(`i18n gate — locales: ${localeNames}`);
    console.log(
      `i18n gate — keys used in code: ${counts.usedCount ?? '?'} · keys defined in en.json: ${counts.sourceCount ?? '?'}`,
    );
    const ratchet = notes.find((n) => n.kind === 'ratchet');
    if (ratchet) {
      console.log(
        `i18n ratchet — baselined backlog: ${ratchet.remaining} (was ${ratchet.baselined}) · ` +
          `newly untranslated in this change: ${ratchet.new}`,
      );
    }
    const deadKeys = notes.find((n) => n.kind === 'dead-keys');
    if (deadKeys) {
      console.log(`\nℹ ${deadKeys.message}:`);
      for (const k of deadKeys.keys.slice(0, 15)) console.log(`   · ${k}`);
      if (deadKeys.keys.length > 15) console.log(`   · … +${deadKeys.keys.length - 15} more`);
    }
    if (!ok) {
      console.error(`\n✖ i18n gate FAILED with ${problems.length} problem(s):\n`);
      const byCheck = problems.reduce((acc, p) => ((acc[p.check] ??= []).push(p), acc), {});
      for (const [check, list] of Object.entries(byCheck)) {
        console.error(`  [${check}] ${list.length} problem(s)`);
        for (const p of list.slice(0, 40)) {
          console.error(`    · ${p.message}`);
          if (p.detail) console.error(`      ${p.detail}`);
        }
        if (list.length > 40) console.error(`    · … +${list.length - 40} more`);
        console.error('');
      }
    } else {
      console.log('\n✔ i18n gate passed — every referenced key exists, locales are in parity, no untranslated or empty leaves.');
    }
  }
  process.exit(ok ? 0 : 1);
}

main();
