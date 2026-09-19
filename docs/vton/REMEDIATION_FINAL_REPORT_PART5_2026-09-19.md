# CONFIT_A — Phase 5 Authoritative Report (Part 5)

**Date:** 2026-09-19 · **Author:** CONFIT_A VTON engineering (agent-executed, all claims evidence-traced)
**Scope:** Phase-5 remediation + discovery + integration decision (34-section master prompt, 2026-09-19): sleeve false-pass (FP) fix (P0), N=2 controlled experiments (P1), exhaustive MCP Market try-on audit (P2), plus status of human calibration, identity licensing, security, and the single release state.
**Predecessors (preserved, not rewritten):** `REMEDIATION_FINAL_REPORT_2026-09-16.md`, `REMEDIATION_FINAL_REPORT_PART4.md`, `DYNAMIC_PHASE_FINAL_REPORT.md`, `ARCHITECTURE_TEST_REPORT.md`, `LOCAL_DYNAMIC_VALIDATION_REPORT.md`, `GLOBAL_DYNAMIC_VALIDATION_REPORT.md`, `MCP_MARKET_TRYON_AUDIT_2026-09-19.md` (this phase, companion document).
**Status vocabulary:** VERIFIED · MEASURED · TESTED · IMPLEMENTED · CONDITIONALLY VERIFIED · PARTIAL · NOT VERIFIED · BLOCKED · UNRESOLVED · UNSUPPORTED · LICENSE-GATED · NO-GO.
**Claim standard:** `CLAIM → EVIDENCE → STATUS`. Banned without explicit evidence: best / strongest / world-class / production-ready / solved / reliable / robust.

---

## A. Branch and worker state (exact)

| Item | Value | Evidence |
|---|---|---|
| Branch | `vton-evidence-reconciliation-2026-09-16` (focused; `main` untouched) | `git branch`, `git log` |
| Phase-5 sleeve commit | `c5d6207` (this phase; on top of `aa0649d`) | `git log --oneline` |
| Worker service | `vton-worker-segfee`, engine `fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)`, device NVIDIA A10, worker `git_sha 928e615110640c00df0db80ef1a93f92ff353870-dirty`, `ready: true` | live health endpoint, 2026-09-19 (this phase) |
| Push / PR / deployment | **NONE** — no GitHub PAT available; no remote evidence exists; nothing pushed, no PR opened, no deployment made | `git remote -v` + credentials inventory (retained from Phase 4) |

## B. P0 — Sleeve false-pass: status, repro, cause, fix, regression

### B.1 Status (one line)
**The sleeve defect render is now rejected (MEASURED, regression-tested, live-verified); the class-E composition is not "fixed" in the engine — the engine drop is stochastic and the gate now guarantees the defective render is never delivered as an ordinary successful long-sleeve result.**

### B.2 The defect (repro + cause, preserved from 2026-09-16, re-confirmed)
- **Repro:** person J + `garment_arabic_tee_2` (declared long-sleeve) on the 2026-09-16 worker instance rendered **sleeveless** (bare forearms in place of sleeves) while garment-color coverage measured **0.7062 → PASS** (artifact: `evaluation/results/p4_fresh_batch/p4_j_arabic2_L1.png`, agent visual inspection: `AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH`).
- **Cause (structural, MEASURED):** the old gate measured only "fraction of arm-band pixels that match the garment". A missing sleeve and a present sleeve are **both** non-garment-or-garment pixels by that single metric — coverage cannot distinguish "sleeve present" from "sleeve replaced by forearm". The drop replaced fabric with skin; skin is not garment color, yet coverage still passed because the garment's body/torso area dominates. Band geometry ≠ anatomical forearm.
- **Why not a threshold move:** 0.7062 is far above any coverage threshold; no threshold on that channel rejects the defect without mass false-refusal of genuine renders (documented in Part 4). The fix adds channels, not a tuned number.

### B.3 The fix (IMPLEMENTED, commit `c5d6207`, `backend/app/services/vton_sleeve_gate.py`)
For declared **long-sleeve** upper/dress slots, PASS now requires, on the best arm:

| Channel | Definition (generic; no product/person/fixture IDs; no filename matching) | τ |
|---|---|---|
| S1 coverage | changed-garment coverage in the forearm band (ΔE radius 40.0 vs garment ref, PIL Lab) | ≥ 0.35 |
| S5 new-skin | fraction of **new** non-garment **skin** pixels in the outer-65% band (ΔE > 40 from the *input* image → skin present where it wasn't before) | < 0.10 |
| S6 wrist-reach | bottom-35% × outer-65% fraction that is CHANGED vs input **AND NOT skin** (fabric reaches the wrist; v2 definition — the v1 garment-radius version is dead for patterned/checkered garments, Part 4) | ≥ 0.05 |

All three AND-ed. N/A for short/none sleeves (unchanged). Error code unchanged: `VTON_SLEEVES_NOT_VERIFIED` (existing taxonomy; no new code invented — P1-B satisfied: `VTON_SLEEVES_NOT_VERIFIED` already existed and its semantics were widened, not a new code).

**Skin window (calibrated, measured provenance in code):** L* 25–85 / a* 7–25 / b* 7–31. The a* ≤ 25 cap is the discriminating axis: 1.38× above the warmest measured forearm (18.1) and 1.17× below the nearest catalog garment family (dark-rust 29.3; rendered rust 41.7–43.2; burgundy 35.0; brick 55.9). Cohort skin tones (fair 8.0 a* → deepest 14.7 a*, b* ≤ 28.9) and class-E forearms (a* 9.6–18.1, b* 12.7–21.7) sit inside; all 12 measured catalog garment colors sit outside. **Documented structural limit (accepted, safe direction):** the warmest tail of person J's *hand* (a* → 33.9, b* 7.6–16.6) is 1.1 a* from catalog burgundy (a* 35.0, b* 7.7, same b*) — no axis-aligned 2D Lab window separates hand-tail from burgundy; the hand is therefore not counted (hand ≠ forearm target; conservative).

### B.4 Calibration and robustness (P0-C: ≥10 new artifacts — 11 delivered, agent-labeled)
- **8 live synthetic drops** (fresh engine generations, `p0c_sleeve_calibration/`): partial-drop, full-drop ×2 (krust/jtunic), gray, white LS, patterned LS, short-sleeve negative — all inspected: `AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH`.
- **3 synthetic adversarial negatives** (TP replays + boundary cases) + class-E + AT-15 + p0c live = **50-row regression matrix** (`evaluation/results/sleeve_signal_matrix.json`).
- **Result (production `evaluate_sleeves_sync`, final window): 50 rows → 21 PASS / 29 REFUSE / 0 failures.** Every known drop (class-E + all synthetic drops + AT-15 R rows) is rejected on ≥1 channel.

### B.5 Hard safety property (P0-D) — VERIFIED
Property: *"A visibly incomplete long-sleeve render must never be delivered as an ordinary successful long-sleeve result."*
- **Defective class-E render → REFUSE:** MEASURED new-skin **0.3043** (3.0× τ 0.10); regression-pinned (`test_sleeve_gate_regression.py` + `test_sleeve_v23_matrix.py`).
- **Independent equivalents → REFUSE:** all 8 live synthetic drops + 3 synthetics rejected (new-skin 0.12–0.40 and/or wrist-reach 0.0000).
- **No over-refusal of good renders:** 21/21 genuine long-sleeve renders PASS (margin table below).
- **Live end-to-end (2026-09-19):** the class-E composition re-run through the current production chain produced, this time, a **correctly sleeved** render (both sleeves to the wrist — agent visual verification of `p0d_live_class_e/p0d_j_arabic2_final`) which the gate **correctly PASSED** (new-skin 0.0/0.0, left wrist-reach 0.4969). This demonstrates: (a) the drop is **stochastic** (same composition, different worker draw — consistent with Phase-4 worker non-determinism, fresh seed per job); (b) the gate neither blocks good renders of the composition nor lets the known defective render through. The regression guarantee is against the saved defective artifact (deterministic), which is the correct guarantee: a single live re-run can never "prove" a stochastic defect is gone.

### B.6 Margin table (final window, MEASURED)
| Channel | τ | Worst drop (must reject) | Worst-protected TP | Margin note |
|---|---|---|---|---|
| S1 coverage | ≥ 0.35 | synth_partial 0.4007 (passes S1 → caught by S6) | E-1 0.3524 (1.01×, historical artifact, not in harness); m0_repro 0.3451 (stays REFUSE) | coverage alone was the flawed channel; now only the first of three ANDs |
| S5 new-skin | < 0.10 | class-E **0.3043** (3.04×); g_short 0.1653 (1.65×) | TP max **0.0923** (m1, ~1.09× — **thinnest margin in the system; disclosed**: benign hand/cuff-edge skin, not a defect) | structural discriminator |
| S6 wrist-reach v2 | ≥ 0.05 | all drops 0.0000 | TP min **0.1485** (cal_05, 2.97×) | catches partial drops that pass S1+S5 |

**SLEEVE SAFETY status: the defect render is rejected; property regression-tested; release still BLOCKED on the other barriers (§H).**

## C. P1 — N=2 controlled experiments (this phase)

Design (production path, live worker, short-sleeve top so the long-sleeve gate is N/A and the LAYER-APPLICATION variable is isolated; one attempt per run — **no retries**; the only repeats are the controlled repeats themselves; 90 s spacing for the time axis). Anchor composition (A, teal-tee rt1) produces a deterministic L1 byte-sample (`0f29f3a5`) via the worker's output cache, so "same L1" = genuinely identical L1 bytes.

| Condition | Runs | Result |
|---|---|---|
| C1 same L1 + same bottom (A, rt1, olive) | 5 (spaced 90 s) | **5/5 PASS** — L1 `0f29f3a5` + L2 `0a461f33` **byte-identical every run** (pxchg 4.1086) |
| C2 same L1 + different bottom (A, rt1) | navy ×3, beige ×3 | **6/6 PASS** — same L1 `0f29f3a5`; navy→L2 `59419fcd` (pxchg 1.3891, identical ×3), beige→L2 `aa1c550d` (pxchg 6.9311, identical ×3): bottom changes the L2 output, stably |
| C3 same person/top + NEW L1 (A, rt4, olive) | 3 | **3/3 PASS** — new L1 sample `c1ab11cd` → L2 `d915a3b0` (pxchg 6.9346, identical ×3) |
| C4 same input across time | = C1 sequence (90 s spacing, ~7 min span) | **0 flips** — no time-axis drift observed on this instance |
| C5 multi-person, same bottom (rt1, navy) | C ×2, I ×2 | **C 2/2 PASS** (L1 `c1c5e9d4` → L2 `3ae494d2`, pxchg 15.769); **I 0/2 — 502 `VTON_LAYER_NOT_APPLIED`** (L1 `de299533`, pxchg **0.2915**, color_shift **0.00206**, bit-identical across both runs) |
| C6 multi-bottom, same L1 (A, rt1, black joggers) | 2 | **2/2 PASS** — L1 `0f29f3a5` → L2 `8d444fd7` (pxchg 5.9472, identical ×2) |

**Total: 18/20 PASS, 2/20 REFUSE. Every refusal is the person-I composition.**

**P1 findings (MEASURED, evidence-bound):**
1. **Within-cache determinism is exact.** Identical (person, top, bottom) → byte-identical L1 and L2 and identical verify metrics, across repeated runs and across a ~7-minute time axis (0 flips). The worker's output cache makes the decision deterministic per composition on a given instance; "retry" only re-reads the same cached outcome.
2. **The L1 sample (person image × top) is the dominant variable.** Same top + same bottom: person A → PASS (L1 `0f29f3a5`), person C → PASS (L1 `c1c5e9d4`), person I → **REFUSE** (L1 `de299533`). The L1 bytes differ per person and the L2 outcome follows the L1 sample.
3. **The person-I failure is mechanistically explained (agent visual inspection of the L1 + input):** person I's base photo already contains **navy drawstring joggers**; the N=2 bottom garment is **navy virgin-wool trousers**. The L2 render changed the bottom region by only **0.29% of pixels (color_shift 0.002)** — one to two orders below every passing run (1.39–15.77) — so the change-based verify cannot confirm application and the service honestly refuses. **Low-contrast payload failure: deterministic, stable, explainable** — not a stochastic drop. (The L2 render bytes are not retained by the service on verify failure, so whether the trousers were "visually" applied cannot be independently confirmed — the honest statement is *unverifiable application*, which is exactly what the refusal semantics assert.)
4. **Bottom payload has a measurable effect** (distinct, stable L2 bytes per bottom for the same L1: `59419fcd`/`aa1c550d`/`8d444fd7`), but on the current instance all three bottoms pass for person A.
5. **Instance-era state matters:** (A, rt1, olive) — L1 `0f29f3a5`, the Phase-3 **3/3 failing** cached composition — is now **5/5 PASS** on the current instance; person C's L1 `c1c5e9d4` (Phase-3 3/3 FAIL) is now PASS. Conversely, person I's L1 `de299533` failed 3/3 in Phase 3 and 2/2 in Phase 5 — **persistent across instances**. Refinement of the Phase-4 classification: the "worker-state" component is at least partly **instance-local output-cache content** (which cached outcomes an instance holds), while the L1-sample-dependent failures (person I) persist across instances.
6. **N=2 does NOT meet a product reliability bar on this evidence:** 18/20 in a controlled 20-run set, but **0% on the person-I composition** — a composition that fails deterministically for a foreseeable reason (customer wearing the same color as the garment). The service behavior is correct-as-designed (refuse unverifiable application; no fake success), but the product decision for low-contrast compositions (refuse vs. calibrated verify) is open and unchanged by this phase — no threshold was moved.
7. **P1-A (retry is not the fix): CONFIRMED AGAIN (measured, not asserted)** — both person-I repeats (a controlled repeat, not a retry-until-success loop) produced the identical failure; Phase-4's measured retry ineffectiveness (first-attempt 13.3%, within-5 30.8%) stands. No retry/hidden-fallback/previous-image/alternate-static/fake-success path exists or was added.
8. **Retained Phase-4 classification (refined, not overturned):** N=2 outcome = f(L1 sample × bottom payload × worker-state), where worker-state now includes instance-local cache content; the internal cache/seed mechanism of the closed worker remains **UNRESOLVED** (no internal access; no root-cause claim made).

## D. P2 — MCP Market audit (summary; full document: `MCP_MARKET_TRYON_AUDIT_2026-09-19.md`)

- Surfaces: MCP servers (48,857) + Agent Skills (358,558). Multi-keyword search sweep (top-20 per query, server-side), category pages (e-commerce 1,297 servers / 67 p; 5,232 e-commerce skills / 100 p — page 1 scanned; **skills surface NOT exhaustively enumerable** — documented residual gap).
- **The 6 known examples (WeShop ×4, AI Clothes Changer, AI/Bikini Virtual Try-On): NOT FOUND / UNVERIFIED on the live site (2026-09-19)** — zero search hits, slug 404s. The earlier list is neither the complete list nor evidence of availability.
- Try-on generation candidates: **Vybe** (REJECTED — its Replicate model `arnab-optimatik/vybe-virtual-tryon` is 404/dead on Replicate, verified), **fal-tryon skill** (EVALUATION — hosted fal.ai VTO endpoints, dynamic engine identity, no key available → not tested; third-party upload of user images), **HeyBeauty** / **TryOnfy** (RESEARCH — proprietary hosted APIs, unverified), **GenPark VTO Fit Matcher** (RESEARCH — sizing attributes, not an engine), **CLO3D** (REJECTED — 3D CAD domain), ComfyUI wrappers (RESEARCH — not turnkey VTO).
- **No open-source VTO engine with auditable weights is distributed through the market.** All generation candidates are hosted commercial APIs. Marketing adjectives treated as unverified.
- Security screening (pre-install): env-var credentials, third-party upload of user images (privacy/residency exposure, no DPA evidenced), third-party egress domains, no retention guarantees, low-provenance wrapper repos. **Nothing installed, nothing connected, nothing called.**
- **INTEGRATION BLOCKED** — 15-condition checklist: every candidate fails ≥1 condition (engine identity, rights, multi-garment, identity, privacy, cost, tests). **FASHN HOLDS.** No blind model replacement; no supporting tool adopted without its own license gate (rembg weight-license caveat documented).

## E. Local / global validation state

- **Global (live worker, this phase):** class-E composition live re-run (2026-09-19) → correctly-sleeved render, gate PASS (sleeve channels: new-skin 0.0/0.0, wrist-reach 0.4969) — `p0d_live_class_e/`. N=2 P1 matrix (this phase) — §C. Prior global dynamic validation (2026-09-15/16) preserved in the global report; no regression observed this phase.
- **Local (hermetic, this phase):** 50-row sleeve matrix replayed through production `evaluate_sleeves_sync` → 21/29, 0 failures; full backend suite **1225 passed / 29 skipped / 0 failed** (214.75 s); evaluation suite **99 passed / 0 failed**; security suites **34 passed** (deployment headers + hardening + measurement-session); licenses/secrets **6 passed**; runtime import closure gate **OK** (no new dependencies — sleeve gate is pure PIL/numpy).
- **Fresh dynamic validation for release:** still outstanding — a new full dynamic batch (persons × garments × N=2, live) is required as part of closing the release barriers; not yet executed this phase.

## F. Human calibration — **BLOCKED (unchanged)**
- No human raters available in this environment; **no VLM / agent / MCP / model-confidence substitution performed or permitted.** All sleeve labels this phase are explicitly `AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH`. The gate's thresholds are calibration-pending human sign-off; the 50-row matrix is agent-labeled evidence, not ground truth. This barrier is unchanged from Part 4 and remains a release blocker.

## G. Identity — **LICENSE-GATED (unchanged)**
- insightface `w600k_r50.onnx` (WebFace600K-trained, sha 4c06341c…, 174,383,860 B) remains eval-only; commercial rights UNRESOLVED. `buffalo_l` (sha 80ffe37d…) identical 4×. No silent promotion to production. Any identity feature stays gated until rights are resolved in writing. AdaFace/w600k production use remains BLOCKED by the same gate.

## H. Security / provenance
- No new secrets introduced (staged-diff secret scan clean); Modal tokens env-only; no GitHub PAT (push BLOCKED); no user images, weights, or secrets committed (artifacts under gitignored `evaluation/results/`); `evaluation/.gitignore` enforces this.
- Security test suites green after the sleeve change (34 passed) — the change adds no I/O, no network, no new imports (runtime closure gate OK).
- MCP Market security screening: §D; nothing installed/connected.
- Provenance: every measurement in this phase has an artifact path (results JSON / saved PNGs / git SHA) recorded in the companion audit and in §B/C.

## I. Release state (ONE)

**RELEASE = BLOCKED.**

| # | Barrier | State | What closes it |
|---|---|---|---|
| 1 | Class-E / sleeve FPs eliminated | **CLOSED for the known defect render + all synthetic/independent equivalents (regression-tested)**; the engine drop itself remains stochastic — the gate, not the engine, provides the guarantee | further only by human-labeled dynamic batch (barrier 5) |
| 2 | N=2 meets the product bar | **NOT MET (MEASURED)** — §C: 18/20 controlled; 0/2 on the low-contrast person-I composition (mechanism identified: navy-on-navy, verify pxchg 0.2915); retry measured ineffective; no threshold moved | product decision on low-contrast compositions (keep refusing vs. calibrated verify) + fresh dynamic batch at the agreed bar |
| 3 | Human calibration | **BLOCKED** — no human raters; agent labels are not ground truth | human sign-off on sleeve labels/thresholds |
| 4 | Identity licensing | **LICENSE-GATED** — w600k commercial rights unresolved | written rights resolution |
| 5 | Fresh dynamic validation (local + global) | **OUTSTANDING** — prior batches preserved; a fresh full dynamic batch (incl. N=2) is required | execute + pass the full test matrix |
| 6 | Integrations pass gates | **INTEGRATION BLOCKED** — MCP Market: no candidate passes; nothing installed | (no candidate to integrate; FASHN HOLDS) |

No barrier may be declared closed without its evidence; no BLOCKED→GO transitions are made in this report.

## J. Git (exact)
- Branch: `vton-evidence-reconciliation-2026-09-16` · sleeve commit: `c5d6207` · base: `aa0649d` (Phase-4 re-commit) · `main` untouched · **no push, no PR, no deployment — no remote evidence exists and none is claimed.**
- Tree: clean after commit (working tree changes staged; audit + Part-5 report committed in the Phase-5 final commit).

## K. What is explicitly NOT claimed
- Not claimed: that the FASHN engine no longer *produces* dropped sleeves (stochastic defect persists; the gate guarantees non-delivery of the defective render).
- Not claimed: that any MCP-market tool was tested, installed, or works.
- Not claimed: that N=2 is deterministic, root-caused, or retry-fixable.
- Not claimed: human-level ground truth anywhere; agent visual inspection only, labeled as such.
- Not claimed: any remote/push/deployment/production state.
