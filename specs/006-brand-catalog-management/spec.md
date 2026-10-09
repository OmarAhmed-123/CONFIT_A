# Feature Specification: Brand Catalog Management (Product Lifecycle, Media, Async Import)

**Feature Branch**: `006-brand-catalog-management`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings BRD-03, BRD-04, BRD-11, BRD-18 (`BRAND_OWNER_REPAIR_PLAN.md`). Constitution Principles I, IV, and platform constraint (serverless, ephemeral FS).

## Problem Context *(evidence)*

- **BRD-03 (GAP):** no product create/publish/archive for partners. `ProductCreateInput` exists but is **unused** — partners cannot manage their own catalog.
- **BRD-04 (BUG-VERIFIED):** catalog import runs **synchronously in-request**, risking Vercel timeout for non-trivial imports.
- **BRD-11 (LIKELY):** no product media manager / image pipeline for partners; depends on `STORAGE_PROVIDER`. On serverless the filesystem is ephemeral, so durable media MUST use real object storage, never local disk.
- **BRD-18 (LIKELY):** catalog import lacks a partial-failure report in the UI (import isolation exists in tests but partners can't see which rows failed).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Partners manage their product lifecycle (Priority: P1)

As a brand member (manager+), I can create, edit, publish, and archive my own products through the UI, scoped to my brand only.

**Why this priority**: BRD-03 — core partner capability currently absent.

**Acceptance Scenarios**:

1. **Given** a brand manager, **When** they create a product via `ProductCreateInput`, **Then** it persists under their brand and can be published/archived.
2. **Given** a BRAND_STAFF role, **When** they attempt a manager-only lifecycle action, **Then** it is rejected server-side (ties to workstream 005).
3. **Given** a member of brand A, **When** they edit a product of brand B, **Then** denied (tenant isolation).

---

### User Story 2 - Catalog import runs asynchronously with a partial-failure report (Priority: P2)

As a brand member, I can upload a catalog import that processes in the background and gives me a per-row success/failure report, without timing out.

**Why this priority**: BRD-04 (timeout risk) + BRD-18 (visibility). High operational value; P2 because small imports currently "work".

**Acceptance Scenarios**:

1. **Given** a large import, **When** submitted, **Then** it enqueues and returns immediately; processing happens out-of-request (no serverless timeout).
2. **Given** an import with some invalid rows, **When** it completes, **Then** valid rows are imported, invalid rows are reported with reasons, and the operation is isolated (one bad row does not fail the batch).

---

### User Story 3 - Durable product media (Priority: P2)

As a brand member, I can upload product images that persist durably (object storage), not on the ephemeral serverless filesystem.

**Why this priority**: BRD-11 — media loss on redeploy/restart is a real risk on Vercel.

**Acceptance Scenarios**:

1. **Given** `STORAGE_PROVIDER` configured, **When** I upload an image, **Then** it is stored in object storage and referenced by URL (survives redeploy).
2. **Given** no storage provider configured, **When** I upload, **Then** the system returns an honest unavailable state (no fake success, Principle IV).

### Edge Cases

- Import encoding/column-mismatch errors; very large files (size/row guardrails).
- Image format/size validation; malicious file rejection.
- Publishing a product with missing required fields.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Partners (manager+) MUST be able to create/edit/publish/archive products via `ProductCreateInput`, scoped to their brand with server-side role + tenant checks. (BRD-03)
- **FR-002**: Catalog import MUST run out-of-request (async job), never inside a single serverless request. (BRD-04)
- **FR-003**: Import MUST be row-isolated and MUST produce a per-row success/failure report visible in the UI. (BRD-18)
- **FR-004**: Product media MUST be stored in a real object-storage provider (never local disk in production); absence of a provider yields an honest unavailable state. (BRD-11, Principle IV)
- **FR-005**: Media uploads MUST validate format/size and reject unsafe files.
- **FR-006**: All catalog actions MUST preserve tenant isolation (BRD-09) and honest product imagery (no placeholder masquerading as real).

### Key Entities

- **Product**: existing; gains partner-driven lifecycle state (draft/published/archived).
- **Import Job**: id, brand_id, status, per-row results.
- **Product Media**: object-storage URL + metadata (not raw bytes in DB).

## Success Criteria *(mandatory)*

- **SC-001**: A manager creates→publishes→archives a product via UI, scoped to their brand; staff is blocked from manager-only actions; cross-tenant edit denied (test-verified).
- **SC-002**: A large import completes without a serverless timeout (processed out-of-request) in an automated test/simulation.
- **SC-003**: An import with mixed valid/invalid rows imports the valid ones and reports each invalid row with a reason.
- **SC-004**: With a storage provider configured, uploaded media survives a simulated redeploy; without one, upload returns an honest 503 (no fake success).

## Assumptions

- The async job mechanism is defined jointly with workstream 008 (both need durable out-of-request processing on serverless); a shared queue/worker abstraction is preferred.
- `STORAGE_PROVIDER` variable NAME is inspected only; no secret values are read or logged.
