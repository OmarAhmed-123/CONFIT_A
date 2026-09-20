# CONFIT_A — Auth / Registration / Onboarding / Email
## Final Release Execution — Evidence Report

**Date:** 2026-09-19
**Branch:** `fix/auth-registration-onboarding-email`
**Reported in this document as:** *verified code tip* `1a2ee6da80e2500280df1955c4328b7875b660ec`
(tree `7f09ffb27dd3084330d9517a947a3d44b4be44e6`) — every gate below was executed against this
exact commit; the only commit after it is this report file (documentation only).
**Base:** `origin/main` @ `f024807b4a6aaa2cc3767827eae632e891f0821c` (fully contained: merge-base = origin/main)
**Production:** `https://confit-a.vercel.app/` running `f024807b…` (main) — **not** this branch

**Convention:** every statement is **WHAT / WHERE / HOW VERIFIED / EVIDENCE / STATUS**.
Evidence levels stay separate: **A** = code + executable test, **B** = real third-party provider
accepted the message, **C** = real mailbox received **and** the real link was redeemed.

---

## A. Executive result

> ## NO-GO — BLOCKED

All three external release prerequisites were re-checked against authorized surfaces only and
**all three remain absent** (§Z). No production migration ran, no email was sent, no PR exists,
nothing was deployed, and the controlled mailbox was not contacted (there is no authorized delivery
or read path). No artificial coding phase was created, and no verified implementation was touched.

This phase did produce two genuinely useful engineering results:

1. **The reported bookkeeping discrepancy is reconciled and benign** (§B–§E): the `24 commits /
   68382ca` figure and the `25 commits / 1a2ee6d` figure are both correct — the delta is exactly one
   documentation-only commit that changed no source file. Proof below.
2. **A CI-failure risk was pre-empted**: the repository runs `gitleaks` with *custom* rules for
   provider/database token classes (`.gitleaks.toml`). The CLI is CI-only, so its rule set was
   replicated locally and run against every file this branch changes → **clean** (§V, §24).

---

## B. Actual HEAD

- **EVIDENCE** — `git rev-parse HEAD` → `1a2ee6da80e2500280df1955c4328b7875b660ec`; branch
  `fix/auth-registration-onboarding-email`; `git status --short` → empty (clean tree).
- **STATUS** — **VERIFIED (actual git state, not reported state)**.

## C. Actual base

- **EVIDENCE** — `origin/main` = `f024807b4a6aaa2cc3767827eae632e891f0821c`;
  `git merge-base HEAD origin/main` = `f024807b…` ⇒ main is **fully contained**, no rebase was
  required this phase. Main did **not** advance since the previous phase (fresh fetch).
- **STATUS** — **VERIFIED**.

## D. Actual commit count

- **EVIDENCE** — `git rev-list --count origin/main..HEAD` → **25**.
- **RECONCILIATION OF THE FLAGGED DISCREPANCY** — the previous report's body was written when the
  tip was `68382ca…` (**24** commits). The subsequent commit `1a2ee6d` (the report itself plus the
  refreshed PR body and push instructions) took the branch to **25**. Proof that it changed **no
  source code**:
  ```
  git diff --stat 68382ca..HEAD
   .../AUTH_PRODUCTION_ACTIVATION_ATTEMPT_20260919.md | 330 ++++++++++
   docs/audits/PR_BODY_AUTH_ONBOARDING_EMAIL.md       |  15 +-
   2 files changed, 342 insertions(+), 3 deletions(-)
  ```
  `git show --name-only 1a2ee6d | grep -v '^docs/'` → **empty**.
- **CONSEQUENCE (stated precisely)** — the gate results recorded in the previous phase describe a
  code tree **byte-identical** to the current tip's code:
  `git diff --name-only 68382ca..HEAD | grep -v '^docs/'` → **empty**. The only delta is documentation.
- **STATUS** — **VERIFIED (reconciled; no history was rewritten to tidy the numbers)**.

## E. Actual tree hash

- **EVIDENCE** — `git rev-parse HEAD^{tree}` → `7f09ffb27dd3084330d9517a947a3d44b4be44e6`.
  PR-facing diff (`git diff origin/main...HEAD`): **62 files, +9894 / −412**.
