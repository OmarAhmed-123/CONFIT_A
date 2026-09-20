# CONFIT_A — Auth / Registration / Onboarding / Email
## Release Activation & Controlled Production Delivery — Final Report

**Date:** 2026-09-19
**Verified code tree:** `3b6be91` (22 commits) on base `origin/main` `463f81cc5623aa7466e1a411d317853c28d8662c`
**Branch:** `fix/auth-registration-onboarding-email`
**Predecessors:** `AUTH_PHASE_3_6_FINAL_REPORT_20260919.md` (authoritative Phase 3–6),
`AUTH_PHASE_7_CLOSURE_REPORT_20260919.md` (Phase 7 closure), `AUTH_REGISTRATION_ONBOARDING_ROOT_CAUSE_20260919.md`,
`EMAIL_PROVIDER_MCP_EVALUATION_20260919.md`, `docs/audits/PR_BODY_AUTH_ONBOARDING_EMAIL.md`

**Convention:** every claim is **WHAT / WHERE / HOW VERIFIED / EVIDENCE / STATUS**.
Evidence levels stay separate: **A** = code/test, **B** = a real provider accepted the message,
**C** = a real mailbox received and redeemed it.

---

## 1. Executive result

The three release blockers were re-tested against legitimate surfaces only, and **all three remain
genuinely blocked**:

| Blocker | Outcome of this phase's investigation |
|---|---|
| Production migration 0018 | **BLOCKED** — no owner-run migration mechanism exists anywhere in the project (CI's PostgreSQL job is a throwaway container with a local password; the Vercel build only builds the frontend; the serverless entrypoint never runs Alembic), and no owner credential is present in any legitimate configuration surface. The previously supplied owner DSN is rotated and was not retried. |
| Production email provider | **BLOCKED** — the production environment contains 68 variables, **none** of them email-related (`EMAIL_*`, `SMTP_*`, `RESEND_API_KEY`, `FRONTEND_BASE_URL` all absent). |
| GitHub push / PR | **BLOCKED** — `git push --dry-run` fails with `could not read Username for 'https://github.com'`; no credential helper, no stored credentials, no `~/.netrc`, no SSH key, no token in the environment. |

Because none of the three could be legitimately cleared, the release sequence could not start
(§7's order requires the migration and the provider before any promotion). Per the phase rule, no
artificial implementation phase was invented to fill the gap — **except** for one item the phase
explicitly asked to investigate and, if the gap proved real, to close: the claim-before-send crash
window (§18 below). That investigation found the gap was real, and a bounded, deterministic
recovery mechanism was implemented and proven on PostgreSQL.

**One discrepancy was found and corrected** (§2): `origin/main` advanced after the Phase 7 report
(`e1419d6` → `463f81c`, PR #112). The branch's own content matched the report exactly; only its
base was stale, so the branch was rebased — a release gate, not a rebuild.

---

## 2. Discrepancy matrix (checked before touching anything)

| Phase 7 report claim | Observed this phase | Verdict |
|---|---|---|
| `origin/main` = `e1419d6` | `origin/main` = `463f81c` ("Merge PR #112: Audit and harden target UX/product surfaces") | **STALE BASE** — main advanced after the report |
| Branch tip `fa01fd7`, tree clean | `fa01fd7`, tree clean | MATCHES |
| 21 commits ahead | 21 | MATCHES |
| 57 files `+8360/−323` | 58 files `+8842/−323` (diff base moved) | Explained by the base change, not by content drift |
| Rebased and containing `origin/main` | Did **not** contain the new `origin/main` | Rebase required (gate G1) |
| No file overlap between main's changes and the branch | `comm -12` of both file lists → **empty** | Rebase safe |

The new main content is 11 frontend consumer/try-on files (PR #112). It was rebased onto, and all
gates were re-run on the rebased tree.

---

## 3. Current production SHA

- **WHAT** — what production is actually running.
- **WHERE** — Vercel project `confit-a` (`prj_XaGsK8FP0dYc7yijAH58d1O0h1Vt`).
- **HOW VERIFIED** — `GET /v6/deployments?projectId=…&target=production`.
- **EVIDENCE** — latest production deployment: `463f81cc5623aa7466e1a411d317853c28d8662c`,
  state `READY`, created `2026-09-19T16:49:40Z`, ref `main`. Previous: `e1419d67…` (16:20:13Z).
- **STATUS** — production runs **main**, i.e. **not** this branch.

## 4. Branch SHA

- **EVIDENCE** — verified code tree `3b6be91`, **22 commits** ahead of `463f81c`,
  **60 files changed, +9230 / −322**, working tree clean; `git bundle` + `git format-patch` at this
  tip; `git am --3way` on a clean `origin/main` worktree reproduces **22 commits with an identical
  tree hash**. History and artifacts are regenerated after every commit (bundle 13,779,308 bytes;
  patch 651,140 bytes, pinned in `PUSH_INSTRUCTIONS.md`).
- **STATUS** — **VERIFIED (local)**.

## 5. PR number and URL

- **EVIDENCE** — `git push --dry-run origin HEAD:refs/heads/…` →
  `fatal: could not read Username for 'https://github.com'`. Credential surfaces checked and absent:
  `credential.helper`, `~/.git-credentials`, `~/.netrc`, `~/.ssh/*`, `GH_*`/`GITHUB_*` env.
- **STATUS** — **BLOCKED**. There is **no PR number, no PR URL, no base/head SHA pair on GitHub.**
  A local branch is not a pull request, and no PR evidence is fabricated here.

## 6. CI result

- **WHAT** — what CI actually verified for this work.
- **WHERE** — `.github/workflows/ci.yml` (jobs: `backend`, `postgres-migrations`, `production-parity`, `frontend`) plus gitleaks workflows.
- **HOW VERIFIED** — GitHub CI runs on `push`/`pull_request`; with no push there is **no CI run for this branch**. Every gate CI would execute was therefore reproduced locally, on the rebased tree:

| CI job | Local reproduction | Result |
|---|---|---|
| `backend` test suite | `PYTHONPATH=. pytest backend/tests -q` | **1177 passed / 0 failed / 13 skipped** (246.91 s), nothing excluded |
| `postgres-migrations` (real chain on PostgreSQL) | `backend/scripts/check_migration_chain_postgres.py` on a fresh database | **PASS** — head `0018`, ORM/migration parity `missing=[] extras=[]`, schema-gate verdict `ok` / `acceptable(production)=True`, downgrade→base→re-upgrade, numeric round-trip ok |
| `postgres-migrations` test files | `CONFIT_TEST_PG_URL=… pytest test_schema_drift_gate.py test_migration_integrity_behavioral.py test_migration_0013_quarantine_audit.py` | **39 passed** |
| `production-parity` | `pytest backend/tests/test_production_parity.py` | **35 passed** |
| `frontend` | `vitest run` / `tsc --noEmit` / `npm run build` | **121 passed / 21 files**, clean, build green (`index-CdcoSBRc.js`, 485.70 kB) |

- **STATUS** — **locally equivalent gates PASS; GitHub CI UNVERIFIED** (no PR → no run). No test was
  weakened or deleted.

## 7. Migration result

- **WHAT** — whether 0018 is applied in production.
- **WHERE** — production Neon database (runtime role `confit_app_rw`), revision `0017_audit_before_after_request_id`.
- **HOW VERIFIED** — the repository's own CI head for `main` ends at `0017_audit_before_after_request_id.py`, and production runs a `main` commit, so the deployed schema ceiling is 0017. The earlier owner-role attempt failed with `InsufficientPrivilege: must be owner of table users`.
- **Owner-path investigation (new this phase, all legitimate surfaces):**
  - `.github/workflows/ci.yml` `postgres-migrations` job → spins up a **throwaway `postgres:17` service container** with a local password (`CI_PG_PASSWORD`); it consumes **no repository or environment secret** and cannot reach the production database.
  - `vercel.json` build command → `npm --prefix frontend ci && npm --prefix frontend run build` (frontend only).
  - `api/index.py` (serverless entrypoint) → imports the ASGI app; **no Alembic invocation anywhere** in the deployment surface (`grep -rn alembic api/ vercel.json` → empty).
  - Vercel environment inventory → only `DATABASE_URL` (the runtime DSN); **no owner DSN, no `MIGRATION_*`, no `NEON_*`, no `ALEMBIC_*` variable**.
  - The owner credential supplied earlier is rotated (authentication failure) and was **not retried**, per the standing constraint.
- **STATUS** — **BLOCKED — awaiting authorized production migration capability.** No ownership
  bypass, no permission change, no table-ownership change, no gate disabled, no migration rewrite,
  no fabricated success. Production remains at **0017**.

## 8. Email provider

- **WHAT** — whether production can send mail at all.
- **HOW VERIFIED** — `GET /v9/projects/{projectId}/env` (full inventory, this phase).
- **EVIDENCE** — **68 variables**, of which the email block is entirely absent: no `EMAIL_PROVIDER`,
  `EMAIL_FROM_ADDRESS`, `EMAIL_REPLY_TO`, `SMTP_*`, `RESEND_API_KEY`, **and no `FRONTEND_BASE_URL`**
  (every emailed link is built from it). Nothing resembling a provider credential exists under any
  other name either (checked the full key list).
- **STATUS** — **BLOCKED — production email provider credentials/configuration unavailable.**
  No credential was invented, no personal mailbox substituted, no localhost SMTP presented as
  production evidence, no secrets committed.

## 9. Provider acceptance evidence (level B)

- **WHAT** — whether a real provider accepted a message.
- **EVIDENCE** — the only level-B evidence that exists is a **local RFC 5321 SMTP server on the
  loopback interface** used by the test suite (`LocalSMTPSink`): a real SMTP conversation, real
  message bytes, real tokens redeemed from the captured mail.
- **STATUS** — **third-party provider acceptance: UNVERIFIED.** A loopback sink is not a provider.
  The transport layer is real and exercised; the claim "a provider accepted our mail" has **no**
  supporting evidence in this environment.

## 10. Mailbox evidence (level C)

- **STATUS** — **UNVERIFIED.** No third-party provider exists, therefore no real mailbox received
  anything and no human-visible mailbox redeemed any link.

## 11. Registration verification

- **WHAT** — register → intent recorded → never born verified → verification email → redeem → verified → onboarding state → login/landing.
- **HOW VERIFIED (local, A-level)** — lifecycle tests plus the live smoke run; the PostgreSQL suite completes the flow end to end, redeeming the token that actually arrived.
- **EVIDENCE** — `test_auth_onboarding_lifecycle.py` (17 tests), `test_email_delivery.py` (21), `test_pg_concurrency_lifecycle.py` (6), live `curl` smoke. Client-injected `role` / `brand_id` / `is_verified` are ignored: the account is created `consumer`, `is_verified=false`.
- **STATUS** — **A VERIFIED (local)**; production registration verification **BLOCKED** (branch not deployed).

## 12. Password reset verification

- **WHAT** — request → single-use reset token → redeem → password changed → sessions rotated.
- **EVIDENCE** — `test_forgot_password_sends_real_one_time_link`, replay/expiry negatives, `test_forgot_password_smtp_failure_does_not_leak`; live smoke showed the endpoint returning 501 when no provider is configured (never a false success).
- **STATUS** — **A VERIFIED (local)**. B/C **UNVERIFIED** (no provider, no mailbox). Production: **BLOCKED**.

## 13. Partner onboarding verification

- **WHAT** — intent `brand_partner` → (still) consumer authorization → verification → application → pending → admin review → approval → BrandProfile → `brand_owner` → `/b2b` → tenant scope.
- **EVIDENCE** — `test_partner_application_is_pending_until_an_admin_approves`, `test_admin_review_requires_a_platform_admin`, `test_rejected_application_leaves_the_account_unprivileged_and_retryable`, plus the PG race suite (dual approval → exactly one brand, one audit row).
- **STATUS** — **A VERIFIED (local)**; production **BLOCKED**.

## 14. Invitation verification

- **WHAT** — owner invites teammate → invitation email → accept → membership with the token's role and brand.
- **EVIDENCE** — `test_brand_owner_invites_a_teammate_who_then_gets_scoped_access`, and the negatives: `test_invitation_escalation_and_abuse_paths_are_refused`, `test_expired_invitation_is_refused`, `test_invitation_cannot_cross_tenants`, `test_invited_member_cannot_touch_another_brands_tenant`; PG race proves dual acceptance yields exactly one membership (and, before the Phase 7 fix, a 500).
- **STATUS** — **A VERIFIED (local)**; production invitation flow **BLOCKED**.

## 15. Original screenshot regression result

- **WHAT** — consumer visits `/b2b`; the application must not grant access, silently change role, fake approval, or misdirect into a privileged portal. It should surface the real next state (apply / pending / rejected).
- **EVIDENCE (local)** — `RoleGuard.tsx` plus the onboarding-state machine: a consumer receives an actionable 403 surface with the true `next_action.route` (`/partner/apply`), never a privilege change; `landingPathForSession` trusts only the server's `next_action`.
- **EVIDENCE (production)** — the deployed build (a `main` commit) shows a real `403 ROLE RESTRICTION` for a consumer on `/b2b` (screenshot `uploads/image-1.png`); prod carries the *old* workflow, not this branch's.
- **STATUS** — **local: PASS (A)**. Production regression test of the *new* workflow: **BLOCKED** (not deployed).

## 16. RBAC result

- **EVIDENCE** — `core/dependencies.py` role guards and admin step-up, unchanged this phase; `AdminPartnersView` / `BrandTeamView` gated; approval is admin-only (`test_admin_review_requires_a_platform_admin`); 19 `@limiter.limit` decorators on auth/partner endpoints.
- **STATUS** — **A VERIFIED (local)**. No authorization control was widened: this phase's only backend edits narrow error paths (500 → precise 409) and add a terminal ledger state.

## 17. Tenant-isolation result

- **EVIDENCE** — `brand_scope_service` + membership checks; negatives prove a member of brand A cannot touch brand B, an invitation cannot cross tenants, and a rejected applicant holds no access.
- **STATUS** — **A VERIFIED (local)**; production **BLOCKED**.

## 18. Email reliability / idempotency result (new work this phase)

- **WHAT** — the phase asked whether the claim-before-send design leaves a real gap and, if so, to close it with the smallest deterministic recovery.
- **INVESTIGATION** — a search for recovery machinery found **none**: no retry worker, no reconciliation job, no stale-claim release, no scheduled repair, no provider-status reconciliation. A claim abandoned mid-send would therefore sit in `retrying` (a non-terminal state with no owner) **forever**, and `GET /auth/email-status` would report "in flight" indefinitely.
- **SEVERITY (honest)** — for verification/reset the user was never stranded (each request mints a new token ⇒ a new key); the concrete defects were (a) a permanently non-terminal ledger state, and (b) stable-key partner notifications (`app-received:{id}`, `app-decision:{id}:{status}`) that could never be re-emitted.
- **IMPLEMENTED (smallest deterministic mechanism, `3b6be91`)** —
  `email_service.resolve_stale_delivery_claims()`: bounded (LIMIT), idempotent, deterministic; resolves claims older than `EMAIL_CLAIM_STALE_SECONDS` (default 900) to a **new terminal status `unknown`** — never `succeeded`, never `failed`, because whether the provider accepted is genuinely unknowable; **transmits nothing**; keeps the idempotency key occupied so a later identical request cannot produce a second copy; emits a structured, secret-free event (`delivery_id`, `purpose`, `request_id`, `age_seconds`, `outcome=unknown_not_resent`). Wired to an existing scheduled maintenance task (15-minute celery beat, alongside the inventory sweeper) and opportunistically before a send. `EMAIL_PROVIDER`-independent; no new worker, no new queue, no new abstraction. Frontend status union extended with `'unknown'` so the UI cannot claim an unasserted success.
- **TESTED** — 4 SQLite cases (stale → `unknown`; fresh claim untouched; resolver idempotent; a replay of a resolved key is honest and sends nothing) and one **real-PostgreSQL** case that emulates abrupt process death (`BaseException`, which the service does not catch): claim → crash → recovery → **exactly one eventual send** on the user's retry, with the crashed key never producing a second copy.
- **BONUS DEFECT FOUND AND FIXED** — the resolver's first implementation crashed with `can't subtract offset-naive and offset-aware datetimes`: ledger timestamps are stored without timezone, so this would have failed in production too. Fixed via `token_service._as_utc` and naive-to-naive SQL comparison.
- **STATUS** — **IMPLEMENTED / TESTED / VERIFIED (local, SQLite + real PostgreSQL)**. Explicit non-decisions: no auto-retry, no "retry forever", no key release that could duplicate a message, no provider-status polling invented.

## 19. Remaining GAPs

| GAP | Status |
|---|---|
| Partner notifications on stable keys cannot be re-emitted automatically after an `unknown` outcome | Documented. The outcome remains visible in-product (`onboarding-state`, brand access); an operator replay would require storing message bodies/tokens — deliberately rejected. FOLLOW-UP. |
| Deliverability tooling (SPF/DKIM/DMARC, bounce webhooks) | FOLLOW-UP — impossible before a provider is chosen; the ledger already records per-attempt outcomes. |
| Social signup intent (Google/Apple/Facebook) | FOLLOW-UP — no provider credential in production; social signup yields a consumer, and the partner path stays reachable server-side. |
| Legacy `is_verified` accounts | **PENDING PRODUCT DECISION** — no silent change, no automatic re-verification, no backfill in any migration (verified by grep). |
| Browser (real-browser) E2E | **UNVERIFIED** — no Playwright/Cypress was added merely to raise coverage; API + component coverage retained. |

## 20. Remaining UNVERIFIED

- Third-party **provider acceptance** (level B) — loopback SMTP only.
- **Real mailbox receipt + redeem** (level C) — verification, reset, invitation.
- **GitHub CI** for this branch — no PR, therefore no run.
- **Real-browser** end-to-end behaviour.

## 21. Remaining BLOCKED

- **Production migration 0018** (no owner-run mechanism, no owner credential).
- **Production email provider** configuration and all email evidence beyond level A.
- **GitHub push / PR / CI / merge**.
- Consequently: the entire production verification programme (registration, verification email,
  reset, partner approval, invitation, tenant isolation, B2B matrix, original-screenshot regression
  on the new workflow, deployment SHA of this work).

## 22. Rollback plan

- **Migration** — 0018 is additive and reversible; both directions were exercised on real PostgreSQL
  this phase (`downgrade 0017_audit_before_after_request_id` → schema back to 0017 →
  `upgrade head` → integrity re-verified), and the CI chain gate repeatedly proves
  base → head → base → head. No destructive statement (no drop of a populated column, no data rewrite
  beyond the additive `registration_intent` backfill).
- **Application** — the branch is a self-contained 22-commit history; production rollback is the
  Vercel instant-rollback to the previous recorded SHA (`463f81cc…`, and if needed `e1419d67…`).
- **Email** — with no provider configured, send-side endpoints answer `501 FEATURE_NOT_CONFIGURED`
  and the ledger records `BLOCKED`; the new claim/resolution logic never transmits on its own, so a
  rollback cannot strand a half-sent message.
- **Ordering constraint honoured** — 0018-dependent code must not be promoted before the migration;
  the deployed prod SHA contains none of this work (new endpoints 404 there).

## 23. Exact deployment SHA

- **Production (current):** `463f81cc5623aa7466e1a411d317853c28d8662c` — **main**, not this work.
- **This work:** `3b6be91` (verified tree) — **not deployed**; no deployment SHA exists for it.
- **STATUS** — gate G15 (deployment SHA verified **for this work**) **BLOCKED**.

## 24. BRD traceability

| BRD requirement | Implementation (WHERE) | Evidence | STATUS |
|---|---|---|---|
| Consumer: registration → intent → verify → onboarding → session → portal routing | `models/user.py` `RegistrationIntent`; `services/onboarding_service.py` (`STATES`, `next_action`, `allowed_areas`); `views/auth/*`, `RoleGuard.tsx`, `AppRoutes.tsx`; endpoints `/auth/register`, `/auth/verify-email`, `/auth/onboarding-state` | lifecycle tests (17), PG crash-recovery test, live smoke | A VERIFIED (local) |
| Password recovery with a single-use reset token | `services/token_service.py`, `/auth/forgot-password`, `/auth/reset-password` | one-time-link test + replay/expiry negatives | A VERIFIED (local) |
| Partner: intent → verify → application/invitation → **server-side** provisioning → brand role → B2B | `services/partner_service.py` (`apply`, `review_application`, `_provision_brand`, `create_invitation`, `accept_invitation`), `/partner/applications`, `/admin/partner-applications`, `/brand/invitations` | lifecycle + invitation negatives + PG races (approval/invitation/application) | A VERIFIED (local) |
| Registration intent is **not** authorization; privileges only from trusted server workflows | `user_repository.create` (`is_verified=False` unconditional), role guards, intent-as-data | injected-role tests, live smoke (injected `role:"admin"` → consumer) | A VERIFIED (local) |
| No fake auth / emails / roles / delivery; MCP never a fake email abstraction | `email_service` real transports + ledger with `BLOCKED`/501 semantics; MCP evaluation document | 21 email tests, live 501 evidence, `EMAIL_PROVIDER_MCP_EVALUATION_20260919.md` (decision preserved — not reversed) | A VERIFIED (local) |
| No secrets in repo | tracked-file scans; the last token-class literal removed this phase | secrets grep on the branch diff | VERIFIED |
| New code quality bar: negatives, structured observability with correlation IDs, rate limiting, redirect allowlisting, a11y, DB-enforced uniqueness, additive migrations | `@limiter.limit` (19), request-id middleware, audit logs, partial unique indexes, 0018 additive + reversible, `test_no_endpoint_accepts_a_redirect_parameter` | suite + schema gate | A VERIFIED (local) |

## 25. Final verdict

> ## NO-GO — BLOCKED

**Why not the other options**

- **PRODUCTION VERIFIED** is unreachable: production is at schema **0017**, has **no email
  provider**, runs a different commit, and this work has no deployment SHA, no PR and no CI run.
- **PARTIALLY VERIFIED** would overstate the production position: nothing from this work is in
  production, and no production gate beyond "the old build serves" passes.

**What genuinely improved in this phase (reviewable now)**

1. Release blockers were re-tested against *legitimate* surfaces — CI database job, Vercel build,
   serverless entrypoint, full environment inventory — and the block is now evidenced, not assumed.
2. The stale-base discrepancy was caught and corrected; all gates re-run on the rebased tree
   (backend 1177 passed / 0 failed; frontend 121 passed, typecheck + build clean; migration chain
   gate PASS; CI's PostgreSQL migration tests 39 passed).
3. §12 re-proven on real PostgreSQL *including the downgrade direction*: 4 legacy users across all
   roles, one brand with its owner, category/product/SKU/refresh token/audit log/order all preserved
   byte-identically; `registration_intent` backfilled 4/4; 5 new tables, 3 partial unique indexes,
   12 foreign keys, 28 indexes.
4. The crash-window reliability gap was investigated, confirmed real, and closed with the smallest
   deterministic mechanism — plus a second latent defect (timezone arithmetic) found while proving it.
5. A residual token-prefix literal that could trip the repository's own secret scanner was removed.

**To unblock, in the required deployment order**

1. **Owner-run migration**: an authorized owner-role credential (or an owner-executed
   `alembic upgrade head`) for the production Neon project. Then verify revision, tables, indexes,
   FKs, existing users/brands/orders/refresh tokens, the startup schema gate and health.
2. **Real email provider** configured with the canonical variables only (`EMAIL_PROVIDER`,
   `EMAIL_FROM_ADDRESS`, `EMAIL_REPLY_TO`, `SMTP_*` or `RESEND_API_KEY`,
   `FRONTEND_BASE_URL=https://…`), then provider acceptance (B) and a real mailbox redeem (C).
3. **GitHub push credentials**, so the branch becomes a PR and CI can run before any merge.

*Nothing in this report is stronger than its evidence. Where evidence stops, it says BLOCKED or
UNVERIFIED.*
