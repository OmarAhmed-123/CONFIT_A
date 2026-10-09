# VIRTUAL_TRY_ON_REPAIR_PLAN.md — CONFIT_A Virtual Try-On: Standalone Deep Technical Repair Plan

> **Document type:** Standalone deep technical plan (PLANNING / AUDIT ONLY — no application code changed).
> **Target repo:** `OmarAhmed-123/CONFIT_A` · **Branch:** `main` @ `a44f1fb` (clean).
> **Audit date:** 2026-10-09.
> **Siblings:** `ADMIN_REPAIR_PLAN.md`, `CUSTOMER_REPAIR_PLAN.md`, `BRAND_OWNER_REPAIR_PLAN.md`, `STYLELIST_AI_REPAIR_PLAN.md`.

---

## 1. Title & Scope

The **Virtual Try-On (VTON)** feature end-to-end: client upload → API intake → image transport → GPU worker render → verification/honesty → delivery → persistence/privacy → polling/job lifecycle → deployment constraints. This is a standalone technical deep-dive, not a role plan.

**Key subsystems:** `backend/app/services/tryon_service.py`, `backend/app/controllers/tryon_controller.py`, `backend/app/models/tryon.py`, the VTON delivery/temporary-image-store module(s), the GPU worker contract (`VTON_WORKER_*`), and the frontend `TryOnFitView` + upload UI.

---

## 2. Status & Severity Legend

**Status:** `VERIFIED` · `IMPLEMENTED` · `TESTED-PASS` · `TESTED-FAIL` · `GAP` · `BUG-VERIFIED` · `LIKELY` · `UNVERIFIED` · `BLOCKED` · `NO-GO` · `NOT FOUND IN SEARCHED SCOPE`.
**Severity:** P0 (blocking/security/privacy) · P1 (major) · P2 (defect w/ workaround) · P3 (polish). Evidence cites `path:line`.

---

## 3. Executive Summary

VTON is **honest by design** (no fake renders — it returns a clean 503 when no GPU worker is configured) and has thoughtful delivery-token security. But three issues undermine it for production:

- **P1 — Synchronous "job queue".** What is described as an async job queue is actually a **synchronous in-request render** (`tryon_service.py:1085–1294`), colliding with Vercel `maxDuration: 300` while the client times out earlier (~150s). Long renders fail for the user even when the worker eventually succeeds.
- **P1 — Partial-layer honesty bug.** A multi-garment render can report `status="completed"` even when `all_layers_verified` is false (`VTON-04`), i.e. success reported for a partial result.
- **P1 — Privacy.** Person photos are persisted as **raw base64 in DB** (`tryon_jobs`/`tryon_sessions` Text columns, DB-11), which is a sensitive-biometric-adjacent data-at-rest concern.
- **P2:** guest job polling broken without a `delivery_token` (**VTON-05**); no content-safety on VTON upload (**VTON-07**); `.env` lacks `VTON_WORKER_*` keys (**VTON-01**).

**Verified-positive (preserve):** honest 503 when worker absent; delivery via short-lived token + hashed storage; `STORAGE_PROVIDER=local` breaks *wardrobe* uploads on Vercel but **not** VTON (VTON uses base64 transport, not the storage provider).

**Baseline tests (this audit):** backend 3732 passed / 4 env-only failed / 21 skipped. The 4 failures are the `test_vton_pose_artifact_regression.py` harness failing on `libEGL.so.1: cannot open shared object file` — a **mediapipe native GL dependency missing in the headless container**, NOT a VTON application defect. In a CI image with `libEGL`/GL userspace libs installed, these are expected to pass.

---

## 4. Baseline & Environment Evidence

