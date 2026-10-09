# Feature Specification: Admin Console (Orders Ops, Users & Roles, Governance, Observability)

**Feature Branch**: `004-admin-console`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings ADM-01, ADM-04, ADM-05, ADM-06, ADM-08, ADM-09, ADM-10, ADM-11, ADM-12, ADM-13, ADM-14, ADM-16, ADM-17, ADM-18, ADM-19, ADM-20 (`ADMIN_REPAIR_PLAN.md`). (ADM-07 promotions is in workstream 002.) Constitution Principle III (real authorization) and I (honesty).

## Problem Context *(evidence)*

CONFIT_A has strong server-side admin authorization primitives that are **already verified positive**: registration cannot escalate to admin/brand (ADM-02, VERIFIED), authorization resolves the DB role not a forgeable JWT claim (ADM-03, VERIFIED), a tamper-evident hash-chained audit log exists (`models/user.py:156`, ADM-15, VERIFIED), and step-up re-auth is contracted (`dependencies.py:153`, `ADMIN_REAUTH_REQUIRED`). The gap is that most admin **operations have no UI**, and the step-up contract is not handled gracefully:

- **ADM-01 (GAP):** no admin user/role management UI; role changes only via direct DB/API. An admin provisioning/management endpoint likely must be added.
- **ADM-04/05 (GAP):** admin order transition + payment-capture APIs exist (`commerce_service.py`, `test_pay01_fulfillment_gate.py`) but there is no admin order list/search UI and no UI to drive transitions/capture.
- **ADM-06 (BUG-VERIFIED):** `ADMIN_REAUTH_REQUIRED` from `dependencies.py:153` is not handled in the catalog UI — the action silently fails instead of prompting re-auth.
- **ADM-08/09 (GAP):** brand verify/suspend service exists but is not governable from the UI; no catalog moderation/takedown.
- **ADM-10 (BUG-VERIFIED):** ad-billing admin endpoints 4xx for an admin who lacks a `BrandProfile`.
- **ADM-11/12/13/20 (GAP):** email outbox diagnostics, deep `/health/ready` ops panel, audit-log viewer/export, and governance CSV export are backend-only/absent.
- **ADM-14 (LIKELY):** admin KPIs use counters, not a ledger (cross-ref BRD-06, workstream 007).
- **ADM-16/17 (GAP, P3):** no rate-limit/abuse console; no feature-flag/kill-switch surface.
- **ADM-18/19 (LIKELY, P2):** inconsistent confirmation/rollback UX and incomplete i18n/RTL on B2B views (cross-ref workstream 010).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin manages users and roles safely (Priority: P1)

As an admin, I can list/search users and change roles through the UI, with step-up re-auth for sensitive changes, self-role-change blocked, and every change written to the tamper-evident audit chain.

**Why this priority**: ADM-01 — today roles can only change by direct DB access, which is unauditable and error-prone.

**Acceptance Scenarios**:

1. **Given** admin role, **When** I open Users & Roles, **Then** I can search users and see current roles.
2. **Given** a role change, **When** I submit it, **Then** step-up re-auth is required and the change appends to the audit chain which still verifies.
3. **Given** I attempt to change my own admin role, **When** I submit, **Then** it is blocked server-side.
4. **Given** a non-admin, **When** they call the admin users API, **Then** they are rejected server-side (Principle III).

---

### User Story 2 - Admin operates orders (list, transition, capture) (Priority: P1)

As an admin, I can browse/filter orders and drive state transitions and payment capture through the UI, backed by the existing idempotent APIs and the fulfillment gate.

**Why this priority**: ADM-04/05 — operational capability exists in the backend but is unreachable.

**Acceptance Scenarios**:

1. **Given** admin role, **When** I open Orders Ops, **Then** I can search/filter/paginate orders.
2. **Given** an order, **When** I trigger a transition or capture, **Then** it calls the existing idempotent endpoint and the fulfillment-gate tests remain green; capture requires step-up re-auth.
3. **Given** repeated identical transition requests, **When** sent, **Then** they are idempotent (no double effect).

---

### User Story 3 - Step-up re-auth recovers transparently (Priority: P2)

As an admin, when a sensitive action returns `ADMIN_REAUTH_REQUIRED`, the UI prompts me to re-authenticate and then completes the original action, instead of silently failing.

**Why this priority**: ADM-06 BUG-VERIFIED — current silent failure is a real defect, but recovery is UX-layer around an existing contract.

**Acceptance Scenarios**:

1. **Given** a sensitive action returning `ADMIN_REAUTH_REQUIRED`, **When** it is intercepted, **Then** a re-auth modal appears and, on success, the original action retries and succeeds.

---

### User Story 4 - Admin governs brands and catalog (Priority: P1)

As an admin, I can verify/suspend/reinstate brands and unpublish/takedown reported products from the UI, all audited.

