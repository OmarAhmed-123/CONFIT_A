# CONFIT_A — Auth / Registration / Onboarding / Email
## Phase 7 Closure Report — production integration, verification and delivery

**Date:** 2026-09-19
**Branch:** `fix/auth-registration-onboarding-email` @ `add627c60e402a359e21eca7244c82a1627f6a10`
**Base:** `origin/main` @ `e1419d67e85db0242b58498cc91c9daddf6f4e2f`
**Verified code tip:** `add627c60e402a359e21eca7244c82a1627f6a10` (all gate results below describe this
tree); this report and the refreshed PR body are committed directly on top of it.
**Companion documents:** `AUTH_PHASE_3_6_FINAL_REPORT_20260919.md` (authoritative for Phase 3–6),
`AUTH_REGISTRATION_ONBOARDING_ROOT_CAUSE_20260919.md` (RC-1…RC-7, G-01…G-18),
`EMAIL_PROVIDER_MCP_EVALUATION_20260919.md`, `PR_BODY_AUTH_ONBOARDING_EMAIL.md`.

**Reporting convention used throughout (§18):** every major statement is given as
**WHAT / WHERE / HOW VERIFIED / EVIDENCE / STATUS**. Evidence levels are kept strictly separate:

| Level | Meaning | In this report |
|---|---|---|
| **A** | Code path exists and is exercised by tests | Many claims |
| **B** | A real provider/transport accepted the message | Reachable only through a local RFC 5321 SMTP server — **third-party provider acceptance UNVERIFIED** |
| **C** | Real mailbox receipt + redeem by a human-visible mailbox | **UNVERIFIED** |

Statuses used: **IMPLEMENTED / TESTED / VERIFIED / BLOCKED / GAP / NO-GO / UNVERIFIED**.
"VERIFIED" is never used for anything that was only observed locally on a replica when the
claim is about production.

---

## A. Scope and method

**WHAT** — Close out the auth/registration/onboarding/email work stream: re-verify the actual
repository state, preserve the already-verified security architecture, prove the concurrency and
migration behaviour on **real PostgreSQL**, settle configuration consistency and fail-safe gates,
triage the remaining gaps, and issue exactly one verdict that the evidence supports.

**WHERE** — Repository `OmarAhmed-123/CONFIT_A`, branch `fix/auth-registration-onboarding-email`;
local PostgreSQL 17.11 replica; production project `confit-a` (Vercel) and its Neon database.

**HOW VERIFIED** — Fresh anonymous `git fetch`; rebase onto current `main`; full backend suite;
frontend suite + typecheck + production build; a new PostgreSQL concurrency suite; a re-run of the
0017→0018 migration on a real PostgreSQL cluster with legacy data; production probes (deployment
SHA, environment inventory, health, endpoint presence); artifact (`bundle` + `patch`) regeneration
with `git am --3way` reproduction.

**EVIDENCE** — Sections B–N below, each with concrete commands, files and results.

**STATUS** — **IMPLEMENTED / TESTED / locally VERIFIED** for the code work; **BLOCKED** for every
gate that requires production credentials or a production email provider (Section K/L/N).

### What Phase 7 deliberately did *not* do
- Did not rebuild or re-litigate Phase 3–6 verified work (only re-verified it, Section C).
- Did not weaken any authorization control to make the workflow smoother (§2, Section D).
- Did not add Playwright/Cypress for feature count (Section M).
- Did not run the concurrency suite against the production database.
- Did not retry the rotated Neon owner credential, and did not attempt any ownership bypass,
  destructive permission change, or migration rewrite.

---

## B. Repository and branch state (fresh, this phase)

**WHAT** — The branch is rebased onto the newest `main` and its content is reproducible outside
this workspace.

**WHERE** — `repo/` (sparse clone), artifacts in `/home/user/`.

**HOW VERIFIED**

1. The `origin` remote had disappeared with a sandbox reset (`.git/config` is not part of the
   snapshot). Re-added `https://github.com/OmarAhmed-123/CONFIT_A.git`; anonymous fetch
   **succeeded** (repository is publicly readable), refreshing all refs.
2. `origin/main` = `e1419d6` ("Merge PR #111: Fix Discover try-on button contrast").
   `git merge-base --is-ancestor origin/main HEAD` → true: the branch **already contains** the
   current main.
3. Overlap check between the branch diff and `e1419d6`'s diff → empty (no shared file), so the
   rebase was clean: 20 commits replayed, no conflicts, working tree clean.
