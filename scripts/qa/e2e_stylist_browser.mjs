// Browser end-to-end journey for the wardrobe stylist — permanent CI gate.
//
// Journey (per language, en then ar):
//   1. sign in through the real AuthModal (httpOnly cookie session)
//   2. add one garment through the manual "add piece" form (UI, not API)
//   3. request an outfit for an occasion, assert a labelled result
//   4. save the look, assert the save status, assert it is listed in "My Looks"
//
// Determinism: the backend runs with WARDROBE_STYLIST_PROVIDER=deterministic
// (no model call, labelled `deterministic` source) and a throwaway PostgreSQL.
// Fixtures: a fresh user per run (API register — the only non-UI step, so the
// journey never depends on the public sign-up rate limit) plus five garments
// seeded over the API so the stylist has a complete closet; the sixth garment
// is added through the UI and must appear in the result-capable closet.
//
// Env: BASE_URL (vite preview), API_URL (backend), OUT_DIR (artifacts),
// PW_EXECUTABLE (optional Chromium path for local runs).
// Exit 0 only when every assertion in both languages passed.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(path.resolve(process.cwd(), "frontend/node_modules/playwright-core"));

const WEB = process.env.BASE_URL || "http://127.0.0.1:43123";
const API = process.env.API_URL || "http://127.0.0.1:8000";
const OUT = process.env.OUT_DIR || path.resolve(process.cwd(), "e2e-artifacts");
fs.mkdirSync(OUT, { recursive: true });

const T = {
  en: { signIn: /^(Sign In)$/, stylistTab: /AI Stylist/, looksTab: /My Looks/, upload: /Upload Wardrobe Piece|Upload piece|Upload garment/i,
        saveManual: /Save Piece Manually/, occasion: "Business", uiItem: "E2E Olive Chinos" },
  ar: { signIn: /^(تسجيل الدخول)$/, stylistTab: /المصمم/, looksTab: /إطلالاتي|إطلالات/, upload: /رفع قطعة/,
        saveManual: /احفظ القطعة يدويًا/, occasion: "عمل", uiItem: "بنطال زيتوني" },
};

const failures = [];
const check = (lang, name, ok, detail) => {
  const rec = { lang, name, ok: !!ok, detail };
  if (!ok) failures.push(rec);
  return rec;
};

async function fixtureUser() {
  const email = `e2e_${Date.now()}_${Math.random().toString(16).slice(2, 6)}@example.com`;
  const password = "Password123!";
  const r = await fetch(`${API}/api/v1/auth/register`, { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password, full_name: "E2E Browser" }) });
  if (!r.ok) throw new Error(`register failed: ${r.status} ${await r.text()}`);
  const { access_token } = await r.json();
  const H = { "content-type": "application/json", authorization: `Bearer ${access_token}` };
  const closet = [
    ["Navy wool blazer", "Outerwear", "Navy", "#1F2A44", ["business", "smart_casual"]],
    ["White Oxford shirt", "Tops", "White", "#FFFFFF", ["business", "smart_casual"]],
    ["Charcoal wool trousers", "Bottoms", "Charcoal", "#36454F", ["business"]],
    ["Grey crew-neck tee", "Tops", "Grey", "#9E9E9E", ["casual"]],
    ["Black leather derbies", "Footwear", "Black", "#111111", ["business", "smart_casual"]],
  ];
  for (const [title, category, color_name, color_hex, occasions] of closet) {
    const ir = await fetch(`${API}/api/v1/wardrobe/items`, { method: "POST", headers: H,
      body: JSON.stringify({ title, category, color_name, color_hex, pattern: "Solid", occasions, seasonality: "All-Season",
        image_url: `https://cdn.example.com/e2e/${encodeURIComponent(title)}.jpg` }) });
    if (!ir.ok) throw new Error(`seed item failed: ${ir.status} ${await ir.text()}`);
  }
  return { email, password };
}

