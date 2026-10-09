---
description: "Task list for Guest Order Trust & Returns"
---

# Tasks: Guest Order Trust & Returns

**Input**: `specs/003-guest-order-trust-returns/{spec.md, plan.md}`
**Tests**: REQUIRED (security IDOR + RBAC).

## Phase 1: Setup
- [ ] T001 [FOUND] Link CUS-09/10/24; inventory existing guest returns backend path + order lookup entrypoint.

## Phase 2: Foundational
- [ ] T002 [FOUND] Implement signed, expiring order-lookup token helper (reuse JWT); define second-factor interface (email match OR token). Linked: FR-001.

## Phase 3: US1 — Second-factor order lookup (P1) 🎯
### Tests first
- [ ] T003 [P] [US1] `backend/tests/test_guest_order_enumeration.py`: number-only denied; number+factor returns only that order; scripted enumeration discloses 0. Linked: FR-001/002, SC-001/002. Acceptance: fails now (current code is number-only).
### Implementation
- [ ] T004 [US1] Require second factor on the guest order lookup endpoint; return uniform denial (no existence leak). Linked: FR-001/002.
- [ ] T005 [US1] Update frontend order-lookup/tracking flow to collect and pass the second factor. Linked: FR-005.

## Phase 4: US2 — Guest returns (P1)
### Tests first
- [ ] T006 [P] [US2] `backend/tests/test_guest_returns.py`: guest with factor submits return; without factor rejected. Linked: FR-003, SC-003. Acceptance: fails now.
### Implementation
- [ ] T007 [US2] Expose the existing guest returns backend path via an endpoint guarded by the second factor. Linked: FR-003.
- [ ] T008 [US2] Add the returns action to the guest order UI. Linked: FR-003.

## Phase 5: US3 — Guest cart merge (P2)
### Tests first
- [ ] T009 [P] [US3] `backend/tests/test_guest_cart_merge.py`: merge dedupes under unique cart-line (DB-20); guest-only cart becomes account cart. Linked: FR-004, SC-004. Acceptance: fails now.
### Implementation
- [ ] T010 [US3] Merge guest cart into account cart on login (quantity dedupe bounded by stock). Linked: FR-004.

## Phase N: Polish
- [ ] T011 [POLISH] Verify no timing/shape leak in denial responses; record final commit + env; `/speckit.analyze`.

## Dependencies
- T002 blocks US1/US2. US3 independent.
