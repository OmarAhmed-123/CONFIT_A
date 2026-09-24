#!/usr/bin/env node
/**
 * Canonical consumer i18n inventory.
 *
 * WHY THIS EXISTS (final gap closure, §4/§5 of the mission)
 * ---------------------------------------------------------
 * `audit_untranslated.mjs` counts JSX text + a fixed set of attributes and
 * message props. That number (542 at 160a530) is NOT the localization surface,
 * and the mission is explicit that it must not be reported as if it were:
 *
 *   1. literals held in ARRAY/OBJECT literals that reach the render through a
 *      variable are invisible to it (measured example: HomeView's guide options
 *      — 14 strings — were only found by hand in the previous batch);
 *   2. DEFAULT PARAMETER values (`label = 'Fit'`) are invisible;
 *   3. template literals are collapsed, hiding interpolation;
 *   4. it has no notion of a CONTRACT VALUE — a string that must NOT be
 *      translated because the backend matches or receives it.
 *
 * So this tool enumerates EVERY English-looking string literal in the consumer
 * surface and CLASSIFIES it. Deletion is never a strategy here: an occurrence is
 * only ever re-classified with a stated reason.
 *
 * Classification is rule-based and deliberately conservative; `--corrections`
 * points at a JSON file of human decisions that override the rules (each entry
 * carries a reason). The point is a truthful inventory, not a small number.
 *
 * Usage:
 *   node scripts/i18n_inventory.mjs [--scope consumer|all] [--json out.json]
 *                                   [--corrections path.json]
 */
import fs from 'node:fs';
import path from 'node:path';
const REQUEST_FUNCTIONS = new Set(['sendPrompt', 'request', 'post', 'put', 'patch']);
import ts from 'typescript';

const args = process.argv.slice(2);
const flag = (name, dflt = undefined) => {
  const i = args.indexOf(name);
  return i === -1 ? dflt : args[i + 1];
};
const SRC = path.resolve(flag('--src', 'src'));
const SCOPE = flag('--scope', 'consumer');
const JSON_OUT = flag('--json', undefined);
const CORRECTIONS = flag('--corrections', undefined);

const CONSUMER_PREFIXES = [
  'src/views/consumer/',
  'src/components/navigation/ConsumerNavbar',
  'src/components/tryon/',
  'src/components/stylist/',
  'src/components/common/',
  'src/components/showcase/',
  'src/components/ui/',
  'src/views/auth/',
  'src/views/public/',
  'src/hooks/',
  'src/stores/',
  'src/lib/',
  'src/i18n/messages.ts',
  'src/services/',
];
const isConsumer = (rel) => CONSUMER_PREFIXES.some((p) => rel.startsWith(p));

/* ── attribute/prop surfaces that always reach a human ─────────────────────── */
const TEXT_ATTRS = new Set(['aria-label', 'aria-description', 'title', 'placeholder', 'alt']);
/**
 * ATTRIBUTES ARE AN ALLOW-LIST, NOT A DENY-LIST.
 *
 * The first version of this tool collected "any attribute that is not in a
 * known-code set" and immediately over-reported: `accept`, `target`, `rel`,
 * `scope`, `stroke`, `xmlns`, `theme`, `decoding`… all code, none copy. A
 * deny-list can never be complete, so the default is now "not copy" and a new
 * copy-bearing attribute has to be added here deliberately. That also makes the
 * tool's own behaviour testable: adding `data-x` to this set must change the
 * count (positive control), and removing an attribute must not silently keep
 * counting it.
 */
const MESSAGE_PROPS = new Set([
  'message', 'title', 'description', 'label', 'placeholder', 'notice', 'subtitle',
  'actionText', 'emptyText', 'confirmText', 'cancelText', 'eyebrow', 'verdict',
  'helperText', 'errorText', 'ariaLabel', 'aria-description',
]);
/** attributes whose value is code, not copy */
const CODE_ATTRS = new Set(['className', 'id', 'name', 'type', 'role', 'value', 'key', 'href', 'to', 'src', 'htmlFor', 'data-testid', 'style', 'variant', 'size', 'tone', 'as', 'method']);