| Item | Evidence | Status |
|---|---|---|
| Synchronous render in request | `backend/app/services/tryon_service.py:1085–1294` | BUG-VERIFIED |
| Delivery token model | `tryon_service.py:1024–1041` (`new_delivery_credentials`, `delivery_token_hash`) | VERIFIED |
| Delivery staging | `tryon_service.py:1217` (`stage_vton_delivery`) | VERIFIED |
| Token verify (hmac compare) | `tryon_service.py:1428–1452` (`compare_digest`, purge on claim) | VERIFIED (positive) |
| Guest polling needs token | `tryon_service.py:1673–1735` | BUG-VERIFIED (VTON-05) |
| Vercel limits | `vercel.json`: `api/index.py maxDuration 300`, region `fra1` | VERIFIED |
| Pose-artifact tests fail (env) | `libEGL.so.1` missing for mediapipe | TESTED-FAIL (env only) |
| Honest 503 (no worker) | worker-absent returns 503, no fake image | VERIFIED (positive) |
| `.env` missing `VTON_WORKER_*` | `.env.example` lists names; local `.env` lacks them | VERIFIED (config gap) |

---

## 5. Current-State Inventory (VTON)

**Flow today:**
1. Client (`TryOnFitView`) collects a person photo + garment selection, base64-encodes, POSTs to the try-on endpoint.
2. `tryon_controller.py` → `tryon_service.py` creates a job row, mints a delivery token (hash stored), then **synchronously** calls the GPU worker over HTTP (FASHN `segfee/v15` on Modal/Baseten/Cerebrium) and waits for the rendered image in-request (`tryon_service.py:1085–1294`).
3. Rendered image staged for delivery behind the hashed token; returned as an in-response data URL / delivery ref.
4. Person image + job state persisted (including raw base64, DB-11).

**Worker contract:** `VTON_WORKER_URL` (+ auth) required; absent → honest 503. No fake render path.

---

## 6. Findings Register (VTON)

| ID | Title | Sev | Status | Evidence |
|---|---|---|---|---|
| VTON-01 | `.env` missing `VTON_WORKER_*` (feature off locally) | P2 | VERIFIED | `.env.example` only |
| VTON-02 | "Async job queue" is synchronous in-request render | P1 | BUG-VERIFIED | `tryon_service.py:1085–1294`; Vercel 300 vs client ~150 |
| VTON-03 | Client timeout < server maxDuration | P2 | BUG-VERIFIED | client ~150s |
| VTON-04 | Partial layer verification reported as success | P1 | BUG-VERIFIED | `status="completed"` with `all_layers_verified=false` |
| VTON-05 | Guest job polling broken without delivery_token | P2 | BUG-VERIFIED | `tryon_service.py:1673–1735` |
| VTON-06 | Person photos persisted as raw base64 in DB | P1 | BUG-VERIFIED | `tryon.py` Text cols (DB-11) |
| VTON-07 | No content-safety screening on VTON upload | P2 | GAP | no moderation |
| VTON-08 | No size/dimension/format guardrails documented at intake | P2 | LIKELY | DoS/cost risk |
| VTON-09 | No retry/backoff on transient worker errors | P2 | LIKELY | single attempt |
| VTON-10 | No cost/rate budget per user for GPU calls | P2 | LIKELY | cost control |
| VTON-11 | Honest 503 when worker absent | — | VERIFIED (positive) | no fake render |
| VTON-12 | Delivery token hashed + short-lived + purge on claim | — | VERIFIED (positive) | `tryon_service.py:1428–1452` |
| VTON-13 | Upload UI a11y/animation gaps (hardcoded EN, emoji, no names) | P1 | BUG-VERIFIED | A11Y-05 / MOT-06 |
| VTON-14 | Try-on modal uses raw `<img>` not HonestProductImage | P2 | BUG-VERIFIED | IMG-03 |
| VTON-15 | No result gallery / history UX for past try-ons | P2 | LIKELY | enhancement |

---

## 7. Root-Cause Analysis