4. `git bundle verify` → "The bundle records a complete history"; `git am --3way` of the patch on a
   clean `origin/main` worktree → 20 commits applied, resulting **tree hash
   `2f8af4994f756d2457c97bc79b2767b449877a80` identical to the branch tree**. (The tip *commit*
   hash differs — `75f2cb3` vs `add627c` — because `git am` rewrites committer metadata; the tree
   is the meaningful equality, and it is exact.)

**EVIDENCE**

| Item | Value |
|---|---|
| Branch tip | `add627c60e402a359e21eca7244c82a1627f6a10` |
| Commits ahead of `origin/main` | 20 |
| Diff vs `origin/main` | 57 files, +8360 / −323 |
| Working tree | clean |
| `auth-onboarding-email.bundle` | 13,729,395 bytes (refs `origin/main` + `HEAD`) |
| `auth-onboarding-email.patch` | 585,298 bytes, 20 patches |
| Patch reproduction | identical tree, verified by `git am --3way` |
| Push / PR | **BLOCKED** — `git push --dry-run` → `fatal: could not read Username for 'https://github.com'`; no credential helper, no `~/.git-credentials`, no `~/.netrc`, no SSH key |

**STATUS** — Rebase and artifact reproduction **VERIFIED**; push/PR **BLOCKED** (a local branch is
not a GitHub PR).

### Commits added in Phase 7 (on top of the rebased Phase 3–6 history)
| SHA | Subject |
|---|---|
| `6eddb63` | `fix(concurrency): map duplicate-insert races to domain conflicts` |
| `d720d95` | `test(concurrency): prove five real races on PostgreSQL (not SQLite)` |
| `e719b20` | `test(config): cover the two production email boot gates` |
| `add627c` | `docs(env): replace drifted SMTP variable names with the canonical set` |

---

## C. §1 Claim / code / test / runtime / prod / status table

**WHAT** — Every headline claim of this work stream, re-checked against the actual repository in
this phase rather than restated from earlier reports.

