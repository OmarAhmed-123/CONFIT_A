# CONFIT_A VTON — Human Calibration Package (Phase 6, 2026-09-19)

**Status: `HUMAN CALIBRATION = BLOCKED` (no ≥3 real independent raters
available). This package is PREPARED and executable as-is once raters
exist.** No VLM or agent visual inspection may be relabeled as human
validation. Agent labels in this repo are engineering calibration only.

## Contents

| file | purpose |
|---|---|
| `RUBRIC.md` | what raters judge, scale, definitions, edge cases |
| `RUN_INSTRUCTIONS.md` | execution protocol (blinding, independence, aggregation, closure criteria) |
| `ARTIFACT_MANIFEST.json` | the 73-item set (66 sleeve + 7 lower-garment) — 10 fresh Phase-7 P1-D base renders added; synthetic composites excluded (defect obvious by construction) (hashes + context + gate verdicts, P8: no image payloads) |
| `LABELING_SHEET.csv` | empty rater sheets (3 templates), one row per item |
| `UNBLINDING_SHEET.csv` | item-ID → gate verdict / truth label mapping (do NOT show raters) |

## What "completion" means (barrier-closure criteria)

1. ≥3 real independent human raters, no prior exposure to this project's
   labels, no mutual communication, no AI assistance.
2. Each rater completes the full 73-item sheet (or the agreed core set,
   see RUN_INSTRUCTIONS §4).
3. Inter-rater agreement (Fleiss' kappa on the primary judgment) reported;
   discordant items re-adjudicated by consensus of the three.
4. Human labels become the calibration reference: agent labels and gate
   verdicts are scored against them; any gate disagreement is a defect
   report (fix + regression pin), not a label negotiation.
5. Result recorded in `evaluation/human_calibration/RESULTS_<date>.md`
   (hashes + verdicts + agreement stats only — P8 hygiene), and the
   release-barrier table in the Phase-6 report is updated.

Until all five hold: `HUMAN CALIBRATION = BLOCKED`.
