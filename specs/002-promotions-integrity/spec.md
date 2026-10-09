# Feature Specification: Promotions Integrity (Caps, Market Scope, Lifecycle) & Admin CRUD

**Feature Branch**: `002-promotions-integrity`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings CUS-05, CUS-11, CUS-13, DB-03, DB-04 (`CUSTOMER_REPAIR_PLAN.md`); ADM-07 (`ADMIN_REPAIR_PLAN.md`). Constitution Principle II.

## Problem Context *(evidence)*

- **CUS-05 / DB-03 (BUG-VERIFIED):** coupon global and per-user redemption caps are not enforced at the database level. Concurrent redemptions can exceed the cap (over-redemption / race). There is no cap/validity/market column set and no atomic redemption ledger.
- **DB-04:** redemption is not committed inside the order transaction, so a coupon can be consumed without an order (or vice versa) under failure.
- **CUS-11 (BUG-VERIFIED):** promo market/region is not enforced at apply time; a promo is usable cross-market.
- **CUS-13 (BUG-VERIFIED):** a stale promo is not cleared when cart contents change and eligibility is lost; the discount persists.
- **ADM-07 (GAP):** there is no admin UI to create/read/update/deactivate promotions, and the enforcement columns DB-03 depends on do not exist, so caps are both uncreatable and unenforced.

This is one shared data-and-logic workstream because `CUSTOMER_REPAIR_PLAN.md:227` explicitly notes "one migration, not two" shared with the admin promotions surface.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Coupon caps are enforced race-safely inside the order transaction (Priority: P1)

As the platform, a coupon with a global cap of N and a per-user cap of M can never be redeemed more than N times total or more than M times by one user, even under concurrent checkout.

**Why this priority**: Financial leakage and abuse (CUS-05/DB-03/DB-04). Direct revenue impact.

**Independent Test**: Fire concurrent checkouts redeeming the same capped coupon and assert the count of successful redemptions never exceeds the cap and equals the count of orders that actually committed with that discount.

**Acceptance Scenarios**:

1. **Given** a coupon with global cap N and (N already redeemed), **When** another checkout attempts to redeem it, **Then** the redemption is rejected and no discount is applied.
2. **Given** C concurrent checkouts for a coupon with K remaining redemptions, **When** they race, **Then** exactly `min(C, K)` succeed and the rest are rejected (no over-redemption).
3. **Given** a successful redemption, **When** the order transaction rolls back, **Then** the redemption is also rolled back (atomic with the order, DB-04).
4. **Given** a per-user cap M and a user who has redeemed M times, **When** they try again, **Then** it is rejected.

---

### User Story 2 - Promotions are scoped to market and validity window (Priority: P1)

As the platform, a promo only applies in its allowed market(s) and only within its validity window.

**Why this priority**: CUS-11 — cross-market discount abuse.

**Independent Test**: Apply a promo scoped to market A while shopping in market B and assert rejection; apply outside its validity window and assert rejection.

**Acceptance Scenarios**:

1. **Given** a promo scoped to market A, **When** applied in market B, **Then** it is rejected with an honest ineligibility reason.
2. **Given** a promo with a start/end window, **When** applied before start or after end, **Then** it is rejected.

---

### User Story 3 - Stale promos are cleared when the cart loses eligibility (Priority: P2)

As a customer, if my cart changes so the applied promo no longer qualifies (e.g., below minimum spend), the discount is removed and I see why, and I am never quoted or charged an invalid discount.

**Why this priority**: CUS-13 — stale discount is a correctness and trust issue, though it is caught by the server re-quote at checkout.

**Acceptance Scenarios**:

1. **Given** an applied promo requiring minimum spend, **When** I remove items below that minimum, **Then** the promo is cleared and the cart total reflects no discount with a visible reason.
2. **Given** a cleared promo, **When** I checkout, **Then** no discount is applied and the order total matches the re-quoted cart.

---

### User Story 4 - Admins manage promotions from the UI with caps and scope (Priority: P1)

As an admin, I can create, view, edit, and deactivate promotions including global cap, per-user cap, market scope, and validity window, all enforced server-side.

**Why this priority**: ADM-07 — without this, caps cannot be configured at all.

**Acceptance Scenarios**:

1. **Given** admin role, **When** I create a promo with caps and scope, **Then** it persists with those enforcement fields and is immediately enforced at apply/redeem.
2. **Given** a non-admin, **When** they call the promotions admin API, **Then** they are rejected server-side (not merely hidden in UI — Principle III).
3. **Given** an active promo, **When** I deactivate it, **Then** it can no longer be applied.

### Edge Cases

- Redemption attempt exactly at the cap boundary under race (covered by US1-2).
- Coupon valid in multiple markets: scope is a set, not a single value.
- Order cancellation/refund after redemption: define whether the redemption is released (assumption below).
- Clock skew on validity window: server time is authoritative.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Promotions MUST carry enforcement fields: global redemption cap, per-user redemption cap, allowed market scope, validity window (start/end). (DB-03)
- **FR-002**: Redemption MUST be enforced atomically and race-safely (row lock or conditional/atomic decrement) so concurrent redemptions cannot exceed any cap. (CUS-05)
- **FR-003**: Redemption MUST be committed inside the same transaction as the order. (DB-04)
- **FR-004**: Promo eligibility MUST be re-validated server-side at apply and again at checkout for market scope, validity window, caps, and minimum-spend/eligibility. (CUS-11/13)
- **FR-005**: When a cart mutation invalidates an applied promo, the system MUST clear it and report an honest reason; no invalid discount is ever quoted or charged. (CUS-13)
- **FR-006**: Admin promotion CRUD endpoints MUST exist and MUST enforce `require_role([ADMIN])` server-side; sensitive changes emit audit records. (ADM-07, Principle III)
- **FR-007**: A redemption ledger MUST record each redemption with (promo, user, order) and support uniqueness/atomic constraints enabling FR-002/003.
- **FR-008**: The migration implementing FR-001/007 MUST forward-chain from the current repo head and MUST be reconciled with the production migration state (see workstream `011-data-integrity-migrations`); no `down_revision` collision.

### Key Entities

- **Promotion**: code, type, value, min-spend, global cap, per-user cap, market scope, validity window, active flag.
- **Redemption Ledger**: promotion_id, user_id, order_id, timestamp; constraints enforce caps.

## Success Criteria *(mandatory)*

- **SC-001**: Under a concurrency test of C simultaneous redemptions with K remaining, exactly `min(C,K)` succeed, 0 over-redemptions, across ≥100 repetitions.
- **SC-002**: 100% of out-of-market and out-of-window apply attempts are rejected.
- **SC-003**: Redemption count equals committed-order-with-discount count after induced rollbacks (atomicity).
- **SC-004**: Admin can create a capped promo via API/UI and a non-admin is rejected 403 server-side (test-verified).
- **SC-005**: A cart that loses eligibility shows zero discount in both cart quote and order.

## Assumptions

- On order cancellation/refund, a redeemed coupon is released back to the pool (reversing ledger entry) — to be confirmed with product; default is release-on-refund.
- The promotions migration is authored but NOT executed during planning; execution and prod reconciliation are gated by workstream 011.
- Pricing consumes the re-validated discount via workstream 001's `price_quote()`.