| # | Claim | Code (WHERE) | Test | Runtime evidence | Prod | STATUS |
|---|---|---|---|---|---|---|
| 1 | Registration intent is recorded as data and never grants a role | `models/user.py` `RegistrationIntent`; `user_repository.create(registration_intent=…)`; `controllers/auth_controller.py` | `test_registration_intent_is_recorded_and_never_grants_a_role`; `test_injected_role_field_is_ignored_and_intent_is_validated` | Live smoke: POST register with `role:"admin"`, `is_verified:true`, `brand_id:1` → account created as **consumer, `is_verified:false`** | Not deployed | **VERIFIED (local)** |
| 2 | No account is ever born verified | `repositories/user_repository.py:48` `is_verified=False` (unconditional) | `test_registration_never_marks_an_unverified_address_verified` | Live smoke above | Prod build (old code) showed `is_verified:true` on a fresh account — the reason this fix exists | **VERIFIED (local)** |
| 3 | Verification is only demanded when a provider exists; no silent bypass | `core/config.py`, `services/email_service.py::is_email_configured`, `501 FEATURE_NOT_CONFIGURED` | `test_register_sends_verification_only_when_configured`; `test_verify_email_still_501_when_unconfigured` | `GET /auth/email-status` → `{status:"none", accepted:false, provider_configured:false}`; verify-email → 501 | Not deployed | **VERIFIED (local)** |
| 4 | Partner approval requires a platform admin and provisions server-side | `services/partner_service.py::review_application`, `_provision_brand`; `core/dependencies.py` admin guard | `test_partner_application_is_pending_until_an_admin_approves`; `test_admin_review_requires_a_platform_admin` | Live smoke: self-approve → 403; admin approve → `{approved, brand_id:5}`, applicant becomes `brand_owner` | Not deployed | **VERIFIED (local)** |
| 5 | Invitation role/brand come from the token row, never the request | `services/partner_service.py::accept_invitation` | `test_invitation_escalation_and_abuse_paths_are_refused`; `test_expired_invitation_is_refused`; `test_invitation_cannot_cross_tenants`; `test_invited_member_cannot_touch_another_brands_tenant` | Live smoke: invite accept → scoped access | Not deployed | **VERIFIED (local)** |
| 6 | Email delivery is real or explicitly refused — never simulated | `services/email_service.py` (`send_transactional`, ledger, `BLOCKED`/501) | `test_email_real_transport.py` (9); `test_email_delivery.py` (17) | Local RFC 5321 SMTP conversation captured; ledger row per attempt | **No provider configured** (0 of 68 Vercel vars are email-related) | **BLOCKED in prod** |
| 7 | Verification / reset tokens are single-use, expiring, hashed at rest | `services/token_service.py` | `test_verification_replay_rejected`; `test_verification_expired_token_rejected`; `test_verification_garbage_token_rejected`; `test_forgot_password_sends_real_one_time_link` | Live smoke: replay refused | Not deployed | **VERIFIED (local)** |
| 8 | No endpoint accepts a client-supplied redirect/return target | OpenAPI scan of every registered route | `test_no_endpoint_accepts_a_redirect_parameter` | OpenAPI dump: zero `next`/`redirect`/`returnUrl`/`continue`/`url` params | Not deployed | **VERIFIED (local)** |
| 9 | Consumers cannot reach privileged B2B surfaces | `core/dependencies.py` role guards; `RoleGuard.tsx`; `AdminPartnersView`/`BrandTeamView` | `test_platform_admin_has_global_oversight`; lifecycle matrix | Local: consumer → `/b2b` denied with actionable 403 | Prod (old build): real 403 ROLE RESTRICTION observed (screenshot `uploads/image-1.png`) | **VERIFIED (local)** / prod = **old build, real control** |
| 10 | Concurrency cannot produce double privileges or double sends | `services/{auth,partner,email}_service.py` (this phase) | `test_pg_concurrency_lifecycle.py` (5 races, real PostgreSQL) | Section F | Race suite **not** run against prod DB (deliberate) | **VERIFIED (local PostgreSQL)** |
| 11 | Migration 0017→0018 preserves existing data non-destructively | `alembic/versions/0018_partner_onboarding_email_lifecycle.py` | `/tmp/verify0018.py` integrity script | Section G | **BLOCKED** — owner credential unavailable | **VERIFIED (local PostgreSQL)** / prod **BLOCKED** |
| 12 | Configuration has one canonical email variable set | `core/config.py`, `backend/.env.example §9`, fixed run guide | `test_production_boots_refuse_*` (3 gates) | Section I | Prod has **no** email variables at all | **VERIFIED (local)** |
| 13 | Deployment and prod E2E | — | — | prod runs `e1419d6` (main), new endpoints 404 | **BLOCKED** | **BLOCKED** |

---

## D. §2 Security architecture preserved

**WHAT** — Phase 7 changed error paths and documentation only. No authorization control was
widened, and the 403 remains a real authorization control whose *workflow* was improved for the
user, not its gate.

**WHERE / EVIDENCE** (all re-read from the current tree, not from memory):

- RBAC: `core/dependencies.py` (`require_roles`, admin step-up) — unchanged.
- Tenant isolation: `services/brand_scope_service.py`, membership checks in `partner_service.py` —
  unchanged; cross-tenant negatives are test-covered (row 5 above).
- CSRF double-submit + httpOnly cookie sessions + refresh rotation: `main.py` middleware,
  `services/token_service.py` — unchanged; verified live (POST without CSRF → 403
  `CSRF_TOKEN_MISMATCH`).
- Rate limiting: 19 `@limiter.limit` decorators on auth/partner endpoints — unchanged.
- Approval controls and invitation authorization — unchanged; the only Phase 7 edits inside
  `partner_service.py` are `except IntegrityError` handlers that **narrow** a 500 into a precise
  409 after re-reading authoritative state.
- redirect allowlisting — no endpoint accepts a redirect target (row 8).

**STATUS** — **VERIFIED** (unaltered; controls re-read, re-tested, cross-checked against the
earlier verification matrix).

---

## E. §3 Verification truth (`is_verified`)

**WHAT** — The defect where a deployment without an email provider silently created accounts with
`is_verified=True` (i.e. an absent integration implying a completed check) is fixed, and no
existing account was silently altered.

**WHERE / HOW VERIFIED**
- Creation path: `backend/app/repositories/user_repository.py` → `is_verified=False`, **line 48**,
  no condition on `settings.EMAIL_PROVIDER` anywhere in the file.
- Backfill policy: `grep -rn "is_verified *= *True" backend/alembic/versions/*.py` → **no match**.
  Migration 0018 backfills only `registration_intent` (varchar NOT NULL DEFAULT `'consumer'`),
  never verification state. Legacy accounts keep exactly the flag they had.