/* ── patterns ──────────────────────────────────────────────────────────────── */
const HAS_ARABIC = /[\u0600-\u06FF]/;
const HAS_LATIN_WORD = /[A-Za-z]{2,}/;
const TECHNICAL = [
  /^[a-z0-9]+(_[a-z0-9]+)+$/,            // snake_case token
  /^[A-Z0-9_]{3,}$/,                     // CONSTANT_CASE
  /^(GET|POST|PUT|PATCH|DELETE)$/,
  /^(utf-8|application\/|text\/|image\/)/i,
  /^https?:\/\//,
  /^\d+(\.\d+)?(px|rem|em|%|ms|s)?$/,
  /^#[0-9A-Fa-f]{3,8}$/,
  /^[A-Za-z-]+\/[A-Za-z0-9-]+$/,         // mime-ish
  /^\{\{.*\}\}$/,
  /^[a-z][a-zA-Z0-9]*\.[a-z][a-zA-Z0-9_.]*$/,   // dotted key / css-ish
];
const PROPER_NOUNS = [
  'CONFIT', 'Tabby', 'Tamara', 'Stripe', 'PayPal', 'BOPIS', 'USP', 'GDPR',
  'Playwright', 'Redis', 'PostgreSQL', 'Vercel', 'AI', 'BNPL', 'MFA', 'TOTP',
  'Google', 'Apple', 'iOS', 'Android',
];

const CLASS_SOUP = /(^|\s)(-?[a-z]+(-[a-z0-9]+)*:)?[a-z-]+-\[[^\]]+\]|\b(px|py|mt|mb|ml|mr|gap|grid|flex|text|bg|border|rounded|shadow|w|h|max-w|min-h)-[a-z0-9-]+\b/;

/**
 * Is this string a CSS utility-class list rather than human copy?
 *
 * The previous test was "contains a utility token AND has 3+ words", which missed
 * short lists: `bg-black/70 text-white` (2 tokens) was reported as MUST_LOCALIZE
 * copy in VirtualStylistDrawer. A count threshold is the wrong shape for this
 * question — EVERY token being a utility class is the right one, and it does not
 * care how many tokens there are.
 *
 * Examples that must be class lists:  "bg-black/70 text-white", "p-3 rounded-xl"
 * Examples that must NOT be:          "Complete Look", "Navy Blue", "Try"
 */
const isUtilityToken = (tok) => {
  const t = tok.replace(/^[a-z-]+:/i, '');        // responsive/state prefixes: sm:, hover:
  if (!t || /^[A-Z]/.test(t)) return false;
  if (t.includes('/') || t.includes('[')) return true;              // bg-black/70, text-[#fff]
  return /^(bg|text|border|rounded|shadow|p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap|grid|flex|inline|block|hidden|w|h|min|max|top|bottom|left|right|z|opacity|font|leading|tracking|space|overflow|items|justify|self|absolute|relative|fixed|sticky|inset|translate|scale|transition|duration|ease|animate|ring|outline|divide|col|row)-[a-z0-9-]+$/i.test(t);
};
const isClassList = (text) => {
  const tokens = text.trim().split(/\s+/).filter(Boolean);
  return tokens.length >= 2 && tokens.every(isUtilityToken);
};
const looksTechnical = (s) => {
  const t = s.trim();
  if (!t) return true;
  // defence in depth for anything that still reaches here as a class list
  if (isClassList(t)) return true;
  if (CLASS_SOUP.test(t) && t.split(/\s+/).length >= 3) return true;
  if (TECHNICAL.some((re) => re.test(t))) return true;
  // a single token with no space that is not a known proper noun and has no
  // human-readable shape (all lower/camel and short) is code, not copy
  if (!/\s/.test(t) && t.length <= 24 && /^[a-zA-Z][a-zA-Z0-9_.-]*$/.test(t)
      && !PROPER_NOUNS.includes(t)) return true;
  return false;
};

/* ── collection ────────────────────────────────────────────────────────────── */
const findings = [];
const i18nKeys = new Set();
const files = [];
const walk = (dir) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (['__tests__', 'node_modules', 'dist'].includes(e.name)) continue;
      walk(full);
    } else if (/\.(ts|tsx|mts)$/.test(e.name) && !/\.test\.(ts|tsx)$/.test(e.name)) {
      files.push(full);
    }
  }
};
walk(SRC);

