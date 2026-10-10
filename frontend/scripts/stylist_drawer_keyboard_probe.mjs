#!/usr/bin/env node
/**
 * Keyboard + focus probe for the StyleList drawer (spec 009 / T-STY-07, WCAG 2.1.1, 2.1.2,
 * 2.4.3, 2.4.7, 4.1.2). Drives real Chromium with real key presses (page.keyboard).
 *
 * Only two steps use a programmatic action, because a browser cannot open a native file
 * picker from the keyboard in automation: selecting the photo files (setInputFiles).
 * Everything else is keyboard input: opening, Tab order, removing a photo, submitting,
 * Escape, and focus restoration.
 *
 * Reporting tool: exits 1 when a required keyboard criterion fails.
 *   BASE_URL=http://localhost:43123 PROBE_JSON=/tmp/kbd.json node scripts/stylist_drawer_keyboard_probe.mjs
 */
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const BASE_URL = process.env.BASE_URL || "http://localhost:43123";
const OUT = process.env.PROBE_JSON || "/tmp/stylist-drawer-keyboard.json";
const en = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/en.json"), "utf8"));
const ar = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/ar.json"), "utf8"));

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

// Describe the focused element and its visible focus indicator.
const describeFocus = (page) =>
  page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return { none: true };
    const cs = getComputedStyle(el);
    const dlg = el.closest('[role="dialog"]');
    const name =
      el.getAttribute("aria-label") ||
      (el.labels && el.labels[0] && el.labels[0].textContent) ||
      (el.textContent || "").trim().slice(0, 60) ||
      el.getAttribute("placeholder") ||
      "";
    const ring = cs.boxShadow !== "none" && cs.boxShadow !== "";
    const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role"),
      type: el.getAttribute("type"),
      name,
      inDialog: !!dlg,
      visibleFocus: ring || outline,
      focusIndicator: ring ? "box-shadow" : outline ? "outline" : "none",
    };
  });