1. **Serverless/async mismatch.** The render is CPU/GPU-heavy and slow, but it runs inside a single serverless request (VTON-02/03). Serverless + long sync work = timeouts; the architecture needs a real async job (submit → poll → deliver).
2. **Success semantics too loose.** The completion status is set without gating on `all_layers_verified` for multi-garment composition (VTON-04) — honesty regression in an otherwise honest feature.
3. **Convenience persistence.** Base64-in-DB (VTON-06) was the path of least resistance for transport but is wrong for sensitive person imagery at rest.
4. **Guest lifecycle under-specified.** Polling assumes the delivery token is always available to the poller (VTON-05).
5. **UI not internationalized/animated/accessible** on the upload surface (VTON-13/14).

---

## 8. Target Architecture / Desired State

**True async pipeline:**
```
Client → POST /tryon (intake, validate, moderate) → 202 {job_id, poll_url, delivery_token}
Server → enqueue job → background worker calls GPU worker (retry/backoff) → stage result (hashed token)
Client → GET /tryon/{job_id} (poll; returns PENDING/RUNNING/COMPLETED/FAILED + honest reasons)
Client → claim delivery via token → image (purged after claim/expiry)
```
- **Transport/storage:** stop storing raw person base64 in DB; store to object storage (encrypted, short TTL) or keep only ephemeral + a reference; DB holds metadata + hashed token, not the image bytes.
- **Honesty:** `COMPLETED` only when all requested layers verified; otherwise `PARTIAL`/`FAILED` with explicit reasons (never claim success for partial).
- **Safety:** content moderation + size/format guardrails + per-user GPU budget at intake.
- **Deployment:** the long render must not live in a serverless request — use a queue + worker (or a provider-hosted async job), with the serverless function only enqueuing and polling.

---

## 9. Specification (Specify)

**Spec A — Async job lifecycle (VTON-02/03/05/09).** Submitting a try-on returns immediately with a job id + poll url + delivery token; the render happens out-of-band with retry/backoff; both authed users and guests can poll by job id, and the delivery token is returned to the submitter at submit time and required only to *claim the image*. Acceptance: submit returns 202 fast; polling reflects real state; guest can poll without re-supplying a token they never got; transient worker errors retried.

**Spec B — Completion honesty (VTON-04).** A multi-layer render is `COMPLETED` only if every requested garment layer is verified; otherwise `PARTIAL` or `FAILED` with per-layer reasons. Acceptance: regression test — partial verification never yields `COMPLETED`.

**Spec C — Privacy at rest (VTON-06).** Person images are not stored as raw base64 in the DB; they live in encrypted object storage with a short TTL (or are discarded after render), and are scrubbed on account/data deletion. Acceptance: DB rows contain no person image bytes; deletion scrubs any stored image (ties to the existing "deletion scrubs personal payloads" test family).

**Spec D — Safety & cost (VTON-07/08/10).** Uploads are screened for content safety and validated for size/format/dimensions; each user has a GPU-call budget/rate limit. Acceptance: unsafe/oversized uploads refused with clear messages; budget enforced.

**Spec E — UX (VTON-13/14/15).** The upload surface is internationalized (EN/AR + RTL), fully accessible (named controls, focus-trapped modal), uses the shared launch animation on the upload button, renders results with `HonestProductImage`, and offers a try-on history gallery. Acceptance: §14/§15 + axe pass.

---

## 10. Plan (Plan)

1. Introduce a job queue + background worker; convert submit to 202 + poll (Spec A). 2. Gate completion on full-layer verification (Spec B). 3. Move person images out of the DB to encrypted short-TTL storage + scrub on delete (Spec C). 4. Add intake moderation + guardrails + per-user GPU budget (Spec D). 5. Rebuild the upload/result UI (i18n, a11y, launch animation, HonestProductImage, history) (Spec E). 6. Converge: add async-lifecycle + honesty + privacy tests; ensure pose-artifact harness runs in a GL-capable CI image.

---

## 11. Tasks (Tasks)

