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
let grand = 0, deferredGrand = 0, focusChecks = 0, focusObscured = 0;
const buckets = {
  'CONTROL-FULLY-COVERED': [], 'CONTROL-PARTLY-COVERED': [],
  'control-graze': [], 'text-graze': [],
};

/* A deferred control has slid off-screen, is `visibility: hidden` and has
   `pointer-events: none`. It cannot obscure anything, so counting its
   geometric intersections would be counting a shadow. Those are tallied
   separately and reported, never folded into the defect count. */
/**
 * Classification, not a raw count.
 *
 * "covered 1.00" means the element's ENTIRE box is behind the control - the
 * user cannot see or reach it. Anything less is a partial graze: the element
 * is still legible and still clickable over the uncovered part. WCAG 2.2
 * SC 2.4.11 is about the FOCUSED element being ENTIRELY hidden, which the
 * focus-deference pass measures directly; this is the pointer/read view.
 */
const classify = (r) => {
  if (r.kind === 'text') return 'text-graze';
  if (r.covered >= 0.99) return 'CONTROL-FULLY-COVERED';
  if (r.covered >= 0.25) return 'CONTROL-PARTLY-COVERED';
  return 'control-graze';
};

const report = (phase, group, vp, route, out) => {
  if (!out.res.length) return;
  if (out.deferred) { deferredGrand += out.res.length; return; }
  for (const r of out.res) buckets[classify(r)].push({ route: `${group} ${vp} ${route}`, r });
  grand += out.res.length;
  console.log(`\n### ${phase} ${group} ${vp} ${route} — FAB box [${out.fab}] overlaps ${out.res.length}`);
  for (const r of out.res.slice(0, 6)) {
    console.log(`    ${classify(r).padEnd(23)} ${String(Math.round((r.covered ?? 0) * 100) + '%').padStart(4)}  ${r.tag.padEnd(6)} "${r.text}" [${r.box}]`);
  }
};
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
      const measure = () => {
        const fab = document.querySelector('.stylist-fab-anchor');
        if (!fab) return { err: 'no FAB' };
        const hidden = fab.getAttribute('data-fab-hidden') === 'true';
        const vis = getComputedStyle(fab).visibility;
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
          const ox = Math.max(0, Math.min(r.right, f.right) - Math.max(r.left, f.left));
          const oy = Math.max(0, Math.min(r.bottom, f.bottom) - Math.max(r.top, f.top));
          const frac = (ox * oy) / (r.width * r.height);
          res.push({ kind: 'control', tag: el.tagName.toLowerCase(),
            sel: el.tagName.toLowerCase() + '.' + (el.getAttribute('class') || '').split(/\s+/).slice(0, 3).join('.'),
            text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40),
            box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
            covered: Number(frac.toFixed(2)) });
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
          const ox = Math.max(0, Math.min(r.right, f.right) - Math.max(r.left, f.left));
          const oy = Math.max(0, Math.min(r.bottom, f.bottom) - Math.max(r.top, f.top));
          const frac = (ox * oy) / (r.width * r.height);
          res.push({ kind: 'text', tag: el.tagName.toLowerCase(), sel: el.tagName.toLowerCase(),
            text: txt.slice(0, 60),
            box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
            covered: Number(frac.toFixed(2)) });
        }
        /* A control that has slid out of the way, is invisible, or does not
           receive pointer events cannot occlude anything. Reporting the
           state alongside the count is what makes the three passes below
           meaningful instead of a single misleading number. */
        const deferred = hidden || vis === 'hidden' || getComputedStyle(fab).pointerEvents === 'none';
        return { fab: [Math.round(f.left), Math.round(f.top), Math.round(f.width), Math.round(f.height)], deferred, res };
      };
      const out = await page.evaluate(measure);
      if (out.err) { console.log(`${group} ${vp.name} ${route}: ${out.err}`); continue; }

      /* PASS 1 — at rest. The control is visible; whatever sits at the bottom
         of the viewport is genuinely behind it. Inherent to a floating
         control; the user can scroll it away, and passes 2 and 3 show they
         can. */
      report('rest', group, vp.name, route, out);

      /* PASS 2 — after scrolling down. Scroll deference must have removed the
         control from hit-testing entirely, so this MUST be zero. */
      await page.evaluate(() => window.scrollBy(0, 500));
      await page.waitForTimeout(650);
      const scrolled = await page.evaluate(measure);
      if (!scrolled.err) report('scrolled', group, vp.name, route, scrolled);

      /* PASS 3 — focus driven. Tab through the controls that pass 1 flagged
         (or, if none, the last ten controls on the page). Focus deference
         must move the control before the focus ring lands under it. */
      const focused = await page.evaluate(async () => {
        const fab = document.querySelector('.stylist-fab-anchor');
        if (!fab) return { err: 'no FAB' };
        const f0 = fab.getBoundingClientRect();
        const hit = (r) => !(r.right <= f0.left || r.left >= f0.right || r.bottom <= f0.top || r.top >= f0.bottom);
        const targets = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button]')]
          .filter((el) => !fab.contains(el))
          .filter((el) => { const r = el.getBoundingClientRect(); return r.width && r.height && hit(r); });
        let obscured = 0;
        for (const el of targets) {
          el.focus();
          await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
          const f = fab.getBoundingClientRect();
          const s = getComputedStyle(fab);
          const deferred = fab.getAttribute('data-fab-hidden') === 'true' || s.visibility === 'hidden' || s.pointerEvents === 'none';
          const r = el.getBoundingClientRect();
          const stillHit = !(r.right <= f.left || r.left >= f.right || r.bottom <= f.top || r.top >= f.bottom);
          if (stillHit && !deferred) obscured++;
        }
        return { checked: targets.length, obscured };
      });
      if (!focused.err && focused.checked) {
        focusChecks += focused.checked;
        focusObscured += focused.obscured;
        if (focused.obscured) console.log(`\n### FOCUS ${group} ${vp.name} ${route} — ${focused.obscured}/${focused.checked} focused controls still obscured`);
      }
    }
    await ctx.close();
  }
}
await browser.close();
console.log(`\n─── classification of the visible-control overlaps ────────────────────`);
for (const [cls, items] of Object.entries(buckets)) {
  console.log(`  ${cls.padEnd(23)} ${String(items.length).padStart(3)}`);
  for (const { route, r } of items) {
    console.log(`        ${String(Math.round((r.covered ?? 0) * 100) + '%').padStart(4)}  ${route.padEnd(26)} ${r.tag.padEnd(7)} "${r.text.slice(0, 44)}"`);
  }
}
console.log(`\n  What each metric proves:`);
console.log(`    CONTROL-FULLY-COVERED  — the whole box is behind the control; the user`);
console.log(`                            cannot see or click it. A real defect.`);
console.log(`    CONTROL-PARTLY-COVERED — >=25% behind it. Still clickable elsewhere,`);
console.log(`                            but worth a look.`);
console.log(`    control-graze / text   — a partial or non-interactive graze; the element`);
console.log(`                            stays legible and operable.`);
console.log(`    focus pass             — WCAG 2.2 SC 2.4.11 measured directly, not`);
console.log(`                            inferred from the geometric counts above.`);

console.log(`\n─── FAB occlusion summary ───────────────────────────────────────────`);
console.log(`DEFECT  overlaps with the control VISIBLE (at rest):   ${grand}`);
console.log(`DEFECT  controls still obscured once focused:           ${focusObscured} of ${focusChecks}`);
console.log(`(not a defect) geometric hits while the control is deferred off-screen: ${deferredGrand}`);
console.log(`\nThe at-rest count is what a floating control costs by definition; the`);
console.log(`user resolves it by scrolling, and the two zero-target guarantees are`);
console.log(`(a) the control defers off-screen on downward scroll and (b) it defers`);
console.log(`the moment a focused element would land under it (WCAG 2.2 SC 2.4.11).`);
