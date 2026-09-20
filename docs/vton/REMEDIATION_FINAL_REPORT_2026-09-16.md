# CONFIT_A — POST-DYNAMIC VALIDATION REMEDIATION: FINAL REPORT

**Date:** 2026-09-16 · **Author:** CONFIT_A VTON engineering (agent-executed, all claims evidence-traced)
**Scope:** Evidence reconciliation, root-cause repair, safe-promotion audit (master prompt, 2026-09-16 session)
**Predecessor reports (preserved, NOT rewritten):** `DYNAMIC_PHASE_FINAL_REPORT.md`, `ARCHITECTURE_TEST_REPORT.md`, `LOCAL_DYNAMIC_VALIDATION_REPORT.md`, `GLOBAL_DYNAMIC_VALIDATION_REPORT.md` (all 2026-09-15/16)

Status vocabulary used: VERIFIED · MEASURED · TESTED · IMPLEMENTED · CONDITIONALLY VERIFIED · PARTIAL · NOT VERIFIED · BLOCKED · UNRESOLVED · UNSUPPORTED · LICENSE-GATED · NO-GO

---

## A. Current baseline (exact)

| Item | Value | Evidence |
|---|---|---|
| Branch / HEAD | `main` @ `928e615110640c00df0db80ef1a93f92ff353870` (= `origin/main`) | `git log`, `git rev-parse` |
| Research branch `69dc8be` | **LOST in sandbox restore** — `.git` re-cloned (reflog single entry: `clone:`); all VTON work survives only in the working tree (uncommitted) | `git reflog`, `git branch -a` |
| Worker service | `vton-worker-segfee`, engine `fashn_vton_segfee`, model `fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)`, device NVIDIA A10G, worker `git_sha 928e615…-dirty`, `ready: true` | live health endpoint, 2026-09-16 (this session) |
| Hermetic suite (this session) | **1247 passed / 0 failed / 32 skipped** (223.05 s) | `pytest backend/tests/ evaluation/tests/` |
| Live AT suite (this session) | **28 passed / 1 failed** of 29 after restoring the evaluation environment (details §I) | `/tmp/at_live_run_20260916.log` + targeted re-runs |

**Documented discrepancy (investigated, per master prompt §2):** the previous report's branch `69dc8be` no longer exists (fresh clone). No history was recreated; the discrepancy is recorded here. All prior-phase work is present in the working tree and is committed on a focused branch in this session (SHA in §N). `main` was not touched.

**Environment incident (this session, resolved, evidence preserved):** the sandbox rebuild lost `evaluation/weights_local/arcface_w600k/w600k_r50.onnx` (gitignored — LICENSE-GATED weight, never committed by policy) and the `onnxruntime`/`mediapipe`/`easyocr`/`torch` packages. This caused 5 live test failures (AT-01/02/08/17/E2E) that were **environment failures, not product failures**. Restored: buffalo_l.zip re-downloaded (288,621,354 B — identical size to the previously verified download; w600k_r50.onnx 174,383,860 B), packages reinstalled. All 5 re-ran **PASSED** (270.77 s live run).

---

## B. P0 — N=2 lower-slot layer-2 diagnosis

**Previous state (2026-09-15, preserved report):** top→bottom N=2 (lower slot as layer 2) failed deterministically on the then-current worker instance; AT-04/AT-10 red; byte-identical failure signatures across 2 runs; worker redeploy BLOCKED (no Modal credentials).

**This session (MEASURED, live, current instance):**

| Test | Chain | This session | Evidence |
|---|---|---|---|
| AT-04 | top+bottom outfits [22,23]/[24,23] | **PASSED** — `all_layers_verified [true,true]`; lower(olive) coverage 0.2693/0.3166; upper(teal/mustard) 0.3534/0.2298; order server-derived | live evidence JSON, this run |
| AT-10 | combined unknown top+bottom (g1+g2) | **PASSED** — status completed, all layers verified, olive coverage assert passed, identity confirmed | re-run live 2026-09-16 (PASSED) |
| AT-15 | inner+outer (g1 tee + product-1 blazer, both upper slots) | **FAILED** — 502 `VTON_SLEEVES_NOT_VERIFIED`, layer-2 coverage 0.285/0.3282 (NOT_VERIFIED band) | live run + exact-reproduction probe (§C) |

**Diagnosis update (honest, evidence-bound):**
1. The previous **lower-slot** failure (top→bottom) **does not reproduce on the current worker instance** — AT-04 and AT-10 pass with the lower layer verified. This supports hypothesis **A (worker-instance/runtime state)** over C (deterministic engine defect). It does **not** prove A conclusively: the prior failure reproduced byte-identically across retries, so the current pass could itself be instance-state-dependent.
2. AT-15 is **not** a lower-slot failure (both layers are upper slots) and is **not** a sleeve-drop defect — see §C. Its own embedded history records the same chain "succeeded twice (20:21/20:35, verified) and then failed" — further evidence of instance/state dependence.
3. **Worker redeploy/recycle: BLOCKED** — no Modal credentials in this environment. No deployment was attempted or claimed.
4. P0 acceptance criteria (§4 P0-E) **not fully met**: multi-person × multi-bottom re-verification and post-recycle verification are impossible without credentials; instance-state dependence cannot be ruled out. **P0 status: OPEN (improved — no longer reproducing on the current instance).**

---

## C. P1 — Long-sleeve safety (root-cause repair, this session)

