# Registration / onboarding / email lifecycle: make the 403 a workflow, not a wall

## Problem (production screenshot)
A signed-in **consumer** account (`ismaeil1234@gmail.com`) landing on the brand-guarded area got
“403 ROLE RESTRICTION — Requires one of: brand_owner, brand_manager, brand_staff, admin” with **no
route forward**. Audit result: the product had **no server-side workflow** to turn a shopper into an
approved partner, no registration intent, no onboarding state machine, no screens behind the emailed
links, and no email transport at all (`email_service` reported “queued” without sending anything).
The 403 was the visible end of a missing lifecycle — **not** a UI bug, and it is not bypassed here.

## What this PR does
**Registration & intent** — `registration_intent` (`consumer` | `brand_partner`) is captured as data;
the resulting role is always `consumer`. An injected `role`/`brand_id`/`is_verified` in the payload is
ignored (tested, and re-verified against the live production API).

**Onboarding state machine (server-authoritative)** — `GET /api/v1/auth/onboarding-state` and
`UserOut.onboarding` expose `SUSPENDED | EMAIL_VERIFICATION_REQUIRED | PARTNER_APPLICATION_PENDING |
ONBOARDING_REQUIRED | ACTIVE` plus `next_action{type,route,label}`, `partner_access`, `allowed_areas`.
The SPA routes on server state only: no guessing, no redirect loops, resumable after refresh/expiry.

**Two trusted routes to a brand role (both server-side)**
1. **Application → review → provisioning**: `POST /auth/partner-applications` (verified email required,
   one pending application per account) → admin approve behind `require_admin_recent(60)` → brand tenant
   + `brand_owner` provisioned with before/after audit and a decision email; reject keeps the account a
   consumer and allows a retry.
2. **Invitation**: `POST /brand/invitations` (brand owner/admin only, `admin` role not invitable) →
   `GET /auth/invitations/preview` + `POST /auth/invitations/accept`; role **and** brand come from the
   server-issued token row, single use, 72 h TTL, cross-tenant conflicts refused.

**Real transactional email (no fake success anywhere)** — `email_service.send_transactional()` with an
SMTP (`starttls`/`ssl`) and a Resend (HTTPS, Vercel-safe) adapter, a delivery ledger written from the
provider's own answer, per-message idempotency keys, transient-only retries, 10 bilingual templates and
SHA-256-only recipient storage. Unconfigured deployment ⇒ **501 `FEATURE_NOT_CONFIGURED`** and a
`BLOCKED` ledger row — registration still succeeds, but nothing claims an email was sent. The account
owner can read the real outcome via `GET /auth/email-status`.

**Every emailed link now lands on a real route** — `/verify-email`, `/reset-password`,
`/settings/confirm-email`, `/invite` (previously they fell through the router catch-all to `/`, so users
believed they had verified/reset when nothing had happened). A contract test now fails if any delivered
link stops resolving to a declared SPA route.

**The 403 is now state-accurate and actionable** — verify-first / in review / not approved / suspended /
admin-only, each with the one action that can change it (apply, view status, verify, contact support).
Authorization stays 100 % server-side: a forged local role still renders nothing and the API still 403s.

**Also** — tenant resolution centralised in `brand_scope_service` (owner **or** member) so delegated
brand users stop hitting spurious 403s; navigation leads to the workflow instead of the guard; Two-step
email change (new address first, sessions revoked, old address notified); EN/AR strings; `apiServices`
no longer accepts a role on register.

## Database
Migration **`0018_partner_onboarding_email_lifecycle`** (additive, idempotent, reversible):
`users.registration_intent`, `partner_applications`, `invitations`, `email_change_requests`,
`email_deliveries`, `brand_members`, with partial unique indexes (one pending application per user, one
pending invitation per email+brand, one open email change per user) and a unique delivery idempotency key.
Verified `upgrade → downgrade -1 → upgrade` on a scratch database.

## Evidence (all run locally)
| Check | Result |
|---|---|
| `pytest` auth/lifecycle/email suites | **61 passed** |
| Real SMTP sink: delivered token redeems, ledger truth, idempotency, no-provider 501 | passing |
| Email-link ↔ SPA-route contract (5 flows) | passing |
| Full backend suite (serial, nothing excluded, after integrating main) | **1185 passed / 0 failed / 13 skipped** |
| `vitest run` | **121 passed / 21 files** |
| `tsc --noEmit` + `npm run build` | clean |
| Migration up/down/up | PASS (head `0018`) |
| 0017→0018 on **real PostgreSQL** with legacy data | PASS — census, users and brand ownership unchanged; `registration_intent` backfilled 4/4; 5 tables, 3 partial unique indexes, 12 FKs |
| **PostgreSQL concurrency races** (5) + abandoned-claim recovery (1) | PASS — found and fixed 3 real defects (dual approval, dual invitation accept, duplicate send), plus the crash-window recovery mechanism |
| Patch reproduction | `git am --3way` on clean `origin/main` → 20 commits, identical tree |

## Integration note (this phase)

`origin/main` advanced to `f024807b` (PRs #113–#115) and **now overlaps this branch** in five files.
The branch was rebased onto it; conflicts in `RoleGuard.tsx`, `apiServices.ts`,
`backend/app/core/config.py` and `brand_controller.py` were resolved by **keeping both sides** —
main's new partner-demo lead form and endpoints, and this branch's actionable 403 state machine and
`registration_intent` typing. Notably, **main still ships the original dead-end `403 · Access
Restricted` page**; replacing it is what this branch does.

## Blockers (documented, not hidden)
* **Not deployed to production yet** — production runs `main @ f024807b4a6aaa2cc3767827eae632e891f0821c` (READY, re-checked); the new endpoints 404 there.
* **Migration 0018 cannot be applied to the production database yet** — `InsufficientPrivilege: must be
  owner of table users` (runtime role `confit_app_rw`; owner `neondb_owner`). Needs one owner-role run of
  `alembic upgrade head` **before** the code is promoted (the startup schema gate would otherwise refuse to boot).
* **No email provider is configured** in the Vercel project (68 vars inspected: no `EMAIL_*`/`SMTP_*`/`RESEND_API_KEY`/`FRONTEND_BASE_URL`)
  → auth email is `BLOCKED` in production, and no third-party provider has accepted a message yet (`UNVERIFIED`).
* **PR could not be pushed from the execution environment** (no GitHub credential available); local commits,
  bundle and patch are provided.

Full detail: **`docs/audits/AUTH_PRODUCTION_ACTIVATION_ATTEMPT_20260919.md`** (latest) and `docs/audits/AUTH_RELEASE_ACTIVATION_REPORT_20260919.md` and `docs/audits/AUTH_PHASE_7_CLOSURE_REPORT_20260919.md` (authoritative closure report;
verdict **NO-GO — BLOCKED**). Earlier documents: `AUTH_PHASE_3_6_FINAL_REPORT_20260919.md` (authoritative
for Phase 3–6), `AUTH_REGISTRATION_ONBOARDING_EMAIL_FINAL_REPORT_20260919.md` (superseded on four points).
