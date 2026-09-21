# BRD — Wardrobe & Saved Outfits, Mood Boards, Gap Analysis (Group 4)

**Project:** CONFIT_A — production `https://confit-a.vercel.app/`
**Scope of this BRD:** the wardrobe lifecycle only — piece upload & analysis,
My Closet, outfit reuse ("My Looks" / wardrobe-first styling), Mood Boards,
and Wardrobe Gap Analysis. No other feature area is modified.
**Date:** 2026-09-21 · **Author:** OmarAhmed-123 (with agentic audit)
**Status:** approved for implementation (4 sequential PRs, one branch)

---

## 1. Business context

CONFIT's retention thesis is *shop your wardrobe first*: the platform should
make customers reuse what they already own before selling them anything new.
Group 4 delivers the mechanics for that promise:

1. **Upload & understand** — the customer photographs their garments; the
   server validates, stores durably, and AI-analyses each piece
   (category, color, pattern, style tags, occasions, seasonality).
2. **Curate** — favorites, wear frequency, wear count, manual correction of
   AI attributes, deletion without orphaned media.
3. **Reuse** — "My Looks" (saved outfits), wardrobe-first outfit building
   (only genuinely missing positions become purchasable suggestions),
   Mood Boards (inspirational tiles: URLs, catalog products, uploads).
4. **Close the loop** — Gap Analysis identifies which capsule categories the
   wardrobe cannot fill and maps *only those* to real catalog products, with
   an explainable rationale and an estimated number of new outfits the
   missing piece unlocks.

A purchase later materialised from any of these flows must never contradict
what the customer sees: the same taxonomy, the same ownership rules, the
same honesty about AI availability.

## 2. Current state (verified, 2026-09-21)

| Surface | Evidence | Verdict |
|---|---|---|
| Closet / looks / gaps endpoints | `GET /api/v1/wardrobe/items`, `/outfits`, `/me/mood-boards`, `/wardrobe/gap-analysis` → 200 for all matrix accounts (G1/G2/G4/G5/VTON) | Reads OK on **empty** wardrobes |
| Production storage | Live `GET /api/v1/health` → `checks.storage = {provider: local, production_grade: false, writable: false}` | **Photo upload is 501 FEATURE_NOT_CONFIGURED in production** |
| Upload pipeline code | `WardrobeService.upload_items`: validate (Pillow verify + MIME cross-check) → store → sha256 dedup → AI analysis | Complete in code, **never executed against production storage** |
| Analysis path | Celery task `auto_tag_wardrobe_task` with inline fallback; no worker/broker in the Vercel deployment | Works only via the fallback; **stuck-`processing` items are possible** |
| Gap analysis | `GapAnalysisService` capsule matrix + real catalog mapping | Correct suppression logic, but `unlocks_outfit_count` is a **hardcoded constant (4/4/5/3/3)** — a fabricated "Unlocks +N New Outfits" claim |
| Mood Boards | Full backend CRUD + real multipart upload (`moodboard_controller.py`) | **No consumer UI** anywhere in `frontend/src` |
| Cross-user tests | Wardrobe IDOR tested (404, no oracle); **none for outfits / mood boards** (mood boards leak existence via 403) | Partial |
| UX states | Gaps tab: no loading/empty/error UI; closet: fetch error only toasts; "Scanning your wardrobe…" shown on every initial load | Empty vs loading vs failure not distinguished (audit finding) |

## 3. Gaps and risk register

| ID | Gap | Severity | User-visible symptom if unaddressed |
|---|---|---|---|
| G-S3A | `S3StorageBackend` creates the boto3 client **without path-style addressing**. Neon Object Storage (and R2/MinIO/B2) do not resolve virtual-hosted bucket subdomains → every S3 operation fails | Critical | Uploads fail in production even after env config |
| G-S3B | `confit-a-media` bucket is **private** (verified: unsigned GET → 403). Plain `endpoint/bucket/key` URLs stored in the DB 403 in every browser `<img>` | Critical | Uploaded photos invisible to the customer; looks broken even though DB + storage are fine |
| G-S3C | Production env not configured for object storage (`STORAGE_PROVIDER=local`) | Critical | Every photo upload → 501 (verified via live health) |
| G-CSP | `vercel.json` CSP `img-src` does not include the object-storage host | High | Even a valid signed URL is blocked by the browser in production |
| G-ASYNC | No analysis worker in the deployment; if a broker is reachable but no worker runs, items stay `processing` **forever**; enqueue-fail + inline-fail path swallows the error and reports "created" with a perpetually-`processing` item | High | "Processing…" badge never resolves; customer cannot tell failure from queue |
| G-GAPCOUNT | `unlocks_outfit_count` hardcoded (4/4/5/3/3) regardless of the user's data | Medium | The "Unlocks +N New Outfits" badge is a fabricated claim (audit: "no fake claims") |
| G-MOODUI | Mood Boards have a real backend but **no UI** | Medium | Feature is invisible to customers |
| G-IDOR | Mood-board cross-user access returns 403 (existence oracle); no regression tests for outfits/mood-boards ownership | Medium | Inconsistent with the rest of the API; untested trust |
| G-UX | Gaps tab renders nothing while loading / on error / when there are no gaps; closet errors only toast; initial "Scanning…" state is ambiguous for empty accounts | Low | Audit's explicit finding on empty/loading/scan-failure ambiguity |
| G-DOCS | No BRD / verification trail for this feature scope | Low | Findings cannot be re-audited |

