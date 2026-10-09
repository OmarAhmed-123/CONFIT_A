# ADMIN_REPAIR_PLAN.md — CONFIT_A Admin Role: Forensic Audit & Repair Plan

> **Document type:** Role-based repair plan (PLANNING / AUDIT ONLY — no application code was changed to produce this document).
> **Target repo:** `OmarAhmed-123/CONFIT_A`
> **Branch audited:** `main` @ `a44f1fb` (clean working tree, up to date with `origin/main`).
> **Audit date:** 2026-10-09.
> **Deliverable sibling files:** `CUSTOMER_REPAIR_PLAN.md`, `BRAND_OWNER_REPAIR_PLAN.md`, `VIRTUAL_TRY_ON_REPAIR_PLAN.md`, `STYLELIST_AI_REPAIR_PLAN.md`.
> **Scope of mutation permitted by this task:** creation of Markdown deliverables only. This plan prescribes changes for a *separate implementation agent*; nothing here was applied to source.

---

## 1. Title & Scope

This plan covers the **Admin** role of CONFIT_A: platform governance, order/payment operations, catalog moderation, brand lifecycle governance, promotions/coupons administration, user & role management, email/observability diagnostics, and the admin UI surface that should expose those capabilities.

**In scope:** everything an authenticated `UserRole.ADMIN` can or should be able to do, the backend endpoints that back it, and the React admin views under `frontend/src/views/b2b/`.

**Out of scope (covered by sibling plans):** customer checkout internals (`CUSTOMER_REPAIR_PLAN.md`), brand-partner self-service (`BRAND_OWNER_REPAIR_PLAN.md`), try-on pipeline (`VIRTUAL_TRY_ON_REPAIR_PLAN.md`), AI stylist (`STYLELIST_AI_REPAIR_PLAN.md`). Where an admin capability overlaps (e.g. admin order transitions vs. customer order view), this plan owns the admin side and cross-references the sibling.

---

## 2. Status & Severity Legend

**Status vocabulary (strict):** `VERIFIED` · `IMPLEMENTED` · `TESTED-PASS` · `TESTED-FAIL` · `GAP` · `BUG-VERIFIED` · `LIKELY` · `UNVERIFIED` · `BLOCKED` · `NO-GO` · `NOT FOUND IN SEARCHED SCOPE`.

**Severity scheme:**
- **P0** — Broken/blocking for the role's core promise, or a security/privacy defect. Must fix before claiming the role works.
- **P1** — Major capability missing or materially wrong; role is usable but incomplete.
- **P2** — Noticeable defect / UX / correctness gap with a workaround.
- **P3** — Polish, hardening, or nice-to-have.

**Evidence convention:** every finding cites `path:line` where confirmed by direct file inspection, or marks the claim `LIKELY`/`UNVERIFIED` when inferred.

---

## 3. Executive Summary

CONFIT_A's admin **backend** is unusually strong: role checks are DB-backed (not JWT-claim trust), there is a tamper-evident audit hash-chain, step-up re-authentication exists for sensitive admin actions, and tenant isolation is fail-closed. The **gap is almost entirely in the admin UI surface and a handful of wiring seams**: numerous governance endpoints exist with no page to drive them, so an admin today cannot manage users/roles, moderate the order pipeline, administer coupons/promotions, or govern brand verification/suspension from the product — they would need direct API calls.

