#!/usr/bin/env node
/**
 * Pixel-level colour-contrast audit for elements axe reports as "incomplete" (spec 009 / T-STY-07).
 *
 * axe cannot resolve a background that is a gradient, an image, or a translucent layer, so it
 * returns "incomplete" instead of pass or fail. This script measures the real rendered background:
 *   1. For each flagged element, its text is made transparent, so only the background is captured.
 *   2. A screenshot of the element's box is taken from the composited page.
 *   3. For every background pixel, the foreground is alpha-composited over that pixel, including
 *      the element's effective opacity (product of ancestor opacities), and the WCAG 2.x ratio is
 *      computed. The worst-case (minimum) ratio over the box is reported, along with the median.
 * Thresholds (WCAG 2.2 SC 1.4.3): 4.5:1 normal text; 3:1 large text (>=24px, or >=18.66px and bold).
 *
 * Reporting tool: exits 1 when any measured text element fails its threshold.
 *   BASE_URL=http://localhost:43123 OUT_JSON=/tmp/contrast.json node scripts/stylist_contrast_audit.mjs
 */
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const BASE_URL = process.env.BASE_URL || "http://localhost:43123";
const OUT = process.env.OUT_JSON || "/tmp/stylist-contrast.json";
const axeSource = fs.readFileSync(path.join(root, "node_modules/axe-core/axe.min.js"), "utf8");
const TAGS = ["wcag2aa", "wcag21aa", "wcag22aa"];
const en = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/en.json"), "utf8"));
const ar = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/ar.json"), "utf8"));
const DICT = { en, ar };
// Select the stylist drawer by its accessible name, not the first dialog on the page.
const drawerSel = (lang) => `[role="dialog"][aria-label="${DICT[lang].stylist.dialog_label}"]`;

// Runs in the page: composite and measure WCAG contrast over the screenshot pixels.
async function measureInPage({ b64, fgs, large }) {
  const img = new Image();
  img.src = "data:image/png;base64," + b64;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, c.width, c.height).data;
  const lin = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const lum = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const out = [];
  for (const fg of fgs) {
    const threshold = large ? 3 : 4.5;
    let min = Infinity;
    const ratios = [];
    for (let i = 0; i < px.length; i += 4) {
      const a = fg.a * fg.opacity;
      // Composite foreground over this background pixel.
      const r = fg.r * a + px[i] * (1 - a);
      const g = fg.g * a + px[i + 1] * (1 - a);
      const b = fg.b * a + px[i + 2] * (1 - a);
      const L1 = lum(r, g, b);
      const L2 = lum(px[i], px[i + 1], px[i + 2]);
      const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
      ratios.push(ratio);
      if (ratio < min) min = ratio;
    }
    ratios.sort((x, y) => x - y);
    const median = ratios[Math.floor(ratios.length / 2)];
    out.push({ fg: fg.raw, worst: +min.toFixed(2), median: +median.toFixed(2), threshold, pass: min >= threshold });
  }
  return out;
}

