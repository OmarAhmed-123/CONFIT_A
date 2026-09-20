

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