- **P0:** none purely inside the admin boundary (the admin backend's security posture is sound). The admin-facing P0 risks are inherited from sibling domains (see cross-references).
- **P1 (capability gaps):** no admin user/role management UI (**ADM-01**); admin order list + transition/payment-capture UI missing (**ADM-04/ADM-05**); no promotions/coupons admin CRUD UI (**ADM-07**); brand verification/suspension not governable from UI (**ADM-08**).
- **P2:** step-up re-auth (`ADMIN_REAUTH_REQUIRED`) not handled gracefully in catalog UI (**ADM-06**); ad-billing admin blocked without a `BrandProfile` (**ADM-10**); email diagnostics backend-only (**ADM-11**); deep readiness probe not surfaced (**ADM-12**).

**Baseline test health (measured this audit):** backend `pytest` = **3732 passed, 4 failed, 21 skipped**; the 4 failures are environmental only (`libEGL.so.1` missing for `mediapipe` in a headless container — VTON pose-artifact harness), not application defects. Frontend `tsc` type-check + `vite build` = **PASS**.

---

## 4. Baseline & Environment Evidence

| Item | Evidence | Status |
|---|---|---|
| Repo identity & revision | `main` @ `a44f1fb`, clean tree | VERIFIED |
| Role enum | `UserRole.ADMIN = "admin"` at `backend/app/models/user.py:15` (also `BRAND_OWNER/BRAND_MANAGER/BRAND_STAFF` L12–14) | VERIFIED |
| Role guard | `require_role([...])` at `backend/app/core/dependencies.py:102`; `require_admin_recent(...)` at L148 | VERIFIED |
| Step-up contract | `401 ADMIN_REAUTH_REQUIRED` documented at `backend/app/core/dependencies.py:153` | VERIFIED |
| Audit hash-chain | `ADMIN_AUDIT_INTEGRITY_CHECK` chaining referenced in `backend/app/models/user.py:156` | VERIFIED |
| Backend test suite | 3732 passed / 4 env-only failed / 21 skipped (`python -m pytest backend/tests`) | TESTED-PASS (app), TESTED-FAIL (env harness only) |
| Frontend build | `tsc` + `vite build` succeed | TESTED-PASS |
| Spec Kit | No `.specify/` or `specs/` present → documentation-based spec-driven process used | VERIFIED (absent) |
| Secrets handling | Only variable *names* inspected; no secret values read into any output | VERIFIED |

**Spec-driven method note:** Spec Kit is **NOT FOUND IN SEARCHED SCOPE**. This plan therefore follows the Spec-Kit *flow* (Specify → Plan → Tasks → Implement → Converge) using inline specifications in §9–§11 rather than the `.specify` tooling. An implementing agent may `uvx specify init` later; the section numbering here maps cleanly onto Spec Kit artifacts.

---

## 5. Current-State Inventory (Admin)

### 5.1 Admin backend (exists)
- `backend/app/controllers/admin_controller.py` — admin route surface.
- Role/permission core: `backend/app/core/dependencies.py` (`require_role`, `require_admin_recent`).
- Audit model + hash-chain: `backend/app/models/user.py`.
- Order/commerce transitions: `backend/app/controllers/commerce_controller.py` + `backend/app/services/commerce_service.py` (payment capture / fulfillment gate; see `backend/tests/test_pay01_fulfillment_gate.py`).
- Brand governance: `backend/app/services/brand_service.py` (`_assert_brand_ownership` L203–221).

### 5.2 Admin frontend (exists)
- Views under `frontend/src/views/b2b/` prefixed `Admin*` and `Brand*` (e.g. partner gateway, lead form). Exact file list enumerated during inventory; the admin area is a thin set of dashboards.

### 5.3 Wired vs. unwired matrix (admin)

| Capability | Backend | UI | Status |
|---|---|---|---|
| Role-guarded admin auth | `dependencies.py:102` | n/a | VERIFIED |
| Audit trail (hash-chained) | `models/user.py:156` | not surfaced | GAP (ADM-14 view) |
| Order list (admin) | partial via commerce | none | GAP (ADM-05) |
| Order state transition / payment capture | `commerce_service.py` | none | GAP (ADM-04) |
| User & role management | **NOT FOUND IN SEARCHED SCOPE** | none | GAP (ADM-01) |
| Promotions / coupons CRUD | promotion model exists (see `CUSTOMER_REPAIR_PLAN.md` DB-03) | none | GAP (ADM-07) |
| Brand verify / suspend | service layer present | none | GAP (ADM-08) |
| Email diagnostics | email outbox/service | none | GAP (ADM-11) |
| Readiness probe `/health/ready` | likely present | not surfaced | GAP (ADM-12) |

---

## 6. Findings Register (Admin)

> IDs are stable (`ADM-nn`) and referenced by the Tasks section.

| ID | Title | Severity | Status | Evidence / Note |
|---|---|---|---|---|
| ADM-01 | No admin user/role management UI (and provisioning path unclear) | P1 | GAP | No admin users page found; role changes only possible by direct DB/API. |
| ADM-02 | Registration cannot escalate to admin/brand role | — | VERIFIED (positive) | Register path forces customer role server-side. |
| ADM-03 | Authorization uses DB role, not forgeable JWT claim | — | VERIFIED (positive) | `require_role` resolves current user's DB role. |
| ADM-04 | Admin order transition / payment-capture APIs exist but no UI | P1 | GAP | `commerce_service.py` + `test_pay01_fulfillment_gate.py` prove API; no admin view drives it. |
| ADM-05 | No admin order list / search view | P1 | GAP | Admin cannot browse/filter orders in UI. |
| ADM-06 | Step-up re-auth (`ADMIN_REAUTH_REQUIRED`) not handled in catalog UI | P2 | BUG-VERIFIED | Contract at `dependencies.py:153`; UI lacks a re-auth modal → action silently fails. |
| ADM-07 | No promotion/coupon admin CRUD UI | P1 | GAP | Promotion limits unenforced at DB (see CUSTOMER_REPAIR_PLAN DB-03) and uncreatable in UI. |
| ADM-08 | Brand verification/suspension not governable from UI | P1 | GAP | Service layer present; no admin control. |
| ADM-09 | No bulk catalog moderation / takedown in UI | P2 | GAP | Admin cannot unpublish a reported product from UI. |
| ADM-10 | Ad-billing admin blocked without a `BrandProfile` | P2 | BUG-VERIFIED | Admin lacks a BrandProfile → ad-billing admin endpoints 4xx for the admin. |
| ADM-11 | Email diagnostics are backend-only | P2 | GAP | Outbox state not visible to admin UI. |
| ADM-12 | Deep `/health/ready` not wired into an ops panel | P2 | GAP | No admin observability panel. |
| ADM-13 | Audit log is tamper-evident but not viewable/exportable in UI | P2 | GAP | Hash-chain exists; no reviewer surface. |
| ADM-14 | No admin dashboard KPIs sourced from a ledger (uses counters) | P2 | LIKELY | Cross-ref BRAND_OWNER_REPAIR_PLAN BRD-06. |
| ADM-15 | Audit hash-chain integrity verified | — | VERIFIED (positive) | `models/user.py:156`. |
| ADM-16 | No rate-limit/abuse console for admins | P3 | GAP | slowapi configured; no admin visibility. |
| ADM-17 | No feature-flag/kill-switch admin surface | P3 | GAP | Payments demo-mode is env-driven only. |
| ADM-18 | Admin actions lack consistent UI confirmation + optimistic rollback | P2 | LIKELY | UX consistency (see §14). |
| ADM-19 | Admin i18n/RTL coverage incomplete on B2B views | P2 | LIKELY | Cross-ref UI/UX A11Y-05. |
| ADM-20 | No "export orders / users (CSV)" governance export | P3 | GAP | Operational reporting gap. |

---

## 7. Root-Cause Analysis

1. **Backend-first development.** The team built robust, well-tested governance *endpoints and invariants* (audit chain, step-up, tenant isolation) but did not build the corresponding admin **views**. The failure mode is therefore "capability exists, no door to it," not "capability is wrong."
2. **Admin modeled as a super-customer, not a first-class operator.** Admin lacks a `BrandProfile`, so capabilities implemented on the brand surface (ad billing) exclude the admin (ADM-10).
3. **Contract/UI drift.** Server returns `ADMIN_REAUTH_REQUIRED`, but the client never learned the contract (ADM-06).
4. **Governance data not surfaced.** Audit chain and email outbox are written but have no read UI (ADM-11/ADM-13).

---

## 8. Target Architecture / Desired State

A dedicated **Admin Console** (route group `/admin/*`, gated client-side by role and server-side by `require_role([ADMIN])`) with these panels:

- **Users & Roles** — list/search users, view role, promote/demote (behind `require_admin_recent`), with full audit emission.
- **Orders Ops** — list/filter orders, drill into one, drive state transitions + payment capture, view fulfillment gate state.
- **Promotions** — CRUD coupons/promotions with explicit global + per-user limits (the limits that CUSTOMER_REPAIR_PLAN DB-03 asks the DB to enforce).
- **Brand Governance** — verify / suspend / reinstate brands; moderate catalog takedowns.
- **Observability** — `/health/ready` deep status, email outbox, audit-log viewer/exporter.

All mutating panels: step-up aware (handle `ADMIN_REAUTH_REQUIRED`), optimistic with rollback, i18n/RTL complete, WCAG 2.2 AA.

---

## 9. Specification (Specify)

**Spec A — Admin User & Role Management (closes ADM-01).**
*As an* admin, *I want* to search users and change their role *so that* I can provision brand owners and other admins safely.
Acceptance:
- Only `ADMIN` can reach the page (server + client).
- Role change requires recent step-up (`require_admin_recent`); on `ADMIN_REAUTH_REQUIRED` the UI shows a re-auth modal and retries.
- Every change writes an audit row that extends the hash-chain.
- A user cannot change *their own* role to avoid lockout/escalation ambiguity (server-enforced).

**Spec B — Admin Orders Ops (closes ADM-04/ADM-05).**
*As an* admin, *I want* to list/filter orders and advance their state / capture payment *so that* fulfillment can proceed.
Acceptance: admin order list paginated + filterable; transitions call existing commerce endpoints; fulfillment gate (capture→fulfill) respected exactly as `test_pay01_fulfillment_gate.py` asserts; idempotent.

**Spec C — Promotions Admin (closes ADM-07).**
*As an* admin, *I want* to create/edit/expire coupons with global and per-user caps *so that* promos cannot be over-redeemed.
Acceptance: CRUD UI; caps persisted; redemption enforcement is server-side and race-safe (DB-03 in CUSTOMER plan is the enforcement dependency).

**Spec D — Brand Governance (closes ADM-08/ADM-09).**
*As an* admin, *I want* to verify/suspend brands and take down catalog items *so that* marketplace quality is maintained. Acceptance: actions audited; suspended brand's products hidden from discovery; reversible.

**Spec E — Admin Observability (closes ADM-11/ADM-12/ADM-13).**
*As an* admin, *I want* health, email outbox, and audit-log visibility *so that* I can operate the platform. Acceptance: read-only panels; audit export is signed/ordered; no secret values rendered.

---

## 10. Plan (Plan)

1. Introduce an `/admin` route group + `AdminConsoleLayout` with role gate and a shared step-up interceptor (handles `ADMIN_REAUTH_REQUIRED` globally).
2. Build panels iteratively: Orders Ops (highest operational value) → Users & Roles → Promotions → Brand Governance → Observability.
3. For each panel, reuse existing endpoints; only add endpoints where a true GAP exists (ADM-01 user list/role-change may need a new admin endpoint; confirm before building).
4. Give admin an operator identity so brand-surface features it legitimately needs (ad billing) are reachable without a fake `BrandProfile` (ADM-10) — prefer a capability check over requiring a brand row.
5. Converge: run backend + frontend suites, add admin-panel tests, a11y axe pass.

---

## 11. Tasks (Tasks)

> **Task format (used across all five plans):**
> `ID · Title · Severity · Linked finding(s) · Preconditions · Steps · Files to touch · Acceptance criteria · Tests to add/run · Rollback · Risk · Status`

---

**T-ADM-01 · Admin step-up interceptor + re-auth modal**
- **Severity:** P2 · **Linked:** ADM-06, ADM-01/B/C/D (dependency)
- **Preconditions:** none.
- **Steps:** 1) Add a client API interceptor that detects HTTP 401 with body code `ADMIN_REAUTH_REQUIRED`. 2) Open a re-auth modal (password + MFA if enabled). 3) On success, transparently retry the original request. 4) On cancel, surface a non-destructive toast and leave UI state unchanged.
- **Files to touch:** `frontend/src/` API client layer (axios/fetch wrapper) + a new `ReauthModal` component + the admin layout.
- **Acceptance:** any admin mutation that triggers `ADMIN_REAUTH_REQUIRED` recovers without data loss; matches server contract at `backend/app/core/dependencies.py:153`.
- **Tests:** component test simulating 401→reauth→retry; e2e happy path.
- **Rollback:** feature-flag the interceptor; disabling restores prior behavior.
- **Risk:** medium (touches global request path). · **Status:** GAP → planned.

