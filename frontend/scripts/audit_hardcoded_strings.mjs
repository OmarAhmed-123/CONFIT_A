#!/usr/bin/env node
/**
 * Ad-hoc audit helper (not a CI gate): enumerate user-facing English literals
 * that never pass through i18n, so the remediation is driven by measurement
 * rather than by whichever file happened to be open.
 */
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(process.argv[2] ?? 'src');
const OUT = [];

function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === '__tests__' || e.name === 'node_modules') continue;
      walk(p);
    } else if (/\.(ts|tsx)$/.test(e.name) && !/\.test\./.test(e.name)) OUT.push(p);
  }
}
walk(SRC);

// Patterns for user-facing surfaces.
const SURFACES = [
  ['toast',   /showToast\(\s*`([^`]{8,})`/g],
  ['toast',   /showToast\(\s*(['"])([^'"]{8,})\1/g],
  ['error',   /(?:new Error|throw new Error)\(\s*(['"])([^'"]{8,})\1/g],
  ['aria',    /aria-label=(['"])([^'"]{3,})\1/g],
  ['aria',    /aria-label=\{`([^`]{3,})`\}/g],
  ['placeholder', /placeholder=(['"])([^'"]{3,})\1/g],
  ['title',   /title=(['"])([^'"]{3,})\1/g],
  ['jsxtext', />\s*([A-Z][A-Za-z][A-Za-z ,'’\-]{6,}[a-z.!?])\s*</g],
  ['string',  /\bmessage:\s*(['"])([^'"]{8,})\1/g],
];

const rows = [];
for (const file of OUT) {
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, i) => {
    if (line.trim().startsWith('//') || line.trim().startsWith('*')) return;
    for (const [kind, re] of SURFACES) {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(line)) !== null) {
        const text = m[m.length - 1] ?? m[1];
        if (!text || !/[A-Za-z]{3}/.test(text)) continue;
        rows.push({ file: path.relative(process.cwd(), file), line: i + 1, kind, text: text.slice(0, 110) });
      }
    }
  });
}

// Deduplicate identical text
const seen = new Set();
const uniq = rows.filter((r) => {
  const k = r.text.trim();
  if (seen.has(k)) return false;
  seen.add(k);
  return true;
});

console.log(`Found ${rows.length} user-facing literal(s), ${uniq.length} distinct.\n`);
const byFile = uniq.reduce((a, r) => ((a[r.file] ??= []).push(r), a), {});
for (const [file, list] of Object.entries(byFile).sort()) {
  console.log(`\n### ${file}  (${list.length})`);
  for (const r of list) console.log(`  L${r.line} [${r.kind}] ${r.text}`);
}
