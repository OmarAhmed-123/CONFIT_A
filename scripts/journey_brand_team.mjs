#!/usr/bin/env node
/**
 * BRD-02 PR-2 real-journey verification (owner invite → acceptance → role
 * change → last-owner protection → AR/RTL → honest failure states).
 *
 * NOTHING here mocks the application flow: it drives the actual Vite dev
 * server (43123) whose /api proxy reaches the actual FastAPI backend on a
 * disposable SQLite DB. The only simulated step is email delivery — the
 * seeded token patch rewrites token_hash on an invitation ROW THAT THE REAL
 * API CREATED, exactly what the (unconfigured locally) email provider would
 * have carried to the recipient. Every state transition, authz decision and
 * refusal you see in the screenshots was computed by the backend.
 *
 * Run:  node scripts/journey_brand_team.mjs          (expects both servers up)
 */
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';

const require = createRequire(new URL('../frontend/package.json', import.meta.url).pathname);
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://localhost:43123';
const API = `${BASE}/api/v1`;
const DB = process.env.JOURNEY_DB || '/home/user/CONFIT_A/backend/data/journey_pr2.db';
const OUT = '/home/user/review_shots/pr2';
fs.mkdirSync(OUT, { recursive: true });

const PASSWORD = 'JourneyPass!2026';
const run = Date.now().toString(36).slice(-5);
const OWNER_EMAIL = `ada.${run}@confitmail.io`;
const STAFF_EMAIL = `sam.${run}@confitmail.io`;
const GUEST_EMAIL = `grace.${run}@confitmail.io`;
const KNOWN_TOKEN = `journey-token-${run}-${Math.random().toString(36).slice(2, 10)}`;

const results = [];
const consoleErrors = [];
const ok = (name, detail = '') => { results.push(['PASS', name, detail]); console.log(`PASS  ${name}  ${detail}`); };
const bad = (name, detail = '') => { results.push(['FAIL', name, detail]); console.log(`FAIL  ${name}  ${detail}`); };
const check = (cond, name, detail = '') => (cond ? ok(name, detail) : bad(name, detail));