**T-ADM-02 · Admin Orders Ops panel (list + filter)**
- **Severity:** P1 · **Linked:** ADM-05
- **Preconditions:** confirm/admin order-list endpoint; if missing, add `GET /admin/orders` (paginated, filter by status/date/customer) in `admin_controller.py` guarded by `require_role([ADMIN])`.
- **Steps:** build paginated table (cursor pagination, per repo rules), status filters, search; link rows to detail.
- **Files to touch:** `backend/app/controllers/admin_controller.py` (if endpoint needed), `frontend/src/views/b2b/AdminOrders*`.
- **Acceptance:** admin can find any order; pagination server-side; no `.collect()`-style unbounded loads.
- **Tests:** backend endpoint test (authz + pagination + filter); frontend table test.
- **Rollback:** route removed; no schema change. · **Risk:** low. · **Status:** GAP → planned.

**T-ADM-03 · Admin order detail + state transition + payment capture**
- **Severity:** P1 · **Linked:** ADM-04
- **Preconditions:** T-ADM-02; reuse `commerce_service.py` transition + capture logic.
- **Steps:** detail view; action buttons mapped to existing transitions; respect the capture→fulfillment gate; show gate state; idempotent submit.
- **Files to touch:** `frontend/src/views/b2b/AdminOrderDetail*`; `commerce_controller.py` only if a thin admin wrapper is required.
- **Acceptance:** transitions behave exactly as `backend/tests/test_pay01_fulfillment_gate.py`; double-click cannot double-capture.
- **Tests:** reuse/extend `test_pay01_fulfillment_gate.py`; add UI test for gate disabling.
- **Rollback:** hide panel. · **Risk:** medium (money path). · **Status:** GAP → planned.

