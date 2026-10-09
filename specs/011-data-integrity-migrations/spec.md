# Feature Specification: Data Integrity & Migration Reconciliation (Alembic Chain Governance)

**Feature Branch**: `011-data-integrity-migrations`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings DB-01 (recently-viewed duplicates / CUS-14), and the migration-chain governance that every schema-touching workstream (002, 005, 006, 007, 008) depends on, including the §21 production-vs-repo reconciliation concern. Constitution: Additional Constraints (Backend/Data) + Safety (no prod migration during planning).

## Problem Context *(evidence)*

- **Repo migration head is `0034_mfa_email_codes`** (`backend/alembic/versions/0034_mfa_email_codes.py`: `revision="0034_mfa_email_codes"`, `down_revision="0033_email_preferences"`). There is **no `0035` in the repo**.
- The `CUSTOMER_REPAIR_PLAN.md` and `VIRTUAL_TRY_ON_REPAIR_PLAN.md` reference a **production** migration `0035_product_images` that is "prod-ahead" of the repo. Per the assignment's §21, **an earlier report does not prove current production state**, and this cannot be safely re-verified during a planning assignment (no prod access / no prod mutations). This is a **latent divergence risk**: if multiple workstreams each author a `0035_*` with `down_revision=0034`, they will collide, and a repo `0035` could conflict with the production `0035_product_images`.
- **DB-01 (BUG-VERIFIED via CUS-14):** recently-viewed has duplicate rows; needs a unique `(user_id, product_id)` + upsert.
- **Verified positives to preserve:** money columns are `Numeric(12,2)` (DB-19) — must not become float; unique cart line (DB-20).

This workstream is the **single authority for Alembic chain ordering** so the six migrations proposed across workstreams (002 promotions, 005 memberships, 006 product-lifecycle/import, 007 ad-ledger, 008 tryon-image-drop, 011 recently-viewed-unique) form one linear, collision-free chain and are reconciled with the true production state before any execution.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The repo and production migration state are reconciled before any new migration is written (Priority: P1)

As the platform, before authoring new migrations, the true production Alembic head is established (via an authorized read-only check — NOT during this planning assignment) and the repo chain is reconciled so there is exactly one head and no duplicate revision ids.

**Why this priority**: §21 — a wrong assumption about the prod head corrupts the migration chain and risks a failed/destructive deploy.

**Acceptance Scenarios**:

1. **Given** an authorized read-only check of production `alembic_current`, **When** performed, **Then** the real prod head is recorded and compared to repo head `0034`.
2. **Given** a prod-only `0035_product_images`, **When** reconciling, **Then** it is either imported into the repo chain or explicitly superseded, so repo and prod share one linear history with no duplicate `0035`.
3. **Given** reconciliation is incomplete, **When** any workstream proposes a new migration, **Then** it is BLOCKED until the head is confirmed (gate).

---

### User Story 2 - All new workstream migrations form one linear, collision-free chain (Priority: P1)

As the platform, the migrations from workstreams 002/005/006/007/008/011 are numbered sequentially off the confirmed head with no two sharing a `down_revision`.

**Why this priority**: prevents multiple-heads / collision failures.

**Acceptance Scenarios**:

1. **Given** six proposed migrations, **When** ordered, **Then** `alembic heads` returns exactly one head after applying all on the test DB.
2. **Given** the chain, **When** `alembic upgrade head` then `downgrade base` runs on the test DB, **Then** both succeed (reversible).

---

### User Story 3 - Recently-viewed is deduplicated (Priority: P2)

As a customer, my recently-viewed list has no duplicates.

**Why this priority**: DB-01/CUS-14 — UI jitter + wasted rows.

**Acceptance Scenarios**:

1. **Given** repeated views of the same product, **When** recorded, **Then** a unique `(user_id, product_id)` constraint + upsert yields one row (most-recent timestamp).

### Edge Cases

- Production has drifted further than reported (more than one unknown revision) — gate must catch "unknown head".
- A data back-fill in a workstream migration must be idempotent and safe on large tables.
- Money columns must never be altered to float (DB-19).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The true production Alembic head MUST be established via an authorized, read-only check BEFORE any new migration is applied to production; this check is NOT performed during the planning assignment and is recorded as a prerequisite gate. (§21)
- **FR-002**: The repo migration chain MUST be reconciled so repo and production share one linear history with exactly one head and no duplicate revision ids (resolve the prod `0035_product_images` vs repo head `0034`). (§21)
- **FR-003**: All new workstream migrations (002/005/006/007/008/011) MUST chain sequentially off the confirmed head; no two may share a `down_revision`.
- **FR-004**: `alembic upgrade head` and `downgrade base` MUST succeed on the test DB for the full combined chain (reversible, single head).
- **FR-005**: Recently-viewed MUST enforce unique `(user_id, product_id)` with upsert. (DB-01/CUS-14)
- **FR-006**: Money columns MUST remain `Numeric(12,2)`; no migration may convert them to float. (DB-19)
- **FR-007**: No migration is executed against production during planning; execution is an explicitly authorized, gated step. (Constitution Safety)

### Key Entities

- **Alembic Revision Graph**: the linear chain; one head.
- **RecentlyViewed**: gains unique `(user_id, product_id)`.

## Success Criteria *(mandatory)*

- **SC-001**: A documented, authorized read-only production-head check procedure exists; the planning artifact records that the prod head is UNVERIFIED-pending-authorized-check (honest status, §21).
- **SC-002**: On the test DB, applying all six workstream migrations yields exactly one `alembic heads` and `upgrade head`/`downgrade base` both succeed.
- **SC-003**: No two migration files share a `down_revision` (structural check).
- **SC-004**: Recently-viewed dedup test passes (one row per user+product).
- **SC-005**: A grep/structural check confirms 0 money columns converted away from `Numeric(12,2)`.

## Assumptions

- Production access for the head check is OUT OF SCOPE for this planning assignment; the gate records it as a required, authorized prerequisite before any deploy/migration wave.
- The six workstream migrations are authored under this workstream's numbering authority to avoid collisions.
