# VTON "Ghost Hands" — Forensic Diagnosis & Remediation (2026-10-10)

Branch: `fix/vton-ghost-hands`. Companion deliverable: workspace
`VTON_GHOST_HANDS_REPORT.md` (exec summary, evidence table, research, plan).

## Incident

User full-body outdoor photo + catalog product *Tuxedo Peak Lapel Evening
Dinner Jacket* (Outerwear/REISS) → render shows the CATALOG model's pale
hands at the waist, the turquoise bow tie missing, sleeves mismatched to the
user's pose, and the UI presenting the result as a clean success
("Dressed with 1 Garment Layer").

## Root cause chain (all verified in source; see report for file:line)

1. The catalog thumbnail (`pexels-photo-883362`, seed_data.py:271) is an
   ON-MODEL photo: hands at the button, bow tie, boutonnière.
2. `_build_garments_payload` (tryon_service.py) sends that RAW photo as the
   garment image; no asset classification exists anywhere in the DB/schema.
3. The deployed engine `fashn_vton_segfee` (modal_app_segfee.py:395-401)
   renders with hardcoded `seed=42`, `num_timesteps=30`, and the engine
   adapter hardcodes `garment_photo_type="flat-lay"` +
   `segmentation_free=True` (engine/fashn_segfee.py:86-87).
4. In the vendored fork (upstream fashn-vton-1.5 @7c0f10af minus the
   non-commercial parser), `flat-lay` + segmentation-free means BOTH the
   person image and the garment image enter the diffusion UNCHANGED
   (pipeline.py:243-255 enforcement; :303-316 `disable_masking=True`
   no-ops) and the garment pose is DUMMY keypoints (pipeline.py:272). The
   catalog model's hands/skin are therefore part of the garment
   conditioning → reproduced on the user (ghost hands).
5. The only quality gate (`_verify_output`, modal_app_segfee.py) proves the
   image *changed* (pixel-change/color-shift/stddev) — a contaminated render
   changes plenty → `PASS` → backend `assert_layer_applied` passes → UI
   shows success. The 2026-09-06 E2E proof doc even logged "minor hand
   deformation near the pockets" of the same family as a non-issue.
6. The correct gate DOES exist on main — `classify_garment_photo`
   (engine/fashn_v15.py:190, merged PR #284) — but only in the
   non-deployed `fashn_v15` engine. The deployed worker (git_sha d2a80417,
   deployed 2026-09-07) runs `segfee`, which lacks it.

## Fix (this branch)

* **P0 worker QA gate** — `services/vton-worker/vton_qa.py`: ghost-limb
  detection (new skin blobs vs person input), face/background drift scores;
  `modal_app_segfee.py` now runs a QA-gated seed ladder (42→1337→20261010),
  pastes identity regions back from the person input, and fails LOUDLY
  (`QA_GATE_FAILED`) when no seed passes. `verify.qa` + `qa_attempts` travel
  to the backend for observability.
* **P0 backend asset gate** — `garment_asset_guard.py` (CPU-only, PIL+numpy):
  classifies every garment pre-GPU (skin-ratio / background-uniformity /
  conservative-model); `_build_garments_payload` raises
  `VTON_GARMENT_ASSET_INVALID` for on-model photos without a validated
  clean asset; kill-switch `VTON_ASSET_GATE_ENABLED=false`.
* **P1 prep pipeline** — `scripts/prep_garment_assets.py`: classify at
  ingestion, mark flat-lays `tryon_ready`, keep an honest seam for licensed
  cleaners (SCHP MIT / LaMa Apache-2.0); migration 0035 adds
  `photo_type/tryon_ready/clean_image_url/classification_json` to
  `garment_assets`; `get_or_create_garment_asset` no longer fakes
  segmentation URLs.
* **P2 UI honesty** — VirtualTryOnModal shows a red quality-gate banner when
  `verification.all_layers_verified === false`.
* **Measurement** — `scripts/vton_golden_set_eval.py` measures success rate,
  ghost-hand rate, face/background drift, latency BEFORE/AFTER against any
  deployed worker; credentials from env only.

## Deployment (exact commands; secrets never on disk in the repo)

```bash
# from a machine with the local .env loaded (never committed)
set -a; . ~/.env; set +a
git checkout fix/vton-ghost-hands   # after PR merge: main
CONFIT_GIT_SHA=$(git rev-parse HEAD) modal deploy services/vton-worker/modal_app_segfee.py
curl -s https://omarsafealden--confit-vton-worker-segfee-fashninferences-bc79fa.modal.run/ | jq .git_sha
python3 scripts/vton_golden_set_eval.py --out reports/golden_AFTER.json
```

Redeploy ONLY after the golden set is run against a staging alias; the P0
backend gate ships independently via Vercel.
