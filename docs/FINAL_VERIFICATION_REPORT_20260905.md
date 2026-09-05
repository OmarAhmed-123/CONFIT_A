# CONFIT_A — Final Production Verification Report (2026-09-05)

**Classification: `PARTIALLY_VERIFIED`**

This report covers the 2026-09-05 production-closure directive (23 items).
Every claim below is backed by a live production request against
`https://confit-a.vercel.app` (deployment of main @ `c60acc7`), a CI run, a
code inspection, or an explicit blocker. Nothing is "verified in theory."

---

## 1. Classification rationale

`VERIFIED_PRODUCTION_VTON` requires ALL gates. The following gates are NOT
fully satisfied, which forces `PARTIALLY_VERIFIED`:

| Gate | Status | Evidence / blocker |
|---|---|---|
| Security clean (dbops, probes, secrets) | PASS | `_dbops` 404 live; gitleaks green; tree scan clean |
| F-14 fixed + live verified | PASS | Full matrix below, all correct |
| Registration identity consistent | PASS | uid 48 chain |
| Production DB revision | PASS | health: `0016 = 0016` |
| API healthy / Bearer / RBAC | PASS | Full matrices below |
| Worker healthy (engine/commercial/A10/real inference) | PASS | Real inferences succeeded; config in health |
| Worker git-sha revision pin | **NOT VERIFIED** | `VTON_WORKER_EXPECTED_GIT_SHA` value not inspectable without production env access; not claimed active |
| Real FASHN inference + full-outfit chaining | PASS (2 layers) | Live 2-layer jobs 46.8s/47.7s completed; **3+ layers exceed the 60s function limit (see §9.3)** |
| Person identity + pose preserved, no duplicated anatomy | PASS (measured) | CV: drift 0.0068–0.0087, hands 2→2; visual artifacts documented §9.4 |
| 502 regression | PASS | Multiple animated + job calls: 200s, no 502 |
| **Temporary delivery reliable across instances** | **FAIL** | One-shot download endpoint returned **410 to the OWNER** on first attempt (cross-instance staging); in-response data URL is the only reliable carrier (now explicit in the contract) |
| **Frontend real-result flow (browser)** | **NOT DONE** | No browser available in this environment; bundle audited statically; click-through explicitly NOT performed |
| No permanent retention | PASS | Code + tests + pre-removal live DB row check (no output URL / inline bytes) |
| Global audit | PASS | No Egypt/EGP/localhost/fixed-host runtime assumptions |
| Regression suite | PASS | 945 passed / 7 skipped / 1 known env artifact; CI green incl. pose tests |

Per the directive: ANY unverified/blocked gate ⇒ `PARTIALLY_VERIFIED`.

---

## 2. Commits, branches, SHAs

| Ref | SHA | Content |
|---|---|---|
| `main` (production) | **`c60acc7`** | merge of all three fix branches |
| `security/fix-registration-role-escalation` | `17cc74c` | PR #52 (merged) |
| `security/fix-measurement-session-idor` | `875e65c` | PR #53 (merged) |
| `feat/vton-temporary-delivery` | `fa7e18b` | PR #51 (merged); base work `c609ace` |
| merge commit (pushed to main) | `27f58a3` → `c02b484` → `c60acc7` | role → F-14 → VTON |
| includes (via feat) | `638be1a` (model_used clamp), `86b138e`+`f2eafb9` (bearer redaction), migration `0016_vton_temporary_delivery` | verified in tree |
| Vercel production | main → auto-deploy on push (GitHub integration); live-verified new tree by behavior (§3) | previous alias `dpl_6Kqk24FXqCpHeCMHLrwkofH8ZV1a` superseded |
| Modal worker | `fashn_vton_segfee` (fashn-AI/fashn-vton-1.5 fork @ `7c0f10af`), commercial, A10 | **not redeployed** (no Modal credentials in environment); no redeploy was required |
| Migrations | production DB = `0016_vton_temporary_delivery` (live health check); no 0017 required (F-14 is code-level only) | |

CI (GitHub Actions, on the merge commit `c60acc7`): `ci` **success**,
`gitleaks` **success**. Earlier feat-branch CI failures were a missing
system library on the runner (`libEGL.so.1`, then `libGLESv2.so.2` for the
MediaPipe pose harness) — fixed in CI config (`fa7e18b`/`8668f2e`), pose
regression tests now RUN and PASS in CI.

Branch protection on `main` (2 required status checks) was enforced live:
an un-CI'd merge push was rejected; after CI green on the merge commit, the
push was accepted. No branch was merged with failing checks.

## 3. Clean production tree verification (item 1)

Deployed tree (= main @ `c60acc7`, byte-identical to the locally tested
deploy tree `f6de156` plus the CI workflow fix):