- No-provider partner exception is explicit and auditable: `email_verified:false`,
  `verification_unavailable:true`, plus reviewer-visible `applicant_email_verified` /
  `applicant_verification_available`.
- Tests: `test_registration_never_marks_an_unverified_address_verified` (line 523),
  `test_partner_application_records_and_exposes_the_verification_exception` (549),
  `test_verified_applicant_is_reported_as_verified_to_the_reviewer` (599) — all green.
- Prod: not deployed; **no prod claim is made**.

**STATUS** — **VERIFIED (local, code + tests)**. Prod re-verification **BLOCKED** (branch not
deployed). Backfill policy for historical accounts remains a product decision and is **not**
performed.

---

## F. §11 Real concurrency on PostgreSQL — three genuine defects found and fixed

**WHAT** — Five races, each driven through the real HTTP API with a `threading.Barrier` so both
requests are provably in flight simultaneously, against **real PostgreSQL 17.11**
(db `confit_pg_race`), not SQLite.

**WHERE** — `backend/tests/test_pg_concurrency_lifecycle.py` (gated on `CONFIT_PG_DSN`), with
fixes in `services/auth_service.py`, `services/partner_service.py`, `services/email_service.py`.

**HOW VERIFIED** — `CONFIT_PG_DSN=postgresql://postgres@127.0.0.1:5433/confit_pg_race PYTHONPATH=. \
python3 -m pytest backend/tests/test_pg_concurrency_lifecycle.py -q` → **5 passed**.

| Race | Behaviour before this phase | Behaviour now | Status |
|---|---|---|---|
| Two admins approve the same application | loser → **HTTP 500** `UniqueViolation brand_profiles_user_id_key` | loser → **409** `APPLICATION_ALREADY_REVIEWED` (or `PROVISIONING_CONFLICT` when the observed state does not support the stronger claim); exactly 1 brand, 1 audit row | **FIXED, TESTED** |
| Two simultaneous acceptances of one invitation | loser → **HTTP 500** `UniqueViolation ix_users_email` | loser → **409** `INVITATION_ALREADY_ACCEPTED` / `INVITATION_ACCEPTANCE_IN_PROGRESS`; exactly 1 membership | **FIXED, TESTED** |
| Two identical email sends (same idempotency key) | **both messages left the process** and reached the provider (2 SMTP messages) while the ledger recorded 1 — the unique index deduplicated the *record*, not the *send* | the key is **claimed (status `retrying`, committed) before the provider call**; exactly 1 message reaches the provider, the other caller gets the winner's outcome or an honest `retrying` | **FIXED, TESTED** |
| Two simultaneous registrations of one address | loser → **HTTP 500** (same check-then-insert shape) | loser → **409** `EMAIL_ALREADY_REGISTERED`; exactly 1 account, role consumer | **FIXED, TESTED** |
| Duplicate partner applications | already correct (partial unique index `uq_partner_applications_user_pending`) | unchanged: one `201` + one `409 PARTNER_APPLICATION_PENDING`, 1 row | **VERIFIED** |

**Honest limitation, documented not hidden:** if the process dies between claiming the key and
recording the outcome, that ledger row stays `retrying` and the same key will not re-send. This is
the deliberate trade-off (the alternative demonstrably double-sends). It does not strand a user:
a resend generates a *new* token and therefore a *new* key. The ledger never reports success for
an in-flight send, so no false delivery claim is possible.

**Scope honesty:** this is **real PostgreSQL semantics** (unique-index arbitration is what the
production engine relies on) but it is **not the production instance**; the prod DB was never
subjected to the race suite.

**STATUS** — **VERIFIED (local PostgreSQL 17.11)**. Prod-instance concurrency proof: **not
attempted (BLOCKED, deliberately)**.

---

## G. §12 Real migration path 0017 → 0018 on PostgreSQL

**WHAT** — The production upgrade path exercised with the real Alembic driver against a real
PostgreSQL cluster carrying legacy, pre-0018 data.

**WHERE** — `confit_pg_prod` (PostgreSQL 17.11, UTF8 / `C.UTF-8`), Alembic
`alembic/versions/0018_partner_onboarding_email_lifecycle.py`
(sha256 `2ab12926d73a377ac44cabc5ddca2e0d7ab8ed25b15fb40bd7f562c142bd1c8e` — unchanged across the
rebase, since the rebase had zero file overlap).

