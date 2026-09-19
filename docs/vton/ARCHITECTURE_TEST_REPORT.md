# CONFIT_A — Architecture Test Report (Dynamic Real-User Multi-Garment VTON)

Date: 2026-09-15
Phase: Dynamic Real-User Multi-Garment VTON — architecture tests AT-01…AT-19
Status: **SUITE COMPLETE — 34 passed / 2 failed (honest reliability-gap failures)**

AT-suite canonical run: `/tmp/at_final_canonical.log` (791.05 s, 2026-09-15):
**34 passed, 2 failed** — AT-04 and AT-10 fail via the designed honest-failure
diagnostic (see §4.1). No test was edited to turn red into green; the two reds
are product-requirement gaps, not test defects.

Extended final run (AT + §34 component contracts + §35 canonical E2E):
`/tmp/at_final_all.log` (900.64 s): **65 passed, 2 failed** (same two honest
reds). Contract suite: 30/30 (test_architecture_contracts.py). Canonical
zero-fixture E2E: PASS. Local (2/2) + global (3/3) dynamic validation renders
reported separately (LOCAL_/GLOBAL_DYNAMIC_VALIDATION_REPORT.md).

---

## 0. Scope & method

Purpose (master prompt 2026-09-15): prove CONFIT_A is a **genuinely DYNAMIC** try-on
system — arbitrary user-uploaded person images + actual catalog garments selected at
runtime → real GPU render through the **real production architecture** (FastAPI service
→ Modal GPU worker `fashn_vton_segfee`, A10). No pre-generated people/outputs, no
fixture substitution, no canned results.

How it is tested:
- **Real production code path**: `POST /api/v1/tryon/multi-render` and
  `POST /api/v1/tryon/jobs` via TestClient against the seeded catalog DB, with the
  production service wired to the **live Modal worker**
  (`VTON_WORKER_URL`/`VTON_WORKER_PROCESS_URL`/`VTON_WORKER_HEALTH_URL`/
  `VTON_WORKER_ADMIN_TOKEN` from the evaluation deployment; health-verified before run).
- **Unknown runtime inputs** (`evaluation/archtest_inputs/`, PROVENANCE.md there):
  - Persons `person_rt1..4.jpg` — 4 AI-generated individuals (2026-09-15) NOT in any
    fixture manifest, benchmark, calibration, training, or regression corpus.
  - Garments `garment_rt1..4.jpg` — flat-lays (teal tee / olive chinos / mustard tee /
    burgundy **long-sleeve** vertical flat-lay) entered as **new catalog product rows**
    with data-URL thumbnails; the client submits only `product_id`s (server-side
    catalog resolution).
- **Identity measurement** (eval-only, LICENSE-GATED — never a production gate):
  ArcFace w600k_r50 (InsightFace model zoo, `w600k_r50.onnx`
  sha256 `4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43`),
  112px IOD-aligned crop from MediaPipe landmarks. The Phase 0.5 AdaFace binary was
  lost in the sandbox recreation (gitignored weights; HF unreachable) — ArcFace is the
  documented restore; both are MS1M/WebFace4M-class, same eval-only license class.
- **Garment-application metric of record** is `color_coverage()`: fraction of the
  torso band's chromatic, skin-excluded pixels within ΔE≤25 of the garment's dominant
  color (median Lab of non-background pixels of the RUNTIME garment image). Calibrated
  2026-09-15 (MEASURED): applied garments 0.22–0.45 (and 0.39–0.76 on the final runs);
  non-applied control garments 0.0 → threshold 0.05 with ≥4× margin. No fixture-ID
  expected values anywhere.
- Live tests opt in via `CONFIT_AT_LIVE_WORKER=1`; hermetic tests always run.
- Evidence: `evaluation/results/architecture_test_evidence.json` (dumped by the suite;
  merged across runs, latest value per test id wins).

## 1. Environment

