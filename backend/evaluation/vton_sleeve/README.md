# VTON sleeve-gate evaluation area

This directory holds NO results — deliberately. Sleeve-gate calibration data
lives OUTSIDE the repository (raw renders can contain personal imagery; the
repo stores only hashes, aggregates, and manifests per the privacy rule).

* Tooling: `scripts/vton_sleeve_calibration.py` (dataset freeze, split,
  threshold scan, manifest publish) — see
  `docs/vton/SLEEVE_CALIBRATION_PROTOCOL_2026-10-18.md`.
* Synthetic wiring fixtures (NEVER calibration evidence):
  `python3 scripts/vton_sleeve_calibration.py make-synthetic --out /tmp/sg_synth`
  — every such case is labeled `synthetic: true` and the harness refuses to
  freeze it into an approved dataset.
* Historical 2026-09 measurement tables (reference only, unfrozen
  thresholds): preserved outside this repo; their provenance summary is in
  the gate module docstring (`backend/app/services/vton_sleeve_gate.py`).