for (const file of files) {
  const rel = path.relative(process.cwd(), file).split(path.sep).join('/');
  if (SCOPE === 'consumer' && !isConsumer(rel)) continue;
  if (SCOPE === 'non-consumer' && isConsumer(rel)) continue;

  const sf = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  const line = (node) => sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
  const push = (node, kind, text, extra = {}) => {
    const clean = String(text).replace(/\s+/g, ' ').trim();
    if (!clean || !HAS_LATIN_WORD.test(clean) || HAS_ARABIC.test(clean)) return;
    findings.push({ file: rel, line: line(node), kind, text: clean, ...extra });
  };

  /** `t('a.b')` / `i18n.t('a.b')` arguments are KEYS, not copy. */
  const isTranslationKey = (node) => {
    const p = node.parent;
    if (!p || !ts.isCallExpression(p)) return false;
    const callee = p.expression.getText(sf);
    return /(^|\.)t$|translate/i.test(callee);
  };
  /** console.* literals are developer messages, never rendered. */
  const isConsoleArg = (node) => {
    let p = node.parent;
    while (p) {
      if (ts.isCallExpression(p) && /^console\./.test(p.expression.getText(sf))) return true;
      if (ts.isStatement(p)) return false;
      p = p.parent;
    }
    return false;
  };
  /** `'use client'` / `'use strict'` are directives, not copy. */
  const isDirective = (node) => {
    const p = node.parent;
    return ts.isExpressionStatement(p) && p.expression === node
      && /^(use client|use strict|use server)$/.test(node.text);
  };
  /** DOM selector strings never render. */
  const isDomSelector = (node) => {
    const p = node.parent;
    return !!p && ts.isCallExpression(p)
      && /querySelector|querySelectorAll|closest|matches|getElementsBy/.test(p.expression.getText(sf));
  };
  /** literals used to COMPARE against data (===, includes, startsWith …) are tokens. */
  const isDataComparison = (node) => {
    const p = node.parent;
    if (!p) return false;
    if (ts.isBinaryExpression(p) && ['===', '!==', '==', '!='].includes(p.operatorToken.getText(sf))) return true;
    if (ts.isCallExpression(p) && /includes|startsWith|endsWith|toLowerCase|toUpperCase|match|test|indexOf|localeCompare/.test(p.expression.getText(sf))) return true;
    if (ts.isCaseClause(p)) return true;
    return false;
  };

  /** is this literal the value of a property named `value` / a code attribute? */
  const inContractPosition = (node) => {
    let p = node.parent;
    while (p && !ts.isObjectLiteralElementLike(p)) {
      if (ts.isJsxAttribute(p)) return p.name.getText(sf) === 'value';
      p = p.parent;
    }
    if (p && ts.isPropertyAssignment(p) && p.name) {
      const n = p.name.getText(sf).replace(/['"]/g, '');
      return n === 'value' || n === 'code' || n === 'slug' || n === 'enum' || n === 'token';
    }
    return false;
  };
  /** is this literal a sibling of a `labelKey`/`label` property? */
  const nearLabelKey = (node) => {
    let p = node.parent;
    while (p && !ts.isObjectLiteralExpression(p)) p = p.parent;
    if (!p) return false;
    return p.properties.some((pr) => pr.name && /label_?key/i.test(pr.name.getText(sf)));
  };

  const visit = (node) => {
    const str = (n) =>
      ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) ? n.text : null;

    // (a) JSX text
    if (ts.isJsxText(node)) {
      const t = node.getText(sf).replace(/\s+/g, ' ').trim();
      if (t) push(node, 'jsx-text', t);
      return ts.forEachChild(node, visit);
    }

    // (b) attributes: copy vs code
    if (ts.isJsxAttribute(node)) {
      const name = node.name.getText(sf);
      // MEASURED false positive: `className={`bg-[#0F291E] border-emerald-500/40`}`
      // was collected as user-facing copy, because the earlier version only
      // filtered string *initializers* of code attributes and still descended
      // into template expressions. A class list is never copy, so these
      // attributes are not descended into at all.
      if (CODE_ATTRS.has(name)) return;
      if (node.initializer && ts.isStringLiteral(node.initializer)
          && (TEXT_ATTRS.has(name) || MESSAGE_PROPS.has(name))) {
        push(node, `attr:${name}`, node.initializer.text);
      }
      return ts.forEachChild(node, visit);
    }

    // (c) string literals anywhere else — the part the old tool missed
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const parent = node.parent;
      const isModuleSpecifier = ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent);
      const isPropName = ts.isPropertyAssignment(parent) && parent.name === node;
      const isRoute = node.text.startsWith('/') && !node.text.startsWith('//');
      if (!isModuleSpecifier && !isPropName && !isRoute) {
        if (isTranslationKey(node)) {
          i18nKeys.add(node.text);
        } else if (isDirective(node) || isDomSelector(node)) {
          push(node, 'code', node.text);
        } else if (!isConsoleArg(node) && !isDataComparison(node)) {
          const contract = inContractPosition(node);
          const labelled = nearLabelKey(node);
          const payload = requestPayloadFn(node);
          push(node, contract ? 'object:value' : labelled ? 'object:label' : 'literal', node.text, {
            contract,
            nearLabelKey: labelled,
            requestPayload: payload,
          });
        }
      }
      return ts.forEachChild(node, visit);
    }

    // (d) template literals with interpolation -> dynamic
    if (ts.isTemplateExpression(node)) {
      const raw = node.getText(sf);
      push(node, 'template', raw);
      return ts.forEachChild(node, visit);
    }

    // (e) default parameter values (`label = 'Fit'`)
    if (ts.isParameter(node) && node.initializer && ts.isStringLiteral(node.initializer)) {
      push(node, 'default-param', node.initializer.text, { param: node.name.getText(sf) });
      return ts.forEachChild(node, visit);
    }

    return ts.forEachChild(node, visit);
  };
  ts.forEachChild(sf, visit);
}

