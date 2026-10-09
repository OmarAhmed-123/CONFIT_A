---
description: "Task list for Virtual Try-On async/privacy"
---

# Tasks: Virtual Try-On — Async, Partial-Layer Honesty & Privacy

**Input**: `specs/008-virtual-try-on-async-privacy/{spec.md, plan.md}`
**Tests**: REQUIRED (honesty, privacy, async).

## Phase 1: Setup
- [ ] T001 [FOUND] Link VTON-01..15 + DB-11; confirm sync render at `tryon_service.py:1085-1294`, token logic `:1428-1452`, guest poll `:1673-1735`; agree async mechanism with workstream 006.

## Phase 2: Foundational
- [ ] T002 [FOUND] Author (test DB) migration `00NN_tryon_drop_image_blobs`: dual-write/backfill images to short-TTL storage, then drop Text base64 columns; forward-chain + reconcile via 011 (mind prod `0035_product_images`). Linked: FR-004/005.
- [ ] T003 [FOUND] Short-TTL encrypted storage adapter (shared w/ 006 object storage); deletion-scrub hook. Linked: FR-004.

## Phase 3: US1 — Async submit/poll (P1) 🎯
### Tests first
- [ ] T004 [P] [US1] `backend/tests/test_tryon_async_flow.py`: submit returns 202 {job_id, poll_url, delivery_token}; render out-of-request; long render completes via poll with no client timeout; transient error retries. Linked: FR-001/002, SC-001. Acceptance: fails now (synchronous).
### Implementation
- [ ] T005 [US1] Convert submit to enqueue + `202`; background worker renders with retry/backoff. Linked: FR-001/002.
- [ ] T006 [US1] Poll endpoint returns state machine with reasons; preserve honest 503 + readiness. Linked: FR-003/009.

## Phase 4: US2 — Partial-layer honesty (P1)
### Tests first
- [ ] T007 [P] [US2] `backend/tests/test_tryon_partial_layers.py`: `all_layers_verified=false` ⇒ `PARTIAL`, never `COMPLETED`. Linked: FR-003, SC-002. Acceptance: fails now (VTON-04).
### Implementation
- [ ] T008 [US2] Gate `COMPLETED` on full layer verification; emit `PARTIAL` + per-layer reasons. Linked: FR-003.

## Phase 5: US3 — Privacy / no bytes in DB (P1)
### Tests first
- [ ] T009 [P] [US3] `backend/tests/test_tryon_no_image_in_db.py`: 0 raw/base64 payloads in job/session rows; account deletion scrubs images. Linked: FR-004, SC-003. Acceptance: fails now (DB-11).
### Implementation
- [ ] T010 [US3] Store images in short-TTL storage + metadata only; wire deletion scrub. Linked: FR-004.

## Phase 6: US4 — Guest poll + token claim (P2)
### Tests first
- [ ] T011 [P] [US4] `backend/tests/test_tryon_guest_poll_claim.py`: guest polls by id; claim token-gated + purged; expired/invalid rejected. Linked: FR-006, SC-004. Acceptance: fails now (VTON-05).
### Implementation
- [ ] T012 [US4] Fix guest polling by id; preserve VTON-12 single-claim purge. Linked: FR-006.

## Phase 7: US5 — Intake safety + budgets (P2)
### Tests first
- [ ] T013 [P] [US5] Tests: unsafe/oversized/invalid uploads rejected at intake; over-budget users rate-limited. Linked: FR-007/008, SC-005.
### Implementation
- [ ] T014 [US5] Content-safety screening + size/format guardrails + per-user GPU budget. Linked: FR-007/008.

## Phase 8: UI honesty/a11y (aligns w/ 010)
- [ ] T015 [P] Upload UI accessible names + i18n/RTL + reduced-motion; modal uses `HonestProductImage`; result gallery/history. Linked: FR-010 (VTON-13/14/15).

## Phase N: Polish
- [ ] T016 [POLISH] Environment-gate `test_vton_pose_artifact_regression.py` (libEGL) — pass in GL-capable env or skip with recorded reason (not silently ignored). Record final commit + env; `/speckit.analyze`.

## Dependencies
- T002/T003 block privacy + async. Async mechanism + storage shared with workstream 006. Migration prod-apply gated by 011.
