# Implementation Plan: Checkout Total Parity & Settlement-Currency Consistency

**Branch**: `001-checkout-total-parity` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-checkout-total-parity/spec.md`

## Summary

Collapse the two divergent pricing paths in `backend/app/services/commerce_service.py` — the cart preview (`_format_cart`, shipping at `:1701`) and checkout (`:314-317`) — into a single `price_quote()` engine that every surface calls. Make the cart quote shipping-method-aware (fixing CUS-01), resolve settlement currency through one function with one documented input (fixing CUS-02), unify the free-shipping base expression, and have the frontend reconcile optimistic totals to the server quote (CUS-03). Preserve all existing positive guarantees (Numeric(12,2), stock validation, discount allocation, no client-trusted prices).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5 / React 18 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic v2, Alembic; Vite, zustand, Tailwind

**Storage**: SQLAlchemy models; money as `Numeric(12,2)`. No new tables required (quote is a computed shape). Order persistence unchanged in schema.

**Testing**: pytest (`backend/tests`, 196 test files present); property/matrix tests for pricing; Vitest/RTL for `cartStore` reconciliation

**Target Platform**: Vercel serverless (`api/index.py`), ephemeral FS

**Project Type**: Web application (backend + frontend)

**Performance Goals**: Quote computation is in-request and synchronous; must add no measurable latency vs the existing single-path computation.

**Constraints**: Server-authoritative; exact Decimal arithmetic; revenue conservation at item grain under conversion.

**Scale/Scope**: One service method pair unified; one frontend store reconciliation; ~1 new/renamed internal function, no migration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Evidence Before Appearance**: PASS — every claim is tied to an evidence line; the fix ships with a regression test that fails before and passes after (SC-004). No "done" without the parity test green.
- **II. Server-Authoritative Commerce**: PASS and is the core intent — one pricing authority for one business context; client never trusted for money.
- **III. Real Authorization**: N/A to pricing math; unchanged (checkout still uses existing auth/guards).
- **IV. Honest AI & Integrations**: N/A.
- **V. Test-First & E2E**: PASS — parity property tests + currency identity tests + a CUS-01 regression test are mandatory before the change is considered complete.

No violations. Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-checkout-total-parity/
├── spec.md       # This feature's requirements (done)
├── plan.md       # This file
└── tasks.md      # Task breakdown by user story
```

(research.md / data-model.md / contracts/ not required: no new persistence or external contract; the "contract" is the single internal `price_quote()` return shape documented in spec Key Entities.)

### Source Code (repository root)

```text
backend/
├── app/
│   ├── services/
│   │   └── commerce_service.py   # unify _format_cart (:1690+) and checkout (:305+) onto price_quote()
│   └── schemas/                  # quote response shape (reuse existing cart/order schemas)
└── tests/
    ├── test_checkout_parity.py          # NEW — cart vs order matrix (SC-001)
    ├── test_settlement_currency.py      # NEW — currency identity (SC-002/003)
    └── test_order_discount_allocation.py # existing — must stay green

frontend/
└── src/
    └── stores/cartStore.ts       # reconcile optimistic totals to server quote (CUS-03)
    └── views/CheckoutView.tsx    # consume unified quote (banner honesty handled in 006/012)
```

**Structure Decision**: Web application layout. The change is concentrated in `commerce_service.py` (extract/unify) plus `cartStore.ts` reconciliation; no schema migration.

## Complexity Tracking

> No constitution violations. Section intentionally empty.
