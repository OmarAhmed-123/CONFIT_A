# CONFIT_A — Auth / Registration / Onboarding / Email
## Final Release Handoff — Production Activation Attempt (Evidence Report)

**Date:** 2026-09-19
**Branch:** `fix/auth-registration-onboarding-email`
**Actual HEAD:** `7654eb4de77d30c64aeac8c3b6f878b03178f4d6` (tree `b51858fccbd7749088cfc83e6571a8d320c550e6`)
**Actual base (`origin/main`):** `10d80a12f2dd364351275ebdfe4cc2850d157b84` ("Merge PR #116: Wire try-on UI to backend capability registry") — **fully contained**
**Actual commit count:** **26** · **changed files:** 63 · **working tree:** clean
**Production:** `https://confit-a.vercel.app/` running `10d80a1…` (main) — **not** this branch

**Convention:** WHAT / WHERE / HOW VERIFIED / EVIDENCE / STATUS.
Evidence levels stay independent: **A** = code + executable test/runtime, **B** = real third-party
provider accepted the message, **C** = real mailbox received **and** the link was redeemed.

---

## 1. Executive result

> ## NO-GO — BLOCKED

All three external release prerequisites were re-checked against authorized surfaces only and
**all three are still absent** (§5, §6, §14). No production migration ran, no email was sent, no PR
exists, nothing was deployed, and the controlled mailbox was not contacted. No source file was
modified for any reason other than the release-integration step the phase itself mandates: main
advanced and **overlapped this branch**, so the branch was rebased (§3) and the affected gates were
re-run (§7).

Three things are worth stating plainly:

