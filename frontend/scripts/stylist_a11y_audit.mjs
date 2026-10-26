// Wardrobe stylist accessibility audit (P4) — automated part.
//
// Drives the REAL built SPA against the REAL API (no mocks): registers a user,
// adds three garments, opens Wardrobe → AI Stylist, generates a look with the
// keyboard only, saves it, opens Looks and checks the saved section — in EN
// and AR/RTL. For every state it records:
//   • axe-core violations (WCAG 2.x A/AA tags)
//   • the accessibility tree (ARIA snapshot) of the stylist region — this is
//     what a screen reader is given, engine-independent
//   • the focused element after result arrival (focus management, 2.4.3)
//   • live-region text that would be announced (role=status / aria-live)
//   • keyboard reachability of every control in the panel (Tab order)
//
// Usage (from frontend/): node scripts/stylist_a11y_audit.mjs --app http://127.0.0.1:4173 --api http://127.0.0.1:8000 \
//        [--browser chromium-headless-shell|firefox] [--exe /path/to/binary] [--out ../docs/qa/stylist_a11y_report.json]
import fs from "node:fs";
import path from "node:path";
import { chromium, firefox } from "playwright-core";

const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith("--") ? [a.slice(2), arr[i + 1]] : []).filter(Boolean));
const APP = args.app || "http://127.0.0.1:4173";
const API = args.api || "http://127.0.0.1:8000";
const OUT = args.out || "../docs/qa/stylist_a11y_report.json";
const BROWSER = args.browser || "chromium-headless-shell";
const AXE = fs.readFileSync(path.resolve("node_modules/axe-core/axe.min.js"), "utf8");

async function api(p, opts = {}) {
  const r = await fetch(API + "/api/v1" + p, { ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  const text = await r.text();
  let body; try { body = JSON.parse(text); } catch { body = text; }
  return { status: r.status, body };
}

async function seedUser(tag) {
  const email = `a11y_${tag}_${Date.now()}@confit.io`;
  const reg = await api("/auth/register", { method: "POST", body: JSON.stringify({ email, password: "Password123!", full_name: "A11y Audit" }) });
  if (reg.status !== 201) throw new Error("register failed " + reg.status + " " + JSON.stringify(reg.body));
  const token = reg.body.access_token;
  const h = { Authorization: `Bearer ${token}` };
  const items = [
    { title: "White Oxford Shirt", category: "Tops", subcategory: "Oxford Shirt", color_name: "White", color_hex: "#FFFFFF" },
    { title: "Navy Chinos", category: "Bottoms", subcategory: "Chinos", color_name: "Navy", color_hex: "#1F2A44" },
    { title: "Brown Loafers", category: "Footwear", subcategory: "Loafers", color_name: "Brown", color_hex: "#5B3A1E" },
  ];
  for (const it of items) {
    const r = await api("/wardrobe/items", { method: "POST", headers: h, body: JSON.stringify({ ...it, pattern: "Solid", image_url: `https://cdn.example.com/${Math.random().toString(16).slice(2)}.jpg`, occasions: ["Smart Casual"], seasonality: "All-Season" }) });
    if (r.status !== 201) throw new Error("item failed " + r.status + " " + JSON.stringify(r.body));
  }
  return { email, token };
}

async function axeRun(page, label) {
  await page.evaluate(AXE);
  const res = await page.evaluate(async () => await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
  return { label, violations: res.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, targets: v.nodes.slice(0, 3).map(n => n.target.join(" ")) })), passes: res.passes.length, incomplete: res.incomplete.length };
}

async function liveRegions(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll('[role="status"],[role="alert"],[aria-live]')).map(el => ({ role: el.getAttribute("role"), live: el.getAttribute("aria-live"), text: (el.textContent || "").trim().slice(0, 200) })).filter(x => x.text));
}

async function focused(page) {
  return page.evaluate(() => { const a = document.activeElement; if (!a) return null; return { tag: a.tagName, role: a.getAttribute("role"), name: (a.getAttribute("aria-label") || a.textContent || "").trim().slice(0, 120), testid: a.getAttribute("data-testid"), tabindex: a.getAttribute("tabindex") }; });
}

async function tabOrder(page, scopeSelector, max = 60) {
  const seq = [];
  await page.evaluate((sel) => { const s = document.querySelector(sel); if (s) { const f = s.querySelector('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'); f && f.focus(); } }, scopeSelector);
  for (let i = 0; i < max; i++) {
    const f = await focused(page);
    const inside = await page.evaluate((sel) => { const s = document.querySelector(sel); return !!(s && document.activeElement && s.contains(document.activeElement)); }, scopeSelector);
    if (!inside) break;
    seq.push(f);
    await page.keyboard.press("Tab");
  }
  return seq;
}

