#!/usr/bin/env node
/**
 * Authenticated browser E2E for Save look (spec 009 / STY-10 scope amendment, Mode A).
 *
 * Real: the Chromium session, the httpOnly cookie login (POST /api/v1/auth/login), the CSRF
 * double-submit, the backend save (POST /api/v1/outfits), the list read (GET /api/v1/outfits),
 * and the SQLite test database.
 *
 * Stubbed, and only this: the stylist chat response is taken from the REAL grounded Mode B
 * engine (no provider call), and then its `mode` / `image_analysis` fields are set to Mode A so
 * the Mode A Save look control renders. Mode A itself needs a vision provider (paid), which
 * AGENTS.md forbids in testing. The save path is not stubbed.
 *
 * Requires: backend on BASE_API (local test DB, not production), frontend dev server on BASE_URL.
 * Credentials: the seeded LOCAL demo accounts only (shopper@confit.io, admin@confit.io). They are
 * read from the environment and never printed:  E2E_PASSWORD (defaults to the seed password).
 *
 * Exits 1 on any failed check. Writes a JSON report to PROBE_JSON.
 */
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const BASE_URL = process.env.BASE_URL || "http://localhost:43123";
const BASE_API = process.env.BASE_API || "http://localhost:8000";
const DB_PATH = process.env.E2E_DB || "/home/user/.cache/confit-e2e/e2e.db";
const OUT = process.env.PROBE_JSON || "/tmp/stylist-save-look-e2e.json";
const PASSWORD = process.env.E2E_PASSWORD || "Password123!";
const SHOPPER = "shopper@confit.io";
const OTHER = "admin@confit.io";

const en = JSON.parse(fs.readFileSync(path.join(root, "src/i18n/en.json"), "utf8"));
const S = en.stylist;
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

