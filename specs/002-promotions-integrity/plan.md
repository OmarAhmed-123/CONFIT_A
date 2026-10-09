# Implementation Plan: Promotions Integrity & Admin CRUD

**Branch**: `002-promotions-integrity` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Add promotion enforcement fields (caps, market scope, validity window) and a redemption ledger via one forward-chained Alembic migration; enforce caps atomically inside the order transaction; re-validate eligibility server-side at apply and checkout; clear stale promos; and expose admin CRUD guarded by `require_role([ADMIN])`. One shared migration serves both the customer-enforcement and admin-authoring surfaces.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18

**Primary Dependencies**: FastAPI, SQLAlchemy 2, Alembic, Pydantic v2

**Storage**: New columns on the promotion model + a `promotion_redemptions` ledger table; `Numeric(12,2)` for value; concurrency via row lock / conditional update

**Testing**: pytest with concurrency harness (threads/async tasks against a shared transaction scope); admin RBAC tests; frontend tests for stale-promo clearing

**Target Platform**: Vercel serverless; migrations run out-of-band (not in request)

**Project Type**: Web application

**Constraints**: Atomicity with the order transaction; race-safety; forward-chained migration (current repo head is `0034_mfa_email_codes`).

## Constitution Check

- **I. Evidence Before Appearance**: PASS — concurrency SC-001 is the proof; no cap claimed enforced without the race test.
- **II. Server-Authoritative Commerce**: PASS/core — caps and eligibility are server-side and race-safe.
- **III. Real Authorization**: PASS — admin CRUD enforced by DB role server-side, audited; not hidden UI.
- **IV / V**: PASS — regression tests for each BUG-VERIFIED finding.

Migration safety is a constitution concern (no prod mutation during planning). The migration is authored and tested on the test DB only; production application is gated by workstream 011. Documented, not a violation.

## Project Structure

```text
backend/
├── alembic/versions/00NN_promotions_caps_and_ledger.py   # NEW (down_revision = current head; reconcile via 011)
├── app/
│   ├── models/promotion.py            # add cap/scope/window fields; redemption ledger model
│   ├── services/commerce_service.py   # atomic redemption in order txn; re-validate at apply+checkout
│   └── controllers/ (admin)           # admin promotions CRUD under require_role([ADMIN])
└── tests/
    ├── test_promotion_caps_race.py    # NEW (SC-001/003)
    ├── test_promotion_scope.py        # NEW (SC-002)
    └── test_admin_promotions_rbac.py  # NEW (SC-004)
frontend/
└── src/ (admin promotions view; cart stale-promo clearing UX)
```

**Structure Decision**: Web app; one migration shared across customer + admin surfaces per audit guidance.

## Complexity Tracking

> No violations. The migration-ordering risk is tracked and gated by workstream 011, not justified as a complexity exception here.
