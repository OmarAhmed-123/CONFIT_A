# Feature Specification: Brand Account Provisioning & Team RBAC

**Feature Branch**: `005-brand-provisioning-rbac`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings BRD-01, BRD-02 (`BRAND_OWNER_REPAIR_PLAN.md`); positives BRD-09 (tenant isolation fail-closed, `brand_service.py:203-221`), BRD-10 (IDOR regression tests). Constitution Principle III.

## Problem Context *(evidence)*

- **BRD-01 (GAP):** brand onboarding is lead-capture only (`LeadForm`). Submitting a lead creates **no brand account** — there is no provisioning path from lead → brand account → login → dashboard.
- **BRD-02 (GAP):** `BrandProfile.user_id` is 1:1, so a brand is a single owner with no team members and no role-based access within the brand. The `UserRole` enum already defines BRAND_OWNER/BRAND_MANAGER/BRAND_STAFF (`models/user.py:12-14`) but there is no membership model to use them.

Tenant isolation already fails closed (BRD-09) with IDOR regression tests (BRD-10); provisioning and RBAC must preserve that.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lead becomes a usable brand account (Priority: P1)

As an approved brand applicant, my lead is provisioned into a brand account whose owner can log in and reach the brand dashboard.

**Why this priority**: BRD-01 — without provisioning, the entire brand portal is unreachable by real partners.

**Acceptance Scenarios**:

1. **Given** an approved lead, **When** provisioning runs, **Then** a BrandProfile and an owner user (role BRAND_OWNER) are created and the owner can log in.
2. **Given** a provisioned owner, **When** they log in, **Then** they land on their brand dashboard scoped to their brand only (BRD-09 preserved).
3. **Given** registration, **When** a user self-registers, **Then** they cannot self-assign a brand role (ADM-02 preserved).

---

### User Story 2 - Brands have teams with roles (Priority: P1)

As a brand owner, I can invite team members and assign BRAND_MANAGER or BRAND_STAFF roles, and each role's permissions are enforced server-side within my brand only.

**Why this priority**: BRD-02 — real brands are multi-user; 1:1 blocks delegation.

**Acceptance Scenarios**:

1. **Given** a brand owner, **When** they add a team member with a role, **Then** a membership (brand_id, user_id, role) is created.
2. **Given** a BRAND_STAFF member, **When** they attempt a manager-only action, **Then** it is rejected server-side.
3. **Given** a member of brand A, **When** they access brand B's resources, **Then** they are denied (tenant isolation, IDOR tests stay green).

### Edge Cases

- Removing the last owner (prevent brand orphaning).
- Re-inviting an existing user; a user belonging to multiple brands (scope resolution).
- Migrating existing 1:1 BrandProfiles into the new membership model without data loss.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An explicit provisioning path MUST create a BrandProfile + owner user (role BRAND_OWNER) from an approved lead; the owner can authenticate and reach the dashboard. (BRD-01)
- **FR-002**: A brand membership model MUST exist (brand_id, user_id, role ∈ {BRAND_OWNER, BRAND_MANAGER, BRAND_STAFF}), replacing the 1:1 assumption. (BRD-02)
- **FR-003**: Every brand action MUST enforce role AND tenant scope server-side (object-level ownership, fail closed); the existing isolation (BRD-09) and IDOR tests (BRD-10) MUST remain green.
- **FR-004**: Role self-escalation MUST be impossible; only authorized owners/managers assign roles within their brand. (Principle III, ADM-02)
- **FR-005**: A migration MUST move existing 1:1 BrandProfiles into the membership model with no data loss, forward-chained and reconciled per workstream 011.

### Key Entities

- **BrandProfile**: existing; becomes 1:many with members.
- **BrandMembership**: brand_id, user_id, role, status.
- **Lead**: existing lead capture; gains a provisioning transition.

## Success Criteria *(mandatory)*

- **SC-001**: An approved lead results in an owner who logs in and sees only their brand (automated E2E).
- **SC-002**: Role matrix enforced: for each (role × action) pair, allowed actions succeed and disallowed actions are 403 server-side.
- **SC-003**: Cross-tenant access attempts are denied 100% (IDOR suite extended, stays green).
- **SC-004**: The 1:1→membership migration preserves all existing brands and owners (row-count + spot-check assertions on test DB).

## Assumptions

- Lead approval is an admin action (ties to workstream 004 governance) or an automated rule; provisioning is idempotent.
- Email invitations are NOT sent during planning; invitation flow is designed but not exercised against a real mailer.
