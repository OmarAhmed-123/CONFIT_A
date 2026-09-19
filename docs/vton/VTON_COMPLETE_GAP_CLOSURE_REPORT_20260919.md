# CONFIT_A — Complete VTON Gap Closure Report (2026-09-19)

> **SUPERSEDED (2026-09-19, same-day consolidation):** this document is retained as the
> detailed pre-reset artifact. Its statements are superseded where they conflict with
> `VTON_FULL_GAP_CLOSURE_REPORT_20260919.md` (consolidated final: deployment ground truth
> 10d80a12, per-feature local/CI/production layers, PR #119, reset-#10 recovery, Modal
> spend-limit state, Neon auth failure). In particular: §B base SHA e1419d6 → re-landed on
> 10d80a12; §F "workspace disabled" → "spend limit" (21:16 UTC probe); §Q2 "credentials not
> in session" → credentials re-supplied and used one-shot; §V "PR = BLOCKED" → PR #119
> created. Pre-reset local commits 5b7fd80/a785c22 are recorded LOST (content-preserving
> recovery into a58cfa9/9972613). History preserved, not rewritten.

**Date:** 2026-09-19 (Africa/Cairo) · **Scope:** VTON subsystem only (frontend → API → auth →
validation → orchestration → worker → output validation → persistence → response → rendering)
· **Repo:** github.com/OmarAhmed-123/CONFIT_A · **Production:** confit-a.vercel.app
· **Method:** evidence-driven audit → root-cause remediation → negative + regression tests →
production observation. Every statement is tagged CLAIM → EVIDENCE → STATUS. An honest
FAIL/BLOCKED/UNVERIFIED/GAP/NO-GO is the intended outcome; fabricated success is the failure.

---

## A. Scope, method, and rules applied

CLAIM: This audit targeted only VTON parts; unrelated commerce/B2B/payments/analytics/UI/auth
findings are recorded in §T.4 and were not implemented.
EVIDENCE: Findings list below is partitioned VTON vs non-VTON; non-VTON items carry
`OUT-OF-SCOPE (recorded)` status only.
STATUS: **DONE**

CLAIM: Prior Phase 5/6/7 evidence was treated as historical context and re-verified before use;
repo/executable code/tests/runtime are authoritative, narrative is not.
EVIDENCE: v2.4 constants re-read from live code (§H); full regression suites re-run raw this
pass (§Q); production re-probed live (§N); git ground truth re-fetched this pass (§B).
STATUS: **DONE**

CLAIM: No credentials were persisted anywhere by this work; no secrets appear in code, tests,
docs, logs, or fixtures.
EVIDENCE: `test_licenses_and_secrets.py` 6P fresh (§Q); new files written contain no tokens;
git diff of this change scanned (see §R).
STATUS: **VERIFIED**

## B. Git ground truth (re-verified this pass, 2026-09-19 ~16:30 UTC)

CLAIM: A 9th local reset had occurred (local branches lost, tree dirty); the canonical recovery
source is the remote reconciliation branch.
EVIDENCE: `git branch -vv` at turn start = only `main @ 928e615` + 22 dirty entries;
`origin/vton-evidence-reconciliation-2026-09-16 @ 1c0c329` remote-verified; working tree
byte-identical to that remote branch (`git diff --cached --name-only` = 0 after `git add -A`),
then stashed and reconstituted via merge (no destructive reset, no evidence destroyed).
STATUS: **VERIFIED**

CLAIM: `origin/main` advanced 928e615 → **e1419d6** (frontend UX-honesty PRs #110/#111 only;
no backend VTON changes) while the VTON work lived on the reconciliation branch.
EVIDENCE: `git log 928e615..e1419d6` = 8 commits, 13 frontend files, 0 backend files;
`git merge-base e1419d6 1c0c329` = 928e615.
STATUS: **VERIFIED**

