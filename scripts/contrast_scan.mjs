#!/usr/bin/env node
/**
 * DOM-level contrast sweep — catches what axe's static pass misses.
 *
 * axe skipped an "Open Virtual Try-On" button on /fit that measured 1.00:1
 * (charcoal text on the charcoal hero): the background came from an ancestor,
 * so no rule in the class string looked wrong. This walks every visible text
 * node on a real rendered page and compares the computed foreground against
 * the first non-transparent ancestor background.
 *
 *   BASE=http://localhost:43123 node scripts/contrast_scan.mjs
 */
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://localhost:43123';
const PASSWORD = 'Password123!';
const PRODUCT = 'goodyear-welted-leather-oxford-shoes';
const ORDER = 'CONF-8821094A';
const UI_LANG = process.env.UI_LANG || '';

const GROUPS = {
  guest: { user: null, routes: ['/', '/discover', '/products', `/product/${PRODUCT}`, '/builder', '/outfits', '/try-on', '/fit', '/wardrobe', '/cart', '/orders', '/privacy', '/terms', '/gdpr', '/reset-password', '/verify-email', '/email/unsubscribe', '/looks/invalid-token', '/this-route-does-not-exist', '/b2b', '/admin'] },
  consumer: { user: 'shopper@confit.io', routes: ['/', '/discover', `/product/${PRODUCT}`, '/builder', '/my-looks', '/try-on', '/fit', '/wardrobe', '/cart', '/checkout', '/orders', `/orders/${ORDER}`, '/returns', '/profile', '/settings', '/notifications', '/b2b', '/admin'] },
  brand: { user: 'brand@cos.com', routes: ['/b2b', '/b2b/catalog', '/b2b/inventory', '/b2b/orders', '/b2b/analytics', '/b2b/placements', '/partner', '/admin'] },
  admin: { user: 'admin@confit.io', routes: ['/admin', '/admin/analytics', '/admin/catalog', '/admin/partners', '/admin/audit'] },
};
const VIEWPORTS = [{ name: 'desk', w: 1280, h: 800 }, { name: 'mob', w: 390, h: 844 }];

const PROBE = (minRatio) => {
  const lum = (rgb) => {
    const m = rgb.match(/[\d.]+/g);
    if (!m) return null;
    const [r, g, b] = m.slice(0, 3).map(Number).map((v) => { const s = v / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const alphaOf = (rgb) => { const m = rgb.match(/[\d.]+/g); return m && m.length > 3 ? Number(m[3]) : 1; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  /** Blend the chain of backgrounds down to one opaque colour. */
  const effectiveBg = (el) => {
    const stack = [];
    let n = el;
    while (n && n !== document.documentElement.parentElement) {
      const bg = getComputedStyle(n).backgroundColor;
      const a = alphaOf(bg);
      if (a > 0) { stack.push([bg, a]); if (a >= 1) break; }
      n = n.parentElement;
    }
    stack.push(['rgb(255, 255, 255)', 1]);
    let out = stack[stack.length - 1][0].match(/[\d.]+/g).slice(0, 3).map(Number);
    for (let i = stack.length - 2; i >= 0; i--) {
      const c = stack[i][0].match(/[\d.]+/g).slice(0, 3).map(Number);
      const a = stack[i][1];
      out = out.map((v, k) => c[k] * a + v * (1 - a));
    }
    return `rgb(${out.map((v) => Math.round(v)).join(', ')})`;
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.1;
  };
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue;
    if (el.closest('svg')) continue;
    // only elements that own a text node directly
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!own) continue;
    const s = getComputedStyle(el);
    if (s.webkitTextFillColor === 'transparent' || s.color === 'rgba(0, 0, 0, 0)') continue;
    // skip anything the user cannot act on or read (decorative/aria-hidden)
    if (el.closest('[aria-hidden="true"]') && !el.closest('[role="alert"]')) continue;
    const fg = s.color;
    const bg = effectiveBg(el);
    const px = parseFloat(s.fontSize);
    const bold = Number(s.fontWeight) >= 700;
    const large = px >= 24 || (bold && px >= 18.66);
    const need = large ? 3.0 : 4.5;
    const r = ratio(fg, bg);
    if (r >= need) continue;
    const disabled = el.matches('button:disabled, [aria-disabled="true"], input:disabled, select:disabled, textarea:disabled')
      || !!el.closest('button:disabled, [aria-disabled="true"]');
    out.push({
      ratio: Number(r.toFixed(2)), need, disabled, px: Math.round(px * 10) / 10,
      text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60),
      sel: el.tagName.toLowerCase() + (el.getAttribute('class') ? '.' + el.getAttribute('class').trim().split(/\s+/).slice(0, 4).join('.') : ''),
      fg, bg,
    });
  }
  const seen = new Set();
  return out.filter((o) => { const k = o.sel + '|' + o.fg + '|' + o.bg; if (seen.has(k)) return false; seen.add(k); return true; })
    .sort((a, b) => a.ratio - b.ratio);
};

const browser = await chromium.launch();
let total = 0, hardTotal = 0;
for (const [group, cfg] of Object.entries(GROUPS)) {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, reducedMotion: 'reduce' });
    await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
    if (UI_LANG) await ctx.addInitScript((l) => { try { localStorage.setItem('confit_lang', l); } catch {} }, UI_LANG);
    const page = await ctx.newPage();
    await page.goto(`${BASE}/privacy`, { waitUntil: 'domcontentloaded' });
    if (cfg.user) {
      const res = await page.request.post(`${BASE}/api/v1/auth/login`, { data: { email: cfg.user, password: PASSWORD } });
      if (!res.ok()) { console.error(`login failed ${group}`); await ctx.close(); continue; }
      const body = await res.json();
      await page.evaluate((u) => localStorage.setItem('confit_user', JSON.stringify(u)), body.user);
    }
    for (const route of cfg.routes) {
      await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
      await page.waitForTimeout(700);
      const bad = await page.evaluate(PROBE);
      if (bad.length) {
        const hard = bad.filter((b) => !b.disabled);
        total += bad.length; hardTotal += hard.length;
        console.log(`\n### ${group} ${vp.name} ${route}  (${hard.length} actionable / ${bad.length} incl. disabled)`);
        for (const b of bad.slice(0, 8)) {
          console.log(`   ${b.ratio.toFixed(2)} need ${b.need}  ${b.disabled ? '[disabled] ' : ''}${b.px}px  ${b.sel.slice(0, 60)}`);
          console.log(`         "${b.text}"  ${b.fg} on ${b.bg}`);
        }
      }
    }
    await ctx.close();
  }
}
await browser.close();
console.log(`\nTOTAL findings: ${total} (${hardTotal} actionable, ${total - hardTotal} disabled/WCAG-exempt)`);