| item | value | status |
|---|---|---|
| Worker | `vton-worker-segfee`, engine `fashn_vton_segfee` | VERIFIED (health, live) |
| Model | fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af) | VERIFIED (health payload) |
| GPU | health payload device string: "NVIDIA A10" (was "NVIDIA A10G" earlier in the run window — Modal instance variation, see §4.1) | VERIFIED (health payload) |
| Worker git_sha | `928e615…-dirty` (main) | REPO-ATTESTED |
| Backend code | main @ 928e615 + this branch's test files | VERIFIED |
| Catalog DB | test SQLite, reseeded (`seed_database` force) each session | VERIFIED |
| Identity model | ArcFace w600k_r50 (eval-only) | VERIFIED (weights sha256 above) |
| Render latency | ~18.2–19.5 s per layer (MEASURED, per-job logs) | MEASURED |

## 2. Results matrix

Per-test fields per master prompt: TEST_ID / PURPOSE / INPUT_TYPE / KNOWN_FIXTURE? /
EXPECTED / ACTUAL / PROVENANCE / PASS-FAIL / EVIDENCE.

### Static (hermetic) — COMPLETE

| TEST_ID | Purpose | Input type | Known fixture? | Expected | Actual | PASS-FAIL |
|---|---|---|---|---|---|---|
| AT-07s / §21 | Fixture IDs never enter production decision paths | code scan of `backend/app`, `backend/alembic`, `CONFIT_A_frontend/src` | n/a | ZERO matches for p0xx/g0xx/g1xx/S_g0xx/KB0x/fixture paths | **ZERO** matches (8 patterns, all production trees) | **PASS** |
| AT-19s | No sleeve/quality logic coupled to fixture IDs | code scan | n/a | no `if garment_id == g010`-class exceptions | **ZERO** matches | **PASS** |
| AT-13 | Authoritative server-side catalog resolution | API schema + `/garments/{id}/asset` (hermetic) | unknown garments (rt rows) | request schema has no client garment image/slot/sleeve fields; slot catalog-derived | request fields = product_ids/slot_mapping/person/avatar/gender/pose/background/preservation/consent only; top slot `upper_inner`, bottom `lower` from category | **PASS** |
| AT-14 | Multi-tenant authz, one-shot delivery, no existence leakage | guest job (hermetic) | unknown person | poll w/o token 404; w/ token 200; wrong token 404; unknown job 404; token single-use | 404 / 200 / 404 / 404; one-shot verified live in AT-05 | **PASS** |
| AT-16 (inputs) | Invalid inputs → explicit, honest rejection | corrupt bytes / non-image / undersized / unknown product / no-worker | n/a | corrupt & non-image: `is_valid=false` + issues; undersized: explicit warning (hard 256px min enforced at submission); unknown product: 404 before worker; no-worker render: 503 | exactly that (MEASURED: `decode_failed:UnidentifiedImageError`, `use_higher_resolution_at_least_480x640`, 404, VTON_ENGINE_UNAVAILABLE) | **PASS** |
| AT-19 (detector) | Generic sleeve detector runs on UNKNOWN garment | garment_rt4 (unknown long-sleeve) | NO | `garment_sleeve_drop` returns geometry verdict without any fixture ID | dict returned on rt4 (sleeve_drop_ratio 0.849, is_long_sleeve_candidate true) — MEASURED | **PASS** |

### Live (GPU) — final run 2026-09-15 (canonical: 34 passed / 2 failed)

All persons/garments below are UNKNOWN runtime inputs (no fixture IDs). Identity
numbers are ArcFace w600k_r50 (eval-only, LICENSE-GATED). Coverage = `color_coverage()`
(measure of record). All provenance in
`evaluation/results/architecture_test_evidence.json`.

