#!/usr/bin/env node
/**
 * Try-on modal: hover + contrast probe.
 *
 * The static axe pass in scripts/uiux_audit_capture.mjs cannot see hover-state
 * colour, and the worst defect found on `main` (2026-10-17) only existed while
 * the pointer was over the control: "+ Dress on Body" turned
 * rgb(2,6,23) on rgb(37,39,41) — 1.35:1, effectively invisible.
 *
 *   BASE=http://localhost:43123 TAG=after node scripts/tryon_probe.mjs
 */
import fs from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://localhost:43123';
const TAG = process.env.TAG || 'run';
const PASSWORD = 'Password123!';
const PRODUCT = 'goodyear-welted-leather-oxford-shoes';
const SHOTS = process.env.OUT_DIR || '/tmp/uiux_shots';
fs.mkdirSync(SHOTS, { recursive: true });

const lum = (rgb) => {
  const [r, g, b] = rgb.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number).map((v) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
};

/** Walk up for the first non-transparent background. */
const bgOf = (page, handle) =>
  page.evaluate((el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const bg = getComputedStyle(n).backgroundColor;
      if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) return bg;
      n = n.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor;
  }, handle);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
const page = await ctx.newPage();

async function run(role) {
  await page.goto(`${BASE}/privacy`, { waitUntil: 'domcontentloaded' });
  if (role === 'consumer') {
    const res = await page.request.post(`${BASE}/api/v1/auth/login`, { data: { email: 'shopper@confit.io', password: PASSWORD } });
    if (!res.ok()) { console.log(`login failed ${res.status()}`); return; }
    const body = await res.json();
    await page.evaluate((u) => localStorage.setItem('confit_user', JSON.stringify(u)), body.user);
  }
  await page.goto(`${BASE}/product/${PRODUCT}`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1200);

  const trigger = page.locator('button:visible').filter({ hasText: /^\s*Try On\s*$/ }).first();
  if (!(await trigger.count())) { console.log(`[${TAG}/${role}] Try On button not found — aborting`); return; }
  await trigger.click();
  await page.waitForTimeout(1800);
  const dialog = page.locator('[role="dialog"]').first();
  if (!(await dialog.count())) { console.log(`[${TAG}/${role}] no dialog opened`); return; }
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${SHOTS}/${TAG}_tryon_${role}.png`, fullPage: false });

  console.log(`\n=== ${TAG} / ${role} — dialog buttons (resting) ===`);
  const buttons = dialog.locator('button:visible');
  const n = await buttons.count();
  for (let i = 0; i < n; i++) {
    const b = buttons.nth(i);
    if (!(await b.isVisible())) continue;
    const label = (await b.innerText()).trim().replace(/\s+/g, ' ').slice(0, 46) || '(icon)';
    const fg = await b.evaluate((el) => getComputedStyle(el).color);
    const bg = await bgOf(page, await b.elementHandle());
    const dis = await b.isDisabled();
    console.log(`  ${ratio(fg, bg).toFixed(2).padStart(6)}  ${dis ? 'DISABLED ' : '         '}${label.padEnd(48)} ${fg} on ${bg}`);
  }

  console.log(`=== ${TAG} / ${role} — "+ Dress on Body" HOVER ===`);
  const dress = dialog.locator('button:visible').filter({ hasText: /Dress on Body/ }).first();
  const cnt = await dialog.locator('button:visible').filter({ hasText: /Dress on Body/ }).count();
  if (!cnt) { console.log('  (no "+ Dress on Body" control rendered)'); }
  for (let i = 0; i < cnt; i++) {
    const b = dialog.locator('button:visible').filter({ hasText: /Dress on Body/ }).nth(i);
    if (await b.isDisabled()) continue;
    await b.hover();
    await page.waitForTimeout(600);
    const fg = await b.evaluate((el) => getComputedStyle(el).color);
    const bg = await bgOf(page, await b.elementHandle());
    console.log(`  ${ratio(fg, bg).toFixed(2).padStart(6)}  ${(await b.innerText()).trim().replace(/\s+/g, ' ').slice(0, 46).padEnd(48)} ${fg} on ${bg}`);
    await page.screenshot({ path: `${SHOTS}/${TAG}_tryonhover_${role}.png`, fullPage: false });
    break;
  }
}

await run('guest');
await ctx.close();
const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
await ctx2.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
page.removeAllListeners();
await browser.close();