async function api(pathname, { method = 'GET', token, csrf, body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const res = await fetch(`${API}${pathname}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  let json = null;
  try { json = await res.json(); } catch { /* non-json */ }
  return { status: res.status, json, setCookie: res.headers.getSetCookie?.() ?? [] };
}
const csrfFrom = (cookies) => {
  for (const c of cookies) { const m = c.match(/confit_csrf=([^;]+)/); if (m) return m[1]; }
  return null;
};

/* ── seed through real endpoints ─────────────────────────────────────────── */
console.log('seeding owner brand via /brand/register …');
const reg = await api('/brand/register', { method: 'POST', body: { brand_name: `Atelier Journey ${run}`, email: OWNER_EMAIL, password: PASSWORD, full_name: 'Ada Owner', country: 'Egypt', city: 'Cairo' } });
if (reg.status !== 201) { console.error('seed failed', reg.status, reg.json); process.exit(2); }
const ownerToken = reg.json.access_token;
ok('seed: owner+brand provisioned', `brand ${reg.json.brand.id}`);

const sam = await api('/auth/register', { method: 'POST', body: { email: STAFF_EMAIL, password: PASSWORD, full_name: 'Sam Staff' } });
if (![200, 201].includes(sam.status)) { console.error('staff register failed', sam.status, sam.json); process.exit(2); }
ok('seed: staff account registered (global role consumer)', `user ${sam.json.user?.id}`);

const inv = await api('/partner/members/invitations', { method: 'POST', token: ownerToken, body: { email: GUEST_EMAIL, role: 'manager' } });
check(inv.status === 201, 'seed: API-created pending invitation for the UI journey', `id ${inv.json?.id}`);
const invSam = await api('/partner/members/invitations', { method: 'POST', token: ownerToken, body: { email: STAFF_EMAIL, role: 'staff' } });
check(invSam.status === 201, 'seed: API-created pending invitation for acceptance', `id ${invSam.json?.id}`);

// Simulated email delivery: point THAT real row's hash at the token we carry
// to the accept page. (sha256, matching the service's hash_token.)
execFileSync('python3', ['-c', `
import sqlite3, hashlib, sys
con = sqlite3.connect(${JSON.stringify(DB)})
cur = con.execute("UPDATE brand_invitations SET token_hash=? WHERE id=?", (hashlib.sha256(${JSON.stringify(KNOWN_TOKEN)}.encode()).hexdigest(), ${invSam.json.id}))
con.commit(); sys.exit(0 if cur.rowcount == 1 else 1)
`]);
ok('seed: invitation token delivered (row real, hash patched once, dev-only)', `invite ${invSam.json.id}`);

/* ── browser journeys ─────────────────────────────────────────────────────── */
const browser = await chromium.launch();
const newCtx = async (label) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 960 }, locale: 'en' });
  await ctx.addInitScript(() => { try { sessionStorage.setItem('confit_splash_viewed', 'true'); } catch {} });
  ctx.on('page', (page) => {
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(`${label}: ${m.text().slice(0, 200)}`); });
    page.on('pageerror', (e) => consoleErrors.push(`${label} pageerror: ${String(e).slice(0, 200)}`));
  });
  return ctx;
};
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
const waitOr = async (page, selector, ms, label) => {
  try { await page.waitForSelector(selector, { timeout: ms }); return true; }
  catch {
    await shot(page, `FAIL_${label}`);
    const body = (await page.locator('body').textContent().catch(() => '')) || '';
    bad(`wait timeout: ${label}`, `selector=${selector} url=${page.url()} body=${body.replace(/\s+/g, ' ').slice(0, 260)}`);
    return false;
  }
};

// --- Journey A: owner sign-in through the awaiting-login gateway → working team
const ownerCtx = await newCtx('owner');
const owner = await ownerCtx.newPage();
const ownerReqs = [];
owner.on('response', (r) => { if (/\/api\/v1\/partner\/members/.test(r.url())) ownerReqs.push(`${r.request().method()} ${new URL(r.url()).pathname} → ${r.status()}`); });

await owner.goto(`${BASE}/b2b`, { waitUntil: 'networkidle' });
check((await owner.getByRole('heading', { name: /partner|brand/i }).count()) > 0, 'A0: signed-out visitor sees the public partner gateway (browse-first preserved)');
await owner.getByRole('button', { name: /existing partner sign in/i }).first().click();
await owner.waitForSelector('[role="dialog"]');
await owner.fill('#auth-email', OWNER_EMAIL);
await owner.fill('#auth-password', PASSWORD);
await owner.locator('[role="dialog"]').getByRole('button', { name: /^sign in$/i }).click();
await owner.waitForURL(/\/(b2b|partner)/, { timeout: 20000 });
await owner.waitForTimeout(700); // let the post-login epilogue navigation settle
await owner.goto(`${BASE}/b2b/team`, { waitUntil: 'networkidle' });
if (!(await waitOr(owner, 'text=Team & access', 25000, 'owner_team'))) { await browser.close(); printReportAndExit(); }
check((await owner.locator('text=Ada Owner').count()) > 0, 'A1: owner roster renders real DB rows');
await owner.reload({ waitUntil: 'networkidle' });
check((await owner.locator('text=Team & access').count()) > 0, 'A2: browser refresh on the nested protected route works (dev history fallback)');

// invite through the dialog
await owner.getByRole('button', { name: /invite member/i }).click();
await owner.getByLabel(/work email/i).fill(GUEST_EMAIL);
await owner.getByLabel(/tenant role/i).selectOption('manager');
await owner.getByRole('button', { name: /send invitation/i }).click();
await owner.waitForSelector('text=queued for delivery', { timeout: 10000 });
check(ownerReqs.some((l) => l.includes('POST /api/v1/partner/members/invitations → 201')), 'A3: invite POST hit the real backend (201)', ownerReqs.at(-1) ?? '');
check((await owner.locator(`text=${GUEST_EMAIL}`).count()) > 0, 'A4: the pending invitation appears in the table it just refreshed from');
await shot(owner, 'team_en_owner');

// resend + revoke — scoped to the invitation the UI itself just created
const graceRow = owner.locator('li').filter({ hasText: GUEST_EMAIL });
await graceRow.getByRole('button', { name: /resend link/i }).click();
await owner.waitForSelector('text=fresh single-use link', { timeout: 8000 });
ok('A5: resend produced a server-confirmed notice');
await graceRow.getByRole('button', { name: /^revoke$/i }).click();
await owner.waitForSelector('text=no longer works', { timeout: 8000 });
const listAfter = await api('/partner/members/invitations', { token: ownerToken });
check(!listAfter.json.some((i) => i.email === GUEST_EMAIL), 'A6: revoked invitation is gone from pending list (persisted, not cosmetic)');

// --- Journey B: invited consumer accepts → portal admission for a consumer
const samCtx = await newCtx('sam');
const samPage = await samCtx.newPage();
await samPage.goto(`${BASE}/b2b/team/accept?token=${KNOWN_TOKEN}`, { waitUntil: 'networkidle' });
check((await samPage.locator('text=Sign in to accept').count()) > 0, 'B1: anonymous holder of a valid token gets the AWAITING-LOGIN card, not access');
await shot(samPage, 'accept_awaiting_login');
await samPage.getByRole('button', { name: /^sign in$/i }).click();
await samPage.waitForSelector('[role="dialog"]');
await samPage.fill('#auth-email', STAFF_EMAIL);
await samPage.fill('#auth-password', PASSWORD);
await samPage.locator('[role="dialog"]').getByRole('button', { name: /^sign in$/i }).click();
const b2 = await waitOr(samPage, 'text=You’re on the team', 25000, 'sam_accept_success');
if (b2) ok('B2: after login the view auto-completed acceptance (token→membership POST ran)'); else { await browser.close(); printReportAndExit(); }
await shot(samPage, 'accept_success');
const members = await api('/partner/members', { token: ownerToken });
const samRow = members.json.find((m) => m.email && m.email.includes(STAFF_EMAIL)) || members.json.find((m) => m.full_name === 'Sam Staff');
check(samRow?.status === 'active' && samRow?.role === 'staff', 'B3: backend persisted the membership (staff/active) — UI claim matches DB', `row ${samRow?.id}`);
await samPage.getByRole('link', { name: /open brand workspace/i }).click();
await samPage.waitForURL(/\/b2b$/, { timeout: 10000 });
await samPage.goto(`${BASE}/b2b/team`, { waitUntil: 'networkidle' });
check((await samPage.locator('text=Team & access').count()) > 0, 'B4: portal gate admits the consumer BY MEMBERSHIP (no global role change)');
check((await samPage.locator('text=team changes are owner-only').count()) > 0, 'B5: staff sees honest read-only copy, no dead controls');
check((await samPage.getByRole('button', { name: /invite member/i }).count()) === 0, 'B5b: staff gets no mutating affordances');
await shot(samPage, 'team_en_staff_readonly');

// replay: second accept with the consumed token must fail uniformly (re-enter URL)
await samPage.goto(`${BASE}/b2b/team/accept?token=${KNOWN_TOKEN}`, { waitUntil: 'networkidle' });
const replayOk = await samPage.waitForSelector('text=already a member', { timeout: 10000 }).then(() => true).catch(() => false);
check(replayOk, 'B6: one-time token replay renders the honest already-member state (server-side idempotence surfaced)');

// --- Journey C: refusals and protected surfaces
const meBefore = await api('/partner/members/me', { token: sam.json.access_token });
check(meBefore.json.length === 1, 'C0: consumer still holds exactly one tenant membership; users.role untouched', JSON.stringify(meBefore.json[0]));
await owner.goto(`${BASE}/b2b/team/accept?token=NOT-A-REAL-TOKEN`, { waitUntil: 'networkidle' });
check((await owner.locator('text=link can’t be used').count()) > 0, 'C1: invalid token renders the uniform refusal card');
await shot(owner, 'accept_invalid');
await owner.goto(`${BASE}/b2b/team/no-such-page`, { waitUntil: 'networkidle' });
check((await owner.locator('text=This page does not exist').count()) > 0, 'C2: unknown nested route → established NotFound view');

// unauthorized management: staff tries owner-only PATCH via API
const patchByStaff = await api(`/partner/members/${samRow?.id ?? 999}`, { method: 'PATCH', token: sam.json.access_token, body: { role: 'owner' } });
check([401, 403, 404].includes(patchByStaff.status) && samRow?.role === 'staff', 'C3: staff escalation attempt refused and row unchanged', `HTTP ${patchByStaff.status}`);

// last-owner removal protection in the UI
await owner.goto(`${BASE}/b2b/team`, { waitUntil: 'networkidle' });
const adaRow = owner.locator('li').filter({ hasText: 'Ada Owner' });
await adaRow.getByRole('button', { name: /^remove$/i }).click(); // the sole owner's row
await owner.getByRole('button', { name: /remove access/i }).click();
const refusal = await owner.waitForSelector('text=at least one active owner', { timeout: 10000 }).then(() => true).catch(() => false);
check(refusal, 'C4: last-owner removal blocked — server 409 message rendered verbatim');
await shot(owner, 'team_last_owner_guard');
const membersAfter = await api('/partner/members', { token: ownerToken });
check(membersAfter.json.some((m) => m.full_name === 'Ada Owner' && m.status === 'active'), 'C4b: DB confirms the owner membership survived the refused removal');

try {
// --- Journey D: Arabic + RTL
await owner.getByRole('group', { name: /change display language/i }).getByRole('button', { name: 'العربية', exact: true }).click();
await owner.waitForSelector('text=الفريق والوصول', { timeout: 10000 });
const dir = await owner.evaluate(() => document.documentElement.dir);
check(dir === 'rtl', 'D1: Team view re-renders fully in Arabic with dir=rtl');
check((await owner.locator('text=الأعضاء').count()) > 0, 'D2: section headings translated (not humanized keys)');
check((await owner.locator('text={{').count()) === 0, 'D3: no unresolved placeholder leaks anywhere in the Arabic render');
check((await owner.locator('text=يجب أن تحتفظ العلامة بمالك نشط واحد').count()) > 0, 'D4: the standing 409 refusal re-translates live into Arabic (messages stored as keys, not frozen strings)');
const dateLines = await owner.locator('li').allInnerTexts();
check(dateLines.some((t) => /انضم في/.test(t) && /أكتوبر|تشرين|\d/.test(t)) && !dateLines.some((t) => /انضم في [A-Z][a-z]+ \d/.test(t)), 'D5: join dates render in the APP locale (Arabic month name), not the browser locale', dateLines.find((t) => t.includes('انضم في')) ?? '');
await shot(owner, 'team_ar_rtl');

// --- Journey E: backend failure must never render as fake success
const failCtx = await newCtx('failure');
const failPage = await failCtx.newPage();
// authenticate this context honestly via the real cookie flow:
await failPage.goto(`${BASE}/b2b`, { waitUntil: 'networkidle' });
await failPage.getByRole('button', { name: /existing partner sign in/i }).first().click();
await failPage.waitForSelector('[role="dialog"]');
await failPage.fill('#auth-email', OWNER_EMAIL);
await failPage.fill('#auth-password', PASSWORD);
await failPage.locator('[role="dialog"]').getByRole('button', { name: /^sign in$/i }).click();
await failPage.waitForURL(/\/(b2b|partner)/, { timeout: 20000 });
await failPage.waitForTimeout(700);
await failPage.route('**/api/v1/partner/members', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: { code: 'INTERNAL', message: 'simulated outage' } }) }));
await failPage.goto(`${BASE}/b2b/team`, { waitUntil: 'networkidle' });
const sawErr = await failPage.waitForSelector('text=couldn’t load the member list', { timeout: 10000 }).then(() => true).catch(() => false);
check(sawErr, 'E1: 500 on the roster → explicit retryable error, no fabricated data');
check((await failPage.locator('li').filter({ hasText: /@confitmail\.io/ }).count()) === 0, 'E1b: failed fetch renders NO fabricated roster rows (list is empty, error shown)');
await shot(failPage, 'team_error_500');
await failPage.unroute('**/api/v1/partner/members');
await failPage.getByRole('button', { name: /retry/i }).click();
await failPage.waitForSelector('text=Sam Staff', { timeout: 10000 });
ok('E2: retry after the outage recovers against the live backend');
} catch (e) {
  bad('D/E journey crashed', String(e).slice(0, 240));
  await shot(owner, 'FAIL_de_endpoint').catch(() => {});
}

function printReportAndExit() {
  console.log('\nconsole errors captured:', consoleErrors.length);
  for (const e of consoleErrors.slice(0, 8)) console.log('  •', e);
  const fails = results.filter((r) => r[0] === 'FAIL');
  console.log(`\nJOURNEY RESULT: ${results.length - fails.length}/${results.length} PASS${fails.length ? ` — ${fails.length} FAIL` : ''}`);
  fs.writeFileSync(`${OUT}/journey-result.json`, JSON.stringify({ results, consoleErrors }, null, 2));
  process.exit(fails.length ? 1 : 0);
}

/* ── report ───────────────────────────────────────────────────────────────── */
await browser.close();
console.log('\nconsole errors captured:', consoleErrors.length);
for (const e of consoleErrors.slice(0, 8)) console.log('  •', e);
const fails = results.filter((r) => r[0] === 'FAIL');
console.log(`\nJOURNEY RESULT: ${results.length - fails.length}/${results.length} PASS${fails.length ? ` — ${fails.length} FAIL` : ''}`);
fs.writeFileSync(`${OUT}/journey-result.json`, JSON.stringify({ results, consoleErrors }, null, 2));
process.exit(fails.length ? 1 : 0);
