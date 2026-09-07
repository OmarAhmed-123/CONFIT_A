# PR: Self-hosted Qwen2.5-VL-7B local vision fallback (Apache-2.0)

**Branch:** `feature/model-qwen25-vl` (one model = one branch)
**Status:** ✅ implemented · ✅ license-gated · ✅ unit/contract-tested (CPU) · ❌ **GPU live-validation BLOCKED**
**Do not merge until the §6 gates pass.**

## 1. What & why
Adds a **local, self-hosted** vision fallback for **Visual Search** and **Wardrobe
Auto-Tagging** (both currently Gemini-only, no failover). When the Gemini vision
provider is exhausted/unavailable, it routes to the local Qwen2.5-VL worker; if
that is also unavailable, it degrades honestly to `analysis_available=False`.
Removes the per-request Gemini credit dependency for that capability (GPU infra
still costs — this is **not** free).

## 2. Model + license (gate)
| | 7B‑Instruct (**selected**) | 3B‑Instruct (**blocked**) |
|---|---|---|
| HF | `Qwen/Qwen2.5-VL-7B-Instruct` | `Qwen/Qwen2.5-VL-3B-Instruct` |
| License | **Apache‑2.0** ✅ commercial | Qwen RESEARCH — **non‑commercial only** ❌ |
| Revision (pinned) | `cc594898137f460bfe9f0759e9844b3ce807cfb5` | `66285546d2b821cf421d4f5eb2576359d3770cd3` |

License verified 2026-09-07 from the HF model card (`license:apache-2.0` tag) and
each model's own `LICENSE` file. The 3B's LICENSE is a Qwen RESEARCH agreement
("NON-COMMERCIAL PURPOSES ONLY"; commercial use requires a separate Alibaba Cloud
license) → **not used**. Apache-2.0 `NOTICE` retained.

## 3. Architecture (follows existing patterns)
* `backend/app/providers/qwen_vision/` — **lightweight HTTP client** (NO
  torch/transformers/weights) → safe in the Vercel serverless function.
* `services/vlm-worker/` — **Modal GPU service** (separate from the VTON worker
  → resource isolation). Model loaded once; single global concurrency
  (`@modal.concurrent(max_inputs=1)`).
* **No multi‑GB weights in git.** Weights live in Modal Volume
  `confit-qwen25vl-weights`, populated once by `bootstrap_weights.py` (deterministic:
  pinned revision + required-file set + min-size + SHA256 manifest).
* Reuses the existing `execute_with_resilience` + `settings` + `VTON_*` patterns.
  `visual_search_service` and `wardrobe_service` are **unchanged**.

## 4. Endpoints (worker)
`GET /health` (public), `GET /readiness` (200 only when loaded, else 503
`VLM_NOT_READY`), `POST /analyze` (auth `X-VLM-Admin`; SSRF-gated image URL; data
URL or http(s); ≤15 MB). Returns the **exact Gemini structured-output contract**
(`analysis_available`, `analysis_source`, + the same feature keys).

## 5. Failure taxonomy (honest, no fake success)
Client reasons: `not_configured / worker_unavailable / worker_not_ready /
worker_error / invalid_response / auth / timeout / bad_input`. Worker returns
`GPU_OOM`, `INFERENCE_FAILED`, `VLM_NOT_READY`. Non-JSON model output →
`analysis_available=False` (fields are **never** invented). **Single attempt + hard
timeout, no retry loop** on the GPU model. Never returns the original image as
"generated"; no permanent user-image storage.

## 6. Merge gate (do NOT merge before all pass)
- [x] License verified (Apache‑2.0; 3B non-commercial excluded)
- [x] Unit + contract tests: worker parser **8/8**, backend client/routing **15/15** (CPU)
- [ ] **Real GPU inference on an A10G** (BLOCKED — no GPU in build sandbox)
- [ ] **Real feature benchmark** — visual search Top‑1/5/10 + wardrobe tagging on a
      diverse real matrix (skin tone / body type / pose / flat‑lay / pattern /
      occlusion / lighting / plain vs styled background)
- [ ] **Measured** VRAM/latency/OOM (cold + warm)
- [ ] No regressions (VTON, Gemini path, services unchanged)
- [ ] Modal deploy (`confit-vlm-worker`) + reproducibility (fresh volume)
- [ ] Security (secret token, SSRF gate, admin endpoints not user-facing)

## 7. Performance / cost (HONEST — NOT MEASURED here)
No GPU in the build sandbox → latency/VRAM/accuracy are **NOT MEASURED, not
invented**. **Estimate** (to be replaced by measurement): BF16 7B ≈ 16.6 GB VRAM
→ needs A10G 24 GB (A10 24 GB also viable). Per-request GPU cost = GPU‑seconds
(estimate only). No per-request provider credit.

## 8. Files
`backend/app/providers/qwen_vision/{__init__,errors,provider,README}.py`
`backend/tests/test_qwen_vision.py`
`services/vlm-worker/{__init__,model_spec,acquire,inference,modal_app,bootstrap_weights,test_inference}.py`
`services/vlm-worker/{requirements.txt,Dockerfile,NOTICE}`
`docs/model-qwen25-vl.md` · `PR_MODEL_QWEN25_VL.md` · (wiring) `config.py` + `tryon_provider.py` (additive).

## 9. Rollout
`QWEN_VL_WORKER_URL` unset = **identical** existing behaviour (safe to merge the
code before the worker exists). Enable by deploying the worker + setting
`QWEN_VL_WORKER_URL` (+ `QWEN_VL_WORKER_TOKEN` = `confit-vlm-admin-token`) in prod.
Keep Gemini primary. Advertise "local fallback available" to users **only after**
§6 is green.
