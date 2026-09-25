#!/usr/bin/env node
/**
 * Real-browser mobile evidence for Admin Governance.
 *
 * This is deliberately separate from jsdom/axe: Chromium computes actual
 * layout, overflow, contrast, focus and direction at 390/414/768/1024/1440 px.
 * It logs into a LOCAL seeded admin account only. Run against Vite + local API:
 *
 *   node scripts/verify_admin_governance_mobile.mjs
 *
 * PLAYWRIGHT_CORE_PATH may point to a temporary playwright-core install;
 * CHROMIUM_PATH defaults to /usr/bin/chromium. It writes a machine-readable
 * report and 390px en/ar screenshots under docs/evidence/.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const playwrightPath = process.env.PLAYWRIGHT_CORE_PATH ||
  path.resolve('frontend/node_modules/playwright-core/index.js');
const playwright = await import(pathToFileURL(playwrightPath).href);
const chromium = playwright.chromium ?? playwright.default?.chromium;
const baseURL = process.env.CONFIT_BROWSER_URL || 'http://localhost:43123';
const outDir = path.resolve('docs/evidence');
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
const page = await context.newPage();
await page.goto(baseURL, { waitUntil: 'networkidle' });
const login = await page.evaluate(async () => {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@confit.io', password: 'Password123!' }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`local login failed: ${response.status}`);
  localStorage.setItem('confit_user', JSON.stringify(body.user));
  return { role: body.user.role, status: response.status };
});
if (login.role !== 'admin') throw new Error(`expected local admin, got ${login.role}`);

const widths = [390, 414, 768, 1024, 1440];
const results = [];
for (const width of widths) {
  await page.setViewportSize({ width, height: width <= 414 ? 844 : 900 });
  await page.goto(`${baseURL}/admin/audit`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: /Audit Trail|سجل التدقيق/i }).waitFor();
  const data = await page.evaluate(() => {
    const nav = document.querySelector('[data-testid="brand-primary-nav"]');
    const auditRegion = document.querySelector('main [role="region"]');
    const links = Array.from(nav?.querySelectorAll('a') || []);
    const governance = links.slice(0, 2).map((link) => {
      const r = link.getBoundingClientRect();
      return {
        text: link.textContent?.trim(),
        left: Math.round(r.left), right: Math.round(r.right),
        inInitialViewport: r.left >= 0 && r.right <= window.innerWidth,
        height: Math.round(r.height),
      };
    });
    const details = document.querySelector('button[aria-controls^="audit-row-details-"]');
    const dr = details?.getBoundingClientRect();

    // Computed-color evidence for the current real integrity state. This is
    // not a formal WCAG audit; it catches the concrete regression where tiny
    // status text inherited a low-contrast colour on the light card.
    const parseColor = (value) => {
      const parts = value.match(/[\d.]+/g)?.map(Number) || [];
      return { r: parts[0] || 0, g: parts[1] || 0, b: parts[2] || 0,
        a: parts.length > 3 ? parts[3] : 1 };
    };
    const blend = (top, bottom) => ({
      r: top.r * top.a + bottom.r * (1 - top.a),
      g: top.g * top.a + bottom.g * (1 - top.a),
      b: top.b * top.a + bottom.b * (1 - top.a),
      a: 1,
    });
    const effectiveBackground = (element) => {
      const layers = [];
      for (let node = element; node instanceof HTMLElement; node = node.parentElement) {
        layers.push(parseColor(getComputedStyle(node).backgroundColor));
      }
      return layers.reverse().reduce((base, layer) => blend(layer, base),
        { r: 255, g: 255, b: 255, a: 1 });
    };
    const luminance = (color) => {
      const channel = (value) => {
        const normal = value / 255;
        return normal <= 0.04045 ? normal / 12.92 : ((normal + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
    };
    const contrast = (element) => {
      const foreground = parseColor(getComputedStyle(element).color);
      const background = effectiveBackground(element);
      const light = Math.max(luminance(foreground), luminance(background));
      const dark = Math.min(luminance(foreground), luminance(background));
      return Number(((light + 0.05) / (dark + 0.05)).toFixed(2));
    };
    const integrity = document.querySelector('[data-testid="audit-integrity"]');
    const contrastSamples = Array.from(integrity?.querySelectorAll('span, p') || [])
      .filter((element) => element.textContent?.trim() && getComputedStyle(element).display !== 'none')
      .map((element) => ({ text: element.textContent.trim().slice(0, 80), ratio: contrast(element) }));
    return {
      width: window.innerWidth,
      direction: document.documentElement.dir,
      pageClientWidth: document.documentElement.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
      pageHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      navClientWidth: nav?.clientWidth,
      navScrollWidth: nav?.scrollWidth,
      navHorizontallyScrollable: Boolean(nav && nav.scrollWidth > nav.clientWidth),
      allSevenDestinationsPresent: links.length === 7,
      governance,
      auditRegionClientWidth: auditRegion?.clientWidth,
      auditRegionScrollWidth: auditRegion?.scrollWidth,
      tableContainedByOwnScroller: Boolean(auditRegion && auditRegion.scrollWidth > auditRegion.clientWidth),
      detailsButton: dr ? {
        width: Math.round(dr.width), height: Math.round(dr.height), tag: details?.tagName,
        accessibleName: details?.getAttribute('aria-label') || details?.textContent?.trim(),
      } : null,
      integrityContrast: {
        samples: contrastSamples,
        minimumRatio: contrastSamples.length
          ? Math.min(...contrastSamples.map((sample) => sample.ratio)) : null,
      },
    };
  });
  if (data.pageHorizontalOverflow) throw new Error(`page overflows horizontally at ${width}px`);
  if (!data.allSevenDestinationsPresent) throw new Error(`nav destination missing at ${width}px`);
  if (width <= 414 && !data.navHorizontallyScrollable) throw new Error(`nav not scrollable at ${width}px`);
  if (width <= 414 && data.governance.some((x) => !x.inInitialViewport)) {
    throw new Error(`governance links not initially visible at ${width}px`);
  }
  if (!data.detailsButton || data.detailsButton.tag !== 'BUTTON' || data.detailsButton.height < 44) {
    throw new Error(`details target is not a >=44px native button at ${width}px`);
  }
  if (!data.detailsButton.accessibleName) {
    throw new Error(`details target has no screen-reader name at ${width}px`);
  }
  if (data.integrityContrast.minimumRatio === null || data.integrityContrast.minimumRatio < 4.5) {
    throw new Error(`integrity text contrast below 4.5:1 at ${width}px: ${JSON.stringify(data.integrityContrast)}`);
  }
  results.push(data);
  if (width === 390) {
    await page.screenshot({ path: path.join(outDir, 'admin-audit-390-en.png'), fullPage: true });
  }
}

// Real keyboard focus (not element.focus()): tab until the row details control.
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(`${baseURL}/admin/audit`, { waitUntil: 'networkidle' });
let keyboardFocus = null;
for (let i = 0; i < 30; i += 1) {
  await page.keyboard.press('Tab');
  keyboardFocus = await page.evaluate(() => {
    const el = document.activeElement;
    if (!(el instanceof HTMLElement)) return null;
    return {
      tag: el.tagName,
      ariaControls: el.getAttribute('aria-controls'),
      outlineStyle: getComputedStyle(el).outlineStyle,
      boxShadow: getComputedStyle(el).boxShadow,
    };
  });
  if (keyboardFocus?.ariaControls?.startsWith('audit-row-details-')) break;
}
if (!keyboardFocus?.ariaControls?.startsWith('audit-row-details-')) {
  throw new Error('real Tab traversal did not reach the audit-row details button');
}
if (keyboardFocus.outlineStyle === 'none' && keyboardFocus.boxShadow === 'none') {
  throw new Error('details button received keyboard focus with no visible indicator');
}
await page.keyboard.press('Enter');
const detailsControl = page.locator('button[aria-controls^="audit-row-details-"]').first();
const expandedByKeyboard = await detailsControl.getAttribute('aria-expanded');
if (expandedByKeyboard !== 'true') throw new Error('Enter did not expand audit row');
const focusAfterOpen = await page.evaluate(() =>
  document.activeElement?.getAttribute('aria-controls')?.startsWith('audit-row-details-') ?? false);
if (!focusAfterOpen) throw new Error('focus left the details control after opening');
await page.keyboard.press('Space');
const collapsedBySpace = await detailsControl.getAttribute('aria-expanded');
if (collapsedBySpace !== 'false') throw new Error('Space did not collapse audit row');
const focusAfterClose = await page.evaluate(() =>
  document.activeElement?.getAttribute('aria-controls')?.startsWith('audit-row-details-') ?? false);
if (!focusAfterClose) throw new Error('focus left the details control after closing');

// Arabic/RTL at the same 390px real viewport.
await page.evaluate(() => localStorage.setItem('confit_lang', 'ar'));
await page.reload({ waitUntil: 'networkidle' });
await page.getByRole('heading', { name: /سجل التدقيق/ }).waitFor();
const rtl = await page.evaluate(() => ({
  dir: document.documentElement.dir,
  platformAdmin: Array.from(document.querySelectorAll('[data-testid="brand-primary-nav"] a')).some((a) => a.textContent?.includes('إدارة المنصة')),
  auditTrail: Array.from(document.querySelectorAll('[data-testid="brand-primary-nav"] a')).some((a) => a.textContent?.includes('سجل التدقيق')),
  overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
}));
if (rtl.dir !== 'rtl' || !rtl.platformAdmin || !rtl.auditTrail || rtl.overflow) {
  throw new Error(`RTL mobile contract failed: ${JSON.stringify(rtl)}`);
}
await page.screenshot({ path: path.join(outDir, 'admin-audit-390-ar.png'), fullPage: true });

const report = {
  ran_at: new Date().toISOString(),
  environment: process.env.CONFIT_BROWSER_ENVIRONMENT ||
    'LOCAL only (Vite + migrated database; not production)',
  browser: await browser.version(),
  login: { status: login.status, role: login.role, credentials: 'local seeded account; no secret recorded' },
  routes: ['/admin/audit'],
  widths: results,
  keyboard: {
    reachedDetailsButton: true, visibleFocusIndicator: true,
    expandedWithEnter: true, collapsedWithSpace: true,
    focusRetainedAfterOpen: focusAfterOpen, focusRetainedAfterClose: focusAfterClose,
    ...keyboardFocus,
  },
  rtl390: rtl,
  limits: [
    'This verifies Chromium layout/interaction, not screen-reader speech.',
    'This does not constitute WCAG 2.2 conformance.',
    'Production admin route was not authenticated by this script.',
  ],
};
fs.writeFileSync(path.join(outDir, 'admin-governance-browser-report.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
await browser.close();
