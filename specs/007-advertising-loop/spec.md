# Feature Specification: Advertising Delivery Loop, Ledger Billing & Analytics

**Feature Branch**: `007-advertising-loop`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings BRD-05, BRD-06, BRD-07, BRD-08, BRD-13, BRD-14, BRD-16 (`BRAND_OWNER_REPAIR_PLAN.md`); ADM-14 (`ADMIN_REPAIR_PLAN.md`). Constitution Principles I, II.

## Problem Context *(evidence)*

- **BRD-05 (BUG-VERIFIED, P1):** the ad delivery loop is broken — there is **no consumer-facing impression-serving path**, and ad tracking is **brand-authenticated** (so the brand would have to be the viewer). Impressions/clicks cannot be recorded from real consumer traffic. The whole paid-advertising product is non-functional end-to-end.
- **BRD-06 (BUG-VERIFIED, P2):** dashboard ad spend is computed from **counters, not a ledger**, so spend can drift and is not auditable. (ADM-14 is the admin-side mirror: KPIs from counters, not a ledger.)
- **BRD-07 (GAP, P2):** billing statement/PDF is backend-only — no UI/download.
- **BRD-13 (LIKELY, P2):** no campaign budget pacing / cap enforcement (ties BRD-06).
- **BRD-08 (GAP), BRD-16/14 (LIKELY):** funnel analytics are computed but not displayed; revenue attribution (double-count already fixed server-side) and brand-side order/returns visibility are not surfaced.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ads are served to consumers and tracked correctly (Priority: P1)

As a consumer, I see brand ad placements in the storefront; as the platform, each genuine impression/click is recorded against the campaign from consumer traffic (not brand-authenticated), with abuse/fraud safeguards.

**Why this priority**: BRD-05 — the advertising product does not work at all without this.

**Acceptance Scenarios**:

1. **Given** an active, funded campaign, **When** a consumer views a placement, **Then** an impression is recorded attributed to that campaign, from the consumer context.
2. **Given** a consumer clicks an ad, **When** the click is handled, **Then** a click is recorded and the consumer is routed to the product.
3. **Given** the tracking endpoint, **When** it is called, **Then** it does NOT require brand authentication to record consumer impressions (fixing the broken loop), while applying anti-fraud/rate safeguards.

---

### User Story 2 - Ad spend is ledger-based, auditable, and budget-paced (Priority: P2)

As a brand, my ad spend is derived from an append-only ledger of billable events (not drifting counters), and campaign budgets/caps are enforced so I never overspend.

**Why this priority**: BRD-06/13 (+ADM-14) — financial accuracy/auditability of spend. Principle II applies to ad money.

**Acceptance Scenarios**:

1. **Given** billable ad events, **When** spend is computed, **Then** it equals the sum of ledger entries (reconciliation holds; no counter drift).
2. **Given** a campaign at its budget cap, **When** further billable events occur, **Then** serving/billing stops (pacing/cap enforced).
3. **Given** admin KPIs, **When** displayed, **Then** they are sourced from the same ledger (ADM-14).

---

### User Story 3 - Brands see billing statements and analytics (Priority: P2)

As a brand, I can view/download a billing statement (PDF) and see my funnel analytics, revenue attribution, and order/returns visibility for my products.

**Why this priority**: BRD-07/08/16/14 — data exists but is not surfaced.

**Acceptance Scenarios**:

1. **Given** a billing period, **When** I open billing, **Then** I can view and download a statement with ledger-consistent totals.
2. **Given** funnel/attribution data, **When** I open analytics, **Then** it is displayed (attribution not double-counted — existing server fix preserved).

### Edge Cases

- Impression/click fraud (bots, repeated clicks): dedupe/rate-limit.
- Budget cap reached mid-serving: stop cleanly without negative balance.
- Ledger reconciliation after refunds/adjustments.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A consumer-facing ad-serving path MUST exist that selects and renders eligible, funded placements. (BRD-05)
- **FR-002**: Impression/click tracking MUST record from consumer traffic WITHOUT requiring brand authentication, with anti-fraud/rate safeguards. (BRD-05)
- **FR-003**: Ad spend MUST be derived from an append-only billing ledger; dashboard and admin KPIs MUST reconcile to the ledger (no counter drift). (BRD-06, ADM-14)
- **FR-004**: Campaign budget/cap pacing MUST be enforced so serving/billing stops at the cap. (BRD-13)
- **FR-005**: Billing statements MUST be viewable and downloadable (PDF) with ledger-consistent totals. (BRD-07)
- **FR-006**: Funnel analytics, revenue attribution (no double-count), and brand order/returns visibility MUST be surfaced in the brand UI. (BRD-08/16/14)
- **FR-007**: All ad-money math MUST be server-authoritative and exact (`Numeric(12,2)`), consistent with Principle II.

### Key Entities

- **Campaign**: budget, cap, status, pacing.
- **Ad Billing Ledger**: append-only billable events (impression/click/CPM/CPC), amounts.
- **Placement/Impression/Click**: serving + tracking records.

## Success Criteria *(mandatory)*

- **SC-001**: An automated E2E records an impression and a click from a consumer context (no brand auth) attributed to the right campaign.
- **SC-002**: Computed spend equals the ledger sum across a generated event set (reconciliation == 0 drift).
- **SC-003**: A campaign at cap stops serving/billing; balance never goes negative.
- **SC-004**: A brand downloads a statement whose total equals the ledger total for the period.
- **SC-005**: Funnel/attribution views render real data; attribution double-count regression stays fixed.

## Assumptions

- Billing model (CPM/CPC) follows existing config; this workstream makes it ledger-backed and consumer-served, not a new pricing model.
- No real ad spend is charged during planning; verification uses the test DB.
