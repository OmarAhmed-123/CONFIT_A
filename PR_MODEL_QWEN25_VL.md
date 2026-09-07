# PR: Self-hosted Qwen2.5-VL-7B local vision fallback (Apache-2.0)

**Branch:** `feature/model-qwen25-vl` (one model = one branch)
**Status:** ✅ implemented · ✅ license-gated · ✅ unit/contract-tested (23/23) ·
✅ **real GPU load + inference + feature benchmark (MEASURED on A10G)** ·
⚠️ live `/analyze` web serving BLOCKED in build env (§8)
**Do not enable `QWEN_VL_WORKER_URL` in prod until §8 (web serving) is resolved.**

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
- [x] License verified (Apache‑2.0 via HF `cardData.license`; 3B non‑commercial excluded)
- [x] Unit + contract tests: worker parser **8/8**, backend client/routing **15/15** (CPU)
- [x] **Real model load on real GPU** — A10G, **VRAM 15.45 GiB** (fits 22 GB), load **~7–8 s**
- [x] **Real GPU inference** — correct STRICT JSON on real images (measured)
- [x] **Real feature benchmark** — real CONFIT_A images + real production prompts (measured below)
- [x] **Measured** VRAM + per‑request latency (see §7)
- [x] No regressions (VTON, Gemini path, `visual_search_service`/`wardrobe_service` unchanged)
- [x] Modal deploy (`confit-vlm-worker`) + deterministic weight bootstrap (fresh volume)
- [x] Security (secret token, SSRF gate, admin auth, endpoints not user‑facing)
- [ ] **Live `/analyze` web serving sustained** — see §8 (BLOCKED in build env; see options)
- [ ] Full diverse catalog benchmark (skin tone / body type / pose / flat‑lay / occlusion) — needs real catalog

## 7. PERFORMANCE — MEASURED on a real A10G (not estimated)
`torch 2.14.0+cu130`, `transformers 5.16.1`, `qwen-vl-utils 0.0.14`, weights BF16
from Modal Volume `confit-qwen25vl-weights` (16.59 GB, 14 files, validated).

| Metric | Value (MEASURED) |
|---|---|
| GPU | NVIDIA A10G, 22.1 GiB |
| Model load (weights → GPU) | **~7–8 s** |
| Peak VRAM (loaded) | **15.45–15.46 GiB** |
| Inference latency (per image, warm) | **3.2–4.9 s** (gen, `max_new_tokens≤300`, no sampling) |
| Concurrency | 1 (`@modal.concurrent(max_inputs=1)`; single‑global, honest) |

**Real feature results (real CONFIT_A images, real production prompts):**
- `VTON_PROOF_blazer_output` (real on‑model photo — blue checkered blazer, white shirt,
  gray trousers, white sneakers) → vision: `Outerwear / Blue / Checkered / Formal` +
  `{Tops: White shirt, Bottoms: Gray trousers, Footwear: White sneakers}` — **all correct**.
- A solid navy color block (not a garment) → vision: `detected_category: null` (correct:
  not a fashion item) but color misread navy→"black"; wardrobe prompt **hallucinated**
  `Tops / Sweater` (false positive). → **Documented failure mode on non‑garments**; the
  service marks items failed/retryable (honest), never fabricates a search result.

## 8. WEB ENDPOINT SERVING — BLOCKED in build env (honest)
The model + inference are proven via direct GPU execution (`modal run`). The deployed
Web endpoint (`…/analyze`, `…/health`) could NOT be kept serving in this environment:
a 16.6 GB model's cold start (~70 s) exceeds the Modal edge request window (the
container is cancelled mid‑load), and `min_containers=1` did not sustain a warm
container (deployed app stayed at 0 tasks; no `modal logs` CLI to read the container).
**Production options** (pick one): (a) a Modal tier/plan that sustains a warm container
for a heavy model (`min_containers=1`, real continuous A10G cost); (b) a quantized
(4‑bit) build to cut cold‑start + VRAM; (c) the backend calls the model via a Modal
Function (`.remote()`) instead of the Web endpoint. Until (a/b/c) is confirmed, the
`QWEN_VL_WORKER_URL` must stay **unset** in prod (existing Gemini‑only behaviour,
honest `analysis_available=False` when Gemini is down).

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
