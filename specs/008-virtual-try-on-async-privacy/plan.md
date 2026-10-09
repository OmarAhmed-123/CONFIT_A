# Implementation Plan: Virtual Try-On — Async, Partial-Layer Honesty & Privacy

**Branch**: `008-virtual-try-on-async-privacy` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

## Summary

Convert the synchronous in-request render (`tryon_service.py:1085-1294`) into an async submit→poll→claim flow (VTON-02/03/05), make partial multi-layer results honestly `PARTIAL` not `COMPLETED` (VTON-04), remove raw base64 person images from the DB in favor of short-TTL encrypted storage with deletion scrubbing (VTON-06/DB-11), add intake moderation/guardrails/budgets (VTON-07/08/10), and preserve honest-503 + hashed single-claim delivery tokens (VTON-11/12). UI accessibility/honesty (VTON-13/14/15) aligns with workstream 010.

## Technical Context

**Language/Version**: Python 3.12; TypeScript/React 18
**Primary Dependencies**: FastAPI, SQLAlchemy 2, Alembic, Pydantic v2; async job worker (shared with 006); object/short-TTL storage; FASHN/Modal-Baseten-Cerebrium worker (existing); mediapipe (pose test needs `libEGL.so.1`)
**Storage**: Job metadata only in DB (drop Text image columns via safe migration); images in short-TTL encrypted storage; hashed delivery tokens
**Testing**: pytest (async submit/poll, partial-layer honesty, no-bytes-in-DB scan, deletion scrub, guest poll, guardrails, readiness); the pose regression test is environment-gated (libEGL)
**Target Platform**: Vercel serverless (ephemeral FS, maxDuration 300) — render MUST be out-of-request
**Project Type**: Web application
**Constraints**: biometric-adjacent data minimization; honest states; no synchronous long render.

## Constitution Check

- **I. Evidence Before Appearance**: PASS — partial-layer and no-bytes-in-DB are proven by regression tests; environmental (libEGL) failures are separated, not ignored.
- **IV. Honest AI & Integrations**: PASS/core — no fake/partial-as-complete renders; honest 503 preserved.
- **Data/privacy constraint**: PASS/core — no raw biometric-adjacent bytes at rest; deletion scrubs.
- **Platform constraint**: PASS — render moved out-of-request.
- **III**: guest poll by id + token-gated claim (existing positive preserved). **II**: N/A. **V**: PASS.

No violations.

## Project Structure

```text
backend/
├── alembic/versions/00NN_tryon_drop_image_blobs.py  # NEW: dual-write/backfill then drop Text cols (reconcile via 011; mind prod 0035)
├── app/
│   ├── models/tryon.py (metadata-only; remove base64 Text cols)
│   ├── services/tryon_service.py (async submit/poll/claim; partial honesty; retry/backoff; budgets)
│   └── controllers/tryon.py (202 submit; poll; token-gated claim; readiness)
└── tests/
    ├── test_tryon_async_flow.py        # NEW (SC-001)
    ├── test_tryon_partial_layers.py    # NEW (SC-002, VTON-04)
    ├── test_tryon_no_image_in_db.py    # NEW (SC-003, DB-11)
    ├── test_tryon_guest_poll_claim.py  # NEW (SC-004, VTON-05/12)
    └── test_vton_pose_artifact_regression.py  # existing — env-gated (libEGL)
frontend/
└── src/views/ (upload a11y/i18n; HonestProductImage in modal; result gallery)
```

**Structure Decision**: Web app; async worker + short-TTL storage shared with workstream 006.

## Complexity Tracking

> No violations. The async worker adds moving parts but is mandated by the serverless platform constraint (synchronous long render is non-viable).