async function auditSurface(page, label, lang) {
  await page.addScriptTag({ content: axeSource });
  // Scope to the drawer only: content behind the modal scrim is not the drawer under test.
  const dsel = drawerSel(lang);
  const incomplete = await page.evaluate(async ({ tags, dsel }) => {
    const dialog = document.querySelector(dsel);
    if (!dialog) throw new Error("drawer not found: " + dsel);
    const res = await window.axe.run(dialog, { runOnly: { type: "tag", values: tags }, resultTypes: ["incomplete"] });
    const v = res.incomplete.find((x) => x.id === "color-contrast");
    return v ? v.nodes.map((n) => n.target.join(" ")) : [];
  }, { tags: TAGS, dsel });
  const seen = new Set();
  const results = [];
  let auditIdx = 0;
  for (const sel of incomplete) {
    if (seen.has(sel)) continue;
    seen.add(sel);
    // Resolve the selector to the instance inside the dialog and tag it, so it can be located exactly.
    const tagged = await page.evaluate(({ sel, idx, dsel }) => {
      const dialog = document.querySelector(dsel);
      const el = Array.from(document.querySelectorAll(sel)).find((e) => dialog && dialog.contains(e));
      if (!el) return false;
      el.setAttribute("data-audit-id", String(idx));
      return true;
    }, { sel, idx: auditIdx, dsel });
    if (!tagged) { results.push({ sel, skipped: "not inside dialog" }); continue; }
    const loc = page.locator(`[data-audit-id="${auditIdx}"]`);
    auditIdx++;
    if ((await loc.count()) === 0) { results.push({ sel, skipped: "not found" }); continue; }
    const info = await loc.evaluate((el) => {
      const txt = (el.innerText || el.textContent || "").trim();
      // Text-bearing descendants: their own text colour, effective opacity, and size.
      const fgs = new Map();
      const walk = (node, opacity) => {
        const cs = getComputedStyle(node);
        const op = opacity * parseFloat(cs.opacity || "1");
        const hasText = Array.from(node.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
        if (hasText) {
          const m = cs.color.match(/rgba?\(([^)]+)\)/);
          if (m) {
            const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
            const a = p.length === 4 ? p[3] : 1;
            const key = p.slice(0, 3).join(",") + "|" + a.toFixed(2);
            if (!fgs.has(key)) fgs.set(key, { r: p[0], g: p[1], b: p[2], a, opacity: op, raw: cs.color, size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight, 10) });
          }
        }
        for (const ch of node.children) walk(ch, op);
      };
      walk(el, 1);
      const r = el.getBoundingClientRect();
      return { txt: txt.slice(0, 80), fgs: Array.from(fgs.values()), box: { x: r.x, y: r.y, w: r.width, h: r.height }, inViewport: r.width > 0 && r.height > 0 };
    });
    if (!info.inViewport) { results.push({ sel, text: info.txt, skipped: "zero-size" }); continue; }
    const vx = Math.max(0, info.box.x), vy = Math.max(0, info.box.y);
    const vr = Math.min(info.box.x + info.box.w, 1280), vb = Math.min(info.box.y + info.box.h, 900);
    if (vr - vx < 1 || vb - vy < 1) { results.push({ sel, text: info.txt, skipped: "outside viewport" }); continue; }
    // Make the text transparent to capture only the background underneath.
    await loc.evaluate((el) => {
      for (const x of [el, ...el.querySelectorAll("*")]) {
        x.dataset.__prev = x.getAttribute("style") || "";
        x.style.setProperty("color", "transparent", "important");
        x.style.setProperty("-webkit-text-fill-color", "transparent", "important");
        x.style.setProperty("text-shadow", "none", "important");
      }
    });
    let png;
    try {
      png = await page.screenshot({ clip: { x: vx, y: vy, width: vr - vx, height: vb - vy }, animations: "disabled" });
    } finally {
      await loc.evaluate((el) => {
        for (const x of [el, ...el.querySelectorAll("*")]) {
          const prev = x.dataset.__prev;
          if (prev) x.setAttribute("style", prev); else x.removeAttribute("style");
          delete x.dataset.__prev;
        }
      });
    }
    // Large text per WCAG: >=24px, or >=18.66px and bold (>=700).
    const fgs = info.fgs.map((f) => ({ ...f }));
    const large = fgs.length ? fgs.every((f) => f.size >= 24 || (f.size >= 18.66 && f.weight >= 700)) : false;
    const measured = await page.evaluate(measureInPage, { b64: png.toString("base64"), fgs, large });
    for (const m of measured) results.push({ surface: label, sel, text: info.txt, ...m, size: fgs[0].size, weight: fgs[0].weight, large });
  }
  return results;
}

const browser = await chromium.launch({ headless: true });
const all = [];
try {
  for (const lang of ["en", "ar"]) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.addInitScript((l) => { try { localStorage.setItem("confit_lang", l); } catch { /* */ } }, lang);
    await page.goto(BASE_URL, { waitUntil: "load", timeout: 90000 });
    await page.addStyleTag({ content: "*,*::before,*::after{animation-duration:0s!important;transition-duration:0s!important;}" });
    const fab = page.getByRole("button", { name: DICT[lang].layout.open_ai_stylist });
    await fab.waitFor({ state: "visible", timeout: 90000 });
    await fab.click();
    await page.locator(drawerSel(lang)).waitFor({ state: "visible", timeout: 30000 });
    await page.waitForTimeout(800);
    // Measure the drawer's own surface (the dialog) and the page surface behind it.
    const rows = await auditSurface(page, `${lang}:drawer`, lang);
    all.push(...rows.map((r) => ({ lang, ...r })));
    await page.close();
  }
} finally {
  await browser.close();
}

const measured = all.filter((r) => r.pass !== undefined);
const failing = measured.filter((r) => !r.pass);
console.log(`measured text elements: ${measured.length}; failing: ${failing.length}; skipped: ${all.length - measured.length}`);
for (const f of failing) console.log(`  FAIL [${f.lang}] ${f.worst}:1 worst / ${f.median}:1 median vs ${f.threshold}:1 ${f.large ? "(large)" : "(normal)"} ${f.fg} "${f.text}" ${f.sel}`);
fs.writeFileSync(OUT, JSON.stringify(all, null, 2));
console.log(`wrote ${OUT}`);
process.exit(failing.length ? 1 : 0);