- **STATUS** — **VERIFIED**.

## F. PR number and URL

- **EVIDENCE** — `git push --dry-run origin HEAD:refs/heads/probe` →
  `fatal: could not read Username for 'https://github.com'`. All credential surfaces re-checked and
  absent: `credential.helper`, `~/.git-credentials`, `~/.netrc`, `~/.ssh`, `GH_*`/`GITHUB_*` env, no `gh` CLI.
- **STATUS** — **BLOCKED**. **No PR number and no PR URL exist.** None is fabricated.

## G. CI result

- **WHERE** — `.github/workflows/ci.yml` (`backend`, `postgres-migrations`, `production-parity`,
  `frontend`) and `.github/workflows/gitleaks*.yml`.
- **HOW VERIFIED** — CI triggers on `push`/`pull_request`; with no push there is **no GitHub CI run
  for this branch**. Every job was therefore reproduced locally at the exact tip:

| CI job | Local reproduction | Result |
|---|---|---|
| `backend` — deployment dependency gate | `backend/scripts/check_runtime_imports.py` | `[vercel] OK — import closure fully declared`; `[docker] OK` |
| `production-parity` | `pytest backend/tests/test_production_parity.py` | **35 passed** |
| auth/email/onboarding batch (tip re-verification) | 4 focused modules | **48 passed** |
| frontend | `vitest run` / `tsc --noEmit` / `npm run build` | **121 passed / 21 files**, clean, built |
| gitleaks (rules replicated locally, see §V) | custom + standard rules vs all 62 changed files | **clean** |
| *(on the byte-identical code tree)* backend suite | `pytest backend/tests -q` | **1185 passed / 0 failed / 13 skipped** |
| *(idem)* migration chain | `check_migration_chain_postgres.py` (fresh PG) | **PASS** |
| *(idem)* CI's PG migration tests | 3 modules with `CONFIT_TEST_PG_URL` | **39 passed** |
| *(idem)* PostgreSQL races + recovery | `test_pg_concurrency_lifecycle.py` | **6 passed** |

- **STATUS** — **locally equivalent gates PASS; GitHub CI UNVERIFIED** (no push ⇒ no run). No test
  was deleted, weakened, skipped or marked expected.

## H. Merge SHA

- **STATUS** — **BLOCKED (nothing merged).** Production still runs main.

## I. Production deployment SHA

- **EVIDENCE (fresh)** — production deployment `f024807b4a6aaa2cc3767827eae632e891f0821c`,
  state `READY`, ref `main`.
- **ENDPOINT EVIDENCE (fresh)** — `/api/v1/health` → **200**; `/api/v1/auth/onboarding-state` →
  **404** ⇒ this branch is demonstrably **not deployed**.
- **STATUS** — production **VERIFIED as running main**; this work **VERIFIED as absent** from production.

## J. Production DB revision

- **EVIDENCE** — main's alembic directory ends at `0017_audit_before_after_request_id.py` and the
  production deployment runs a main commit ⇒ deployed schema ceiling **0017**.
- **STATUS** — production **0017**; 0018 **BLOCKED** (§K).

## K. Migration evidence

- **WHAT** — whether 0018 can be applied in production.
- **HOW VERIFIED (authorized surfaces only, re-checked this phase)** —
  - Vercel environment: **68 variables**; pattern scan `OWNER|MIGRAT|ALEMBIC|NEON` → **NONE**. The
    only database variable is the runtime `DATABASE_URL`.
  - No Alembic invocation exists in the deployment surface (Vercel build = frontend only; the
    serverless entrypoint imports the app).
  - CI's `postgres-migrations` job runs against a **throwaway `postgres:17` service container with a
    local password** — it consumes no project secret and cannot reach production.
  - The previously supplied owner credential is **rotated**; per standing constraint it was **not retried**.
- **LOCAL PROOF (unchanged, real PostgreSQL, not production)** — 0017 → legacy data → `upgrade head`
  → 0018 with all legacy users/brands/orders/refresh tokens/audit logs preserved byte-identically,
  `registration_intent` backfilled 4/4, 5 new tables, 3 partial unique indexes, 12 FKs, 28 indexes;
  the CI chain gate additionally proves downgrade→base→upgrade on a fresh database.
