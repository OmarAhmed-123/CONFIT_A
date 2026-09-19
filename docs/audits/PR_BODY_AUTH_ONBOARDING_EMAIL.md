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
| Full backend suite | see the report §15/§16 (only pre-existing, environment-related failures) |
| `vitest run` | **114 passed / 19 files** (13 new lifecycle-routing cases) |
| `tsc --noEmit` + `npm run build` | clean |
| Migration up/down/up | PASS (head `0018`) |

## Blockers (documented, not hidden)
* **Not deployed to production yet** — production runs `main @ 928e61511` (READY); the new endpoints 404 there.
* **Migration 0018 cannot be applied to the production database yet** — `InsufficientPrivilege: must be
  owner of table users` (runtime role `confit_app_rw`; owner `neondb_owner`). Needs one owner-role run of
  `alembic upgrade head` **before** the code is promoted (the startup schema gate would otherwise refuse to boot).
* **No email provider is configured** in the Vercel project (68 vars inspected: no `EMAIL_*`/`SMTP_*`/`RESEND_API_KEY`/`FRONTEND_BASE_URL`)
  → auth email is `BLOCKED` in production, and no third-party provider has accepted a message yet (`UNVERIFIED`).
* **PR could not be pushed from the execution environment** (no GitHub credential available); local commits,
  bundle and patch are provided.

Full detail: `docs/audits/AUTH_REGISTRATION_ONBOARDING_EMAIL_FINAL_REPORT_20260919.md`.
