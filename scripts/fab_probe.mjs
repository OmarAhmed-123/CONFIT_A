#!/usr/bin/env node
/**
 * Floating AI-Stylist FAB overlap probe.
 *
 * The FAB is `position: fixed`, so it can cover page content the user still
 * needs — a real WCAG 2.2 "focus not obscured" / content-obscuring defect, and
 * one a static axe pass cannot see. For each route it reports every interactive
 * element or text run whose box intersects the FAB's box.
 *
 *   BASE=http://localhost:43123 node scripts/fab_probe.mjs
 */
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://localhost:43123';
const PASSWORD = 'Password123!';
const PRODUCT = 'goodyear-welted-leather-oxford-shoes';
const ORDER = 'CONF-8821094A';
const ROUTES = [
  ['guest', null, ['/', '/discover', `/product/${PRODUCT}`, '/builder', '/outfits', '/fit', '/wardrobe', '/cart', '/orders', '/privacy']],
  ['consumer', 'shopper@confit.io', ['/', '/discover', `/product/${PRODUCT}`, '/builder', '/my-looks', '/fit', '/wardrobe', '/cart', '/checkout', '/orders', `/orders/${ORDER}`, '/profile', '/settings', '/notifications']],
];
const VIEWPORTS = [{ name: 'desk', w: 1280, h: 800 }, { name: 'mob', w: 390, h: 844 }];

const browser = await chromium.launch();
let grand = 0;
for (const [group, user, routes] of ROUTES) {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, reducedMotion: 'reduce' });
    await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
    const page = await ctx.newPage();
    await page.goto(`${BASE}/privacy`, { waitUntil: 'domcontentloaded' });
    if (user) {
      const res = await page.request.post(`${BASE}/api/v1/auth/login`, { data: { email: user, password: PASSWORD } });
      if (!res.ok()) { console.error('login failed'); await ctx.close(); continue; }
      const body = await res.json();
      await page.evaluate((u) => localStorage.setItem('confit_user', JSON.stringify(u)), body.user);
    }
    for (const route of routes) {
      await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
      await page.waitForTimeout(900);
      const out = await page.evaluate(() => {
        const fab = document.querySelector('.stylist-fab-anchor');
        if (!fab) return { err: 'no FAB' };
        const f = fab.getBoundingClientRect();
        const hit = (r) => !(r.right <= f.left || r.left >= f.right || r.bottom <= f.top || r.top >= f.bottom);
        const res = [];
        for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=tab]')) {
          if (fab.contains(el)) continue;
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          const s = getComputedStyle(el);
          if (s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) < 0.1) continue;
          if (!hit(r)) continue;
          res.push({ kind: 'control', sel: el.tagName.toLowerCase() + '.' + (el.getAttribute('class') || '').split(/\s+/).slice(0, 3).join('.'), text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40), box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] });
        }
        // text runs only (leaf nodes with text) that are not the FAB's own
        for (const el of document.querySelectorAll('h1,h2,h3,p,span,li,label,td,th,strong,em')) {
          if (fab.contains(el) || el.closest('.stylist-fab-anchor')) continue;
          if (el.children.length) continue;
          const txt = (el.textContent || '').trim();
          if (txt.length < 3) continue;
          const r = el.getBoundingClientRect();
          if (r.width === 0) continue;
          const s = getComputedStyle(el);
          if (s.visibility === 'hidden' || Number(s.opacity) < 0.1) continue;
          if (!hit(r)) continue;
          res.push({ kind: 'text', sel: el.tagName.toLowerCase(), text: txt.slice(0, 60), box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] });
        }
        return { fab: [Math.round(f.left), Math.round(f.top), Math.round(f.width), Math.round(f.height)], res };
      });
      if (out.err) { console.log(`${group} ${vp.name} ${route}: ${out.err}`); continue; }
      if (out.res.length) {
        grand += out.res.length;
        console.log(`\n### ${group} ${vp.name} ${route} — FAB box [${out.fab}] overlaps ${out.res.length}`);
        for (const r of out.res.slice(0, 6)) console.log(`    ${r.kind.padEnd(8)} ${r.sel.slice(0, 46).padEnd(48)} "${r.text}" [${r.box}]`);
      }
    }
    await ctx.close();
  }
}
await browser.close();
console.log(`\nTOTAL FAB overlaps: ${grand}`);