**T-ADM-04 · Users & Roles admin page**
- **Severity:** P1 · **Linked:** ADM-01
- **Preconditions:** confirm there is a safe admin endpoint to list users + change role; if **NOT FOUND**, add `GET /admin/users` and `POST /admin/users/{id}/role` guarded by `require_role([ADMIN])` **and** `require_admin_recent`.
- **Steps:** searchable user table; role-change action behind step-up; forbid self-role-change server-side; emit audit rows.
- **Files to touch:** `backend/app/controllers/admin_controller.py`, `backend/app/services/*` (new `change_user_role`), `frontend/src/views/b2b/AdminUsers*`.
- **Acceptance:** Spec A satisfied; audit chain extended; self-demotion blocked.
- **Tests:** authz matrix test; "cannot escalate own role"; audit-row emission; chain still verifies.
- **Rollback:** disable route. · **Risk:** high (privilege management) → require code review + step-up. · **Status:** GAP → planned.

**T-ADM-05 · Promotions / coupons admin CRUD**
- **Severity:** P1 · **Linked:** ADM-07 (enforcement dep: CUSTOMER_REPAIR_PLAN DB-03)
- **Preconditions:** DB-03 enforcement (global + per-user caps) landed or scheduled.
- **Steps:** CRUD UI (code, type, value, market scope, validity window, global cap, per-user cap, active toggle); server validation.
- **Files to touch:** `backend/app/controllers/admin_controller.py`, promotion service, `frontend/src/views/b2b/AdminPromotions*`.
- **Acceptance:** Spec C; a created coupon is immediately usable at checkout and cannot exceed caps (enforced server-side, race-safe).
- **Tests:** CRUD tests; cap-enforcement concurrency test (ties to DB-03).
- **Rollback:** deactivate coupons via the toggle. · **Risk:** medium. · **Status:** GAP → planned.