/* ── classification ────────────────────────────────────────────────────────── */
/**
 * Functions whose string arguments are REQUEST PAYLOAD, not copy.
 *
 * Measured 2026-09-24: after the stylist drawer was localized, the English strings
 * that remain in it are the ones the UI SENDS — `sendPrompt("Style an outfit for
 * …", "Work & Business")`. The backend parses those with English keyword matching,
 * so translating them would silently break occasion detection. They are contract
 * values and are reported as such, with the function name in the reason.
 */



/**
 * Is this string literal an argument to one of the API-calling helpers?
 * Walks up only as far as the nearest call expression, so it cannot misfire on
 * unrelated calls further up the tree.
 */
// A function DECLARATION, not a const arrow: the collector below runs before this
// line, so a const would be in its temporal dead zone and throw
// "Cannot access 'requestPayloadFn' before initialization" at the first literal.
function requestPayloadFn(node) {
  let p = node.parent;
  while (p && !ts.isCallExpression(p)) {
    if (ts.isStatement(p) || ts.isJsxElement(p) || ts.isFunctionDeclaration(p)) return null;
    p = p.parent;
  }
  if (!p) return null;
  const callee = p.expression;
  const name = ts.isIdentifier(callee) ? callee.text
    : ts.isPropertyAccessExpression(callee) ? callee.name.text : null;
  return name && REQUEST_FUNCTIONS.has(name) ? name : null;
}

