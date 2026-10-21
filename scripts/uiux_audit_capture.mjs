#!/usr/bin/env node
/**
 * UI/UX audit capture — route-by-route rendered evidence for the Logo #3
 * ("Individual Grid") white-first identity.
 *
 * For every route x role x viewport it records, from the REAL rendered page:
 *   - final URL (redirects / guards), first <h1>
 *   - horizontal overflow (scrollWidth > innerWidth)
 *   - page canvas colour (html, body, first <main>)
 *   - computed-style hits of the legacy navy/gold/cream identity
 *   - presence of the official mark (inline SVG coral quadrant or /brand/ asset)
 *   - axe-core WCAG 2 A/AA violations (id, impact, node count)
 *   - broken images, console errors, interactive targets under 24x24 CSS px
 *   - a full-page screenshot
 *
 * A screenshot is evidence of appearance only; it does not prove a feature works.
 *
 * Usage:
 *   BASE_URL=http://localhost:43123 OUT_DIR=/tmp/shots LABEL=after \
 *     node scripts/uiux_audit_capture.mjs [--only=consumer,brand]
 *   Optional: UI_LANG=ar (Arabic/RTL pass), VIEWPORTS=desk:1280x800,mob:390x844
 *
 * Requires a backend reachable through the preview proxy (/api) with the
 * development seed (demo accounts). Never point it at production with real
 * credentials: it signs in.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(path.resolve('frontend/package.json'));
const { chromium } = require('playwright-core');
const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

const BASE = process.env.BASE_URL || 'http://localhost:43123';
const OUT = process.env.OUT_DIR || '/tmp/uiux_shots';
const LABEL = process.env.LABEL || 'run';
const UI_LANG = process.env.UI_LANG || '';
const PASSWORD = process.env.DEMO_PASSWORD || 'Password123!';
const only = (process.argv.find((a) => a.startsWith('--only=')) || '').slice(7).split(',').filter(Boolean);
const routeFilter = (process.argv.find((a) => a.startsWith('--routes=')) || '').slice(9).split(',').filter(Boolean);
fs.mkdirSync(OUT, { recursive: true });

const PRODUCT = process.env.PRODUCT_SLUG || 'goodyear-welted-leather-oxford-shoes';
const ORDER = process.env.ORDER_NUMBER || 'CONF-8821094A';

const GROUPS = {
  guest: {
    user: null,
    routes: ['/', '/discover', `/product/${PRODUCT}`, '/builder', '/outfits', '/try-on', '/fit', '/wardrobe',
      '/cart', '/orders', '/privacy', '/terms', '/gdpr', '/reset-password', '/verify-email',
      '/email/unsubscribe', '/looks/invalid-token', '/this-route-does-not-exist', '/b2b', '/admin'],
  },
  consumer: {
    user: 'shopper@confit.io',
    routes: ['/', '/discover', `/product/${PRODUCT}`, '/builder', '/my-looks', '/try-on', '/fit', '/wardrobe',
      '/cart', '/checkout', '/orders', `/orders/${ORDER}`, '/returns', '/profile', '/settings', '/notifications', '/b2b', '/admin'],
  },
  brand: {
    user: 'brand@casalumen.com',
    routes: ['/b2b', '/b2b/catalog', '/b2b/inventory', '/b2b/orders', '/b2b/analytics', '/b2b/placements', '/partner', '/admin'],
  },
  admin: {
    user: 'admin@confit.io',
    routes: ['/admin', '/admin/analytics', '/admin/catalog', '/admin/partners', '/admin/audit'],
  },
};

const VIEWPORTS = (process.env.VIEWPORTS || 'desk:1280x800,mob:390x844').split(',').map((v) => {
  const [name, wh] = v.split(':'); const [w, h] = wh.split('x').map(Number); return { name, w, h };
});

const LEGACY = {
  'rgb(27, 31, 59)': 'navy #1B1F3B', 'rgb(197, 160, 89)': 'gold #C5A059', 'rgb(163, 126, 68)': 'gold-dark #A37E44',
  'rgb(184, 147, 90)': 'bronze #B8935A', 'rgb(253, 248, 238)': 'gold-light #FDF8EE', 'rgb(226, 191, 112)': 'gold-hover #E2BF70',
  'rgb(250, 249, 246)': 'cream #FAF9F6', 'rgb(12, 14, 30)': 'slate-dark #0C0E1E', 'rgb(122, 92, 40)': 'gold-text #7A5C28',
  'rgb(107, 79, 30)': 'editorial ink #6B4F1E',
};

async function inspect(page) {
  return page.evaluate((LEGACY) => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05; };
    const sel = (el) => { let s = el.tagName.toLowerCase(); if (el.id) s += '#' + el.id; const c = (el.getAttribute('class') || '').trim().split(/\s+/).slice(0, 3).join('.'); if (c) s += '.' + c; return s.slice(0, 90); };
    const hits = {}; const samples = [];
    for (const el of document.querySelectorAll('body *')) {
      if (!vis(el) || el.closest('svg[data-brand-mark], [data-palette-swatch]')) continue;
      const s = getComputedStyle(el);
      const props = { color: s.color, bg: s.backgroundColor, border: s.borderTopWidth !== '0px' ? s.borderTopColor : null, outline: s.outlineStyle !== 'none' ? s.outlineColor : null, fill: el instanceof SVGElement ? s.fill : null };
      for (const [k, v] of Object.entries(props)) {
        if (v && LEGACY[v]) { const key = `${LEGACY[v]} (${k})`; hits[key] = (hits[key] || 0) + 1; if (samples.length < 12) samples.push(`${key} → ${sel(el)}`); }
      }
    }
    const small = [];
    for (const el of document.querySelectorAll('a[href], button, [role="button"], input:not([type="hidden"]), select, textarea, [role="tab"], [role="checkbox"], [role="switch"]')) {
      if (!vis(el)) continue; const r = el.getBoundingClientRect();
      const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
      if (!inline && (r.width < 24 || r.height < 24)) small.push(`${sel(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    const brokenImgs = [...document.images].filter((i) => i.complete && i.naturalWidth === 0 && vis(i)).map((i) => i.currentSrc || i.src).slice(0, 8);
    const coralMark = [...document.querySelectorAll('svg path, svg rect, svg circle')].some((p) => (p.getAttribute('fill') || '').toUpperCase() === '#EF826D');
    const brandImg = [...document.querySelectorAll('img')].some((i) => /\/brand\/confit-(logo|symbol)/.test(i.src));
    const main = document.querySelector('main');
    return {
      h1: (document.querySelector('h1')?.textContent || '').trim().slice(0, 80),
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      canvas: { html: getComputedStyle(document.documentElement).backgroundColor, body: getComputedStyle(document.body).backgroundColor, main: main ? getComputedStyle(main).backgroundColor : null },
      legacyHits: hits, legacySamples: samples, logo: coralMark || brandImg,
      smallTargets: small.length, smallSamples: small.slice(0, 6), brokenImgs,
      dir: document.documentElement.dir || 'ltr',
    };
  }, LEGACY);
}

async function runAxe(page) {
  await page.addScriptTag({ content: axeSource });
  return page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] }, resultTypes: ['violations'] });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, target: v.nodes.slice(0, 3).map((n) => n.target.join(' ')) }));
  });
}

const browser = await chromium.launch();
const results = [];
for (const [group, cfg] of Object.entries(GROUPS)) {
  if (only.length && !only.includes(group)) continue;
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
    await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
    // UI_LANG=ar runs the same pass in Arabic (the app reads `confit_lang`).
    if (UI_LANG) await ctx.addInitScript((lang) => { try { localStorage.setItem('confit_lang', lang); } catch {} }, UI_LANG);
    const page = await ctx.newPage();
    const consoleErrors = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 160)); });
    page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e.message).slice(0, 160)));
    await page.goto(BASE + '/privacy', { waitUntil: 'domcontentloaded' });
    if (cfg.user) {
      const res = await page.request.post(BASE + '/api/v1/auth/login', { data: { email: cfg.user, password: PASSWORD } });
      if (!res.ok()) { console.error(`login failed for ${group}: ${res.status()}`); await ctx.close(); continue; }
      const body = await res.json();
      await page.evaluate((u) => localStorage.setItem('confit_user', JSON.stringify(u)), body.user);
    }
    for (const route of cfg.routes) {
      if (routeFilter.length && !routeFilter.includes(route)) continue;
      consoleErrors.length = 0;
      const t0 = Date.now();
      try {
        await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 30000 });
      } catch { /* networkidle may not settle (polling) — capture anyway */ }
      await page.waitForTimeout(900);
      const info = await inspect(page);
      let axe = [];
      try { axe = await runAxe(page); } catch (e) { axe = [{ id: 'axe-error', impact: 'n/a', nodes: 0, target: [String(e).slice(0, 80)] }]; }
      const slug = `${LABEL}_${group}_${vp.name}_${route.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home'}`;
      const file = path.join(OUT, slug + '.png');
      await page.screenshot({ path: file, fullPage: true });
      const row = { label: LABEL, group, viewport: vp.name, route, finalUrl: page.url().replace(BASE, ''), ms: Date.now() - t0, ...info, axe, consoleErrors: [...consoleErrors].slice(0, 6), screenshot: file };
      results.push(row);
      const lh = Object.values(info.legacyHits).reduce((a, b) => a + b, 0);
      console.log(`${group.padEnd(8)} ${vp.name} ${route.padEnd(34)} → ${row.finalUrl.padEnd(28)} legacy=${lh} axe=${axe.length} ovf=${info.overflowX} logo=${info.logo} small=${info.smallTargets} err=${consoleErrors.length}`);
    }
    await ctx.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(OUT, `${LABEL}_results.json`), JSON.stringify(results, null, 2));
console.log(`\nwrote ${results.length} rows → ${path.join(OUT, LABEL + '_results.json')}`);
