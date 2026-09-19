# HUMAN EVALUATION RUBRIC (FROZEN) — Phase 0.5 §19

**FROZEN 2026-09-15.** This rubric is the calibration reference. Model outputs
and VLM-judge outputs are NOT ground truth.

## Rater protocol
- ≥3 independent human raters; each sample rated independently (no discussion
  before individual submission).
- Each rater sees: ORIGINAL person image, all reference garments (flat lays),
  GENERATED output — in a blinded tool (rater identity and model arm hidden
  where possible; arm is revealed only in post-hoc subgroup analysis).
- Raters score each dimension 0–10 integer, plus a defect checklist.
- A sample is "consensus-pass/fail" only via recorded majority; per-rater
  scores are always retained (no aggregation before analysis).

## Dimensions (8, frozen)
| # | Dimension | 0 | 5 | 10 |
|---|-----------|---|---|---|
| D1 | Identity preservation | person unrecognizable as the reference | partially recognizable, clear changes | clearly the same person |
| D2 | Facial preservation | face distorted/changed | minor artifacts | natural, undistorted |
| D3 | Garment correctness | wrong/missing garment | right garment, notable color/pattern errors | exact garment rendered |
| D4 | Layering correctness | layers in wrong order/phantom | visible order errors on 1 layer | correct occlusion & extents (N/A=excluded) |
| D5 | Artifact severity | severe artifacts (holes, warps) | mild artifacts | clean |
| D6 | Hair preservation | hair changed/lost | minor changes | preserved |
| D7 | Pose preservation | pose broken/changed | minor pose drift | pose preserved |
| D8 | Overall realism | obvious AI artifact feel | plausible with flaws | photoreal |

Scale anchoring: 0 = total failure of the property; 10 = indistinguishable from
a real photo of that person in that outfit; 5 = usable but clearly imperfect.

## Defect checklist (per sample, all that apply)
`wrong_garment, missing_garment, shifted_garment, wrong_color, lost_pattern,
lost_text_logo, face_distortion, identity_change, hair_change, pose_change,
layer_order_error, phantom_garment, partial_layer_drop, seam_artifacts,
skin_texture_artifacts, limb_artifacts, other` (other requires free text)

## Aggregation (recorded per sample)
- individual scores (3×8), mean, median, variance per dimension
- consensus = majority (≥2 of 3) on the defect checklist
- inter-rater agreement: per-dimension Spearman ρ and weighted kappa on the
  defect checklist; overall mean ρ
- these statistics feed `calibrate.py` (`human_ratings.json`)

## Rater status
**PENDING** — tooling + schema below are built and frozen; human raters are
required and have NOT been engaged yet (cannot be self-completed). Until
ratings exist, all "human correlation" fields in calibration are UNMEASURED.

## Files
- `evaluation/harness/human_ratings_tool.py` — console rating tool (writes
  `evaluation/results/human_ratings_raw.json`)
- `evaluation/results/human_ratings_raw.json` — schema `{rater_id, sample_id,
  scores: {D1..D8}, defects: [...], notes, rated_at}` (PENDING)
