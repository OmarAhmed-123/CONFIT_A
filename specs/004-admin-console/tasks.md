---
description: "Task list for Admin Console"
---

# Tasks: Admin Console

**Input**: `specs/004-admin-console/{spec.md, plan.md}`
**Tests**: REQUIRED (RBAC, audit, idempotency).

## Phase 1: Setup
- [ ] T001 [FOUND] Link ADM-01/04/05/06/08/09/10/11/12/13/20; confirm existing endpoints for orders transition/capture and brand verify/suspend (reuse, don't rewrite).

## Phase 2: Foundational
- [ ] T002 [FOUND] Frontend admin API client with a global interceptor stub for `ADMIN_REAUTH_REQUIRED`. Linked: FR-004.
- [ ] T003 [FOUND] Admin route shell + role-gated navigation (server still enforces). Linked: FR-008.

## Phase 3: US1 — Users & Roles (P1) 🎯
### Tests first
- [ ] T004 [P] [US1] `backend/tests/test_admin_users_roles.py`: admin changes role (audited, chain verifies); non-admin 403; self-change blocked; last-admin demotion blocked. Linked: FR-001/002, SC-001/002. Acceptance: fails now (no endpoint).
### Implementation
- [ ] T005 [US1] Admin user list/search + role-change endpoint (NEW) under `require_role([ADMIN])` + `require_admin_recent` for the change; append audit entry. Linked: FR-001/002/009.
- [ ] T006 [US1] Users & Roles UI (search, role change, re-auth-aware). Linked: FR-001.

## Phase 4: US2 — Orders Ops (P1)
### Tests first
- [ ] T007 [P] [US2] `backend/tests/test_admin_orders_ops.py`: list/filter; transition idempotent; capture requires step-up; `test_pay01_fulfillment_gate.py` stays green. Linked: FR-003, SC-003. Acceptance: covers reuse.
### Implementation
- [ ] T008 [US2] Orders Ops UI over existing list + idempotent transition/capture endpoints. Linked: FR-003.

## Phase 5: US3 — Step-up re-auth recovery (P2)
### Tests first
- [ ] T009 [P] [US3] Frontend test: `ADMIN_REAUTH_REQUIRED` → modal → retry succeeds. Linked: FR-004, SC-004. Acceptance: fails now (silent failure).
### Implementation
- [ ] T010 [US3] Implement the interceptor + re-auth modal + original-action retry (fixes ADM-06 in catalog + admin UIs). Linked: FR-004.

## Phase 6: US4 — Brand & catalog governance (P1)
### Tests first
- [ ] T011 [P] [US4] Tests: verify/suspend/reinstate + product takedown audited; non-admin rejected. Linked: FR-005. Acceptance: fails now (no UI/endpoint wiring).
### Implementation
- [ ] T012 [US4] Governance UI over existing brand verify/suspend service + catalog unpublish/takedown. Linked: FR-005.

## Phase 7: US5 — Ad-billing without BrandProfile (P2)
### Tests first
- [ ] T013 [P] [US5] `backend/tests/test_admin_adbilling_no_brandprofile.py`: admin without BrandProfile succeeds. Linked: FR-006, SC-005. Acceptance: fails now (4xx).
### Implementation
- [ ] T014 [US5] Decouple ad-billing admin endpoints from BrandProfile ownership. Linked: FR-006.

## Phase 8: US6 — Observability & exports (P2)
### Tests first
- [ ] T015 [P] [US6] `backend/tests/test_admin_audit_export_secretfree.py`: outbox/readiness/audit/export expose 0 secrets; audit ordered; chain verifies. Linked: FR-007, SC-006. Acceptance: fails now.
### Implementation
- [ ] T016 [US6] Ops panels: email outbox status, `/health/ready` surface, audit viewer + ordered export, orders/users CSV export (secret-free). Linked: FR-007.

## Phase N: Polish
- [ ] T017 [POLISH] Confirm ADM-02/03/15 positives remain green; align i18n/RTL + confirmation UX with workstream 010 (ADM-18/19); schedule ADM-16/17 (P3) in later wave; KPI ledger from workstream 007 (ADM-14).
- [ ] T018 [POLISH] Record final commit + env; `/speckit.analyze`.

## Dependencies
- T002/T003 block UI stories. US2 depends on workstream 001 commerce path being intact (capture). ADM-14 KPIs depend on workstream 007 ledger.
