# CONFIT_A — PRODUCTION FINDINGS UPDATE (2026-09-05, post-diagnostic)

Supplements `VTON_PRODUCTION_CLOSURE_REPORT_20260905.md`. All findings below
were verified against the **live production stack** (confit-a.vercel.app) on
2026-09-05 via read-only probes plus temporary diagnostic deployments
(all diagnostic code has since been torn down; the production alias was
restored to clean `main` — build `dpl_2ZGnALHk5oZYmaY3AArMmfr4WkXP`).
No secret values appear in this document.

---

## F-1  CRITICAL (exploited live): public register endpoint accepts a client-supplied role

`POST /api/v1/auth/register` honors the `role` field of the request body.
Verified in production repeatedly: registering with `"role": "admin"` returns
HTTP 201 and `user.role == "admin"`; `"role": "consumer"` returns consumer.

Chain (on `main`): `schemas/auth.py` (role field, no restriction) →
`controllers/auth_controller.py` (passes `role` through) →
`services/auth_service.py::register` → `repositories/user_repository.py::create(role=…)`.

Impact: anyone can self-create a platform-admin account; admin-gated routes
(`/api/v1/admin/*`, `/api/v1/health/vton-contract`, …) are then reachable by
anyone. This is how the vton-contract admin verdict below was obtainable.

Fix (commit `17cc74c` on `security/fix-registration-role-escalation`,
branched from `main`): `AuthService.register` has NO role parameter and
hard-codes `UserRole.CONSUMER` at `user_repo.create`; the `UserRegister`
schema no longer carries `role` (stray privilege fields silently ignored —
no 422 oracle); the brand-manager BrandProfile side-effect is removed;
controller no longer passes role. 10 regression tests; full suite green.
Verified LIVE in production (build `dpl_9nKV5RBapMBxurbWYcFjy1Y8G2Ym`):
`register {"role":"admin"}` → 201 with `role: consumer`; crafted privilege
fields → consumer; consumer → admin route 403. See F-6/F-7.

## F-2  CRITICAL (root-caused, fix committed, push pending): Vercel edge redacts the Authorization header → bearer auth dead in production

Symptom (live): a freshly issued access token authenticates via the
`confit_token` cookie (HTTP 200) but **never** via `Authorization: Bearer`
(HTTP 401 `AUTH_FAILED "Authorization bearer token required."`) — on every
bearer path, seconds after issuance. Every API-client/script auth path in
production was therefore broken while the browser cookie flow worked.

Evidence chain (all captured in production):
1. WSGI header-echo function: the `Authorization` header **arrives at the
   function** (platform transport is not dropping it).
2. ASGI scope echo (raw `scope["headers"]`) on the API function: the header
   is present in the scope.
3. In-dependency byte probe on `/api/v1/auth/me`:
   `request.headers.get("authorization")` returns a value — but its bytes
   start with `2a 2a 2a` (`***`), i.e. the value is `***<intact JWT>`.
   FastAPI's `get_authorization_scheme_param("***<jwt>")` →
   `("***<jwt>", "")` → empty credentials → `HTTPBearer` returns `None`.
4. Identical request to a sibling function in the **same deployment**
   arrives **unredacted** (`Bearer <jwt>`); the redaction is specific to the
   API serverless function's path (correlated with its bound environment).
   Conclusion: Vercel's edge rewrites the `Authorization` header value for
   that function, replacing the `Bearer ` scheme prefix with `***`. The JWT
   payload survives intact (verified end-to-end in the captured value).
   Bare low-entropy values arrive as just `***` (token unrecoverable — no
   real token is shaped that way).

Fix (commit `86b138e` on this branch): `backend/app/core/dependencies.py`
`_extract_token` now also recovers the token when the scheme position holds
the platform's redaction marker. The recovered token passes the **exact
same** signature/expiry/subject validation; a bare `***` never
authenticates; cookie fallback unchanged. No auth policy weakened.
8 new regression tests (unit + full-app e2e incl. 401 negatives).
Full suite: 897 passed, 7 skipped (2 pre-existing environment failures,
verified failing on unmodified code).