**Why this priority**: ADM-08/09 — governance of a multi-tenant marketplace.

**Acceptance Scenarios**:

1. **Given** admin role, **When** I verify or suspend a brand, **Then** the existing service runs and the action is audited.
2. **Given** a reported product, **When** I take it down, **Then** it is unpublished and audited.

---

### User Story 5 - Admin ad-billing works without a BrandProfile (Priority: P2)

As an admin, I can access ad-billing admin functions even though I have no `BrandProfile`.

**Why this priority**: ADM-10 BUG-VERIFIED — admin is locked out of a function it should govern.

**Acceptance Scenarios**:

1. **Given** an admin with no BrandProfile, **When** they call ad-billing admin endpoints, **Then** they succeed (the endpoint no longer assumes the caller owns a brand).

---

### User Story 6 - Admin observability & governance exports (Priority: P2)

As an admin, I can view the email outbox status, a deep readiness panel, the audit log (ordered, exportable), and export orders/users as CSV — none of which expose secrets.

**Why this priority**: ADM-11/12/13/20 — operability/compliance.

**Acceptance Scenarios**:

1. **Given** admin role, **When** I open Ops, **Then** I see outbox status and `/health/ready` results with no secret values.
2. **Given** the audit log, **When** I view/export it, **Then** entries are ordered and exportable and the hash chain verifies.
3. **Given** governance export, **When** I export orders/users, **Then** I receive a CSV with no secrets.

### Edge Cases

- Self-lockout prevention (last remaining admin cannot demote themselves).
- Audit export must not include secret values or raw tokens.
- Idempotency keys for order transitions under retry.
- Feature-flag/kill-switch (ADM-17) and abuse console (ADM-16) are P3 and may be deferred to a later wave.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Admin user list/search and role-change endpoints MUST exist, enforce `require_role([ADMIN])`, block self-role-change, and append to the tamper-evident audit chain. (ADM-01)
- **FR-002**: Sensitive admin actions (role change, payment capture, takedown) MUST require step-up re-auth (`require_admin_recent`, `ADMIN_REAUTH_REQUIRED`). (ADM-06)
- **FR-003**: Admin order list/search/filter/paginate MUST be available in the UI over existing endpoints; transitions and capture MUST reuse existing idempotent APIs and keep the fulfillment gate green. (ADM-04/05)
- **FR-004**: The frontend MUST intercept `ADMIN_REAUTH_REQUIRED`, prompt re-auth, and retry the original action. (ADM-06)
- **FR-005**: Brand verify/suspend/reinstate and catalog takedown MUST be drivable from the admin UI, audited. (ADM-08/09)
- **FR-006**: Ad-billing admin endpoints MUST NOT require the admin to own a `BrandProfile`. (ADM-10)
- **FR-007**: Admin ops surfaces (email outbox status, readiness, audit viewer/export, CSV governance export) MUST exist and MUST NOT expose secret values. (ADM-11/12/13/20)
- **FR-008**: All admin endpoints MUST enforce authorization server-side via DB role; UI hiding is never the control. (Principle III)
- **FR-009**: New admin endpoints are added ONLY where a true GAP exists (ADM-01 user/role, ops panels); existing endpoints are reused for orders/brands. (audit §ADM guidance)

### Key Entities

- **User/Role**: existing `UserRole` enum (`models/user.py:15` ADMIN; BRAND_OWNER/MANAGER/STAFF L12-14).
- **Audit Entry**: existing hash-chained record (`models/user.py:156`).
- **Order**: existing; admin operates transitions/capture.

## Success Criteria *(mandatory)*

- **SC-001**: An admin can change a user's role via the UI; the change is audited and the chain verifies; a non-admin receives 403 from the same endpoint (test-verified).
- **SC-002**: Self-role-change is rejected 100% of the time; last-admin demotion is prevented.
- **SC-003**: Admin can list and transition orders via the UI; `test_pay01_fulfillment_gate.py` and transition idempotency tests stay green.
- **SC-004**: `ADMIN_REAUTH_REQUIRED` triggers a re-auth prompt and the retried action succeeds (frontend test).
- **SC-005**: Admin (no BrandProfile) successfully calls ad-billing admin endpoints (regression for ADM-10).
- **SC-006**: Audit export is ordered and secret-free; a scan of all admin responses finds 0 secret values.

## Assumptions

- The existing order transition/capture and brand verify/suspend services are correct and are wrapped, not rewritten.
- KPI ledger sourcing (ADM-14) is delivered with the advertising ledger in workstream 007; this console consumes it.
- ADM-16 (abuse console) and ADM-17 (feature-flag/kill-switch) are P3 and scheduled in a later wave.
- i18n/RTL/confirmation UX (ADM-18/19) align with workstream 010's design system.
