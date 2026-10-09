# Implementation Plan: Guest Order Trust & Returns

**Branch**: `003-guest-order-trust-returns` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Require a second factor (order email match or signed expiring token) for all guest order access, close the enumeration/IDOR hole (CUS-09), expose the existing guest returns backend path in the UI with the same server-side guard (CUS-10), and merge guest carts into account carts on login respecting the unique cart-line constraint (CUS-24).

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, SQLAlchemy 2, Pydantic v2, PyJWT (for signed lookup tokens — reuse existing JWT/cookie infra)
**Storage**: No new table strictly required (email match); optional short-lived signed token (stateless) or a small token table. Reuse cart tables for merge.
**Testing**: pytest (enumeration/IDOR tests, returns RBAC), frontend tests for returns UI + merge-on-login
**Target Platform**: Vercel serverless
**Project Type**: Web application
**Constraints**: Avoid existence/timing leaks; tokens signed + expiring; fail closed.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — enumeration test is the proof of CUS-09 closure.
- **III. Real Authorization**: PASS/core — server-side second factor; no UI-only gating.
- **II**: N/A (no pricing change). **IV**: N/A. **V**: PASS — IDOR regression + returns + merge tests required.

No violations.

## Project Structure

```text
backend/
├── app/
│   ├── controllers/ (order lookup + guest returns endpoints with second-factor guard)
│   ├── services/commerce_service.py (lookup/returns/merge logic)
│   └── core/ (signed lookup token helper, reuse JWT)
└── tests/
    ├── test_guest_order_enumeration.py   # NEW (SC-001/002)
    ├── test_guest_returns.py             # NEW (SC-003)
    └── test_guest_cart_merge.py          # NEW (SC-004)
frontend/
└── src/views/ (OrderTracking/guest returns UI; login merge trigger)
```

**Structure Decision**: Web app; reuse JWT infra for the optional token; no large schema change.

## Complexity Tracking

> No violations.