1. **Main advanced twice more and overlapped again** — `f024807` → `10d80a1` (PR #116) overlapped in
   `frontend/src/services/apiServices.ts`. Resolved by rebase; the merge was auto-clean because the
   two changes sit in different service objects.
2. **The original defect is still live on main today** — the dead-end `403 · Access Restricted` page
   is present on `origin/main` and absent from this branch (§4). Production's deployed SHA is main.
3. **The environment was reset between phases** (Python packages, `node_modules`, and the local
   PostgreSQL replica are not part of workspace snapshots). Everything reported below was re-executed
   from a freshly installed environment at the current tip, except the PostgreSQL-gated proofs, which
   are handled honestly in §11.

---

## 2. Actual HEAD · 3. Base SHA · 4. Commit count · 5. Tree hash

| Item | WHAT / EVIDENCE | STATUS |
|---|---|---|
| HEAD | `7654eb4de77d30c64aeac8c3b6f878b03178f4d6` | VERIFIED (actual git state) |
| Base | `10d80a12f2dd364351275ebdfe4cc2850d157b84`; `git merge-base HEAD origin/main` = same ⇒ main fully contained, no divergence | VERIFIED |
| Commit count | `git rev-list --count origin/main..HEAD` → **26** | VERIFIED |
| Tree hash | `git rev-parse HEAD^{tree}` → `b51858fccbd7749088cfc83e6571a8d320c550e6` | VERIFIED |
| Branch diff | `git diff --stat origin/main...HEAD` → **63 files, +10228 / −412** | VERIFIED |
| Working tree | `git status --short` → empty | VERIFIED |

**Bookkeeping chain reconciled (the phase flagged 24 → 25 → 26):** all three numbers were correct at
their moments. The differences are **documentation commits only**, proven two ways:

- `git diff --stat 1a2ee6d..HEAD` at the previous phase → the report file only; and after this phase's
  rebase, `git diff --numstat` of the branch patch is **+10228 / −412** versus the earlier
  **+9894 / −412** — the **deletions are byte-for-byte identical** and the insertion delta (334 lines)
  is exactly the new report document. The only file added to the patch is this report; no source file
  entered or left the change set.
- File-set diff of the branch patch before/after the rebase:
  `diff <(git diff --name-only f024807...1a2ee6d | sort) <(git diff --name-only 10d80a1...HEAD | sort)`
  → a single added line, the new report.

**No source file differs from the previously verified code tree.** Explicitly re-checked file by file
(all `IDENTICAL`): `RoleGuard.tsx`, `auth_service.py`, `models/user.py`, `core/config.py`,
`brand_controller.py`, `email_service.py`, `partner_service.py`, `user_repository.py`,
`AppRoutes.tsx`, `AuthModal.tsx`. Additionally `git diff --stat 1a2ee6d HEAD -- backend/` → **empty**,
i.e. the entire backend is byte-identical to the tree that produced 1185 passing tests and the
PostgreSQL proofs.

---

## 3. Current main and the overlap (release integration)

`origin/main` moved from `f024807` to **`10d80a1`** ("Merge PR #116: Wire try-on UI to backend
capability registry", commit `1e83ced`), touching 5 frontend files.

**Overlap with this branch:** exactly one file — `frontend/src/services/apiServices.ts`.

**Resolution:** `git rebase origin/main` completed with **no conflicts** — main's additions
(`TryOnProductCapability`, `TryOnCapabilitiesResponse` interfaces and
`tryOnService.getCapabilities()` calling `/try-on/capabilities`) live in the `tryOnService` object,
while this branch's additions live in `authService`. Both verified present after the rebase:

| Check | Evidence | Status |
|---|---|---|
| Main's PR #116 content retained | `TryOnCapabilitiesResponse` ×2, `getCapabilities` ×2, `try-on/capabilities` call ×1 in `apiServices.ts` | VERIFIED |
| This branch's lifecycle endpoints retained | 6 refs to `onboarding-state` / `email-status` / `email-change` / `verify-email` | VERIFIED |
| Auth-critical files unchanged by the rebase | byte-identical to the gated tree (§2) | VERIFIED |
| Backend untouched by the rebase | `git diff 1a2ee6d HEAD -- backend/` empty | VERIFIED |

---

## 4. Original defect — final regression control

**WHAT** — a consumer visiting `/b2b` must not be granted privilege and must not be a dead end; the
page must present the state the backend actually reports, with a legitimate next step.

**HOW VERIFIED** (checks A–F executed against the current tree):

| Check | Evidence | Status |
|---|---|---|
| **A.** main's public partner/demo experience preserved | `PartnerRequestDemoForm` 2 refs (mounted once); `brandService.requestDemo` present; `/b2b/request-demo` endpoint present | VERIFIED |
| **B.** authenticated consumer gate is state-aware | `accountState` + `partner_access` drive the branch (`user.partner_access ?? state?.partner_access`) | VERIFIED |
| **C.** backend state is authoritative | the frontend reads the server's onboarding payload; it does not compute state | VERIFIED |
| **D.** server-derived next action rendered | `SUSPENDED` → suspension; `pending` → `/partner/status`; `rejected` → `/partner/apply`; `EMAIL_VERIFICATION_REQUIRED` / `is_verified === false` → `/verify-email`; none → `/partner/apply` | VERIFIED |
| **E.** no frontend role escalation | `hasRole = !allowedRoles \|\| allowedRoles.includes(userRole) \|\| userRole === 'admin'` — authorization is unchanged; the SPA only decides what to render | VERIFIED |
| **F.** brand roles still role-authorized | `BRAND_ROLES = ['brand_owner','brand_manager','brand_staff']` | VERIFIED |

**The defect itself:** the dead-end markers (`Switch Account / Re-authenticate`,
`Return to Consumer Storefront`) occur **0 times on this branch** and **1 time on `origin/main`**.
Production runs main, so **the original defect is still live in production and fixed only here**.

**STATUS** — fix VERIFIED (local); the production regression test of the new behaviour **BLOCKED**.

---

## 5. Blocker A — production database

**HOW VERIFIED (authorized surfaces only, re-checked this phase):**

- Vercel environment: **68 variables**; pattern scan `OWNER|MIGRAT|ALEMBIC|NEON` → **NONE**. The only
  database variable is the runtime `DATABASE_URL`.
- Vercel build command is frontend-only; the serverless entrypoint imports the ASGI app; **no Alembic
  invocation exists in the deployment surface**.
- CI's `postgres-migrations` job runs a **throwaway `postgres:17` service container with a local
  password** — it consumes no project secret and cannot reach production.
- The previously supplied owner credential is **rotated**; per the standing constraint it was
  **not retried**.

**STATUS** — **BLOCKED**. No ownership change, no permission grant, no schema-gate disabled, no
migration rewrite, no data dropped, no fabricated success.

## 6. Blocker B — production email provider

**EVIDENCE (fresh)** — Vercel inventory: **68 variables**; `EMAIL|SMTP|RESEND|MAIL|FRONTEND_BASE`
→ **NONE** (including `FRONTEND_BASE_URL`, which every emailed link requires).

**STATUS** — **BLOCKED**. No localhost SMTP, loopback sink, mock provider or MCP path was substituted;
no personal credential was used; no secret was printed or committed.

## 7. GitHub (Blocker C) · 8. CI · 9. Merge

- **Push** — `git push --dry-run origin HEAD:refs/heads/probe` →
  `fatal: could not read Username for 'https://github.com'`. Surfaces re-checked and absent:
  `credential.helper`, `~/.git-credentials`, `~/.netrc`, no key material in `~/.ssh` (only
  `known_hosts`), no `GH_*`/`GITHUB_*` token env, no `gh` CLI.
- **STATUS** — **BLOCKED. No PR number, no PR URL, no remote branch.** None is fabricated.
- **CI result** — CI triggers on push/PR; with no push there is **no GitHub CI run**. Every job was
  reproduced locally at the current tip (§7 table below).
- **Merge SHA** — **BLOCKED (nothing merged).**

### Gate re-run at the current tip (fresh environment)

| CI job / gate | Command | Result |
|---|---|---|
| backend suite | `PYTHONPATH=. pytest backend/tests -q` | **1185 passed / 0 failed / 13 skipped** (235 s) |
| frontend tests (incl. main's new try-on tests) | `npx vitest run` | **122 passed / 21 files** |
| typecheck | `npx tsc --noEmit` | clean |
| production build | `npm run build` | green (`index-BjlTfs1g.js`, 491.26 kB) |
| secret scanning | repository's own gitleaks rules replicated locally | **clean** (63 files) |
| patch reproduction | `git am --3way` on clean `origin/main` | 26 commits, **tree identical** |

*Honest note:* Python packages, `node_modules` and the local PostgreSQL replica do **not** persist
between phases; all of the above was therefore re-installed and re-executed from scratch at the
current tip rather than carried over.

---

## 10. Production deployment SHA

- **EVIDENCE (fresh)** — production deployment `10d80a12f2dd364351275ebdfe4cc2850d157b84`,
  state `READY`, ref `main`, created `2026-09-19T18:36:34Z`.
- **ENDPOINT EVIDENCE** — `/api/v1/health` → **200**; `/api/v1/auth/onboarding-state` → **404**;
  `/api/v1/auth/email-status` → **404** ⇒ this branch is demonstrably **not deployed**.
- **STATUS** — production VERIFIED as running main; this work VERIFIED as absent from production.

## 11. Production DB revision and migration evidence

- **EVIDENCE** — main's alembic directory ends at `0017_audit_before_after_request_id.py` and the
  production deployment runs a main commit ⇒ deployed schema ceiling **0017**.
- **LOCAL PROOF (real PostgreSQL, executed in earlier phases against a byte-identical backend)** —
  0017 → legacy seed → `upgrade head` → 0018: census, users and brand ownership preserved
  byte-identically; `registration_intent` backfilled 4/4; 5 new tables; 3 partial unique indexes;
  12 FKs; 28 indexes. The CI chain gate additionally proves base → head → base → head on a fresh
  database.
- **IMPORTANT LIMITATION (stated, not hidden)** — the local PostgreSQL replica and its data directory
  do not survive the environment reset, so in this phase's suite run the **PostgreSQL-gated tests
  skipped** (`CONFIT_PG_DSN` unset; 13 skipped include them). Those proofs stand for the **current
  code** because the entire backend is byte-identical to the tree that produced them
  (`git diff 1a2ee6d HEAD -- backend/` → empty), but they were **not re-executed in this phase**.
- **STATUS** — local proof VERIFIED (byte-identical code); production **BLOCKED**.

## 12. Email provider · 13. Provider acceptance (B) · 14. Mailbox (C)

- **Provider** — none configured (§6). **STATUS: BLOCKED.**
- **B (third-party provider acceptance)** — the only level-B transport evidence in existence is the
  suite's loopback RFC 5321 server. **Zero messages were sent this phase.** **STATUS: UNVERIFIED** —
  for verification, reset and invitation mail alike.
- **C (real mailbox)** — the controlled recipient `omarsafealden@gmail.com` was **not contacted**:
  no provider exists to deliver through and no mailbox credential exists to read it. Zero messages
  sent (no marketing, no bulk, no repeats). **Hygiene:** `grep -rn "omarsafealden"` over the repo
  returns only pre-existing documents referencing project-owned Vercel/Modal URLs; the address
  appears **nowhere** in application source, configuration defaults, or the branch diff.
  **STATUS: UNVERIFIED.**

### Evidence levels per email type

| Message type | A | B | C |
|---|---|---|---|
| Verification | **VERIFIED (local)** — 17 lifecycle + 21 delivery tests, plus the PostgreSQL flow completing redemption from a captured token | UNVERIFIED | UNVERIFIED |
| Password reset | **VERIFIED (local)** — one-time link, replay/expiry negatives, no-leak on transport failure, explicit 501 when unconfigured | UNVERIFIED | UNVERIFIED |
| Invitation | **VERIFIED (local)** — accept path plus escalation/expiry/cross-tenant/foreign-tenant negatives | UNVERIFIED | UNVERIFIED |

## 15–20. Production flows (registration, verification, reset, partner, invitation, B2B)

**WHAT** — the complete production verification programme the phase specifies.
**HOW VERIFIED** — it **cannot** be executed: it requires a deployed branch (blocked at push/merge),
a migrated database (blocked at §5) and a real provider (blocked at §6).
**STATUS** — **NOT RUN — BLOCKED**, with the local equivalents named above and in §3. No state was
faked to make any flow appear complete.

## 21. RBAC · 22. Tenant isolation · 23. Negative security tests

- **RBAC** — unchanged and re-verified: role guards, admin step-up, 19 `@limiter.limit` decorators,
  admin-only approval. This phase modified no authorization control.
- **Tenant isolation** — cross-tenant and foreign-tenant denial tests pass at the tip.
- **Negatives (local)** — injected `role`/`brand_id`/`is_verified` ignored (account stays `consumer`,
  `is_verified=false`); invitation role/brand override, expiry, replay, cross-tenant refused; CSRF
  enforced (403 `CSRF_TOKEN_MISMATCH`); no endpoint accepts a redirect target; duplicate application
  and duplicate acceptance blocked by partial unique indexes + PostgreSQL races.
- **Production negatives** — **BLOCKED** (nothing deployed).
- **Secret leakage** — the branch's 63 changed files scanned with the repository's own gitleaks rules
  (custom DSN/Modal/Vercel/Groq/Gemini rules plus standard token classes): **clean**.

## 24. Email reliability

- Claim-before-send (one provider transmission per key), terminal `unknown`, bounded stale-claim
  resolver, no retry-forever, no duplicate-prone automatic resend: all preserved and unmodified this
  phase. `unknown` is never converted to `succeeded`.
- **STATUS** — VERIFIED (local, on the byte-identical backend); production **BLOCKED**.

## 25. Remaining GAPs

Partner-notification replay after `unknown` (documented FOLLOW-UP); deliverability tooling
(SPF/DKIM/DMARC — needs a provider); social signup intent (no OAuth credential in production);
legacy `is_verified` (**PENDING PRODUCT DECISION** — no silent change, no backfill); real-browser E2E
(UNVERIFIED; no browser framework added merely for coverage); quote-style churn in two merged
frontend files (cosmetic, documented).

## 26. Remaining UNVERIFIED

Third-party provider acceptance (B) and real mailbox receipt + redemption (C) for all three email
types; GitHub CI for this branch; real-browser E2E; production behaviour of every new endpoint;
PostgreSQL-gated tests **not re-executed in this phase** (§11 limitation).

## 27. Remaining BLOCKED

1. Production migration 0018 — no authorized owner path.
2. Production email provider — no configuration, no credential.
3. Push / PR / CI / merge — no GitHub credential.
4. The whole production programme: deployment SHA, schema 0018, registration, verification mail,
   reset, partner approval, invitation, tenant isolation, B2B matrix, original-screenshot regression.

## 28. Rollback

- **Migration** — 0018 additive and reversible; both directions proven on real PostgreSQL and by the
  CI chain gate. No populated column dropped; no data rewritten beyond the additive backfill.
- **Application** — Vercel instant rollback to a recorded SHA (`10d80a1…`, `f024807b…`, `463f81cc…`).
- **Email** — without a provider the send-side endpoints answer `501 FEATURE_NOT_CONFIGURED` and the
  ledger records `BLOCKED`; the claim/resolver never transmits on its own, so a rollback cannot strand
  a half-sent message.
- **Ordering honoured** — 0018-dependent code is not promoted before the migration; the deployed SHA
  contains none of this work (404 evidence in §10).

## 29. BRD traceability

| BRD requirement | Implementation | Test | Production evidence | Status |
|---|---|---|---|---|
| Consumer lifecycle (register → intent → verify → onboarding → session → portal) | `onboarding_service`, `RegistrationIntent`, auth endpoints, SPA routes | 17 lifecycle tests | none | A VERIFIED / prod BLOCKED |
| Password recovery, single-use token | `token_service`, forgot/reset endpoints | one-time, replay, expiry, no-leak | none | A VERIFIED / prod BLOCKED |
| Partner lifecycle with server-side provisioning | `partner_service` (apply/review/provision/invite/accept) | lifecycle + PostgreSQL races | none | A VERIFIED / prod BLOCKED |
| **Intent ≠ authorization** | `user_repository.create` (`is_verified=False` unconditional), role guards; `registration_intent` typing retained (no `role` field reintroduced) | injected-role tests | none | A VERIFIED |
| Real email → ledger, never fake success | `email_service` transports + ledger + 501 + claim-before-send + resolver | 21 delivery tests | loopback SMTP only | A VERIFIED / B,C UNVERIFIED |
| MCP excluded from the transactional path | `EMAIL_PROVIDER_MCP_EVALUATION_20260919.md` — decision unchanged, not reversed | n/a | n/a | VERIFIED (documented) |
| No secrets in repo | branch-wide scan with the repo's own gitleaks rules | this phase | n/a | VERIFIED (clean) |
| Quality bar (negatives, correlation IDs, rate limiting, redirect allowlisting, DB uniqueness, additive migrations) | 19 limiters, request-id middleware, audit trail, partial uniques, 0018 | suite + chain gate | n/a | A VERIFIED |

## 30. Final verdict

> ## NO-GO — BLOCKED

**Why not `PRODUCTION VERIFIED`** — production is at schema 0017, runs `10d80a1…` (main), has no
email provider, and this work has no push, no PR, no CI run, no merge and no deployment SHA.

**Why not `PARTIALLY VERIFIED`** — no production gate passes; nothing from this work is in production.

**What stands as complete and reviewable**

1. A **26-commit** branch integrated with the newest main (`10d80a1`), clean tree, reproducible
   artifacts (`git am --3way` reproduces an **identical tree**).
2. Fresh-environment gates at the current tip: backend **1185 passed / 0 failed**, frontend
   **122 passed**, typecheck clean, build green, secret scan clean.
3. Backend **byte-identical** to the tree that produced the PostgreSQL concurrency, crash-recovery
   and 0017→0018 migration proofs.
4. The original `/b2b` dead end is replaced here and **still ships on main** — stated with evidence
   rather than assumed.
5. This phase: main's overlap handled without losing either side, and the 24/25/26 commit bookkeeping
   chain reconciled with proof that every delta was documentation-only.

**To unblock — in the required order**

1. Authorized **owner-run** production migration (credential or owner-executed `alembic upgrade head`),
   then verify revision, tables, indexes, FKs, existing data, schema gate and health.
2. Real **email provider** configured with canonical variables only (`EMAIL_PROVIDER`,
   `EMAIL_FROM_ADDRESS`, `EMAIL_REPLY_TO`, `SMTP_*` or `RESEND_API_KEY`,
   `FRONTEND_BASE_URL=https://confit-a.vercel.app`), then provider acceptance (B) and mailbox
   redemption (C).
3. **GitHub push credentials** so the branch becomes a PR and CI runs before any merge.

*Nothing in this report is stronger than its evidence. Where the evidence stops, it says BLOCKED or
UNVERIFIED — including the PostgreSQL tests that this phase could not re-execute.*