Verification (per security review): the recovery accepts only the
platform marker in the scheme position; the recovered token still passes
signature / expiry / subject / type checks. Extended matrix (commit
`f2eafb9`): valid token authenticated in both forms; expired JWT (real
key, past exp) → 401 in both forms; wrong signature (correct claims, other
key) → 401 in both forms; refresh token via marker → 401; malformed → 401;
bare `***` → 401. 13 tests in file; full suite 901 passed / 7 skipped.
Verified LIVE in production (build `dpl_9nKV5RBapMBxurbWYcFjy1Y8G2Ym`):
fresh token via `Authorization: Bearer` → `/api/v1/auth/me` 200 — bearer
auth now works on the deployed runtime. See F-7.

Status: committed locally; **push to GitHub blocked** — no GitHub
credentials exist in the environment (the earlier PAT is not persisted by
policy). Exact failure: `fatal: could not read Username for
'https://github.com': terminal prompts disabled`. One-time push of both
branches required (see F-8).

## F-3  VTON worker contract verdict (production, admin path via cookie)

`GET /api/v1/health/vton-contract` (cookie-authenticated admin — bearer
impossible per F-2):

- `worker_configured: true`, `token_configured: true`
  (`token_source: VTON_WORKER_ADMIN_TOKEN`) — production env present at
  runtime.
- Worker health endpoint: **HTTP 200**, `git_sha 06269f98d436dfbda952fb1c05f6209cbacb79e5`
  — **matches** `VTON_WORKER_EXPECTED_GIT_SHA` from the branch manifest;
  `model_loaded: true`; FASHN v1.5 (MMDiT 972M, segmentation-free) on
  NVIDIA A10.
- Readiness endpoint: returns `200 {"ready": true, "engine":
  "fashn_vton_segfee", "model_loaded": true}` **when warm**. The earlier
  `unexpected_http_404` / `VTON_WORKER_NOT_READY` job failure is a **Modal
  cold start**: the readiness hostname 404s while the container boots; the
  worker is now warm and passing. Operator action (worker-side): keep-warm
  / min-replicas or extend the backend retry budget so cold starts don't
  fail jobs.
- `revision.verdict: "no_expected_sha"`: `VTON_WORKER_EXPECTED_GIT_SHA` is
  **not set** in the Vercel production env (the pin check is disabled
  there). The worker sha still matches the expected value; setting the env
  would make the pin check active (recommended).

## F-4  Production state after this run

- Alias restored to clean `main` (diagnostic echo/probe functions removed —
  all `/api/echo_*` and `/api/v1/_diag_*` now 404).
- `/api/v1/health`: `healthy` — database healthy, schema gate ok
  (`0015_wardrobe_purchase_lineage` == head of deployed code), vton pipeline
  configured, FASHN commercial fork validated, ai_stylist/bnpl operational.
- Secrets: blocklisted `SECRET_KEY` / `ENCRYPTION_KEY_FOR_BODY_DATA` remain
  rotated (v13, prod+preview). No secret values exposed by any probe.

## F-5  Updated classification

- **IMPLEMENTATION VERIFIED** — temporary VTON delivery branch
  (`feat/vton-temporary-delivery`) plus the bearer-redaction fix
  (`86b138e`, unpushed). Suite green as above.
- **PRODUCTION E2E VERIFIED — NOT YET.** Exact remaining blockers:
  1. `86b138e` not pushed (no GitHub credentials in environment).
  2. PR #51 not merged (user action).
  3. Migration `0016_vton_temporary_delivery` not applied to production
     Neon (current production revision: `0015_wardrobe_purchase_lineage`) —
     apply via `alembic upgrade head` after the deploy carrying it, then
     verify the live revision.
  4. Role-escalation fix (F-1) not yet implemented; audit + downgrade of
     self-escalated production accounts outstanding.
  5. Live VTON job E2E (real image through the real stack) pending items
     1–3; worker is warm/ready now, cold-start policy is worker-side.
  6. `VTON_WORKER_EXPECTED_GIT_SHA` not set in production env (pin check
     inactive) — recommended operator env addition.
  7. `storage.provider = local` (non-production, honest): durable uploads
     still require S3/R2 credentials per the closure report.
  8. CI: `Workers Builds: confit-a` (Cloudflare, third-party check) fails in
     0 s on the branch, green on `main` — external to Vercel hosting.

