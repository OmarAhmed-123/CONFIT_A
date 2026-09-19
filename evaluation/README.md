# CONFIT_A Phase 0.5 — Evaluation & Calibration Infrastructure

Research/evaluation-only code. **NO production behavior is modified by anything
in this directory.** Production VTON = `services/vton-worker/` (untouched,
verified by diff); production Modal app `confit-vton-worker-segfee` untouched.

## Layout
```
evaluation/
├── modal_deploy/                  # renamed from `modal/` 2026-09-16 (the old name shadowed the pip `modal` SDK once this dir was on sys.path)
│   ├── modal_app_segfee_eval.py   # eval-only FASHN worker copy (2 identifiers + 1 path; see README)
│   └── modal_app_vlm_eval.py      # eval-only Qwen VLM worker copy (identifiers + import shim)
├── fixtures/
│   ├── persons/                   # 10 synthetic AI persons (no real persons), 768x1024 standardized
│   ├── person_manifest.json       # pose/hair/lighting/bg/glasses/tattoo + standardization record
│   ├── garments/                  # 24 procedural flat-lay garments (deterministic, seed 20260915)
│   ├── garment_manifest.json      # exact ground truth: color, pattern, text, logo, slot, category
│   └── outfits.json               # 38 outfits / 54 inferences (SINGLE, N2_TB, N2_IO, N2_WC, N3, N3_WC)
├── vton_metrics/                  # offline metric package (deterministic; no frozen thresholds)
├── harness/
│   ├── matrix.py                  # job matrix generator
│   ├── run_baseline_modal.py      # GPU baseline runner (client-side chaining; no image data in logs)
│   ├── construct_known_bad.py     # 10 deterministic known-bad composite types
│   ├── run_offline_eval.py        # metric extraction over outputs
│   ├── calibrate.py               # distributions, AUC, FPR/FNR at CANDIDATE points (UNFROZEN)
│   ├── judge_client.py            # Qwen2.5-VL judge (frozen config; 2 calls/sample consistency)
│   └── human_ratings_tool.py      # console tool for human raters (PENDING human use)
├── tests/                         # 35 passing tests (known-good/bad, deterministic values,
│                                  # malformed/missing/occluded, OCR-absence, license-absence,
│                                  # no-image-data-in-logs)
├── config/judge_config.yaml       # FROZEN judge config (revision, prompts, ordering, schema)
├── scripts/                       # fixture generation + model fetch (sha256 manifests)
├── weights_local/                 # gitignored; pinned models + manifests
├── results/                       # gitignored; run records (JSON/CSV), outputs (sha256 sidecars)
└── .eval_env                      # gitignored, chmod 600; ephemeral eval admin tokens (NEVER committed)
```

## Eval deployments (separate from production)
- `confit-vton-worker-segfee-eval` — FASHN A10, weights volume shared read-only
- `confit-vlm-worker-eval` — Qwen2.5-VL-7B A10, weights volume shared read-only
- URLs recorded in `.eval_urls` / `.eval_vlm_urls` (gitignored)

## Reproduce
```bash
python3 evaluation/harness/matrix.py                 # regenerate outfits.json
python3 evaluation/harness/run_baseline_modal.py     # GPU run (~20 min A10)
python3 evaluation/harness/run_offline_eval.py       # metrics over outputs
python3 evaluation/harness/construct_known_bad.py    # known-bad composites
python3 evaluation/harness/calibrate.py              # calibration analysis
python3 evaluation/harness/judge_client.py           # Qwen judge (frozen config)
python3 -m pytest evaluation/tests/ -q               # 35 tests
```

## Hard rules enforced here
- thresholds UNFROZEN (verdict.py operates on candidate points only)
- no image bytes in logs/records (test: test_no_image_data_in_run_records)
- no weights/private images in git (test: test_no_weights_or_images_in_git)
- DINOv2 = drift proxy only; no face-recognition claims
- N=3 = eval regime only; N=2 = initial production candidate
- human raters are the calibration reference; judge ≠ ground truth