async function run(lang, creds, browser) {
  const t = T[lang];
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.addInitScript(([l]) => {
    localStorage.setItem("confit_lang", l);
    sessionStorage.setItem("confit_splash_viewed", "true");
    sessionStorage.setItem("confit_onboarding_dismissed", "1");
  }, [lang]);
  const page = await ctx.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  const steps = [];
  const shot = (n) => page.screenshot({ path: path.join(OUT, `${lang}_${n}.png`), fullPage: false });

  // 1. auth through the UI
  await page.goto(`${WEB}/wardrobe`, { waitUntil: "networkidle", timeout: 90000 });
  await page.getByRole("button", { name: t.signIn }).first().click();
  await page.waitForSelector("#auth-email", { timeout: 20000 });
  await page.fill("#auth-email", creds.email);
  await page.fill("#auth-password", creds.password);
  await page.locator("#auth-password").press("Enter");
  await page.waitForFunction(() => !!localStorage.getItem("confit_user"), null, { timeout: 30000 });
  await page.waitForLoadState("networkidle");
  const cookieNames = (await ctx.cookies()).map((c) => c.name);
  steps.push(check(lang, "auth.session_cookie_set", cookieNames.includes("confit_token"), cookieNames));
  steps.push(check(lang, "page.dir", (await page.evaluate(() => document.documentElement.dir)) === (lang === "ar" ? "rtl" : "ltr")));
  await shot("1_signed_in");

  // 2. add a garment through the manual form
  await page.goto(`${WEB}/wardrobe?tab=closet`, { waitUntil: "networkidle", timeout: 90000 });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: t.upload }).first().click();
  const dialog = page.getByRole("dialog").last();
  await dialog.waitFor({ timeout: 20000 });
  const manualForm = dialog.locator("form").filter({ has: page.getByRole("button", { name: t.saveManual }) });
  await manualForm.locator("input[type=text]").first().fill(t.uiItem);
  await manualForm.locator("select").first().selectOption("Bottoms");
  await manualForm.locator("input[type=text]").nth(1).fill(lang === "ar" ? "زيتوني" : "Olive");
  await shot("2_add_form");
  const [addResp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/v1/wardrobe/items") && r.request().method() === "POST", { timeout: 30000 }),
    manualForm.getByRole("button", { name: t.saveManual }).click(),
  ]);
  const added = addResp.ok() ? await addResp.json() : null;
  steps.push(check(lang, "wardrobe.add_via_ui", addResp.status() === 201 && added && added.title === t.uiItem,
    { status: addResp.status(), color_name: added && added.color_name }));
  steps.push(check(lang, "wardrobe.ui_item_colour_family_is_known", added && added.color_name === "Green", added && added.color_name));
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
  steps.push(check(lang, "wardrobe.ui_item_visible_in_closet", (await page.getByText(t.uiItem).count()) > 0));

  // 3. recommendation
  await page.goto(`${WEB}/wardrobe?tab=stylist`, { waitUntil: "networkidle", timeout: 90000 });
  await page.keyboard.press("Escape");
  if (!(await page.locator("form button[type=submit]").count())) await page.getByRole("button", { name: t.stylistTab }).first().click();
  await page.waitForSelector("form button[type=submit]", { timeout: 30000 });
  const occ = page.locator('[id$="-occasion"]').first();
  if ((await occ.evaluate((e) => e.tagName)) === "SELECT") await occ.selectOption({ index: 1 }); else await occ.fill(t.occasion);
  await page.locator("form button[type=submit]").first().click();
  await page.waitForSelector("[data-testid=stylist-result]", { timeout: 60000 });
  await page.waitForTimeout(400);
  const source = await page.getAttribute("[data-testid=stylist-result]", "data-source");
  const badge = (await page.textContent("[data-testid=stylist-source-badge]"))?.trim();
  const nItems = await page.locator("[data-testid=stylist-result] ul[aria-label] > li").count();
  steps.push(check(lang, "stylist.result_rendered", nItems >= 2, { items: nItems }));
  // WARDROBE_STYLIST_PROVIDER=deterministic surfaces as data-source="deterministic_fallback"
  // with a visible non-AI badge; the gate must never see a model-attributed result.
  steps.push(check(lang, "stylist.source_is_deterministic_and_labelled", /^deterministic/.test(source || "") && !!badge, { source, badge }));
  steps.push(check(lang, "stylist.no_live_ai_claim", !/granite|watsonx|جرانيت/i.test(badge || ""), { badge }));
  await page.locator("[data-testid=stylist-result]").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, `${lang}_3_result.png`), fullPage: true });

  // 4. save the look and find it in My Looks
  const saveBtn = page.locator("[data-testid=stylist-save-look]").first();
  steps.push(check(lang, "stylist.save_button_present", (await saveBtn.count()) > 0));
  const [saveResp] = await Promise.all([
    page.waitForResponse((r) => /\/api\/v1\/wardrobe\/outfits/.test(r.url()) && r.request().method() === "POST", { timeout: 30000 }),
    saveBtn.click(),
  ]);
  await page.waitForTimeout(600);
  const saveStatus = (await page.textContent("[data-testid=stylist-save-status]").catch(() => ""))?.trim();
  steps.push(check(lang, "stylist.save_persisted", saveResp.status() === 201, { status: saveResp.status(), ui: saveStatus }));
  const savedTitle = saveResp.ok() ? (await saveResp.json()).title : null;
  await page.getByRole("button", { name: t.looksTab }).first().click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
  steps.push(check(lang, "looks.saved_outfit_listed", !!savedTitle && (await page.getByText(savedTitle, { exact: false }).count()) > 0, { savedTitle }));
  await shot("4_my_looks");

  steps.push(check(lang, "page.no_uncaught_errors", pageErrors.length === 0, pageErrors.slice(0, 3)));
  await ctx.close();
  return steps;
}

const browser = await chromium.launch(process.env.PW_EXECUTABLE ? { executablePath: process.env.PW_EXECUTABLE } : {});
const report = { started_at: new Date().toISOString(), web: WEB, api: API, languages: {} };
try {
  for (const lang of ["en", "ar"]) {
    const creds = await fixtureUser();
    try {
      report.languages[lang] = await run(lang, creds, browser);
    } catch (err) {
      report.languages[lang] = [check(lang, "journey.completed", false, String(err).slice(0, 500))];
    }
  }
} finally {
  await browser.close();
}
report.failures = failures;
report.pass = failures.length === 0;
fs.writeFileSync(path.join(OUT, "e2e-report.json"), JSON.stringify(report, null, 2));
for (const [lang, steps] of Object.entries(report.languages))
  for (const s of steps) console.log(`${s.ok ? "PASS" : "FAIL"}  ${lang}  ${s.name}${s.ok ? "" : "  " + JSON.stringify(s.detail)}`);
console.log(`e2e: ${report.pass ? "PASS" : "FAIL"} (${failures.length} failing checks) → ${OUT}/e2e-report.json`);
process.exit(report.pass ? 0 : 1);