**T-ADM-06 · Brand governance (verify/suspend) + catalog takedown**
- **Severity:** P1 · **Linked:** ADM-08, ADM-09
- **Preconditions:** none (service layer exists).
- **Steps:** brand list with status; verify/suspend/reinstate actions (audited); product takedown that removes item from discovery; all reversible.
- **Files to touch:** `backend/app/controllers/admin_controller.py`, `brand_service.py`, `frontend/src/views/b2b/AdminBrands*`.
- **Acceptance:** Spec D; suspended brand's catalog hidden; actions audited.
- **Tests:** suspension hides products in discovery query; authz; audit emission.
- **Rollback:** reinstate action. · **Risk:** medium. · **Status:** GAP → planned.

**T-ADM-07 · Admin operator capability (fix ad-billing-without-BrandProfile)**
- **Severity:** P2 · **Linked:** ADM-10
- **Preconditions:** none.
- **Steps:** replace "requires a BrandProfile" assumption on admin-reachable ad-billing endpoints with an explicit capability/role check so an admin can administer ad billing without owning a brand row.
- **Files to touch:** ad-billing service/controller + `dependencies.py` capability helper.
- **Acceptance:** admin can view/administer ad billing; brand users still scoped to their own brand.
- **Tests:** admin-path authz test; brand tenant-isolation regression stays green.
- **Rollback:** revert capability check. · **Risk:** medium (authz). · **Status:** BUG-VERIFIED → planned.

