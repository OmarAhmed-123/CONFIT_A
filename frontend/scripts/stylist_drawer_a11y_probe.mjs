#!/usr/bin/env node
/**
 * Browser-level accessibility + RTL probe for the StyleList drawer (spec 009 / T-STY-07).
 *
 * jsdom cannot compute colour contrast or layout, so this drives real Chromium
 * against a running frontend (no backend required; nothing is sent to the chat API):
 *   1. opens the real "Open AI Virtual Stylist" floating button,
 *   2. attaches a valid PNG and a rejected GIF,
 *   3. runs axe-core with colour-contrast ENABLED and the WCAG 2.x A/AA tags,
 *   4. checks the document direction for English (ltr) and Arabic (rtl).
 *
 * It is a reporting tool: it exits non-zero on any serious/critical violation
 * and writes its full JSON result to the path in PROBE_JSON.
 *
 * Usage (frontend dev server running on BASE_URL):
 *   BASE_URL=http://localhost:43123 node scripts/stylist_drawer_a11y_probe.mjs
 */
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const BASE_URL = process.env.BASE_URL || "http://localhost:43123";
const OUT = process.env.PROBE_JSON || "/tmp/stylist-drawer-a11y.json";
const axeSource = fs.readFileSync(path.join(root, "node_modules/axe-core/axe.min.js"), "utf8");
const en = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/en.json"), "utf8"));
const ar = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/ar.json"), "utf8"));

// 1x1 PNG, valid bytes.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);
const GIF = Buffer.from("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7", "base64");

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function runAxe(page) {
  await page.addScriptTag({ content: axeSource });
  return page.evaluate(async (tags) => {
    const res = await window.axe.run(document, {
      runOnly: { type: "tag", values: tags },
      resultTypes: ["violations", "incomplete"],
    });
    const slim = (list) =>
      list.map((v) => ({
        id: v.id,
        impact: v.impact,
        help: v.help,
        nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target.join(" "), summary: (n.failureSummary || "").slice(0, 240) })),
        nodeCount: v.nodes.length,
      }));
    return { violations: slim(res.violations), incomplete: slim(res.incomplete) };
  }, TAGS);
}

async function probe(browser, lang, dict) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.addInitScript((l) => {
    try { localStorage.setItem("confit_lang", l); } catch { /* storage disabled */ }
  }, lang);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 200)));

  await page.goto(BASE_URL, { waitUntil: "load", timeout: 90000 });
  const fab = page.getByRole("button", { name: dict.layout.open_ai_stylist });
  await fab.first().waitFor({ state: "visible", timeout: 90000 });
  await fab.first().click();
  const dialog = page.getByRole("dialog").first();
  await dialog.waitFor({ state: "visible", timeout: 30000 });

  const dir = await page.evaluate(() => document.documentElement.getAttribute("dir"));

  const fileInput = dialog.locator('input[type="file"]');
  await fileInput.setInputFiles([{ name: "outfit.png", mimeType: "image/png", buffer: PNG }]);
  await dialog.locator("img").first().waitFor({ state: "visible", timeout: 15000 });
  const thumbAlt = await dialog.locator("img").first().getAttribute("alt");

  await fileInput.setInputFiles([{ name: "anim.gif", mimeType: "image/gif", buffer: GIF }]);
  const alert = dialog.getByRole("alert").first();
  await alert.waitFor({ state: "visible", timeout: 15000 });
  const alertText = (await alert.textContent())?.trim();

  // Entrance animations leave text semi-transparent mid-transition, which makes
  // axe read a faded colour. Freeze motion and let the drawer settle before measuring.
  await page.addStyleTag({ content: "*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important;transition-delay:0s!important;}" });
  await page.waitForTimeout(800);
  const axeResult = await runAxe(page);
  await page.screenshot({ path: `/tmp/stylist-drawer-${lang}.png`, fullPage: false });
  await page.close();
  return { lang, dir, thumbAlt, alertText, expectedAlert: dict.stylist.attach_error_type, pageErrors: errors, ...axeResult };
}

const browser = await chromium.launch({ headless: true });
const results = [];
try {
  results.push(await probe(browser, "en", en));
  results.push(await probe(browser, "ar", ar));
} finally {
  await browser.close();
}

let blocking = 0;
for (const r of results) {
  const serious = r.violations.filter((v) => ["serious", "critical"].includes(v.impact));
  blocking += serious.length;
  const contrast = r.violations.find((v) => v.id === "color-contrast");
  const contrastIncomplete = r.incomplete.find((v) => v.id === "color-contrast");
  console.log(`[${r.lang}] dir=${r.dir} thumbAlt=${JSON.stringify(r.thumbAlt)} alert=${JSON.stringify(r.alertText)}`);
  console.log(`[${r.lang}] axe violations=${r.violations.length} serious/critical=${serious.length} ` +
    `color-contrast violations=${contrast ? contrast.nodeCount : 0} incomplete=${contrastIncomplete ? contrastIncomplete.nodeCount : 0}`);
  for (const v of serious) console.log(`  - ${v.impact} ${v.id}: ${v.help} (${v.nodeCount} nodes)`);
}
fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
console.log(`wrote ${OUT}`);

const failures = results.filter((r) => r.dir === null || r.alertText !== r.expectedAlert || !r.thumbAlt);
if (blocking > 0 || failures.length > 0) {
  console.error(`PROBE FAILED: serious/critical=${blocking}, structural failures=${failures.length}`);
  process.exit(1);
}
console.log("PROBE PASSED: no serious/critical axe violations; structure checks passed.");