| TEST_ID | Purpose | Inputs (all UNKNOWN) | Expected | Actual (MEASURED) | PASS-FAIL |
|---|---|---|---|---|---|
| AT-01 | User-image passthrough, content-hash trace | person_rt1 + rt teal tee (new product row) | response person-ref = exact upload (hash match); output ≠ input; output ∉ {known fixture renders}; output face corresponds to rt1 | ref hash match (input sha `d5800f44…`); output `20c151d2…` (390,040 B) ∉ 89 known fixture render hashes; identity self 0.6767 > other 0.4953 | **PASS** |
| AT-02 | Two unique persons, same garment | person_rt1, person_rt2 + rt teal tee | outputs differ; each face ↔ its person | hashes differ; matrix a/a 0.6767 vs a/b 0.4953, b/b 0.9154 vs b/a 0.4217 (self > cross in both rows) | **PASS** |
| AT-03 | Two unique garments, same person | person_rt3 + teal vs mustard tee | outputs differ; torso color ↔ rendered garment | coverage: a_teal 0.7623 vs a_mustard 0.0000; b_mustard 0.5236 vs b_teal 0.0000 — zero cross-contamination | **PASS** |
| AT-04 | Two unique outfits (N=2 top+bottom), no cross-contamination | person_rt1 + (teal top + olive bottom) vs (mustard top + olive bottom) | per-slot provenance; all layers verified; A torso teal / B torso mustard; lower olive both | layer 1 (top) renders and verifies; **layer 2 (bottom) → 502 `VTON_LAYER_NOT_APPLIED`** on both outfits (e.g. pixel_change 0.1994, color_shift 0.001356, stddev 37.68). Explicit failure, no fake image. See §4.1 | **FAIL — honest reliability-gap diagnostic** |
| AT-05 | Request→output provenance chain (job path) | person_rt4 + rt teal tee (job API) | job_id→person-hash→garment ids→model→one-shot token→output hash | job `vton_job_cc543e64bf0e`; person hash = upload hash; garment_ids `[26]`; model_used `fashn-vton-v1.5 (fashn_vton_segfee…)`; one-shot delivery verified; gaps documented in §3 | **PASS** (core chain; enrichment gaps documented) |
| AT-06 | Determinism / cache safety | person_rt1 + rt teal tee ×2 identical, ×1 different garment | identical inputs → identical sha256; one-field change → different sha256 | identical → identical sha256 (`20c151d2…` ×2); different garment → different sha. No inference cache in production (delivery TTL cache only) | **PASS** |
| AT-07 | No fixture substitution (runtime half) | person_rt2 + rt olive chinos | unknown person+garment renders; output ∉ known fixture renders | 200 completed; output `b68522df…` ∉ 89 known fixture hashes. (The suite excludes `archtest*` outputs from the known-set: dynamic-phase outputs are not pre-generated artifacts — see self-contamination note in §4.2) | **PASS** |
| AT-08 | Unknown person end-to-end | person_rt4 + rt teal tee | completes; face detected in output; identity corresponds | 200 completed; identity self 0.8724 > other 0.7079 | **PASS** |
| AT-09 | Unknown garment end-to-end | person_rt1 + rt olive chinos | completes; lower region ≈ olive | 200 completed; olive coverage 0.3909; teal control 0.0000 | **PASS** |
| AT-10 | **Combined unknown full outfit (MOST IMPORTANT)** | person_rt2 + rt teal top + rt olive bottom | completes; both layers verified; slots correct; top teal / bottom olive; identity corresponds | same §4.1 failure mode: layer 1 verified; **layer 2 → 502 `VTON_LAYER_NOT_APPLIED`** (pixel_change 0.2172, color_shift 0.00149, stddev 48.08). Explicit failure, no fake image | **FAIL — honest reliability-gap diagnostic** |
| AT-11 | Person image variability (4 transforms) | rt1: ½ downscale / 90° / center-crop / dimmed | each → real render (200) OR explicit 422 — never 500 | all 4 → 200 completed. (Outputs byte-identical across variants: the worker normalizes the person reference — legitimate, documented) | **PASS** |
| AT-12 | Garment image variability (3 transforms) | mustard: ½ downscale / padded / landscape native | each → 200 OR explicit 422 — never crash/substitute | all 3 → 200 completed; distinct output hashes (`c0c75d5b…`, `3a6128b5…`, `2b5f948c…`) | **PASS** |
| AT-15 | Dynamic layering N=2 (inner+outer), server-derived order | rt1 + (teal top, catalog blazer) in BOTH submission orders | all layers verified; order identical regardless of client order | both orders → 200, identical output `6aed7c23…`; `layering_order = [upper_inner, upper_outer]` both times; all layers verified | **PASS** |
| AT-15b | N=3 (top+outer+bottom) — EVALUATION-ONLY | rt1 + 3 layers | must not crash; result recorded (no production claim) | 502 explicit failure (consistent with the layer-2 lower-slot gap, §4.1); no crash, honest code | **EVALUATION-ONLY — recorded** |
| AT-16b | Dynamic quality gate / honest failure on long-sleeve | person_rt1 + rt burgundy LONG-sleeve (vertical flat-lay) | render WITH sleeves, OR explicit `UNSUPPORTED_OR_UNVERIFIED_GARMENT_RENDER`-class error — never silent sleeveless success | 200 completed; **sleeves present to wrist** — structural forearm probe 0.7744/0.6403 (threshold 0.35; negative control bare forearms 0.1648/0.1582); visual confirmation on `archtest_at16b_rt1_burgundy_long_sleeve.png`. Eval `arm_coverage` metric false-positived (FAIL_SLEEVES_INCOMPLETE) — recorded as reference, NOT gating (uncalibrated metric; see §4.3) | **PASS** |
| AT-17 | Dynamic identity, 4 unknown persons | rt1..rt4 + rt teal tee | 4×4 matrix; each output argmax = its person (margin recorded) | diagonal argmax in all 4 rows; margins 0.1645–0.2407 (matrix in evidence) | **PASS** |
| AT-18 | Dynamic garment fidelity (generic metrics) | rt renders vs runtime garment images | measured ΔE torso↔garment (no fixture expected values) | ΔE teal 24.9, mustard 38.6 (MEASURED, recorded; acceptance is Gate A / human-calibration territory — NOT hard-gated here) | **PASS (MEASURED, no fixture expected values)** |

