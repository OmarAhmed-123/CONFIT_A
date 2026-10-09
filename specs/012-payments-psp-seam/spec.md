# Feature Specification: Payments — Honest Demo Mode & Real-PSP Integration Seam

**Feature Branch**: `012-payments-psp-seam`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings CUS-04, CUS-06, CUS-07, CUS-08 (`CUSTOMER_REPAIR_PLAN.md`); positives CUS-06 (live payments fail-closed in demo mode), CUS-16 (webhook signature fail-closed). Constitution Principles I, II, IV.

## Problem Context *(evidence)*

- **CUS-07 (VERIFIED):** saved cards are **demo-only** — there is no real vault/PSP token. This is acceptable by design but MUST be honest in the UI.
- **CUS-04 (BUG-VERIFIED):** the demo-payment banner is **always shown** (`CheckoutView.tsx:217-226`), even when not applicable — dishonest/incorrect UI state.
- **CUS-08 (LIKELY):** card entry lacks PSP-grade validation/tokenization; a real-PSP seam needs to be planned so the system can switch from demo to a live processor without rearchitecting.
- **CUS-06 (VERIFIED, positive):** live payments fail closed in demo mode (orchestrator) — must be preserved. **CUS-16 (VERIFIED, positive):** webhook signature verification fails closed — must be preserved.

This workstream makes the current demo mode **honest** and defines a clean **PSP seam** (tokenization, capture, webhooks, idempotency, reconciliation) so a real processor can be integrated later without breaking server-authoritative commerce.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The demo-payment banner is shown only when demo mode is actually active (Priority: P2)

As a customer, I see the demo-payment notice only when payments are actually in demo mode, and never when a real processor is active.

**Why this priority**: CUS-04 BUG-VERIFIED — a persistently-shown banner is misleading.

**Acceptance Scenarios**:

1. **Given** demo mode active, **When** I reach checkout, **Then** the demo banner is shown.
2. **Given** a real processor active, **When** I reach checkout, **Then** the demo banner is NOT shown.

---

### User Story 2 - Saved cards and card entry are honestly labeled in demo mode (Priority: P2)

As a customer, I am clearly and honestly told that saved cards are demo-only (not a real vaulted card) while in demo mode.

**Why this priority**: CUS-07 — honesty about what is stored/charged (Principle IV).

**Acceptance Scenarios**:

1. **Given** demo mode, **When** I view saved cards, **Then** they are labeled as demo and no real card data is implied or stored.
2. **Given** demo mode, **When** I "save" a card, **Then** no real PAN/token is persisted; only a demo reference exists.

---

### User Story 3 - A real-PSP seam exists for future live payments (Priority: P2)

As the platform, there is a well-defined payment-processor interface (tokenize, authorize/capture, refund, webhook, idempotency, reconciliation) so a real PSP can be integrated without changing the commerce core, and live mode fails closed until fully configured.

**Why this priority**: CUS-08 — avoids a rewrite later; preserves CUS-06/16 positives.

**Acceptance Scenarios**:

1. **Given** the PSP seam, **When** a provider is not fully configured, **Then** live payments fail closed (CUS-06 preserved) with an honest state.
2. **Given** a webhook, **When** received, **Then** its signature is verified and it fails closed on mismatch (CUS-16 preserved); capture/refund are idempotent.
3. **Given** the commerce core, **When** payments switch demo↔live, **Then** server-authoritative totals (workstream 001) are unchanged — the PSP only moves money for the server-computed amount.

### Edge Cases

- Duplicate webhook delivery (idempotency key).
- Partial capture / refund reconciliation to the ledger.
- Card validation errors surfaced honestly without exposing PSP internals.
- No secret values (PSP keys) are ever logged or committed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The demo-payment banner MUST render only when demo mode is actually active (driven by server/config state, not hardcoded). (CUS-04)
- **FR-002**: In demo mode, saved cards and card entry MUST be honestly labeled as demo and MUST NOT persist real card data/tokens. (CUS-07, Principle IV)
- **FR-003**: A payment-processor interface (seam) MUST define tokenize, authorize/capture, refund, webhook verification, idempotency, and reconciliation, decoupled from the commerce core. (CUS-08)
- **FR-004**: Live payments MUST fail closed until the PSP is fully configured. (CUS-06 preserved)
- **FR-005**: Webhook signature verification MUST fail closed on mismatch; capture/refund MUST be idempotent. (CUS-16 preserved)
- **FR-006**: The PSP MUST only move the server-authoritative amount computed by `price_quote()` (workstream 001); the client never determines the charge. (Principle II)
- **FR-007**: No PSP secret values are logged, committed, or exposed; only variable NAMES/presence are referenced.

### Key Entities

- **Payment Mode**: demo | live (config/server-driven).
- **PSP Adapter**: interface for tokenize/authorize/capture/refund/webhook.
- **Payment Record / Webhook Event**: idempotent, reconciled to order + (ad) ledgers.

## Success Criteria *(mandatory)*

- **SC-001**: Demo banner appears iff demo mode is active (test across both modes).
- **SC-002**: In demo mode, no real card token/PAN is persisted; saved cards are labeled demo (test-verified).
- **SC-003**: The PSP adapter interface exists with contract tests; an unconfigured live provider fails closed with an honest state (regression for CUS-06).
- **SC-004**: Webhook mismatch is rejected; duplicate webhooks are idempotent (regression for CUS-16).
- **SC-005**: The charged amount equals the `price_quote()` total for the order in 100% of tested cases (ties workstream 001).
- **SC-006**: A secret scan of payment code/logs/responses finds 0 PSP secret values.

## Assumptions

- No real PSP is integrated or charged during planning; this workstream defines the seam and makes demo mode honest. Live-provider selection/config is a later, authorized step.
- The charge amount is always the server-computed total from workstream 001.