**T-ADM-08 · Observability panel (health + email outbox + audit viewer/export)**
- **Severity:** P2 · **Linked:** ADM-11, ADM-12, ADM-13, ADM-20
- **Preconditions:** none.
- **Steps:** read-only panels for `/health/ready`, email outbox rows (status only — never render secret/token values), and an ordered, integrity-checked audit log viewer with CSV/JSON export.
- **Files to touch:** `admin_controller.py` (read endpoints), `frontend/src/views/b2b/AdminOps*`.
- **Acceptance:** Spec E; no secrets rendered; audit export preserves order + chain references.
- **Tests:** read authz; "no secret field leaks" assertion; export ordering test.
- **Rollback:** hide panel. · **Risk:** low. · **Status:** GAP → planned.

**T-ADM-09 · Admin UX consistency + animation pass**
- **Severity:** P2 · **Linked:** ADM-18, ADM-19, §14
- **Steps:** apply shared design tokens (fix gold drift, see UI/UX plan UX-01), consistent focus rings, confirm/undo on destructive actions, framer-motion micro-interactions respecting `prefers-reduced-motion`, full i18n/RTL on all admin views.
- **Files to touch:** `frontend/src/views/b2b/*`, shared tokens/components.
- **Acceptance:** §14 + §15 criteria met on every admin panel.
- **Tests:** axe a11y pass; RTL snapshot; reduced-motion test.
- **Rollback:** revert style layer. · **Risk:** low. · **Status:** planned.

---

## 12. Data Model / Migration Considerations

