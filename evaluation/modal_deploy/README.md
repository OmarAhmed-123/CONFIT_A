# Eval Modal deployments — diff vs production (verified)

## modal_app_segfee_eval.py vs services/vton-worker/modal_app_segfee.py
Exactly 3 line-level differences (diff-verified 2026-09-15):
1. `app = modal.App("confit-vton-worker-segfee-eval")` — app name
2. `secrets=[modal.Secret.from_name("confit-vton-eval-admin-token")]` — secret
3. `_ENGINE_DIR = .../services/vton-worker/engine` — path correction (the copy
   lives in `evaluation/modal_deploy/` (renamed 2026-09-16 from `evaluation/modal/` — the old name shadowed the pip `modal` SDK once this directory was on sys.path); the production expression resolved to a
   non-existent `evaluation/modal_deploy/engine`). Points at the SAME vendored engine
   directory production uses — engine code identical, no behavior change.
   (Plus a header comment block identifying this as the eval copy.)
Everything else (schema, limits, auth, GPU, volume, MAX_GARMENTS=1, error
taxonomy, verify block) is byte-identical to production.

## modal_app_vlm_eval.py vs services/vlm-worker/modal_app.py
1. `app = modal.App("confit-vlm-worker-eval")`
2. `secrets=[modal.Secret.from_name("confit-vlm-eval-admin-token")]` (both objects)
3. `add_local_file` paths → `../../services/vlm-worker/{inference,model_spec}.py`
   (same canonical files, baked from their production location)
4. local import shim (sys.path insert) so the local import resolves at deploy
   time — no runtime behavior change.

## Secrets
- `confit-vton-eval-admin-token` (key VTON_WORKER_ADMIN_TOKEN) — NEW ephemeral token, value in `evaluation/.eval_env` (gitignored, 600).
- `confit-vlm-eval-admin-token` (keys CONFIT_VLM_ADMIN_TOKEN + QWEN_VL_WORKER_TOKEN) — NEW token, same file.
- Production secrets were NOT read, copied, or modified.

## Cleanup (phase end)
- `modal app deploy --delete confit-vton-worker-segfee-eval` / `confit-vlm-worker-eval` (or dashboard)
- `modal secret delete confit-vton-eval-admin-token confit-vlm-eval-admin-token`
- delete `evaluation/.eval_env` + `.eval_urls` + `.eval_vlm_urls`
