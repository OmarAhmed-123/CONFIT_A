#!/usr/bin/env node
/**
 * Keyboard, focus and dialog guarantees for the floating AI Stylist control.
 *
 * fab_probe.mjs measures GEOMETRY: what the control's box intersects. This
 * file measures BEHAVIOUR, which geometry cannot prove:
 *
 *   1. the control is reachable by keyboard even while it is deferred
 *      off-screen by the scroll rule;
 *   2. it becomes visible again the moment it receives focus, so the user is
 *      never parked on an invisible focus target;
 *   3. NO focus stop on the page is ever an invisible element;
 *   4. no FOCUSED element is ever entirely behind the control (WCAG 2.2
 *      SC 2.4.11 Focus Not Obscured, measured per focus stop, not inferred);
 *   5. opening the stylist drawer from the control keeps the focus trap and
 *      returns focus to the opener on Escape;
 *   6. scrolling never steals focus or hides a focused element.
 *
 * Deliberately NOT tested here: the on-screen mobile keyboard. Headless
 * Chromium has no soft keyboard, so "the control collides with the keyboard"
 * cannot be measured in CI. See the PR's Phase 4 notes.
 *
 *   BASE=http://127.0.0.1:4173 node scripts/fab_keyboard_probe.mjs
 */
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://127.0.0.1:4173';
const ROUTES = ['/builder', '/fit', '/cart', '/wardrobe', '/'];
const MOBILE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 800 };
const MAX_TABS = 90;

let failures = 0;
const check = (ok, id, detail) => {
  if (!ok) failures++;
  console.log(`  ${ok ? 'PASS' : 'FAIL'} ${id}${detail ? '  ' + JSON.stringify(detail) : ''}`);
};

/** Everything the browser would consider a focus stop, in DOM order. */
const FOCUSABLE = [
  'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea',
  '[tabindex]:not([tabindex="-1"])', '[role=button]',
].join(',');

const browser = await chromium.launch();