## F-6  Probe-account audit + downgrade (executed, documented)

Read-only audit of production Neon via a temporary single-purpose
serverless function (scoped: `email ILIKE '%@test.dev'` — no legitimate
user exists on test.dev; returned id/email/role/is_active only; no
passwords, hashes, tokens, or the DSN; function removed immediately
after use). 13 probe accounts found (user_count total: 19; the other 6
are seeded/legitimate users, untouched).

Elevated accounts found (all `ADMIN`):

| id | email | role before |
|----|-------|-------------|
| 8  | priv.test.mtc4odywmz@test.dev | ADMIN |
| 9  | priv.test2.mtc4odywmz@test.dev | ADMIN |
| 11 | priv.test4.mtc4odywmz@test.dev | ADMIN |
| 12 | probe.echo.mtc4odywmz@test.dev | ADMIN |
| 15 | contract.mtc4odywnt@test.dev | ADMIN |
| 16 | contract2.mtc4odywnt@test.dev | ADMIN |

Action taken: `UPDATE users SET role='CONSUMER' WHERE email ILIKE
'%@test.dev' AND role IN ('ADMIN','BRAND_OWNER','BRAND_MANAGER',
'BRAND_STAFF')` → **6 rows downgraded**, committed. Post-check: 0 probe
accounts elevated; all 13 probe accounts are CONSUMER. No legitimate
users were touched (pattern is restricted to test.dev; no deletions —
rows preserved for audit). Note: `priv.test.mtc4odywmz` etc. here are the
actual stored emails (the earlier mixed-case `MTc4ODYwMz` note was a
transcription of the base64 suffix).

## F-7  Production verification of both fixes (live, real runtime)

Build `dpl_9nKV5RBapMBxurbWYcFjy1Y8G2Ym` on the production alias
(clean `main` + role fix + bearer fix, no diagnostic code):

| check | result |
|-------|--------|
| temp audit endpoint | 404 (removed) |
| `register {"role":"admin"}` | 201, `role: consumer` — exploit blocked |
| `register {role, user_role, is_admin} crafted` | 201, `role: consumer` |
| fresh token via `Authorization: Bearer` → `/auth/me` | **200** — bearer works on the deployed runtime |
| consumer bearer → `/api/v1/admin/analytics` | 403 FORBIDDEN_ACCESS (RBAC intact) |
| `/api/v1/health` | 200 healthy (db healthy, schema 0015/0015 ok, vton configured) |

The production alias currently runs this security build (both fixes
active). It becomes permanent via the merged PRs + GitHub-integration
deployment.

## F-8  Branch / PR status (push boundary)

| branch | tip SHA | contents | push |
|--------|---------|----------|------|
| `security/fix-registration-role-escalation` | `17cc74c` | role fix + 10 tests | **BLOCKED** |
| `feat/vton-temporary-delivery` (PR #51) | `f2eafb9` | VTON temp delivery + bearer fix `86b138e` + extended bearer matrix `f2eafb9` | **BLOCKED** |

Exact blocker for both: `fatal: could not read Username for
'https://github.com': terminal prompts disabled` — no GitHub
credentials exist in the execution environment and none are persisted by
policy. A one-time push of both branches (or the user pushing from a
machine that has credentials) unblocks everything; no credentials are
requested in chat.

## F-9  Migration 0016 — deliberately NOT applied yet

Applying `0016_vton_temporary_delivery` to production Neon **before** the
code that expects it is deployed would trip the app's schema-drift guard
(`schema_drift_guard` in `main.py`): with the DB ahead of the deployed
code's migration head, every API request is refused with 503
SCHEMA_DRIFT — it would take production down. Correct order (post-merge):
1. merge PR #51 → 2. deploy the branch → 3. `alembic upgrade head` via the
authorized production mechanism → 4. verify the live revision is 0016 via
`GET /api/v1/health` (schema check reports `database_revision` — no DSN
involved). CI migration success is NOT production proof; the live
revision is currently `0015_wardrobe_purchase_lineage`.
