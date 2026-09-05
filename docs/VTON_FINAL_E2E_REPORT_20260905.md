# CONFIT_A — VTON FINAL E2E & SECURITY REPORT (2026-09-05)

Scope: the 23-item closure directive. Every claim below is backed by a
live production request, a committed regression test, code inspection, or
deployment evidence. No secret values appear in this document. Production
alias during this run: `confit-a.vercel.app` → deployment
`dpl_6Kqk24FXqCpHeCMHLrwkofH8ZV1a` (combined pre-merge tree; see §L).

---

## A. Role-escalation fix (CRITICAL #1)

- Fix: `security/fix-registration-role-escalation` @ `17cc74c` —
  server-side service-layer CONSUMER invariant; `UserRegister` no longer
  carries `role`; crafted privilege fields silently ignored (no 422
  oracle); 10 regression tests.
- **Live-verified**: registering with `"role":"admin"` (and crafted
  `user_role`/`is_admin` fields) in production → 201 with `role: consumer`
  (E2E User A, id 21 — created this way, confirmed in DB and via
  `/auth/me`). Consumer bearer → `/api/v1/admin/analytics` → 403.
- PR strategy: dedicated branch, never auto-merged. **Push blocked at the
  environment level** (no GitHub credentials in the execution environment;
  not re-requested in chat per policy). Branch + SHA + exact blocker
  reported.

## B. Bearer-redaction fix (CRITICAL #2)

- Fix: `86b138e` (defensive normalization of the platform-redacted
  `***<jwt>` form) + `f2eafb9` (13-test redaction matrix). The workaround
  never bypasses JWT validation — full JWT is still parsed and verified;
  only the `Bearer ` scheme prefix is recovered when the platform has
  replaced it.
- **Live-verified** in this run: every E2E request (register → me → jobs →
  download) authenticated via `Authorization: Bearer`; `/auth/me` returned
  the correct identity (A=21, B=22) on every call.

## C. Account audit (probe accounts)

- 13 `*@test.dev` probe accounts identified; 6 ADMIN → CONSUMER downgrades
  executed (ids 8, 9, 11, 12, 15, 16); 0 elevated; all 13 now CONSUMER;
  documented per account. 6 legitimate accounts untouched.
- E2E users (A=21, B=22) and the seeded diagnostic admin
  (`admin@confit.io`) remain — flagged in §L for cleanup at closure.

## D. Migration 0016

- **Applied to production** in the mandated order: code deployed first,
  then `alembic upgrade head` (0015 → `0016_vton_temporary_delivery`) via a
  temporary scoped function.
- **Live-verified**: `/api/v1/health` → `expected_head ==
  database_revision == 0016_vton_temporary_delivery`, verdict `ok`,
  `missing_tables: []`. Production is not DB-ahead-of-code.

## E. Live E2E (production frontend contract + production API)

Real users (A/B), real catalog garments (products 1, 2, 5), real GPU
inference, production API, bearer auth, in-request execution:

| run | garment | result | wall time |
|---|---|---|---|
| #4 | product 1 | 202 → `completed`, 640×640 PNG, data-URL 806 KB, metrics PASS (pixel_change 47.95) | 33.8 s |
| #5 | product 2 | 202 → `completed`, data-URL 720 KB | 25.2 s |
| #6 | product 5 | 202 → `completed`, data-URL 908 KB | 30.8 s |

Frontend-origin evidence: the **live production JS bundle** (fetched from
the alias, all 5 asset files, 824 KB) contains the real API client —
`submitTryOnJob → POST /try-on/jobs`, `getTryOnJobStatus →
GET /try-on/jobs/{id}`, `cancelTryOnJob`, garment/animation/multi/fit
endpoints — and **zero** fixture/mock-garment/placeholder-image strings.
The E2E calls used exactly that contract. The only step not executed is a
browser click-through (no browser in the execution environment) — see §L.

Earlier in the day the animated (multi-garment) try-on was also live-
verified: 200, ~27 s, generated image (this was the 502-resolution proof).

## F. Identity / ownership / non-retention

- **Ownership**: all of A's jobs have `user_id = 21` in the DB (verified
  row-by-row). B reading A's job → 404 RESOURCE_NOT_FOUND (no existence
  oracle). Identity is derived server-side from the bearer JWT; the
  response payload carries no client-trusted identity.
- **Frontend identity lifecycle**: session token in an httpOnly cookie
  (JS-unreadable, XSS-resistant); CSRF double-submit cookie; `confit_user`
  in localStorage is a display cache only (cleared on logout) and is never
  used for authorization; `getAuthToken()` is a null no-op in the browser.
- **Repository-wide auth audit** (146 endpoints): every stateful endpoint
  carries a server-side user/role dependency (`get_current_user`,
  `require_role`, `brand_auth = require_role(BRAND_ROLES)`, ownership
  checks in services). Public by design: auth entrypoints, catalog reads,
  `/health`-family, public share links (token-gated), payment webhooks
  (raw-body signature verified in service). No endpoint authorizes from
  body/query `user_id`, client role, or localStorage.
- **New finding (F-14)**: pre-existing measurement-session endpoints
  (`GET/POST /tryon/measurements/sessions/{id}`) have no auth/ownership and
  auto-create sessions with `consent_granted=True` (IDOR + consent
  fabrication, medium-high). Not introduced by this work; recommended fix
  pattern defined; deferred to next security cycle (needs 0017).
