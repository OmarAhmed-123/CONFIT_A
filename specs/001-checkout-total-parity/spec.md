# Feature Specification: Checkout Total Parity & Settlement-Currency Consistency

**Feature Branch**: `001-checkout-total-parity`

**Created**: 2026-10-09

**Status**: Draft (planning only — no implementation performed)

**Input**: Forensic findings CUS-01, CUS-02, CUS-03, CUS-12 (`docs/audits/CUSTOMER_REPAIR_PLAN.md`); Constitution Principle II (Server-Authoritative Commerce).

## Problem Context *(evidence)*

CONFIT_A computes a cart/mini-cart quote in `CommerceService._format_cart` and a checkout/order quote in the checkout path, in **two separate code paths** of `backend/app/services/commerce_service.py`:

- **Checkout** (`commerce_service.py:314-317`) honors the selected shipping method: when `shipping_method == "express"`, shipping is `express_fee` unless `(subtotal - discount) >= free_threshold`.
- **Cart preview** (`commerce_service.py:1701`) has **no express branch at all** — it always uses `standard_fee` (or free when `taxable >= free_threshold or subtotal == 0`).

Result (**CUS-01, BUG-VERIFIED**): a customer who selects express shipping sees a cart total built with the *standard* fee but is charged the *express* fee at order placement. The displayed amount and the charged amount diverge for the same cart. This violates Constitution Principle II ("the amount displayed and the amount charged MUST derive from one pricing authority for the same business context").

Related findings in the same pricing surface:
- **CUS-02 (BUG-VERIFIED):** settlement currency is resolved in two places; the cart comment at `commerce_service.py:1709` claims "one authority" via `MarketPaymentCapabilityRegistry.resolve_settlement(settings.MARKET)`, but the cart path keys currency on `settings.MARKET` while the checkout path can resolve settlement against the shipping **country** — the two can disagree when a customer ships to a country whose settlement currency differs from the platform market.
- **CUS-03 (BUG-VERIFIED):** the frontend `cartStore.ts` renders optimistic totals that can drift from the server recompute.
- **CUS-12 (LIKELY):** multiple currency display sources cause FX/formatting inconsistencies.

The fix is to collapse both quotes onto a single server-side pricing engine (`price_quote()`), so every surface (cart, mini-cart, checkout, order) is the same function of the same inputs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Express shipping total is identical in cart and at checkout (Priority: P1)

As a customer selecting express shipping, the total I see in the cart/mini-cart must equal the total I am charged when I place the order, for the same cart contents, promo, and destination.

**Why this priority**: Direct financial-integrity defect (CUS-01). The customer is quoted one price and charged another. This is the single most severe customer-facing commerce bug in scope.

**Independent Test**: Build a cart, choose express shipping below the free-shipping threshold, read the cart quote, place the order, and assert the cart `total` equals the order `total` to the cent. Repeat above the free threshold (both should be free shipping).

**Acceptance Scenarios**:

1. **Given** a cart whose `(subtotal - discount)` is below `FREE_SHIPPING_THRESHOLD` and express shipping is selected, **When** I view the cart quote and then place the order, **Then** both quotes include `EXPRESS_SHIPPING_FEE` and the two totals are equal to the cent.
2. **Given** a cart whose `(subtotal - discount)` is at or above `FREE_SHIPPING_THRESHOLD` and express shipping is selected, **When** I view the cart quote and then place the order, **Then** shipping is `0.00` in both and the totals are equal.
3. **Given** standard shipping selected, **When** I view the cart and place the order, **Then** totals match (regression — must not break the currently-correct standard path).
4. **Given** a BOPIS/pickup fulfillment, **When** priced in both surfaces, **Then** shipping is `0.00` in both.

---

### User Story 2 - Settlement currency is identical across cart, checkout, and order (Priority: P1)

As a customer, every surface that shows me money for one checkout context shows it in exactly one settlement currency, and the currency I'm quoted is the currency I'm charged.

**Why this priority**: CUS-02 — charging/quoting in mismatched currencies is a financial-integrity and legal risk.

**Independent Test**: For each supported market/destination pair, request the cart quote and the checkout/order quote and assert identical `currency` and identical converted aggregates; assert `subtotal - discount + tax + shipping == total` holds post-conversion in both.

**Acceptance Scenarios**:

1. **Given** a market whose settlement currency equals the pricing currency, **When** cart and order are priced, **Then** both report that currency and conversion is a no-op.
2. **Given** a market/destination whose settlement currency differs from the pricing currency, **When** cart and order are priced, **Then** both report the **same** settlement currency and both satisfy the component-sum identity after conversion.
3. **Given** a destination country whose settlement currency differs from `settings.MARKET`, **When** cart and checkout resolve settlement, **Then** they agree on currency (single resolver, single input definition).

---