**T-VTON-01 · Convert render to true async (queue + poll)**
- **Sev:** P1 · **Linked:** VTON-02, VTON-03, VTON-09
- **Preconditions:** choose a queue/worker compatible with the deployment (serverless cannot hold a 150–300s request).
- **Steps:** 1) Submit endpoint validates + enqueues + returns `202 {job_id, poll_url, delivery_token}`. 2) Background worker calls the GPU worker with retry/backoff; updates job state. 3) Poll endpoint returns `PENDING|RUNNING|COMPLETED|PARTIAL|FAILED` with reasons. 4) Keep the honest 503 when no worker configured (VTON-11).
- **Files:** `tryon_service.py` (split sync render out of `1085–1294`), `tryon_controller.py`, job/worker module.
- **Acceptance:** Spec A; submit is fast; no request exceeds serverless limits.
- **Tests:** submit→poll→complete; transient-error retry; worker-absent 503 preserved.
- **Rollback:** feature-flag; sync path retained for local only. · **Risk:** high (architecture). · **Status:** BUG-VERIFIED → planned.

**T-VTON-02 · Completion honesty gate**
- **Sev:** P1 · **Linked:** VTON-04
- **Steps:** set `COMPLETED` only when `all_layers_verified`; else `PARTIAL`/`FAILED` + per-layer reasons; surface in poll response.
- **Files:** `tryon_service.py` completion logic, schemas.
- **Acceptance:** Spec B.
- **Tests:** partial verification → never COMPLETED; full → COMPLETED.
- **Rollback:** revert gate. · **Risk:** low. · **Status:** BUG-VERIFIED → planned.

**T-VTON-03 · Privacy: move person images out of the DB**
- **Sev:** P1 · **Linked:** VTON-06 (DB-11)
- **Steps:** 1) Store person/result images in encrypted object storage with short TTL (or discard post-render). 2) DB keeps metadata + hashed delivery token only. 3) Ensure account/data deletion scrubs any stored image (extend the existing deletion-scrub test family). 4) Migrate/retire existing base64 Text columns safely.
- **Files:** `tryon.py` model, storage provider, deletion service, Alembic migration (forward from head; mind prod `0035`, §19).
- **Acceptance:** Spec C; DB holds no image bytes; deletion scrubs.
- **Tests:** "tryon rows lose person images on delete" stays green; "no base64 image bytes in DB".
- **Rollback:** dual-write during migration. · **Risk:** high (data migration + privacy). · **Status:** BUG-VERIFIED → planned.

**T-VTON-04 · Guest polling without re-supplying token**
- **Sev:** P2 · **Linked:** VTON-05
- **Steps:** allow guests to poll job *state* by job id (no secret), while the delivery token (minted at submit, returned once) is required only to *claim the image* (`tryon_service.py:1673–1735`).
- **Files:** `tryon_controller.py`, `tryon_service.py`.
- **Acceptance:** guest can see progress; image claim still token-gated (preserve VTON-12).
- **Tests:** guest poll state OK without token; claim without token refused.
- **Rollback:** revert. · **Risk:** medium. · **Status:** BUG-VERIFIED → planned.

**T-VTON-05 · Intake safety + guardrails + GPU budget**
- **Sev:** P2 · **Linked:** VTON-07, VTON-08, VTON-10
- **Steps:** content-safety screen on person upload; validate size/format/dimensions; per-user rate/cost budget on GPU calls; clear refusals.
- **Files:** `tryon_service.py` intake, moderation hook, rate-limit (slowapi).
- **Acceptance:** Spec D.
- **Tests:** oversized/invalid refused; budget enforced; unsafe content refused.
- **Rollback:** disable moderation flag (keep size/format). · **Risk:** medium. · **Status:** GAP → planned.

**T-VTON-06 · Config: document + wire `VTON_WORKER_*`**
- **Sev:** P2 · **Linked:** VTON-01
- **Steps:** ensure `.env.example` documents `VTON_WORKER_URL` + auth; add a readiness check that reports VTON availability honestly (no secret values). Do **not** print secrets.
- **Files:** `.env.example`, health/readiness.
- **Acceptance:** operators can tell if VTON is configured without seeing secret values.
- **Tests:** readiness reports configured/not-configured.
- **Rollback:** n/a. · **Risk:** low. · **Status:** VERIFIED gap → planned.