- **STATUS** — **BLOCKED — authorized production migration access unavailable.** No ownership change,
  no permission grant, no gate disabled, no migration rewrite, no data dropped, no fabricated success.

## L. Email provider

- **EVIDENCE (fresh)** — Vercel inventory: **68 variables**; `EMAIL|SMTP|RESEND|MAIL|FRONTEND_BASE`
  → **NONE** (including `FRONTEND_BASE_URL`, which every emailed link requires).
- **STATUS** — **BLOCKED**. No provider invented; no localhost SMTP / mock / test sink presented as
  production; no MCP inserted into the transactional path; no secret printed or committed.

## M. Provider acceptance evidence (level B)

- **EVIDENCE** — the only level-B transport evidence in existence is a loopback RFC 5321 server used
  by the test suite. **Zero messages were sent this phase.**
- **STATUS** — **third-party provider acceptance: UNVERIFIED** — for verification, reset and
  invitation mail alike.

## N. Mailbox evidence (level C)

- **WHAT** — the controlled recipient `omarsafealden@gmail.com`.
- **EVIDENCE** — not contacted; no provider exists to deliver through and no mailbox credential
  exists to read it. **Zero messages sent** (no marketing, no bulk, no repeats).
- **HYGIENE** — `grep -rn "omarsafealden"` over the repository returns only pre-existing documents
  referencing project-owned Vercel/Modal URLs; the address appears **nowhere** in application source,
  configuration defaults, or the branch diff.
- **STATUS** — **UNVERIFIED** (no receipt, no redemption).

## O. Verification evidence

- **A** — **VERIFIED (local)**: 17 lifecycle + 21 delivery + 6 PostgreSQL tests, including completing
  the flow by redeeming the token captured from the transport; 48-test focused batch re-run at the tip.
- **B** — **UNVERIFIED**. **C** — **UNVERIFIED**.

## P. Password reset evidence

- **A** — **VERIFIED (local)**: one-time reset link, replay/expiry negatives, no-leak on transport
  failure, explicit 501 when unconfigured (never a false success).
- **B** — **UNVERIFIED**. **C** — **UNVERIFIED**.

## Q. Partner approval evidence

- **A** — **VERIFIED (local)**: application → pending → admin-only approval → server-side brand
  provisioning → `brand_owner`; PostgreSQL race proves dual approval yields exactly one brand and one
  audit row.
- **B/C** — **UNVERIFIED**; production **BLOCKED**.

## R. Invitation evidence

- **A** — **VERIFIED (local)**: invitation → accept → membership carrying the token's role/brand,
  plus escalation / expiry / cross-tenant / foreign-tenant negatives, plus the PostgreSQL race
  (dual acceptance → exactly one membership).
- **B/C** — **UNVERIFIED**; production **BLOCKED**.

## S. B2B regression evidence (original screenshot defect)

- **WHAT** — consumer → `/b2b` must not be a dead end and must not grant privilege.
- **EVIDENCE (this phase, explicit A–E checks on the current tree)**
  - **A. main's public partner experience preserved** — `PartnerRequestDemoForm` 2 refs, 1 mount;
    `requestDemo` service 1 ref; `/b2b/request-demo` endpoint 1 ref.
  - **B/C/D. gate is state-aware and the state machine authoritative** — `account_state` +
    `partner_access` drive four real branches with server-chosen next actions:
    pending → `/partner/status`; rejected → `/partner/apply`;
    `EMAIL_VERIFICATION_REQUIRED`/`is_verified === false` → `/verify-email`;
    no workflow → `/partner/apply`; suspended → suspension copy.
  - **E. no frontend privilege grant** — authorization still `role`-based
    (`hasRole = !allowedRoles || allowedRoles.includes(userRole) || userRole === 'admin'`);
    the frontend only decides what to render.
- **EVIDENCE — the old dead end** — `grep` for main's dead-end markers
  (`Switch Account / Re-authenticate`, `Return to Consumer Storefront`) → **0 occurrences in this
  branch**, **1 occurrence on `origin/main` today**. The defect this work stream exists to fix is
  therefore still live on the deployed branch and fixed only here.
- **STATUS** — fix **VERIFIED (local)**; the production regression test of the new behaviour **BLOCKED**.

