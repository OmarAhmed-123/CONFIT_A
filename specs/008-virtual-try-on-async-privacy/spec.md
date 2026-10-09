# Feature Specification: Virtual Try-On — Async Rendering, Partial-Layer Honesty & Biometric Privacy

**Feature Branch**: `008-virtual-try-on-async-privacy`

**Created**: 2026-10-09

**Status**: Draft (planning only)

**Input**: Findings VTON-01..15 (`VIRTUAL_TRY_ON_REPAIR_PLAN.md`), DB-11. Constitution Principles I, IV, V and the data/privacy + serverless platform constraints.

## Problem Context *(evidence)*

- **VTON-02 (BUG-VERIFIED, P1):** the "async job queue" is actually a **synchronous in-request render** (`tryon_service.py:1085-1294`). On Vercel the server `maxDuration` is 300s but the client times out around ~150s (VTON-03), so renders fail from the client side even when the server could finish.
- **VTON-04 (BUG-VERIFIED, P1):** a multi-garment render can report `status="completed"` while `all_layers_verified=false` — **success reported for a partial result**. This is a direct Principle-IV honesty violation.
- **VTON-06 / DB-11 (BUG-VERIFIED, P1):** person photos are persisted as **raw base64 in DB** Text columns (`tryon_jobs`/`tryon_sessions`). This is sensitive, biometric-adjacent data at rest — a privacy violation of the constitution's data/privacy constraint.
- **VTON-05 (BUG-VERIFIED, P2):** guest job polling is broken without a `delivery_token` (`tryon_service.py:1673-1735`).
- **VTON-07 (GAP), VTON-08/09/10 (LIKELY):** no content-safety screening on upload; no size/dimension/format guardrails; no retry/backoff on transient worker errors; no per-user cost/rate budget for GPU calls.
- **VTON-01 (VERIFIED):** `.env` lacks `VTON_WORKER_*` keys (feature off locally) — this is expected; readiness must report availability honestly.
- **VTON-13 (BUG-VERIFIED, P1 a11y):** upload UI has hardcoded EN, emoji, no accessible names (ties workstream 010). **VTON-14 (BUG-VERIFIED):** try-on modal uses raw `<img>` not `HonestProductImage`. **VTON-15 (LIKELY):** no result gallery/history.