**T-VTON-07 · Upload/result UI: i18n + a11y + animation + honest images + history**
- **Sev:** P1 (a11y) · **Linked:** VTON-13, VTON-14, VTON-15, §14/§15
- **Steps:** 1) Replace hardcoded English + emoji with i18n strings (EN/AR, RTL). 2) Give every control an accessible name; focus-trap the try-on modal. 3) Upload button uses `<LaunchButton>` (rocket rising bottom→top + color shift) honoring reduced motion. 4) Render results via `HonestProductImage`. 5) Add a try-on history gallery.
- **Files:** `frontend/src/views/consumer/TryOnFitView.tsx` + upload components + shared Modal/Button.
- **Acceptance:** Spec E; axe passes; RTL correct.
- **Tests:** axe a11y; RTL snapshot; reduced-motion; upload keyboard flow.
- **Rollback:** revert UI layer. · **Risk:** medium. · **Status:** BUG-VERIFIED → planned.

**T-VTON-08 · CI: GL-capable image for pose-artifact harness**
- **Sev:** P2 (test infra) · **Linked:** the 4 env failures
- **Steps:** install `libEGL`/GL userspace libs (and any `mediapipe` runtime deps) in the test/CI image so `test_vton_pose_artifact_regression.py` can load the hand-landmarker; or mark these tests `skip` when GL is unavailable with an explicit reason (not a silent pass).
- **Files:** CI/docker/test setup (not app code).
- **Acceptance:** pose-artifact tests pass in CI or skip with a clear reason.
- **Tests:** the 4 tests pass in a GL image.
- **Rollback:** keep explicit skips. · **Risk:** low. · **Status:** TESTED-FAIL (env) → planned.

---

## 12. Data Model / Migration Considerations

- **DB-11 (VTON-06):** remove raw base64 image storage from `tryon_jobs`/`tryon_sessions`; keep metadata + hashed delivery token. Migration must dual-write/back-fill safely and then drop the Text image columns. **Mind prod `0035_product_images`** — forward-chain any new revision (§19).
- **Job lifecycle:** add/confirm job-state columns (`PENDING/RUNNING/COMPLETED/PARTIAL/FAILED`, per-layer verification, reason) to support true async + honesty.
- **Deletion:** ensure the data-deletion path scrubs any externally-stored person image (object-storage delete), preserving the existing deletion-scrub guarantees.
- **No migration authored here.**

---

## 13. API Contract Changes (proposed)

| Endpoint | Change | Note |
|---|---|---|
| `POST /tryon` | returns `202 {job_id, poll_url, delivery_token}`; validates + moderates at intake | async (VTON-02/05) |
| `GET /tryon/{job_id}` | returns state + per-layer reasons; guest-pollable by id | VTON-04/05 |
| `GET /tryon/{job_id}/image` | token-gated claim; purges after claim/expiry | preserve VTON-12 |
| readiness | reports VTON configured (no secrets) | VTON-01 |

Explicit schemas; `await` all async; never return a fake image; never log/return secret worker credentials.

---

## 14. UI/UX Plan (colors · animation · dynamism)

- **Launch animation on upload (explicit user request):** the upload button morphs into a rocket that rises bottom→top with a color shift to the brand/success token, then settles into a progress indicator while the async job runs; reduced-motion → simple fade. Implement via the shared `<LaunchButton>`.
- **Dynamic progress:** live poll-driven progress states (queued → rendering → verifying → done) with animated transitions; honest `PARTIAL`/`FAILED` messaging.
- **Professional result presentation:** before/after and layered views via `HonestProductImage`; try-on history gallery with consistent aspect ratios.
- Canonical gold token; consistent focus rings.

---

## 15. Accessibility Plan (WCAG 2.2 AA)

