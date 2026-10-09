# Feature Specification: UI/UX, Accessibility (WCAG 2.2 AA), i18n/RTL & Motion System

**Feature Branch**: `010-uiux-accessibility-system`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Cross-cutting UI/a11y findings across all five audits — ADM-18/19, CUS-19/21/22, BRD-12/15, VTON-13/14, STY-14, and the shared A11Y-05 / MOT-06 / IMG-03 references (`§14`/`§15` in the plans). Constitution: Accessibility (WCAG 2.2 AA) + honest imagery.

## Problem Context *(evidence)*

The five audits repeatedly surface the same cross-cutting UI/UX debts, strongest on B2B and AI surfaces:

- **Accessibility (A11Y-05):** hardcoded English strings, emoji-as-UI, missing accessible names/labels — called out explicitly for VTON upload (VTON-13, BUG-VERIFIED P1 a11y), stylist drawer (STY-14), admin/brand B2B views (ADM-19, BRD-15), and consumer checkout (CUS-19).
- **Honest imagery (IMG-03):** raw `<img>` used instead of `HonestProductImage` (e.g., try-on modal VTON-14) — placeholder/broken images can masquerade as real content, violating the honesty principle.
- **Motion (MOT-06):** animations not consistently respecting `prefers-reduced-motion`.
- **Dynamic/stateful UX:** order status timeline not live (CUS-21); empty/error/loading states uneven across consumer views (CUS-22); brand/admin dashboards static (BRD-12, ADM-18 confirmation/rollback UX).
- **i18n/RTL:** EN/AR + RTL coverage incomplete on B2B views (ADM-19, BRD-15).

This workstream provides the shared design-system primitives the other workstreams consume, rather than each re-solving a11y/i18n/motion independently.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every interactive surface is keyboard- and screen-reader-accessible (Priority: P1)

As a keyboard or screen-reader user, I can operate uploads, the stylist drawer, checkout, and B2B consoles with accessible names, focus management, and no emoji-only controls.

**Why this priority**: VTON-13 is a BUG-VERIFIED P1 a11y defect; a11y is a constitution target and legal concern.

**Acceptance Scenarios**:

1. **Given** the VTON upload / stylist drawer / checkout / admin & brand views, **When** audited with axe and manual keyboard/SR testing, **Then** there are no critical violations, all controls have accessible names, and focus is managed.
2. **Given** emoji used as a control, **When** reviewed, **Then** it is replaced or given an accessible label/role.

---

### User Story 2 - Product imagery is always honest (Priority: P1)

As a user, I never see a broken/placeholder image presented as a real product; all product imagery flows through `HonestProductImage`.

**Why this priority**: IMG-03 / VTON-14 — honesty principle.

**Acceptance Scenarios**:

1. **Given** any product/try-on image, **When** rendered, **Then** it uses `HonestProductImage` (not raw `<img>`) and degrades to an honest placeholder state on load failure.

---

### User Story 3 - Internationalization and RTL are complete (Priority: P2)

As an Arabic-speaking user, all surfaces (including B2B) are fully translated and render correctly in RTL.

**Acceptance Scenarios**:

1. **Given** AR locale, **When** I use admin/brand/consumer/AI surfaces, **Then** strings are translated (no hardcoded EN) and layout is correct in RTL.

---

### User Story 4 - Motion respects user preferences and states are consistent (Priority: P2)

As a user sensitive to motion, animations respect `prefers-reduced-motion`; all views have consistent empty/loading/error states and live status where expected.

**Acceptance Scenarios**:

1. **Given** `prefers-reduced-motion`, **When** animations would play, **Then** they are reduced/disabled.
2. **Given** consumer/B2B views, **When** loading/empty/error occurs, **Then** a consistent, honest state is shown; order tracking updates live (CUS-21).

### Edge Cases

- Mixed LTR/RTL content (numbers, currency) within AR layout.
- Long translated strings overflowing B2B tables.
- Reduced-motion with essential state-change cues (must remain perceivable without motion).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All interactive controls MUST have accessible names and keyboard operability; emoji MUST NOT be the sole control affordance. (A11Y-05, VTON-13, STY-14, ADM-19, BRD-15, CUS-19)
- **FR-002**: All product/try-on imagery MUST use `HonestProductImage` with an honest failure state. (IMG-03, VTON-14)
- **FR-003**: No hardcoded user-facing strings; all surfaces (incl. B2B) MUST be fully translated EN/AR with correct RTL. (ADM-19, BRD-15)
- **FR-004**: All animations MUST respect `prefers-reduced-motion`. (MOT-06)
- **FR-005**: Consumer and B2B views MUST have consistent empty/loading/error states; order tracking MUST update live. (CUS-21/22, BRD-12, ADM-18)
- **FR-006**: Admin actions MUST have consistent confirmation + optimistic-rollback UX. (ADM-18)
- **FR-007**: The workstream MUST deliver shared primitives/components the other workstreams consume (single source for a11y/i18n/motion/honest-image patterns).

### Key Entities

- **Design-system primitives**: accessible form controls, `HonestProductImage`, i18n message catalog, motion wrapper honoring reduced-motion, standard empty/loading/error components.

## Success Criteria *(mandatory)*

- **SC-001**: axe automated scan reports 0 critical/serious violations on VTON upload, stylist drawer, checkout, and admin/brand consoles; manual keyboard/SR pass recorded.
- **SC-002**: A structural check finds 0 raw `<img>` for product/try-on imagery (all via `HonestProductImage`).
- **SC-003**: An i18n lint finds 0 hardcoded user-facing strings on targeted surfaces; AR/RTL visual checks pass.
- **SC-004**: With `prefers-reduced-motion`, no non-essential animation plays (automated + manual).
- **SC-005**: Each targeted view has defined empty/loading/error states; order tracking shows live updates.

## Assumptions

- `HonestProductImage` and an i18n framework already exist (EN/AR) per the constitution tech stack; this workstream completes coverage and standardizes usage.
- Accessibility verification tracks automated (axe) and manual results separately (Principle V).