for (const vp of [MOBILE, DESKTOP]) {
  const label = `${vp.width}x${vp.height}`;
  for (const route of ROUTES) {
    const ctx = await browser.newContext({ viewport: vp, reducedMotion: 'reduce' });
    await ctx.addInitScript(() => {
      try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {}
    });
    const page = await ctx.newPage();
    await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(1500);
    console.log(`\n=== ${label} ${route} ===`);

    /* 1 + 2 + 3 + 4: walk focus stops with the control deferred. */
    await page.evaluate(() => window.scrollBy(0, 600));   // trigger scroll deferral
    await page.waitForTimeout(500);
    const deferred = await page.evaluate(() => {
      const a = document.querySelector('.stylist-fab-anchor');
      return a ? a.getAttribute('data-fab-hidden') === 'true' : null;
    });

    const walk = await page.evaluate(async (sel) => {
      const FOCUSABLE_SEL = sel;
      const anchor = document.querySelector('.stylist-fab-anchor');
      const isVisible = (el) => {
        const s = getComputedStyle(el);
        if (s.visibility === 'hidden' || s.display === 'none') return false;
        if (Number(s.opacity) < 0.1) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      };
      const inViewport = (el) => {
        const r = el.getBoundingClientRect();
        return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
      };

      // Start from the very top of the document.
      document.body.focus();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();

      const stops = [];
      let reachedFab = false;
      let fabVisibleWhenFocused = null;
      let invisibleStops = 0;
      let fullyObscured = 0;

      const all = [...document.querySelectorAll(FOCUSABLE_SEL)].filter((el) => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
          && el.tabIndex !== -1;
      });

      for (const el of all.slice(0, 120)) {
        el.focus();
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
        if (document.activeElement !== el) continue;   // not actually focusable
        const desc = {
          tag: el.tagName.toLowerCase(),
          name: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 34),
        };
        if (!isVisible(el)) { invisibleStops++; stops.push({ ...desc, why: 'invisible' }); continue; }
        // 4. is the FOCUSED element entirely behind the control?
        // The control sitting on top of ITSELF is not an obstruction - the
        // anchor is the positioned wrapper and the button fills it. Skip the
        // control and its own children, then measure everything else.
        const isSelf = !!(anchor && anchor.contains(el));
        if (anchor && !isSelf) {
          const s = getComputedStyle(anchor);
          const deferredNow = anchor.getAttribute('data-fab-hidden') === 'true'
            || s.visibility === 'hidden' || s.pointerEvents === 'none';
          if (!deferredNow) {
            const r = el.getBoundingClientRect();
            const f = anchor.getBoundingClientRect();
            const inside = r.left >= f.left && r.right <= f.right && r.top >= f.top && r.bottom <= f.bottom;
            const coversAll = r.width > 0 && r.height > 0
              && !(r.right <= f.left || r.left >= f.right || r.bottom <= f.top || r.top >= f.bottom)
              && inside;
            if (coversAll) { fullyObscured++; stops.push({ ...desc, why: 'fully-obscured' }); }
          }
        }
        if (anchor && anchor.contains(el)) {
          reachedFab = true;
          fabVisibleWhenFocused = isVisible(el) && inViewport(el);
        }
      }
      return { total: all.length, reachedFab, fabVisibleWhenFocused, invisibleStops, fullyObscured, stops: stops.slice(0, 8) };
    }, FOCUSABLE);

    console.log(`  (scroll deferral active: ${deferred})`);
    check(walk.invisibleStops === 0, 'no focus stop lands on an invisible element',
      walk.invisibleStops ? { count: walk.invisibleStops, stops: walk.stops } : undefined);
    check(walk.fullyObscured === 0, 'no focused element is ENTIRELY behind the control (SC 2.4.11)',
      walk.fullyObscured ? { count: walk.fullyObscured, stops: walk.stops } : undefined);
    check(walk.reachedFab === true, 'the control IS reachable by keyboard while deferred');
    check(walk.fabVisibleWhenFocused === true,
      'the control becomes visible again when it receives focus',
      { visible: walk.fabVisibleWhenFocused });

    /* 5: dialog focus trap + focus restoration. */
    const dialog = await page.evaluate(async () => {
      const anchor = document.querySelector('.stylist-fab-anchor');
      const btn = anchor && anchor.querySelector('button');
      if (!btn) return { err: 'no FAB button' };
      btn.focus();
      await new Promise((r) => requestAnimationFrame(r));
      const openerName = (btn.getAttribute('aria-label') || '').trim();
      btn.click();
      await new Promise((r) => setTimeout(r, 1200));
      const d = document.querySelector('[role="dialog"]');
      if (!d) return { err: 'dialog did not open', openerName };
      const trapOkInit = d.contains(document.activeElement);
      return { openerName, opened: true, ariaModal: d.getAttribute('aria-modal'), trapOkInit };
    });

    if (dialog.err) {
      check(false, 'stylist drawer opens from the control', dialog);
    } else {
      check(dialog.opened === true, 'stylist drawer opens from the control');
      // Tab 30 times: focus must never leave the dialog.
      let escaped = 0;
      for (let i = 0; i < 30; i++) {
        await page.keyboard.press('Tab');
        const inside = await page.evaluate(() => {
          const d = document.querySelector('[role="dialog"]');
          return !!(d && document.activeElement && d.contains(document.activeElement));
        });
        if (!inside) escaped++;
      }
      check(escaped === 0, 'focus is trapped inside the drawer (30 tabs)', { escaped });

      await page.keyboard.press('Escape');
      await page.waitForTimeout(700);
      const restored = await page.evaluate(() => {
        const el = document.activeElement;
        return {
          name: (el && (el.getAttribute('aria-label') || el.textContent) || '').trim().slice(0, 40),
          tag: el ? el.tagName.toLowerCase() : null,
          stillOpen: !!document.querySelector('[role="dialog"]'),
        };
      });
      check(restored.stillOpen === false, 'Escape closes the drawer');
      check(!!restored.name && restored.name === dialog.openerName,
        'focus returns to the opener after close',
        { expected: dialog.openerName, got: restored });
    }

    /* 6: scrolling must not steal focus or hide the focused element. */
    const scroll = await page.evaluate(async () => {
      const el = document.querySelector('a[href], button, input, select, textarea');
      if (!el) return { err: 'no focusable' };
      el.focus();
      const before = document.activeElement;
      window.scrollBy(0, 400);
      await new Promise((r) => setTimeout(r, 500));
      const s = getComputedStyle(document.activeElement || document.body);
      return {
        kept: document.activeElement === before,
        visible: s.visibility !== 'hidden' && Number(s.opacity) >= 0.1,
      };
    });
    if (!scroll.err) {
      check(scroll.kept === true, 'scrolling does not steal focus', scroll);
      check(scroll.visible === true, 'the focused element stays visible while scrolling', scroll);
    }

    await ctx.close();
  }
}

await browser.close();
console.log(`\n${failures === 0 ? 'FAB KEYBOARD/FOCUS PROBE: all checks passed' : `FAB KEYBOARD/FOCUS PROBE: ${failures} failing check(s)`}`);
process.exit(failures === 0 ? 0 : 1);
