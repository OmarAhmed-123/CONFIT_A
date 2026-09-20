# CONFIT_A — Auth / Registration / Onboarding / Email
## Production Activation Attempt — Final Evidence Report

**Date:** 2026-09-19
**Branch:** `fix/auth-registration-onboarding-email` @ `68382ca3fcd1c2447b2721ec5484ab6e30fed310`
**Integrated base:** `origin/main` @ `f024807b4a6aaa2cc3767827eae632e891f0821c`
**Production:** `https://confit-a.vercel.app/` running `f024807b…` (main) — **not** this branch
**Frozen handoff this phase resumed from:** `f68284d6747281d566238892801f7c4372446169`

**Reporting convention:** WHAT / WHERE / HOW VERIFIED / EVIDENCE / STATUS.
Evidence levels kept strictly apart: **A** = code/test, **B** = real third-party provider accepted,
**C** = real mailbox received **and** the link was redeemed.

---

## 1. Executive result

> ## NO-GO — BLOCKED

The three external release prerequisites were re-tested against authorized surfaces only, and
**all three are still absent** (§11, §25, §26). No email was sent, no production migration ran, no
PR exists, and nothing was deployed. Per the phase rule, no artificial coding phase was invented —
the only work performed was the **mandatory release-integration step the phase itself specifies**,
because `origin/main` advanced and now **overlaps this branch** (§3).

The significant engineering event of this phase is that overlap: main's PRs #113/#114/#115 touched
five files this branch also modifies — including `RoleGuard.tsx`, the file at the centre of the
original 403 defect. A careful rebase was performed, both sides were preserved, and **main still
contains the original dead-end 403 page that this branch replaces** (evidence in §3.3).

---

## 2. Branch SHA

- **WHAT** — the deliverable branch, after integration with current main.
- **EVIDENCE** — `68382ca3fcd1c2447b2721ec5484ab6e30fed310`, **24 commits** ahead of
  `origin/main`, working tree clean, `git merge-base HEAD origin/main` = `f024807` (main fully contained).
  PR-facing diff (`git diff origin/main..HEAD`): **61 files, +9555 / −412**.
- **STATUS** — **VERIFIED (local)**; not pushed.

## 3. Main SHA and the overlap event (release integration)

**3.1 Main moved twice while the work was frozen**

| When | `origin/main` | Content |
|---|---|---|
| Frozen handoff | `463f81cc…` | PR #112 |
| This phase (start) | `f024807b…` | PRs #113 "Close targeted backend product capability gaps", #114 "Hotfix partner leads without schema drift", #115 "Fix partner lead IP hash storage length" |

**3.2 Overlap — this time it was NOT empty**

`comm -12` of main's changed files and this branch's changed files (both vs `463f81c`):

```
backend/app/controllers/brand_controller.py
backend/app/core/config.py
backend/app/models/user.py
frontend/src/components/auth/RoleGuard.tsx
frontend/src/services/apiServices.ts
```

The earlier phase recorded *zero* overlap; that is no longer true, so §2's triggered path
(inspect delta → check overlap → rebase safely → re-run affected gates) was executed in full.

**3.3 What main had changed, and the resolution**

