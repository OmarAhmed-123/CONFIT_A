#!/usr/bin/env node
/**
 * Honest image gate — ensures product/try-on imagery uses HonestProductImage (FR-002, SC-002).
 *
 * WHY: Audits IMG-03 / VTON-14 found raw <img> used instead of HonestProductImage,
 * allowing broken/placeholder images to masquerade as real content, violating honesty.
 *
 * CONTRACT:
 * - Any <img> with product-related alt or src (thumbnail_url, image_url, product, tryon, etc.)
 *   must use HonestProductImage component, not raw <img>
 * - Raw <img> is allowed for non-product imagery (icons, decorative, etc.) with proper alt
 * - Empty alt (alt="") for product images is forbidden — must have descriptive alt
 *
 * Usage: node scripts/check_honest_image.mjs [--json]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(HERE, '..');
const SRC_DIR = path.join(FRONTEND_ROOT, 'src');

const problems = [];

function fail(file, line, message) {
  problems.push({ file: path.relative(FRONTEND_ROOT, file), line, message });
}

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

// Patterns that indicate product/try-on imagery
const PRODUCT_IMAGE_PATTERNS = [
  /thumbnail_url/i,
  /image_url/i,
  /product.*image/i,
  /tryon.*image/i,
  /product_id/i,
  /sku.*image/i,
];

const RAW_IMG_RE = /<img\s+[^>]*>/gi;
const ALT_EMPTY_RE = /alt\s*=\s*["']\s*["']/;

function checkFile(file) {
  const text = fs.readFileSync(file, 'utf8');
  const lines = text.split('\n');

  lines.forEach((line, idx) => {
    const lineNum = idx + 1;
    let match;
    const imgRegex = new RegExp(RAW_IMG_RE.source, 'gi');
    
    while ((match = imgRegex.exec(line)) !== null) {
      const imgTag = match[0];
      
      // Skip if it's HonestProductImage (not raw <img>)
      if (line.includes('HonestProductImage')) continue;
      
      // Check if this is product-related imagery
      const isProductRelated = PRODUCT_IMAGE_PATTERNS.some(pattern => 
        pattern.test(line) || pattern.test(text.slice(Math.max(0, match.index - 200), match.index + 200))
      );

      if (isProductRelated) {
        // Check for empty alt
        if (ALT_EMPTY_RE.test(imgTag)) {
          fail(file, lineNum, `Product image with empty alt="" — must have descriptive alt and use HonestProductImage: ${imgTag.slice(0, 100)}`);
        } else {
          fail(file, lineNum, `Raw <img> for product/try-on imagery — must use HonestProductImage with honest failure state: ${imgTag.slice(0, 100)}`);
        }
      }
    }
  });
}

function main() {
  const asJson = process.argv.includes('--json');
  const sources = collectSources(SRC_DIR);

  for (const file of sources) {
    checkFile(file);
  }

  if (asJson) {
    console.log(JSON.stringify({ ok: problems.length === 0, problems }, null, 2));
  } else {
    if (problems.length === 0) {
      console.log('✔ honest image gate passed — no raw <img> for product/try-on imagery, all use HonestProductImage');
    } else {
      console.error(`\n✖ honest image gate FAILED with ${problems.length} problem(s):\n`);
      for (const p of problems.slice(0, 50)) {
        console.error(`  ${p.file}:${p.line} — ${p.message}`);
      }
      if (problems.length > 50) {
        console.error(`  ... +${problems.length - 50} more`);
      }
      console.error('');
    }
  }

  process.exit(problems.length === 0 ? 0 : 1);
}

main();