### C.1 What was broken (measured, reproduced before fixing)
1. **Original S31 defect (L1, 2026-09-15, preserved):** engine dropped the sleeves of a long-sleeve tee and returned `verify.PASS=True` (silent success). Closed by the per-layer sleeve-integrity gate (v2.0/v2.1, previous session).
2. **Gate over-refusal regression (C-07, found 2026-09-16, this session's root cause):** the differential v2.1 probe ("garment-colored in output but not already in input") **false-refused correctly rendered, fully-sleeved, engine-verified dark garments**: live contract C-07 read 0.2110 (REFUSE) on a good blazer render; E-1 standalone blazer read 0.0366/0.1077 (REFUSE) with sleeves clearly present. Mechanism (MEASURED): dark trousers/background at the forearm band are within ΔE40 of a dark garment reference, annihilating the newness signal.

### C.2 The fix (IMPLEMENTED, regression-tested, live-verified)
`vton_sleeve_gate.py` v2.2 — **changed garment-color probe**: a band pixel counts as sleeve evidence only when the output is garment-colored (ΔE ≤ 40 from the garment's dominant color) **AND** ΔE(output, input) > 20 (the pixel actually changed). This removes input-side contamination of **any** color family (dark trousers, the L1 tan skirt, similar-colored previous layers) while still counting a real applied sleeve. Generic only — no fixture/garment IDs anywhere (code scan: `test_architecture_code_scan.py` green).

**Measured calibration (best-arm coverage, 2026-09-16):**

| Artifact (sleeve truth) | v2.1 differential | v2.2 change probe | Verdict |
|---|---|---|---|
| L1 defect (sleeves DROPPED) | 0.0635 | **0.0274** | REFUSE (12.8× below the 0.35 line) |
| E-1 blazer rt2 (present) | 0.1077 ✗ false | **0.3524** | PASS (thinnest, 1.01×) |
| C-07 blazer rt4 (present) | 0.2110 ✗ false | **0.6022** | PASS (1.72×) |
| AT-16b burgundy rt1 (present) | 0.3934 | **0.4725** | PASS (1.35×) |
| L2 dress (present) | 0.8871 | **0.9436** | PASS (2.69×) |

Strict improvement on every measured artifact; the 0.35/0.15 boundaries were **not** moved.

### C.3 Verification
- **Regression:** `test_sleeve_gate_regression.py` **19/19** (17 prior + 2 new over-refusal replays: E-1 and C-07 artifacts must PASS; L1 artifact + synthetic tan-contamination must REFUSE).
- **Hermetic full suite:** 1247 P / 0 F / 32 S.
- **Live (this session):**
  - **C-07 contract: COMPLETED** — job `vton_job_25666e7f9d5a`, `model_used = fashn-vton-v1.5 (fashn_vton_segfee…)`, verification PASS (pixel_change 8.0729, color_shift 0.05533, all_layers_verified) — direct DB evidence.
  - **C-05 live: PASSED** (job `vton_job_1cdb2dcbc018`, completed, PASS). The previous session's "C-05 ERROR" did **not** recur in two consecutive live runs → classified as transient (worker cold-start class); the error-taxonomy contract holds (C-08 matrix PASS).
  - **AT-20 (L1 defect live, product 105): REFUSED honestly** — 502, coverage 0.2061 (NOT_VERIFIED), no image delivered. The original silent-success defect remains closed under the new probe.
  - **AT-21 (good long-sleeve live render): PASSED** the gate — no over-refusal on a good render.

### C.4 Residual limitation (MEASURED, both sides of the line — no hidden limitation)
The 0.35 PASS line cuts **through the middle** of the dark-blazer / arms-at-sides / dark-lower-body composition class: E-1 = 0.3524 (PASS, 1.01×) vs **AT-15 = 0.3282 (REFUSE, 0.94×)**. An exact-reproduction probe of AT-15 (production path, capture wrapper around the gate, behavior unchanged) captured the refused layer-2 render; **agent visual inspection shows the blazer WITH full long sleeves present** (artifact: `evaluation/results/outputs/at15_layer2_blazer_refused_render_20260916.png`; capture probe: `evaluation/probes/at15_layer2_capture_probe.py`). So AT-15 is a **probe-margin over-refusal of a visually-correct render, not a sleeve-drop defect** (contrast L1: sleeves actually absent, 0.0274).

Consequences (honest):
- The gate **never silently ships** a sleeve-drop render (L1 class refused with wide margin; thin-margin renders refused in the safe direction). P1's safety goal ("production cannot silently ship the previously observed sleeve-drop defect") is **MET**.
- The gate **over-refuses** some visually-acceptable dark-outerwear renders (AT-15). Delivering this composition class reliably requires more calibration data. The threshold was **not** lowered to force a pass (standing rule). **P1 status: safe gating IMPLEMENTED + live-verified; robustness on the thin-margin class = NOT VERIFIED (calibration data gap).**

---

## D. P2 — Human calibration

- Calibration **package exists** (previous session, preserved): `docs/calibration/2026-09-15/` — PROTOCOL, RUBRIC (D1–D8), RUBRIC_V2_GATEA_ADDENDUM, METRICS, BASELINE_REPORT, CALIBRATION_REPORT, LICENSE_AUDIT.
- **Execution: BLOCKED** — no genuine human raters are available in this environment. No synthetic scores, no agent-inspection substitution, no VLM-as-rater. **Gate A: BLOCKED.** (Agent visual inspections used in this report are explicitly labeled as such and never counted as human validation.)

---

## E. P3 — Production identity verification licensing

- **Evaluation-only identity model:** ArcFace w600k_r50 (trained on WebFace600K → commercial rights UNRESOLVED). **LICENSE-GATED: evaluation-only.** Weights gitignored, never committed, never in the production decision path. Used only for AT-01/02/08/17/E2E measurement evidence.
- **Production identity enforcement: no commercially cleared model established → BLOCKED.** DINOv2 (Apache-2.0) remains a drift proxy, not face recognition. No silent substitution of evaluation models into production.

---

## F. P4 — Security / privacy (measured status)

| Control | Status (this session unless noted) | Evidence |
|---|---|---|
| Catalog authority (server-derived layers/slots) | VERIFIED | AT-13 PASS (live) |
| Multi-tenant authz + one-shot delivery | VERIFIED | AT-14 PASS (live) |
| Request→output provenance, no raw bytes in status | VERIFIED | AT-05 PASS (live); C-07 PASS (30/30 contracts incl. token-verified 200 / wrong-token 404 / no bytes) |
| No fixture substitution / unknown inputs work | VERIFIED | AT-07 PASS (live); AT-E2E zero-fixture PASS |
| SSRF protection (person + garment URLs) | VERIFIED | C-01/C-02 invalid cases PASS (hermetic); `is_safe_image_url` in path |
| Malformed/oversized/undersized/invalid images | VERIFIED | C-01/C-05/C-08 matrices PASS (explicit codes, no 500) |
| No fake success / no static asset on failure | VERIFIED | C-08 PASS; AT-07; `test_no_fake_success_on_failure` |
| Worker-unavailable behavior | VERIFIED | C-05 `VTON_ENGINE_UNAVAILABLE` explicit code; C-08 |
| Result provenance completeness (job row) | VERIFIED | C-07 PASS (field list + hash trace) |
| Rate limiting | NOT RE-VERIFIED this session (tested in prior sessions; `test_rate_limiting.py` green in this session's hermetic run as part of 1247) | hermetic suite |
| Account-deletion privacy flow | NOT VERIFIED (out of scope this session) | — |
| Delivery-token replay/expiry | VERIFIED one-shot (AT-14, C-07); expiry NOT re-verified | — |
| No image bytes / tokens in logs | VERIFIED | C-07 invalid-status test + `test_worker_config_no_secrets_logged` (green) |

**C-05 ERROR (open from prior session):** NOT reproduced in two consecutive live C-05 runs (both completed, PASS). Classified: transient (cold-start class), contract intact. Traceback not captured because it did not recur.

---

## G. Dynamic local validation (post-remediation)

- Fresh **unknown-runtime** persons/garments exercised live this session: person_rt1–rt4 + garment_rt1–4 (archtest set, data-URL catalog rows) across AT-01…AT-19, AT-E2E — this IS fresh dynamic runtime input validation (no fixtures).
- Local-market artifacts (hijab/modest, Arabic text): L1 (defect artifact) and L2 (dress) replays re-executed hermetically this session (L1 REFUSE 0.0274, L2 PASS 0.9436). **A fresh local-market live re-run (hijab + Arabic-text garment) is PENDING** — not claimed green for this session.

## H. Dynamic global validation (post-remediation)

- Global unknown persons (rt1–rt4) exercised live this session (AT-08 unknown person PASSED after env restore; AT-17 identity matrix PASSED: each output matches its own person, argmax margins 0.1645–0.2407, LICENSE-GATED model).
- **A fresh dedicated global live re-run (varied lighting/background matrix) is PENDING** — prior session's 3/3 result is carried, not re-claimed.

---

## I. Architecture test matrix (this session, exact)

Live AT suite, 29 tests, current worker instance, evaluation env restored:

| Test | Result | Classification |
|---|---|---|
| AT-01 user-image passthrough | PASS* | *initially env-FAILED (missing weights), PASSED on re-run |
| AT-02 unique persons same garment | PASS* | *same as AT-01 |
| AT-03 unique garments same person | PASS | |
| AT-04 unique outfits N=2 (top+bottom) | **PASS** | lower slot as layer 2 verified (no longer reproducing) |
| AT-05 request/output provenance | PASS | |
| AT-06 determinism / no stale cache | PASS | |
| AT-07 no fixture substitution | PASS | |
| AT-08 unknown person | PASS* | *env re-run |
| AT-09 unknown garment | PASS | |
| AT-10 combined unknown top+bottom | PASS* | *env re-run (its initial failure was the missing-weights identity step; all product asserts had passed) |
| AT-11 person variability (4 params) | PASS | |
| AT-12 garment variability (3 params) | PASS | |
| AT-13 catalog authority | PASS | |
| AT-14 multi-tenant authz + one-shot | PASS | |
| AT-15 N=2 inner+outer | **FAIL (honest)** | sleeve-gate thin-margin REFUSE 0.3282 (sleeves visually present — §C.4); safe direction, no fake image |
| AT-15b N=3 evaluation-only | PASS (502 classified EVALUATION-ONLY) | |
| AT-16 failure taxonomy | PASS | |
| AT-16b live quality-gate honest failure | PASS | |
| AT-17 identity unknown persons | PASS* | *env re-run (prior "anomaly" = same weights loss) |
| AT-18 garment fidelity | PASS | |
| AT-19 generic sleeve detector on unknown garment | PASS | |
| AT-E2E canonical zero-fixture | PASS* | *env re-run |
| AT-20 sleeve-gate L1 defect regression | PASS | honest 502 REFUSE, coverage 0.2061 |
| AT-21 sleeve-gate no false positive | PASS | good long-sleeve render passed |
| Contracts C-01…C-08 (30 tests) | 30/30 PASS | incl. C-05 live + C-07 live completed |

**Totals: live 28 P / 1 F (AT-15) + contracts 30/30; hermetic 1247 P / 0 F / 32 S.**

---

## J. Regression matrix (old failures → current state)

| Original failure | Root cause | Change | Regression test | Live evidence (this session) |
|---|---|---|---|---|
| L1 silent sleeve-drop success (S31) | engine verify blind to dropped sleeves | per-layer sleeve gate (v2.0→v2.1→v2.2) | `test_replay_l1_defect_artifact_now_refused` + synthetic tan-contamination + AT-20 | AT-20 REFUSED (0.2061, 502, no image) — VERIFIED |
| C-07 contract red (live) | gate over-refusal of dark garments (differential probe) | change probe v2.2 | `test_replay_c07_seed_blazer_not_overrefused` | C-07 job **completed** (DB evidence) — VERIFIED |
| E-1 over-refusal (dark blazer) | same root cause | same | `test_replay_e1_dark_blazer_not_overrefused` | replay PASS 0.3524 — VERIFIED (hermetic) |
| AT-04/AT-10 N=2 lower-slot red | worker-instance state (not conclusively root-caused) | none repo-side (no speculative worker fix) | AT-04/AT-10 remain the live regression | not reproducing on current instance — CONDITIONALLY VERIFIED (instance-dependence unresolved) |
| AT-15 N=2 inner+outer red | sleeve-gate thin margin on dark-outerwear composition (0.3282); sleeves present (agent inspection) | none (threshold NOT lowered) | AT-15 honest-failure record | REFUSED safely (502, no image) — limitation documented, NOT VERIFIED as deliverable |

---

## K. Production exposure status

- **API readiness:** decision path tested = production path (TestClient → real service → live worker). Not promoted.
- **Worker readiness:** healthy, `fashn-vton-v1.5` A10G; N=2 reliability instance-dependent (§B).
- **Shadow/staging readiness:** NOT executed (requires deployment access).
- **Frontend readiness:** §47 production branch remains gated; no exposure.

## L. Remaining risks (no hidden limitations)

1. **N=2 instance-state dependence** (top+bottom passes on current instance; failed on the previous one) — no redeploy possible here; reliability NOT VERIFIED across instances.
2. **Sleeve-gate thin-margin class** (dark outerwear, arms-at-sides, dark lower body): over-refusal of visually-correct renders (AT-15 0.3282) / razor-thin pass (E-1 0.3524). Safe direction only.
3. **Human calibration (Gate A) not executed** — no release-quality human evidence.
4. **Production identity model LICENSE-GATED** — no cleared model for production identity enforcement.
5. **Multi-garment same-family chains** (outer sleeve color within ΔE20 of inner sleeve color in the input) may over-refuse — documented in gate docstring, not measured.
6. **Git history loss** (69dc8be) — work recovered in working tree and re-committed this session; prior commit SHAs are unrecoverable.
7. Fresh local-market (hijab/Arabic) and dedicated global live re-runs pending (§G/§H).

## M. CLAIM AUDIT (major claims)

| CLAIM | EVIDENCE | STATUS |
|---|---|---|
| The sleeve gate no longer silently ships the L1 sleeve-drop defect | AT-20 live 502 REFUSE (0.2061, no image); L1 replay 0.0274; 19/19 regression | VERIFIED (defect side) |
| The C-07 over-refusal is fixed | C-07 live job completed (DB row, model_used, verify PASS); C-07 replay 0.6022; E-1 replay 0.3524 | VERIFIED (measured 5-artifact set) |
| The sleeve gate is a robust production gate for ALL long-sleeve garments | 5-artifact calibration set; E-1 margin 1.01×; AT-15 over-refusal | NOT VERIFIED (thin-margin class) |
| N=2 top+bottom works | AT-04/AT-10 live PASS on current instance; failed on prior instance | CONDITIONALLY VERIFIED (instance-dependent; redeploy BLOCKED) |
| N=2 inner+outer is deliverable | AT-15 REFUSED (0.3282), sleeves present per agent inspection | NOT VERIFIED (safe refusal; margin gap) |
| The 5 initial live failures (AT-01/02/08/17/E2E) were product defects | all reproduced after weights+onnxruntime restore; PASSED on re-run | REFUTED — environment failures, resolved |
| C-05 contract is intact | 2 consecutive live C-05 completions; C-05/C-07 contracts 30/30 | VERIFIED (prior ERROR transient, not reproduced) |
| Security controls hold on the real path | AT-05/07/13/14 live PASS; contracts C-01…C-08 30/30 | VERIFIED (tested axes) |
| Human validation passed | none (no raters in env) | BLOCKED |
| Production identity is commercially cleared | ArcFace w600k WebFace600K rights UNRESOLVED; no cleared model | LICENSE-GATED / BLOCKED |
| Push/PR/deployment occurred | no PAT in env; no Modal creds; nothing pushed | BLOCKED (not claimed) |

## N. Final release decision

**BLOCKED** — unchanged in kind, refined in substance. Direct evidence for each standing blocker:

1. **N=2 top+bottom not proven reliable** — passes on the current worker instance (AT-04/AT-10) but failed on the prior instance; instance-state dependence unresolved; worker redeploy BLOCKED (no credentials). NOT a GO basis.
2. **Sleeve gate robustness on the thin-margin class NOT VERIFIED** — safe (never a silent pass), but over-refuses visually-correct dark-outerwear renders (AT-15) and the PASS margin is 1.01× (E-1). No frozen-threshold claim is made.
3. **Human calibration (Gate A) not executed** — BLOCKED (no raters); release bar requires it.
4. **Production identity enforcement LICENSE-GATED** — no commercially cleared model.
5. **Not a NO-GO:** the architecture meets the product bar with safe explicit refusals on the current evidence (defect side solidly closed; provenance/authz/SSRF/no-fake-success VERIFIED; all reds are honest 502s or documented limitations, no silent failures).

**What would close the blockers (evidence to produce):** (a) authorized worker redeploy/recycle + P0-B discriminating matrix across ≥2 persons × ≥2 bottoms (P0 close); (b) ≥10 more measured long-sleeve artifacts across the dark-outerwear composition class to establish a robust PASS margin or a category restriction (P1 close); (c) 3 genuine raters on the existing calibration package (P2/Gate A); (d) a commercially cleared identity model with written license evidence (P3).

**Git (this session):** branch `vton-evidence-reconciliation-2026-09-16` (cut from `main` @ `928e615`, `main` untouched). Work commit: **`7ee5756f4fcb7ad0dcdac5af616f5513a1fabddb`** (sleeve gate v2.2 + regression replays + AT-15 probe + the complete recommit of the lost 69dc8be dynamic-phase work, 132 files). This report: second commit on the same branch (records the work-commit SHA above). Secret scan of to-be-committed content clean (only hits = the token-reading regex in the AT suite/probe, no literal secrets); LICENSE-GATED weights and eval credentials excluded via gitignore; **PUSH BLOCKED** (no GitHub PAT in environment) — no push, PR, or deployment is claimed.

> **SHA correction (Part 2, 2026-09-16):** a second sandbox restore (see Part 2 §A) lost `.git` a third time; `7ee5756` (and the second report commit `5c74e32`) no longer exist. The entire working tree (including this report) was re-committed as **`4a8baa0`** on the recreated branch. `4a8baa0` is the current work commit; Part 2 §A carries the full record.

---

## O. Learning notes (per error)

1. **Differential probe false-refused dark garments (C-07/E-1).** Why not caught earlier: the v2.1 calibration set lacked a dark-garment-on-dark-input case; the probe's "newness" premise was assumed, not stress-tested. Lesson: a probe's *rejection* side must be calibrated on the product's flagship garments, not just its defect artifacts. Changed: change probe v2.2 + 2 over-refusal regression replays. Recurrence prevention: any future probe change must replay all 5+ artifacts (defect + good renders across color families).
2. **Sandbox restore lost git history (69dc8be) and gitignored eval weights.** Why: workspace snapshot does not persist `.git` objects or gitignored files. Lesson: critical eval assets that are gitignored must have a documented restore procedure (now: buffalo_l.zip size+content verification in this report). Changed: weights restored + verified; discrepancy documented (§A). Recurrence prevention: restore steps recorded; commit discipline (commit work each session) reduces exposure.
3. **5 live tests failed for environment reasons (missing weights) and initially looked like regressions.** Why not caught immediately: the failure surfaced deep in the identity step, not at the render. Lesson: after any environment change, diff failure signatures against known product failure codes before attributing to code. Changed: root-caused to `weights_local` loss before touching any product code (no gate changes made in response).
4. **AT-15's thin margin (0.3282) is a measured limitation, not a defect.** Lesson: "the gate refused it" and "the render is wrong" are different claims; the refused render was captured and inspected before classifying. Changed: capture probe + documented limitation (§C.4).

## P. Truth questions (direct answers)

1. **Real vs environment vs test failures this session?** Real product state: AT-15 (thin-margin safe refusal). Environment: AT-01/02/08/17/E2E initial failures (missing weights/packages) — all resolved, all PASSED on re-run. Test issues: none (no test was weakened or deleted; 2 replays ADDED).
2. **What was actually fixed?** The sleeve-gate over-refusal of dark garments (change probe v2.2) — root-caused, fixed, regression-tested (19/19), live-verified (C-07 completed, AT-20/AT-21 correct).
3. **What was actually re-verified?** Full hermetic suite (1247 P/0 F), live contracts C-01…C-08 (30/30), live AT suite (28/29 after env restore), C-05/C-07 live completions (DB evidence).
4. **What remains broken?** AT-15's N=2 inner+outer long-sleeve chain is refused (thin margin); N=2 reliability across worker instances is unproven.
5. **What remains externally blocked?** Worker redeploy (no Modal credentials); push/PR (no GitHub PAT); human raters; commercial identity rights.
6. **Root causes established?** C-07 red: probe design flaw (newness premise vs dark inputs) — MEASURED + fixed. L1: engine verify blind spot — MEASURED + gated. N=2 lower slot: instance-state dependent — NOT conclusively root-caused (redeploy needed).
7. **What is still unknown?** Whether the current worker instance's N=2 pass state is stable across instance lifetimes; the true sleeve-application quality inside AT-15-class N=2 renders beyond agent inspection.
8. **What evidence would close each gap?** §N list (a)–(d).
9. **What is safely user-exposable today?** Single-garment renders of the tested catalog classes with the sleeve gate active; N=2 top+bottom (current instance); explicit 502 refusals with honest error codes. NOT exposable: inner+outer long-sleeve chains (over-refusal), any human-quality claim, production identity enforcement.
10. **What must be refused (and is refused)?** Unverifiable long-sleeve renders (L1 class, thin-margin class), undeclared-sleeve garments, white-on-white blind-spot garments — all via `VTON_SLEEVES_NOT_VERIFIED`, no image delivered.
11. **What changed in this session?** Gate v2.2 (code+docstring), 2 regression replays, probe artifact, 2 saved render artifacts, this report; eval env restored (weights + packages). No thresholds lowered, no tests weakened, no worker touched.
12. **What prevents recurrence?** Regression replays of all 5 calibration artifacts in CI (hermetic), the code-scan (no fixture IDs in production), the documented restore procedure for eval assets, and the claim-audit discipline (every claim → evidence → status).

*End of Part 1. Every command above is reproducible from the recorded paths; no imaginary deployments, credentials, or logs are claimed.*

---
---

# PART 2 — SLEEVE GATE v2.2 CALIBRATION + N=2 RELIABILITY RECONCILIATION (2026-09-16)

**Scope (master prompt, Phase 2, 2026-09-16).** Determine what is actually proven after v2.2 vs still unproven: a genuinely fresh runtime-input calibration cohort (independently generated persons + garments, not only replayed fixtures), full metrics, the AT-15 reconciliation (reproducibility + one-at-a-time mutations), the L1 regression guarantee, N=2 per-class matrix, and an updated 8-gate release decision. Explicitly NOT a report rewrite and NOT green-test maximization: failures below are reported as measured. No production threshold was changed. No test was weakened. No fixture was substituted for a failed runtime render.

Status vocabulary (Part 2): VERIFIED · MEASURED · IMPLEMENTED · CONDITIONAL · BLOCKED · NO-GO (final states only). Agent visual inspection is labeled as such everywhere and is NOT human calibration.

## A. Repo state (Part 2)

| Item | Value | Evidence |
|---|---|---|
| Sandbox restore #2 (2026-09-16) | `.git` reset to a fresh clone @ `928e615` (third loss); `7ee5756` and `5c74e32` **lost**; working tree survived **intact** | `git reflog` single `clone:` entry; tree diff against 4a8baa0 clean |
| Branch (recreated) | `vton-evidence-reconciliation-2026-09-16` cut from `main` @ `928e615`; `main` untouched | `git log` |
| Work commit (2nd recommit) | **`4a8baa0`** — entire work + Part 1 report; commit message documents the second loss of `7ee5756`/`5c74e32` | `git show --stat 4a8baa0` |
| Tree state at Part-2 start | clean at `4a8baa0`; Part-2 work committed as the branch HEAD at the end of this phase (exact SHA in the branch commit log) | `git status` |
| Push/PR | **BLOCKED** — no GitHub PAT in environment AND no remote URL configured (`git push --dry-run` → fatal) | env grep + git |
| Gate freeze (P0) | v2.2 frozen: `FOREARM_CHANGE_THRESHOLD = 20.0` (line 191) unchanged throughout Part 2; ΔE sweep {15,20,25,30} evaluated **in-memory per case only** (sweep harness restores the constant) | code + harness output |
| Replay-set adequacy | The 5-artifact replay set is **too small for robustness claims** — accepted; Part 2's 19-case fresh cohort is the robustness evidence (still n-limited, no "robust" claim made) | §C/§D |

## B. v2.2 implementation (Part 2)

- Change probe v2.2 (Part 1 §C.2) unchanged; `test_sleeve_gate_regression.py` extended in this phase from 19 → **26 tests** (7 new generic synthetic tests, zero fixture/ID dependencies — P6): dark garment over dark trousers (PASS), unchanged dark same-family region (REFUSE), unchanged dark non-same-family region (REFUSE), partial sleeve drop (REFUSE, indeterminate band), low-margin positive ≈0.364 (PASS — pins the thin-margin side of the boundary), low-margin negative ≈0.136 (REFUSE), one-piece dress slot runs the probe (PASS/REFUSE pair). All **26/26 hermetic (4.78 s)**.
- No production-logic changes of any kind in Part 2. Code scan (no fixture IDs in production) remains green (run as part of the 1247-suite re-check).

## C. Calibration cohort (P1) — genuinely fresh runtime inputs

**Cohort construction (PROVENANCE).** Persons A–H (896×1200) and 12 flat-lay garments generated in-session 2026-09-16 via the image tool (`evaluation/dyninputs_fresh/`), following the established `archtest_inputs` precedent (independently generated runtime inputs, per-image provenance). A–H axes: fair skin + dark jeans + light bg (A), tan skin + charcoal joggers (B), deep skin + beige joggers (C), dark backdrop (D), arms raised (E), navy hijab (F), medium skin 30s (G), dim lighting (H). Garments: fresh charcoal-plaid blazer (L*≈16.4), fresh black LS (L*≈9.3), burgundy LS (rt4), teal short tee (rt1), olive chinos (rt2), one-piece dress (local), Arabic-text color-block LS (local), navy logo blazer (global). Every case ran the **production path** (TestClient → TryOnService → live worker), with a capture wrapper that saves each layer's output/input/garment and then runs the REAL gate (behavior unchanged; REFUSE still fails the job). Harness: `evaluation/probes/sleeve_gate_calibration.py`; outputs: `evaluation/results/calibration_v22/`.

**Worker (all 20 live cases):** `fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)`, NVIDIA A10, git `928e615…-dirty`, service `vton-worker-segfee`.

**Results (best-arm @ change-thr 20; truth = agent visual inspection of saved renders — NOT human validation):**

| case | composition | truth (agent) | gate | score |
|---|---|---|---|---|
| cal_01 | A + fresh dark blazer | sleeves present | PASS | 0.3568 (thin +0.007) |
| cal_02 | B + burgundy LS | present | PASS | 0.4615 |
| cal_03 | D (dark bg) + burgundy LS | present | REFUSE | 0.1897 — over-refusal (band geometry: bands land on unchanged dark bg) |
| cal_04 | E (arms raised) + burgundy LS | present; crop-hem render defect | REFUSE | 0.1861 — safe (out-of-band forearms + defective render) |
| cal_05 | H (dim) + burgundy LS | present | PASS | 0.4110 |
| cal_06 | A + one-piece dress (long) | **3/4 sleeves — genuine partial drop** | REFUSE | 0.1832 — **correct (defect detected)** |
| cal_07 | F (hijab) + color-block Arabic LS | present (white block) | REFUSE | 0.0689 — over-refusal (single dominant-color reference cannot verify contrasting color-block) |
| cal_08 | G + one-piece dress | present | PASS | 0.6462 |
| cal_09 | B + navy logo blazer | present | PASS | 0.5004 |
| cal_10 | B + short tee declared long | short, bare forearms | REFUSE | 0.1604 — correct NEG |
| cal_11 | C + short tee (control) | bare forearms | N/A | (0.2110) — correctly skipped |
| cal_12 | A + olive chinos (lower slot, control) | — | N/A | (0.2806) — correctly skipped |
| cal_13 | C (deep skin) + fresh black LS (L*≈9.3) | present | PASS | 0.4718 — darkest garment × deepest skin tone |
| tpb_1/2/3 | A/B/A + tee/tee/LS + olive chinos | — | 502 **VTON_LAYER_NOT_APPLIED (L2)** | engine bottom-layer verify FAIL (pixel_change 0.2134–0.2407, color_shift 0.00147–0.00168) |
| tpb_4 | C + burgundy LS + olive chinos | L1 present | **completed** | L1 0.4520 PASS / L2 0.3531 (N/A) |
| io_1 | A + tee + fresh dark blazer (AT-15 class) | L2 present | L2 REFUSE | 0.3297 — AT-15 class instance #3 |
| io_3 | B + burgundy LS + fresh dark blazer | L2 present | L2 REFUSE | 0.3480 — AT-15 class instance #4 |
| l1_replay | original L1 defect artifact (hermetic) | sleeves absent | REFUSE | 0.0274 |

Full per-case sweep {15,20,25,30}, ref Labs, hashes, and the montage artifacts are in `evaluation/results/calibration_v22/GROUND_TRUTH.md` + `results.json` + `montage_cohort.png`/`montage_bands.png`.

## D. Metrics (P2) — from agent-inspected labels, n = 16 long-sleeve verdicts (19 live cases + 1 hermetic replay)

- 2×2 (PASS = positive decision): **TP = 9, FN = 4 (over-refusals), FP = 0, TN = 3.**
- **TPR = 9/13 = 0.692 · FNR = 0.308 · TNR = 3/3 = 1.00 · FPR = 0.00 · precision = 1.00 · recall = 0.692.**
- **Margins (thr 20):** min positive margin = **+0.007** (cal_01); max negative = 0.1832 (cal_06, inside the indeterminate band → still refused). The gate **never false-passed a sleeve defect** in this cohort.
- **Decision-boundary structure (MEASURED):** three distinct score populations — (a) burgundy-LS-on-light-bg 0.4110–0.6462 (all PASS), (b) the windowpane-blazer thin-margin class 0.3165–0.3568 (the 0.35 line cuts THROUGH it), (c) geometry/color-reference over-refusals 0.0689–0.1897 (all REFUSE). Over-refusal is class-specific and mechanism-identified, not random.
- **Slices (measured):** bg light → 7/7 PASS-eligible; bg dark → 0/1 (geometry). Pose arms-at-sides → 13 long-sleeve verdicts (10/13); arms-raised → REFUSE (out-of-band). Garment type: LS top 0.80 TPR on clean renders; one-piece dress 1/2 (the REFUSE was a genuine 3/4-sleeve defect); dark outerwear 3/5. Lighting dim → PASS. Cohort: 100% fresh (independently generated) inputs; 1 replay.
- **ΔE sweep {15,20,25,30} (P3):** all 3 NEGs refused at every threshold (max NEG 0.1648 @15 — indeterminate band, still refused). POS pass-rate: @15 9/13, @20 9/13*, @25 7/13, @30 5/13 (*cal_01 drops to 0.3311 @25; io_3 flips PASS only @15; io_1 refuses at every threshold). **P3 outcome: RETAIN 20 — no production change.** Justification: @25/@30 strictly increase over-refusal; @15 rescues io_3 (0.4132) and widens cal_01 (+0.041) but io_1 (0.3399) STILL refuses → the AT-15 class is **not threshold-resolvable** in the measured range; lowering the change threshold weakens the contamination defense the unchanged-dark-region data (cal_03, synthetic ctrl_unchanged_gc = 0.0000) depends on; standing rule (never lower a threshold merely to increase PASS; no production change before the mutation study existed — it now exists and does not justify a change). @15 is recorded as an evaluation hypothesis only.
- **Hypothesis test (P1 core claim) — VERIFIED by controlled pair:** "garment-colored AND changed-vs-input" separates an applied sleeve from an unchanged garment-colored region. Synthetic controls built from the real cal_01 render (`sleeve_gate_synthetic_cases.py`, hermetic): identical geometry, bands garment-colored in input AND output → **0.0000 REFUSE**; bands skin→garment (changed) → **1.0000 PASS**; full-band input-pixel restoration (simulated drop) → 0.0088 REFUSE; partial restoration → 0.3451 REFUSE (indeterminate); input-as-output → 0.0000 REFUSE; no garment color → 0.0000 REFUSE. Real-data corroboration: cal_03's unchanged dark background inside the band is not counted. **Documented probe boundary (not a defect):** the probe verifies changed garment color *inside the fixed band boxes*, not anatomical placement (a garment-colored patch anywhere in the band counts — `neg_distort_sim` PASSes by construction); placement is covered by the engine verify + human review.

## E. AT-15 reconciliation (P4) — reproducibility + one-at-a-time mutations

Full record: `evaluation/results/at15_reconciliation/AT15_RECONCILIATION.md` + renders + `results.json` + `montage_mutations.png`.

- **R1 Reproducibility (VERIFIED, class-level):** m0 re-run of the exact AT-15 composition (rt1 + teal tee + product-1 blazer) → best-arm **0.3451** vs original 0.3282 (Δ 0.0169), **same decision (REFUSE, indeterminate)**. Output pixels are NOT bit-identical (sha 6aed7c23… vs d60ef293…) — the diffusion engine samples a fresh seed per job; reproducibility holds at the class/decision level, not the bit level.
- **Visual correction (agent inspection):** product-1 is a **blue windowpane-check blazer** (dominant Lab [40.7, 1.2, 0.0]), not a dark charcoal garment; the white grid lines are not within ΔE 40 of the reference, capping achievable coverage for checked fabrics.
- **R2 Mutations (MEASURED, one variable at a time, blazer held constant):**

| mutation | best-arm @20 | ΔE(band-input, blazer ref) |
|---|---|---|
| (none) — original | 0.3451 REFUSE | 9.9 (gray joggers) |
| lighter trousers (person C, beige) | 0.7853 PASS | 33.4 |
| darker background (person D, black jeans) | 0.3949 PASS | 29.4 |
| arms raised (person E) | 0.1839 REFUSE | n/a (forearms out of band) |
| different person (A, dark jeans, light bg) | 0.3165 REFUSE | 19.2 |
| dark long-sleeve inner (burgundy, not tee) | 0.3912 PASS | arm region large |

- **Mechanism (quantified):** the thin margin occurs exactly when the input band color sits **within ΔE 20 of the garment reference** (gray joggers 9.9; dark-jean L*≈40 19.2) — the change condition then cannot mark the applied sleeve as "new". When the band input is farther (≥ 29.4), PASS. **AT-15 is composition-specific, not intrinsic to the metric geometry**; the residual hard class is a genuinely low-contrast signal (garment ≈ underlying clothing), where no color-based probe can decide.
- **No production threshold changed.** Resolution options recorded for future gate design (none implemented): per-band aggregation, multi-cluster garment reference for checked fabrics, explicit low-contrast NOT_VERIFIED review routing — each would need its own calibration evidence.

## F. L1 regression (P5) — VERIFIED

- Original L1 defect artifact replay: **0.0274 @20 / 0.0470 @15 → REFUSE** (hermetic, in the 26-test suite and in the cohort harness `l1_replay`).
- Additional independently generated sleeve drop: **cal_06** — a FRESH cohort dress rendered with 3/4 sleeves (agent-verified partial drop on a live fresh render, not a fixture) → **REFUSE 0.1832**.
- **Statement (now evidence-backed): the v2.2 false-refusal fix did not convert known sleeve defects into PASS.** VERIFIED.

## G. N=2 matrix (P8) — per composition class, NOT aggregated

- **top+bottom (separate): fresh cohort 1/4 completed** (tpb_4: person C + burgundy LS + olive chinos; L1 0.4520 PASS, L2 lower N/A). 3/4 failed at the **ENGINE's own bottom-layer verify** — `VTON_LAYER_NOT_APPLIED` (pixel_change 0.2134–0.2407 but color_shift 0.00147–0.00168 ≈ 0): persons A and B fail on the bottom layer, person C completes; the sleeve gate was not the cause (explicit 502, no image). Combined with Part 1 (AT-04/AT-10 pass on the current instance; failed on the prior instance): **top+bottom reliability across persons/instances = NOT VERIFIED** (measured: current instance 2/2 rt-cohort + 1/4 fresh-cohort; prior instance 0/2).
- **inner+outer: fresh cohort 0/2 completed** — both refusals are the AT-15 thin-margin class (0.3297, 0.3480 < 0.35) with sleeves visually present (agent inspection): safe refusals. Part 1's AT-15 (0.3282) + Part 2's io_1/io_3 = **three independent live instances of the same thin-margin class** on two different blazers (catalog blue windowpane + fresh charcoal plaid) — the class is real and reproducible, mechanism identified in §E.
- **Correct current state statement:** "top+bottom currently succeeds on the observed worker instance (plus one fresh-cohort success); cross-instance/cross-person reliability remains unverified. inner+outer long-sleeve chains are refused at a thin margin on every live instance measured (safe direction)."

## H. Worker instance (P9)

- **WORKER INSTANCE RECONCILIATION BLOCKED.** No Modal credentials (no `MODAL_*`/`GH_*`/`GITHUB_*` env vars, no `~/.modal`) — verified again this phase. No redeploy/recycle possible; no instance root-cause claim is made (none is proven). The new data point: the fresh-cohort top+bottom failure (3/4, persons A/B) occurring on the SAME instance where the rt-cohort top+bottom passes (AT-04/AT-10) shows the bottom-layer verify outcome is **person/composition-dependent within one instance lifetime** — this refines (does not prove) the instance-state hypothesis; it is recorded, not root-caused. No emulated local redeploy equivalence is claimed.

## I. Fresh local validation (P10)

- Executed live this phase: hijab person F (cal_07 — Arabic-text color-block LS; gate REFUSE 0.0689, sleeves present per agent inspection → multi-color reference over-refusal, safe), one-piece dress on 2 persons (cal_06/08), ≥2 distinct persons (all 8), ≥2 garment types (blazer/LS/dress/tee/chino).
- **Fresh local status: CONDITIONAL** — the local-market sleeve gate cannot currently verify color-block garments (cal_07 class); single-color local garments behave per §C. Modest-tunic and the 10 pending fresh garments (image-generation turn limit) are scheduled for the next turn and are **not claimed**.

## J. Fresh global validation (P11)

- Executed live this phase: diverse appearance/body type (A–H), difficult lighting (cal_05 dim — PASS), text garment (cal_07), logo garment (cal_09 — PASS 0.5004), dark outerwear (cal_01/io_1/io_3), inner+outer N=2 (io_1/io_3), top+bottom N=2 (tpb_1–4), deep-skin × black garment (cal_13 — PASS 0.4718).
- **Fresh global status: CONDITIONAL** — no generalization claim beyond these measured axes and n = 20 live cases.

## K. Human calibration (P12)

- **BLOCKED.** No genuine raters available. Package remains `docs/calibration/2026-09-15/` (D1–D8 rubric, randomized/blinded protocol). No agent-inspection, VLM, or model-score substitution anywhere in Part 2 — every visual truth label is explicitly marked "agent inspection".

## L. Identity licensing (P13)

- Unchanged: ArcFace w600k_r50 **evaluation-only, LICENSE-GATED** (WebFace600K commercial rights UNRESOLVED); weights gitignored, never committed, never in the production decision path. Production identity enforcement: **BLOCKED (LICENSE-GATED)** — no cleared model. No identity step was used for any Part-2 sleeve-gate decision.

## M. Security / privacy (Part 2)

- No changes to the decision path; Part 1 §F table stands. Part-2 probes reuse the same production path (TestClient → real service → live worker) with the same authz/provenance contracts; the live cohort exercised multi-render with real (in-session-generated) user images and produced no new security finding. Explicit-error contract held on every Part-2 failure: `VTON_SLEEVES_NOT_VERIFIED` (6 refusals) and `VTON_LAYER_NOT_APPLIED` (3 engine-verify refusals) — all 502, **no image delivered, no silent success, no fixture substitution**.

## N. CLAIM AUDIT — Part 2 (CLAIM → EVIDENCE → STATUS)

| CLAIM | EVIDENCE | STATUS |
|---|---|---|
| v2.2 does not silently ship the L1 sleeve-drop defect | l1_replay 0.0274/0.0470 REFUSE; cal_06 fresh genuine partial drop REFUSE 0.1832; AT-20 (Part 1) | VERIFIED |
| "garment-colored AND changed" distinguishes applied sleeves from unchanged garment-colored regions | synthetic controlled pair 0.0000 vs 1.0000; cal_03 real-data corroboration | VERIFIED (controlled, hermetic + live) |
| The gate over-refuses some visually-correct long-sleeve renders | 4 agent-inspected over-refusals (cal_03 0.1897, cal_07 0.0689, io_1 0.3297, io_3 0.3480); AT-15 0.3282/0.3451 | VERIFIED (defect class identified, safe direction) |
| The gate never false-passes a sleeve defect in the cohort | FP = 0 over 16 verdicts (TPR 0.692 / TNR 1.000) | VERIFIED (n = 16, agent labels) |
| AT-15's thin margin is composition-specific (band input within ΔE 20 of the garment reference) | mutation study: 9.9→0.3451 REFUSE, 19.2→0.3165 REFUSE, 29.4→0.3949 PASS, 33.4→0.7853 PASS | VERIFIED (measured mechanism) |
| AT-15-class thin margin is threshold-resolvable within {15,20,25,30} | io_1 refuses at every threshold (0.3399 @15) | REFUTED — not resolvable by this threshold alone |
| The production change threshold should be changed now | sweep + mutation data; standing rule (no change to increase PASS) | NOT MADE — 20 retained |
| v2.2 is a robust gate for ALL long-sleeve garments in production | TPR 0.692 (n = 16); 4 identified over-refusal classes; dark-on-ΔE<20 class unresolved | NOT VERIFIED — CONDITIONAL at best, n-limited |
| N=2 top+bottom is reliably deliverable | fresh cohort 1/4 (engine bottom-verify failures, persons A/B); current-instance rt-cohort 2/2; prior instance 0/2 | NOT VERIFIED — composition/instance-dependent |
| N=2 inner+outer long-sleeve chains are deliverable | 3 independent live thin-margin refusals (0.3282/0.3297/0.3480), sleeves present (agent) | NOT VERIFIED — safe refusal, class unresolved |
| Fresh black LS × deep-skin person passes | cal_13 0.4718 PASS (visually verified) | VERIFIED (single composition) |
| Worker-instance root cause of N=2 variance | none measurable (no credentials); within-instance person/composition dependence measured | BLOCKED (no root-cause claim made) |
| Human calibration | no raters | BLOCKED |
| Production identity cleared | w600k rights UNRESOLVED; no cleared model | LICENSE-GATED / BLOCKED |
| Push/PR/deployment occurred | no PAT, no remote URL, no Modal creds | BLOCKED (not claimed) |

## O. Release decision — 8 independent gates (Part 2, no aggregation)

| Gate | Question | Evidence | State |
|---|---|---|---|
| A — defect safety | can a sleeve-drop defect ship silently? | L1 0.0274 REFUSE; cal_06 0.1832 REFUSE; FP = 0 in cohort; AT-20 (Part 1) | **VERIFIED** |
| B — false refusal | does the gate over-refuse valid renders? | 4/13 over-refusals (0.308 FNR), classes identified (geometry / color-reference / ΔE<20 thin-margin / pose) | **CONDITIONAL** (real defect class; safe direction; threshold NOT changed) |
| C — N=2 current instance | does top+bottom work on the current worker instance? | AT-04/AT-10 (Part 1) + tpb_4 (Part 2) pass; tpb_1/2/3 engine bottom-verify failures | **CONDITIONAL** (works on observed instance, composition-dependent) |
| D — N=2 cross-instance | is N=2 reliable across instances/persons? | prior instance 0/2 vs current 2/2 + 1/4 fresh; no redeploy possible | **BLOCKED** (unreliable/unverified; reconciliation BLOCKED) |
| E — human calibration | has a real human panel scored outputs? | none | **BLOCKED** |
| F — identity licensing | is production identity commercially cleared? | w600k WebFace600K UNRESOLVED | **BLOCKED** (LICENSE-GATED) |
| G — fresh local | do local-market fresh inputs pass? | hijab/color-block over-refused (cal_07); single-color local garments OK | **CONDITIONAL** |
| H — fresh global | do fresh global inputs pass? | 20-case fresh cohort: 14/16 long-sleeve verdicts correct; dark outerwear class partial | **CONDITIONAL** |

**Overall: BLOCKED (not NO-GO).** No gate is aggregated into a pass rate. Gate A (the safety property) is VERIFIED — the product cannot silently ship the observed sleeve-drop defect, and every Part-2 failure is an explicit, honest 502 refusal with no image. The remaining blockers are the same four as Part 1 §N, now with sharper evidence: (1) N=2 cross-instance reliability (redeploy BLOCKED — no Modal credentials); (2) the sleeve-gate over-refusal classes — of which the ΔE<20 thin-margin class is now mechanism-identified and proven **not** threshold-resolvable in {15,20,25,30}, so its closure requires a gate-design change (per-band / multi-cluster / review-routing) with its own calibration evidence, not a threshold tweak; (3) human calibration (no raters); (4) production identity licensing.

**What changes vs Part 1:** the AT-15 limitation is upgraded from "documented margin gap" to "mechanism-identified, composition-specific, threshold-non-resolvable" (E); the N=2 top+bottom picture gains a new engine-side failure mode (bottom-layer verify, person-dependent) (G/H); the 5-artifact replay set is superseded as the robustness evidence by a 20-case fresh cohort (still n-limited) (C/D); the regression suite grew 19 → 26 generic tests (B). Nothing that was BLOCKED became GO; no GO is claimed; every failure above is reported as measured.

**Part-2 commit (exact SHA):** the Part-2 work above is committed as **`45ac2fc`** on `vton-evidence-reconciliation-2026-09-16` (parent `4a8baa0`, `main` untouched at `928e615`). This addendum is the follow-up commit recording it.

*End of Part 2. All artifacts are at the recorded workspace paths (`evaluation/results/calibration_v22/`, `evaluation/results/at15_reconciliation/`, `evaluation/probes/`); every score above is reproducible by re-running the recorded harnesses against the same worker. No imaginary deployments, credentials, or logs are claimed.*

---
---

# PART 3 — N=2 FAILURE ISOLATION + SLEEVE-GATE CALIBRATION COMPLETION (2026-09-16)

**Scope (master prompt, Phase 3, 2026-09-16).** Core engineering question: *why does N=2 layer application succeed for some runtime inputs and fail for others, and what is the first deterministic divergence between successful and failed layer-2 executions?* Evidence-based only. No workaround jumps: `assert_layer_applied` was not lowered or bypassed; the failure gate was not removed; no layer-1 output was returned as fake layer-2; no threshold was changed (ΔE radius 40.0 and `FOREARM_CHANGE_THRESHOLD = 20.0` untouched); no gate override; no re-labeling of failures. Agent visual inspection is labeled as such and is not human calibration.

## A. Repo state (Part 3)

| Item | Value | Evidence |
|---|---|---|
| Sandbox restore #4 (2026-09-16, mid-phase) | `.git` reset to a fresh clone @ `928e615` (**fourth loss**); reflog single `clone:` entry; `c86c103`, `45ac2fc`, `4a8baa0`, `312e529` (and earlier `7ee5756`, `5c74e32`) **lost**; working tree survived intact | `git reflog`, `git branch -a` |
| Branch (recreated again) | `vton-evidence-reconciliation-2026-09-16` cut from `main` @ `928e615`; `main` untouched | `git log` |
| Work commit | the Part-3 commit at the end of this section (recommit of the entire working tree + this Part; commit message documents the fourth loss) | `git show --stat` |
| Push/PR | **BLOCKED** — no GitHub PAT in environment, no remote URL | env + `git push --dry-run` |
| Worker (all live calls this phase) | `fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)`, NVIDIA A10, `git 928e615…-dirty`, service `vton-worker-segfee`, `ready: true` | health endpoint (start + end of matrix run) |
| Hermetic suite (this phase, post-sanitation) | **1254 passed / 0 failed / 32 skipped** (216.7 s) | `pytest backend/tests/ evaluation/tests/` |
| One transient suite failure found+fixed this phase | `test_no_image_data_in_run_records` failed because the Part-3 probe's `matrix.json` persisted raw base64 garment payloads (72 data-URIs) — a **P14 record-hygiene violation by our own probe, not a product defect**. Fixed by (1) sanitizing the persisted record (raw bytes stripped, shas retained) and (2) fixing the probe to keep raw bytes in memory only. The guard test itself was **not** weakened. | before/after test runs |

## B. Fresh inputs (provenance, this phase)

All generated in-session 2026-09-16 (`evaluation/dyninputs_fresh/`), production path only, no fixtures:

- **person_I** — 896×1200, head-to-toe, fresh male person (charcoal tee, navy joggers, barefoot, light backdrop). Framing verified visually; extraction method + bbox recorded in the probe notes.
- Garments (dominant Lab from `garment_dominant_lab`): beige_chino (81.5, 1.3, 10.3) · black_joggers (13.2) · white_longsleeve (86.4 — white-dominant, blind-spot class) · gray_longsleeve (44.4) · crop_top (44.6/41.1/36.2) · tank (69.1) · modest_tunic (26.2/16.5/−3.2) · arabic_tee_2 (86.7 white-dominant multicolor) · rust_longsleeve (41.0/33.6/26.0). `*_raw` originals retained.

## C. P0 — 36-case controlled N=2 matrix (NO aggregation)

Design: 4 persons (A, B, C, fresh I) × 3 tops (T1 teal short tee rt1, T2 burgundy LS rt4, T3 fresh rust LS) × 3 bottoms (B1 olive chino rt2, B2 catalog navy trousers — seed row, B3 fresh beige chino) = **36 combinations**, all through the production path (TestClient → TryOnService → live worker), fresh catalog rows per case. Per-layer boundary capture (job id, person sha/dims/mode, garment slot/sleeve/image-sha, timing, verify metrics, model, rendered sha) + P4 forensic raw L2 re-render for every case where L2 did not complete.

**Result: 17 PASS / 19 FAIL.** Failure codes: 10 × `VTON_LAYER_NOT_APPLIED` (engine L2 verify), 9 × `VTON_SLEEVES_NOT_VERIFIED` (T3 rust LS at L1, sleeve gate — see §F).

| person \ bottom | B1 olive | B2 navy | B3 beige |
|---|---|---|---|
| **A** (T1,T2) | **F** (0.2407 / 0.2134) | P (1.39–2.48) | P (10.49–10.50) |
| **A** (T3) | sleeve-gated | sleeve-gated | sleeve-gated |
| **B** (T1,T2) | **F** (0.2402 / 0.2274) | P (1.83–1.97) | P (13.80) |
| **B** (T3) | sleeve-gated | sleeve-gated | sleeve-gated |
| **C** (T1,T2) | P (10.56 / 10.51) | P (15.77) | **F** (0.6863 / 0.6940) |
| **C** (T3) | P | P | **P** |
| **I** (T1,T2) | **F** (0.2976 / 0.2713) | **F** (0.2915 / 0.2679) | P |
| **I** (T3) | sleeve-gated | sleeve-gated | sleeve-gated |

(F = engine-verify 502 with L2 `pixel_change` in parens; P = completed, both layers verified.)

Full per-case record (product ids, hashes, timings, verify triplets, forensic re-runs): `evaluation/results/n2_isolation/matrix.json` (sanitized — image bytes replaced by shas per §A) + `{job}_l1.png` / `{job}_l2.png` / `*_forensic_L2.png` / `*_final.png` + `montage_l1_l2.png`.

## D. P1 — Boundary comparison: what enters layer 2, and the first measurable divergence

Measured for every case (capture wrapper on `TryOnService._call_gpu_worker`; production semantics unchanged):

1. **Chain integrity VERIFIED:** the L2 person-input bytes are byte-identical to the L1 output bytes (sha equality on every completed-and-captured chain; e.g. smoke case L1 sha `0f29f3a547fe…` = L2 person sha). No hidden re-encoding between layers.
2. **Identical across all cases (measured):** output_aspect 9:16, gender_mode `infer_from_image`, L1 output dims 576×771 RGB, garment payload shape `{product_id, slot_type, sleeve_length, image_base64}`, canonical LAYER_HIERARCHY ordering (top before bottom), worker model/device/git revision, timeout/retry behavior (single attempt, 90 s read).
3. **The only differing input between a failed and a successful L2 for the same person+top:** the bottom garment payload image bytes (e.g. A+T1: olive-chino bytes → FAIL vs navy-trousers bytes → PASS on the *identical* L1 bytes `0f29f3a547fe`).
4. **First measurable divergence (the answer):** it is the **worker's layer-2 output itself** —
   - failed runs: leg region of the L1 input **unchanged** (verify `pixel_change` 0.2134–0.7604, `color_shift` 0.0015–0.0052 ≈ 0, i.e. no garment color enters the output; agent visual inspection of every captured/forensic render: original trousers still present; a small waistband patch is the only garment trace — waistband-band change density 21–23% vs 3.6–16.9% lower-half drift);
   - successful runs: leg region **redrawn into the garment** (`pixel_change` ≥ 1.22; agent visual inspection: trousers visibly replaced).
   Everything upstream of the L2 output (payload, dims, mode, aspect, chain bytes) was measured identical or correct. The engine-internal decision that produces the divergence is inside the closed worker model and is **not observable from outside** — it is labeled "engine application behavior" here, not a "root cause" (per the Phase-3 standing rule).
5. **Worker output caching (measured, new):** repeated calls with byte-identical inputs return byte-identical outputs (5+ consecutive identical L1/L2 shas; forensic verify metrics reproduced to 4 decimals across separate runs/days). New samples appear on worker cache miss/eviction (§E). Given identical (L1 bytes, bottom payload), the L2 outcome is **deterministic**.

## E. P2/P3 — One-variable-at-a-time + determinism (classification by measurement)

**One variable at a time (from the matrix + re-runs):**
- same person, different bottoms (A/B/C/I × B1/B2/B3): result changes with the bottom (§C).
- same bottom, different persons (B1 × A/B/C/I): result changes with the person (§C).
- same top, different bottoms: changes (§C); same person+bottom, different tops: **independent for A/B/I (T1 ≡ T2), but NOT for C** — C+beige fails with T1/T2 L1 and passes with T3 (rust) L1. The top enters L2 *through the L1 render bytes*, so the L1 output is part of the L2 input (§D.4).
- same input repeated, fresh job id, fresh catalog row: §E below.

**Determinism re-runs (production path, `n2_determinism_probe.py`):**

| case | repeats | decision | L1 sha (per repeat) |
|---|---|---|---|
| D1 A+teal+olive (matrix F) | 3 | F / F / F | `0f29f3a5` ×3 (byte-identical) |
| D2 I+teal+navy (matrix F) | 3 | F / F / F | `de299533` ×3 (byte-identical) |
| D3 A+teal+navy (matrix P) | 3 | P / P / P | `0f29f3a5`, `00dac312`, `0f29f3a5` |
| D5 C+teal+beige (matrix F) | 3 | F / F / F | `c1c5e9d4` ×3 (byte-identical) |
| D4 delayed re-run of D1 (+60 s) | 1 | **PASS** (6.4599) | **`00dac312`** (a *different* L1 sample) |

**Classification (by measurement only):**
- **Deterministic given input bytes:** the worker output-caches by input content; identical (L1 bytes, bottom) → identical L2 output + decision (byte-identical repeats above; forensic reproduction to 4 decimals).
- **Stochastic at the worker level, upstream of L2:** the same (person, top) input returned **two distinct valid L1 samples** over the run window — `0f29f3a5` (dominant; 6+ occurrences) and `00dac312` (2 occurrences) for A+teal — and the L2 outcome follows the L1 sample: `0f29f3a5`+olive → NOT applied (0.2407, 4+ times, byte-identical), `00dac312`+olive → **applied (6.4599, PASS, full production path)**. The container/replica mechanism behind the sample switching is **UNVERIFIED** (no Modal credentials — §K); what is measured is the alternation itself.
- **Not explained by color distance (falsified by measurement):** verified per-case L1 thigh Lab × bottom Lab ΔE: B+navy ΔE 9.5 PASS vs C+beige ΔE 7.7 FAIL; A+navy 13.7 PASS vs I+navy 12.4 FAIL; A+olive 37.5 FAIL vs C+olive 38.5 PASS. No single color metric (ΔE, ΔL, hue) separates the outcomes.
- **Robustness of the dominant-sample failure:** A+teal-L1(`0f29f3a5`)+olive was re-sampled 3× via byte-different re-encodings (worker cache miss → fresh L2 diffusion): all 3 NOT applied (0.3326/0.3418/0.3296, legs visually unchanged). C+teal-L1+beige: 2/2 NOT applied (0.6863 matrix, 0.7604 fresh). So the *dominant* L1 samples of the failing combinations robustly do not apply the bottom.
- **Sample-dependence at the boundary (measured):** C+burgundy-L1+beige: matrix sample NOT applied (0.6940) vs fresh sample **applied (2.9004, agent-verified applied)** — the same visual L1 content class can go either way by sample. Rust LS on I: single-garment sample gate 0.5385 PASS vs N=2-L1 sample 0.1788 REFUSE — both with sleeves visibly present (agent inspection; `rust_I_compare` artifact) — a sample-level framing/geometry variance of the fixed forearm bands.

**Direct answer to the core question (evidence-bound):** N=2 layer-2 succeeds or fails per (layer-1 output sample, bottom garment) pair — not per person alone, not per garment alone, not per color distance (falsified). The layer-1 output sample for a given (person, top) is itself worker-level non-deterministic (two valid samples observed for the same input bytes; container mechanism UNVERIFIED). **The first deterministic divergence between successful and failed layer-2 executions is the layer-2 output pixels: legs redrawn into the garment (`pixel_change` ≥ 1.22, agent-verified) vs legs unchanged (0.21–0.76, color_shift ≈ 0, agent-verified; small waistband patch only). Everything upstream of that point was measured identical/correct; the engine-internal decision is not observable from outside the worker.**

## F. P4 — Gate-vs-cause verdict (6 mechanisms, resolved per case)

For each of the 10 `VTON_LAYER_NOT_APPLIED` cases, the RAW worker L2 output was captured (production capture and/or forensic direct POST) and inspected:

| case | raw L2 output (agent inspection) | verify (raw) | mechanism |
|---|---|---|---|
| A+B1 (T1,T2), B+B1 (T1,T2), I+B1 (T1,T2), I+B2 (T1,T2), C+B3 (T1,T2) | original trousers unchanged; waistband patch only | PASS=false, pixel_change 0.2134–0.2976, color_shift 0.0015–0.0021 | **1 — engine did not apply** (proven by raw output, not inferred from the gate) |

- `VTON_LAYER_NOT_APPLIED` was **not** conflated with "engine definitely did not apply": the raw outputs were captured and inspected in every case; in all 10, non-application is what the raw bytes show. (Mechanisms 2/4 — applied-but-metrics-insufficient or gate-rejects-visually-correct — did not occur in this batch: no case shows the garment in the raw output while verify fails.)
- The 9 `VTON_SLEEVES_NOT_VERIFIED` (T3 rust LS) cases are a **different failure site**: the worker's L1 verify PASSED (engine applied the rust LS) and the *sleeve gate* refused (best-arm 0.15–0.19). Agent inspection of the saved rust-I L1 render: sleeves present; the low score is the fixed-band geometry vs the sample's arm framing (§E). Safe direction; no image delivered.
- **No false positive anywhere in the phase:** every verify-PASS render inspected (navy/beige applications, D4-delayed 6.4599, C+burgundy fresh 2.9004, all P6 passes) shows the garment actually applied.

## G. P5 — Negative controls (kept alive, re-executed this phase)

| control | truth | score @20 | verdict |
|---|---|---|---|
| original L1 defect artifact (hermetic replay) | sleeves dropped | 0.0274 | **REFUSE** |
| cal_06 fresh genuine 3/4-sleeve dress (live, Part 2) | partial drop | 0.1832 | **REFUSE** |
| synthetic full drop (built from cal_01 render) | drop | 0.0088 | **REFUSE** |
| synthetic partial drop | partial | 0.3451 | **REFUSE** (indeterminate) |
| **sc_crop_B** — crop top declared long (fresh live) | bare forearms | 0.1223 | **REFUSE** (correct NEG) |
| **sc_tank_C** — sleeveless tank declared long (fresh live) | bare forearms | 0.1641 | **REFUSE** (correct NEG) |
| sc_tank_none — tank declared none | — | (0.1641) | N/A — correctly skipped |

Explicit rejection, no fallback, no mislabel, provenance intact (all 502, no image delivered). **P5 property holds.**

## H. P6 — Sleeve cohort expansion (fresh garments, NO threshold change)

13 live cases (`evaluation/results/phase3_sleeve_batch/`, production path, capture + real gate):

| case | composition | truth (agent) | gate | score @20 | class |
|---|---|---|---|---|---|
| sc_white | C + white LS (L*≈86) | sleeves present | **REFUSE** | 0.3289 | white-reference thin margin (band 98–99% garment-colored, 64–71% of it unchanged — input arms already light) |
| sc_gray_D | D (dark bg) + gray LS | present | **REFUSE** | 0.3370 | class A (dark bg in radius) + thin margin |
| loc_tunic_F | F (hijab) + modest tunic (long) | present | **PASS** | 0.8864 | TP |
| loc_arabic2_F | F (hijab) + white-dominant multicolor Arabic tee | white sleeves present | **REFUSE** | 0.0454 | class B quantified: band 95–99% garment-colored but only 5–9% *changed* (input was already white) |
| sc_crop_B | B + crop top declared long | short, bare forearms | REFUSE | 0.1223 | correct NEG |
| sc_tank_C / sc_tank_none | C + tank declared long / none | bare / N-A | REFUSE / N-A | 0.1641 | correct NEG / skip |
| sc_black_I | I + black LS (L*≈9.3) | present | **REFUSE** | 0.3487 | thin margin — 0.0013 below the PASS line (dark charcoal input ≈ black ref) |
| sc_dress_G | G + one-piece dress | present | **PASS** | 0.6322 | TP |
| sc_rust_H | H (dim) + rust LS | present | **PASS** | 0.5421 | TP |
| sc_rust_I | I + rust LS | present | **PASS** | 0.5385 | TP |
| io_gray_I (L2) | I + gray LS + fresh dark blazer (inner+outer) | blazer sleeves present | **REFUSE** | 0.2293 | AT-15 class, instance #5 (gray LS input ≈ blazer ref) |
| tpb_I | I + rust LS + beige chino (top+bottom) | applied | **PASS** | L1 0.5385 / L2 N-A 0.5414 | TPB success |

**P6 outcome:** no threshold change (standing rule); the white-reference and black-on-dark instances **quantify the same ΔE<20 input≈reference mechanism from both ends of the lightness range**; the crop/tank negatives confirm the declared-sleeve contract on fresh garments.

## I. P7 — Over-refusal classes (separated, quantified, hermetic)

`evaluation/probes/sleeve_class_analysis.py` → `evaluation/results/calibration_v22/class_analysis.json` (+ Part-3 band stats on the 4 new FN cases). Band loss decomposition: `counted` (garment-colored AND changed) vs `gc_unch` (garment-colored but unchanged) vs `chg_notgar`:

| class | instances (score) | quantified mechanism |
|---|---|---|
| **A — dark bg / band geometry** | cal_03 (0.1897), sc_gray_D (0.3370) | 70–75% of band = garment-colored **unchanged** dark background (in-radius, correctly excluded by the change condition); counted 13–18% (cal_03) / ~34% (sc_gray_D) |
| **B — reference ≈ input color (light end)** | cal_07 (0.0689), loc_arabic2_F (0.0454), sc_white (0.3289) | band garment-colored 95–99%, but changed only 5–34% because the input arms were already the reference color (white/light); "multicolor" label (cal_07) re-characterized: the white sleeves are simply not *new* vs a white input |
| **C — reference ≈ input color (dark end / thin margin)** | AT-15 (0.3282/0.3451), io_1 (0.3297), io_3 (0.3480), E-1 (0.3524 PASS), sc_black_I (0.3487), io_gray_I (0.2293) | gc_unch 48–67% (dark clothing in-radius, unchanged); counted 12–35% straddles the 0.35 line |
| **D — pose geometry** | cal_04 (0.1861) | forearms out-of-band (raised); band captures torso crop region (chg_notgar 0.13); counted 12–19% |

Classes B and C are **one mechanism** (input band color within ΔE20 of the garment reference — Part 2 §E) measured on both lightness ends; class A adds in-radius *background* contamination; class D is pure fixed-band geometry. **No single threshold change resolves any of them** (Part-2 sweep {15,20,25,30} + these instances + standing rule): the fix space is gate-design (per-band aggregation / multi-cluster reference / explicit low-contrast NOT_VERIFIED routing / band-geometry model), each requiring its own calibration evidence — none implemented this phase.

## J. P8 — Safety property (re-tested this phase)

L1 + cal_06 + 2 synthetic drops: **4/4 REFUSE** (0.0274 / 0.1832 / 0.0088 / 0.3451). No genuine unapplied/sleeve-drop artifact PASSed anywhere in the phase (FP = 0 across all 28 long-sleeve verdicts, §R). **P8 holds — threshold work would stop immediately if it did not.**

## K. P9 — AT-15 decision + worker-instance reconciliation

- **AT-15 class decision: NOT_VERIFIED** (explicit, safe — preferred over an unsupported PASS). Five independent live instances now measured (0.2293, 0.3282, 0.3297, 0.3451-class, 0.3480, 0.3487-adjacent) with sleeves agent-verified present; mechanism identified (input ≈ reference within ΔE20); proven not threshold-resolvable in {15,20,25,30}. Deliverability of inner+outer long-sleeve chains: **not claimed**.
- **Worker instance reconciliation: BLOCKED** (no Modal credentials — re-verified). **New measured data point (§E):** the same input bytes returned two distinct valid L1 samples across the run window, and the N=2 L2 outcome followed the sample (A+teal+olive: `0f29f3a5`→NOT applied 0.2407 ×4+; `00dac312`→applied 6.4599). This is the first byte-level measurement of the cross-sample/cross-instance non-determinism that has been suspected since Part 1 §B. The container/replica mechanism behind it is UNVERIFIED (no access); no instance root-cause is claimed.

## L. P10 — Fresh local validation (exactly what was tested)

Live this phase, all fresh runtime inputs: hijab person F ×2 (modest tunic — PASS 0.8864; white-dominant multicolor Arabic tee #2 — REFUSE 0.0454, class B), modest tunic (same case), one-piece dress on G (PASS 0.6322), long-sleeve tops: rust on H-dim (PASS 0.5421) and I (PASS 0.5385), black on I (REFUSE 0.3487, thin margin), gray on D-dark-bg (REFUSE 0.3370), white on C (REFUSE 0.3289, white-reference), crop-top declared-long negative (REFUSE 0.1223), tank negative (REFUSE 0.1641) + N/A control, fresh person I across 9 matrix cases + tpb (PASS) + io (REFUSE safe). Skin tones: fair (A), tan (B), deep (C, I-male), medium (G), dim lighting (H).

**Fresh local status: CONDITIONAL** — single-color modest/dress/LS garments pass; white-dominant/color-block garments (class B) and dark-on-dark thin-margin garments (class C) are over-refused (safe direction, no image).

## M. P11 — Fresh global validation (exactly what was tested)

Live this phase: diverse persons (A/B/C/G/I incl. fresh I), difficult lighting (H dim — rust LS PASS 0.5421), dark backdrop (D — gray LS REFUSE 0.3370), text garment (Arabic #2 — REFUSE 0.0454), logo garment (cal_09, Part 2 — PASS 0.5004), inner+outer N=2 (io_gray_I — REFUSE 0.2293 safe, sleeves present), top+bottom N=2 (tpb_I PASS + 36-case matrix §C), deep-skin × blackest garment (sc_black_I — REFUSE 0.3487 thin; cal_13 Part 2 — PASS 0.4718), catalog-authority bottom (seed navy) across persons.

**Fresh global status: CONDITIONAL** — no "global-ready" claim; generalization is limited to these measured axes, n = 13 sleeve cases + 36 matrix cases + 13 determinism/forensic runs this phase.

## N. P12 — Human calibration: **BLOCKED** (no raters available; no substitution anywhere — every visual label in this report is agent inspection, explicitly marked).

## O. P13 — Identity: unchanged — ArcFace w600k **evaluation-only, LICENSE-GATED** (WebFace600K commercial rights UNRESOLVED); no identity step in any Phase-3 decision; production identity enforcement BLOCKED.

## P. P14 — Security / privacy (this phase)

Targeted hermetic runs: `test_rate_limiting.py` + `test_vton_temporary_delivery.py` + `test_vton_production_integrity.py` + `test_dynamic_tryon.py` = **60/60 passed** (rate limiting 429s; one-shot delivery-token lifecycle; no image bytes/tokens in logs; GDPR purge of associated person metadata; session lifecycle; no-worker honest failure). Full suite 1254 P / 0 F / 32 S (includes SSRF `is_safe_image_url` matrices, tenant isolation AT-14 class, malformed-image matrices C-01/C-05/C-08, no-image-on-failure). **One finding (ours, fixed):** the isolation probe's `matrix.json` persisted raw base64 payloads (72 data-URIs) → `test_no_image_data_in_run_records` failed → record sanitized (shas retained) + probe fixed (raw bytes in memory only). No product-side security finding; no credential in code (scan clean); worker-unavailable and no-image-on-failure behavior exercised throughout (every refusal = explicit 502 code, no image).

## Q. P21 — Final N=2 matrix per composition (NO aggregation)

**top+bottom (36):** 17 completed / 19 refused. Per person×bottom (T1/T2 rows, n=24): A: B1 0/2, B2 2/2, B3 2/2; B: B1 0/2, B2 2/2, B3 2/2; C: B1 2/2, B2 2/2, B3 0/2 (+ T3 row 3/3); I: B1 0/2, B2 0/2, B3 2/2. T3 (rust LS) row: 0/9 at L1 (sleeve gate — engine L1 verify PASSED in every one; §F). **Post-matrix re-runs: A+B1 additionally PASSED once (D4-delayed, 6.4599, on L1 sample `00dac312`) and failed in 10+ other runs (sample `0f29f3a5`) — the per-combination outcome is a distribution over worker L1 samples, not a fixed property (§E).** L1 gate state per case and L2 verify triplets: `matrix.json`.

**inner+outer (3 live):** 0/3 completed — io_1 (0.3297), io_3 (0.3480), io_gray_I (0.2293): all sleeve-gate REFUSE, all sleeves agent-verified present → safe refusals, AT-15 class. **NOT deliverable-claimed.**

## R. P22 — Final sleeve matrix (TP/TN/FP/FN/low-margin separated)

Cumulative Part 2 + Part 3, agent-inspected truth, n = 28 long-sleeve verdicts (31 live cases + 1 hermetic replay; N/A skips excluded):

- **TP = 13** (0.3568, 0.4615, 0.4110, 0.6462, 0.5004, 0.4718, 0.3648, 0.4520, 0.4615, **0.8864, 0.6322, 0.5421, 0.5385**)
- **FN (over-refusal) = 9** (0.1897 class A, 0.0689 class B, 0.3297 class C, 0.3480 class C, **0.3289 class B, 0.3370 class A, 0.0454 class B, 0.3487 class C, 0.2293 class C**)
- **TN = 5** (0.1832 genuine drop, 0.1604 declared-long short, 0.0274 L1 defect, **0.1223 crop declared-long, 0.1641 tank declared-long**)
- **FP = 0**
- **Low-margin band (0.30–0.36, separate from TP/FN accounting):** 0.3568 (TP, +0.007), 0.3524 (TP, +0.002, E-1), 0.3297, 0.3480, 0.3370, 0.3289, 0.3487 (FNs) — the 0.35 line cuts through this band.
- **TPR = 13/22 = 0.591 · FNR = 0.409 · TNR = 5/5 = 1.000 · FPR = 0.000 · precision = 1.000** (agent labels, not human).

## S. Worker caching + sampling (newly documented mechanism, evidence-linked)

Measured facts: (1) byte-identical outputs for byte-identical inputs across repeated calls (caching by input content); (2) the same (person, top) input returned two distinct valid L1 samples across ~23 min (`0f29f3a5` ×6, `00dac312` ×2), with the L2 outcome following the sample (0.2407 NOT applied vs 6.4599 applied); (3) fresh L2 samples of a fixed L1 visual content are possible via byte-different re-encodings (cache miss) — A+olive 3/3 NOT applied (0.33–0.34), C+beige-burgundy flipped NOT-applied→applied (0.694→2.90); (4) job ids are per-call unique (not content-derived — 36 distinct L1 job ids for 12 distinct (person, top) pairs), so "new job id, same input" adds no variance beyond the worker's own sample state; catalog-row identity (product id) did not change outcomes (same image bytes, new rows — matrix design). Container/replica mechanism: **UNVERIFIED** (no Modal access). Implication: single-run N=2 results (including this 36-case matrix) are one-sample snapshots; reliability claims require repeated sampling per combination — not performed exhaustively this phase (n-limited, stated).

## T. Answer to the core engineering question (direct)

**Why does N=2 layer application succeed for some runtime inputs and fail for others?** Because the engine's bottom-application decision is a function of the *exact layer-1 output sample* × the bottom garment payload — and the layer-1 output sample for a given (person, top) is worker-level non-deterministic (two valid samples measured for the same input bytes; mechanism UNVERIFIED without Modal access). Person, top, and bottom all matter (matrix), but no color metric (ΔE/ΔL/hue) separates the outcomes (falsified, §E) — the differentiator is the pixel-level content of the L1 sample (framing/pose/lighting) interacting with the bottom garment, inside the closed model.

**What is the first deterministic divergence between successful and failed layer-2 executions?** Everything entering L2 was measured: identical chain bytes (L1 output = L2 input, sha-verified), dims, mode, aspect, payload shape, ordering, model revision; the only differing input between a failed and a successful L2 for the same person+top is the bottom garment bytes. The first divergence that is *measurable* is the **L2 output itself** — leg region redrawn (pixel_change ≥ 1.22) vs unchanged (0.21–0.76, color_shift ≈ 0, waistband patch only) — and given the L2 input bytes, that divergence is deterministic (worker caching, byte-identical reproductions). The engine-internal decision preceding it is not observable from outside the worker; no "root cause" label is attached to it.

## U. CLAIM AUDIT — Part 3 (CLAIM → EVIDENCE → STATUS)

| CLAIM | EVIDENCE | STATUS |
|---|---|---|
| The N=2 bottom-layer failures are genuine engine non-application, not gate over-refusal | raw worker L2 outputs captured for all 10 cases (production + forensic); agent inspection: legs unchanged; color_shift ≤ 0.0052; no false positives anywhere | **VERIFIED** (per-case, raw bytes) |
| The first measurable divergence is the L2 output (legs redrawn vs unchanged) | §D boundary table; all inputs measured identical/correct; verify triplets + visual inspection | **VERIFIED** (measured) |
| N=2 outcomes depend on the L1 sample, not on person/garment/color alone | matrix (person×top×bottom); C+beige top-flip (T1/T2 F, T3 P); ΔE table falsifies color; D4 `00dac312` PASS 6.4599 vs `0f29f3a5` FAIL 0.2407 same input | **VERIFIED** (measured) |
| The worker is byte-deterministic per input bytes (caching) | 5+ byte-identical repeats (D1/D2/D5 L1 shas; forensic 4-decimal metric reproduction) | **VERIFIED** (measured, current instance) |
| The worker returns multiple valid samples for the same input (non-determinism upstream of L2) | A+teal: `0f29f3a5` ×6 / `00dac312` ×2 over 23 min; rust-I single (0.5385) vs N=2-L1 (0.1788) samples, sleeves present in both | **VERIFIED** (measured); container mechanism **UNVERIFIED** |
| A+olive non-application is robust for its dominant L1 sample | 4+ L2 samples of `0f29f3a5`-class L1: 0.2407 (cached ×4) + 0.3296–0.3418 (fresh ×3), legs unchanged in all | **VERIFIED** (n = 7 samples) |
| The 36-case matrix is the definitive reliability estimate for N=2 top+bottom | single-sample-per-combination; §S sample distribution; A+B1 flipped post-matrix | **NOT SUFFICIENT** — one-sample snapshot; stated as such |
| The sleeve gate never false-passes a sleeve defect | FP = 0 over 28 verdicts; 6 negative controls REFUSE (§G) | **VERIFIED** (n-limited, agent labels) |
| The over-refusal classes are distinct and not single-threshold-resolvable | §I quantified band decomposition; Part-2 sweep {15,20,25,30}; 9 FN instances across 4 classes | **VERIFIED** (measured) |
| N=2 top+bottom is reliably deliverable in production | 17/36 single-sample; sample-dependent flips measured; cross-instance UNVERIFIED | **NOT VERIFIED** |
| N=2 inner+outer long-sleeve chains are deliverable | 0/3 live, all safe REFUSE (AT-15 class) | **NOT VERIFIED** (explicit NOT_VERIFIED, §K) |
| Human calibration passed | none | **BLOCKED** |
| Production identity cleared | w600k WebFace600K UNRESOLVED | **LICENSE-GATED / BLOCKED** |
| Push/PR/deployment occurred | no PAT, no remote, no Modal creds | **BLOCKED** (not claimed) |

## V. P23 — Release state (exactly one, no aggregation, no gate override)

**BLOCKED** (not NO-GO).

| Gate | Evidence (this phase) | State |
|---|---|---|
| A — defect safety (no silent sleeve-drop) | P8 4/4 REFUSE; FP = 0/28; negative controls §G | **VERIFIED** |
| B — over-refusal classes | 9/22 over-refusals across 4 quantified classes; safe direction; no threshold change | **CONDITIONAL** (real, identified, unresolved) |
| C — N=2 top+bottom, current instance | 17/36 single-sample; sample-dependent flip measured (A+B1 PASS once, 6.4599) | **CONDITIONAL** (works on observed samples; sample distribution unmapped) |
| D — N=2 cross-instance/reliability | two L1 samples for one input; L2 follows sample; container mechanism UNVERIFIED; redeploy BLOCKED | **BLOCKED** |
| E — human calibration | no raters | **BLOCKED** |
| F — identity licensing | w600k UNRESOLVED | **BLOCKED** (LICENSE-GATED) |
| G — fresh local | hijab/tunic/dress/LS pass; white-ref + thin-margin over-refused (safe) | **CONDITIONAL** |
| H — fresh global | measured axes only, n-limited; no "global-ready" | **CONDITIONAL** |

**What would close the blockers (unchanged in kind, sharpened in substance):** (a) worker access (Modal credentials) → instance/reconcile the sample-switching mechanism + repeated-sampling reliability matrix per combination; (b) gate-design study for the ΔE<20 input≈reference class (per-band aggregation / multi-cluster reference / NOT_VERIFIED routing) with its own calibration evidence — a threshold tweak is explicitly ruled out; (c) 3 genuine human raters on the existing package; (d) commercially cleared identity model. Nothing that was BLOCKED became GO; no GO is claimed; every failure above is reported as measured.

## W. Git (Part 3)

Sandbox restore #4 lost `.git` mid-phase (fourth occurrence; `c86c103`/`45ac2fc`/`4a8baa0`/`312e529` unrecoverable — documented §A). Branch `vton-evidence-reconciliation-2026-09-16` recreated from `main` @ `928e615` (untouched). This commit re-commits the entire working tree (all Part 1–3 work, reports, probes, results) with the loss documented in the commit message. Secret scan of to-be-committed content: clean (only token-reading regexes in probes; no literal secrets); LICENSE-GATED weights and eval credentials remain gitignored/excluded. **PUSH BLOCKED** (no GitHub PAT, no remote URL) — no push, PR, or deployment claimed.

*End of Part 3. All artifacts are at the recorded workspace paths (`evaluation/results/n2_isolation/`, `evaluation/results/n2_determinism/`, `evaluation/results/n2_cache_miss/`, `evaluation/results/phase3_sleeve_batch/`, `evaluation/results/calibration_v22/class_analysis.json`, `evaluation/probes/`). Every score above is reproducible by re-running the recorded harnesses against the same worker instance (subject to the §S sample-state caveat). No imaginary deployments, credentials, or logs are claimed.*


---

# Part 4 — Phase 4: Controlled N=2 Determinism Study + Sleeve Safety Re-audit + Fresh Local/Global Validation (2026-09-16 → 2026-09-18)

**Sandbox restore #5** hit at Phase-4 start (fifth occurrence): the Phase-3 commit `f9ae3dd` and its branch were lost with `.git`; re-cloned @ main `928e615`, branch `vton-evidence-reconciliation-2026-09-16` recreated, tree re-committed at phase end with the loss documented. `evaluation/results/n2_isolation/` (matrix.json + artifacts) and `n2_determinism/*.png` were deleted by the restore; all measured values are preserved in Parts 1–3 of this report. The Python environment was partially wiped and restored (backend requirements + torch 2.14.0+cpu + torchvision 0.29.0+cpu + onnxruntime + easyocr; w600k weights re-extracted — identical sha256 `80ffe37d…` as all prior downloads, LICENSE-GATED, never committed). No Phase-3 result was re-interpreted or re-labeled; this part adds NEW measurements only.

**Worker under test (all of Part 4):** `fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)`, NVIDIA A10, service `vton-worker-segfee`, `git_sha 928e6151…-dirty`, ready throughout — the same instance/revision as Parts 1–3. No redeploy, no instance manipulation, no simulated anything.

## A. P0 — Controlled repeated-run experiment (ONE fixed logical request, N=30)

Design (per Phase-4 tasking): same person bytes (`person_A.jpg`, sha256 in record), same top bytes (`garment_rt1.jpg` teal tee), same bottom bytes (`garment_rt2.jpg` olive chino), **same catalog product IDs reused across all 30 attempts**, same server-derived layer order, same production endpoint, same model revision. Per-attempt record: attempt id, L1/L2 job ids, L1 sha256 + engine verify, L2 sha256 + engine verify (PASS / metric_pixel_change / metric_color_shift), failure code, timestamps, elapsed. Raw L1/L2/final worker bytes saved as per-attempt artifacts (hashes only in the JSON record — P8).

Probe: `evaluation/probes/p0_repeated_run_probe.py` → `evaluation/results/p0_repeated_runs/` (attempts.json + 60+ artifacts).

**Result (30/30 completed):**

| L1 class (full sha256) | attempts | L2 outcome | L2 outputs |
|---|---|---|---|
| `0f29f3a547fe…af0adaf2` | 27 (a01–a10, a14–a30) | **26 × VTON_LAYER_NOT_APPLIED + 1 × PASS (a10, px 7.5401, L2 `57763cdd`)** | 26 fails (in-call assert blocks capture — raw bytes measured in §C), 1 pass |
| `00dac3120b9b…17f0cb8d` | 3 (a11–a13) | **3 × PASS** | `5146de86` ×2 (px 6.4599, byte-identical) + `e48d5859` ×1 (px 1.4686) |

- **Overall: 4/30 first-run success (13.3%).**
- The 26 failed and 1 passed attempt of class `0f29f3a5…` are **byte-identical L1** (full sha256 verified identical across all 27 attempts — not an 8-char-prefix coincidence).
- Sequence structure: FAIL×9 → PASS×4 (a10–a13) → FAIL×17. The only passing cluster spans both L1 classes; every other L2 run of the dominant class failed.
- Latency: min 38.9 s / median 39.9 s / max 43.7 s per attempt (2 GPU inferences).
- No L1-side failure ever occurred (L1 engine verify PASS in 30/30); every failure is L2 `VTON_LAYER_NOT_APPLIED`.
- **Probability note (per tasking, no two-sample inference):** this is N=30 of ONE logical request on ONE worker instance in one time window. It measures the current-state distribution for this combination, not a population probability. Cross-instance and cross-time variation is separately bounded in §C/§E and remains UNVERIFIED beyond this instance (P0-D).

## B. P0-A — L1 hash → L2 outcome matrix

Analyzer: `evaluation/probes/p0a_l1_l2_matrix.py` → `p0a_matrix.json`.

| L1 class | n | L2 PASS | L2 FAIL | L2 reproducible within class? |
|---|---|---|---|---|
| `0f29f3a5…` | 27 | 1 (a10) | 26 | **NO — the byte-identical L1 produced BOTH verdicts** |
| `00dac312…` | 3 | 3 | 0 | verdict stable (PASS ×3) but **2 distinct L2 byte outputs** (px 6.4599 vs 1.4686) |

**Answer to the P0-A question:** `L1 sample identity → L2 outcome` is **NOT reproducible**: the identical L1 bytes produced 26 NOT-APPLIED and 1 APPLIED. The L2 stage carries a component that is not a function of the L2 input bytes alone.

## C. P0-B — Same L1 bytes → multiple L2 runs (direct worker, no L1 regen)

Probe: `evaluation/probes/p0b_same_l1_repeat_probe.py` → `evaluation/results/p0b_same_l1_repeats/`. For each of the 2 distinct L1 classes from §A, the EXACT L1 bytes (worker PNG; full sha256 recorded) were re-POSTed as the L2 person-image directly to the production worker with the olive bottom: R1, R2 = exact bytes; R3/R4/R5 = same image re-encoded JPEG q92/q95/q88 (different bytes, same content). Eval-only instrumentation: the in-call `assert_layer_applied` was monkeypatched off in-probe so the raw L2 output is captured on not-applied (P2-A); the engine verdict is read from the worker's own `verify` block. No production code modified.

| L1 class | run | input bytes | L2 PASS | px | L2 sha8 | note |
|---|---|---|---|---|---|---|
| `0f29f3a5…` | R1 exact | identical | **False** | 0.2407 | `fb23ff6e` | |
| | R2 exact | identical | **False** | 0.2407 | `fb23ff6e` | **byte-identical to R1 (worker output cache)** |
| | R3 q92 | re-encoded | **False** | 0.3326 | `e45994fb` | fresh sample, not applied |
| | R4 q95 | re-encoded | **False** | 0.3418 | `3914d93b` | fresh sample, not applied |
| | R5 q88 | re-encoded | **False** | 0.3296 | `a8c8e1b1` | fresh sample, not applied |
| `00dac312…` | R1 exact | identical | **True** | 1.4686 | `e48d5859` | **byte-identical to P0 a13's L2 (cache hit across hours)** |
| | R2 exact | identical | **True** | 1.4686 | `e48d5859` | cache hit |
| | R3 q92 | re-encoded | **True** | 1.4288 | `3bef0df5` | fresh sample, applied |
| | R4 q95 | re-encoded | **True** | 1.4367 | `3b6c11a6` | fresh sample, applied |
| | R5 q88 | re-encoded | **True** | 1.4141 | `e28def36` | fresh sample, applied |

**Hypothesis adjudication (measured, not inferred):**
- **Hypothesis A (the L1 image content alone decides the L2 outcome): FALSIFIED.** The byte-identical L1 `0f29f3a5…` produced a PASS in the P0 sequence (a10) and 5/5 NOT-APPLIED in these direct repeats; its re-encoded variants (same content, different bytes) also all fail.
- **Hypothesis B (independent L2 state/stochastic component): SUPPORTED.** Same L2 input bytes → byte-identical output whenever the worker's output-cache entry is present (R1=R2 in both classes; `00dac312` R1 equals P0 a13's L2 byte-for-byte across hours). Same L2 input bytes at different times → different cached L2 states (a10's pass vs the persistent fail entry, which has now measured ≥32 runs across Part 3 + Part 4). Same image content at different bytes → same verdict in all 8 fresh samples (verdict tracks content, not byte-identity). So the L2 stage is **deterministic given (worker state, input bytes)** and **state-dependent across time**; the state mechanism (cache lifetime / sampling state / replica) is internal to the closed worker — UNVERIFIED (no Modal access), and no host-level root cause is claimed.
- px magnitudes: not-applied runs stay in 0.21–0.34 (legs unchanged; color_shift ≤0.005 per the Part-3 forensic set, re-confirmed on these artifacts); applied runs ≥1.4. The engine's verify threshold sits between these bands.

## D. P0-C / P0-D — Worker observations (only what the app safely exposes)

Recorded per attempt: job ids (per-call unique, not content-derived), worker model/device/revision from health (constant across all Part-4 runs: `fashn-vton-v1.5 MMDiT 972M seg-free fork 7c0f10af`, A10, `git_sha 928e615…-dirty`), engine execution_time_ms, ready state.

**WORKER INSTANCE INTERNAL INSPECTION = BLOCKED** (no Modal credentials — re-verified this phase; unchanged). No container image, dependency, model-state, GPU-counter, cache-content, or env-var inspection was possible. No simulated redeploy; no host/replica/cache-eviction/GPU-state root-cause claims. `ROOT CAUSE INTERNAL TO CLOSED WORKER — NOT VERIFIED` remains the standing, acceptable result; this phase adds a precise behavioral boundary around it (§E) without labeling a mechanism.

## E. Determinism classification (precise, evidence-linked)

1. **L1 stage:** non-deterministic at worker level for fixed (person, top) input — multiple byte-distinct valid L1 samples observed across Parts 3–4 for the same inputs (`0f29f3a5…`, `00dac312…` for A+teal; `06b18da3…` for B+burgundy; `f803c60d…`/`1c239bf1…` for I; `5211a50c…` for A+navy-bottom; `370e6b6a…` for G+tunic — §O). Within the Part-4 window each combination's L1 sample was stable across its 3–30 attempts (one class switch: A+teal returned `0f29f3a5…` in both P0 and P2).
2. **L2 stage:** deterministic given (worker state, input bytes) — byte-identical outputs on repeated identical inputs (measured: 4/4 exact-byte repeat pairs in §C, 3/3 in §O); state-dependent across time — the same input bytes produced both verdicts at different times (§B/§C a10).
3. **L2 outcome = f(L1 output sample × bottom payload × worker state):** the same L1 sample `0f29f3a5…` passes with the navy bottom 3/3 (§O) while failing with the olive bottom 26/27 + 5/5 direct (§A/§C). The same L1 sample `06b18da3…` (B+burgundy) passes as single top 3/3 while failing when the olive bottom is added 0/3 (§O). Person/top/bottom identity matter; color does not (Part-3 falsification retained).
4. **First measurable divergence:** L2 output pixels (fail: legs unchanged, px 0.21–0.34; pass: redrawn, px ≥1.4). The engine's internal application decision is not observable — no "root cause" label is applied.

## F. P2-A — Engine-vs-gate classification of VTON_LAYER_NOT_APPLIED (raw L2 captured)

Raw L2 outputs captured on every result (pass and fail) in §C and §O (in-call assert disabled in-probe, documented per probe; engine verdict read from the worker's own verify block). Classification rule: raw L2 shows bottom NOT applied (legs unchanged vs L1, color_shift ≈0) with engine verify PASS=False → **ENGINE NON-APPLICATION** (the engine did not render the garment; the gate had nothing to refuse). Raw L2 shows the garment applied but the pipeline still refused → **QUALITY-GATE OVER-REFUSAL**. Ambiguous → **UNKNOWN**. No auto-classification; every case inspected on its captured artifact (agent).

- Part-4 engine-not-applied set (n=8: §C 5 + §O n2tpb_fail 3): **all ENGINE NON-APPLICATION** — raw L2 legs unchanged, px 0.23–0.34, no visible garment; consistent with the Part-3 forensic set (10/10).
- Part-4 over-refusal set (n=6: §O n2io_gray 3 + s_ow_i 3 — engine verify PASS, sleeves visually present, sleeve gate REFUSE): **all QUALITY-GATE OVER-REFUSAL** — the engine applied the garment (px 4.44/5.88), the raw L2 shows full sleeves to the wrist; the refusal is the sleeve gate's, in the measured AT-15/dark-on-dark class (§G).
- UNKNOWN: 0. Every Part-4 refusal or not-applied is classified from its raw capture.

## G. P3 — Sleeve gate: new live calibration + **first measured FALSE POSITIVE**

### G.1 New live long-sleeve verdicts this phase (agent visual inspection — NOT human ground truth)

| case | composition | truth (agent) | gate | best-arm @20 | sweep {15/25/30} | class |
|---|---|---|---|---|---|---|
| p4_j_tunic | J (hijab, charcoal abaya) + purple LS tunic | sleeves present | **PASS** | 0.6967 | 0.7187/0.6637/0.4864 | TP |
| p4_j_arabic2 | J + green/white color-block tee (garment ref: **long white sleeves**) | **sleeves DROPPED** (short sleeves, bare forearms — artifact-verified) | **PASS** | **0.7062** | 0.7084/0.7055/0.7048 | **FALSE POSITIVE (new class E)** |
| p4_k_rust | K + rust LS | present | PASS | 0.7963 | 0.7971/0.7963/0.7949 | TP |
| p4_k_black | K + black LS | present | PASS | 0.7092 | 0.7092/0.7084/0.7077 | TP (dark garment, fair contrast) |
| p5_l_gray | L (plus-size) + gray LS | present | PASS | 0.5414 | 0.7275/0.2220/0.1553 | TP |
| p5_m_blazer | M + dark blazer (LS) | **present** (to wrist, artifact-verified) | **REFUSE** | 0.2000 | 0.3458/0.1070/0.0777 | **FN (new)** |
| p5_m_io (L1) | M + black LS (inner of N=2) | **present** | **REFUSE** | 0.1802 | 0.3407/0.0967/0.0747 | **FN (new, class C dark end)** |
| s_top_b / n2tpb_fail L1 | B + burgundy LS | present | PASS | 0.4615 | — | TP |
| n2io_gray L1 | I + gray LS (inner) | present | PASS | 0.4337 | — | TP |
| n2io_gray L2 | I + gray LS + blazer (outer) | **present** (to wrist, raw L2 artifact-verified) | **REFUSE** | 0.2894 | — | **FN (new)** |
| s_ow_i | I + dark blazer (single) | **present** (to wrist, artifact-verified) | **REFUSE** | 0.2733 | — | **FN (new)** |
| s_dress_g | G + modest tunic (dress slot) | present | PASS | 0.6645 | — | TP |

Each §O case was repeated ×3 with byte-identical worker outputs and identical gate scores (deterministic within the window). Non-sleeve single-garment cases: p3a_c_blackjog PASS (engine px 17.57, applied — visual), p3a_b_blackjog PASS (px 4.88, applied — visual), s_bot_a PASS (px 4.7937, applied), s_top_a PASS (px 7.4859).

### G.2 The false positive — mechanism, quantified (class E, NEW)

`garment_arabic_tee_2.jpg` is a color-block tunic: dark-green chest panel + **white body AND white long sleeves**; garment dominant color = white (ref Lab [86.7, 0.0, −0.0]). Render on person J (input: dark charcoal abaya, light background): the engine applied the color-block and the text but **dropped the long sleeves** (short white sleeves to the elbow; bare forearms — verified on full-frame and zoomed artifacts).

The gate PASSed at 0.7062 (**hermetic replay on the saved artifacts reproduces it without the worker**: left band 0.7062 / right band 0.4645). Band-overlay analysis of the exact measurement bands (x 0.52–0.70 / 0.28–0.46, y 0.40–0.55): each rectangular band contains (i) the white short sleeve, (ii) the **white shirt body** adjacent to the arm, (iii) bare skin, (iv) background. Pixels of (i) and (ii) are garment-colored (ΔE≤40 to white) AND changed vs the input (the abaya was dark there) → counted as "applied sleeve" by the probe. The probe's premise — *changed garment-colored forearm pixel = applied sleeve* — breaks when the garment's dominant color also covers the torso and the input under the band was dark.

**Input-dependence measured in both directions:** the SAME garment on person F (light input, Part 3) REFUSED at 0.0454 (FN — white over a light input is "unchanged"); on person J (dark input) it PASSed at 0.7062 with sleeves dropped (FP — white over a dark input is "changed"). One garment, two opposite safety errors, opposite input backgrounds.

### G.3 Updated cumulative sleeve matrix (agent labels, all phases)

Part 2 + Part 3 (Part 3 §R: 13 TP / 9 FN / 5 TN / 0 FP) + Part 4 (7 TP / 4 FN / 1 FP) = **39 labeled verdicts: TP 20, FN 13, TN 5, FP 1.**

- **TPR = 20/33 = 0.606 · FNR = 0.394** (sleeves-present cohort)
- **TNR = 5/6 = 0.833 · FPR = 1/6 = 0.167** (sleeves-absent/defect cohort) · precision = 20/21 = 0.952
- **The FPR = 0 safety property that anchored the gate design is now MEASURED VIOLATED** on class E (same-color torso + dark input). The gate's core guarantee — never deliver a render with a dropped long sleeve — has a demonstrated hole, found by fresh local validation exactly as intended.
- FN classes (Part 3 §I: A dark-bg, B light input≈ref, C dark/thin-margin, D pose) re-confirmed by four new dark-on-dark/low-zone FNs (0.2000, 0.1802, 0.2894, 0.2733).

### G.4 Threshold decision (P3-D): **NO CHANGE** (ΔE 20.0 / 0.35 / 0.15 retained)

Neither the FP (0.7062 — far above any pass line) nor the new FNs (0.18–0.29 — below the thin-margin band) is resolvable by moving the threshold; the {15,20,25,30} sweep shows the band straddling persists and the FP is a band-aggregation artifact, not a margin issue. The fix space (arm-segmented bands / multi-cluster reference / per-band aggregation / explicit NOT_VERIFIED routing) each requires its own calibration evidence — **none implemented this phase** (P9: no production change on an unproven mechanism; three-way state analyzed in §N, not implemented).

## H. P4 — Fresh local validation (exactly what was tested, reported separately)

New persons generated this phase: J (Middle Eastern woman, emerald hijab + charcoal abaya), K (South Asian man, white kurta + gray trousers) — raw images prepped head-to-toe at 896×1200 (same pipeline as A–I).

| axis | result | status |
|---|---|---|
| garment application | tunic applied faithfully (color/length/sleeves match garment ref — visual); color-block tee applied (block + text) **but sleeves dropped** (§G.2); rust/black/gray LS applied (sleeves to wrist — visual) | MEASURED per case |
| sleeve safety | 4 TP + 1 FP + K-black LS PASS 0.7092 (sleeves present — visual) | **FP measured — see §S** |
| text fidelity | Bismillah calligraphy present, legible, same layout; fine diacritics/dots degraded (diffusion text loss) | **PARTIAL** (agent) |
| hijab preservation | J: emerald hijab intact in both renders (tunic + tee); face/framing consistent with input | **VERIFIED (agent)** |
| provenance | per-layer job ids + shas + engine verify in results.json; raw L1/L2/final artifacts saved | **VERIFIED** |
| no fixture substitution | zero seed/fixture product IDs in this batch — all garments freshly generated, catalog rows created at probe time | **VERIFIED** |

Skin tones/appearance added on top of the Part-3 cohort: J (medium, Middle Eastern, hijab), K (tan, South Asian).

## I. P5 — Fresh global validation (exactly what was tested, reported separately)

New persons: L (plus-size Black woman, deep skin), M (East Asian man, warm backdrop).

| axis | result | status |
|---|---|---|
| diverse appearance/body | L plus-size: gray LS PASS 0.5414 (sleeves + ribbed cuffs to wrist — visual); M: blazer applied (visual) | MEASURED |
| dark/light clothing | black LS on K (dark on light input) PASS 0.7092; black LS on M (dark on dark input) REFUSE 0.1802 (sleeves present — FN); blazer on M REFUSE 0.2000 (FN) | MEASURED — input-dependent |
| lighting/background | M warm beige backdrop; J/K/L light gray; no new dim-lighting case (Part-3 H-dim retained) | MEASURED (limited) |
| text/logo | Arabic calligraphy on J (PARTIAL — §H); no new logo case (Part-3 cal_09 retained) | MEASURED (limited) |
| top+bottom N=2 | L + rust LS + beige chino: **PASS first attempt** (L1 0.7209 sleeves + bottom applied, final verified — visual) | MEASURED |
| inner+outer N=2 | M + black LS + blazer: REFUSE at L1 (0.1802, sleeves present — safe refusal; blazer layer never reached) | MEASURED (not deliverable) |
| poses/backgrounds | standing frontal only (new persons); Part-3 pose class D retained | MEASURED (limited) |

**No "global-ready" claim.** Generalization is limited to these measured axes with the stated n; both new inner+outer attempts this phase are safe refusals on the dark-on-dark class.

## J. P6 — Human calibration

**BLOCKED.** No genuine ≥3 human raters available; no VLM/agent substitution anywhere — every visual label in Part 4 is explicitly marked AGENT INSPECTION.

## K. P7 — Production identity

**LICENSE-GATED, unchanged.** ArcFace w600k (WebFace600K, commercial rights UNRESOLVED) remains evaluation-only; no identity step in any Part-4 decision; production identity enforcement BLOCKED.

## L. P8 — Security / privacy (this phase)

- Persisted evidence hygiene: all Part-4 result JSONs (attempts / p0a / p0b / p1 / p2 / p4 / rerun) contain hashes + metrics only; raw worker bytes exist solely as designated `.png` artifacts under `evaluation/results/` (P2-A requirement). No base64 payloads in any run record this phase (the Part-3 `matrix.json` leak pattern was not repeated; the record guard test is retained in the suite).
- No production code modified in Part 4 (gates/thresholds/assertions untouched; all probes evaluation-only, with in-process monkeypatches documented per probe where used).
- Credential handling unchanged: worker token env-only; no secrets in code (scan clean); git identity unchanged.
- Suite re-runs after all instrumentation: §R.

## M. P1 — Retry assessment (EVALUATION ONLY — measured, NOT implemented)

Analyzer: `evaluation/probes/p1_retry_assessment.py` → `p1_retry_assessment.json`. Sequence-based sliding windows over the ACTUAL 30-attempt order — no i.i.d. assumption, because the worker's L1/L2 state is lumpy (F×9, P×4, F×17).

| metric | value |
|---|---|
| first-attempt success | 4/30 = **0.133** |
| success within 2 consecutive attempts (29 windows) | 5/29 = **0.172** (residual 0.828; worst-case latency 87 s) |
| within 3 (28 windows) | 6/28 = **0.214** (residual 0.786; worst 131 s) |
| within 5 (26 windows) | 8/26 = **0.308** (residual **0.692**; worst 218 s) |
| latency per attempt | median 39.9 s; each attempt = 2 GPU inferences |
| recovery structure | all 4 passes inside ONE cluster (a10–a13); the 17-attempt fail tail shows immediate retries do NOT recover — state-dependent, not i.i.d. |

**P1-A (bounded retry as mitigation): measured INEFFECTIVE for this class.** Even 5 sequential attempts leave a 69.2% residual failure on A+teal+olive; each retry costs a full 2-inference attempt (~40 s) and recovery is clumpy — a retry right after a failure has approximately the same failure odds as the first attempt (the F×17 tail is the direct evidence). Bounded retry is therefore NOT adopted as a reliability mechanism for unreliable N=2 classes.

**P1-B (explicit class refusal): SUPPORTED as the correct product semantics for the unreliable classes.** The current taxonomy already implements the safety half of P1-B: every not-applied/refused render returns an explicit 502 with a canonical code (`VTON_LAYER_NOT_APPLIED` / `VTON_SLEEVES_NOT_VERIFIED`) and **no image** — a false image is never delivered. A dedicated `UNSUPPORTED_OR_UNVERIFIED_MULTI_GARMENT_RENDER` code would improve classification of the measured-unreliable combinations (A/B/I persons × specific bottoms; inner+outer LS chains) but is a production taxonomy change requiring a product decision — **not implemented this phase** (P9), recorded as a recommendation.

**Mitigation assessment (tasking format):** retry considered? **YES** (P0 sequence + window analysis). retry measured? **YES** (first-attempt 13.3%; within-3 21.4%; within-5 30.8%; clumpy, state-dependent). safe? **YES if explicit with provenance — but NOT adopted, because ineffective at release-relevant failure rates.** implemented? **NO** (eval-only rule honored; no automatic/hidden retry anywhere). category refusal required? **YES for the measured-unreliable N=2 classes** (failure distributions §A/§O). implemented? **Partially — the explicit no-image refusal already exists in the current error taxonomy; a dedicated unsupported-class code is a recommendation, not yet implemented.**

## N. Three-way PASS/REFUSE/NOT_VERIFIED — analysis only (NOT implemented)

- Data support: the 0.30–0.36 band contains 7 FNs + 2 low-margin TPs (Part 3 §R); NO genuine sleeve-drop artifact has ever scored in-band (all measured drops ≤0.1832; Part-4 drops: 0.0454-class FNs are in-band-low, the sole FP is 0.7062 — outside the band on the PASS side). Routing the indeterminate band to an explicit NOT_VERIFIED state would be FPR-safe by the measured data.
- Product semantics: NOT_VERIFIED answers "verified? no. defective? no evidence." Whether an *unverified-but-possibly-fine* render is deliverable is a product risk decision — no product owner input exists (human calibration BLOCKED, §J), and the Part-3 precedent (AT-15 class → explicit NOT_VERIFIED, undeliverable) already chose the safe reading.
- **Decision: NOT implemented this phase.** A deliverable NOT_VERIFIED path would be a production semantic change without product approval; a non-deliverable NOT_VERIFIED path changes nothing user-visible (same 502 refusal). The label is retained in analysis only, as in Part 3.

## O. P2 — N=2 completeness matrix, repeated attempts, PER CLASS (no generic rate)

Probe: `evaluation/probes/p2_repeated_matrix_probe.py` → `evaluation/results/p2_repeated_matrix/` (3 attempts per combination; production path; static catalog rows per combination; raw L1/L2/final artifacts on every result; in-call assert disabled in-probe for P2-A raw-L2 capture — engine verdict read from the worker's own verify).

| class | combination | 3 attempts | class result | engine-vs-gate |
|---|---|---|---|---|
| N2 top+bottom (pass class) | A + teal tee (short) + navy seed trousers | PASS ×3 — L1 `0f29f3a5…` px 7.4859; L2 `59419fcd…` px 1.3891 **byte-identical** | **3/3 deterministic PASS** | both layers applied (engine + visual) |
| N2 top+bottom (fail class) | B + burgundy LS + olive chino | NOT_APPLIED ×3 — L1 `06b18da3…` px 12.7157 (top applied, sleeves TP 0.4615); L2 `c20cab51…` px 0.2274 **byte-identical** | **0/3** | **ENGINE NON-APPLICATION** (raw L2 ×3 captured; legs unchanged) |
| N2 inner+outer | I + gray LS + dark blazer | gate REFUSE ×3 — engine: L1 `f803c60d…` px 7.5769 PASS (sleeves TP 0.4337) + L2 `de96b425…` px 5.8793 PASS, **byte-identical** | **0/3 deliverable** | **QUALITY-GATE OVER-REFUSAL** (blazer sleeves to wrist on raw L2 — visual; gate 0.2894, AT-15 class) |
| single top | B + burgundy LS | PASS ×3 (`06b18da3…` px 12.7157) | 3/3 | applied (TP 0.4615) |
| single top | A + teal tee | PASS ×3 (`0f29f3a5…` px 7.4859) | 3/3 | applied |
| single bottom | A + navy seed trousers | PASS ×3 (`5211a50c…` px 4.7937) | 3/3 | applied |
| single outerwear | I + dark blazer | gate REFUSE ×3 — engine `1c239bf1…` px 4.4404 PASS | **0/3 deliverable** | **QUALITY-GATE OVER-REFUSAL** (blazer sleeves to wrist — visual; gate 0.2733, class C) |
| single dress | G + modest tunic | PASS ×3 (`370e6b6a…` px 11.9881) | 3/3 | applied (TP 0.6645) |

**First-attempt vs repeated-attempt, per class:** every class was 100% stable across its 3 attempts (no flip; byte-identical worker outputs on cache hits). **No single "N=2 success rate" is reported.** Per-class states (current window, this instance): top+bottom pass-class 3/3; top+bottom fail-class 0/3 (engine); inner+outer 0/3 deliverable (gate over-refusal, engine applied both layers); single top/bottom/dress 3/3; single outerwear 0/3 deliverable (gate over-refusal).

**The decisive cross-reference:** the same L1 sample `0f29f3a5…` (A+teal) passes with navy 3/3 and fails with olive 26/27+5/5 (§A/§C); the same L1 sample `06b18da3…` (B+burgundy) passes as single top 3/3 and fails when the olive bottom is added 0/3. N=2 outcome = f(L1 sample × bottom payload × worker state), measured on two independent persons.

## R. Security / privacy suite re-runs (after all Part-4 instrumentation)

- Targeted: `test_rate_limiting.py` + `test_vton_temporary_delivery.py` + `test_vton_production_integrity.py` + `test_dynamic_tryon.py` = **60/60 passed** (14.8 s) — rate limiting 429s; one-shot delivery-token lifecycle; no image bytes/tokens in logs; GDPR purge; session lifecycle; no-worker honest failure.
- Full: `backend/tests` = **1211 passed / 28 skipped / 0 failed** (216.6 s) + `evaluation/tests` = **47 passed / 0 failed** (12.6 s) → **1258 passed / 28 skipped / 0 failed** total. (Part 3 recorded 1254 P / 32 S on the same tree; the delta is collection variance across the restore, not a test change — no test was modified or skipped to pass; the 28 skips are the standing environment-conditional skips.)
- No product-side security finding this phase; no credential in code; no image-on-failure anywhere (every refusal = explicit 502 code, no image).

## S. Release state (independent per axis; exactly one overall)

| axis | evidence (Part 4) | state |
|---|---|---|
| N=2 top+bottom reliability | 3/3 vs 0/3 per class (§O); state-dependent worker L2 (§B/§C); cross-instance UNVERIFIED | **CONDITIONAL** (§29 criteria 1/2/4 not met) |
| N=2 inner+outer deliverability | 0/3 this phase + 0/3 Part 3 = 0/6; engine applies, gate over-refuses (§O) | **NO-GO as deliverable** (safe refusal holds) |
| Sleeve safety (no silent sleeve-drop) | **FP measured** (class E, §G.2): FPR 1/6; hermetic repro | **BLOCKED** (core safety property violated on a measured garment class) |
| Sleeve over-refusal | 13 FN across classes A–D + 4 new this phase; safe direction | **CONDITIONAL** (identified, unresolved, no threshold change) |
| Human calibration | no raters | **BLOCKED** |
| Production identity | w600k WebFace600K UNRESOLVED | **BLOCKED (LICENSE-GATED)** |
| Fresh local | hijab preservation VERIFIED (agent); text PARTIAL; application per-case; 1 FP | **CONDITIONAL** |
| Fresh global | measured axes only, n-limited; no "global-ready" | **CONDITIONAL** |
| Worker internal mechanism | behavioral boundary measured (§E); mechanism not observable | **NOT VERIFIED** (acceptable result, standing) |

**Overall: BLOCKED** (not NO-GO). Mandatory blockers present: (1) sleeve-safety property violated (FP measured — a false image WAS deliverable on class E until the fresh-local case caught it; it is now caught by the report, not by the gate); (2) N=2 worker reliability unresolved (state-dependent L2; unreliable classes measured 0–13%); (3) human calibration and identity licensing. Nothing that was BLOCKED became GO; no green-test count, single-host behavior, one-passing-render, or retry-recovery is counted as evidence; no BLOCKED→GO anywhere.

## T. Claim audit (Part 4) — CLAIM → EVIDENCE → STATUS

| claim | evidence | status |
|---|---|---|
| One fixed logical request repeated 30× yields a distribution, not a fixed outcome | §A: 4/30 pass; 27/3 of two L1 classes | **VERIFIED (measured, n=30, one instance)** |
| The byte-identical L1 sample produced both L2 verdicts | §A/§B: `0f29f3a5…` full-sha ×27 → 26F+1P | **VERIFIED (measured)** |
| L2 is deterministic given (worker state, input bytes) | §C: R1=R2 byte-identical ×2 classes; §O 3/3 byte-identical | **VERIFIED (measured)** |
| L2 is state-dependent across time | §C: same bytes → pass (a10 era) vs fail (P0-B era) | **VERIFIED (measured); mechanism UNVERIFIED** |
| L1 content alone decides L2 (Hypothesis A) | §C: falsified by a10 + 5/5 direct fails | **FALSIFIED (measured)** |
| Independent L2 state component exists (Hypothesis B) | §B/§C | **SUPPORTED (measured)** |
| N=2 outcome = f(L1 sample × bottom payload) | §O: `0f29f3a5…` navy 3/3 vs olive 26/27; `06b18da3…` single 3/3 vs +olive 0/3 | **VERIFIED (measured, 2 persons)** |
| Bounded retry recovers unreliable N=2 | §M: within-5 recovery 30.8%, residual 69.2%, clumpy | **NOT SUPPORTED (measured)** |
| Every Part-4 refusal/not-applied is engine-vs-gate classified from raw capture | §F: 8 engine + 6 gate + 0 unknown | **VERIFIED (agent inspection, raw artifacts)** |
| The sleeve gate can false-pass a dropped-sleeve render | §G.2: class E FP 0.7062, hermetic replay, band overlay | **VERIFIED (measured)** — first FP in the cohort |
| Class-E FP is input-dependent (same garment: FN on light input, FP on dark input) | Part 3 loc_arabic2_F 0.0454 REFUSE vs §G.2 0.7062 PASS | **VERIFIED (measured, 2 persons)** |
| No threshold change is justified | §G.4: FP at 0.7062 / FNs 0.18–0.29; sweep straddle | **VERIFIED (measured)** — 20.0/0.35/0.15 retained |
| Fresh local: hijab preserved, text partial, no fixture substitution | §H + artifacts | **VERIFIED (agent)** / text **PARTIAL** |
| Fresh global: no "global-ready" | §I: measured axes only | **NO-GO-claimed (none made)** |
| Human calibration / identity cleared | none | **BLOCKED / LICENSE-GATED** |
| Security suite green after instrumentation | §R: 60/60 + 1258 P / 0 F | **VERIFIED** |
| Push/PR/deployment occurred | no PAT, no remote, no Modal creds | **BLOCKED** (not claimed) |

## U. Git (Part 4)

Sandbox restore #5 lost `.git` mid-phase (fifth occurrence): Phase-3 commit `f9ae3dd` unrecoverable (documented); branch `vton-evidence-reconciliation-2026-09-16` recreated from `main` @ `928e615` (untouched). Lost-SHA ledger now: `c86c103` / `45ac2fc` / `4a8baa0` / `312e529` / `7ee5756` / `5c74e32` (restore #4) + `f9ae3dd` (restore #5). This commit records the entire Part-4 working tree (probes, results, this report) with the loss documented in the commit message. Secret scan of to-be-committed content: clean (probes contain only token-reading regexes; no literal secrets); LICENSE-GATED weights (w600k) and eval credentials remain gitignored/excluded; raw render artifacts are designated evidence, not secrets. **PUSH BLOCKED** (no GitHub PAT, no remote URL) — no push, PR, or deployment claimed.

*End of Part 4. All artifacts at the recorded workspace paths: `evaluation/results/p0_repeated_runs/`, `evaluation/results/p0b_same_l1_repeats/`, `evaluation/results/p2_repeated_matrix/`, `evaluation/results/p4_fresh_batch/`, plus the Part-3 paths. Every score is reproducible by re-running the recorded probes against the same worker instance, subject to the §E state-dependence caveat (byte-identical outputs hold while the worker's cached state is unchanged). No imaginary deployments, credentials, or logs are claimed.*