## 4. Remediation plan (one branch, four sequential PRs)

Branch: `g4-wardrobe-lifecycle-closure` → `main`. Each PR merges before the
next is opened (the branch carries the cumulative work).

### PR 1 — Production object storage for photo uploads
- Path-style addressing + SigV4 on the boto3 client (G-S3A).
- Endpoint resolution: `S3_ENDPOINT_URL` (app) with `AWS_ENDPOINT_URL_S3`
  (AWS-SDK / Neon convention) fallback (G-S3C support).
- **Presigned-URL pattern** (G-S3B): the database keeps the canonical object
  URL; every API serialization boundary (`WardrobeItemOut`, wardrobe-first
  outfit owned picks, mood-board upload tiles) swaps owned URLs for
  time-limited SigV4 GETs (`S3_PRESIGN_EXPIRY_SECONDS`, default 3600).
  Signing is computed locally by boto3 — no network cost per response.
  External/seeded URLs (Unsplash, catalog CDN) pass through untouched —
  enforced by `key_for_url` ownership, never by URL guessing.
- CSP `img-src` + `connect-src` extended with the storage host (G-CSP).
- `.env.example` documents the full storage section (names only, per repo
  policy).
- Contract tests: path-style kwargs asserted behaviourally; endpoint
  fallback; presign round-trip; owned-vs-foreign URL pass-through;
  wardrobe serialization wiring.
- **Acceptance:** `test_storage_backend_contract.py` green; after deploy +
  env config, live `/health` reports `checks.storage.production_grade=true`
  and a real uploaded photo loads in a browser from a signed URL.

### PR 2 — Honest analysis lifecycle + lifecycle/IDOR regression tests
- `WARDROBE_ANALYSIS_MODE` = `auto | sync | async` (default `auto`):
  `auto` pings the broker with a hard 1s budget — only a *reachable* broker
  takes the async path, otherwise analysis runs inline in the request
  (serverless-safe; Vercel function `maxDuration` 300s covers it).
  `sync` is forced inline; `async` is operator-explicit (dedicated worker).
  The deployment has no worker, so production runs inline and **the upload
  response already contains the final status** — no silent queue.
- Self-healing stale guard: any wardrobe read marks items stuck in
  `processing` longer than `WARDROBE_PROCESSING_STALE_MINUTES` (default 10)
  as `failed` with `processing_error="analysis timed out — please retry"`,
  so no item can ever be permanently invisible (G-ASYNC).
- The swallow path (enqueue-fail + inline-fail) now marks the item `failed`
  and reports it honestly in the per-file report.
- Behavioural test suite (new `test_g4_wardrobe_lifecycle_e2e.py`) with a
  cleanable fixture (one top, one bottom, one shoe per user):
  upload → analysis (real provider mocked) → edit (PUT) →
  wardrobe-first outfit (owned picks verified) → gap analysis (covered
  categories suppressed) → delete (item + S3 object removed).
  Plus: stale-processing heal; enqueue-fail+inline-fail honesty;
  `sync` mode never enqueues; **cross-user IDOR** for wardrobe analyze,
  outfit read/patch/delete and mood-board read/patch/delete/add-item
  (all 404, no existence oracle — G-IDOR).

### PR 3 — Data-driven Gap Analysis + complete UI states + Mood Boards UI
- `unlocks_outfit_count` computed deterministically from the user's **ready**
  items (documented formula in `gap_analysis_service.py`):
  - `core = {Tops, Bottoms, Footwear}`; `core_combos = min(counts, caps)`
  - missing **core** category → product of the two other core counts
    (each new piece completes that many owned pairings), capped at 12
  - missing **layering** category (Outerwear/Accessories) → `core_combos`,
    capped at 12 (one new layer dresses every owned core combination)
  - empty wardrobe → 0, and the rationale says so instead of inventing a
    number (G-GAPCOUNT)
- Every gap response carries `owned_counts` (the source data the rationale
  quotes) so the UI's "AI Analysis" text is auditable against the payload.
- Frontend: gaps tab gets loading skeleton / "no gaps" / error-with-retry;
  closet gets an error state with retry (error no longer masquerades as
  empty); the "Scanning your wardrobe…" spinner is reserved for real loading
  (G-UX).
- **Mood Boards UI** (G-MOODUI): fourth tab on the Wardrobe page — list /
  create / rename / delete boards, add tiles (URL / catalog product / real
  multipart upload via `POST /me/mood-boards/{id}/upload`), remove tiles.
  Same storage contract as wardrobe photos (private bucket → presigned
  reads, already covered by PR 1).
- Tests: deterministic unlock-matrix cases (incl. empty wardrobe), owned
  counts presence, mood-board IDOR 404s.