- **`/api/_dbops` → 404 live for anonymous AND consumer** (measured:
  `anon_status: 404, consumer_status: 404`). The route was never
  role-gated, so 404 for anon+consumer implies 404 for admin.
  Admin-user live test not performed (no admin account exists outside
  the owner's; route absence is role-independent).
- No `dbops|probe|debug|diagnostic|temporary-production-helper` markers in
  `backend/app` + `api` (grep over final tree; only hits: admin-RBAC-
  protected `/health/vton-contract` diagnostic, docstrings, one test file
  `test_vton_contract_diagnostic.py` which is outside the production
  closure).
- No `X-Diag-Trace` or other debug instrumentation.
- Secrets scan: gitleaks CI green on all branches + manual pattern scan
  (ghp_/github_pat_/xox/sk-/AKIA/vcp_/postgres DSN/JWT/private keys) over
  `backend frontend api` → only docstring/test placeholders.
- No `.env` files shipped (only `vercel.json`); no generated production
  result images in the tree (test fixtures = real single-person photos
  with attribution, test-only, outside the production closure; CV models
  are MediaPipe weights, test-only).

## 4. Identity, registration, auth (items 6, 8, 11)

Live, on the new deployment:

**Role matrix** (real registrations): `plain` → 201 CONSUMER,
`role=admin` → 201 CONSUMER, `crafted` (role+user_role+is_admin) →
201 CONSUMER. Client-controlled role: **rejected server-side**.

**Identity chain** (fresh user via real registration):
register 201 (uid 48, role consumer) → login 200 → JWT → `/auth/me` 200
(uid 48, consumer) → **consistent: true**. No manual DB inserts anywhere
in this campaign.

**Bearer matrix** (live): valid JWT 200 · truncated 401 · bare `***` 401 ·
missing scheme 401 · Vercel-redacted `***<jwt>` 200 (recovery fix works;
the JWT is still fully signature-validated — no bypass) · forged signature
401 · wrong type forged 401.

**RBAC**: consumer → `GET /api/v1/admin/analytics` = **403**.

## 5. F-14 measurement-session live matrix (item 7)

Two rounds (first round exposed invalid test bodies; corrected round is
authoritative):

| Check | Result |
|---|---|
| A creates session (no consent field) | 201, `consent_granted=false` (default False — never assumed) |
| A reads own session | 200 |
| B reads A's session | **404** |
| Anonymous reads A's session | **404** |
| A writes valid results to own session | 201 |
| **A posts `consent_granted: true` via results (fabrication attempt)** | 201 accepted as data, but re-read → **`consent_granted` still `false`** — consent cannot be fabricated via request input |
| B writes valid body to A's session | **404** |
| Anonymous writes valid body to A's session | **404** |
| Unknown session id (B) | 404 — byte-identical status, **no existence oracle** |
| Anonymous create | 422 (rejected) |

F-14: **closed with live evidence** (not unit tests only).

## 6. VTON — engine, inference, chaining (items 9, 11, 15)

- **Worker**: `fashn_vton_segfee` (commercial, Apache-2.0 fork;
  non-commercial human-parser removed), A10. Real inference confirmed by
  completed jobs (25–48s). Per-job readiness gate passes on every success.
- **502 regression**: retested live — `POST /try-on/animation-render`
  (1 garment: 200 @ 41.9s; 2 products: 200 @ 24.0s/29.3s) and all
  `/try-on/jobs` calls: **no 502, no worker-URL 404**.
- **Worker contract discovered live**: the deployed worker enforces
  **max 1 garment per inference call** ("fashn_vton_segfee is
  single-category; max 1 garment per job"). The feat branch therefore
  implements **sequential single-garment chaining**: layer i renders on
  layer i−1's output (same architecture as the animated path); the final
  frame is the complete-outfit result; metrics record the ordered
  `outfit_layers`; a mid-chain failure fails the job (no partial image as
  success). Chaining is proven by unit tests (layer-2 input == layer-1
  output asserted) and live (2-layer jobs completed in ~47s ≈ 2× single
  garment ~25s).
- **Layer ordering**: garments are applied in request order; slot dedupe
  keeps one garment per slot (two outerwear items → one applied). For
  best visual layering the frontend should send inner-first (see §9.4).
- **60s platform limit** (see §9.3): 2-layer outfits complete in
  46.8–47.7s warm but **504'd once at 60.2s under load**; 3+ layers will
  exceed the limit reliably. `vercel.json` sets `maxDuration: 60`
  (plan-dependent ceiling). This is a platform constraint, documented,
  not faked: no background queue exists (async-honesty), and the failure
  is a truthful 504, never a fake success.

## 7. Person identity & pose — measured (items 10, 12)

CV harness (MediaPipe hand + pose landmarkers, `backend/tests/
vton_artifact_check.py`, test-only, outside the production closure):

| Pair (production render) | hands | pose drift | verdict |
|---|---|---|---|
| Single garment, hands-on-waist person | 2 → 2 | 0.0087 | PASS |
| Full outfit [blazer, shirt] (outer-first), hands-on-waist | 2 → 2 | 0.0087 | PASS |
| Full outfit [shirt, blazer] (inner-first), hands-on-waist | 2 → 2 | 0.0068 | PASS |

Regression suite (7 tests): mirror-transformed result of the hands-on-waist
fixture **FAILs** (drift 0.1309 ≥ 0.07 → pose transfer detected), clean
pair PASSes (drift < 0.02), extra/missing hand detected, garment-derived
pose transfer structurally impossible in the worker payload.

**Honest visual limitations** (inner-first full-outfit render): identity
(face/hair) and pose (hands-on-waist, stance, limbs) preserved; both
garments visible in correct layering (white oxford shirt under blue
blazer); no duplicated hands/arms/limbs. Artifacts: dark smudge along one
arm/jacket edge, white distortion at one fist/wrist, and the input photo's
watermark faintly retained in the background. The model does not
guarantee perfect pose preservation — the measured drift (≤0.009) and
hand counts are the honest metric, plus this documented human review.

## 8. Temporary delivery & isolation (items 12, 13)

Live on the new deployment:

- Result delivered **in the authenticated response**
  (`result_image_data_url`, 510–564 KB PNGs decoded and inspected) —
  the **guaranteed carrier**, now explicit in the API contract
  (live-verified fields: `carrier: "in_response"`,
  `guaranteed_field: "result_image_data_url"`, `download_note`
  "best-effort one-shot; 410 possible within TTL under multi-instance
  serverless routing").
- Job read isolation: other user 404, anonymous 404 (no oracle).
- One-shot download endpoint: other user with owner token **404**,
  anonymous with owner token **404**, reuse **410** — all correct.
- **Owner first download: 410** (staged bytes live on the completing
  function instance; the follow-up GET routed to another instance).
  **This is the unresolved reliability gap.** The endpoint is now
  explicitly documented as best-effort (not a 900s guarantee); the
  frontend renders/downloads from the in-response bytes (bundle audit:
  `renderTryOn`/`renderAnimationTryOn` consume the response data URLs;
  Blob download; no permanent local storage of bytes).
- Recommended fix for a reliable follow-up download (not implemented —
  requires storage credentials not present in this environment): a
  short-TTL (≤15 min) object-store copy with forced expiration. This is
  *temporary* retention (cleanup/expiration), compatible with the
  no-permanent-storage rule — but it needs R2/S3 config, which I cannot
  provision here.
- No permanent retention: job row carries token hash + expiry only;
  no output URL, no inline bytes (live DB row check pre-`_dbops`-removal;
  code + unit tests post-removal).

## 9. Frontend (item 14)

- **Static bundle audit (done)**: current production JS bundle — real API
  calls only (`/try-on/jobs`, status, cancel, garment asset,
  `renderTryOn`, `multiRenderTryOn`, `renderAnimationTryOn`); zero
  mock/fixture/static-image substitution; person image vs garment
  separation in the request payload; no secrets in bundle; in-response
  data-URL rendering + Blob download; no permanent local storage.
- **Browser click-through: NOT performed — no browser is available in
  this environment.** Per the directive, this is an explicit remaining
  gap, not a claimed verification. The API-level flow (register → login →
  job → result → isolation) is fully live-verified with the exact
  payloads the frontend sends.

## 10. Performance (item 20) — live production, in-request (no queue)

| Scenario | n | min (s) | P50 (s) | max (s) |
|---|---|---|---|---|
| Single garment (warm worker) | 3 | 25.2 | 25.7 | 31.5 |
| Full outfit, 2 layers, inner-first (warm) | 3 | 46.8 | 47.3 | 47.7 |
| Full outfit, 2 layers (under concurrent load) | 1 | — | — | **60.2 → 504** |
| Animated render (1 layer, after slot dedupe) | 3 | 24.0 | 29.3 | 41.9 |
| Cold worker start (earlier round, same deployment line) | 1 | ~15 s extra | | |

Frontend-visible latency = end-to-end request time (execution is
in-request; there is no background queue — documented honestly).
Worker-only measurements were NOT used for these numbers.

## 11. Security cleanup & account hygiene (item 19)

- `_dbops` removed from the tree and **live 404** (§3). No diagnostic/
  probe/debug tooling in the deployed tree.
- Secrets: gitleaks green + manual scan clean (§3). The GitHub token
  pasted in chat was used transiently (git push + REST) only, never
  written to any file/commit/bundle. **Rotate it.** (All previously
  pasted credentials remain advised-for-rotation.)
- **Campaign test accounts: 40 created across the campaign** (22
  documented earlier + 18 this round). Deletion is BLOCKED from this
  environment: the app has no admin user-disable/delete route and no
  production DB credentials exist here (credential policy). Risk is
  contained: all are CONSUMER (server-enforced), zero commerce state,
  no admin reach, no generated-image data. Exact scoped removal list +
  SQL for the owner/DBA: `docs/CAMPAIGN_ACCOUNT_HYGIENE_20260905.md`
  (update that file's Section C with this round's users before running:
  all `@e2e-final2/3/4/5/6/7.example.com` domains are campaign-generated
  and cannot collide with legitimate users).

## 12. Global readiness (item 17)

Runtime scan of `backend/app` + `api`: no Egypt/Cairo/EGP hardcoding
(payment-provider registry entries for Paymob/MISR are legitimate
configurable capabilities with multi-currency rate config; no single-
country assumption in core flow); `localhost` only in dev defaults
(Redis URL, CORS allowlist — configurable); Modal host only in a
docstring (real URL from env settings); no local-filesystem persistence
for VTON output. Product is globally deployable without architecture
changes.

## 13. Authorization audit (item 18)

Repository-wide audit (146 endpoints, all stateful domains: auth, users,
profiles, orders, cart, checkout, payments, wardrobe, try-on,
measurements, favorites, uploads, downloads, admin, brand, notifications,
webhooks, share links, search/history) — per-endpoint: authentication,
ownership via `get_current_user` only (never client `user_id`),
ID-enumeration behavior (404, no oracle), role enforcement. **F-14
(measurement sessions) was the single remaining authorization hole; it is
fixed (PR #53) and live-verified (§5).** Role escalation (registration)
fixed (PR #52) and live-verified (§4). Bearer redaction recovery
(86b138e/f2eafb9) live-verified with forged-token rejections (§4).

## 14. Test status (item 21) — exact counts

| Suite | passed | failed | skipped | blocked |
|---|---|---|---|---|
| Full suite, merged tree `c60acc7` (local, isolated run) | **945** | 1* | 7 | 0 |
| Full suite, same tree (GitHub Actions `ci` job) | green (4 pose tests now run in CI) | 0 | — | 0 |
| Full suite, F-14 branch `875e65c` | 881 | 0* | 7 | 0 |
| VTON subset (person-reference 11 + pose 7 + delivery 24 + pipeline 4) | 46 | 0 | 0 | 0 |
| Live production battery (this report) | §3–§10 tables | §1 gates marked FAIL/NOT DONE | — | browser click-through (no browser), worker git-sha pin (no env access), 3+-layer full outfits (60s platform limit) |

\* the single local failure is the known environment artifact
`TestAlembic::test_upgrade_downgrade_round_trip` (system `python3` lacks
the `alembic` module; the migration itself is exercised by the CI
"postgres migration chain + schema gate" job, which passes).
Blocked items are NOT counted as passed.

## 15. Real remaining issues (no hiding)

1. **One-shot download endpoint is not reliable across serverless
   instances** (owner got 410 within TTL). Mitigated by contract
   (in-response bytes are the guaranteed carrier; endpoint labeled
   best-effort; frontend uses in-response bytes). Full fix needs a
   short-TTL object store (credentials not available here).
2. **Multi-layer inference vs 60s function limit**: 2-layer outfits sit
   at the limit (one live 504 observed under load); 3+ garments will
   reliably exceed it. Fix = higher `maxDuration` (plan-dependent) or a
   real background-job architecture (out of scope per the async-honesty
   rule; currently truthful 504, never fake success).
3. **No browser click-through** of the production frontend (no browser
   in this environment) — API-level flow fully verified; UI-level
   confirmation remains manual.
4. **Worker git-sha revision pin unverified** (production env not
   inspectable from here); not claimed active.
5. **Test-account cleanup blocked** (no admin delete route, no DB
   credentials in environment) — scoped list + SQL prepared
   (`docs/CAMPAIGN_ACCOUNT_HYGIENE_20260905.md`).
6. Visual artifacts on full-outfit renders (smudge/distortion at garment
   boundaries, background watermark retention) — inherent to the model;
   measured and documented, not claimed perfect.

## 16. Deploy record

Order followed: code merged (CI green) → Vercel auto-deploy from main →
deployed code verified by live behavior (new fields `carrier/
guaranteed_field/download_note` present, `_dbops` 404, schema 0016,
health healthy) → no migration required (DB already 0016) →
auth/authz/VTON/pose/delivery live-verified. Production was never
left DB-ahead-of-code (no 0017 exists; 0016 pre-applied).