### User Story 3 - Displayed cart totals never silently diverge from server truth (Priority: P2)

As a customer, the cart total I see is always the server-authoritative total; optimistic UI updates reconcile to the server quote and never leave a stale number on screen.

**Why this priority**: CUS-03/CUS-12 — stale optimistic totals erode trust and can mislead at the moment of purchase, but they are a client reconciliation defect, not a wrong charge.

**Independent Test**: Mutate the cart (qty change, add/remove, apply/clear promo) and assert the displayed total converges to the latest server quote within one reconciliation cycle, with a visible pending state while recomputing.

**Acceptance Scenarios**:

1. **Given** an optimistic quantity change, **When** the server quote returns, **Then** the displayed total equals the server total and any transient optimistic value is replaced, not retained.
2. **Given** a failed recompute (network error), **When** reconciliation fails, **Then** the UI shows an honest "could not update total" state rather than a stale confident number.

---

### Edge Cases

- Promo becomes ineligible between cart view and checkout (ties to workstream 002): checkout must re-quote and the total must reflect the re-validated discount, with parity preserved.
- Rounding at item grain under currency conversion: converted line subtotals must sum to the converted subtotal (revenue conservation), identical rule in both paths.
- Zero-item cart: shipping `0.00`, total `0.00`, no express fee, both paths.
- Free-shipping threshold evaluated on `(subtotal - discount)` at checkout vs `taxable` at cart — these definitions must be unified (currently they use different expressions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST compute cart, mini-cart, checkout, and order totals from a single server-side pricing function (`price_quote()`), parameterized by cart contents, promo, fulfillment type, shipping method, and destination/market.
- **FR-002**: The pricing function MUST support all shipping methods used anywhere in the UI (at minimum `standard`, `express`, and BOPIS/pickup) so the cart quote can reflect the customer's selected method.
- **FR-003**: The free-shipping threshold MUST be evaluated against one unified base expression in all surfaces (resolve the current `(subtotal - discount)` vs `taxable` discrepancy to a single defined rule).
- **FR-004**: Settlement currency MUST be resolved by exactly one function with one documented input (market and/or destination), used by every pricing surface, so cart and order never disagree on currency.
- **FR-005**: After currency conversion, every surface MUST satisfy `subtotal - discount + tax + shipping == total` and MUST rebuild `subtotal` as the sum of converted line subtotals (not the conversion of the summed subtotal).
- **FR-006**: The client MUST NOT be trusted for any pricing input that affects money; the server recompute is authoritative and the order is persisted from server-computed values only.
- **FR-007**: The frontend MUST reconcile optimistic cart totals to the latest server quote and MUST surface an honest error state when reconciliation fails (no retained stale totals).
- **FR-008**: Money MUST remain `Numeric(12,2)` with explicit range enforcement (`assert_money_range`) on every persisted/returned monetary aggregate (preserve DB-19).
- **FR-009**: All existing positive guarantees MUST be preserved: no client-trusted prices (CUS-23), server-side stock validation (CUS-17), discount allocation correctness (CUS-18).

### Key Entities *(include if feature involves data)*

- **Price Quote**: the canonical priced result for a cart in a context — `currency`, `subtotal`, `discount`, `tax`, `shipping`, `total`, per-line converted subtotals, `shipping_method`, `fulfillment`. Not necessarily a new table; it is the single return shape of `price_quote()`.
- **Settlement**: resolved `{currency, converted, convert()}` from the market/destination registry; one resolver.
- **Order**: persisted from the quote; stored aggregates must equal the quote that was shown at confirmation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of (shipping method × threshold side × fulfillment) combinations, the cart quote `total` equals the order `total` to the cent (property test over a generated matrix).
- **SC-002**: For 100% of supported market/destination pairs, cart and order report the identical settlement `currency`.
- **SC-003**: The component-sum identity `subtotal - discount + tax + shipping == total` holds in 100% of generated quote cases, pre- and post-conversion.
- **SC-004**: A dedicated regression test for CUS-01 exists and fails against the current code and passes after the fix.
- **SC-005**: Zero occurrences of a second, independent shipping/currency calculation remain in the codebase (grep/structural check: only `price_quote()` computes shipping and settlement).

## Assumptions

- The intended behavior is that the customer is charged the fee for the shipping method they selected; the cart must therefore become shipping-method-aware (the checkout path is treated as the correct reference for fee selection).
- `EXPRESS_SHIPPING_FEE`, `STANDARD_SHIPPING_FEE`, `FREE_SHIPPING_THRESHOLD`, `TAX_RATE`, and `MARKET` remain configuration-driven.
- Promotion re-validation semantics are owned by workstream `002-promotions-integrity`; this workstream consumes the re-validated discount but does not redefine coupon caps.
- No production pricing data is mutated during planning; all verification runs against the test database.