## T. RBAC evidence

- **EVIDENCE** — role guards and admin step-up unchanged; 19 `@limiter.limit` decorators;
  admin-only approval; `test_admin_review_requires_a_platform_admin` passing at the tip. This phase
  changed no authorization control.
- **STATUS** — **VERIFIED (local)**.

## U. Tenant-isolation evidence

- **EVIDENCE** — cross-tenant and foreign-tenant denial tests pass at the tip
  (`test_invitation_cannot_cross_tenants`, `test_invited_member_cannot_touch_another_brands_tenant`,
  plus the lifecycle matrix).
- **STATUS** — **VERIFIED (local)**; production **BLOCKED**.

## V. Security-negative evidence

| Negative | Evidence | Status |
|---|---|---|
| Injected `role` / `brand_id` / `is_verified` (register, incl. production-shaped payloads) | ignored; account `consumer`, `is_verified=false` | VERIFIED (local) |
| Invitation role/brand override, expiry, replay, cross-tenant | dedicated tests | VERIFIED (local) |
| Unauthorized admin approval | `test_admin_review_requires_a_platform_admin` | VERIFIED (local) |
| CSRF enforcement | POST without token → 403 `CSRF_TOKEN_MISMATCH` | VERIFIED (local) |
| Redirect parameters | `test_no_endpoint_accepts_a_redirect_parameter` (OpenAPI scan) | VERIFIED (local) |
| Duplicate application / duplicate acceptance | partial unique indexes + PostgreSQL races | VERIFIED (local) |
| **Secret leakage into the PR diff** | **62 changed files scanned with the repository's own gitleaks rules (custom + standard)** | **clean** |
| Production negatives | require a deployed branch | **BLOCKED** |

## W. Email reliability / idempotency evidence

- **EVIDENCE** — claim-before-send (one provider transmission per key, race-proved);
  `resolve_stale_delivery_claims` verified **active** at the tip: PostgreSQL test drives
  claim → abrupt process death (`BaseException`, which the service does not catch) → resolver →
  `unknown` → user retry with a **new** key → **exactly one** eventual message; the crashed key never
  re-transmits; a settled replay never touches the transport.
- **STATUS** — **VERIFIED (local, real PostgreSQL)**; production **BLOCKED** (feature not deployed).
  No unlimited retry exists and `unknown` is never converted to `succeeded`.

## X. Remaining GAPs

| GAP | Status |
|---|---|
| Partner notifications on stable keys cannot be re-emitted after an `unknown` outcome | Documented FOLLOW-UP (operator replay would require storing bodies/tokens — rejected) |
| Deliverability tooling (SPF/DKIM/DMARC, bounce handling) | FOLLOW-UP (requires a chosen provider) |
| Social signup intent | FOLLOW-UP (no OAuth credential in production) |
| Legacy `is_verified` accounts | **PENDING PRODUCT DECISION** — no silent change, no backfill in any migration |
| Real-browser E2E | UNVERIFIED — no browser framework added merely for coverage |
| Quote-style churn in two merged files (main uses double quotes) | Cosmetic; documented for reviewers |

## Y. Remaining UNVERIFIED

- Third-party provider acceptance (B) and real mailbox receipt + redemption (C) — verification, reset, invitation.
- GitHub CI for this branch; real-browser E2E; production behaviour of every new endpoint.

## Z. Remaining BLOCKED

1. **Production migration 0018** — no authorized owner path.
2. **Production email provider** — no configuration and no credential.
3. **Push / PR / CI / merge** — no GitHub credential.
4. Consequently the whole production programme: deployment SHA, schema 0018, registration,
   verification mail, reset, partner approval, invitation, tenant isolation, B2B matrix,
   original-screenshot regression on the new workflow.

## AA. Rollback plan

- **Migration** — 0018 additive and reversible; both directions exercised on real PostgreSQL and
  repeatedly proven by the chain gate (base → head → base → head). No populated column dropped; no
  data rewritten beyond the additive `registration_intent` backfill.
- **Application** — Vercel instant rollback to a recorded SHA (`f024807b…`, previously `463f81cc…`, `e1419d67…`).
- **Email** — with no provider configured, send-side endpoints answer `501 FEATURE_NOT_CONFIGURED`
  and the ledger records `BLOCKED`; the claim/resolver never transmits on its own, so a rollback
  cannot strand a half-sent message.
