# Implementation Plan: Payments — Honest Demo Mode & Real-PSP Seam

**Branch**: `012-payments-psp-seam` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Make demo mode honest — the demo banner (`CheckoutView.tsx:217-226`) renders only when demo mode is actually active (CUS-04) and saved cards are clearly demo-only with no real token stored (CUS-07) — and define a clean PSP adapter seam (tokenize/authorize/capture/refund/webhook/idempotency/reconciliation) so a real processor can be added later without touching the server-authoritative commerce core. Preserve fail-closed live payments (CUS-06) and fail-closed webhook verification (CUS-16). The PSP only ever moves the `price_quote()` amount from workstream 001.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, Pydantic v2, existing payment orchestrator + webhook verifier; config-driven payment mode
**Storage**: Payment records + webhook events (idempotent); no real card data in demo; `Numeric(12,2)`
**Testing**: pytest (mode-gating, fail-closed live, webhook idempotency/mismatch, amount==quote), frontend (banner gating, honest labels)
**Target Platform**: Vercel serverless
**Project Type**: Web application
**Constraints**: no secret exposure; server-authoritative charge amount; fail closed.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — banner/label honesty + fail-closed proven by tests.
- **II. Server-Authoritative Commerce**: PASS/core — PSP moves only the server-computed total.
- **IV. Honest AI & Integrations**: PASS/core — demo clearly labeled; no fake vault; honest unavailability.
- **Secrets constraint**: PASS — names/presence only. **III**: N/A. **V**: PASS.

No violations.

## Project Structure

```text
backend/
├── app/
│   ├── services/ (payment orchestrator: mode gating; PSP adapter interface; reconciliation)
│   └── controllers/ (webhook verify — preserve fail-closed)
└── tests/
    ├── test_payment_mode_gating.py     # NEW (SC-001)
    ├── test_demo_cards_honest.py       # NEW (SC-002)
    ├── test_psp_seam_failclosed.py     # NEW (SC-003, CUS-06)
    └── test_webhook_idempotency.py     # NEW (SC-004, CUS-16)
frontend/
└── src/views/CheckoutView.tsx (banner gated by real demo state; honest saved-card labels)
```

**Structure Decision**: Web app; introduce a PSP adapter interface; no commerce-core change (amount comes from workstream 001).

## Complexity Tracking

> No violations. The adapter seam is the minimal abstraction needed to add a real PSP later without rearchitecting; inlining a specific PSP now is rejected (no provider selected, and it would couple commerce to one vendor).