| File | Main's change | This branch's change | Resolution (both preserved) |
|---|---|---|---|
| `frontend/src/components/auth/RoleGuard.tsx` | Added a `PartnerRequestDemoForm` lead-capture component and mounted it on the public partner page — **and left the original dead-end 403 intact** | Replaced the dead-end with the backend-driven state machine (verify / apply / pending / rejected / suspended, each with the real next action) | Kept the state machine **and** inserted main's demo form at main's mount point. Verified: `PartnerRequestDemoForm` present (2 refs), state branches present (2 refs) |
| `frontend/src/services/apiServices.ts` | `brandService.requestDemo`, stylist and consumer additions; `register` still typed `role?: string` | New lifecycle endpoints (`onboarding-state`, `email-status`, `verify-email*`, `email-change*`); `registration_intent` replacing `role` | Kept main's additions (verified: `requestDemo` present) + the branch's endpoints and the `registration_intent` typing — no caller anywhere sends `role` (checked `authStore`, `AuthModal`), so the security-correct typing stands |
| `backend/app/core/config.py` | Added `PARTNER_LEAD_NOTIFY_EMAIL` | Added the canonical email block (`EMAIL_*`, `SMTP_*`, `RESEND_API_KEY`, `FRONTEND_BASE_URL`, claim-staleness) | Both kept |
| `backend/app/controllers/brand_controller.py` | Added `/brand/request-demo`, `/b2b/request-demo` + imports | Added invitation and partner-application endpoints | Both kept (import-order conflict resolved to upstream's ordering; `request_partner_demo` verified present) |
| `backend/app/models/user.py` | Whitespace only | Domain model: intents, applications, invitations, memberships, delivery ledger, `EmailDeliveryStatus.UNKNOWN` | Branch content kept |

**3.4 Finding worth stating plainly:** the original defect this whole work stream exists to fix —
a consumer hitting `/b2b` and landing on a dead-end `403 · Access Restricted` page with only
"return to storefront" — **is still present on `main` today** (main's `RoleGuard.tsx`, section 3 of
the guard, lines ~375–414). It is fixed only on this branch.

**3.5 Post-merge verification** — `tsc --noEmit` clean; `vitest run` 21 files / 121 tests passed;
`npm run build` green (`index-0shMftHS.js`, 489.02 kB); backend suite 1185 passed / 0 failed;
migration chain gate PASS; CI's PostgreSQL migration tests 39 passed; PostgreSQL concurrency +
recovery suite 6 passed. Detail in §24.

**3.6 Known cosmetic limitation of the PR diff** — main's newly written `RoleGuard`/`apiServices`
code uses double quotes while the repository's prevailing style is single quotes. The rebase
preserved both, so those two files show quote-style churn alongside the semantic changes. No
behavioural impact; flagged so a reviewer is not surprised by the line count.

## 4. PR URL, 5. PR number

- **EVIDENCE** — `git push --dry-run origin HEAD:refs/heads/probe-credential-check` →
  `fatal: could not read Username for 'https://github.com'`. Re-checked surfaces, all absent:
  `credential.helper`, `~/.git-credentials`, `~/.netrc`, `~/.ssh` (empty), `GH_*`/`GITHUB_*` env,
  no `gh` CLI.
- **STATUS** — **BLOCKED**. **No PR URL and no PR number exist.** None is fabricated.

## 6. CI status

- **WHERE** — `.github/workflows/ci.yml` (`backend`, `postgres-migrations`, `production-parity`, `frontend`) + gitleaks workflows.
- **STATUS** — **GitHub CI UNVERIFIED: no push ⇒ no run.** Every job CI would execute was reproduced
  locally on the merged tree (§24). No test was weakened, skipped or deleted to achieve green.

## 7. Merge SHA

- **STATUS** — **BLOCKED (no merge performed).** Nothing was merged anywhere; production still runs
  main.

## 8. Production deployment SHA

- **EVIDENCE (fresh)** — `f024807b4a6aaa2cc3767827eae632e891f0821c`, state `READY`, ref `main`,
  created `2026-09-19T18:12:47Z`.
- **Endpoints (fresh)** — `/api/v1/health` → **200**; `/api/v1/auth/onboarding-state` → **404**;
  `/api/v1/auth/email-status` → **404** ⇒ this branch is demonstrably not deployed.
- **STATUS** — production **VERIFIED as running main**; this work **VERIFIED as absent** from production.

## 9. Production DB revision

- **EVIDENCE** — main's alembic directory ends at `0017_audit_before_after_request_id.py`; the
  production deployment runs a main commit ⇒ the deployed schema ceiling is **0017**.
- **STATUS** — production at **0017**; 0018 **BLOCKED** (§10).

## 10. Migration evidence

- **WHAT** — whether production can be migrated.
- **HOW VERIFIED (all legitimate surfaces inspected this phase)**
  - `.github/workflows/ci.yml` → `postgres-migrations` runs against a **throwaway `postgres:17`
    service container with a local password** (`CI_PG_PASSWORD`); it consumes **no** repository or
    environment secret and cannot reach production.
  - `vercel.json` → build command is frontend-only (`npm --prefix frontend ci && … run build`);
    `api/index.py` imports the ASGI app; **no Alembic invocation exists anywhere in the deployment
    surface**.
  - Vercel environment inventory (decrypt-checked) → only the runtime `DATABASE_URL`; **no owner
    DSN, no `NEON_*`, no `MIGRATION_*`, no `ALEMBIC_*`**.
  - The previously supplied owner credential is rotated; per standing constraint it was **not retried**.
- **STATUS** — **BLOCKED — authorized production migration access unavailable.** No ownership
  bypass, no permission/ownership change, no gate disabled, no migration rewrite, no fabricated success.

## 11. Email provider

- **EVIDENCE (fresh)** — Vercel project env inventory: **68 variables**, and a pattern scan for
  `EMAIL|SMTP|RESEND|MAIL|FRONTEND_BASE|OWNER|MIGRAT|ALEMBIC|NEON` returns **NONE**.
- **STATUS** — **BLOCKED**. No provider was invented; no personal mailbox was substituted; no
  localhost SMTP was presented as production; no secret was printed or committed.

## 12. Provider acceptance evidence (level B)

- **EVIDENCE** — the only level-B transport evidence in existence is a **loopback RFC 5321 server**
  (`LocalSMTPSink`) used by the test suite.
- **STATUS** — **third-party provider acceptance: UNVERIFIED.** Nothing was sent to any provider
  this phase, because no provider exists to send through.

## 13. Mailbox receipt evidence (level C)

- **WHAT** — the controlled mailbox (`omarsafealden@gmail.com`) supplied for this phase.
- **EVIDENCE** — the mailbox was **not contacted**: with no provider configured there is no
  authorized way to deliver mail, and no IMAP/SMTP credential exists to read it. **Zero messages
  were sent** — no marketing, no bulk, no repeats.
- **Hygiene check (§4 requirement)** — the address is **not hardcoded** in application source:
  `grep -rn "omarsafealden"` across the repo returns only pre-existing documents referencing
  project-owned account URLs (Vercel/Modal slugs), never the mailbox in code or configuration.
- **STATUS** — **UNVERIFIED**. No receipt, no redemption.

## 14. Verification evidence (registration verification email)

- **A** — **VERIFIED (local)**: `test_auth_onboarding_lifecycle.py`, `test_email_delivery.py`,
  `test_pg_concurrency_lifecycle.py` (which completes the real flow by redeeming the token captured
  from the transport), plus the live smoke run.
- **B** — **UNVERIFIED**. **C** — **UNVERIFIED**.

## 15. Password reset evidence

- **A** — **VERIFIED (local)**: one-time reset link, replay/expiry negatives, no-leak on transport
  failure, 501 when unconfigured (never a false success).
- **B** — **UNVERIFIED**. **C** — **UNVERIFIED**.

## 16. Partner onboarding evidence

- **A** — **VERIFIED (local)**: application → pending → admin-only approval → server-side brand
  provisioning → `brand_owner`; the PostgreSQL race suite proves dual approval yields exactly one
  brand and one audit row.
- **B/C** — **UNVERIFIED**; production **BLOCKED**.

## 17. Invitation evidence

- **A** — **VERIFIED (local)**: invitation → accept → membership with the token's role/brand, plus
  negatives (escalation, expiry, cross-tenant, foreign-tenant access) and the PostgreSQL race
  (dual acceptance → exactly one membership).
- **B/C** — **UNVERIFIED**; production **BLOCKED**.

## 18. B2B regression evidence (original screenshot scenario)

- **WHAT** — consumer → `/b2b`.
- **EVIDENCE (local)** — the branch's guard renders the backend-authoritative state with a real next
  action (`/partner/apply`, `/partner/status`, `/verify-email`, suspended copy), never a privilege
  change; the four state branches are present in the merged file.
- **EVIDENCE (main, today)** — **the dead-end 403 is still on main** (§3.4): the original defect
  remains un-fixed on the deployed branch.
- **STATUS** — fix **VERIFIED (local)**; the production regression test of the new behaviour is **BLOCKED**.

## 19. RBAC evidence

- Unchanged and re-verified on the merged tree: role guards, admin step-up, 19 `@limiter.limit`
  decorators, approval/invitation authorization. No control was widened; this phase's backend edits
  are error-path narrowing (500 → precise 409) plus a terminal ledger state.
- **STATUS** — **VERIFIED (local)**.

## 20. Tenant-isolation evidence

- Cross-tenant negatives and foreign-tenant denial pass on the merged tree.
- **STATUS** — **VERIFIED (local)**; production **BLOCKED**.

## 21. Security-negative evidence

| Negative | Evidence | Status |
|---|---|---|
| Injected `role` / `brand_id` / `is_verified` on register | ignored; account created `consumer`, `is_verified=false` | VERIFIED (local) |
| Invitation role/brand override, expiry, replay, cross-tenant | dedicated tests | VERIFIED (local) |
| Unauthorized admin approval | `test_admin_review_requires_a_platform_admin` | VERIFIED (local) |
| CSRF enforcement | live probe: POST without token → 403 `CSRF_TOKEN_MISMATCH` | VERIFIED (local) |
| Redirect parameters | `test_no_endpoint_accepts_a_redirect_parameter` (OpenAPI scan) | VERIFIED (local) |
| Duplicate application / duplicate acceptance | partial unique indexes + PG races | VERIFIED (local) |
| Production negatives | not executed — requires a deployed branch | **BLOCKED** |

## 22. Email reliability / idempotency evidence

- Claim-before-send: exactly one provider transmission per idempotency key (PG race proved 1 message).
- Stale-claim resolver **verified active** on the merged tree: 6 PostgreSQL tests pass, including
  claim → abrupt process death (`BaseException`) → resolver → `unknown` → user retry with a **new**
  key → **exactly one** eventual message; the crashed key never re-transmits; a settled replay never
  touches the transport.
- No unlimited retry was added; `unknown` is terminal and never reported as success.
- **STATUS** — **VERIFIED (local, real PostgreSQL)**; production behaviour **BLOCKED** (feature not deployed).

## 23. Remaining GAPs

| GAP | Status |
|---|---|
| Partner notifications on stable keys cannot be re-emitted after `unknown` | Documented; operator replay would require storing bodies/tokens — rejected. FOLLOW-UP |
| Deliverability tooling (SPF/DKIM/DMARC, bounce handling) | FOLLOW-UP (needs a chosen provider) |
| Social signup intent | FOLLOW-UP (no OAuth credential in production) |
| Legacy `is_verified` accounts | **PENDING PRODUCT DECISION** — no silent change, no backfill in any migration |
| Real-browser E2E | UNVERIFIED — no browser framework added merely for coverage |
| Quote-style churn in two merged files | Cosmetic, documented (§3.6) |

## 24. Gates re-run on the merged tree

| Gate (CI job) | Command | Result |
|---|---|---|
| backend suite | `PYTHONPATH=. pytest backend/tests -q` | **1185 passed / 0 failed / 13 skipped** (249 s) |
| postgres-migrations (chain) | `check_migration_chain_postgres.py` on a fresh DB | **PASS** — head `0018`, parity `missing=[] extras=[]`, schema gate `ok`/`acceptable(production)=True`, base↔head round trip, numeric round trip |
| postgres-migrations (tests) | `CONFIT_TEST_PG_URL=… pytest test_schema_drift_gate test_migration_integrity_behavioral test_migration_0013…` | **39 passed** |
| concurrency + recovery | `CONFIT_PG_DSN=… pytest test_pg_concurrency_lifecycle.py` | **6 passed** |
| frontend | `vitest run` / `tsc --noEmit` / `npm run build` | **121 passed / 21 files**, clean, built |
| patch reproduction | `git am --3way` on a clean `origin/main` worktree | 24 commits, **tree identical** to the branch tip |
| GitHub CI | — | **UNVERIFIED** (no PR) |

## 25. Remaining UNVERIFIED

- Third-party provider acceptance (level B) — for verification, reset and invitation mail.
- Real mailbox receipt + redemption (level C).
- GitHub CI for this branch; real-browser E2E; production behaviour of every new endpoint.

## 26. Remaining BLOCKED

1. Production migration 0018 — no authorized owner path (§10).
2. Production email provider — no configuration and no credential (§11).
3. Branch push / PR / CI / merge — no GitHub credential (§4).
4. Consequently: the entire production verification programme (deployment SHA, schema 0018,
   registration, verification mail, reset, partner approval, invitation, tenant isolation,
   B2B matrix, original-screenshot regression on the new workflow).

## 27. Rollback plan

- **Migration** — 0018 is additive and reversible; **both directions were exercised on real
  PostgreSQL** this phase and the chain gate repeatedly proves base→head→base→head. No populated
  column is dropped and no data is rewritten beyond the additive `registration_intent` backfill.
- **Application** — production rollback is Vercel instant rollback to a recorded SHA
  (`f024807b…`, previously `463f81cc…`, `e1419d67…`).
- **Email** — with no provider configured, send-side endpoints answer `501 FEATURE_NOT_CONFIGURED`
  and the ledger records `BLOCKED`; the resolver never transmits, so a rollback cannot strand a
  half-sent message.
- **Ordering honoured** — 0018-dependent code is not promoted before the migration; the deployed
  SHA contains none of this work (404s in §8).

## 28. BRD traceability (updated)

| Requirement | Implementation | Test | Prod evidence | Status |
|---|---|---|---|---|
| Consumer lifecycle (register→intent→verify→onboarding→session→portal) | `onboarding_service`, `RegistrationIntent`, auth endpoints, SPA routes | 17 lifecycle + PG flow tests | none | A: VERIFIED (local) / prod BLOCKED |
| Password recovery, single-use token | `token_service`, forgot/reset endpoints | one-time, replay, expiry, no-leak | none | A: VERIFIED (local) / prod BLOCKED |
| Partner lifecycle with **server-side** provisioning | `partner_service` (apply, review, provision, invite, accept) | lifecycle + PG races | none | A: VERIFIED (local) / prod BLOCKED |
| Intent ≠ privilege | `user_repository.create` (`is_verified=False`), role guards, intent-as-data | injected-role tests, live smoke | none | A: VERIFIED (local) |
| Real email → ledger, no fake success | `email_service` transports + ledger + 501 semantics; claim-before-send; resolver | 21 email + 6 PG tests | none | A: VERIFIED (local) / B,C UNVERIFIED |
| MCP excluded from the send path | `EMAIL_PROVIDER_MCP_EVALUATION…` (decision unchanged, not reversed) | n/a | n/a | VERIFIED (documented) |
| No secrets in repo | tracked-file scans; token-prefix literal removed | grep scans | n/a | VERIFIED |
| Quality bar (negatives, correlation IDs, rate limiting, redirect allowlisting, DB uniqueness, additive migrations) | 19 limiters, request-id middleware, audit trail, partial uniques, 0018 | suite + schema gate | n/a | A: VERIFIED (local) |

## 29. Final verdict

> ## NO-GO — BLOCKED

**Why not `PRODUCTION VERIFIED`** — production is at schema 0017, runs `f024807b…` (main), has no
email provider, and this work has no push, no PR, no CI run and no deployment SHA.

**Why not `PARTIALLY VERIFIED`** — no production gate beyond "the old build serves" passes; nothing
from this work is in production.

**What is genuinely stronger than at the frozen handoff**

1. The branch is **integrated with current main** (`f024807`), including PRs #113–#115, with an
   audited conflict resolution that preserves both sides (§3.3) — verified by 1185 backend tests,
   121 frontend tests, typecheck, build, the migration chain gate, and the PostgreSQL suites.
2. **New evidence that the original defect is still live on main** (§3.4) — the dead-end 403 page
   remains in the deployed branch; this is now documented rather than assumed.
3. The canonical email variable set survived the merge with main's new `PARTNER_LEAD_NOTIFY_EMAIL`
   setting, and main's new partner-demo endpoints/UI are intact in the merged tree.
4. Artifacts regenerated and independently reproduced (`git am --3way`, identical tree).

**To unblock — unchanged, in the deployment order the phase specifies**

1. An authorized **owner-run migration** path for the production database (credential or an
   owner-executed `alembic upgrade head`).
2. A real **email provider** configured with the canonical variables
   (`EMAIL_PROVIDER`, `EMAIL_FROM_ADDRESS`, `EMAIL_REPLY_TO`, `SMTP_*` or `RESEND_API_KEY`,
   `FRONTEND_BASE_URL=https://confit-a.vercel.app`).
3. **GitHub push credentials** so the branch becomes a PR and CI can run.

*Nothing here is claimed more strongly than the evidence supports. Where evidence stops, this
report says BLOCKED or UNVERIFIED.*
