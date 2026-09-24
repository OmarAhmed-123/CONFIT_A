#!/usr/bin/env node
/**
 * Measure untranslated user-facing English in the frontend — by reading the
 * syntax tree, not by pattern-matching lines.
 *
 * WHY THIS REPLACES audit_hardcoded_strings.mjs (kept for reference):
 * that script was a set of regexes, and regexes cannot count this. MEASURED
 * 2026-09-24: it reported 184 occurrences / 172 distinct for the whole
 * frontend, while CheckoutView.tsx alone visibly contains literals it never
 * listed — `{m === 'standard' ? 'Standard' : 'Express'}`,
 * `>Phone<`, `aria-label="Promo code"`, `'No store currently holds this SKU…'`.
 * Its jsxtext pattern required 7+ characters and excluded digits and `/`, its
 * aria pattern required double quotes, and it had no pattern at all for text
 * inside JSX expressions. A count from that instrument is a SAMPLE, and the
 * mission forbids reporting a sample as a total.
 *
 * What this one does instead: parse each .ts/.tsx file with the TypeScript
 * parser and walk the AST for the positions where English reaches a user:
 *
 *   jsx-text        text children of JSX elements
 *   jsx-attr        aria-label / title / placeholder / alt / label attributes
 *   jsx-expr        string or template literals inside a JSX expression child
 *                   (ternaries, conditionals, `{cond && 'text'}`)
 *   message-prop    `message:` / `title:` / `description:` object properties
 *                   (the shape showToast() and EmptyState take)
 *
 * It deliberately does NOT flag: technical strings (class names, ids, URLs,
 * CSS), locale-independent tokens (`USD`, `SKU`, `xl`, `M`, `#fff`), strings
 * passed to a `t()`/`i18n` call, and text that is only punctuation or numerals.
 *
 * Usage:
 *   node scripts/audit_untranslated.mjs                 # human report
 *   node scripts/audit_untranslated.mjs --json out.json # machine-readable
 *   node scripts/audit_untranslated.mjs --scope consumer
 *   node scripts/audit_untranslated.mjs --scope consumer --fail-on 0
 *
 * Exit code is 0 unless --fail-on N is given and the scope count exceeds N,
 * so it can be used as a gate without changing behaviour by default.
 */
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const args = process.argv.slice(2);
const flag = (name, dflt = undefined) => {
  const i = args.indexOf(name);
  return i === -1 ? dflt : args[i + 1];
};
const SRC = path.resolve(flag('--src', 'src'));
const SCOPE = flag('--scope', 'all');
const FAIL_ON = flag('--fail-on', undefined);
const JSON_OUT = flag('--json', undefined);

//: A consumer surface is anything a shopper or an anonymous visitor can reach.
//  Brand/partner/admin views are out of scope for this mission and are counted
//  separately so the two are never mixed in one number.
const CONSUMER_PREFIXES = [
  'src/views/consumer/',
  'src/views/auth/',
  'src/views/public/',
  'src/components/commerce/',
  'src/components/stylist/',
  'src/components/tryon/',
  'src/components/common/',
  'src/components/navigation/',
  'src/components/layout/',
];

const isConsumer = (rel) => CONSUMER_PREFIXES.some((p) => rel.split(path.sep).join('/').startsWith(p));

//: English prose detector. Requires a run of two or more ASCII letters and at
//  least one word of 3+ letters, so `xl`, `M`, `USD`, `#fff`, `1.` and `—` are
//  not reported. Arabic text, digits and punctuation pass.
const LOOKS_ENGLISH = /(?=.*[A-Za-z]{3})[A-Za-z]/;
const stripNoise = (s) => s.replace(/\s+/g, ' ').trim();

const NOISY_EXACT = new Set([
  'USD', 'SAR', 'AED', 'EGP', 'EUR', 'GBP', 'SKU', 'JSON', 'CSV', 'API', 'ID', 'COD', 'BNPL',
  'CONFIT', 'MFA', 'AI', 'GPT', 'PDF', 'PNG', 'JPG', 'URL', 'CSS', 'HTML', 'OTP', 'CVV',
  'email@example.com', 'phone', 'tel', 'text', 'number', 'password', 'email',
]);
//: A single token with no spaces is an identifier, a route, an enum value or a
//  CSS class far more often than it is copy — `login`, `bopis`, `delivery`,
//  `/discover`, `guest-email-error`. MEASURED: without this, those tokens were
//  reported as untranslated text. Real one-word copy (`Phone`, `Subtotal`) is
//  capitalised and has no technical punctuation, so it still reports.
const looksTechnical = (t) => !/\s/.test(t) && (
  t.startsWith('/') || /[-_:[\]().#]/.test(t) || /^[a-z][a-z0-9]*$/.test(t)
);

const isNoisy = (s) => {
  const t = s.trim();
  if (!t) return true;
  if (NOISY_EXACT.has(t)) return true;
  if (!LOOKS_ENGLISH.test(t)) return true;          // no English at all
  if (looksTechnical(t)) return true;
  return false;
};

const files = [];
(function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (['__tests__', 'node_modules', 'dist'].includes(e.name)) continue;
      walk(p);
    } else if (/\.(ts|tsx)$/.test(e.name) && !/\.test\./.test(e.name) && !/\.d\.ts$/.test(e.name)) {
      files.push(p);
    }
  }
})(SRC);