**HOW VERIFIED (sequence actually executed)**
1. Migration back to `0017_audit_before_after_request_id` with the real driver.
2. Legacy seed (`/tmp/seed0017.py`, raw SQL — the ORM cannot create users at 0017 because
   `registration_intent` does not exist yet): 4 users covering every role, `legacy-atelier` brand
   plus owner, 1 category, 1 product, 1 SKU, 1 refresh token, 1 audit log, 1 order.
3. Pre-migration census → `/tmp/pre0018_census.json`.
4. `alembic upgrade head` → `0018_partner_onboarding_email_lifecycle`.
5. Post-migration integrity checks (`/tmp/verify0018.py`), all passing.

**EVIDENCE**
- Census, user rows and brand ownership **byte-identical** before/after.
- `registration_intent` backfilled **4/4** — varchar, NOT NULL, server_default `'consumer'`.
- 5 new tables: `brand_members`, `email_change_requests`, `email_deliveries`, `invitations`,
  `partner_applications`.
- 3 partial unique indexes: `uq_partner_applications_user_pending` (status='pending'),
  `uq_invitations_pending_email_brand` (email, brand) WHERE pending,
  `uq_email_change_open_user` (user) WHERE `used_at IS NULL`.
- 12 foreign keys, 28 indexes.
- No destructive statement in the migration (no column drop, no data rewrite beyond the additive
  backfill).

**STATUS** — **VERIFIED (local PostgreSQL replica)**. **Prod remains at 0017** (Section K);
"works locally" is explicitly **not** counted as prod verification.

---

## H. §6 Email evidence levels

| Level | What was actually observed | STATUS |
|---|---|---|
| A — code path | `send_transactional` → `DeliveryResult{status, provider, message_id, error_class, attempts, delivery_id, idempotent_replay, accepted}`; ledger row on **every** attempt; unconfigured ⇒ `BLOCKED`; SMTP (starttls/ssl, retries) and Resend transports; SHA-256 recipient hashing only; 10 bilingual templates | **VERIFIED** |
| B — provider accepted | A real RFC 5321 conversation against a **local SMTP server** on the loopback interface, message captured and its link tokens extracted and redeemed through the API | **VERIFIED for the transport implementation; NOT third-party provider acceptance** |
| C — real mailbox receipt + redeem | — | **UNVERIFIED** (no third-party provider configured anywhere; production has zero email variables) |

**Consequence, stated plainly:** the deliverability claim that a real user's Gmail/Outlook/company
mailbox receives the verification or reset link is **UNVERIFIED**. Nothing in this report or the
code claims otherwise.

---

## I. §13/§14 Configuration consistency and fail-safe gates

**WHAT (13)** — One canonical email variable set, no undocumented aliases.

- Runtime canonical set (`core/config.py`): `EMAIL_PROVIDER`, `EMAIL_FROM_ADDRESS`,
  `EMAIL_REPLY_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
  `SMTP_TLS_MODE`, `RESEND_API_KEY`, `FRONTEND_BASE_URL`.
- **Drift found and fixed in this phase:** `docs/CONFIT_Production_Run_and_Environment_Guide.md`
  documented `SMTP_USER` / `SMTP_PASS` / `MAIL_FROM_NAME` — names the runtime does **not** read.
  A deployment following that guide would have left email silently unconfigured while believing it
  was configured. The guide now uses the canonical names only and points at
  `backend/.env.example §9` as the source of truth (`add627c`).
- `backend/.env.example §9` was already canonical; no alias was introduced anywhere (aliases are
  how drift survives).

**WHAT (14)** — Fail-safe behaviour, now directly tested:

| Failure mode | Required behaviour | Test |
|---|---|---|
| Provider unset | send-side endpoints 501 `FEATURE_NOT_CONFIGURED`; ledger records `BLOCKED`; `email-status` reports it | `test_verify_email_still_501_when_unconfigured`; `test_register_sends_verification_only_when_configured` |
| Provider set but `SMTP_HOST` missing | production refuses to boot, naming the variable | `test_production_boots_refuse_provider_without_smtp_host` |
| `SMTP_TLS_MODE=none` (cleartext credentials + body) | production refuses to boot | `test_production_boots_refuse_cleartext_smtp` **(new)** |
| `FRONTEND_BASE_URL` not `https://` (links built from it) | production refuses to boot; checked against `http://…`, bare host, `javascript:…` | `test_production_boots_refuse_non_https_link_base` **(new)** |
| Schema behind code | startup schema gate refuses to serve | `test_schema_drift_gate.py` |