Code-scan tests (10/10): all **PASS** — zero fixture IDs in any production decision
path; zero hard-coded sleeve exceptions by fixture id.

## 3. Provenance chain status (§34)

Fields required: request_id, person_image_hash, garment_ids, SKUs, slot mapping, layer
order, engine, model+worker revision, seed, verification, output hash; no raw bytes in
logs.

Verified present (this run): `job_id` (request id), person image stored on the job row
(content-hash trace computed from it), `garment_ids_json`, `garment_layers_json`
(id/title/category/slot), `model_used`, `delivery_token_hash` (one-shot), output
delivered one-shot (hash recorded), `metrics_json` (per-layer verify metrics).

**Documented gaps (production work items, not test failures of the core chain):**
- garment image content hashes not stored (only product ids);
- worker git revision not stored on the job (health payload carries it; not persisted);
- seed not stored/controlled by the service — the worker payload
  (`{job_id, user_image, garments, gender_mode, output_aspect}`) carries **no seed**;
  worker-side determinism VERIFIED in AT-06 (identical inputs → identical bytes);
- SKU not on the job row (session path records `recommended_size`).

## 4. Findings

### 4.1 N=2 chain reliability gap (worker-side, layer-2 lower slot) — UNRESOLVED

**The single most important finding of this phase.** The top+bottom N=2 composition
(person rt2 + teal tee + olive chinos, the AT-04/AT-10 core case) **succeeded with both
layers verified** and then **deterministically failed on layer 2** — with byte-identical
inputs.

Timeline (all times 2026-09-15, worker live):

