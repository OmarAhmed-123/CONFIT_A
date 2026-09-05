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

Required fix (not yet in this branch): force `UserRole.CONSUMER` server-side
in `AuthService.register` regardless of the payload; add a regression test
that a register with `role=admin` yields a consumer. Existing accounts that
self-escalated in production must be audited/downgraded by an operator
(all probe accounts follow the `*.@test.dev` email pattern; one failed
registration, no account).

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

Status: committed locally; **push to GitHub blocked** — no GitHub
credentials exist in the environment (the earlier PAT is not persisted by
policy). Exact failure: `fatal: could not read Username for
'https://github.com': terminal prompts disabled`. One-time push of
`feat/vton-temporary-delivery` (tip `86b138e`) required.

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
