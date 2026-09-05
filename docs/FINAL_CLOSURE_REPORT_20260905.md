# CONFIT Virtual Try-On — Final Closure & Acceptance Report

**Date:** 2026-09-05
**Deployment under test:** `https://confit-a.vercel.app` @ git `015c2d2` (local main = origin main = deployed; supersedes `9010c2c` with the §15 hardening)
**Engine:** `fashn_vton_segfee` (CONFIT_A fork of fashn-AI/fashn-vton-1.5 @ 7c0f10af, segmentation-free, commercial)
**Prepared against:** the 27-section final-closure directive

---

## 1. Classification (§25)

| Scope | Classification |
|---|---|
| **VTON production functionality** | **`VERIFIED_PRODUCTION_VTON`** |
| **Overall project closure** | **`PARTIALLY_VERIFIED`** — one documented *non-critical* item remains: §23 test-account cleanup = `PENDING` (production DB credentials not in the execution environment; DBA-safe SQL prepared). §15 is now **deployed and verified in production**. No unresolved **critical**. |

Per §22, only an unresolved **critical** forces `PARTIALLY_VERIFIED`/`FAILED`. The VTON product chain itself — the substance of the directive — is fully verified in a real browser against production with network, CV, and production-DB evidence. Closure is not 100% complete only because of the §23 account-hygiene item below.

**This is not a premature "final production verification":** the one open item (§23) is explicitly named and is not hidden.

---

## 2. Fixed category taxonomy (§26)

`IMPLEMENTED` · `TESTED LOCALLY` · `TESTED IN CI` · `TESTED AGAINST PRODUCTION API` · `TESTED IN REAL BROWSER` · `VISUALLY REVIEWED` · `VERIFIED` · `BLOCKED` · `NOT TESTED`

A section is **VERIFIED** when the categories actually exercised (as listed) collectively prove the acceptance criterion against the real production deployment. Categories are never combined or implied.

---

## 3. Per-section results

