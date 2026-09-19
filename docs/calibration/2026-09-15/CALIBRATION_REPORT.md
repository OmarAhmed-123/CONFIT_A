# CALIBRATION REPORT — metric validation against known-good / known-bad (2026-09-15)

**Thresholds UNFROZEN** (per task §10). Numbers below characterize operating
points; NOTHING is frozen as a production gate. Targets (not thresholds):
FPR ≤ 5%, FNR ≤ 15%, meaningful human correlation (ρ ≥ 0.5).

## Cohorts
- KNOWN-GOOD: 54 baseline run-2 outputs (unmodified engine, valid inputs;
  "good" = produced by the pipeline, NOT asserted perfect).
- KNOWN-BAD: 13 deterministic composites with controlled defects
  (`evaluation/harness/construct_known_bad.py`) — covering the full task §20
  list:
  KB01 wrong_garment, KB02 missing_garment, KB03 shifted_garment,
  KB04 altered_face (clean identity swap), KB05 wrong_color (LAB a*+45),
  KB06 lost_text, KB07 layer_swap, KB08 phantom_garment, KB09 partial_drop,
  KB10 distorted_pose (8° torso rotation), KB11 lost_logo,
  KB12 deformed_face (affine squash+skew warp), KB13 duplicated_garment
  (ghost copy at offset).
- HUMAN reference: **PENDING** (3 raters required; tooling + frozen rubric
  ready — `RUBRIC.md`). All human-correlation values UNMEASURED.

## Per-metric results (direction-aware AUC; best-F1 candidate point)
| Metric | dir | good mean±std | bad mean±std | AUC | best-F1 thr | FPR | FNR | STATUS (evidence-based) |
|--------|-----|--------------|--------------|-----|-------------|-----|-----|--------------------------|
| texture_period_ok | high | 0.750±0.43 | 0.000 | **0.875** | 0.2 | 0.250 | **0.000** | EXPERIMENTAL — best-in-class; pattern-loss family only; top priority for human validation |
| identity_dinov2_face_cos | high | 0.866±0.08 | 0.804±0.11 | 0.613 | 0.906 | 0.463 | 0.385 | RESEARCH-ONLY — drift proxy as specified; clean-swap blind spot (below); KB12 deformation does move it |
| face_aligned_ssim | high | 0.628±0.12 | 0.595±0.12 | 0.544 | 0.663 | 0.481 | 0.462 | EXPERIMENTAL — structural/artifact signal; not identity |
| face_geo_mean_disp | low | 0.084±0.04 | 0.081±0.04 | 0.537 | 0.073 | 0.407 | 0.615 | EXPERIMENTAL — deformation family; cannot detect clean swap |
| garment_dominant_match | high | 0.482±0.29 | 0.462±0.29 | 0.515 | 0.667 | 0.389 | 0.615 | EXPERIMENTAL — weak as implemented |
| landmark_mpjpe_norm | low | 0.096±0.03 | 0.128±0.05 | 0.474 | 0.102 | 0.389 | 0.615 | EXPERIMENTAL — fine deformation signal; no swap detection |
| garment_histogram | high | 0.259±0.15 | 0.281±0.15 | 0.464 | 0.278 | 0.481 | 0.462 | REJECTED (current form) — no discrimination |
| garment_delta_e_mean | low | 23.86±11.7 | 25.07±11.8 | 0.437 | 23.9 | 0.481 | 0.462 | REJECTED (current form) — systematic flat-lay→on-body bias (good mean ΔE 23.9) swamps defect signal; lightness-conditioned variant is a follow-up |
| dinov2_garment_cos | high | 0.179±0.08 | 0.189±0.08 | 0.423 | 0.175 | 0.518 | 0.615 | REJECTED (current form) — near-chance; pasted-flat-lay composites score HIGHER similarity to the flat-lay reference (direction inverted); documented failure modes confirmed |
| pose_mpjpe_torso_norm | low | 0.035±0.02 | 0.058±0.04 | 0.332* | 0.044 | 0.204 | 0.385 | EXPERIMENTAL — *only 1 of 13 bads is a pose defect; needs a larger pose-corruption cohort |
| ocr_text_score | high | n=1 (1.0) | n=1 (0.0) | — | — | — | — | UNRESOLVED — insufficient data; behavior proven by tests; needs ≥8 text fixtures |
| face_present / pose_present (structural) | — | 54/54 detected | 10/10 detected | — | — | — | — | VERIFIED SOFT-WARNING CANDIDATE — deterministic detection, 100% on this set, unit-tested; no threshold involved |
| worker verify PASS (repo check) | — | 44/54 PASS | — | — | — | — | — | REPO-ATTESTED + MEASURED — advisory echo/blank check; the 10 FAILs are genuine weak-change renders |

## Key findings (evidence, not claims)
1. **Clean face-swap blind spot.** KB04 (different person's face pasted in)
   is NOT detected by any deterministic identity metric: face-SSIM 0.464
   (structure intact), geometry delta small (it's a human face), DINOv2 face
   cosine 0.865 (within the good range 0.68–0.96). DINOv2 base is a generic
   visual similarity model, not a face recognizer — exactly as the task
   predicted ("drift proxy only"). **Consequence: no license-permitted metric
   in this phase detects clean identity swap.** Detecting it requires either
   (a) a licensed face-recognition model (InsightFace commercial track —
   procurement item) or (b) human raters (D1/D2). Until then, identity
   preservation is NOT measurably gateable beyond deformation/blur signals.
2. **Color ΔE needs normalization.** Flat-lay hex vs on-body rendered region
   carries a systematic ~ΔE 24 bias (shading, folds, lighting) that is larger
   than most defect effects. A per-region lightness- or skin-referenced
   normalization variant is the concrete follow-up before color can be a gate
   input.
3. **DINOv2 flat-lay→on-body similarity is inverted** for composite defects
   (pasted flat-lay regions resemble the flat-lay reference). Do not use this
   metric as a garment-correctness signal; keep as texture/semantics proxy
   for research.
4. **Pattern period detection works** (AUC 0.875, FNR 0.0 at the candidate
   point): stripes/checks loss is reliably flagged; 1 of 4 good pattern
   samples lost period in rendering (FPR 0.25) — a genuine engine limitation
   to investigate.
5. **The Qwen judge caught 2 real rendering failures** (S_g010 white
   long-sleeve shirt, S_g012 black long-sleeve tee: garment not applied,
   output ≈ input) that color metrics missed (base clothing ≈ expected color
   family). Judge added real signal (see BENCHMARK_REPORT §judge).
6. **Human correlation UNMEASURED** — every status above is pre-human.
   Upgrading any metric to VERIFIED requires the 3-rater reference (rubric
   frozen, tooling built, raters PENDING).

## Subgroup stability (known-good only)
Per-arm std of face_aligned_ssim: SINGLE 0.13, N2 0.11, N3 0.10 — no
degradation trend across chain depth on this small N=3 (n=6 inferences).
Per-arm garment_delta_e_mean: SINGLE 11.7, N2 10.9, N3 14.1 (n small).

## What is needed to promote statuses
- 3 human raters on ≥30 samples (singles + chain finals + all 10 KB types) →
  Spearman per metric + inter-rater agreement.
- ≥8 text fixtures for OCR calibration; ≥6 pose-corruption composites for
  pose MPJPE; lightness-conditioned ΔE variant re-measured.
- Then re-run `calibrate.py` → re-assign statuses from the fixed enum.