- Every upload/try-on control has an accessible name (fixes A11Y-05); replace emoji-as-UI with labeled icons.
- Try-on modal focus-trapped (A11Y-03); status announced via `aria-live` (don't drop focus when the upload button enters pending — MOT-02/MOT-06).
- Full EN/AR + RTL on the upload surface (currently hardcoded English).
- Reduced-motion respected by the launch/progress animation.

---

## 16. Security & Privacy

- **Biometric-adjacent data:** treat person photos as sensitive — encrypt at rest, short TTL, scrub on delete (VTON-06). Preserve hashed, short-lived delivery tokens + purge-on-claim (VTON-12).
- Content-safety moderation at intake (VTON-07).
- Per-user GPU budget/rate limit to prevent cost abuse (VTON-10).
- Never render a fake result; keep honest 503 (VTON-11).
- Never log or return worker secrets.

---

## 17. Testing & Verification Plan

- Async lifecycle (submit→poll→complete), retry/backoff, guest polling, token-gated claim.
- Honesty: partial-layer never COMPLETED.
- Privacy: no image bytes in DB; deletion scrubs external storage (preserve existing deletion-scrub tests).
- Safety: oversized/invalid/unsafe refused; budget enforced.
- UI: axe, RTL, reduced-motion, keyboard upload.
- **Pose-artifact harness:** currently 4 TESTED-FAIL due to `libEGL.so.1` missing (env). Resolve via T-VTON-08 (GL-capable CI image) or explicit skips. These are **not** VTON app defects.
- **Baseline to preserve:** 3732 passed / 21 skipped; frontend build PASS.

---

## 18. Rollout / Deployment / Flags

- Async pipeline behind a flag; serverless function only enqueues/polls (never holds the long render). The render worker must run where long jobs are allowed (the GPU worker host / a queue consumer), not inside `api/index.py` (maxDuration 300, region `fra1`).
- Privacy migration staged (dual-write → back-fill → drop columns).
- VTON availability gated on `VTON_WORKER_*` being configured (honest 503 otherwise).

---

## 19. Risks, Assumptions, Open Questions

- **R1 (migration drift):** prod `0035_product_images` ahead of `main` `0034` — forward-chain the privacy + job-state migrations after `0035`. **UNVERIFIED in `main`.**
- **R2 (queue infra):** true async needs a queue/worker; on Vercel this likely means an external queue or provider-hosted async job. Decision required before T-VTON-01.
- **R3 (test env):** CI must provide GL libs for mediapipe or the pose-artifact tests remain red (env, not app).
- **A1:** GPU worker is FASHN `segfee/v15` hosted on Modal/Baseten/Cerebrium via `VTON_WORKER_URL`.
- **Q1:** retention policy for try-on result images (how long to keep history vs. privacy)?

---

## 20. Acceptance Criteria / DoD + Traceability

**VTON is "done" when:** submitting a try-on returns immediately and the render completes out-of-band without timeouts; completion is reported honestly (no success for partial); person images are never stored as raw base64 in the DB and are scrubbed on deletion; intake is moderated, guardrailed, and budget-limited; the upload/result UI is i18n/RTL, accessible, animated (launch button), and image-polished; and the honest 503 + token security are preserved.

| Finding | Task | DoD signal |
|---|---|---|
| VTON-02/03/09 | T-VTON-01 | Async submit/poll; no timeouts. |
| VTON-04 | T-VTON-02 | Partial never COMPLETED. |
| VTON-06 | T-VTON-03 | No image bytes in DB; deletion scrubs. |
| VTON-05 | T-VTON-04 | Guest polls by id; claim token-gated. |
| VTON-07/08/10 | T-VTON-05 | Moderation + guardrails + budget. |
| VTON-01 | T-VTON-06 | Honest availability readiness. |
| VTON-13/14/15 | T-VTON-07 | i18n/a11y/animation/history. |
| env failures | T-VTON-08 | Pose tests pass or skip w/ reason. |

**Preserve:** VTON-11 (honest 503), VTON-12 (token security).
