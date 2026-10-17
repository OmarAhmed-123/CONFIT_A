#!/usr/bin/env node
/** Find elements that really push documentElement.scrollWidth (no scroll-container ancestor). */
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');
const BASE = process.env.BASE || 'http://localhost:43123';
const ROUTE = process.env.ROUTE || '/wardrobe';
const [W, H] = (process.env.VP || '390x844').split('x').map(Number);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, reducedMotion: 'reduce' });
await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
const page = await ctx.newPage();
await page.goto(BASE + ROUTE, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
await page.waitForTimeout(1500);
const out = await page.evaluate((w) => {
  const clipped = (el) => {
    let n = el.parentElement;
    while (n && n !== document.documentElement) {
      const ox = getComputedStyle(n).overflowX;
      if (ox !== 'visible') return true;
      n = n.parentElement;
    }
    return false;
  };
  const res = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.right <= w + 0.5) continue;
    if (clipped(el)) continue;
    let p = el.parentElement, chain = [];
    while (p && chain.length < 4) { chain.push(p.tagName.toLowerCase() + '.' + (p.getAttribute('class') || '').split(/\s+/).slice(0, 4).join('.')); p = p.parentElement; }
    res.push({ sel: el.tagName.toLowerCase() + '.' + (el.getAttribute('class') || '').split(/\s+/).slice(0, 6).join('.'), right: Math.round(r.right), width: Math.round(r.width), over: Math.round(r.right - w), text: (el.textContent || '').trim().slice(0, 70), parents: chain });
  }
  return { scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, res: res.slice(0, 15) };
}, W);
console.log(JSON.stringify(out, null, 1));
await browser.close();