### PR 4 — Production verification + evidence
- Verification report with **real** evidence, no claims without a probe:
  before/after `/health` storage check; a live register → upload →
  analyze → gap-analysis → delete cycle on a dedicated throwaway account
  (real Gemini vision call, real Neon S3 object, real signed URL fetch
  from the browser's perspective); cross-user 404 probes.
- `CHANGELOG.md` entry.
- **Acceptance:** production upload returns 201 with `processing_status`
  resolving to `ready` (or an honest `failed` + retry), the photo renders
  from the signed URL, and the gap analysis reflects the uploaded pieces.

## 5. Design decisions

1. **Presign-on-read, not public bucket.** Private buckets are the secure
   default (Neon Object Storage). Making the bucket `public_read` would
   expose every customer's garment photo to anyone who guesses/enumerates a
   key and would require a console change we cannot audit from here.
   Presigned GETs (1h TTL) cost nothing at request time (local SigV4) and
   keep the DB canonical. This is exactly the pattern in Neon's own
   documentation ("Store the object key … and presign on read").
2. **Path-style addressing is a hard requirement** for S3-compatible stores
   (Neon docs: "Without forcePathStyle: true … the SDK treats the bucket
   name as a subdomain instead of a path segment"). Enforced in the client
   config and covered by a behavioural test.
3. **Sync-first analysis in serverless.** A Celery queue is only correct
   when a worker actually runs. Defaulting to inline analysis (with an
   explicit broker probe for `auto`) removes the whole class of
   "permanently processing" items; `async` remains available for a
   real-worker deployment without code changes.
4. **Deterministic, explainable numbers.** Gap-analysis unlock estimates and
   duplicate scoring are pure functions of owned data with documented
   formulas — no model call, no constants presented as analytics.
5. **Ownership 404, never 403.** Non-owned and non-existent resources are
   indistinguishable (no enumeration oracle) — the existing codebase
   contract; mood boards are brought into line.
6. **Taxonomy at every boundary.** All controlled fields (category, color,
   pattern, occasions, seasonality) are normalized on create *and* update
   through `wardrobe_taxonomy`, so duplicate detection, gap analysis and
   outfit scoring see one vocabulary.

## 6. Technical-concept coverage (requested)

| Concept | Where applied |
|---|---|
| **BRD** | This document: scope, evidence, risk register, acceptance criteria per PR |
| **DRY** | One storage abstraction for wardrobe + mood boards; one `storage_public_url` boundary helper used by every serializer; shared taxonomy module; single capsule matrix for gap logic |
| **Design patterns** | *Strategy* (`StorageBackend` local/S3 with factory + singleton), *Repository* (all persistence behind repos), *Service/Controller* layering, *Template Method* for upload pipeline steps, *Builder-lite* for the wardrobe-first outfit, fail-losed *Feature Toggle* (`require_production_storage`) |
| **System design** | Serverless-safe sync-first async pipeline with broker probe; idempotency keys (`uq_wardrobe_items_user_image_hash`, `uq_wardrobe_items_source_order_item`); self-healing stale guard; per-file partial-success contract; preflight 501 instead of mid-upload 500 |
| **Architecture** | Frontend view-model split (`useWardrobeViewModel`), API-boundary serialization (presigning lives only at the edge), CSP at the edge, env contract in `core/config.py` |
| **Database** | Lifecycle columns (`processing_status/processing_error/ai_confidence`), unique idempotency constraints, JSONB-ish JSON text columns with schema-level validation, no migration needed for this remediation (schema 0017 already complete — verified against live `alembic_version`) |
| **Algorithms** | Deterministic duplicate scoring (55/35/10 attribute weights, centralized thresholds); owned-piece ranking (`owned_score`: occasion 50 > favorite 20 > frequency 10/4 > wear-count 0.5× > neutral-color 5); combinatorial unlock estimate (bounded products, cap 12); color-anchor harmony via the existing `ColorHarmonyEngine` map |

## 7. Non-goals (explicit)

- No changes to catalog, commerce, try-on (VTON), B2B, or admin surfaces.
- No new migrations (schema parity with live head `0017` is verified).
- No public bucket, no server-side image CDN (presigned TTL covers sessions;
  a CDN front can be added later without code changes).
- No ML model training; the vision provider stays Gemini via the existing
  `VisualSearchAIProvider` orchestration (with the existing failover).

## 8. Acceptance summary (whole scope)

1. `pytest` wardrobe + storage + lifecycle + IDOR suites green locally.
2. Production `/health`: `checks.storage.production_grade == true`.
3. Live cycle on a throwaway account: upload 1 photo → 201 →
   `processing_status: ready` with non-fabricated AI tags → appears in
   closet, in a wardrobe-first outfit, and (as a gap-closer) in gap
   analysis → delete removes the DB row **and** the S3 object.
4. Cross-user probes on wardrobe/outfits/mood-boards all return 404.
5. UI shows distinct empty / loading / error / failure states on all tabs;
   Mood Boards is fully usable in-browser.
6. No secrets in the repo (gitleaks clean); DB stores canonical URLs only.