const checks = [];
const check = (id, ok, detail) => {
  checks.push({ id, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${id}${detail !== undefined && !ok ? "  " + JSON.stringify(detail).slice(0, 300) : ""}`);
};

// Read-only SQL against the LOCAL test DB via the sqlite3 CLI (python stdlib).
const sqlite = (sql) =>
  execFileSync("python3", ["-c",
    `import sqlite3,sys,json;c=sqlite3.connect(${JSON.stringify(DB_PATH)});print(json.dumps(c.execute(sys.argv[1]).fetchall()))`,
    sql], { encoding: "utf8" });

async function apiLogin(request, email) {
  const r = await request.post(`${BASE_URL}/api/v1/auth/login`, { data: { email, password: PASSWORD } });
  return r.status();
}
async function listOutfits(request) {
  const r = await request.get(`${BASE_URL}/api/v1/outfits`);
  return { status: r.status(), body: r.status() === 200 ? await r.json() : null };
}

// Real grounded Mode B reply, relabelled as Mode A so the Mode A save control renders.
async function stubModeA(page) {
  await page.route("**/api/v1/stylist/chat", async (route) => {
    const real = await route.fetch();
    const body = await real.json();
    body.mode = "A";
    body.image_analysis = { available: true, engine: "e2e-stub", reason: null, images: 1 };
    await route.fulfill({ response: real, json: body });
  });
}

async function openDrawerAndAsk(page, withPhoto) {
  await page.goto(BASE_URL, { waitUntil: "load", timeout: 90000 });
  await page.addStyleTag({ content: "*,*::before,*::after{animation-duration:0s!important;transition-duration:0s!important;}" });
  const fab = page.getByRole("button", { name: en.layout.open_ai_stylist });
  await fab.waitFor({ state: "visible", timeout: 90000 });
  await fab.click();
  const dialog = page.getByRole("dialog", { name: S.dialog_label });
  await dialog.waitFor({ state: "visible", timeout: 30000 });
  if (withPhoto) {
    await dialog.locator('input[type="file"]').setInputFiles([{ name: "look.png", mimeType: "image/png", buffer: PNG }]);
  }
  await dialog.getByRole("textbox", { name: S.input_label }).fill("Smart casual dinner outfit within my budget");
  await dialog.getByRole("button", { name: S.submit }).click();
  const save = dialog.getByRole("button", { name: S.save_look }).first();
  await save.waitFor({ state: "visible", timeout: 60000 });
  return { dialog, save };
}

const report = {};
const browser = await chromium.launch({ headless: true });
try {
  // ---------- Signed-in shopper ----------
  const shopperCtx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await shopperCtx.addInitScript(() => { try { localStorage.setItem("confit_lang", "en"); } catch { /* */ } });
  const sPage = await shopperCtx.newPage();
  const sLogin = await apiLogin(shopperCtx.request, SHOPPER);
  check("shopper login via real endpoint returns 200", sLogin === 200, { sLogin });

  const before = await listOutfits(shopperCtx.request);
  const beforeCount = before.body ? before.body.length : -1;
  await stubModeA(sPage);

  // Observe the exact save request the drawer sends.
  const saveRequests = [];
  sPage.on("request", (req) => {
    if (req.method() === "POST" && /\/api\/v1\/outfits(\/save)?$/.test(new URL(req.url()).pathname)) {
      saveRequests.push({ url: req.url(), body: req.postData() || "" });
    }
  });

  const { dialog, save } = await openDrawerAndAsk(sPage, true);
  check("Mode A answer shows the Save look control", await save.isVisible());

  // The drawer can show several looks, each with its own Save control.
  const saveButtonsBefore = await dialog.getByRole("button", { name: S.save_look }).count();

  // Duplicate-click guard: two rapid clicks must create exactly one look.
  await save.dblclick();
  const savedStatus = dialog.getByRole("status", { name: S.look_saved });
  await savedStatus.waitFor({ state: "visible", timeout: 30000 }).catch(() => {});
  check("saved state announced with role=status", (await savedStatus.count()) === 1);
  // Only the saved look's control is removed; the other looks keep theirs.
  check("the saved look's Save control is removed (count drops by exactly one)", (await dialog.getByRole("button", { name: S.save_look }).count()) === saveButtonsBefore - 1, { saveButtonsBefore });

  const sentPosts = saveRequests.length;
  check("exactly one save request sent for a double click", sentPosts === 1, { sentPosts });
  const reqBody = sentPosts ? JSON.parse(saveRequests[0].body) : {};
  check("save request carries product ids (numbers) and a title", Array.isArray(reqBody.product_ids) && reqBody.product_ids.length > 0 && reqBody.product_ids.every((n) => Number.isInteger(n)) && typeof reqBody.title === "string", reqBody);
  check("save request carries no image payload", !/data:image|base64|images/.test(saveRequests[0]?.body || ""), {});

  const after = await listOutfits(shopperCtx.request);
  const afterCount = after.body ? after.body.length : -1;
  check("exactly one look persisted (count +1)", afterCount === beforeCount + 1, { beforeCount, afterCount });
  const saved = after.body ? after.body.find((o) => o.title === reqBody.title) : null;
  check("persisted look is retrievable via GET /api/v1/outfits with the same title", !!saved, { title: reqBody.title });
  report.persisted = saved ? { id: saved.id, title: saved.title, occasion: saved.occasion, items: (saved.items || []).length } : null;

  // Cross-user isolation: the other account must not see the shopper's look.
  const otherCtx = await browser.newContext();
  const oLogin = await apiLogin(otherCtx.request, OTHER);
  const other = await listOutfits(otherCtx.request);
  const leaked = other.body ? other.body.some((o) => saved && o.id === saved.id) : null;
  check("other user's login succeeds (isolation test is meaningful)", oLogin === 200, { oLogin });
  check("other user cannot see the shopper's look", leaked === false, { leaked });
  await otherCtx.close();

  // No image bytes stored: scan every text column of the test DB for data-URI image payloads.
  const dataUriRows = JSON.parse(sqlite(`
    SELECT name FROM sqlite_master WHERE type='table'`)).flat();
  let hits = 0;
  for (const t of dataUriRows) {
    const cols = JSON.parse(sqlite(`SELECT name, type FROM pragma_table_info('${t}')`)).filter(([, ty]) => /CHAR|TEXT|CLOB|JSON/i.test(ty || "")).map(([n]) => n);
    for (const c of cols) {
      const n = JSON.parse(sqlite(`SELECT count(*) FROM "${t}" WHERE "${c}" LIKE '%data:image/%;base64%'`))[0][0];
      hits += n;
    }
  }
  check("no data:image base64 stored in any text column of the test DB", hits === 0, { hits });
  await sPage.close();

  // Save-look error handling: the endpoint fails -> an honest, localized message, nothing raw.
  const errPage = await shopperCtx.newPage();
  await stubModeA(errPage);
  await errPage.route("**/api/v1/outfits", async (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "INTERNAL_BOOM_TRACE" }) });
    }
    return route.continue();
  });
  const { dialog: d2, save: s2 } = await openDrawerAndAsk(errPage, false);
  await s2.click();
  const failAlert = d2.getByRole("alert").filter({ hasText: S.save_look_failed });
  await failAlert.waitFor({ state: "visible", timeout: 20000 }).catch(() => {});
  check("server failure shows the generic localized error", (await failAlert.count()) === 1);
  check("server failure does not leak the raw server detail", (await d2.getByText("INTERNAL_BOOM_TRACE").count()) === 0);
  check("save button stays available to retry after a failure", (await d2.getByRole("button", { name: S.save_look }).count()) >= 1);
  await errPage.close();

  // ---------- Signed-out guest ----------
  const guestCtx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await guestCtx.addInitScript(() => { try { localStorage.setItem("confit_lang", "en"); } catch { /* */ } });
  const gPage = await guestCtx.newPage();
  await stubModeA(gPage);
  const beforeGuest = await listOutfits(shopperCtx.request);
  const { dialog: gd, save: gs } = await openDrawerAndAsk(gPage, false);
  await gs.click();
  const signinAlert = gd.getByRole("alert").filter({ hasText: S.save_look_signin });
  await signinAlert.waitFor({ state: "visible", timeout: 20000 }).catch(() => {});
  check("guest sees the sign-in message (401), not a silent failure", (await signinAlert.count()) === 1);
  check("guest save does not show success", (await gd.getByRole("status", { name: S.look_saved }).count()) === 0);
  const afterGuest = await listOutfits(shopperCtx.request);
  check("guest save persists nothing", afterGuest.body && beforeGuest.body && afterGuest.body.length === beforeGuest.body.length, {});
  await guestCtx.close();

  await shopperCtx.close();
} finally {
  await browser.close();
}

report.checks = checks;
fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
const failed = checks.filter((c) => !c.ok);
console.log(`${checks.length - failed.length}/${checks.length} checks passed`);
if (failed.length) {
  console.error(`SAVE-LOOK E2E: ${failed.length} failing check(s)`);
  process.exit(1);
}
console.log("SAVE-LOOK E2E PASSED");
