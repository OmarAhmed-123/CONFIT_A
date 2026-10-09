---
description: "Task list for Promotions Integrity & Admin CRUD"
---

# Tasks: Promotions Integrity & Admin CRUD

**Input**: `specs/002-promotions-integrity/{spec.md, plan.md}`

**Tests**: REQUIRED (financial integrity + RBAC).

## Phase 1: Setup
- [ ] T001 [FOUND] Link findings CUS-05/11/13, DB-03/04, ADM-07; confirm current Alembic head before authoring migration (coordinate with workstream 011). Completion: head recorded in this file.

## Phase 2: Foundational (Blocking)
- [ ] T002 [FOUND] Author (do NOT run against prod) migration `00NN_promotions_caps_and_ledger`: add global cap, per-user cap, market scope, validity window to the promotion model; create `promotion_redemptions` ledger with constraints enabling atomic caps. `down_revision` = current repo head; reconcile with 011. Linked: FR-001/007/008. Acceptance: `alembic upgrade head` succeeds on test DB; `downgrade` reverses cleanly.
- [ ] T003 [FOUND] Update models in `app/models/promotion.py` to match the migration (fields + ledger relationship). Linked: FR-001/007.

**Checkpoint**: schema + models on test DB; no prod mutation.

## Phase 3: US1 — Race-safe caps in order txn (P1) 🎯
### Tests first
- [ ] T004 [P] [US1] `backend/tests/test_promotion_caps_race.py`: concurrency harness asserting exactly `min(C,K)` succeed and redemption count == committed-order-with-discount count under induced rollback. Linked: FR-002/003, SC-001/003. Acceptance: fails now.
### Implementation
- [ ] T005 [US1] Enforce redemption atomically (row lock / conditional decrement) inside the order transaction in `commerce_service.py`. Linked: FR-002/003.
- [ ] T006 [US1] Reject at global and per-user caps with honest reasons. Linked: FR-002.

**Checkpoint**: T004 green.

## Phase 4: US2 — Market scope + validity (P1)
### Tests first
- [ ] T007 [P] [US2] `backend/tests/test_promotion_scope.py`: out-of-market and out-of-window apply attempts rejected. Linked: FR-004, SC-002. Acceptance: fails now.
### Implementation
- [ ] T008 [US2] Re-validate market scope + validity window at apply and at checkout in `commerce_service.py`. Linked: FR-004.

## Phase 5: US4 — Admin promotions CRUD (P1)
### Tests first
- [ ] T009 [P] [US4] `backend/tests/test_admin_promotions_rbac.py`: admin creates capped promo; non-admin 403 server-side; deactivate blocks apply. Linked: FR-006, SC-004. Acceptance: fails now.
### Implementation
- [ ] T010 [US4] Admin promotions CRUD controller/service under `require_role([ADMIN])`, emitting audit records. Linked: FR-006.
- [ ] T011 [US4] Admin promotions UI (create/edit/deactivate, caps + scope + window). Linked: FR-006, ADM-07.

## Phase 6: US3 — Stale promo clearing (P2)
### Tests first
- [ ] T012 [P] [US3] Test: cart mutation that loses eligibility clears the promo in cart quote and order. Linked: FR-005, SC-005. Acceptance: fails now.
### Implementation
- [ ] T013 [US3] Clear invalidated promo server-side on recompute with honest reason; surface in cart UI. Linked: FR-005.

## Phase N: Polish
- [ ] T014 [P] [POLISH] Confirm the discount consumed by `price_quote()` (workstream 001) is the re-validated value.
- [ ] T015 [POLISH] Record final commit + tested env; `/speckit.analyze`.

## Dependencies
- T002/T003 block all stories. Migration execution against production is OUT OF SCOPE here and gated by workstream 011. US1 must land before/with workstream 001 relies on re-validated discount.