**STATUS** — **VERIFIED (local)**; silent-success paths are structurally impossible for these
inputs (the process either refuses to start or answers an explicit 501/BLOCKED).

---

## J. §15 Deployment order and rollback readiness

**WHAT** — The required order is fixed and encoded in the hand-over instructions:

```
1. 0018 migration on the production DB         ← BLOCKED (owner credential)
2. email provider configured in Vercel         ← BLOCKED (zero email vars; BLOCKED)
3. deploy the branch (SHA recorded)            ← cannot start before 1–2
4. health + schema revision + startup gate
5. provider acceptance (level B)
6. mailbox receipt + redeem (level C)
7. partner onboarding in prod, invitation, B2B tenant access
8. rollback readiness confirmed before promotion
```

**Constraints honoured:** the 0018-dependent code will not be promoted while prod is at 0017 (the
deployed prod SHA `e1419d6` contains neither the migration nor the endpoints — confirmed by 404s
on `/auth/onboarding-state` and `/auth/email-status`); email functionality is not promoted without
a provider (its absence degrades safely to 501 + `BLOCKED`, never to a false success).

**Rollback:** the migration is additive and reversible (`alembic downgrade 0017_…` verified to be
reachable), the branch is a single self-contained history, and the previous prod deployment SHA is
recorded for instant rollback. Rollback has **not** been exercised in production (nothing was
promoted).

**STATUS** — Order **IMPLEMENTED/TESTED** (downgrade path verified locally); promotion **BLOCKED**.

---

## K. §4/§5/§16 Production blockers — re-verified in this phase

### K1. Production database at 0017 — upgrade BLOCKED
- **WHAT** — The production DB cannot be brought to 0018 with any credential available to this
  work stream.
- **HOW VERIFIED (fresh)** — `origin/main`'s alembic version directory ends at
  `0017_audit_before_after_request_id.py`; the production deployment runs a commit of `main`
  (`e1419d6`), so the deployed application's own head is 0017 and prod is at 0017.
- **EVIDENCE (earlier this phase)** — the upgrade attempt with the application runtime role
  `confit_app_rw` failed with `InsufficientPrivilege: must be owner of table users` (owner is
  `neondb_owner`); the provided `neondb_owner` DSN now returns
  `password authentication failed for user 'neondb_owner'` (rotated).
- **Actions deliberately NOT taken** — retrying the dead credential, ownership bypass, granting
  the runtime role ownership, rewriting the migration to dodge ownership.
- **STATUS** — **BLOCKED**. Requires an authorized owner credential (or an owner-run migration
  job) supplied by the project owner.

### K2. Production email — BLOCKED
- **WHAT** — Production cannot send any mail.
- **HOW VERIFIED (fresh, this phase)** — Vercel REST: **68 environment variables**, **zero**
  matching `SMTP`/`EMAIL`/`RESEND`/`MAIL`/`FRONTEND_BASE` (the intended email block is absent
  entirely, including `FRONTEND_BASE_URL`).
- **EVIDENCE** — `GET /v9/projects/prj_XaGsK8FP0dYc7yijAH58d1O0h1Vt/env` (2026-09-19) → email-ish
  keys: `NONE`.
- **STATUS** — **BLOCKED**. No provider was invented, no personal mailbox was substituted, no mock
  provider is claimed as success. Email is **not** marked VERIFIED.

### K3. Push / pull request — BLOCKED
- **HOW VERIFIED** — `git push --dry-run origin HEAD:refs/heads/fix/auth-registration-onboarding-email`
  → `fatal: could not read Username for 'https://github.com'`; no credential helper, no stored
  credentials, no `~/.netrc`, no SSH key material.
- **Consequence** — deliverable is a bundle + patch (`/home/user/auth-onboarding-email.{bundle,patch}`)
  plus `PUSH_INSTRUCTIONS.md`. **STATUS** — **BLOCKED**. A local branch is not a PR.

### K4. Production deployment state (fresh)
| Probe | Result |
|---|---|
| Latest production deployment SHA | `e1419d67e85db0242b58498cc91c9daddf6f4e2f`, state `READY` (the current `main`, not this branch) |
| `GET /api/v1/health` | `200` |
| `GET /api/v1/auth/me` (unauthenticated) | `401` |
| `GET /api/v1/auth/onboarding-state` | `404` — this branch is **not deployed** |
| `GET /api/v1/auth/email-status` | `404` — same |

