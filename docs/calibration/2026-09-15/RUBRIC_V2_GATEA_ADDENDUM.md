# RUBRIC v2 ADDENDUM — for Gate A execution (human calibration)

Date: 2026-09-15 · Supersedes: nothing — the Phase 0.5 rubric (frozen)
remains the reference for already-collected artifacts. This addendum amends
the rater-facing protocol for Gate A ratings ONLY, with reasons tied to
measured evidence. Gate A remains **BLOCKED — HUMAN CALIBRATION PENDING**
until ≥3 genuine raters submit.

## Amendment 1 — D3 "Garment correctness": explicit completeness scope

Raters must score D3 against the **garment image** (the flat lay they are
shown), not the garment name. D3 explicitly covers:
- color and pattern fidelity (as before),
- **sleeve extent**: a garment whose product image shows long sleeves MUST
  be rendered with sleeves covering the arms to the reference extent. A
  sleeveless or short-sleeve render of a long-sleeve garment is a D3 defect
  (≤4) even when the garment name does not say "long-sleeve".
- **hem/torso extent**, text and logo presence.

**Why (measured):** the VLM judge gave 10/10 to S_g001 — a sleeveless render
of a long-sleeve flat lay — because the garment was named "plain white tee"
(judge panel 38/38 agreement; see root-cause report §4/§5). Name-conditional
scoring is a documented blind spot; human raters must anchor on the image.

## Amendment 2 — defect checklist: new item

Add `sleeve_length_mismatch` to the checklist (definition: rendered sleeve
extent clearly shorter/absent vs the garment image). Retain `limb_artifacts`
for arm shape issues (distinct from coverage).

## Amendment 3 — identity dimension anchoring

D1/D2 unchanged, but the rater UI must show the reference person and output
side-by-side at equal size (existing tool behavior — re-verified before
Gate A launch). Known engine context (raters are NOT told this; it goes in
the analysis only): clean identity swaps are the critical failure class;
AdaFace (eval-only) measured KB04 swap at cosine 0.255 vs good p05 0.281 —
human ratings on the swap/deformation fixtures (KB04, KB12) are the
calibration anchor for the G3 band.

## Amendment 4 — sample set for Gate A (frozen candidate, pre-launch)

- the 13 known-bad constructed samples (KB01–KB13) — all defect classes,
- the 54 baseline samples (note: sleeve-completeness attribute is invalid
  for the 9 long-sleeve-geometry garments per the fixture audit — raters
  will score D3 on what they see; this is exactly the attribute under
  calibration),
- the 4 local-market OCR renders (AO-g120×2, AO-g121, AO-g009) — text
  fidelity (Arabic/English/mixed) human ground truth,
- optional: up to 6 sleeve-gate boundary cases from the 52-job set (g010
  white-on-white "pass" cases) — to calibrate the behavioral-accept
  decision.
Blinding: rater identity hidden; model arm hidden; garment NAMES hidden
from the rating UI (images only) — to enforce Amendment 1.

## Unchanged
8-dimension scale, 0–10 integer, defect checklist mechanics, aggregation
(mean/median/variance, Spearman ρ, weighted kappa, consensus rules),
tooling (human_ratings_tool.py), `human_ratings.json` schema (D1..D8).

## Status
**PENDING RATERS** — no ratings collected; no threshold may be frozen from
this rubric before Gate A completes.