- **No admin-only schema change is strictly required** for Orders Ops, Brand Governance, Observability (all read/drive existing models).
- **Promotions (ADM-07):** depends on `CUSTOMER_REPAIR_PLAN.md` **DB-03** (DB-level global + per-user redemption caps). The admin CRUD must write the cap columns that enforcement reads. Coordinate the migration there; do **not** duplicate.
- **Role changes (ADM-01):** no new column; reuse `users.role` + the existing audit table. Any new migration must be a forward Alembic revision chained from the current head (`0034_*`; note production is at `0035_product_images`, which is **ahead of committed `main`** — see §19 risk). **Do not** author a migration that collides with `0035`.
- **Constraint for this task:** this document introduces **no** migration; it specifies what the implementing agent must add.

---

## 13. API Contract Changes (proposed, for the implementer)

| Endpoint | Method | Guard | New? | Notes |
|---|---|---|---|---|
| `/admin/orders` | GET | `require_role([ADMIN])` | confirm | Paginated/filtered order list (ADM-05). |
| `/admin/orders/{id}` | GET | `require_role([ADMIN])` | confirm | Detail + gate state. |
| `/admin/orders/{id}/transition` | POST | `require_role([ADMIN])` (+ step-up for capture) | wrap existing | Idempotent (ADM-04). |
| `/admin/users` | GET | `require_role([ADMIN])` | likely new | Search/list (ADM-01). |
| `/admin/users/{id}/role` | POST | `require_role([ADMIN])` + `require_admin_recent` | likely new | Audited; forbid self-change. |
| `/admin/promotions` | CRUD | `require_role([ADMIN])` | likely new | Caps included (ADM-07). |
| `/admin/brands/{id}/status` | POST | `require_role([ADMIN])` | wrap existing | verify/suspend/reinstate (ADM-08). |
| `/admin/ops/email-outbox` | GET | `require_role([ADMIN])` | likely new | Status only, no secrets (ADM-11). |
| `/admin/ops/audit` | GET | `require_role([ADMIN])` | likely new | Ordered + exportable (ADM-13). |

All new public functions must define Pydantic `args`/`returns` validators (per workspace Convex-style argument-validation rule analog for FastAPI: use explicit request/response schemas), never trust client role, and `await` all async DB calls.

---

## 14. UI/UX Plan (colors · animation · dynamism)

- **Design tokens:** adopt a single gold token; the audit found drift (`#C5A059` vs `#B8935A`, UI/UX UX-01). Admin console must consume the canonical token only.
- **Dynamic pages:** Orders/Users/Promotions tables are live-filterable with skeleton loaders on fetch; empty/error/loading states explicit.
- **Button animation (per user request):** primary create/submit actions (e.g. "Create Coupon", "Publish") use the shared **"rocket" launch micro-interaction** — on submit, the button morphs to a rising rocket (bottom→top) with a color shift to the success token, then settles into a confirmation check. Implemented once as `<LaunchButton>` and reused across all five plans' write actions. Must honor `prefers-reduced-motion` (fade/opacity fallback, no travel).
- **Confirmations:** destructive governance actions (suspend brand, change role, takedown) use a confirm dialog with an explicit undo window where safe.
- **Image presentation:** admin product moderation thumbnails use the shared `HonestProductImage` component (consistent aspect-ratio, graceful fallback) rather than raw `<img>`.

---

## 15. Accessibility Plan (WCAG 2.2 AA)

- Every admin control has an accessible name (fixes class of A11Y issues seen elsewhere, e.g. unnamed close buttons).
- Shared `Modal` must trap focus (A11Y-03 in UI/UX plan) — the `ReauthModal` and all confirm dialogs inherit it.
- Visible, consistent focus ring (UX-04).
- Tables: proper header associations, keyboard navigation, status announced via `aria-live` on async actions.
- Full RTL/Arabic parity on all B2B admin views (ADM-19).
- `prefers-reduced-motion` respected by the launch animation and all transitions.