---

## L. §7/§8/§9 Production lifecycle, invitation and 403 matrix — not run

**WHAT** — The three production end-to-end programmes required by the task cannot be executed,
because the branch is not deployed, the production database cannot be migrated, and production has
no email provider. They are reported as **NOT RUN — BLOCKED**, never as passed.

| # | Required prod proof | Status | Local equivalent actually achieved |
|---|---|---|---|
| 7 | register → intent → verify link → onboarding-state → login → landing; partner → application → admin approve → BrandProfile → `brand_owner` → `/b2b` → tenant scope | **BLOCKED** | Full path driven through the API on the local runtime, including real token redemption from a captured message; client-injected `role`/`brand_id`/`is_verified` had no effect |
| 8 | Invitation flow + negatives (reuse, wrong brand/role, expired, revoked, tampered) | **BLOCKED** | Test-covered: `test_invitation_escalation_and_abuse_paths_are_refused`, `test_expired_invitation_is_refused`, `test_invitation_cannot_cross_tenants`, `test_invited_member_cannot_touch_another_brands_tenant` |
| 9 | B2B 403 matrix: consumer (no / pending / rejected application), brand_owner/manager/staff, foreign tenant, suspended, anonymous | **BLOCKED** | Covered locally by the lifecycle matrix (`test_partner_application_is_pending_until_an_admin_approves`, `test_rejected_application_leaves_the_account_unprivileged_and_retryable`, tenant negatives); the deployed prod build independently shows a real 403 ROLE RESTRICTION (screenshot), i.e. the control exists in prod for the *old* code path |

No fake state changes were performed to make any of these look complete.

---

## M. §10 Gap triage

| Gap | Decision | Reasoning |
|---|---|---|
| Browser E2E (Playwright/Cypress) | **FOLLOW-UP** (not added) | The standing directive forbids adding a browser framework merely to raise feature count. Backend + frontend suites already assert the flows at the API and component level; a browser runner is a tooling decision for the team, and it would not change the prod blockers. |
| Parallel races on PostgreSQL | **DONE** | Section F: 5 races, 3 real defects fixed. |
| Social signup intent | **FOLLOW-UP** | OAuth clients are configurable (`GOOGLE_/APPLE_/FACEBOOK_OAUTH_*`) but no provider credential exists in production. Social signup yields a consumer account; the partner path is still reachable server-side via the verified application flow, so this is not release-blocking. |
| Deliverability tooling (SPF/DKIM/DMARC, bounce handling) | **FOLLOW-UP** | Requires a chosen provider plus DNS control. Cannot be implemented before a provider exists; the ledger already records per-attempt outcomes, which is the prerequisite. |
| Backfill policy for legacy accounts' `is_verified` | **OUT OF SCOPE (needs product approval)** | No silent backfill is performed (Section E). Any policy must be an explicit, documented, product-approved script — not a side effect of this work. |
| Old-address confirmation on email change | **RESOLVED BY DESIGN** | The confirmation link is delivered to the **address being added** (possession proven), the **old** address receives a security notice, and existing refresh tokens are revoked on change. Optional hardening (an old-address veto window) is **FOLLOW-UP**. |

---

## N. §17 Gates 1–15

| # | Gate | Result |
|---|---|---|
| 1 | Rebased on latest `main` | **PASS** — fresh anonymous fetch; `origin/main` = `e1419d6`; branch contains it; rebase replay clean; 20 commits |
| 2 | Backend suite | **PASS** — `1173 passed, 12 skipped, 0 failed, 0 errors` in 251.68 s, nothing excluded (`/home/user/phase7_final_backend.log`) |
| 3 | Frontend tests / typecheck / build | **PASS** — vitest 20 files / 119 tests; `tsc --noEmit` clean; `npm run build` green (`index-M9j1Zfnq.js`, 482.19 kB) |
| 4 | 0018 applied on the **actual prod DB** | **BLOCKED** — owner credential unavailable; prod at 0017 |
| 5 | Email provider genuinely configured (prod) | **BLOCKED** — 0 of 68 Vercel vars are email-related |
| 6 | Provider accepted ≥1 verification email (third-party) | **UNVERIFIED** — only a local RFC 5321 transport proof exists |
| 7 | Real verification email redeemed (real mailbox) | **UNVERIFIED** |
| 8 | Real reset email redeemed (real mailbox) | **UNVERIFIED** |
| 9 | Partner approval in prod | **BLOCKED** (not deployed) |
| 10 | Invitation + tenant access in prod | **BLOCKED** (not deployed) |
| 11 | Consumer blocked from privileged B2B in prod | **BLOCKED** for this branch's workflow; the control itself exists in the deployed build (real 403) |
| 12 | No role escalation via client input | **PASS (local)** — tests + live smoke; prod re-verification **BLOCKED** |
| 13 | No cross-tenant access | **PASS (local)** — tenant negatives green |
| 14 | No false email-success claims | **PASS** — 501 + `BLOCKED` ledger + honest `email-status`; verified by tests and live probe |
| 15 | Deployment SHA verified | **BLOCKED** — production runs `e1419d6` (main); this branch cannot be deployed, so no SHA of this work exists in production |