- **Non-retention**: completed job rows persist only
  `delivery_token_hash` (SHA-256), `delivery_expires_at`,
  `delivery_content_type`. `has_output_url = false`,
  `looks_like_inline_bytes = false` for all jobs. No R2/S3 was added.
  Generated pixels exist only in the authenticated response (and the
  per-instance staged copy, TTL 900 s).

## G. Temporary delivery (one-shot download)

- Delivery object on completed jobs: one-time token (only its hash in DB),
  `byte_size` 604 789, `content_type image/png`, `ttl_seconds` 900,
  `one_time: true`, `expires_at` set.
- **Isolation (live)**: owner + token = authorized; User B with A's token
  → 404 (no bytes/URL); anonymous with A's token → 404; re-use → 410.
- **Limitation (honest)**: the staged copy lives in the function instance
  that rendered the job; Vercel routed follow-up GETs to other instances,
  so the live download returned 410 GONE (within TTL) — the endpoint's
  200 path is covered by the 24/24 delivery unit tests and the guaranteed
  user-visible carrier is the in-response data URL, which delivered the
  full image to the owner in all 3 runs. This is a documented serverless
  property, not a hidden failure.

## H. Failure paths (all live unless noted)

| path | behavior |
|---|---|
| invalid garment id | 404 RESOURCE_NOT_FOUND (pre-pipeline) |
| empty product list | 422 VALIDATION_ERROR |
| invalid person image (non-image URL) | job → `failed`, `VTON_INPUT_INVALID`; no fake success |
| SSRF attempt (`169.254.169.254`) | blocked by `is_safe_image_url` → job failed cleanly |
| worker unavailable | 502 VTON_WORKER_UNAVAILABLE — this exact path is what the user's reported 502 was (missing `VTON_WORKER_PROCESS_URL` env; resolved; see findings F-10) |
| inference crash mid-job | surfaced as 500 after the pre-fix overflow (F-11); post-fix, 3/3 clean completions. Stuck intermediate state is documented, no auto-expiry (limitation) |
| unauthenticated job/download | 401/404 as applicable (tested) |
| expired/stale token | claim() refuses; 410 (unit + live 410 observed) |
| duplicate download | second claim → 410 (live) |
| cleanup failure | in-process staged copy is discarded on instance death; no durable store exists to leak (design) |

## I. Performance (real production flow)

Full user-visible latency = request wall time (there is **no queue**;
inference runs inside the request, `maxDuration=60 s`; queue delay ≡ 0).
Warm worker; single-garment, 9:16:

n = 3 → min 25.2 s · P50 30.8 s · P95 33.7 s · max 33.8 s
(33.8 / 25.2 / 30.8). Worker cold start measured separately ≈ 15 s (would
add to first request after scale-to-zero). Failures fail faster
(≈22 s to a clean `VTON_INPUT_INVALID`).

## J. Async honesty

The 202 response is returned **after** inference completes — this is
in-request execution, not a background queue. DB job states are truthful
but `queued` is never a pollable in-flight state for a separate request.
Documented as a serverless platform limitation (per directive: no fake
states, no Vercel-incompatible queue machinery invented).

## K. Global + final security audits

- **Global (no Egypt-only assumptions)**: no Cairo/EGP/Egypt/localhost
  runtime assumptions in product logic. EGP appears only as (a) an
  overridable frontend prop default (`ShareCard` currency) and (b) payment
  capability catalog data (multi-market registry). `'Cairo'` in CSS is a
  typeface name. All timestamps are explicit `timezone.utc`.
- **Secrets**: deploy-tree scan clean (only an intentionally-fake JWT in a
  test file). No secret values were printed, persisted, or committed in
  this run.
- **Probes/diagnostics**: `/api/v1/diagnostic` is 404 for all authenticated
  users in production (ENVIRONMENT=production guard confirmed live;
  anonymous gets auth error first). All earlier diagnostic deployments
  torn down. **Exception**: the temporary `/api/_dbops` scoped function is
  still on the alias (see §L) — its four ops are read/no-op and leak no
  live values, but it must be removed by the prepared teardown deploy.
- **No-fake compliance**: no fixture images, no mocked API, no manual DB
  rows for acceptance, no injected frontend state, no worker-direct final
  proof — every completed job above was produced by the production stack
  through the production API with real user credentials.

## L. Classification (§21)

**`PARTIALLY_VERIFIED`**

Every §21 gate is live-verified on the production stack **except** the
strict reading of "acceptance must originate from the production
frontend": the browser click-through itself was not executed (no browser
in the execution environment). The gap is narrow and fully characterized:
the live production bundle was audited and calls exactly the verified API
contract with no client-controlled state, and the same flow was exercised
end-to-end via that contract with real users, garments, and GPU
inference. A 30-second manual click-through on `confit-a.vercel.app`
(catalog → try-on → result → download) would flip the classification to
`VERIFIED_PRODUCTION_VTON`.

Open items (blockers / actions, all environment- or scope-level, none
technical):
1. **Teardown deploy pending** — tree prepared (`/tmp/deploy_branch`,
   dbops removed, `/api/_dbops` verified absent): one-command Vercel
   deploy; blocked because the deploy credential is no longer present in
   the execution environment (not re-requested per policy).
2. **Push/PR pending** — `feat/vton-temporary-delivery` @ `281b0f4` (638be1a
   code + findings) and `security/fix-registration-role-escalation` @
   `17cc74c`: blocked on absent GitHub credentials.
3. **F-14 measurement-session IDOR** — fix designed, needs 0017 + a
   dedicated branch/PR (same pattern as the role fix).
4. **Hygiene at closure** — delete E2E users A/B and the seeded diagnostic
   admin `admin@confit.io` (or rotate) once the above land.