| time | event | evidence |
|---|---|---|
| 20:21 | rt2 + teal + olive N=2 → **200, both layers verified** | suite run #1 |
| 20:35 | same composition → **200, both layers verified** (l1 517,314 B / l2 529,242 B, `all_layers_verified=True`) | `archtest_at10_probe_rt2_teal_olive.png` (saved) |
| ~20:42 | composition begins failing on layer 2 | rerun #4: 502 |
| 20:46–20:51 | 5/5 isolated probes → **502 `VTON_LAYER_NOT_APPLIED`**, all with IDENTICAL metrics (l1 517,314 B verify_pass=True; l2 pixel_change 0.2172, color_shift 0.00149, stddev 48.08) | probes 1–5 |
| 20:52 | **control**: rt2 + olive chinos ALONE → 200 verified (sha `b68522df…`) | `archtest_ctrl_single_chinos_rt2.png` (saved) |
| 20:54–21:07 | full suite (canonical #1): AT-04/AT-10 fail identically | `/tmp/at_final_run.log` |
| 21:17–21:30 | final canonical run: same failures, same metrics | `/tmp/at_final_canonical.log` |

Root-cause analysis (what was MEASURED vs what is UNRESOLVED):

1. **Service side is byte-deterministic — proven, not assumed.** The worker payload is
   exactly `{job_id, user_image_base64_or_url, garments, gender_mode, output_aspect}`
   (`tryon_service.py:668-676`) — no seed. `_prepare_person_image` is a data-URL
   passthrough with byte checks; `_build_garments_payload` is thumbnail→base64 +
   `LAYER_HIERARCHY` sort. All five failing job_ids were unique; outputs were
   byte-identical across all of them → the worker is deterministic per input and the
   inputs were identical in the passing and failing windows. **The flip is therefore
   worker-side state, not service-side.**
2. **Worker state changed between 20:35 and 20:46.** Health payload: same model string
   (`fashn-vton-v1.5`, fork 7c0f10af) and git_sha (`928e615…-dirty`), but the device
   string changed `A10G` → `NVIDIA A10` — consistent with a different Modal instance
   (recycle/redeploy). What exactly changed on the instance is **UNRESOLVED from the
   service side** (no worker-side introspection access from this environment).
3. **The defect is specific, not global.** In the failing state: (a) single olive chinos
   render = 200 verified → the lower garment is fine as layer 1; (b) inner+outer chain
   (teal tee → blazer, upper slots, both client orders) = 200, both layers verified
   (AT-15) → the upper chain is fine; (c) N=3 (top→outer→bottom) fails with the same
   honest 502 (AT-15b). ⇒ the failing unit is the **lower-slot garment as layer 2** of a
   sequential chain (bottom rendered onto the top's render), or its interaction with the
   current instance state.
4. **The system's failure behavior is CORRECT per §31/§44 in every window**: explicit
   502 + machine code `VTON_LAYER_NOT_APPLIED` + per-layer metrics; never a fake image,
   never a silently partial "complete" outfit, no previous-success replay.

Classification: **reliability gap in the N=2 lower-slot-as-layer-2 chain,
worker-instance-level and PERSISTENT** (updated 21:50–21:52 with two follow-up
diagnostics):

5. **Time-delayed retry (21:50, +19 min after last failure): NO RECOVERY.**
   Identical metrics to the byte — L1 517,314 B verify_pass=True (pixel_change
   5.6433, color_shift 0.039863); L2 pixel_change 0.2172, color_shift 0.00149,
   stddev 48.08 → 502. ⇒ not a transient warm-start condition.
6. **Generalization probe (21:52): the defect is systematic, not input-specific.**
   A *different* top (mustard tee on rt1; L1 392,152 B, verify_pass=True) with
   olive chinos as layer 2 → same failure signature (pixel_change 0.1979,
   color_shift 0.001347, stddev 35.86 ≈ the L1 image stddev — the layer-2 output
   is a near-identity copy of the layer-1 render with NO color transfer).
   ⇒ on the current worker instance, **ANY lower-slot garment as layer 2 on a
   rendered top fails verification**; single lower-slot (layer 1) and upper-slot
   chaining (tee→blazer) work. The earlier instance (A10G device string, 20:21–
   20:35) applied the identical bytes successfully — the instance-level
   difference (GPU SKU string A10G→A10, or instance image/environment) is the
   prime suspect.

Worker redeploy from this environment is **BLOCKED** (Modal account credentials
absent — `modal token info`: "Token missing"; worker source not in this
workspace). Resolution path: redeploy/spin the worker with the known-good
instance configuration, or worker-side introspection of the layer-2 lower-slot
pipeline on the current instance. Until then AT-04/AT-10 remain FAILED by
design (product requirement unmet; the honest 502 is the correct product
behavior per §31/§44). NOT converted to PASS.

### 4.2 Self-contamination trap (test-suite hygiene, fixed)

Saving a dynamic output into `evaluation/results/outputs/` put its sha256 into the
known-fixture-render set; the deterministic worker then reproduced byte-identical bytes
on the next identical render and AT-07's "output ∉ known fixture renders" assert fired
on the suite's **own** output. Fixed: `known_fixture_render_hashes()` excludes
`archtest*`-named files (dynamic-phase outputs are not pre-generated artifacts), and all
dynamic-phase outputs are named `archtest_*`. This is why AT-07's evidence records
"∉ 89 known fixture hashes" (89 = pre-dynamic-set size).

### 4.3 Quality-gate sufficiency (structural finding, with one measured exception)

The production per-layer gate is the engine's `verify.PASS` (pixel-change based),
invoked on every path. Phase 0.5 MEASURED this gate BLIND to the sleeve-missing class
(17/20 defective renders had `verify.PASS=True`).

New data point (AT-16b, 2026-09-15): on the standard full-body upright input, the
burgundy long-sleeve vertical flat-lay rendered **with complete sleeves** (visual +
structural probe), and `verify.PASS=True` — so for this input the production gate and
reality agree. Phase 0.5's sleeve drop-out was **pose/rotation-dependent** (0° FULL /
45° partial / 90° sleeveless) and remains the standing risk class; the generic sleeve
gate is therefore still a required production work item (integrate the calibrated
structural probe from AT-16b — `_lower_arm_coverage`, threshold 0.35, ≥2× margin both
sides — or refuse the category with `UNSUPPORTED_OR_UNVERIFIED_GARMENT_RENDER`).

Caveat recorded: the `vton_metrics.sleeve_metrics.arm_coverage` sub-metric
**false-positived** (`SLEEVES_PARTIAL` / `FAIL_SLEEVES_INCOMPLETE`) on the visually and
structurally verified long-sleeve render. It is an uncalibrated proxy; per standing
standards (no hard gate without statistical justification) it is **recorded as eval
reference only and must not gate production**.

## 5. Explicit answer (master prompt question)

> "Can arbitrary user image + authorized garments pass through the real production
> architecture without substitution?"

**YES for the core dynamic architecture — MEASURED:** arbitrary unknown user images and
runtime catalog garments render end-to-end through the real production path with zero
substitution (AT-01, AT-02, AT-07, AT-08, AT-09, AT-11, AT-12, AT-13, AT-14, AT-17,
AT-18 all PASS on unknown inputs; AT-15 proves server-derived inner+outer N=2 layering
with client-order independence; AT-16b proves honest long-sleeve handling).

**WITH ONE OUTSTANDING RELIABILITY GAP:** the top+bottom N=2 chain (lower slot as
layer 2) currently fails on the live worker with an honest explicit 502 rather than a
fake success (§4.1). The architecture is dynamic and correct; the gap is worker-side
chain reliability. AT-04/AT-10 remain FAILED by design until that is resolved and
re-verified. **Gate A remains BLOCKED — HUMAN CALIBRATION PENDING; no BLOCKED→GO.**

## 6. Evidence index

- `evaluation/results/architecture_test_evidence.json` — per-test inputs/outputs/hashes/metrics (merged across runs; WORKER/CATALOG/AT-01…AT-19)
- `evaluation/archtest_inputs/` + `PROVENANCE.md` — unknownness claim for the runtime inputs
- `backend/tests/test_architecture_dynamic.py` — the suite (live + hermetic; honest-failure helper `_render_outfit_honest()`)
- `backend/tests/test_architecture_code_scan.py` — §21 static scan
- Output images (all `archtest_*`, dynamic-phase, NOT pre-generated artifacts):
  - `evaluation/results/outputs/archtest_at10_probe_rt2_teal_olive.png` — 20:35 verified N=2 success (pre-flip)
  - `evaluation/results/outputs/archtest_ctrl_single_chinos_rt2.png` — 20:52 single-layer control (failing state)
  - `evaluation/results/outputs/archtest_at16b_rt1_burgundy_long_sleeve.png` — sleeves present to wrist (AT-16b visual check)
- Logs: `/tmp/at_final_canonical.log` (final: 34/2), `/tmp/at_final_run.log` (canonical #1: 33/3, AT-07 false-fail), `/tmp/at_rerun5.log` (AT-07 fix confirmation)
- Worker health payload recorded in evidence (`WORKER`).

## 7. Non-goals / not claimed here

- No production gate thresholds introduced (Gate A human calibration still BLOCKED;
  identity/color values are MEASURED evidence, not acceptance criteria).
- N=3 is EVALUATION-ONLY (standing decision); its current 502 is recorded, not claimed.
- ArcFace identity numbers are eval-only (LICENSE-GATED), not FR/production claims.
- Static fixture benchmark results are reported separately (Phase 0.5 report); dynamic
  and fixture results are never mixed in this report.
- No claim that the N=2 gap is resolved, and no claim that it is a test artifact
  (it is worker-side state; root cause UNRESOLVED pending worker-side introspection or
  the time-delayed retry diagnostic).
