#!/usr/bin/env node
/**
 * Auth modal behaviour probe — real interaction, real network.
 *
 * Checks the states the static capture cannot: focus trap and initial focus,
 * Escape restoring focus, validation keeping what the user typed, a failed
 * sign-in showing an error (never a silent success), and the single-flight
 * guard on submit (no duplicate POST from a double click).
 */
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://localhost:43123';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
const page = await ctx.newPage();
const posts = [];
page.on('request', (r) => { if (r.method() === 'POST' && /\/auth\/(login|register)/.test(r.url())) posts.push(new URL(r.url()).pathname); });

const open = async () => {
  await page.goto(`${BASE}/discover`, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(600);
  const signIn = page.locator('header button:visible').filter({ hasText: /sign in/i }).first();
  if (await signIn.count()) { await signIn.click({ timeout: 5000 }).catch(async () => { await signIn.evaluate((b) => b.click()); }); }
  else { console.log('nav sign-in button not found'); }
  await page.waitForTimeout(900);
  return page.locator('[role="dialog"]').first();
};

let dlg = await open();
const ok = await dlg.count();
console.log('dialog opened:', !!ok);
if (!ok) { console.log('ABORT: no dialog'); await browser.close(); process.exit(1); }

const info = await page.evaluate(() => {
  const d = document.querySelector('[role="dialog"]');
  const lum = (rgb) => { const m = rgb.match(/[\d.]+/g); if (!m) return null; const [r, g, b] = m.slice(0, 3).map(Number).map((v) => { const s = v / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  const bgOf = (el) => { let n = el; while (n) { const c = getComputedStyle(n).backgroundColor; if (c && !/rgba\(0, 0, 0, 0\)/.test(c)) return c; n = n.parentElement; } return 'rgb(255,255,255)'; };
  const fields = [...d.querySelectorAll('input:not([type=hidden])')].map((i) => {
    const lab = i.labels?.[0]?.textContent?.trim() || i.getAttribute('aria-label') || i.getAttribute('placeholder') || '(no label)';
    return { tag: i.type, label: lab.slice(0, 40), autocomplete: i.getAttribute('autocomplete'), required: i.required };
  });
  const buttons = [...d.querySelectorAll('button')].filter((b) => b.offsetParent).map((b) => {
    const r = b.getBoundingClientRect(); const fg = getComputedStyle(b).color; const bg = bgOf(b);
    return { text: (b.textContent || b.getAttribute('aria-label') || '').trim().slice(0, 34), ratio: Number(ratio(fg, bg).toFixed(2)), w: Math.round(r.width), h: Math.round(r.height), type: b.type };
  });
  return { ariaModal: d.getAttribute('aria-modal'), labelled: !!(d.getAttribute('aria-label') || d.getAttribute('aria-labelledby')), name: (d.getAttribute('aria-label') || (d.getAttribute('aria-labelledby') && document.getElementById(d.getAttribute('aria-labelledby'))?.textContent) || '').trim().slice(0, 50), active: document.activeElement?.tagName + '#' + (document.activeElement?.id || '') + (document.activeElement?.getAttribute('autocomplete') || ''), fields, buttons };
});
console.log('aria-modal:', info.ariaModal, '| accessible name:', JSON.stringify(info.name));
console.log('initial focus:', info.active);
console.log('fields:', JSON.stringify(info.fields));
console.log('buttons (contrast / size):');
for (const b of info.buttons) console.log(`   ${String(b.ratio).padStart(6)}  ${String(b.w + 'x' + b.h).padEnd(9)} ${String(b.type).padEnd(8)} "${b.text}"`);

// focus trap: 30 tabs must never leave the dialog
let escaped = 0;
for (let i = 0; i < 30; i++) {
  await page.keyboard.press('Tab');
  const inside = await page.evaluate(() => { const d = document.querySelector('[role="dialog"]'); return !!(d && document.activeElement && d.contains(document.activeElement)); });
  if (!inside) escaped++;
}
console.log(`focus trap: ${escaped}/30 tab stops landed outside the dialog`);

// validation keeps input
const email = dlg.locator('input[type="email"], input[autocomplete="email"]').first();
if (await email.count()) {
  await email.fill('not-an-email');
  const pass = dlg.locator('input[type="password"]').first();
  if (await pass.count()) await pass.fill('x');
  const submit = dlg.locator('button[type="submit"]').first();
  if (await submit.count()) { await submit.click(); await page.waitForTimeout(900); }
  const kept = await email.inputValue();
  const err = await page.evaluate(() => { const d = document.querySelector('[role="dialog"]'); const a = d?.querySelector('[role="alert"], .text-rose-600, .text-rose-700'); return (a?.textContent || '').trim().slice(0, 120); });
  console.log('after invalid submit → input kept:', JSON.stringify(kept), '| error shown:', JSON.stringify(err));
}

// single-flight: bad password, triple click
const goodEmail = dlg.locator('input[type="email"], input[autocomplete="email"]').first();
await goodEmail.fill('shopper@confit.io');
const pw = dlg.locator('input[type="password"]').first();
if (await pw.count()) await pw.fill('WrongPassword1!');
posts.length = 0;
const submit2 = dlg.locator('button[type="submit"]').first();
if (await submit2.count()) { await submit2.click({ clickCount: 3, delay: 30 }).catch(async () => { await submit2.click(); await submit2.click(); }); }
await page.waitForTimeout(2500);
const err2 = await page.evaluate(() => { const d = document.querySelector('[role="dialog"]'); const a = d?.querySelector('[role="alert"], .text-rose-600, .text-rose-700'); return (a?.textContent || '').trim().slice(0, 140); });
console.log('failed sign-in → POSTs:', posts.length, JSON.stringify(posts), '| error shown:', JSON.stringify(err2));
console.log('still signed out (dialog open):', !!(await page.locator('[role="dialog"]').count()));

// Escape closes and restores focus
await page.keyboard.press('Escape');
await page.waitForTimeout(700);
console.log('Escape closed dialog:', !(await page.locator('[role="dialog"]').count()), '| focus is on body/container:', await page.evaluate(() => document.activeElement?.tagName));
await browser.close();
