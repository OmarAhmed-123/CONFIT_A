# Feature: `fix/auth-session-lifecycle` — BLOCKER J (auth session lifecycle)

**Cycle 3 · 2026-09-07 · branch `fix/auth-session-lifecycle` · one feature = one branch = one PR**

## Problem (root cause, verified on code HEAD `cb9f6ed`)

The backend implements a **correct** token lifecycle: short-lived access token
(15 min in code), 30-day rotating refresh tokens with server-side reuse
detection (family revocation + `REFRESH_REUSE_DETECTED` audit), persisted in a
`refresh_tokens` table. But the browser session could never use it:

1. `/auth/login|register|refresh` returned the refresh token **in the body only** —
   and the SPA deliberately discards body tokens (`setAuthTokens` is an
   intentional stub: no token-shaped value may reach web storage).
2. `apiClient` never called `/auth/refresh` (the `authService.refresh` binding
   existed with zero callers), and did not retry on 401.

Consequence: the only thing keeping browser users signed in was the access
cookie's lifetime. Production env sets `ACCESS_TOKEN_EXPIRE_MINUTES=1440`
(24 h) — 96× the researched default — because lowering it to 15 min would
kick every user out with no recovery path. The operator was trapped between
"insecure 24 h access tokens" and "unusable 15 min sessions".

## Research → design decision (docs/research/CONFIT_A_CYCLE_3_RESEARCH.md)

OWASP Session Management CS + Authentication CS and 2026 token-lifetime
practice converge on: **short access (5–15 min) + long rotating refresh
(30 d) with reuse detection; session evidence in httpOnly cookies; never in
web storage.** The backend already implements the server half verbatim. The
missing half is transport + client renewal:

- **Backend**: issue the refresh token as a dedicated httpOnly cookie
  (`confit_refresh`), separate lifetime/path semantics from the access
  cookie, rotated on every refresh, deleted on logout and on any refresh
  failure. Body-token contract unchanged (API/mobile clients).
- **Frontend**: on 401 from any non-auth endpoint → ONE cookie-based
  `/auth/refresh` (single-flight) → replay the original request once. Failed
  renewal ⇒ honest session-expired: purge `confit_user`, dispatch
  `confit:session-expired`, auth store syncs to signed-out. No loops
  (retry is 401 again ⇒ surface the error), no fake success.

CSRF note: `/auth/refresh` is NOT added to `CSRF_EXEMPT_PATH_PREFIXES`. The
guard only enforces `X-CSRF-Token` on POSTs carrying a live `confit_token`
cookie; when the access cookie has expired the request is exempt by
construction, and after renewal subsequent POSTs carry the (rotated) CSRF
cookie as before. A stolen-refresh-cookie attacker still cannot mint a
session without a live CSRF cookie; rotation + reuse detection remain
authoritative server-side.

## Acceptance criteria (Given/When/Then)

**AC1 — refresh cookie issued**
Given a successful login, When the response arrives, Then an httpOnly
`confit_refresh` cookie (SameSite=Lax, Secure in prod, 30 d) is set whose
value equals the body's `refresh_token`, alongside the existing
`confit_token`/`confit_csrf` cookies.

**AC2 — cookie-only refresh (the SPA path)**
Given an expired access cookie but a valid `confit_refresh` cookie, When
`POST /api/v1/auth/refresh` is sent with an empty body, Then the endpoint
returns 200 with rotated tokens, rotates both cookies, and the new access
cookie authenticates `GET /auth/me`.

**AC3 — reuse detection still bites**
Given a refreshed session, When the OLD refresh cookie value is replayed,
Then the server answers 401 (family revoked).

**AC4 — backward compatibility**
Given an API/mobile client, When `POST /auth/refresh` is called with
`{"refresh_token": ...}` in the body, Then it works exactly as before.

**AC5 — honest failure**
Given no refresh token anywhere (or an invalid/expired one), When
`POST /auth/refresh` is called, Then 401 with the standard error envelope AND
the stale `confit_refresh` cookie is deleted (no client retry hammering).

**AC6 — transparent renewal in the SPA**
Given the SPA receives 401 on `/wardrobe/items`, When the refresh succeeds,
Then exactly one `/auth/refresh` fires and the original request is replayed
once and succeeds; `confit_user` survives.

**AC7 — honest expiry in the SPA**
Given the refresh itself fails, Then the original 401 surfaces (no retry
loop), `confit_user` is purged, and `confit:session-expired` is dispatched
exactly once; the auth store clears to signed-out.

**AC8 — no recursion / single-flight**
`/auth/refresh` 401s never trigger the renewal path itself; parallel 401s
share ONE refresh call.

**AC9 — logout**
`POST /auth/logout` deletes `confit_refresh` together with the session and
CSRF cookies.

## Tests pinning the contract

- `backend/tests/test_session_refresh_lifecycle.py` — 6 tests (AC1–AC5, AC9).
- `frontend/src/services/__tests__/apiClient.sessionRefresh.test.ts` — 5
  tests (AC6–AC8 + no-loop-after-retry).
- Full suites at PR time: backend **1033 passed / 7 skipped** (was 1028),
  frontend **100 passed / 18 files** (was 95), `tsc --noEmit` clean, prod
  build ✓.

## Operator impact (unblocks the secure env change)

With renewal working end-to-end, `ACCESS_TOKEN_EXPIRE_MINUTES` can now be
lowered in the production env to the code default (15) per the researched
threat model. That env change is an owner action (Vercel dashboard) — this
PR makes it **safe**, it does not perform it.

## Rollback

Single revert of the merge commit. The body-token contract is untouched, so
pre-update clients keep working; the frontend returns to no-auto-refresh
behavior (status quo ante: 24 h access cookie in prod). No DB migration was
added or removed; `refresh_tokens` schema is unchanged. The `confit_refresh`
cookie simply stops being set/expected; any lingering cookie is inert
(30 d max) and cleared on next logout.

---

## Closure (2026-09-07)

- **PR #84** merged as **`44fa877`** (commits `50d6ea9` → `8b60fed` → `f9b162a` → `80f2ed1` → `31b1298`).
- **CI**: backend ✅ frontend ✅ parity ✅ migration gate ✅ gitleaks ✅ (Workers Builds = main-only, non-required).
- **Preview verification** (Playwright, destructive, `confit-a-git-fix-auth-sessi-8501c6-…`): **13/13 PASS** — evidence table on PR #84. Two real defects found live and fixed on-branch: `80f2ed1` (empty-JSON body → 422 on /auth/refresh), `31b1298` (same class on /auth/logout).
- **Production verification** (read-only-class smoke, self-cleaning session, `confit-a.vercel.app`): login sets `confit_refresh` (httpOnly, SameSite=Lax, max-age=2592000) · `/auth/me` 200 · cookie-only refresh 200 with access+refresh+CSRF rotated · logout 200 (revokes, cookies cleared) · 6/6 security headers intact on `/`.
- **Status: FIXED (verified in production).**
- Remaining OWNER ACTION (recommended, now safe): lower production env `ACCESS_TOKEN_EXPIRE_MINUTES` 1440 → 15 (code default, researched). Blocking J's insecure-lifetime half cannot close until this env change lands — tracked in MASTER_REMEDIATION_PLAN §6.

Full suites at merge: backend **1034 passed / 7 skipped** · frontend **100 passed** · tsc clean · build ✓.