- **Ordering honoured** — 0018-dependent code is not promoted before the migration; the deployed SHA
  contains none of this work (404 evidence in §I).

## AB. BRD traceability

| BRD requirement | Implementation (WHERE) | Test | Runtime | Production | Status |
|---|---|---|---|---|---|
| Consumer lifecycle | `onboarding_service`, `RegistrationIntent`, auth endpoints, SPA routes | 17 lifecycle + PG flow | local smoke | none | A VERIFIED (local) / prod BLOCKED |
| Password recovery, single-use token | `token_service`, forgot/reset endpoints | one-time, replay, expiry, no-leak | local smoke | none | A VERIFIED (local) / prod BLOCKED |
| Partner lifecycle, **server-side** provisioning | `partner_service` (apply/review/provision/invite/accept) | lifecycle + PG races | local smoke | none | A VERIFIED (local) / prod BLOCKED |
| **Intent ≠ authorization** | `user_repository.create` (`is_verified=False` unconditional), role guards, intent-as-data; `registration_intent` typing (no `role` field — not reintroduced because another main component still types it) | injected-role tests | local smoke | none | A VERIFIED (local) |
| Real email → ledger, never fake success | `email_service` transports + ledger + 501 + claim-before-send + resolver | 21 delivery + 6 PG | loopback SMTP only | none | A VERIFIED / B,C UNVERIFIED |
| MCP excluded from the transactional path | `EMAIL_PROVIDER_MCP_EVALUATION_20260919.md` (decision unchanged, not reversed) | n/a | n/a | n/a | VERIFIED (documented) |
| No secrets in repo | branch-wide scan with the repo's own gitleaks rules | this phase | n/a | n/a | VERIFIED (clean) |
| Quality bar (negatives, correlation IDs, rate limiting, redirect allowlisting, DB uniqueness, additive migrations) | 19 limiters, request-id middleware, audit trail, partial uniques, 0018 | suite + chain gate | n/a | A VERIFIED (local) |

## AC. Final verdict

> ## NO-GO — BLOCKED

**Why not `PRODUCTION VERIFIED`** — production is at schema 0017, runs `f024807b…` (main), has no
email provider, and this work has no push, no PR, no CI run, no merge and no deployment SHA.

**Why not `PARTIALLY VERIFIED`** — no production gate passes; nothing from this work is in production.

**What stands as genuinely complete and reviewable**

1. A 25-commit branch integrated with current main, clean tree, reproducible artifacts
   (bundle + patch at the tip; `git am --3way` reproduces an **identical tree**).
2. All three lifecycles implemented with server-side authorization only, with the full quality bar
   (negatives, correlation IDs, rate limiting, redirect allowlisting, DB-enforced uniqueness,
   additive migrations).
3. Real-PostgreSQL proofs: five concurrency races (three genuine defects found and fixed, including a
   duplicate-send bug that really put two copies on the wire) and the mid-send crash recovery.
4. 0017 → 0018 proven non-destructive on real PostgreSQL, both directions.
5. The original `/b2b` dead end is replaced by the server-authoritative workflow — while main still
   ships the dead end.
6. This phase: the git-state discrepancy reconciled with proof, the critical defect preservation
   re-verified item by item (A–E), and the repository's own secret-scanner rules replicated locally
   and shown clean across all 62 changed files.

**To unblock — unchanged, in the required order**

1. Authorized **owner-run** production migration path (credential or owner-executed
   `alembic upgrade head`), then verify revision, tables, indexes, FKs, existing data, schema gate, health.
2. Real **email provider** configured with canonical variables only
   (`EMAIL_PROVIDER`, `EMAIL_FROM_ADDRESS`, `EMAIL_REPLY_TO`, `SMTP_*` or `RESEND_API_KEY`,
   `FRONTEND_BASE_URL=https://confit-a.vercel.app`), then provider acceptance (B) and mailbox
   redemption (C).
3. **GitHub push credentials** so the branch becomes a PR and CI can run before any merge.

*Nothing in this report is stronger than its evidence. Where the evidence stops, it says BLOCKED or
UNVERIFIED.*