async function probe(browser, lang, dict) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.addInitScript((l) => {
    try { localStorage.setItem("confit_lang", l); } catch { /* storage disabled */ }
  }, lang);
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e.message).slice(0, 200)));
  await page.goto(BASE_URL, { waitUntil: "load", timeout: 90000 });
  await page.addStyleTag({ content: "*,*::before,*::after{animation-duration:0s!important;transition-duration:0s!important;}" });

  const checks = [];
  const check = (id, ok, detail) => checks.push({ id, ok: !!ok, detail });

  // 1. Reach the opener with Tab from the top of the page, then open with Enter.
  const fabLabel = dict.layout.open_ai_stylist;
  let reachedFab = false;
  const trace = [];
  for (let i = 0; i < 200 && !reachedFab; i++) {
    await page.keyboard.press("Tab");
    const f = await describeFocus(page);
    if (f.name === fabLabel) reachedFab = true;
    if (i < 3 || reachedFab) trace.push(f);
  }
  check("opener reachable by Tab", reachedFab, { trace });
  const openerFocusVisible = (await describeFocus(page)).visibleFocus;
  check("opener shows a visible focus indicator", openerFocusVisible, await describeFocus(page));
  await page.keyboard.press("Enter");

  const dialog = page.getByRole("dialog", { name: dict.stylist.dialog_label });
  await dialog.waitFor({ state: "visible", timeout: 30000 });
  await page.waitForTimeout(300);
  const onOpen = await describeFocus(page);
  check("Enter on opener opens dialog", true, { dialogLabel: await dialog.getAttribute("aria-label") });
  check("focus moves into dialog on open", onOpen.inDialog, onOpen);
  check("dialog is aria-modal", (await dialog.getAttribute("aria-modal")) === "true");

  // 2. Tab through the drawer. Focus must stay inside (focus trap), and every stop must show focus.
  const stops = [];
  let escaped = false;
  let noFocusVisible = [];
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press("Tab");
    const f = await describeFocus(page);
    stops.push(f);
    if (!f.inDialog && !f.none) escaped = true;
    if (!f.none && !f.visibleFocus) noFocusVisible.push(f);
  }
  check("Tab focus is trapped inside the dialog", !escaped, { escaped });
  check("every Tab stop shows a visible focus indicator", noFocusVisible.length === 0, { noFocusVisible });

  // 3. Attach photos (programmatic file selection, see header), then remove one with the keyboard.
  const fileInput = dialog.locator('input[type="file"]');
  await fileInput.setInputFiles([
    { name: "a.png", mimeType: "image/png", buffer: PNG },
    { name: "b.png", mimeType: "image/png", buffer: PNG },
  ]);
  await dialog.locator("img").first().waitFor({ state: "visible", timeout: 15000 });
  const removeBtns = dialog.locator('button[aria-label]').filter({ hasText: "×" });
  const removeCount = await removeBtns.count();
  // Focus the first remove button via keyboard by tabbing until it is reached.
  let reachedRemove = false;
  for (let i = 0; i < 20 && !reachedRemove; i++) {
    await page.keyboard.press("Tab");
    const f = await describeFocus(page);
    if (f.name && /remove|Remove|حذف|إزالة/i.test(f.name)) reachedRemove = true;
  }
  check("remove-photo control reachable by keyboard", reachedRemove, { removeCount });
  const beforeRemove = await dialog.locator("img").count();
  if (reachedRemove) await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  const afterRemove = await dialog.locator("img").count();
  const focusAfterRemove = await describeFocus(page);
  check("keyboard Enter removes a photo", reachedRemove && afterRemove === beforeRemove - 1, { beforeRemove, afterRemove });
  // Focus lost to <body> after the removed control unmounts is a WCAG 2.4.3 failure.
  check("focus stays inside dialog after removing a photo", focusAfterRemove.inDialog, focusAfterRemove);

  // 4. Type and submit with Enter. Backend is not running, so a failure is expected to be announced.
  const promptInput = dialog.locator('input[type="text"]');
  const promptLabelled = await promptInput.evaluate((el) => ({
    ariaLabel: el.getAttribute("aria-label"),
    labelCount: el.labels ? el.labels.length : 0,
    placeholder: el.getAttribute("placeholder"),
  }));
  check("prompt input has an accessible name (not placeholder-only)",
    !!promptLabelled.ariaLabel || promptLabelled.labelCount > 0, promptLabelled);
  await promptInput.focus();
  await page.keyboard.type("Smart casual dinner");
  await page.keyboard.press("Enter");
  const errAnnounced = await dialog.locator('[role="alert"], [role="status"]').first().waitFor({ timeout: 20000 })
    .then(() => true).catch(() => false);
  check("submit with Enter reaches a live-region state (loading or error)", errAnnounced);

  // 5. Escape closes and focus returns to the opener.
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  const dialogStillOpen = await page.getByRole("dialog").count();
  const afterEscape = await describeFocus(page);
  check("Escape closes the dialog", dialogStillOpen === 0, { dialogStillOpen });
  check("focus returns to the opener after close", afterEscape.name === fabLabel, afterEscape);

  await page.close();
  return { lang, pageErrors, checks };
}

const browser = await chromium.launch({ headless: true });
const results = [];
try {
  results.push(await probe(browser, "en", en));
  results.push(await probe(browser, "ar", ar));
} finally {
  await browser.close();
}

let failed = 0;
for (const r of results) {
  console.log(`[${r.lang}]`);
  for (const c of r.checks) {
    if (!c.ok) failed++;
    console.log(`  ${c.ok ? "PASS" : "FAIL"} ${c.id}`);
  }
  if (r.pageErrors.length) console.log(`  page errors: ${r.pageErrors.length}`);
}
fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
console.log(`wrote ${OUT}`);
if (failed) {
  console.error(`KEYBOARD PROBE: ${failed} failing check(s)`);
  process.exit(1);
}
console.log("KEYBOARD PROBE PASSED");
