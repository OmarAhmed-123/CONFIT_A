# Implementation Plan: Advertising Delivery Loop, Ledger Billing & Analytics

**Branch**: `007-advertising-loop` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Restore the end-to-end advertising loop: add a consumer-facing ad-serving path and consumer-context (non-brand-auth) impression/click tracking with anti-fraud safeguards (BRD-05); replace counter-based spend with an append-only billing ledger that dashboard and admin KPIs reconcile to (BRD-06, ADM-14); enforce budget pacing/caps (BRD-13); and surface statements/PDF (BRD-07) and funnel/attribution/order visibility (BRD-08/16/14). All ad-money math is server-authoritative and exact.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, SQLAlchemy 2, Alembic, Pydantic v2; slowapi (rate/abuse); PDF generation for statements
**Storage**: `ad_billing_ledger` (append-only), campaign pacing fields, impression/click records; `Numeric(12,2)` for amounts
**Testing**: pytest (consumer tracking, ledger reconciliation, cap pacing, statement totals, attribution regression), frontend (analytics/billing views)
**Target Platform**: Vercel serverless
**Project Type**: Web application
**Constraints**: anti-fraud on public tracking endpoint; exact money; ledger is the single source of spend.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — reconciliation + E2E tracking prove the loop; no "working ads" claim without SC-001/002.
- **II. Server-Authoritative Commerce**: PASS/core — ad money is server-side, exact, ledger-backed.
- **III**: PASS — brand views remain tenant-scoped; consumer tracking is intentionally unauthenticated but safeguarded.
- **IV**: PASS — no fabricated impressions. **V**: PASS.

No violations.

## Project Structure

```text
backend/
├── alembic/versions/00NN_ad_ledger_and_pacing.py  # NEW (reconcile via 011)
├── app/
│   ├── models/ (ad_billing_ledger, campaign pacing, impression/click)
│   ├── services/ (ad serving selection, tracking w/ anti-fraud, ledger spend, statements)
│   └── controllers/ (public ad-serve + track; brand billing/analytics)
└── tests/
    ├── test_ad_consumer_tracking.py    # NEW (SC-001)
    ├── test_ad_ledger_reconcile.py     # NEW (SC-002)
    ├── test_ad_budget_pacing.py        # NEW (SC-003)
    └── test_ad_statement_totals.py     # NEW (SC-004)
frontend/
└── src/views/ (consumer ad placements; brand analytics/billing/statement download)
```

**Structure Decision**: Web app; introduce a public, safeguarded tracking surface distinct from brand-authenticated endpoints.

## Complexity Tracking

> No violations. A public tracking endpoint is required by BRD-05 (consumers are unauthenticated); it is mitigated by rate/abuse controls rather than removed.