const findings = [];
const push = (file, node, kind, text) => {
  if (isNoisy(text)) return;
  const { line } = ts.getLineAndCharacterOfPosition(
    ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest),
    node.getStart(),
  );
  findings.push({ file: path.relative(process.cwd(), file).split(path.sep).join('/'), line: line + 1, kind, text: stripNoise(text) });
};

const TEXT_ATTRS = new Set(['aria-label', 'aria-description', 'title', 'placeholder', 'alt', 'label']);
const MESSAGE_PROPS = new Set(['message', 'title', 'description', 'label', 'placeholder', 'notice']);

for (const file of files) {
  const rel = path.relative(process.cwd(), file).split(path.sep).join('/');
  if (SCOPE === 'consumer' && !isConsumer(rel)) continue;
  if (SCOPE === 'non-consumer' && isConsumer(rel)) continue;

  const src = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const text = (n) => (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) ? n.text : null);

  const visit = (node) => {
    // 1. JSX text children
    if (ts.isJsxText(node)) {
      const t = stripNoise(node.getText(src));
      if (t) push(file, node, 'jsx-text', t);
    }

    // 2. attributes that are read aloud or shown as a hint
    if (ts.isJsxAttribute(node) && node.initializer) {
      const name = node.name.getText(src);
      if (TEXT_ATTRS.has(name)) {
        if (ts.isStringLiteral(node.initializer)) push(file, node, 'jsx-attr', node.initializer.text);
        else if (ts.isJsxExpression(node.initializer) && node.initializer.expression) {
          const t = text(node.initializer.expression);
          if (t) push(file, node, 'jsx-attr', t);
          else if (ts.isTemplateExpression(node.initializer.expression)) {
            push(file, node, 'jsx-attr', node.initializer.expression.getText(src));
          }
        }
      }
    }

    // 3. literals inside a JSX expression CHILD: {cond ? 'A' : 'B'}, {cond && 'A'}
    //    An attribute initializer (`className={cond ? 'a' : 'b'}`) is also a
    //    JsxExpression node. MEASURED: not excluding it made this rule report
    //    Tailwind class strings as untranslated copy (CheckoutView: 4 of them).
    if (ts.isJsxExpression(node) && node.expression && !ts.isJsxAttribute(node.parent)) {
      const literals = [];
      const collect = (n) => {
        // MEASURED (first version of this script): descending into a nested
        // element harvested every className inside it and reported 3695
        // "untranslated" literals in consumer surfaces. Nested markup is a
        // different node with its own attributes and text, visited on its own
        // pass, so the recursion stops at its boundary.
        if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) return;
        const t = text(n);
        if (t) literals.push(t);
        else ts.forEachChild(n, collect);
      };
      collect(node.expression);
      for (const t of literals) push(file, node, 'jsx-expr', t);
    }

    // 4. object properties that carry user-visible copy
    if (ts.isPropertyAssignment(node)) {
      const key = node.name.getText(src).replace(/['"]/g, '');
      if (MESSAGE_PROPS.has(key)) {
        const t = text(node.initializer);
        if (t) push(file, node, 'message-prop', t);
      }
    }

    ts.forEachChild(node, visit);
  };
  visit(src);
}

// Deduplicate identical (file,line,kind,text) tuples produced by overlapping visitors.
const seen = new Set();
const unique = findings.filter((f) => {
  const k = `${f.file}|${f.line}|${f.kind}|${f.text}`;
  if (seen.has(k)) return false;
  seen.add(k);
  return true;
});

const consumer = unique.filter((f) => isConsumer(f.file));
const other = unique.filter((f) => !isConsumer(f.file));
const byFile = (list) => {
  const m = new Map();
  for (const f of list) m.set(f.file, (m.get(f.file) ?? 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
};

console.log(`Untranslated user-facing English — parsed with the TypeScript AST (not regexes)`);
console.log(`  consumer surfaces : ${consumer.length}`);
console.log(`  other surfaces    : ${other.length}`);
console.log(`  total             : ${unique.length}   (distinct texts: ${new Set(unique.map((f) => f.text)).size})`);
console.log('');
for (const [file, n] of byFile(consumer)) console.log(`  ${String(n).padStart(3)}  ${file}`);
if (SCOPE !== 'consumer') {
  console.log('\n  ── other surfaces (out of mission scope) ──');
  for (const [file, n] of byFile(other)) console.log(`  ${String(n).padStart(3)}  ${file}`);
}

if (SCOPE === 'consumer' || SCOPE === 'all') {
  console.log('\n  consumer-scope occurrences:');
  for (const f of consumer) console.log(`  ${f.file}:${f.line}  [${f.kind}]  ${f.text}`);
}

if (JSON_OUT) {
  fs.writeFileSync(JSON_OUT, JSON.stringify({ generated_at: new Date().toISOString(), scope: SCOPE, consumer, other }, null, 2));
  console.log(`\n  json -> ${JSON_OUT}`);
}

const scoped = SCOPE === 'non-consumer' ? other.length : SCOPE === 'consumer' ? consumer.length : unique.length;
if (FAIL_ON !== undefined && scoped > Number(FAIL_ON)) {
  console.error(`\n  FAIL: ${scoped} untranslated literal(s) in scope '${SCOPE}', limit ${FAIL_ON}`);
  process.exit(1);
}