### Verification totals in this phase
| Gate | Command | Result |
|---|---|---|
| Backend (all, serial, nothing excluded) | `PYTHONPATH=. python3 -m pytest backend/tests -q` | 1173 passed / 0 failed / 12 skipped |
| PostgreSQL races | `CONFIT_PG_DSN=…confit_pg_race pytest backend/tests/test_pg_concurrency_lifecycle.py -q` | 5 passed |
| Targeted batch (races + email + lifecycle) | `pytest test_pg_concurrency_lifecycle.py test_email_delivery.py test_auth_onboarding_lifecycle.py -q` | 39 passed |
| Frontend | `npx vitest run` / `npx tsc --noEmit` / `npm run build` | 119 passed / clean / built |
| Migration on PostgreSQL | `alembic upgrade head` + `/tmp/verify0018.py` | all integrity checks pass |
| Patch reproduction | `git am --3way` on clean `origin/main` | 20 commits, identical tree |

*Methodological note:* an earlier full-suite run in this phase showed 8 failures that were **not**
regressions — two pytest processes of mine ran concurrently and collided on the shared SQLite test
file (`backend/data/confit_test.db`). The final numbers above come from a single serial run of the
rebased tree with nothing else touching the database.

---

## O. Verdict

> ## NO-GO — BLOCKED

**Why this verdict and not the other two**

- `PRODUCTION VERIFIED` is unreachable on the evidence: the production database is still at 0017,
  production has no email provider, the branch is not deployed, no third-party provider has
  accepted a message, no real mailbox has received or redeemed a link, and no pull request exists.
- `PARTIALLY VERIFIED` would overstate the production position. Nothing from this work stream is in
  production at all; what exists is a locally verified, release-ready branch plus two external
  prerequisites that only the project owner can satisfy.

**What is genuinely done (and can be reviewed today)**
1. A 20-commit branch rebased onto current `main`, clean, with a reproducible bundle and patch
   (verified by tree-identity through `git am --3way`).
2. All three lifecycles implemented with server-side authorization only, negative/security tests,
   structured observability with request IDs and no secrets, rate limiting, DB-enforced uniqueness
   and additive migrations.
3. Five real PostgreSQL races proven, **three genuine defects found and fixed** — including a
   duplicate-send bug that really did put two copies of a message on the wire.
4. The 0017→0018 upgrade proven non-destructive on real PostgreSQL with legacy data intact.
5. Configuration drift eliminated (documented variables now match the ones the runtime reads) and
   the fail-safe gates for provider/TLS/link-base are directly tested.

**What the owner must supply to unblock (in this order)**
1. An authorized **owner-role** database credential for the production Neon project (or an
   owner-run migration job) so 0018 can be applied — then prod revision, schema, tables, indexes,
   FKs, startup gate and health must be re-checked.
2. A **real email provider** configuration in the production environment (canonical variables only:
   `EMAIL_PROVIDER`, `EMAIL_FROM_ADDRESS`, `SMTP_*` or `RESEND_API_KEY`, `FRONTEND_BASE_URL=https://…`),
   followed by a provider-acceptance test and a real mailbox redeem.
3. **GitHub push credentials** (a complete PAT for `OmarAhmed-123`, or a configured credential
   helper) so the branch can become a pull request — until then the bundle/patch is the delivery.

**Rollback position if 1–2 are satisfied and something goes wrong:** the migration is additive and
reversible, the previous production deployment SHA is recorded, and no destructive change was made
to any production object.

*No claim in this report is stronger than its evidence. Where the evidence stops, the report says
BLOCKED or UNVERIFIED.*
