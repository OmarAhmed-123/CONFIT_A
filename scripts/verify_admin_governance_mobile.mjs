#!/usr/bin/env node
/**
 * Real-browser mobile evidence for Admin Governance.
 *
 * This is deliberately separate from jsdom/axe: Chromium computes actual
 * layout, overflow, focus dimensions and direction at 390/414/768/1024 px.
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

const widths = [390, 414, 768, 1024];
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
      detailsButton: dr ? { width: Math.round(dr.width), height: Math.round(dr.height), tag: details?.tagName } : null,
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
const expandedByKeyboard = await page.locator('button[aria-controls^="audit-row-details-"]').first().getAttribute('aria-expanded');
if (expandedByKeyboard !== 'true') throw new Error('Enter did not expand audit row');

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
  environment: 'LOCAL only (Vite + migrated SQLite; not production)',
  browser: await browser.version(),
  login: { status: login.status, role: login.role, credentials: 'local seeded account; no secret recorded' },
  routes: ['/admin/audit'],
  widths: results,
  keyboard: { reachedDetailsButton: true, visibleFocusIndicator: true, expandedWithEnter: true, ...keyboardFocus },
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