CLAIM: Baseline for remediation = focused branch **`feature/vton-complete-gap-closure` @ f7a2fdd**
= merge of actual current `origin/main` (e1419d6) + reconciliation branch (1c0c329). The
reconciliation branch is the VTON work itself (purpose: Phase 5/6/7 evidence reconciliation),
not an unrelated branch; all ~15 pre-existing remote VTON branches were inspected for purpose/
divergence and none was reused (each is either an older subset of, or a documentation-only
variant of, the reconciliation line; `fix/discover-tryon-contrast` is already merged into main
via PR #111).
EVIDENCE: `git log --oneline -3` on the feature branch (f7a2fdd → e1419d6 → ddfa35c…);
merge was conflict-free (frontend-only overlap absent); remote branch list + per-branch
`git log`/`git diff --stat` inspected this pass.
STATUS: **VERIFIED**

## C. Requirements sources & BRD traceability matrix

CLAIM: Requirement sources read in full this pass: Backend Master Spec §3.5 + provider matrix +
§5 Celery + §6 security/privacy; Architecture Master Spec §3.2/§5.1/§6 G3.1–G3.3; Frontend
Master Spec §5.3/§7; Feature Spec G2/G3 (API contracts, events, provider table); VTON_GATE_SPEC_v1
(DRAFT); VTON_PRODUCTION_INTEGRITY_REPORT (historical). No BRD text was rewritten.
EVIDENCE: All files under `docs/` (master specs, feature specs, `docs/specs/VTON_GATE_SPEC_v1.md`).
STATUS: **VERIFIED**

Traceability matrix (BRD requirement → implementation → evidence → status):

| # | BRD requirement (source) | Implementation | Evidence (this pass) | Gap → remediation | Test | Production evidence | Status |
|---|---|---|---|---|---|---|---|
| 1 | `POST /tryon/render` real diffusion VTON, 24h purge, VTON-CERT-* (Backend §3.5) | `execute_tryon`/`execute_multi_garment_tryon`/async jobs → FASHN GPU worker; temporary (non-durable) delivery; VTON-CERT hash | raw renders in evaluation/results (P5 blocked in prod); hash now content-bound (§D.4) | G4 fixed (hash verifiability); purge now enforced on job rows too (§K) | 1344P incl. 18 new | 503 honest (worker down) | **FIXED (local) / PROD: BLOCKED-INFRA** |
| 2 | No-Photo Fit Finder (G3.2) | `no_photo_fit` endpoints + FitFinderView | present; untouched by this audit | — | suite green | not probed (out of VTON-render path) | **VERIFIED-UNCHANGED** |
| 3 | Visual search (G3.3) | visual_search_service + provider | present | — | suite green | not probed | **VERIFIED-UNCHANGED** |
| 4 | Avatar flow: "multi-ethnic 3D avatars" (G3.1) | 4 Unsplash-photo avatars, EXPLICIT selection only | VTON_AVATARS + picker; default removed this pass (G1) | deviation disclosed: photos, not 3D avatars | G1 tests | n/a | **DEVIATION-DISCLOSED** |
| 5 | Side-by-side comparison (G3.1) | before/after split slider in VirtualTryOnModal | modal L340+ | — | frontend 103P | n/a | **VERIFIED** |
| 6 | Certified AI disclosure VTON-CERT-* + 24h notice VISIBLE to user (Frontend §5.3) | fields existed in TS models; **never rendered** | grep: no display site pre-fix | G12 fixed: modal disclosure line (hash + engine + 24h) | tsc + vitest | n/a | **FIXED (local)** |
| 7 | Fallback "high-fidelity canvas compositor" when provider fails (provider matrix) | **Intentionally not implemented** — honest 503/502 failure (project directive 2026-09-05/16: no fake fallbacks) | provider `fallback_multi` raises `TryOnEngineUnavailableError(no_render_backend)` when garments present; production probe returned 503, no image | BRD conflict recorded; requires BRD-side decision (compositor = fake-success risk under project rules) | fallback-honesty tests | 503 no-image | **DEVIATION-DISCLOSED (decision item)** |
| 8 | Celery `vton_heavy` queue + hourly GDPR purge daemon (Backend §5/§6) | Celery app + `purge_expired_sessions_task` exist in repo; **not running in production** (Vercel serverless, no broker/worker host in provided production config) | prod /health shows no worker liveness; guide documents local-only Celery | G3c fixed: read-time retention enforcement works without the daemon; daemon now covers jobs too | G3 tests | **not enforceable yet** | **FIXED (local) / PROD: GAP-INFRA** |
| 9 | GDPR Art. 17: input + composite images auto-erased after 24h (Architecture §3.2) | sessions had retention; **job rows did not** (person photo in `tryon_jobs.input_person_image_url` = indefinite retention) | schema read + live prod row shape (0017 prod lacks even session enforcement in practice) | G3a/b/c fixed: migration 0019, daemon extension, read-time purge | G3 tests (purge, consent, expiry, read-time) | prod DB not readable this pass (creds) | **FIXED (local) / PROD: UNVERIFIED** |
| 10 | RBAC consumer/brand/admin + secret isolation (Backend §6) | optional-auth controller + owner/guest-token fail-closed gates; admin token from env/Modal secret | 404 no-existence-leakage probe (prod); authz tests | — | suite green | 404 probe clean | **VERIFIED** |
| 11 | Engine capability honesty: unsupported category = explicit refusal | `VTON_ENGINE_RENDERABLE_SLOTS` upfront 422; worker single-category enforcement; footwear/accessory refused | code read + worker contract (MAX_GARMENTS=1, category map) | — | suite green | 422 path tested locally | **VERIFIED** |

## D. Architecture & runtime-path audit (frontend → … → rendering)

CLAIM D1: No client-selected privileged option survives in the VTON render path. Layer order is
server-side (`SlotLayeringEngine.LAYER_HIERARCHY`, single source — verified used by both the
chain sort in `_build_garments_payload` and the animated sort via `layer_order`); catalog
metadata (incl. `sleeve_length`) is server-authoritative (AT-13); client reorder affects display
only, never render order.
EVIDENCE: code read this pass (slot_layering_engine L46/64-69; tryon_service `_build_garments_payload`);
AT-13/AT-19 rules in vton_sleeve_gate docstring.
STATUS: **VERIFIED**

CLAIM D2: No silent provider substitution or fake success in the render path. The only "fallback"
is the no-op provider that RAISES when garments are present; every layer must pass
`assert_layer_applied` (verify.PASS is exactly True) or the chain aborts
`VTON_LAYER_NOT_APPLIED`; a mid-chain failure fails the whole job/animation (no partial success).
EVIDENCE: `tryon_provider.fallback_multi`/`_resolve_rendered_image_asset` (raises
`TryOnEngineUnavailableError`); `assert_layer_applied` invoked from `_call_gpu_worker` for every
path; animated per-frame handler re-raises on LAYER_NOT_APPLIED/SLEEVES_NOT_VERIFIED.
STATUS: **VERIFIED**

CLAIM D3: The API layer previously SILENTLY defaulted to a stock person (`avatar_model_id`
defaulted to `avatar_athletic_m` in 5 request schemas + 4 service signatures) and the sessions
endpoint silently defaulted to product 1 (`else [1]`) — contradicting the documented
2026-09-05 explicit-reference directive (service-level docstring said "never substituted"; the
API layer did it anyway). Production mainline still behaves this way (probe §N: no-person
request was accepted into a worker call, not 422'd).
EVIDENCE: pre-fix code; production probe `POST /api/v1/tryon/multi-render {"product_ids":[1]}`
→ 503 worker-not-ready (i.e., it attempted a render) rather than 422.
STATUS: **GAP FOUND → FIXED (G1, G2; tests G1/G2)**

CLAIM D4: `traceability_hash` (VTON-CERT-*) was computed from `job_id + time.time()` — not
tied to the delivered artifact, therefore not verifiable by anyone holding the image (BRD:
"verifiable AI disclosure hash").
EVIDENCE: pre-fix line in `execute_multi_garment_tryon` (replaced this pass).
STATUS: **GAP FOUND → FIXED (G4: content hash of job|model|rendered-bytes; hash-only persisted;
recomputability pinned by test G4)**

CLAIM D5: Stale engine naming: user- and operator-facing strings said "CatVTON" in 6+ places
(error messages, animated disclosure "CONFIT VTON Engine — CatVTON — Identity Preserved — Real
per-layer inference", frontend toasts) while the production engine is `fashn_vton_segfee`
(Apache-2.0, per prod /health `vton_engine`).
EVIDENCE: pre-fix greps; prod /health `vton_engine.engine`.
STATUS: **GAP FOUND → FIXED (all replaced; tests assert absence)**

CLAIM D6: The animated path hardcoded `"Optimal Garment Fit"` / 95 / "Identity Preserved" in the
response AND the session row (created before rendering, never updated after), and the
`AnimationKeyframeOut` response model STRIPPED the service's per-frame `failed`/`error`
markers — a partial sequence reached the client as complete.
EVIDENCE: pre-fix code (session creation + final return); response model read; reproduced in
test G7 (frame 2 forced to fail → pre-fix response shape would have claimed 95/Optimal).
STATUS: **GAP FOUND → FIXED (G7: honest verdict/confidence/verification in response + session
row; keyframe contract extended; tests G7a/G7b)**

CLAIM D7: `ai_disclosure` in the static path defaulted to `'CatVTON'` when the worker omitted
`model_used`; defensive fit-verdict defaults were the false-success string "Optimal Garment Fit".
EVIDENCE: pre-fix lines.
STATUS: **GAP FOUND → FIXED (defaults now 'unknown' / "Fit not verified")**

## E. FASHN integration audit (actual used version/config)

CLAIM: The production worker runs the segmentation-free FASHN fork `fashn-AI/fashn-vton-1.5 @
7c0f10af` with the non-commercial `fashn-human-parser` REMOVED from the runtime; engine
`VTON_ENGINE=fashn_vton_segfee`; single category per call; seed=42, 30 timesteps; A10G GPU;
concurrency 1; weights in Modal volume `confit-vton-fashn-weights`; admin token from Modal
secret `confit-worker-admin-token`. The legacy CatVTON worker (`modal_app.py`) is labeled
LEGACY, unregistered in the engine registry, and not deployed.
EVIDENCE: `services/vton-worker/modal_app_segfee.py` (full read this pass); health contract
includes `git_sha` (deployment correlation) + `parser_present` + `commercial` flags; prod /health
`vton_engine` block matches (Apache-2.0, parser removed, fork 7c0f10af).
STATUS: **VERIFIED**

CLAIM: Unsupported category/composition = honest refusal, never fake generation: footwear/
accessory → explicit 422 upfront (API) and at worker; `garments>1` → 422; white-on-light
garment color → gate REFUSE (blind spot); undecodable/undetermined → REFUSE, never PASS.
EVIDENCE: worker `SLOT_TO_CATEGORY` + validators; `VTON_ENGINE_RENDERABLE_SLOTS` upfront check;
sleeve gate fail-safe branches (all REFUSE, no silent pass) — re-read this pass.
STATUS: **VERIFIED**

## F. Modal worker audit

CLAIM: The worker endpoint is currently UNREACHABLE because the Modal workspace
(`ac-io3nXB7Q2nuaHHl8mVkeLH`) is disabled. Latest direct pings (2026-09-19 12:11, 13:15, 13:56
UTC) returned 404 "workspace is disabled" for both process/health URLs with real payloads.
This pass, production corroborates it live: `POST /api/v1/tryon/multi-render` on
confit-a.vercel.app → **503 `VTON_WORKER_NOT_READY` after 3 attempts: unreachable (34.3 s),
no image returned**.
EVIDENCE: `evaluation/results/p5_dynamic_fresh/results.json` (blocker.rechecked 12:11 UTC);
production probe this pass (§N).
STATUS: **BLOCKED-INFRA** (re-enable/redeploy not attempted: Modal credentials were provided in
a prior session and are not recoverable in the current session context — see §T.2; deterministic
rerun: `python3 evaluation/probes/p6_p5_dynamic_fresh.py` once a token is available)

CLAIM: The worker's own contract is production-hardened: SSRF guard (private/loopback/metadata
blocked incl. DNS-resolution check), 15MB/4096px/decompression-bomb limits, admin-token auth
(never logged), honest error taxonomy (UNAUTHORIZED / VTON_ENGINE_UNAVAILABLE / INPUT_INVALID /
GPU_OOM / INFERENCE_FAILED / OUTPUT_INVALID / VTON_NOT_READY), output validation (no echo,
pixel_change ≥ 1.0, color_shift > 0.005, stddev > 5), license guard aborting if the restricted
parser is importable, git_sha in health.
EVIDENCE: full worker read this pass.
STATUS: **VERIFIED** (code-level; runtime health UNVERIFIED — BLOCKED-INFRA)

## G. N=2 / multi-garment audit

CLAIM: "Complete outfit" renders are SEQUENTIAL single-garment composition (layer i+1 renders on
layer i's output), not native multi-garment inference; layer order is server-derived from
`LAYER_HIERARCHY`; every layer must independently pass engine verify + sleeve gate or the whole
job fails. The uploaded person anchors layer 1; subsequent layers are anchored to the previous
layer's output (by construction of sequential composition — documented, not hidden).
EVIDENCE: `_call_gpu_worker` per-layer chain in both job and sync paths; `assert_layer_applied`
+ `evaluate_layer_sleeves` per layer; `aggregate_layer_verification` (defense-in-depth;
unreachable while the hard gate stands — recorded, not a gap).
STATUS: **VERIFIED** (sequential composition; "N=2 verified" claims must always say
"sequentially composed", and do in the docs)

## H. Sleeve gate audit (v2.4 — active rule re-verified in live code)

CLAIM: Active production rule = **v2.3 AND max(any-skin, both arms) < 0.15** (S5b), i.e.
v2.4, exactly as frozen on 2026-09-19. Constants in live code this pass: S1 PASS 0.35 /
FAIL 0.15 (L241/242), S5 new-skin 0.10 (L283), S5b any-skin **0.15 (L372)**, S6 wrist-reach
0.05 (L299); max-arm aggregation; channels run only on the coverage-PASS path (monotone-safe);
[0.15, 0.35) = NOT VERIFIED → REFUSE; undeclared `sleeve_length` on upper slots → REFUSE
(AT-19); probe error → REFUSE.
EVIDENCE: `backend/app/services/vton_sleeve_gate.py` full re-read (line-anchored);
`test_sleeve_gate_regression.py` 42P/1S fresh this pass; v2.4 frozen spec
`docs/vton/SLEEVE_GATE_V24_FROZEN_SPEC_2026-09-19.md`.
STATUS: **VERIFIED (frozen, unchanged)**

CLAIM: Coverage of defect classes: coverage-drop (S1), class-E torso-carry (S5), asymmetric /
old-skin drops (S5b — the v2.4 channel), partial-drop-over-garment (S6); wrist-reach + skin
window calibrated on the 50+7 artifact matrix; documented residual classes (dark-on-dark
margins, white blind spot, thin-margin blazer class, short-sleeve drop out of scope) are
recorded, and all residuals fail SAFE (over-refusal), never silent pass.
EVIDENCE: module docstring measurement tables; `evaluation/results/sleeve_signal_matrix.json`,
`p6_sleeve_v24.json`, Phase-6/7 reports; adversarial composites all REFUSED (P1-B).
STATUS: **VERIFIED** (measurement-level for the tested defect family; not a statistical
guarantee — as documented)

CLAIM: False positives AND false refusals are disclosed, not hidden: over-refusal measured on
the 56-case confusion matrix (FN20 healthy over-refused at τ=0.15 historical; thin-margin
blazer class REFUSEs visually-correct renders); FP=0 on measured defect artifacts.
EVIDENCE: `p7_v24_confusion_matrix.json`; v2.4 flip table in frozen spec; audit report Part 5.
STATUS: **VERIFIED (disclosed)**

CLAIM (gap): the decision dict's reported `thresholds` metadata omitted the v2.4 any-skin
constant, so job metrics under-reported the active rule.
EVIDENCE: pre-fix `evaluate_sleeves_sync` thresholds dict.
STATUS: **GAP FOUND → FIXED (G8; test asserts all five thresholds incl. 0.15)**

## I. Generic application-verifier audit

CLAIM: Application verification is generic (no fixture/person/garment IDs in production code):
worker verify (pixel_change/color_shift/stddev) + `assert_layer_applied` (PASS is exactly True,
applied to EVERY path from `_call_gpu_worker`) + sleeve gate (pure-PIL generic probe).
No one-off hacks found this pass. The 0.5 pixel-change line in `_call_gpu_worker` is a log
warning only (the canonical gates are the worker's ≥1.0 PASS and the sleeve gate).
EVIDENCE: full service read; grep for hardcoded IDs in gate/verify code (none); test sweep.
STATUS: **VERIFIED**

## J. DRY audit

CLAIM: Single authoritative sources confirmed: layer hierarchy = `SlotLayeringEngine.
LAYER_HIERARCHY` (used by both render orderings); status taxonomy = one VTON_* code family
mapped in one place per endpoint; gate config = module constants in vton_sleeve_gate.py (one
file, now fully exposed in decision metadata); provider/model config = env/settings
(`VTON_WORKER_*`) + engine registry; verification contract = worker `verify` dict +
`assert_layer_applied`. No duplicated thresholds across the VTON path.
EVIDENCE: code reads this pass; grep of threshold literals (0.35/0.15/0.10/0.05/20.0 only in
the gate module; 1.0/0.005/5.0 only in the worker).
STATUS: **VERIFIED** (one noted, accepted duplication: the sleeve gate re-implements a
SSRF-protected garment fetch identical in behavior to the service's — documented in its
docstring as "exactly as the worker sees it"; low risk, left as-is to avoid speculative
refactor)

## K. Security audit (with negative tests)

CLAIM K1 (authz/IDOR): job/session endpoints fail closed — unknown → 404, other user's → 404
(no existence leakage), guest bound to one-time 192-bit delivery token (hash persisted;
plaintext only in the completion response; destroyed on first use/TTL/revocation).
EVIDENCE: `get_vton_job_status`/`deliver_job_result`/`revoke_job_result` read; prod probe
`GET /api/v1/tryon/jobs/vton_job_deadbeef0000` → clean 404 (this pass); authz tests in suite.
STATUS: **VERIFIED**

CLAIM K2 (SSRF): worker + service both guard URL-fetched images (private/loopback/link-local/
metadata blocked, DNS-resolution checked). **GAP found:** the service's `_fetch_image_as_base64`
FAILED OPEN when the security module import raised ("ssrf_check_failed_allowing").
EVIDENCE: pre-fix except-branch; negative test G5 (import forced to fail → URL now blocked).
STATUS: **GAP FOUND → FIXED (G5: fail-closed; test G5)**

CLAIM K3 (decompression bombs / input limits): 15MB, 32–4096px, w*h cap, `img.verify()`,
person-specific checks (≥256px short side, aspect ≤ 4, ≥10KB) BEFORE any GPU call.
EVIDENCE: worker `_validate_and_decode_image`; service `check_person_bytes`; negative tests.
STATUS: **VERIFIED**

CLAIM K4 (secret leakage): worker admin token never logged (only `has_admin_token=bool`);
**GAP found:** image URLs were logged/stored with their query strings intact — signed URLs
carry credentials in the query.
EVIDENCE: pre-fix `url[:100]` log fields; `_log_safe_url` now strips query/fragment and fully
redacts data URLs (no image bytes in logs/errors); test G6.
STATUS: **GAP FOUND → FIXED (G6; test G6)**

CLAIM K5 (replay/idempotency, races): delivery is one-shot claim (entry deleted on claim);
cancel/revocation purge staged copies; no double-serve of the token (status endpoint never
re-serves it).
EVIDENCE: `vton_delivery.py` store semantics read; delivery tests in suite.
STATUS: **VERIFIED** (serverless caveat: process-local staging is best-effort across instances
— documented in the delivery contract; in-response data URL is the guaranteed carrier)

## L. Privacy & image lifecycle (end-to-end)

CLAIM L1: Generated try-on images are NEVER durably stored (in-response data URL + one-shot
15-min TTL process-local staging + token hash/expiry only in DB) — product requirement met by
design and enforced in code.
EVIDENCE: `vton_delivery` contract; `TryOnJob.output_image_url` left NULL; session rows store
non-generated refs only (`_is_generated_data_url` gate).
STATUS: **VERIFIED (local)**

CLAIM L2: **GAP (root cause of indefinite person-photo retention):** user-uploaded person
photos (data URLs) ARE persisted on `tryon_jobs.input_person_image_url` and
`tryon_sessions.input_user_image_url`; sessions had 24h/consent retention, but **job rows had
no retention columns at all**, and the purge daemon only covered sessions — so job-row photos
would be retained indefinitely (BRD: 24h, GDPR Art. 17). Additionally, the purge daemon runs on
Celery beat, which is **not running in production** (Vercel serverless; the production guide
documents Celery as local-only; no broker in the provided production config).
EVIDENCE: pre-fix `TryOnJob` schema (no expires_at/consent); pre-fix `purge_expired_sessions_task`
(sessions only); production /health + production run guide reads.
STATUS: **GAP FOUND → FIXED in code (G3a: migration 0019 adds job retention + back-fill;
G3b: daemon purges jobs; G3c: opportunistic read-time purge enforces retention on any
deployment topology); PROD ENFORCEMENT = BLOCKED-INFRA until 0019 migrates + (optionally) a
cron is configured**

CLAIM L3: If production storage is non-production-grade where the BRD requires it, that is a
GAP, not something to hide. Production /health itself reports
`storage: {provider: local, production_grade: false, writable: false}` (wardrobe/storage
service — non-VTON, recorded in §T.4). For VTON specifically, durable storage is NOT used by
design; the privacy-critical persistence is the person-photo data URLs, now under retention.
EVIDENCE: prod /health response (this pass); `vton_delivery` design.
STATUS: **GAP (storage service) = OUT-OF-SCOPE recorded; VTON retention = FIXED (local) /
PROD UNVERIFIED**

## M. Identity preservation

CLAIM: Identity preservation is NOT a production-verified property. The only identity metric
ever measured (AdaFace/WebFace600K) is evaluation-only (LICENSE-GATED, no commercial rights);
no identity gate is active in the production path; the BRD's "multi-ethnic 3D avatars" are
Unsplash stock photos (disclosed, §C row 4). All user-facing "Identity Preserved" claims were
removed this pass (animated disclosure, rendering overlay "identity-preserving compositing").
EVIDENCE: GATE SPEC G3 (LICENSE-GATED section); pre-fix strings removed; license suite 6P.
STATUS: **IDENTITY = LICENSE-GATED** (unchanged; no popularity/wrapper-license reasoning used)

## N. Frontend UX audit

CLAIM N1: No success wording without verified application: the modal shows "engine
verification pending…" while rendering, labels the fit badge explicitly as "catalog heuristic —
not a drape fit", hides it when nothing is applied, and success state requires
`status === 'completed' && rendered_result_url` from the verified render path (which hard-aborts
on any unverified layer).
EVIDENCE: VirtualTryOnModal + useTryOnViewModel reads; service hard gates.
STATUS: **VERIFIED**

CLAIM N2: Failure UX is the single canonical VTON_* taxonomy; **GAP found:** the new canonical
verifier-refusal code `VTON_SLEEVES_NOT_VERIFIED` had NO dedicated user-facing message (raw
error string fell through), and the catch (HTTP-error) branch showed no per-code toasts at all.
EVIDENCE: pre-fix viewmodel branches (engine/worker/auth/layer only).
STATUS: **GAP FOUND → FIXED (G10: dedicated sleeve-refusal messages for multi-render AND
animated paths; user-facing wording distinguishes engine-unavailable vs worker-not-ready vs
verifier-refused)**

CLAIM N3: **GAP found:** the BRD-mandated VTON-CERT disclosure + 24h retention notice was in the
API contract and TS models but never rendered in the UI.
EVIDENCE: pre-fix grep (fields unused in any component).
STATUS: **GAP FOUND → FIXED (G12: disclosure line — engine + cert hash + "photo auto-purged
after 24h" — in the result area)**

CLAIM N4: Stale user-facing "CatVTON" strings (3 toasts/info lines) mislabeled the engine.
EVIDENCE: pre-fix viewmodel; prod /health engine name.
STATUS: **GAP FOUND → FIXED (G9)**

CLAIM N5: Accessibility/responsive basics: dialog role/aria-modal/aria-label/tabIndex, alt text
on all result imagery, disabled states, split-slider is a native range input (keyboard-
operable), responsive breakpoints throughout the modal.
EVIDENCE: modal read (L199-690).
STATUS: **VERIFIED** (residual: no focus-trap cycle for the modal — recorded as minor, not
fixed this pass to avoid speculative scope creep)

## O. Observability

CLAIM: Structured logging distinguishes engine-failed (INFERENCE_FAILED / GPU_OOM /
VTON_LAYER_NOT_APPLIED), verifier-refused (VTON_SLEEVES_NOT_VERIFIED with per-arm coverage +
anatomy metrics + reason), and worker-unavailable (VTON_WORKER_NOT_READY /
VTON_WORKER_UNAVAILABLE / VTON_TIMEOUT); job rows persist error_code + honest error_message +
per-layer verification metrics; sensitive data excluded (token never logged; URLs now
query-stripped; data URLs redacted — G6).
EVIDENCE: service logging read; G6 fix + test.
STATUS: **VERIFIED**

## P. Test pyramid & regression safety (raw results, this pass)

| Suite | Raw result (this pass) | Baseline (reconciled branch) | Delta |
|---|---|---|---|
| backend + evaluation full | **1344 passed, 29 skipped, 0 failed** (234.53 s) | 1326P/29S/0F | +18 = the new gap-closure tests |
| `test_vton_gap_closure_20260919.py` (NEW) | **18 passed** | — | G1×4, G2, G3×4, G4×2, G5, G6, G7×2, G8 |
| `test_sleeve_gate_regression.py` | **42 passed, 1 skipped** | 42P/1S | 0 |
| `test_sleeve_v23_matrix.py` | **52 passed** | 52P | 0 |
| `test_licenses_and_secrets.py` | **6 passed** | 6P | 0 |
| migration chain (0019 round-trip) | **12 passed** (incl. up→base→up) | head was 0018 | head moved consciously 0018→0019 (documented in test) |
| frontend `tsc --noEmit` | **0 errors** | — | typecheck clean |
| frontend vitest (full) | **103 passed (19 files)** | — | includes 5 tryon viewmodel tests |

Negative tests per boundary: unsafe URL blocked when guard fails (G5); no-person request →
422 with 0 GPU calls (G1); empty session request → 422 (G2); expired+unconsented purged,
consented + future kept (G3); content-different hash differs (G4); query creds never logged
(G6); forced frame failure → honest partial (G7).
STATUS: **VERIFIED**

## Q. Production verification (what was run / what is blocked)

CLAIM Q1 (executed, public, no credentials): production site UP (200, 0.09 s);
`GET /api/v1/health` → healthy; **deployment schema = 0017** (i.e., production runs mainline
code — the reconciliation VTON work incl. 0018/sleeve-gate is NOT deployed); `vton_pipeline`
configured (worker URL + token present); `vton_engine` = fashn_vton_segfee, Apache-2.0,
commercial, parser removed; `storage.production_grade = false` (self-reported, non-VTON
service). `GET /api/v1/tryon/jobs/<random>` → clean 404 (no existence leakage).
`POST /api/v1/tryon/multi-render {"product_ids":[1]}` → **503 VTON_WORKER_NOT_READY after 3
attempts (34.3 s), no image** — honest failure confirmed in production; note it also proves
production mainline still silently accepts no-person requests (the G1 fix is not deployed).
EVIDENCE: curl outputs this pass (timestamps in session log).
STATUS: **PROBES EXECUTED (public surface only)**

CLAIM Q2 (blocked): `PRODUCTION VERIFIED` is NOT claimed for any VTON behavior requiring
authenticated/internal access. Deployment-SHA correlation (Vercel API), production DB state
(Neon), and Modal worker health/re-enable all require credentials that were provided in a
prior session and are **not recoverable in the current session context** (no .env, no env vars,
no persisted copies — by the no-persist rule). They are recorded with exact rerun commands
(§T.2). A local test, code inspection, or this report's statements never count as production
evidence.
STATUS: **BLOCKED (credentials not in session)** — no simulated production evidence used.

CLAIM Q3: No browser runtime available → browser-level checks are
`BLOCKED — NO BROWSER RUNTIME`; none were simulated.
STATUS: **BLOCKED**

## R. Claim audit / no-fake sweep

CLAIM: No banned claims in this change: no "production verified", no "identity preserved", no
fake worker/model/deployment/PR/CI claims; no fixture filled runtime; no threshold moved for
pass rate (v2.4 constants byte-identical to frozen spec, line-anchored in §H); no fake
recovery; no documentation-as-execution-evidence (every PASS above is a raw run this pass).
EVIDENCE: diff of the change scanned for banned phrases; threshold line-anchors; raw suite
outputs.
STATUS: **VERIFIED**

## S. Final readiness matrix, gap register, and release decision

Readiness (≥19 areas; exactly one status each):

| # | Area | Status |
|---|---|---|
| 1 | BRD traceability complete | VERIFIED |
| 2 | Explicit person-reference contract (API+service) | FIXED-VERIFIED (local) |
| 3 | No silent default product | FIXED-VERIFIED (local) |
| 4 | FASHN engine integration (single-category, honest refusal) | VERIFIED |
| 5 | Worker hardening (SSRF/auth/limits/taxonomy/license-guard) | VERIFIED (code) |
| 6 | Worker runtime health (Modal) | **BLOCKED-INFRA** (workspace disabled; creds out of session) |
| 7 | N=2 sequential composition honesty | VERIFIED |
| 8 | Sleeve gate v2.4 active + frozen + thresholds fully reported | FIXED-VERIFIED (S5b metadata) |
| 9 | Application verifier generic, all paths | VERIFIED |
| 10 | DRY (hierarchy/taxonomy/gate/provider/verification) | VERIFIED |
| 11 | Security: authz/IDOR fail-closed, no leakage | VERIFIED |
| 12 | Security: SSRF fail-closed | FIXED-VERIFIED |
| 13 | Privacy: generated images never durable | VERIFIED (local) |
| 14 | Privacy: person-photo retention (jobs+sessions, daemon+read-time) | FIXED-VERIFIED (local) / PROD **UNVERIFIED** |
| 15 | Identity preservation | **LICENSE-GATED** |
| 16 | Frontend UX honesty (no unverified success) | VERIFIED |
| 17 | Frontend: BRD disclosure + 24h notice visible | FIXED (local) |
| 18 | Failure-UX canonical taxonomy (engine/verifier/worker) | FIXED-VERIFIED (sleeve message) |
| 19 | Observability without sensitive data | FIXED-VERIFIED (URL redaction) |
| 20 | Test pyramid + regression (1344P; 42P/1S; 52P; 6P; FE 103P; tsc clean) | VERIFIED |
| 21 | Production deployment of hardened VTON (0018+0019+branch) | **NOT DEPLOYED** (no deployment performed/claimed) |
| 22 | Production SHA correlation + DB read + worker re-enable | **BLOCKED (credentials out of session)** |
| 23 | Human calibration (≥3 real raters) | **BLOCKED (calibration)** — package prepared, zero labels |
| 24 | Browser-level production UX check | **BLOCKED — NO BROWSER RUNTIME** |

Gap register (exact deficiency → state; no "needs improvement"):

| ID | Deficiency (exact) | State |
|---|---|---|
| G1 | `avatar_model_id` defaulted to `avatar_athletic_m` in 5 schemas + 4 service signatures; no-person API requests silently rendered a stock person (also still true in deployed mainline) | FIXED (None default; 422 otherwise) + tests |
| G2 | `POST /try-on/sessions` defaulted `product_ids` to `[1]` for empty requests | FIXED (explicit 422) + test |
| G3a | `tryon_jobs` had no `expires_at`/`consent_retained`; uploaded person photos on job rows retained indefinitely | FIXED (migration 0019 + back-fill + creation wiring) + tests |
| G3b | `purge_expired_sessions_task` purged sessions only, never job rows | FIXED (jobs purged; `purged_job_count`) + test |
| G3c | No retention enforcement in serverless production (Celery beat not running; no broker) | FIXED in code (read-time opportunistic purge); prod enforcement still needs 0019 deploy → PROD: GAP-INFRA |
| G4 | `VTON-CERT-*` = sha256(job_id+timestamp): not tied to the delivered artifact, not verifiable | FIXED (content hash; hash-only persisted) + verifiability test |
| G5 | `_fetch_image_as_base64` SSRF guard failed OPEN on guard import failure | FIXED (fail-closed) + negative test |
| G6 | Image URLs logged/stored with query strings (signed credentials in logs/errors) | FIXED (`_log_safe_url`: query stripped; data URLs redacted) + test |
| G7a | Animated response/session row hardcoded "Optimal Garment Fit"/95/"Identity Preserved"/"CatVTON" and survived frame failures | FIXED (derived from keyframe verification; session row updated) + tests |
| G7b | `AnimationKeyframeOut` stripped per-frame `failed`/`error`/`model_used`/`execution_time_ms` | FIXED (contract extended) + test |
| G8 | Sleeve-gate decision metadata omitted the v2.4 any-skin threshold (0.15) | FIXED (exposed) + test |
| G9 | User-facing toasts/info named the engine "CatVTON" (3 sites) | FIXED (fashn_vton_segfee) |
| G10 | `VTON_SLEEVES_NOT_VERIFIED` (verifier refusal) had no dedicated user-facing message; catch branch had no per-code toasts | FIXED (dedicated messages, multi + animated) |
| G11 | Rendering overlay claimed "identity-preserving compositing" (not a production-verified property) | FIXED (honest wording) |
| G12 | BRD G3.1 VTON-CERT disclosure + 24h retention notice never rendered in the UI | FIXED (modal disclosure line) |
| B1 | Modal workspace disabled → VTON renders impossible in production (P5) | **BLOCKED-INFRA** (creds out of session; rerun command in §T.2) |
| B2 | Production runs mainline 0017: all Phase 5/6/7 hardening + G1-G12 undeployed | **NOT DEPLOYED** (deployment not performed; nothing claimed) |
| B3 | Vercel deployment-SHA correlation, Neon DB read, Modal re-enable | **BLOCKED** (credentials not in current session context) |
| B4 | Human calibration: 3+ real raters; identity licensing | **BLOCKED (calibration) / LICENSE-GATED** |
| D1 | BRD fallback "canvas compositor" intentionally not implemented (honest-failure directive) — BRD text not rewritten | **DEVIATION-DISCLOSED** (decision item for BRD owner) |
| D2 | Avatars = Unsplash photos, not BRD "3D avatars" | **DEVIATION-DISCLOSED** |
| D3 | Modal readiness URL not derivable from process URL (hash-truncated label) — explicit config exists (`VTON_WORKER_READINESS_URL`) | VERIFIED (documented design, config present) |

**RELEASE = BLOCKED**

Barrier table (exactly one release state; all four barriers must clear first):
1. Modal workspace re-enabled + worker health PRODUCTION-VERIFIED (needs Modal credentials in
   session; rerun: `python3 evaluation/probes/p6_p5_dynamic_fresh.py`);
2. Hardened branch deployed to production + alembic 0018→0019 applied + deployment-SHA
   correlation (needs Vercel credentials in session; deployment must be a deliberate act, never
   claimed from a local commit);
3. ≥3 real human raters complete the prepared calibration package;
4. Identity licensing resolved (or the product explicitly disclaims identity preservation
   everywhere — partially done by G7a/G11 removals; BRD alignment decision needed).

## T. Out-of-scope findings (recorded, not implemented)

1. Production `/health` self-reports the storage service as `production_grade: false`
   (wardrobe/campaign storage — non-VTON).
2. Credential-dependent rerun commands (exact): Vercel: `curl -H "Authorization: Bearer <VERCEL_TOKEN>" https://api.vercel.com/v6/projects/<PROJECT>/deployments` (correlate SHA);
   Neon: `psql "$NEON_DATABASE_URL" -c "select version_num from alembic_version; select count(*) from tryon_jobs;" -c "select count(*) from tryon_sessions where consent_retained is false and expires_at < now();"` (read-only);
   Modal: `modal token`-style workspace re-enable per Modal dashboard/API with the provided ak-/as- pair, then `python3 evaluation/probes/p6_p5_dynamic_fresh.py`.
3. Celery `vton_heavy` queue (BRD) is not the production transport (serverless request-scoped
   rendering via direct worker HTTP) — architecture deviation, disclosed, not re-architected.
4. Modal readiness hash-label quirk — documented design with explicit config escape (not a defect).

## U. 20-question final truthfulness audit

1. Did I verify every claim against raw evidence re-run or re-read THIS pass? **Yes.**
2. Is every "VERIFIED" backed by an executable artifact (test run, probe output, file read) from this pass? **Yes.**
3. Is VTON production-verified end-to-end with deployment-SHA correlation? **No — BLOCKED (credentials out of session); not claimed.**
4. Is the Modal worker healthy/available in production? **No — workspace disabled; BLOCKED-INFRA; no health claim made either direction beyond the captured 404s/503.**
5. Did I deploy anything? **No. Nothing is claimed as deployed.**
6. Did I move any threshold to make a pass rate look better? **No — v2.4 constants byte-identical to the frozen spec (line-anchored).**
7. Did I use fixtures as production/runtime evidence? **No — fixtures are test inputs only; runtime evidence = raw suite runs + public prod probes.**
8. Did I simulate a browser or production environment? **No — BLOCKED — NO BROWSER RUNTIME; public prod probed for real.**
9. Is any "success" wording shown to users without verified application? **No — audited and fixed (G7a/G11/G12); hard gate aborts unverified renders.**
10. Is the traceability hash verifiable from the delivered artifact? **Yes (post-fix, G4 + test); pre-fix state disclosed.**
11. Are person photos retained longer than the BRD's 24h in the fixed code? **No — jobs now carry retention; daemon + read-time enforcement; prod enforcement pending deploy.**
12. Does any user-facing text still claim identity preservation? **No (removed); identity status remains LICENSE-GATED and is not claimed as a feature.**
13. Did I rewrite any BRD text to match the implementation? **No — deviations disclosed as DEVIATION-DISCLOSED (D1, D2).**
14. Are false positives AND false refusals of the sleeve gate disclosed? **Yes — both, with measurements (over-refusal CN + thin-margin class).**
15. Are all 10 Phase-7 defect classes refused by v2.4? **Yes per the frozen-spec flip table (re-verified 42P/1S this pass); stated as measurement-level for the tested family.**
16. Is the N=2 result native multi-garment inference? **No — sequential single-garment composition; stated exactly as such.**
17. Were any secrets persisted in code/docs/logs/fixtures? **No — license/secrets suite 6P; diff scanned; credentials used only when in-session (none were, this pass).**
18. Was git history destroyed, force-pushed, or reset? **No — merge-based branch creation from verified remote refs; no destructive operations.**
19. Is there exactly one release state, and is it truthful? **Yes — RELEASE = BLOCKED, barrier table above.**
20. Is the mixed result (fixed / verified / blocked / license-gated) reported without hiding the blocked parts? **Yes.**

Any "no" above ⇒ full closure is NOT claimed. (Q3/Q4/Q16 are honest "no/No" by nature; none
was papered over.)

## V. Final executor summary (mandate §33)

- **Branch / commit:** `feature/vton-complete-gap-closure` (from actual current `origin/main`
  e1419d6 + reconciliation merge 1c0c329; remediation committed on top — see commit log).
- **Base SHA:** e1419d6 (origin/main at work start) + 1c0c329 (reconciliation, VTON work).
- **Files changed:** `backend/app/services/tryon_service.py`, `vton_sleeve_gate.py`,
  `schemas/tryon.py`, `controllers/tryon_controller.py`, `models/tryon.py`,
  `workers/tasks.py`, `alembic/versions/0019_vton_job_retention.py` (new),
  `tests/test_vton_gap_closure_20260919.py` (new, 18 tests),
  `tests/test_flow_e_purchase_to_wardrobe.py` (conscious head-move 0018→0019),
  `frontend/src/viewmodels/useTryOnViewModel.ts`,
  `frontend/src/components/tryon/VirtualTryOnModal.tsx`, this report.
- **Gaps found:** 14 code gaps (G1–G12) + 4 blocking states (B1–B4) + 3 disclosed deviations (D1–D3).
- **Gaps fixed (genuine, root-cause, test-pinned):** all 14 code gaps.
- **Gaps blocked:** B1 (Modal workspace; creds out of session), B2 (deployment not performed),
  B3 (Vercel/Neon/Modal credential-gated checks), B4 (human calibration / identity licensing).
- **Exact tests + results:** backend+evaluation **1344P/29S/0F** (234.53 s; baseline 1326 + 18
  new); sleeve regression **42P/1S**; sleeve v2.3 matrix **52P**; licenses+secrets **6P**;
  migration chain **12P** (0019 round-trip); frontend **tsc 0 errors, vitest 103P/19 files**.
- **Production checks run:** site 200; /health (schema 0017, engine fashn_vton_segfee,
  pipeline configured, storage non-production-grade self-report); job 404 no-leakage;
  multi-render → honest 503 VTON_WORKER_NOT_READY (34.3 s, no image). **Blocked:** SHA
  correlation, DB read, worker re-enable (credentials out of session — exact rerun commands in
  §T.2).
- **Security findings:** SSRF fail-open → fixed; signed-credential URL logging → fixed;
  authz/IDOR/delivery-token verified fail-closed; no secrets persisted.
- **Privacy findings:** indefinite job-row person-photo retention → fixed (0019 + daemon +
  read-time purge); prod enforcement pending deployment; storage-service non-production-grade
  = OUT-OF-SCOPE recorded.
- **Licensing findings:** FASHN fork Apache-2.0 (parser removed, guard runtime-enforced);
  CatVTON legacy path unregistered; identity = LICENSE-GATED.
- **BRD result:** 11-row traceability matrix (§C): 6 VERIFIED / 3 FIXED-local / 2
  DEVIATION-DISCLOSED (decision items). BRD not rewritten.
- **DRY result:** single sources confirmed for hierarchy/taxonomy/gate/provider/verification;
  one accepted, documented duplication noted (§J).
- **Final VTON status (local, this branch):** honest, verified, gated; sleeve v2.4 frozen and
  active; explicit-reference contract enforced; retention lifecycle closed in code.
- **Final VTON status (production):** mainline 0017; worker DOWN (BLOCKED-INFRA); hardened code
  NOT deployed.
- **Release state (exactly one):** **RELEASE = BLOCKED** (barrier table §S).
- **PR / CI / deployment:** PR = **BLOCKED** (GitHub PAT not in current session context —
  re-provide to push `feature/vton-complete-gap-closure` and open the PR); no CI run claimed
  beyond the local suites above; **no deployment performed or claimed**.
