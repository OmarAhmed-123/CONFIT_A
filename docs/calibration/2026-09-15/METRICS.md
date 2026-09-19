# METRIC INVENTORY & EVIDENCE STATUS — Phase 0.5 §5/§11-18/§21

**Thresholds UNFROZEN.** Every metric below carries: purpose, implementation,
license, and an evidence status. Statuses are provisional until calibration
(CALIBRATION_REPORT.md) completes; the final per-metric status comes from the
fixed enum: VERIFIED HARD-GATE CANDIDATE / VERIFIED SOFT-WARNING CANDIDATE /
EXPERIMENTAL / RESEARCH-ONLY / REJECTED / UNRESOLVED.

## Identity preservation (PROXY — not a validated face-recognition system)
| Metric | Implementation | License | Role |
|--------|---------------|---------|------|
| `face_aligned_ssim` | IOD-aligned (eye-midpoint center, 3.2·IOD, 160×160) crop SSIM (skimage) | Apache-2.0 (scikit-image) | structural facial similarity |
| `face_geo_mean_disp` / `max` | MediaPipe Face Landmarker 478 lm; eye/mouth/jaw/nose geometry normalized by IOD; per-property abs delta | Apache-2.0 (mediapipe + face_landmarker.task, sha256-recorded) | facial geometry drift |
| `landmark_mpjpe_norm` | IOD-normalized L2 over all 478 landmarks | same | fine geometry displacement |
| `identity_dinov2_face_cos` | DINOv2 ViT-B/14 (facebook/dinov2-base @ f9e44c81…, Apache-2.0) CLS cosine on aligned face crop | Apache-2.0 (HF card tag verified 2026-09-15; weights sha256-recorded) | **DRIFT PROXY ONLY** — not a face-recognition system, no recognition claims |

Excluded (license): OpenAI CLIP (all deployed use out of scope + face-rec
excluded), InsightFace (NC research-only weights).

## Pose preservation
| Metric | Implementation | License |
|--------|---------------|---------|
| `pose_mpjpe_torso_norm` | MediaPipe Pose Landmarker lite, 33 lm, torso-normalized (shoulder-mid→hip-mid), raw + Procrustes | Apache-2.0 |

## Garment fidelity (NOT a single embedding — §15/§16)
| Metric | Implementation | License | Notes |
|--------|---------------|---------|-------|
| `garment_delta_e_mean/p95` | CIEDE2000 (Sharma-2005 impl) expected fixture color vs region pixels | n/a (math) | region = tier-1 pose+prior box |
| `garment_dominant_match` | deterministic LAB-quantized dominant colors vs expected set | n/a | |
| `garment_histogram` | per-channel histogram intersection (16 bins) vs fixture region | n/a | |
| `texture_edge_density` / orientation entropy | Sobel structure on region | Apache-2.0 (scipy) | |
| `texture_period_ok` | axis-aware normalized autocorrelation period vs fixture ground-truth period | n/a | stripes/checks only |
| `dinov2_garment_cos` | DINOv2 regional cosine (fixture region vs output region) | Apache-2.0 | **proxy with documented failure modes**: warping, occlusion, lighting, perspective, partial visibility, texture change |
| `ocr_text_score` | EasyOCR (Apache-2.0, models sha256-recorded) expected-vs-generated text; occlusion-lenient regime (word-overlap credit) when region is PARTIALLY_VISIBLE/OCCLUDED_VERIFIED | Apache-2.0 | g009 "STUDIO 2026"; logo (g008) = shape → DINOv2+edge proxy, no invented logo detector |

## Regions (§17)
- Tier-1 (REQUIRED, deterministic): MediaPipe pose keypoints + slot/category
  anatomical priors + image boxes (`regions.py`). No heavy segmentation.
- Tier-2 (SAM2): EXPERIMENTAL, offline-only, default OFF, never render path —
  NOT wired into this package (kept out on purpose; license Apache-2.0 verified
  separately for the future gate design).

## Occlusion (§18)
Per-garment state ∈ FULLY_VISIBLE / PARTIALLY_VISIBLE / OCCLUDED_VERIFIED /
NOT_APPLIED / UNDETERMINED — deterministic classification from pose+region
geometry + outfit layer order (`occlusion.py`). Partial hiding ≠ failure:
metrics switch to lenient regimes based on state.

## Artifacts (EXPERIMENTAL proxies)
`face_blur` (Laplacian variance), `edge_anomaly` (Sobel p99 ratio vs fixture),
`blockiness` (8px grid discontinuity ratio). No learned artifact model claimed.

## Tattoo / hair / accessories
FIXTURE_DEPENDENT by design (§14): no invented detectors. Tattoo fixture p008
(left forearm) + glasses p007 are tracked as fixture-defined properties;
their preservation is scored by human raters (D6/hair, defect checklist) —
UNMEASURED until raters engage.

## Human correlation target (not a threshold)
Spearman ρ ≥ 0.5 vs per-rater and consensus human scores where n ≥ 3 raters
exist. Currently UNMEASURED (raters PENDING).