const corrections = CORRECTIONS ? JSON.parse(fs.readFileSync(CORRECTIONS, 'utf8')) : {};
const classify = (f) => {
  const key = `${f.file}:${f.line}:${f.kind}:${f.text}`;
  if (corrections[key]) return corrections[key];              // {class, reason}
  if (f.requestPayload) return { class: 'CONTRACT_VALUE', reason: `argument to ${f.requestPayload}() — sent to the API, not displayed` };
  if (f.contract) return { class: 'CONTRACT_VALUE', reason: 'object property named value/code/slug — matched or sent, not displayed' };
  if (f.nearLabelKey) return { class: 'DISPLAY_LABEL', reason: 'sits beside a labelKey: label is the translatable unit' };
  if (f.kind === 'template') return { class: 'DYNAMIC_LOCALIZATION', reason: 'template literal interpolates runtime data' };
  if (f.kind === 'code') return { class: 'TECHNICAL', reason: 'framework directive or DOM selector' };
  if (f.kind === 'object:value') return { class: 'CONTRACT_VALUE', reason: 'value: property in a literal array/object' };
  if (isClassList(f.text)) return { class: 'TECHNICAL', reason: 'CSS class list (every token is a utility class)' };
  if (CLASS_SOUP.test(f.text) && f.text.split(/\s+/).length >= 3) return { class: 'TECHNICAL', reason: 'CSS class list' };
  // Position beats shape for the question "is this copy?". A literal's LENGTH and
  // SHAPE cannot answer it: `Retry`, `Save`, `Size` are copy, `mt-4`, `snake_case`,
  // `application/json` are not — and the previous rules asked only about shape, so
  // every one-word label rendered as JSX text was filed as code and never counted
  // as actionable. `Retry` in VirtualStylistDrawer's error state sat at class
  // TECHNICAL while that drawer was being reported as fully localized. Text between
  // tags is rendered, therefore it is copy — unless it is a brand name, which stays
  // untranslated wherever it appears.
  if (f.kind === 'jsx-text') {
    const brand = PROPER_NOUNS.some((p) => new RegExp(`\\b${p}\\b`).test(f.text));
    if (brand) {
      const words = f.text.split(/\s+/).filter((w) => HAS_LATIN_WORD.test(w));
      if (words.length <= 2) return { class: 'PROPER_NOUN', reason: 'brand/entity name (rendered, but not translatable)' };
      return { class: 'EDITORIAL', reason: 'sentence containing a brand name — needs a human read, not blind translation' };
    }
    return { class: 'MUST_LOCALIZE', reason: 'text rendered as JSX children' };
  }
  if (looksTechnical(f.text)) return { class: 'TECHNICAL', reason: 'code-like token (not human copy)' };
  if (PROPER_NOUNS.some((p) => new RegExp(`\\b${p}\\b`).test(f.text))) {
    const words = f.text.split(/\s+/).filter((w) => HAS_LATIN_WORD.test(w));
    if (words.length <= 2) return { class: 'PROPER_NOUN', reason: 'brand/entity name' };
    return { class: 'EDITORIAL', reason: 'sentence containing a brand name — needs a human read, not blind translation' };
  }
  if (!/\s/.test(f.text) && f.kind === 'literal') {
    return { class: 'REVIEW', reason: 'single word in an unclassified position — needs a human read (not counted as actionable)' };
  }
  return { class: 'MUST_LOCALIZE', reason: 'user-facing copy with no data contract' };
};

const dedup = new Map();
for (const f of findings) {
  const k = `${f.file}|${f.line}|${f.kind}|${f.text}`;
  if (!dedup.has(k)) dedup.set(k, f);
}
const items = [...dedup.values()].map((f) => ({ ...f, ...classify(f) }));

const byClass = {};
const byFile = {};
for (const it of items) {
  byClass[it.class] = (byClass[it.class] ?? 0) + 1;
  byFile[it.file] = (byFile[it.file] ?? 0) + 1;
}

const actionable = items.filter((i) => i.class === 'MUST_LOCALIZE' || i.class === 'DYNAMIC_LOCALIZATION');
const payload = {
  scope: SCOPE,
  source_root: 'frontend/src',
  total_occurrences: items.length,
  distinct_texts: new Set(items.map((i) => i.text)).size,
  by_class: byClass,
  actionable_total: actionable.length,
  per_file_total: Object.fromEntries(Object.entries(byFile).sort((a, b) => b[1] - a[1])),
  i18n_keys_referenced: [...i18nKeys].sort(),
  i18n_keys_count: i18nKeys.size,
  items,
};
if (JSON_OUT) fs.writeFileSync(JSON_OUT, JSON.stringify(payload, null, 2), 'utf8');

console.log(`\nCanonical i18n inventory — scope=${SCOPE}`);
console.log(`  occurrences : ${items.length}   distinct texts: ${payload.distinct_texts}`);
console.log(`  actionable (MUST_LOCALIZE + DYNAMIC): ${actionable.length}`);
console.log('  by classification:');
for (const [k, v] of Object.entries(byClass).sort((a, b) => b[1] - a[1])) console.log(`    ${String(v).padStart(4)}  ${k}`);
console.log('  by kind:');
const byKind = {};
for (const it of items) byKind[it.kind] = (byKind[it.kind] ?? 0) + 1;
for (const [k, v] of Object.entries(byKind).sort((a, b) => b[1] - a[1])) console.log(`    ${String(v).padStart(4)}  ${k}`);
console.log('  top files:');
for (const [f, c] of Object.entries(byFile).sort((a, b) => b[1] - a[1]).slice(0, 14)) console.log(`    ${String(c).padStart(4)}  ${f}`);
if (JSON_OUT) console.log(`\n  inventory -> ${JSON_OUT}`);