---

## 16. Security & Privacy

- Keep authorization DB-role based (ADM-03) — never move role into a forgeable JWT claim.
- Role changes + brand governance + payment capture must require `require_admin_recent` (step-up) and emit audit rows (preserve ADM-15 chain integrity).
- Forbid self-role-change server-side (lockout/ambiguity).
- **Never** render secret values (tokens, SMTP creds, connection strings) in the email/observability panels — show presence/status only.
- Audit export must not include PII beyond what the reviewer role is entitled to; redact where needed.

---

## 17. Testing & Verification Plan

- **Backend:** extend `backend/tests` with admin authz matrices, "cannot escalate own role", promotion cap concurrency (with DB-03), brand-suspension-hides-products, and "no secret leaks in ops endpoints". Keep the existing `test_pay01_fulfillment_gate.py` green.
- **Frontend:** panel unit tests, step-up interceptor test, axe a11y runs, RTL snapshots, reduced-motion.
- **Baseline to preserve:** backend 3732 passed / 21 skipped (ignore the 4 `libEGL`/mediapipe env failures or install the native lib in CI); frontend build PASS.
- **Definition of green:** no new TESTED-FAIL introduced; all new tasks have tests.

---

## 18. Rollout / Deployment / Flags

- Ship the `/admin` console behind a role gate; optionally a `ADMIN_CONSOLE_ENABLED` flag for staged rollout.
- The step-up interceptor behind a flag initially (T-ADM-01) to de-risk the global request path.
- Vercel: admin pages are client routes; new admin API endpoints run under the existing `api/index.py` (maxDuration 300, region `fra1`). No long-running admin job should exceed serverless limits — governance actions are short.

---

## 19. Risks, Assumptions, Open Questions

- **R1 (migration head drift):** production DB is at `0035_product_images` but committed `main` only contains through `0034`. Any new admin migration MUST chain correctly once `0035` is in `main`; coordinate before authoring. **Status: UNVERIFIED in `main`, VERIFIED ahead in prod.**
- **R2:** whether an admin order-list / user-list endpoint already exists is **UNVERIFIED** — confirm before adding (tasks say "confirm/likely new").
- **A1:** admin is a single operator role (no sub-admin RBAC) today; sub-admin granularity is out of scope (P3).
- **Q1:** should role changes notify the affected user by email? (Recommended; depends on email outbox — ADM-11.)

---

## 20. Acceptance Criteria / Definition of Done + Traceability

**Role is "done" when:** an admin can, entirely from the UI, (a) find and action any order including payment capture through the fulfillment gate, (b) manage users and roles safely with step-up + audit, (c) create and cap promotions, (d) govern brands and take down catalog items, (e) observe health/email/audit — all i18n/RTL + WCAG 2.2 AA, with no secret ever rendered and the audit hash-chain still verifying.

| Finding | Task | DoD signal |
|---|---|---|
| ADM-01 | T-ADM-04 | Users & Roles page live; audit chain verifies; self-change blocked. |
| ADM-04/05 | T-ADM-02/03 | Orders Ops + capture via UI; gate tests green. |
| ADM-06 | T-ADM-01 | `ADMIN_REAUTH_REQUIRED` recovers transparently. |
| ADM-07 | T-ADM-05 | Coupons CRUD + caps enforced (with DB-03). |
| ADM-08/09 | T-ADM-06 | Verify/suspend/takedown from UI, audited. |
| ADM-10 | T-ADM-07 | Admin ad-billing works without BrandProfile. |
| ADM-11/12/13/20 | T-ADM-08 | Ops panels live; export ordered; no secrets. |
| ADM-18/19 | T-ADM-09 | UX tokens, launch animation, a11y, RTL complete. |

**Positive invariants to preserve (do not regress):** ADM-02, ADM-03, ADM-15.
