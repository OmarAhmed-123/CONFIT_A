# Feature Specification: Guest Order Trust & Returns (+ Guest Cart Merge)

**Feature Branch**: `003-guest-order-trust-returns`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings CUS-09, CUS-10, CUS-24 (`CUSTOMER_REPAIR_PLAN.md`). Constitution Principle III (authorization) and I (honesty).

## Problem Context *(evidence)*

- **CUS-09 (BUG-VERIFIED):** guest order access is keyed on the order number alone. Order numbers are low-entropy/guessable, so anyone who guesses or enumerates a number can view another person's order (IDOR-class exposure of PII and order details).
- **CUS-10 (GAP):** a guest returns path exists in the backend but is not exposed in the UI; guests cannot initiate a return.
- **CUS-24 (LIKELY):** a guest's cart is not merged into their account on login, breaking cart continuity.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guest order lookup requires a second factor (Priority: P1)

As a guest, I can view my order only by providing the order number **and** a second factor (the email used on the order, or a signed lookup token from the confirmation), and I cannot view anyone else's order by guessing a number.

**Why this priority**: PII exposure / IDOR (CUS-09). Security-critical.

**Independent Test**: Request an order with the correct number but wrong/absent second factor → denied; with correct number + correct email/token → allowed; enumerate sequential numbers without the factor → all denied.

**Acceptance Scenarios**:

1. **Given** a valid order number without the matching email/token, **When** I request the order, **Then** access is denied (indistinguishable response for exists/not-exists where feasible).
2. **Given** a valid order number with the matching email/token, **When** I request it, **Then** I see only that order.
3. **Given** sequential/guessed order numbers, **When** I enumerate them without the factor, **Then** no order is disclosed.

---

### User Story 2 - Guests can initiate returns (Priority: P1)

As a guest, I can start a return for my order through the UI, authenticated by the same second factor as order lookup.

**Why this priority**: CUS-10 — a supported backend capability is unreachable, blocking a core post-purchase workflow.

**Acceptance Scenarios**:

1. **Given** a guest who passes the second-factor check, **When** they open the order, **Then** a returns action is available and submits to the existing backend path.
2. **Given** a guest without the second factor, **When** they attempt a return, **Then** it is rejected server-side.

---

### User Story 3 - Guest cart merges into the account on login (Priority: P2)

As a user who built a cart as a guest and then logs in, my guest cart merges into my account cart without losing or duplicating items.

**Why this priority**: CUS-24 — continuity/UX; not a security defect.

**Acceptance Scenarios**:

1. **Given** a guest cart and an account cart, **When** I log in, **Then** the carts merge with correct quantity dedupe (respecting the unique cart-line constraint DB-20).
2. **Given** a guest cart only, **When** I log in, **Then** it becomes my account cart.

### Edge Cases

- Timing/enumeration: lookup responses should avoid leaking existence via timing or differing error shapes where feasible.
- Token expiry/revocation for the signed lookup token.
- Merge conflicts where the same product+variant exists in both carts (sum vs max — assumption below).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Guest order lookup MUST require order number PLUS a second factor (order email match or a signed, expiring lookup token). (CUS-09)
- **FR-002**: Order lookup MUST NOT disclose order existence or contents to a request lacking the second factor; enumeration MUST NOT reveal other orders.
- **FR-003**: The guest returns capability MUST be exposed in the UI and MUST enforce the same second factor server-side. (CUS-10)
- **FR-004**: Guest cart MUST merge into the account cart on login with correct dedupe under the unique cart-line constraint. (CUS-24, DB-20)
- **FR-005**: All guest access paths MUST be enforced server-side (Principle III) — UI gating alone is insufficient.

### Key Entities

- **Order Lookup Token**: signed, expiring, bound to one order; alternative to email match.
- **Guest Session Cart**: pre-auth cart identified by session; merged on login.

## Success Criteria *(mandatory)*

- **SC-001**: 100% of order-number-only lookups (no second factor) are denied; a scripted enumeration discloses 0 orders.
- **SC-002**: Correct number + correct factor returns exactly the matching order and nothing else.
- **SC-003**: Guests can submit a return end-to-end in the UI; server rejects returns lacking the factor.
- **SC-004**: Guest→account cart merge produces correct quantities with 0 duplicate lines across a generated test matrix.

## Assumptions

- The second factor defaults to the order email; a signed lookup token embedded in the confirmation link/email is the token alternative (email sending is NOT exercised during planning).
- On merge, matching product+variant lines sum quantities (subject to stock), bounded by availability.
