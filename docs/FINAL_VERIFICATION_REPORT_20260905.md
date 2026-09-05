# CONFIT_A — Final Production Verification Report (2026-09-05, round 2)

**Classification: `PARTIALLY_VERIFIED`**

Covers the 2026-09-05 directive (items 0–38). Every claim below is backed by
a live production request against `https://confit-a.vercel.app` (deployment
of main @ `3e5c49e`), a CI run on that SHA, a code inspection with file:line
references, or an explicit labeled blocker. Nothing is "verified in theory."

**What changed in this round:** the deliberate layer-order fix (item 17) was
implemented, tested, deployed, and verified live (byte-identical renders
across all request orders); the delivery contract no longer advertises the
one-shot endpoint as a download promise (items 19/20); `maxDuration` was
raised to 300 s and the plan accepted it, so complete multi-garment outfits
now complete inside one production request (item 18); /tmp compliance was
measured (item 27: zero runtime usage).

---

## 1. Classification rationale (gate table)

`VERIFIED_PRODUCTION_VTON` requires ALL gates. Current state:

| Gate | Status | Evidence |
|---|---|---|
| Security clean (dbops, secrets) | PASS | `_dbops` 404 anon+consumer live; gitleaks green on `3e5c49e`; secret-leak check on health output CLEAN |
| Registration / role escalation | PASS | tree unchanged since `17cc74c` (PR #52); live register+login this round |
| F-14 measurement-session IDOR | PASS | tree unchanged since `875e65c` (PR #53); full live matrix previous round |
| Production DB = real configured DB, revision 0016 | PASS | all checks via live API → real DB; live health `0016 = 0016`; no replacement DB created (item 0, absolute) |
| API healthy / Bearer / RBAC | PASS | live matrices (auth code unchanged this round; re-probes §5) |
| Worker healthy (engine/commercial/A10/real inference) | PASS | 13 real FASHN inferences live this round; engine `fashn_vton_segfee` commercial valid |
| Worker git-sha pin independently readable | **NOT VERIFIED** | worker source pin declared in API config (`config.py:86` = `7c0f10af`); live behavior matches the contract; Modal deployment SHA not readable from this environment (no Modal credentials) — labeled, not claimed |
| Real inference + full-outfit chaining | **PASS (3 layers)** | live 3-garment jobs completed at 65.1–72.9 s on the 300 s ceiling (was 504/impossible at 60 s) |
| **Deliberate category-aware layer order (item 17)** | **PASS** | byte-identical renders across request orders (jobs + production multi-render endpoint); CV PASS; visual side-by-side committed (§8) |
| Person identity + pose preserved, no duplicated anatomy | PASS (measured) | project CV validator: drift ≤ 0.0089, hand delta 0, no wrist swap, on all 4 live artifacts this round |
| 502 / 504 regression | PASS | 13 live inferences: no 502; 504 eliminated (previous 504 @ 60.2 s was the 60 s limit, now 300 s) |
| **Delivery reliable (items 19/20)** | PASS | guaranteed user-facing download = in-response data URL + frontend Blob (verified live on the production endpoint); contract no longer advertises the one-shot endpoint as a promise; isolation 404s live |
| No permanent retention; no image bytes in DB | PASS | staging = in-process memory TTL 900 s (`vton_delivery.py:104`); DB holds metadata only (verified previous round); `/api` returns data URL, not a durable URL |
| **/tmp compliance (item 27)** | PASS | 0 hits for `/tmp|mktemp|tempfile|TemporaryDirectory|NamedTemporaryFile` in `backend/app` + API runtime code (scanned this round); no /tmp in VTON/delivery/queue/state |
| Global readiness (no Egypt/EGP/localhost/fixed-host assumptions) | PASS | audited previous round; no such code changed this round |
| Env presence on deployed runtime (item 29) | PASS (non-secret) | live health: `database: healthy` (DATABASE_URL works), `vton_pipeline: configured: GPU worker URL + admin token present`; all worker URLs function behaviorally; no secret value ever printed |
| SHA chain Git→Vercel→live behavior (item 31) | PASS | main `3e5c49e` → push → deploy → new contract text + new order semantics + 3-layer support all live (present only in this tree) |
| SHA chain Git→Modal worker→live behavior (item 31) | PASS (behavioral) | worker unchanged since previous round's verified deploy; contract + 13 live inferences consistent; SHA pin value = `7c0f10af` per API config; independent Modal SHA read not possible (labeled) |
| Frontend real-result flow (browser) | **NOT DONE** | no browser in this environment; machine-verifiable parts ALL verified (§10): exact endpoint, payload, response contract, in-response data URL, Blob download code present in the deployed production bundle; manual click-through left to owner — explicitly NOT performed |
| Regression suite | PASS | 947 passed / 7 skipped / 1 known env artifact (local); CI `ci`+`gitleaks` success on `3e5c49e` |
| Test-account hygiene | PASS (documented) | 4 new e2e accounts this round, listed §4; DBA-safe cleanup SQL documented; no legitimate users touched; no separate DB created |

Per the standing rule: ANY unverified/blocked gate ⇒ `PARTIALLY_VERIFIED`.
Exactly two gates remain, both **environment-bound, not functional defects**:
(1) browser click-through — no browser available in this execution
environment; (2) independent read of the Modal worker's deployed SHA — no
Modal credentials in this environment. All functional gates PASS with live
production evidence.

---

## 2. Repository

| Ref | SHA | Content |
|---|---|---|
| `main` (production) | **`3e5c49e`** | `7f06caa` (fix) + `3e5c49e` (duration probe) |
| `7f06caa` | fix(vton): deliberate category-aware layer order + honest delivery contract | PR #54 (merged via main push) |
| `3e5c49e` | chore(vercel): `maxDuration` 60 → 300 | accepted by the plan (build succeeded; 3-layer jobs now complete live) |
| branch | `fix/vton-layer-order-delivery` | CI `ci` success + `gitleaks` success on `3e5c49e` |
| previous production code | `c60acc7` (docs at `382c43c`) | superseded by this round |
| Modal worker | **not redeployed this round** (unchanged since previous verified deploy); expected source per API config `config.py:86`: `fashn-AI/fashn-vton-1.5 @ 7c0f10af (vendor/fashn-vton-segfee)`, commercial, A10 | contract re-proven behaviorally by 13 live inferences |
| migrations | production DB = `0016_vton_temporary_delivery` (live health this round); **no 0017** (not required) | DB never moved ahead of code |

Deployment record (live): API served with `x-vercel-id`
`pdx1::iad1::56zqk-1788631872282-980e3ff81d82` /
`pdx1::iad1::wkrt9-1788632193210-b7b6084ac455` (routing IDs — Vercel does
not expose deployment IDs on public responses; SHA→deploy linkage is
behavioral: the new `download_note` text and the new ordering semantics
exist only in this tree and are live). Frontend bundle
`/assets/index-B4P19E5J.js` — identical content hash to the previous deploy
because no frontend source changed this round (deterministic build; verified
the bundle contains the Blob download flow, §10).

---

## 3. Database (item 0 absolute rule, item 21)

- **No replacement/empty/in-memory/SQLite/tmp database was created;
  `DATABASE_URL` was never changed.** Every production verification in this
  report went through the deployed application's public API, which reads and
  writes the configured production database.
- Live schema gate (two separate calls this round):
  `expected_head 0016_vton_temporary_delivery = database_revision
  0016_vton_temporary_delivery`, `missing_tables: []`, `verdict: ok`.
- **No image bytes in the database** (verified previous round against the
  live DB: the VTON tables carry job_id/user_id/status/timestamps/metrics/
  delivery token hash/expiration/content type only; `output_image_url` is
  NULL by contract — schema comment `schemas/tryon.py:55-57`).
- Test-account hygiene (this round): 4 new e2e accounts —
  `final8.deploy.b91c7c@e2e-final8.example.com`,
  `final8c.*@e2e-final8c.example.com`, `final8d.*@e2e-final8d.example.com`
  (one per delivery battery; emails follow the `e2e-*` pattern). No admin
  deletion route exists and no DB credentials are available in this
  environment, so cleanup remains the documented DBA-safe SQL in
  `docs/CAMPAIGN_ACCOUNT_HYGIENE_20260905.md` (owner executes against the
  real production DB; **never** against a separate database). No legitimate
  users or admins were touched.

---

## 4. Auth (live, this round, on tree `3e5c49e`)

- `GET /api/v1/health` anon → 200; `GET /api/v1/users/me` anon → 401
  (unauthenticated rejected).
- Truncated bearer / bare-`***` / forged / schemeless bearer → 401 on
  protected GETs (full matrix re-run previous round on `c60acc7`; the auth
  code path is unchanged between `c60acc7` and `3e5c49e` — diff limited to
  `tryon_service.py`, `schemas/tryon.py`, tests, `vercel.json`, docs).
- Bearer marker never bypasses JWT validation (invariant, code unchanged).
- Live registration + login performed this round (real flow, real DB rows).

## 5. Authz (live)

- `GET /api/_dbops` anon → **404**, consumer → **404** (re-probed this
  round on the new tree).
- Consumer token against admin surface → rejected (403/404 per route
  existence; no data returned; consumer cannot read admin data — full role
  matrix verified previous round, code unchanged).
- Job isolation (re-probed this round): owner `GET /try-on/jobs/{id}` →
  200; other authenticated user → **404**; anon → **404**.

## 6. Identity (live)

- Server-derived identity only: job rows created by this round's e2e users
  belong to the registering account (owner 200 / foreign 404 above). No
  `user_id` in request bodies is trusted; no `localStorage.userId`; no
  client role.
- New production users created **only** via the real registration flow
  (no manual DB inserts/updates — and no DB access exists in this
  environment anyway).

---

## 7. VTON — engine, inference, chaining, LAYER ORDER (items 9, 11, 13, 15, 17)

**Engine (live health, this round):** `fashn_vton_segfee`, `valid: true`,
`commercial: true`, Apache-2.0 fork with the non-commercial human-parser
removed from the runtime; `source: CONFIT_A fork of fashn-AI/fashn-vton-1.5
@ 7c0f10af (vendor/fashn-vton-segfee)`.

**Real inference this round (all live, production API, real A10 GPU worker,
1 garment per worker call, sequential chaining):**

| # | Endpoint | Request `product_ids` | Result | Time |
|---|---|---|---|---|
| deploycheck | jobs | `[1]` | 202 completed, data URL in response | 42.5 s |
| A1 | jobs | `[1, 3]` (blazer first) | 202 completed | 52.7 s |
| A2 | jobs | `[3, 1]` | 202 completed | 46.6 s |
| A3 | jobs | `[1, 3, 4]` (3 layers) | 202 completed | 72.9 s |
| A4 | jobs | `[3]` | 202 completed | 30.8 s |
| A5 | jobs | `[1, 3]` | 202 completed | 47.8 s |
| delivery | jobs | `[3]` | 202 completed, data URL 654,790 chars | 50.2 s |
| probe2 | jobs | `[4]` | 202 completed, byte_size 496,209 | — |
| A6 | jobs | `[4, 1, 3]` (shuffled 3) | 202 completed | 71.7 s |
| M1 | **multi-render (production frontend endpoint)** | `[1, 3]` | 200 completed, data URL | 46.9 s |
| M2 | multi-render | `[3, 1]` | 200 completed, data URL | 40.0 s |
| M3 | multi-render | `[4, 1, 3]` | 200 completed, data URL | 65.1 s |
| +1 earlier probe | jobs | `[4]` | 202 completed | — |

No 502, no 504. 3-garment complete outfits now complete inside one
request (item 18 resolved: 300 s ceiling accepted by the plan).

**Layer order (item 17) — THE fix of this round.**

Root cause: `_build_garments_payload` (`tryon_service.py:312`, the single
choke point for BOTH the jobs chain and the multi-render chain) applied
garments in **client request order**. Live proof of the bug (previous
round): request `[blazer, shirt]` rendered the blazer as the inner layer
and **hid the shirt entirely** (see committed evidence image, left panel).

Fix: `_build_garments_payload` now sorts by the canonical anatomical
hierarchy `SlotLayeringEngine.LAYER_HIERARCHY`
(`styling/slot_layering_engine.py:46`): inner tops (2) → outerwear (4) →
bottoms (10) → footwear (20) → accessories (30). Deterministic regardless
of request order; the animated path already used engine ordering
(`tryon_provider.py:106`).

Live verification on the new deployment — **the render pipeline is
deterministic, so byte identity across request orders is the test**:

| Render | Request order | md5 |
|---|---|---|
| A1 (jobs) | `[1, 3]` blazer first | `143e2e0a…74ee` |
| A2 (jobs) | `[3, 1]` shirt first | `143e2e0a…74ee` |
| A5 (jobs) | `[1, 3]` re-run | `143e2e0a…74ee` |
| M1 (multi-render) | `[1, 3]` blazer first | `143e2e0a…74ee` |
| M2 (multi-render) | `[3, 1]` | `143e2e0a…74ee` |
| previous round, verified-correct inner-first | `[3, 1]` | `143e2e0a…74ee` |
| A3 (jobs) 3-layer | `[1, 3, 4]` | `3dadf3fa…b80b` |
| A6 (jobs) 3-layer | `[4, 1, 3]` shuffled | `3dadf3fa…b80b` |
| M3 (multi-render) 3-layer | `[4, 1, 3]` shuffled | `3dadf3fa…b80b` |

- The formerly-buggy request order `[blazer, shirt]` now produces the
  **byte-identical** image to the previously verified correct order, on
  BOTH endpoints.
- API responses now report the deliberate order honestly:
  `applied_items` `[3, 1]`, `layering_order: ["upper_inner", "upper_outer"]`
  (M1/M2), `["upper_inner", "upper_outer", "lower"]` (M3) — no hidden
  layers, no duplicates (same-slot dedupe unchanged).
- Visual evidence (committed):
  `docs/EVIDENCE_layer_order_fix_20260905.png` — left: old tree, request
  `[blazer, shirt]`, shirt hidden under the blazer; right: new tree, same
  request, white shirt visibly layered under the blue blazer.

**Regression tests (committed, `tests/test_vton_person_reference.py`):**
`test_layer_order_is_deliberate_not_request_order` — request `[1, 3]`
(blazer, shirt) asserts the worker receives shirt first
(`slot_type upper_inner`), blazer second (`upper_outer`), chain intact
(layer 2 renders on layer 1's output), and metrics record the sorted
order; `test_full_category_ordering_inner_to_outer` — a
3-category request asserts the canonical
`upper_inner → upper_outer → lower` order. Both PASS.

**Person identity + pose + no duplicated anatomy (project CV validator
`tests/vton_artifact_check.py`, run on the live artifacts this round):**

| Artifact | verdict | pose drift | hand delta | wrist swap |
|---|---|---|---|---|
| A1 (2-layer) | PASS | 0.0068 | 0 | no |
| A3 (3-layer) | PASS | 0.0089 | 0 | no |
| A4 (single) | PASS | 0.0064 | 0 | no |
| A6 (3-layer shuffled) | PASS | 0.0089 | 0 | no |

Reference person: `person_hands_on_waist.jpg` (2 hands). The uploaded
person remains the identity + pose anchor in every artifact; no extra
hands; pose drift ≤ 0.0089 (warn 0.05 / fail 0.07).

---

## 8. Delivery (items 19, 20)

**Guaranteed user-facing download path = in-response bytes + frontend
Blob — verified end-to-end as far as is possible without a browser:**

1. Every completed job/multi-render response this round carried the
   generated image **in the authenticated response**
   (`result_image_data_url` / `rendered_result_url` as data URLs —
   measured: 654,790 chars / byte_size 496,209). The multi-render path's
   GPU output travels in-response by code contract
   (`tryon_service.py:1213-1217`: "travels in the authenticated response
   only … NEVER written to durable storage").
2. The production frontend (`VirtualTryOnModal.tsx:93-113`) renders that
   data URL and the user's Download button performs a **client-side Blob
   download** (`URL.createObjectURL`) — no server round-trip, works on
   every serverless instance. The deployed production bundle
   `index-B4P19E5J.js` was fetched and verified to contain the Blob
   download flow (`confit-try-on-` download name + `createObjectURL`
   present; no `_dbops` or any diagnostic code in the bundle).
3. The API contract no longer advertises the one-shot endpoint as a
   download promise (live in this round's responses):
   "Guaranteed user-facing download = the frontend Blob download of
   result_image_data_url from THIS response (always works). download_url
   is an opportunistic one-shot cache, NOT a download promise … 410
   possible within the TTL under multi-instance serverless routing."
4. Measured behavior of the opportunistic cache this round: present in the
   create response (token, `ttl_seconds: 900`, `one_time: true`); a
   seconds-later GET of the job from a different owner context returned
   `delivery: null` (GET routed to an instance without the in-memory
   staging) — exactly the documented cross-instance behavior of the
   non-guaranteed cache. The product-promise path (in-response) was
   unaffected in every case.

**Retention:** staging is in-process memory with a 900 s TTL and one-time
token semantics (`vton_delivery.py`); nothing is written to durable storage
or the DB; the DB stores metadata only (token hash, expiration, content
type, byte size — no bytes).

**Isolation (live this round):** owner job GET → 200; other user → 404;
anon → 404.

---

## 9. Frontend (item 14)

- Production bundle `index-B4P19E5J.js` served; deterministic content hash
  (frontend source unchanged this round); audited: contains the multi
  render flow, the Blob download, the honest error taxonomy
  ("Virtual try-on rendering is unavailable right now. Your photo was not
  modified."), no diagnostic endpoints, no `_dbops`, no client-side
  identity/authorization code.
- The exact production call is `POST /api/v1/tryon/multi-render` with
  `{product_ids (user selection order), user_image_url, avatar_model_id,
  consent_retain_photo}` — the response contract it consumes was verified
  live in §7 (data URL, deliberate `layering_order`/`applied_items`).
- **Explicit gap (no browser in this environment):** the click-through
  (open modal → select garments → render → click Download → file saved)
  was NOT performed and is NOT claimed. Every machine-verifiable segment
  of that path is verified above; the manual browser step is left to the
  owner.

---

## 10. Performance (item 35) — live production, in-request, user-visible

No queue exists (and none is faked): each job is synchronous in-request
GPU inference on the worker (1 garment/call, sequential chain). Queue
delay = 0 by construction. All numbers are wall-clock of the production
request, warm worker unless noted.

| Class | n | samples (s) | min / median / max |
|---|---|---|---|
| Single garment (jobs) | 3 | 30.8, 42.5, 50.2 | 30.8 / 42.5 / 50.2 |
| 2-garment (jobs) | 3 | 46.6, 47.8, 52.7 | 46.6 / 47.8 / 52.7 |
| 3-garment complete outfit (jobs) | 2 | 71.7, 72.9 | 71.7 / 72.3 / 72.9 |
| 2-garment (multi-render, production endpoint) | 2 | 40.0, 46.9 | 40.0 / 43.5 / 46.9 |
| 3-garment (multi-render, production endpoint) | 1 | 65.1 | 65.1 |

- The 42.5 s first job after deploy includes possible worker cold-start
  (previous round measured ~15 s cold on the A10); subsequent samples are
  warm.
- **Before (60 s ceiling):** 2-garment 504'd at 60.2 s under load;
  3+ garments structurally impossible. **After (300 s ceiling):** 3
  garments complete at 65–73 s with >150 s of headroom; a full 5-slot
  outfit (≤ ~150 s projected) fits inside the ceiling. This is a measured
  platform-capacity result, not a projection presented as fact: the
  5-slot figure is a projection (3-layer measured × slot count).
- P50/P95 at n=1–3 are reported as medians/ranges; with n this small a
  P95 estimator would be noise, and noise will not be presented as
  statistics.

---

## 11. /tmp compliance (item 27) — measured this round

- Scan of ALL runtime code (`backend/app` + the API entry): **0 hits** for
  `/tmp`, `mktemp`, `tempfile`, `TemporaryDirectory`, `NamedTemporaryFile`.
- VTON delivery staging: in-process dict with 900 s TTL
  (`vton_delivery.py:104` `self._entries: Dict[str, _Entry]`) — memory,
  not disk.
- No /tmp in: VTON delivery, job state, auth, identity, retention, queue,
  cache, assets, or application state. Test tooling writes ephemeral files
  only in CI/local test scratch space, outside the acceptance path, and no
  /tmp artifact is used as evidence of any production fix.

---

## 12. Test counts (exact)

| Suite | Result |
|---|---|
| Local full suite on branch tip `3e5c49e` | **947 passed, 7 skipped, 1 failed** — the single failure is the known environment artifact (`alembic` not installed in the local system python used for that test; the same test PASSES in CI where alembic is installed). 0 other failures. Includes the 2 new layer-order regression tests (945 → 947). |
| CI on `3e5c49e` (GitHub Actions, 2 required checks) | `ci` **success**, `gitleaks` **success** (full suite green on the runner, pose/MediaPipe harness included) |
| Live production battery (this round) | 13 real GPU inferences + delivery/isolation/auth probes (§7, §8, §4–6) |

---

## 13. Blockers (real, no hiding)

1. **Credential rotation (owner, security-critical):** GitHub PAT ×2,
   Modal token, Neon `DATABASE_URL`, OpenAI/Gemini/Groq keys, and Vercel
   token were pasted into chat earlier in this engagement. They must be
   rotated. Nothing in this report depends on any of them (the Vercel
   token is unrecoverable and was NOT needed — deploys are via
   push-to-main, verified behaviorally).
2. **Browser click-through (owner, manual):** no browser exists in this
   execution environment; the modal render → download click sequence is
   the one segment of the user flow not exercised in a real browser. All
   machine-verifiable parts are verified (§9).
3. **Independent read of the Modal worker's deployed git SHA (no access):**
   Modal credentials are not in this environment and the Vercel token is
   gone, so the worker deployment's SHA cannot be read independently.
   What IS verified: the worker's expected source is pinned in the API
   config (`7c0f10af`, `config.py:86`), the worker was last deployed and
   verified in the previous round, it was NOT changed this round, and 13
   live inferences this round behave exactly per that contract.
4. **maxDuration ceiling (platform):** 300 s is the plan-accepted ceiling;
   outfits whose sequential chain exceeds ~300 s cannot complete in one
   request. Current catalog (≤ 5 slots, ~25–30 s/garment) fits with
   headroom; if catalog depth grows, a real background-job architecture
   (durable queue + worker polling + DB status — no /tmp, no fake states)
   would be required. Not needed today; stated as a limit, not hidden.
5. **Test-account cleanup:** 4 e2e accounts remain in the production DB
   (list §3); deletion requires DBA access this environment does not have;
   the cleanup SQL is documented against the real production DB.

---

## 14. Classification

**`PARTIALLY_VERIFIED`**

Rationale: every functional gate of the 0–38 directive now PASSES with
live production evidence on tree `3e5c49e` — including the three that
failed or were impossible in the previous round (deliberate layer order;
reliable user-facing delivery; complete-outfit within the platform
ceiling). The classification is held at `PARTIALLY_VERIFIED` — and not
`VERIFIED_PRODUCTION_VTON` — solely by two explicitly labeled,
environment-bound gates: (1) the browser click-through, which cannot be
performed in this environment and is therefore NOT claimed (per the
standing rule: no browser claims without a browser); (2) the independent
read of the Modal worker's deployed SHA, which cannot be inspected without
Modal/Vercel environment access and is therefore NOT claimed active.
Neither gap indicates a defect; both are owner/infrastructure steps,
listed in §13. No "almost verified": the two gaps are named, evidenced as
environment-bound, and separated from every functional result above.

*Report generated 2026-09-05 (round 2). Supersedes the same-named
previous-round report (retained in git history at `382c43c`).*
