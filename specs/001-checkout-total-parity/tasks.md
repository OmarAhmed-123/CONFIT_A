---
description: "Task list for Checkout Total Parity & Settlement-Currency Consistency"
---

# Tasks: Checkout Total Parity & Settlement-Currency Consistency

**Input**: `specs/001-checkout-total-parity/{spec.md, plan.md}`

**Tests**: REQUIRED. This workstream fixes financial-integrity bugs; regression and property tests are mandatory per Constitution Principles II and V.

**Organization**: Grouped by user story (US1 = CUS-01 express parity, US2 = CUS-02 currency, US3 = CUS-03 reconciliation).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 / FOUND / POLISH

## Phase 1: Setup

- [ ] T001 [FOUND] Create `specs/001-checkout-total-parity/` tracking and link findings CUS-01/02/03/12 and constitution gate (this file). Completion: file committed. (No app code.)

## Phase 2: Foundational (Blocking)

- [ ] T002 [FOUND] Characterization tests FIRST: in `backend/tests/test_checkout_parity.py`, assert current behavior and capture the CUS-01 divergence (express, below threshold) as an xfail/failing test proving the bug. Linked: CUS-01. Acceptance: test FAILS against current `commerce_service.py`. Required test: itself.
- [ ] T003 [FOUND] Define the canonical `price_quote()` signature and return shape (currency, subtotal, discount, tax, shipping, per-line converted subtotals, shipping_method, fulfillment) as an internal contract comment + Pydantic/typed dict in `commerce_service.py`. Linked: FR-001. Acceptance: type exists; no behavior change yet.

**Checkpoint**: Failing CUS-01 test exists; target shape defined.

## Phase 3: User Story 1 — Express parity (P1) 🎯 MVP

**Goal**: Cart quote and order total are identical for every shipping method.

**Independent Test**: SC-001 matrix (shipping method × threshold side × fulfillment).

### Tests (write first)
- [ ] T004 [P] [US1] Property/matrix test in `backend/tests/test_checkout_parity.py`: for each (standard|express|bopis) × (below|at|above free threshold), assert cart `price_quote().total == order total`. Linked: FR-001/002/003, SC-001/004. Acceptance: fails now.

### Implementation
- [ ] T005 [US1] Extract shipping-fee selection into `price_quote()` so it honors `shipping_method` (standard/express/bopis) using `EXPRESS/STANDARD_SHIPPING_FEE` and the unified free-threshold rule. File: `commerce_service.py`. Linked: FR-002/003.
- [ ] T006 [US1] Rewrite `_format_cart` (`:1690+`) to call `price_quote()` with the cart's selected shipping method instead of the hardcoded standard-only branch at `:1701`. Linked: CUS-01, FR-001.
- [ ] T007 [US1] Rewrite the checkout path (`:305-347`) to call the same `price_quote()` so order persistence uses the identical result. Linked: FR-001/006.
- [ ] T008 [US1] Unify the free-shipping base expression (resolve `(subtotal - discount)` vs `taxable`) to one documented rule used by both. Linked: FR-003.

**Checkpoint**: T004 passes; CUS-01 fixed.

## Phase 4: User Story 2 — Settlement currency identity (P1)

**Goal**: One settlement resolver; cart and order never disagree on currency.

### Tests (write first)
- [ ] T009 [P] [US2] `backend/tests/test_settlement_currency.py`: for each market/destination pair, assert cart and order `currency` equal and the component-sum identity holds post-conversion. Linked: FR-004/005, SC-002/003. Acceptance: fails/surfaces CUS-02 now.

### Implementation
- [ ] T010 [US2] Make `price_quote()` resolve settlement via the single `MarketPaymentCapabilityRegistry.resolve_settlement(...)` call with one documented input (market and, where applicable, destination country); remove the second independent resolution in checkout. Linked: CUS-02, FR-004.
- [ ] T011 [US2] Ensure converted `subtotal` is rebuilt as the sum of converted line subtotals in the single engine (revenue conservation). Linked: FR-005.

**Checkpoint**: T009 passes; CUS-02 fixed.

## Phase 5: User Story 3 — Optimistic reconciliation (P2)

### Tests (write first)
- [ ] T012 [P] [US3] `frontend` test for `cartStore`: after an optimistic mutation, displayed total converges to server quote; on recompute failure, an honest error state is shown (no stale total). Linked: CUS-03/12, FR-007.

### Implementation
- [ ] T013 [US3] Update `frontend/src/stores/cartStore.ts` to replace optimistic totals with the server quote on resolve and to render a pending/error state. Linked: FR-007.
- [ ] T014 [US3] Audit currency display sources in consumer views; render from the server quote's `currency` only (CUS-12). Linked: FR-004/007.

**Checkpoint**: T012 passes; no stale totals.

## Phase N: Polish & Cross-Cutting

- [ ] T015 [P] [POLISH] Structural check / grep gate: only `price_quote()` computes shipping and settlement (SC-005). Linked: SC-005.
- [ ] T016 [POLISH] Confirm regression suite stays green: `test_order_discount_allocation.py`, stock-validation (CUS-17), no-client-price (CUS-23). Linked: FR-008/009.
- [ ] T017 [POLISH] Record final commit SHA + tested environment in this workstream; run `/speckit.analyze`.

## Dependencies & Execution Order

- Phase 2 blocks all stories. US1 and US2 both touch `price_quote()` — sequence US1 then US2 (same function) to avoid conflicts; US3 (frontend) is parallelizable with US2.
- Promotion re-validation discount value is provided by workstream 002; US1/US2 consume it but do not define caps.

## Notes

- No Alembic migration in this workstream.
- Verify every test FAILS before implementing (T002/T004/T009/T012).