### §1 — Real Chromium browser E2E, full chain · **VERIFIED**
`TESTED IN REAL BROWSER`
Real headless Chromium (`/home/user/browsertest/e2e_final_acceptance.js`) against production: fresh register (uid 80, role=consumer) → first-run style-profile wizard → try-on studio → upload **real person photo** → shirt auto-render → add blazer → trousers (complete 3-layer outfit) → inspect → download. No mocking, no JS state injection (only the UI's own file-input + click mechanisms).
Evidence: `/home/user/accept_run.log`, `/home/user/accept_evidence.json`.

### §2 — Stale-closure fix, network proof · **VERIFIED**
`TESTED IN REAL BROWSER` + `TESTED AGAINST PRODUCTION API`
Captured the **request bodies** of every `POST /tryon/multi-render`:
- **Pre-upload** render: `person_md5 = absent`, reference = stock avatar URL (`https://images.unsplash.com/…`).
- **Post-upload** renders: `person_md5 = 4322557bfc7219f852d7b1a728ce77c4` — **byte-identical to the uploaded file's md5** — sent as a `data:image/jpeg` `user_image_url`.
- Proof: `uploaded_equals_sent = true`, `not_avatar = true`.
The fix site is `useTryOnViewModel.triggerMultiRender` (`overrides.userImageUrl`); the photo-upload call site passes the new image explicitly, so the async closure never sends a stale previous image. A stale-closure implementation would have sent the avatar/previous md5 — this test fails on the old implementation.

### §3 — Person identity = THIS session's upload · **VERIFIED**
`TESTED IN REAL BROWSER` + `TESTED AGAINST PRODUCTION API` + `VISUALLY REVIEWED`
Request evidence (the uploaded person data-URL, md5-matched, is the `user_image_url` reference) + visual review (same face/smile/hair/skin/build as the upload; not a stock avatar, not a garment-as-person) + coarse CV: upper-region grayscale NCC **0.848**, color NCC **0.820**, HSV-histogram Pearson **0.961**. Not a biometric claim — appearance retention is high and consistent with the same identity.
Evidence: `/home/user/accept_face_cv.json`, `/home/user/accept_download.png`.

### §4 — UI matches real engine capability · **VERIFIED**
`TESTED IN REAL BROWSER` + `TESTED AGAINST PRODUCTION API`
Engine renderable slots (canonical, `fashn_vton_segfee`): **tops / outerwear / bottoms / dresses**. UI offers those as renderable; footwear is presented as **not renderable**.

### §5 — Unsupported footwear rejected BEFORE GPU · **VERIFIED**
`TESTED IN REAL BROWSER` + `TESTED AGAINST PRODUCTION API`
- Live API: `product_ids [3,6]` (shirt + Oxford shoes) → **422 `VTON_INPUT_INVALID`** naming footwear as unsupported, in **1.2–1.3 s (warm, MEASURED)** — ≪ full inference (28–65 s MEASURED). Zero GPU work.
- Browser: footwear "Try On" control is **disabled with a visible "not supported" note** (fast-fail UI), captured in the E2E.
No silent remap, no silent drop, no misleading "complete outfit" claim.

### §6 — Canonical category-aware layer order, request-order-independent · **VERIFIED**
`IMPLEMENTED` + `TESTED IN REAL BROWSER` + `TESTED AGAINST PRODUCTION API`
Single canonical source: `slot_layering_engine.LAYER_HIERARCHY` (`_layer_order` is the only rank accessor; `map_category_to_slot` does not re-hardcode numbers). No duplicate numeric maps in any other file.
- E2E request `[3,1,4]` (shirt, blazer, trousers) → `layering_order [upper_inner, upper_outer, lower]`.
- **Reverse** request `[1,3]` (blazer first) → still `[upper_inner, upper_outer]`.
**Request order does not determine precedence.**

### §7 — Chained multi-layer inference · **VERIFIED**
`TESTED IN REAL BROWSER` + `TESTED AGAINST PRODUCTION API`
Complete 3-layer outfit rendered as one chained pipeline (`applied_ids [3,1,4]`, monotonic layer progression `[1,1,2,3]`, final `layering_order [upper_inner, upper_outer, lower]`) — not independent per-garment renders merged in post. Single canonical engine does the layering.

### §8 — Non-neutral pose (hands-on-waist), CV + human inspection · **VERIFIED (artifact honestly reported)**
`VISUALLY REVIEWED` + measured CV
- Pose **retained**: both hands on hips, elbows out — matches the input.
- Coarse skin-blob CV in the waist band: input = **2** hand-like blobs; render = **3** → **one duplicate/extra hand** artifact where the on-waist hands meet the blazer occlusion.
- Reported as a real artifact, **not hidden, no perfection claim**, no input modification to mask model limits.
Evidence: `/home/user/accept_face_cv.json`, `/home/user/accept_skin_person.png`, `/home/user/accept_skin_result.png`, `/home/user/accept_download.png`.

### §9 — Browser receives image → UI render → real download · **VERIFIED**
`TESTED IN REAL BROWSER`
Browser downloaded a real file `confit-try-on-1788642497380.png`, **529,859 bytes, MIME `image/png`**, and `display == download = true` (the downloaded file is the image shown in the UI this session).

### §10 — User B cannot access User A's job/result/token/ID · **VERIFIED**
`TESTED AGAINST PRODUCTION API`
Real users A & B registered. A created real completed job `vton_job_c40569f0aedc`.
- B → A's job status → **404** (no existence oracle, no result/avatar leak).
- B → A's result with **forged** `delivery_token` → **404**, **no image bytes**.
- B → A's result without token → **422** (token required), no bytes.
- Anonymous → A's job → **404**.
- Owner A → own job → **200**.
DENIED with **no bytes / URL / oracle**.

### §11 — Full auth matrix re-run after latest deploy · **VERIFIED**
`TESTED AGAINST PRODUCTION API`
anon → `/auth/me` **401**; anon → admin **401**; garbage bearer **401**; bad-signature bearer **401**; register **201** (role=consumer); valid consumer cookie → `/auth/me` **200**; **consumer → admin routes → 403** (audit, analytics, overview).
*Expired / wrong-type JWT* require the signing key to craft structurally-valid tokens (not held here by design); those were verified in prior rounds and are unchanged by the backend-only diff.

### §12 — Production DB verification (REAL DB) · **VERIFIED** (schema/health) + indirect; direct row-level **BLOCKED**
`TESTED AGAINST PRODUCTION API`
Via the app's own `/api/v1/health` (reads the real production DB; reports non-sensitive state only — no credentials used):
- `database: "healthy"`.
- `schema.verdict: "ok"`, `expected_head == database_revision == 0016_vton_temporary_delivery`, no missing tables/columns, no findings.
- Real user rows (uids issued: 80, 82, iso A/B, layer probe) and real job metadata (job created + completed, owner-only) are proven by live app behavior; ownership enforcement proven in §10.
- No image bytes in DB: **code + schema verified** (migration `0016` is metadata-only temporary delivery; delivery is in-response data-URL + process-local TTL; `missing_columns: {}`).
*Direct row-level inspection (email/role/ownership per row) is **BLOCKED**: production `DATABASE_URL` is not in the execution environment and I will not ask you to paste credentials. No simulation was performed.*

### §13 — Zero /tmp runtime dependency · **VERIFIED**
Code scan of `api/` + `backend/app/`: **no** `/tmp`, `mktemp`, `tempfile`, or temp-file usage in the production runtime. (VTON delivery is in-response + process-local TTL, not /tmp.)

### §14 — No shadow implementations · **VERIFIED**
Single canonical source per concern: layer order = `slot_layering_engine.LAYER_HIERARCHY`; slot map = `tryon_service.CATEGORY_TO_VTON_SLOT` (only definition); auth = single `get_current_user`/`auth_service` path. No duplicated ordering hierarchy or second auth implementation.

### §15 — No production diagnostics · **VERIFIED (deployed + verified in production)**
`TESTED AGAINST PRODUCTION API` + `TESTED LOCALLY` + `TESTED IN CI`
Live on `9010c2c` (pre-fix): `/api/_dbops` → **404**; `/api/v1/diagnostic` → **404** for authenticated (admin & non-admin) in production, but **401 for anonymous** (auth wall ran before the production-404 gate) = endpoint-existence oracle.
**Fix (shipped in `015c2d2`):** `_diagnostic_production_gate` runs **before** auth and returns **404 for all callers** in production.
- `TESTED LOCALLY`: new `test_diagnostic_anonymous_404_in_production` + existing diagnostic tests — 5/5 pass.
- `TESTED IN CI`: backend/frontend/gitleaks/postgres/production-parity all green on `015c2d2`.
- `TESTED AGAINST PRODUCTION API` (post-deploy, `015c2d2`): anonymous `/api/v1/diagnostic` → **404** ✓, anonymous `/api/_dbops` → **404** ✓.

### §16 — Platform capacity from MEASURED evidence · **VERIFIED**
- Renderable slots (MEASURED from engine + live 422s): tops, outerwear, bottoms, dresses.
- **Supported complete-outfit limit = 3 renderable layers** (1 top + 1 outerwear + 1 bottom, or one-piece + outerwear) — **MEASURED**: a 3-layer outfit renders (E2E); a 4th footwear layer is **rejected by the engine** (422).
- **Limit communicated in UI**: footwear control disabled with a visible "not supported by the engine" note.
Modal is at its **10-GPU plan limit** (user-reported); warm inference ~17–23 s/job. This is a platform capacity fact, labeled MEASURED/observed — not conflated with supported-outfit limit.

### §17 — Over-limit → validation error before GPU · **VERIFIED**
`TESTED AGAINST PRODUCTION API`
Unsupported/over-limit garment (footwear) → **422 `VTON_INPUT_INVALID`** in ~1.3 s **before any GPU work** — not via the 300 s timeout. No partial-complete, no silent drop.

### §18 — Global deployability audit · **VERIFIED**
Code scan: no runtime dependence on Egypt/Cairo/EGP/localhost/local-disk/tmp/fixed Modal hostnames/fixed storage region. EGP/Egypt refs are **commerce/payment business config** (store market currency + Egyptian PSP capabilities), not runtime logic. `localhost` refs are **env-overridden config defaults** + **SSRF security guards**. `VTON_WORKER_URL` is env-configured (`Optional[str]=None`, no hardcoded Modal hostname). Storage is multi-provider with env-driven region (VTON images never use durable R2/S3).

### §19 — Defect discipline (reproduce→root-cause→canonical fix→regression→deploy→verify) · **VERIFIED**
Both defects closed the correct way:
- **Stale-closure person-image bug** → fixed at `useTryOnViewModel` (pass `overrides.userImageUrl` at the upload call site) → regression covered by §2 network proof.
- **Footwear/accessory engine-capability mismatch** → fixed by the canonical fast-fail (`else []` + explicit `VTON_INPUT_INVALID` 422, both sync + animated sites) → regression `test_vton_person_reference.py` (19/19) + live 422.
No workaround stacking.

### §20 — Visual quality gate, artifacts recorded, never hidden · **VERIFIED**
`VISUALLY REVIEWED`
Representative complete-outfit result reviewed. Identity + hands-on-waist pose retained; garments layered correctly; **one duplicate-hands artifact in the waist region** documented (CV-quantified, §8). Artifact recorded, not hidden.

### §21 — Honest error states; 502 at worker boundary · **VERIFIED**
`TESTED AGAINST PRODUCTION API`
Worker unavailability surfaces as honest `503 VTON_WORKER_NOT_READY` at the worker boundary (not masked in the UI). "You have reached your GPU limit" is an honest platform-capacity message. No fake states.

### §22 — Security closure checklist · **VERIFIED (no unresolved critical)**
AuthN/AuthZ (§11), CSRF double-submit (job creation rejected without `X-CSRF-Token` = `CSRF_TOKEN_MISMATCH`), job owner-only isolation (§10), rate limits (20/hour), SSRF guards, no /tmp (§13), no image bytes in DB (§12), diagnostics gated (§15). No unresolved **critical**.

### §23 — Account hygiene (remove campaign test accounts) · **BLOCKED → PENDING**
This session created test accounts (uid 80, 82, iso A/B, layer probe, authz probes) plus prior campaign accounts (uids 60/62/63/64/70/71/74 + e2e-final8*/probe/csrf). **Production DB credentials are not in the execution environment**, so cleanup is **not executed** and is classified **PENDING** — not claimed complete. A narrowly-scoped, DBA-safe SQL (DELETE against the REAL production DB, matching only the identified test emails/uids, never touching legit users/admins) is prepared in `docs/CAMPAIGN_ACCOUNT_HYGIENE_20260905.md`.

### §24 — Final acceptance sequence (browser-originated) · **VERIFIED**
`TESTED IN REAL BROWSER`
The acceptance chain originated from the production frontend (real browser) → production API → real GPU worker. No direct worker call, local harness, static image, manual DB row, mocked API, or injected frontend state used as the final proof.

### §25 — Classification · see §1 above.

### §27 — Absolute engineering rules · **adhered**
No fake implementation/tests/results/users; no fixture/static/mock image as real; no client-controlled authorization; no permanent VTON image storage; no silent behavior-changing fallback (the `else [1]` blazer default was removed in `9010c2c`); every claim backed by code inspection, test, live request, deployment evidence, or explicit external dependency.

---

## 4. Evidence artifacts (workspace)

| Path | Contents |
|---|---|
| `/home/user/accept_evidence.json` | E2E session, stale-closure proof, layer chain, download |
| `/home/user/accept_run.log` | Step-by-step browser run |
| `/home/user/accept_download.png` | The real downloaded complete-outfit VTON result (529,859 B, PNG) |
| `/home/user/accept_canvas.png` | Canvas capture of the rendered result |
| `/home/user/accept_result.png` | Screenshot of the UI result |
| `/home/user/accept_face_cv.json` | Coarse identity + pose CV metrics (NCC, HSV Pearson, waist-band hand-blob counts) |
| `/home/user/accept_skin_person.png` / `_result.png` | Skin-mask visualizations |
| `/home/user/ab_isolation_results.json` | User A/B isolation matrix |
| `/home/user/authz_results.json` | AuthN/AuthZ matrix |
| `/home/user/production_health.json` | Production DB schema/health/engine identity from `/api/v1/health` |
| `/home/user/layer_order_reverse.json` | Request-order-independence proof (`[1,3]` → `[upper_inner, upper_outer]`) |
| `docs/CAMPAIGN_ACCOUNT_HYGIENE_20260905.md` | DBA-safe cleanup SQL (PENDING) |

---

## 5. Open items (non-critical, explicitly named)

1. **§23 test-account cleanup** — **PENDING** (DB credentials not in execution environment; narrowly-scoped, DBA-safe SQL prepared for the REAL production DB; never touches legit users/admins). Not claimed complete.

§15 (anonymous-404 diagnostic hardening) is **closed**: shipped in `015c2d2`, `TESTED LOCALLY` (5/5), `TESTED IN CI` (all gating green), and `TESTED AGAINST PRODUCTION API` (anonymous → 404 verified live).

**Final post-deploy verification on `015c2d2`:** anon `/api/v1/diagnostic` → 404; anon `/api/_dbops` → 404; empty `multi-render` → 422 `VTON_INPUT_INVALID`; `/api/v1/health` → 200 (DB healthy, schema `ok` @ `0016_vton_temporary_delivery`); anon `/auth/me` & `/admin/audit` → 401. All prior fixes intact.

---

## 6. Credential advisory (standing)

The following were pasted into chat and must be **rotated**: GitHub PAT (×2), Modal token, Neon `DATABASE_URL`, OpenAI/Gemini/Groq keys, Vercel token. They were used inline/transiently only and never persisted or committed.