**Verified positives to preserve:** honest 503 when worker absent (VTON-11); delivery token hashed + short-lived + purged on claim (VTON-12, `tryon_service.py:1428-1452`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Try-on renders asynchronously without client timeout (Priority: P1)

As a user, I submit a try-on and immediately get a job id + poll URL; the render happens out-of-request; I poll for status and never hit a client timeout while the server is still working.

**Why this priority**: VTON-02/03 — the core feature fails for realistic render times.

**Acceptance Scenarios**:

1. **Given** a submitted try-on, **When** I submit, **Then** I receive `202 {job_id, poll_url, delivery_token}` immediately (no synchronous render in the request).
2. **Given** a running job, **When** I poll, **Then** I get `PENDING|RUNNING|COMPLETED|PARTIAL|FAILED` with reasons; the client never times out while the server progresses.
3. **Given** a transient worker error, **When** it occurs, **Then** the job retries with backoff (VTON-09) before failing honestly.
4. **Given** no worker configured, **When** I submit, **Then** I get an honest 503 (VTON-11 preserved), not a fake result.

---

### User Story 2 - Partial renders are never reported as success (Priority: P1)

As a user doing a multi-garment try-on, a result is only `COMPLETED` if every layer is verified; otherwise it is `PARTIAL` with per-layer reasons.

**Why this priority**: VTON-04 — fabricated success violates Principle IV and misleads the user.

**Acceptance Scenarios**:

1. **Given** a multi-layer render where `all_layers_verified=false`, **When** the job finishes, **Then** status is `PARTIAL` (never `COMPLETED`) with per-layer reasons.
2. **Given** all layers verified, **When** finished, **Then** status is `COMPLETED`.

---

### User Story 3 - Person photos are never stored as raw bytes in the DB (Priority: P1)

As a user, my person photo is not persisted as raw base64 in the database; it lives in short-TTL encrypted storage or is discarded, and account deletion scrubs it.

**Why this priority**: VTON-06/DB-11 — biometric-adjacent data at rest; privacy/compliance risk.

**Acceptance Scenarios**:

1. **Given** a try-on submission, **When** the job is stored, **Then** no raw image bytes/base64 are in `tryon_jobs`/`tryon_sessions`; only metadata + hashed delivery token remain (VTON-12 preserved).
2. **Given** account deletion, **When** it runs, **Then** all associated try-on images are scrubbed.
3. **Given** the migration removing the Text image columns, **When** applied, **Then** it dual-writes/back-fills safely before dropping columns and is forward-chained (reconcile via workstream 011; mind prod `0035_product_images`).

---

### User Story 4 - Guests can poll by job id; results are token-gated (Priority: P2)

As a guest, I can poll my job by its id, and I can claim the resulting image only with a valid delivery token, which is purged on claim/expiry.

**Why this priority**: VTON-05 — guest polling is currently broken.

**Acceptance Scenarios**:

1. **Given** a guest job id, **When** I poll, **Then** I get status without needing a session.
2. **Given** a delivery token, **When** I claim the image, **Then** it is served once and purged (VTON-12 preserved); an invalid/expired token is rejected.

---

### User Story 5 - Upload safety, guardrails, and budgets (Priority: P2)

As the platform, uploads are content-safety screened and size/format-guarded, and per-user GPU cost/rate budgets prevent abuse.

**Why this priority**: VTON-07/08/10 — safety and cost control.

**Acceptance Scenarios**:

1. **Given** an unsafe or oversized/invalid upload, **When** submitted, **Then** it is rejected at intake with a clear reason.
2. **Given** a user over their GPU budget, **When** they submit, **Then** they are rate/cost-limited honestly.

### Edge Cases

- `test_vton_pose_artifact_regression.py` requires `libEGL.so.1` (mediapipe) which is absent in the headless container — this is an ENVIRONMENTAL failure, not an app defect; the test must pass in a GL-capable environment or skip with a recorded reason (not silently ignored).
- Worker returns malformed output; job orphaned if worker dies (timeout → FAILED with reason).
- Delivery token replay after expiry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Try-on submission MUST return `202 {job_id, poll_url, delivery_token}` and MUST NOT run the render synchronously in the request. (VTON-02/03)
- **FR-002**: A background worker MUST perform the render out-of-request with retry/backoff on transient errors and update job state. (VTON-02/09)
- **FR-003**: Poll MUST return `PENDING|RUNNING|COMPLETED|PARTIAL|FAILED` with per-layer reasons; a partial result MUST NEVER be `COMPLETED`. (VTON-04)
- **FR-004**: Person images MUST NOT be stored as raw base64 in the DB; use short-TTL encrypted storage or discard; account deletion scrubs them. (VTON-06/DB-11)
- **FR-005**: The migration removing Text image columns MUST dual-write/back-fill then drop, forward-chained and reconciled with production migration state (workstream 011).
- **FR-006**: Guests MUST be able to poll by job id; image claim MUST be delivery-token-gated and purged on claim/expiry (preserve VTON-12). (VTON-05)
- **FR-007**: Uploads MUST be content-safety screened and size/dimension/format-guarded at intake. (VTON-07/08)
- **FR-008**: Per-user GPU cost/rate budgets MUST be enforced. (VTON-10)
- **FR-009**: Readiness MUST honestly report whether VTON is configured (no secrets); honest 503 when the worker is absent MUST be preserved. (VTON-01/11)
- **FR-010**: Upload/result UI MUST be accessible (names, i18n/RTL, reduced-motion) and use `HonestProductImage` (not raw `<img>`); a result gallery/history SHOULD be provided. (VTON-13/14/15 — aligns with workstream 010)

### Key Entities

- **TryOn Job**: id, status, per-layer verification, metadata (NO raw image bytes), hashed delivery token.
- **Person Image (transient)**: short-TTL encrypted blob or discarded; never in DB as base64.
- **Delivery Token**: hashed, short-lived, single-claim (existing positive).

## Success Criteria *(mandatory)*

- **SC-001**: Submission returns `202` with job id in <1s; a render exceeding the old ~150s client limit completes via polling with no client timeout (simulated).
- **SC-002**: 100% of `all_layers_verified=false` renders report `PARTIAL`, 0 report `COMPLETED` (regression for VTON-04).
- **SC-003**: A scan of `tryon_jobs`/`tryon_sessions` rows after submission finds 0 raw image/base64 payloads; account deletion leaves 0 residual images.
- **SC-004**: Guest polls by id successfully; image claim works once then is purged; expired/invalid tokens rejected.
- **SC-005**: Unsafe/oversized uploads rejected at intake; over-budget users rate-limited.
- **SC-006**: Readiness reports VTON availability truthfully with no secret values; honest 503 preserved when unconfigured.

## Assumptions

- The async mechanism is shared with workstream 006 (both need durable out-of-request processing on serverless).
- `VTON_WORKER_*` variable NAMES only are inspected; no secret values are read/logged; no paid GPU jobs are triggered during planning.
- Short-TTL storage uses the object-storage provider from workstream 006 or an equivalent; not local disk.