async function runLocale(browser, lang, report) {
  const user = await seedUser(lang);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: lang === "ar" ? "ar-EG" : "en-GB" });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("pageerror", e => consoleErrors.push(String(e).slice(0, 200)));
  await page.goto(APP + "/", { waitUntil: "domcontentloaded" });
  await page.evaluate(([t, l]) => {
    localStorage.setItem("i18nextLng", l);
    localStorage.setItem("confit_lang", l);
  }, [user.token, lang]);
  // Sign in through the real auth flow (token injection into the store is not stable across builds).
  await page.goto(APP + "/wardrobe", { waitUntil: "networkidle" });
  const loc = { ar: { signIn: /تسجيل الدخول|دخول/, stylistTab: "المصمّم الذكي", generate: "ابنِ إطلالتي", looksTab: /إطلالات/ }, en: { signIn: /^Sign in$/i, stylistTab: "AI Stylist", generate: "Build my outfit", looksTab: /My Looks/ } }[lang];
  const section = { lang, user: user.email, states: {} };
  // login through the real modal
  const signIn = page.getByRole("button", { name: loc.signIn }).first();
  if (await signIn.count()) {
    await signIn.click();
    await page.getByLabel(/email|البريد/i).first().fill(user.email);
    await page.getByLabel(/password|كلمة المرور/i).first().fill("Password123!");
    await page.locator("form").getByRole("button", { name: loc.signIn }).first().click();
    await page.waitForTimeout(2500);
  }
  // Style Profile Wizard appears after first login — close it (✕) so it does not trap focus
  const wizardClose = page.getByRole("button", { name: /^✕$|close|إغلاق/i }).first();
  if (await wizardClose.count()) { try { await wizardClose.click({ timeout: 2000 }); } catch {} }
  await page.goto(APP + "/wardrobe", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: loc.stylistTab, exact: true }).first().click();
  await page.waitForTimeout(500);
  section.states.form = { axe: await axeRun(page, `${lang}-form`), tabOrder: await tabOrder(page, "section,main"), ariaSnapshot: await page.locator("main").ariaSnapshot().catch(() => null) };
  // keyboard-only generate: focus the generate button via Tab until found, then Enter
  const gen = page.getByRole("button", { name: loc.generate, exact: true }).first();
  await gen.focus();
  await page.keyboard.press("Enter");
  const result = page.getByTestId("stylist-result");
  await result.waitFor({ timeout: 60000 });
  await page.waitForTimeout(300);
  section.states.result = {
    axe: await axeRun(page, `${lang}-result`),
    focusedAfterResult: await focused(page),
    liveRegions: await liveRegions(page),
    source: await result.getAttribute("data-source"),
    badge: (await page.getByTestId("stylist-source-badge").textContent().catch(() => "")).trim(),
    ariaSnapshot: await result.ariaSnapshot().catch(() => null),
    tabOrder: await tabOrder(page, '[data-testid="stylist-result"]'),
  };
  // save with keyboard
  const save = page.getByTestId("stylist-save-look");
  await save.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector('[data-testid="stylist-save-look"]')?.getAttribute("data-save-state") !== "saving", null, { timeout: 15000 });
  section.states.saved = { saveState: await save.getAttribute("data-save-state"), liveRegions: await liveRegions(page), axe: await axeRun(page, `${lang}-saved`) };
  // Looks tab → saved section
  await page.getByRole("button", { name: loc.looksTab }).first().click();
  const savedSection = page.getByTestId("saved-wardrobe-looks");
  await savedSection.waitFor({ timeout: 15000 });
  await page.getByTestId("saved-wardrobe-look").first().waitFor({ timeout: 15000 });
  section.states.looks = { axe: await axeRun(page, `${lang}-looks`), ariaSnapshot: await savedSection.ariaSnapshot().catch(() => null), cards: await page.getByTestId("saved-wardrobe-look").count(), provenance: await page.getByTestId("saved-look-provenance").first().textContent(), dir: await page.evaluate(() => document.documentElement.getAttribute("dir")) };
  await page.screenshot({ path: `../docs/qa/stylist_a11y_${lang}_looks.png`, fullPage: false });
  section.pageErrors = consoleErrors;
  report.locales.push(section);
  await ctx.close();
}

(async () => {
  const report = { generated_at: new Date().toISOString(), browser: BROWSER, app: APP, locales: [], method: "playwright-core + axe-core; real SPA + real API; keyboard-driven; ARIA snapshots = what AT receives. NOT a screen-reader session unless 'orca' section is present." };
  const launcher = BROWSER === "firefox" ? firefox : chromium;
  const browser = await launcher.launch({ headless: !args.headed, executablePath: args.exe || undefined, args: BROWSER === "firefox" ? [] : ["--no-sandbox"] });
  try {
    for (const lang of ["en", "ar"]) {
      try { await runLocale(browser, lang, report); } catch (e) { report.locales.push({ lang, error: String(e).slice(0, 400) }); }
    }
  } finally { await browser.close(); }
  const totalViolations = report.locales.flatMap(l => Object.values(l.states || {}).flatMap(s => s.axe?.violations || [])).length;
  report.summary = { axe_violations_total: totalViolations, locales_completed: report.locales.filter(l => !l.error).length };
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report.summary), "→", OUT);
  process.exit(totalViolations === 0 && report.summary.locales_completed === 2 ? 0 : 1);
})();
