## What broke (forensic, verified in source)

The "ghost hands" render (catalog model's pale hands at the user's waist,
missing bow tie, pose-mismatched sleeves, presented as success) is a
five-link chain, each link pinned to a file:line in
`docs/VTON_GHOST_HANDS_REMEDIATION_20261010.md`:

1. catalog thumb `pexels-photo-883362` is an **on-model** photo (seed_data.py:271);
2. `_build_garments_payload` sends it **raw** as the garment image;
3. deployed `fashn_vton_segfee` hardcodes `seed=42`, `num_timesteps=30`
   (modal_app_segfee.py:395-401) and the adapter hardcodes
   `garment_photo_type="flat-lay"` + `segmentation_free=True`
   (engine/fashn_segfee.py:86-87);
4. in the vendored fork those flags pass **both** images to the diffusion
   UNCHANGED with a dummy garment pose (pipeline.py:243-255, 272, 303-316) →
   the catalog model's hands/skin are garment conditioning → reproduced;
5. the only gate (`_verify_output`) proves the image *changed*, so the
   contaminated render passed and the UI showed a clean success. The correct
   anti-contamination gate exists on main (PR #284, engine/fashn_v15.py:190)
   but only in the **non-deployed** engine; live worker git_sha `d2a80417`
   (deployed 2026-09-07) runs `segfee` without it.

## The fix (5 commits)

* **P0 worker QA gate** — `vton_qa.py`: ghost-limb detection (skin blobs in
  render absent from person), face/background drift; seed ladder
  42→1337→20261010 with identity paste-back; loud `QA_GATE_FAILED` when no
  seed passes; `verify.qa`/`qa_attempts` surfaced to the backend.
* **P0 backend asset gate** — CPU-only classifier (skin-ratio /
  bg-uniformity / conservative-model) blocks on-model products without a
  validated clean asset via `VTON_GARMENT_ASSET_INVALID`
  (`VTON_ASSET_GATE_ENABLED` kill-switch); migration 0035 adds
  `photo_type/tryon_ready/clean_image_url/classification_json`;
  `get_or_create_garment_asset` stops faking segmentation URLs.
* **UI honesty** — red quality-gate banner when
  `verification.all_layers_verified === false`.
* **Measurement & P1 prep** — `scripts/vton_golden_set_eval.py` (BEFORE/AFTER
  success rate, ghost-hand rate, drift, latency; creds env-only) and
  `scripts/prep_garment_assets.py` (ingestion-time classification, licensed
  cleaner seams: SCHP MIT / LaMa Apache-2.0).

## Tests

29 pass: 7 worker QA (clean passes / invented hands fail / paste-back
pixel-exact), 5 guard (real tuxedo photo classifies `model` at skin_ratio
0.099; flat-lay accepted; conservative default), plus the pre-existing chain
+ commercial-worker suites (scoped off the gate — different contract).

## Deployment

Backend gate ships via Vercel on merge. Worker redeploy ONLY after staging
golden set (exact commands in the design doc; secrets from local env only):
`CONFIT_GIT_SHA=$(git rev-parse HEAD) modal deploy services/vton-worker/modal_app_segfee.py`.

## Not claimed

No render-quality improvement is claimed without the AFTER golden-set run;
this PR makes failure loud and blocks the incident input class.
