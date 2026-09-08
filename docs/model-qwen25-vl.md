# CONFIT_A — Self-Hosted Qwen2.5-VL-7B Local Vision Fallback

Local, self-hosted, license-compliant vision **fallback** for Visual Search +
Wardrobe Auto-Tagging (both currently Gemini-only, no failover).

## Why one model
Full spec + code discovery (see `docs/MODEL_PROGRAM_REPORT.md`) shows the
**only** new local model justified by an *approved* feature is Qwen2.5-VL-7B:
both Gemini-dependent vision features need a local fallback, and one VLM serves
both. (fashionCLIP/SAM2/OCR/identity/etc. are NOT REQUIRED — no approved feature.)

## License gate (VERIFIED 2026-09-07)
- **Qwen2.5-VL-7B-Instruct = Apache-2.0** (commercial ✅) — SELECTED, revision
  `cc594898137f460bfe9f0759e9844b3ce807cfb5`.
- **Qwen2.5-VL-3B-Instruct = Qwen RESEARCH LICENSE (non-commercial only)** —
  BLOCKED for this commercial product (verified from its LICENSE file).
- HF = primary source; weights in a Modal Volume (`confit-qwen25vl-weights`),
  deterministic bootstrap (pinned revision + file set + min-size + SHA256);
  **no multi-GB weights in git**; Apache-2.0 `NOTICE` retained.

## Components
| Path | Role |
|---|---|
| `backend/app/providers/qwen_vision/` | Lightweight HTTP client (NO torch) — safe in the Vercel fn |
| `services/vlm-worker/` | Modal GPU service (`modal_app.py`), model load, inference, bootstrap, NOTICE |
| `services/vlm-worker/model_spec.py` | Pinned HF revision + required files + size (single source of truth) |
| `services/vlm-worker/inference.py` | Lazy model load, decode, pure `parse_vision_json` |
| `services/vlm-worker/acquire.py` / `bootstrap_weights.py` | Deterministic acquisition + integrity + manifest |
| `backend/app/providers/tryon_provider.py` | `VisualSearchAIProvider.fallback` (Gemini→Qwen→honest) — additive |
| `backend/app/core/config.py` | `QWEN_VL_*` settings — additive |

## Behaviour
`Gemini (primary) → local Qwen (when QWEN_VL_WORKER_URL set) → honest
analysis_available=False`. **Single attempt + hard timeout; no GPU retry loop.**
Service layers and prompts are **unchanged**; the worker returns the exact Gemini
structured-output contract.

## Endpoints / transports
- **web** (stateless, **verified**): `GET /health`, `GET /readiness` (503 `VLM_NOT_READY`
  until loaded), `POST /analyze` (auth `X-VLM-Admin` = secret `confit-vlm-admin-token2`;
  SSRF-gated image URL; data URL or http(s); ≤15 MB).
- **remote** (robust): standalone Modal Function `vlm_analyze(image_b64, mime, prompt,
  mode)` — the backend's `QWEN_VL_TRANSPORT=remote` calls it via
  `modal.Function.from_name("confit-vlm-worker","vlm_analyze").remote(...)` (container
  held for the call; heavy cold start is fine). Same honest contract as `/analyze`.

## Failure taxonomy
`not_configured / worker_unavailable / worker_not_ready / worker_error /
invalid_response / auth / timeout / bad_input` (client); `GPU_OOM / INFERENCE_FAILED
/ VLM_NOT_READY` (worker). Non-JSON model output → `analysis_available=False`
(never invents fields). Never fakes success; no permanent user-image storage.

## Deployment
```bash
modal secret create confit-vlm-admin-token2 QWEN_VL_WORKER_TOKEN=<random>
# populate the volume once (deterministic), then:
modal deploy services/vlm-worker/modal_app.py      # default GPU: A10G 24GB
export QWEN_VL_WORKER_URL=https://<modal-fn>       # + QWEN_VL_WORKER_TOKEN, in prod
```
Note: `modal_app.py` bakes the sibling `inference.py` + `model_spec.py` into the image
(`add_local_file`) — **required**, else the container crash-loops on
`from inference import …` (the earlier root cause). Separate from the VTON worker
(resource isolation). `QWEN_VL_WORKER_URL` unset ⇒ existing behaviour unchanged.

## Status (HONEST)
✅ license-gated (Apache-2.0 verified) · ✅ unit/contract-tested (29/29: worker parser
8/8 + backend client/routing + **remote transport** 21/21) ·
✅ **real GPU load + inference + feature benchmark MEASURED on A10G**:
load ~7–8 s, peak VRAM **15.45 GiB**, per-image latency **3.2–4.9 s**; real
on-model blazer image → all attributes correct; non-garment color block →
honest `null` category (vision) / documented wardrobe false-positive.

✅ **Live web endpoint VERIFIED working.** Root cause of the earlier crash-loop was
`ModuleNotFoundError: No module named 'inference'` (`modal deploy` ships only
`modal_app.py`; the sibling `inference`/`model_spec` modules were missing from the image) —
fixed by baking them in (`image.add_local_file(...)`). On the deployed **NVIDIA A10** worker:
`GET /health` → **200** (`model_loaded: true`, cold start **14.7 s**); `POST /analyze` (real
blazer photo, admin auth) → **200**, cold **26.0 s** / warm **5.1 s**, accurate attributes.
Warm-container *sustainability* (`min_containers=1`) is a tier/account choice —
`VLM_MIN_CONTAINERS=0` (default) scales to 0 to avoid idle GPU burn. The robust **`.remote()`
transport** (`vlm_analyze` + `QWEN_VL_TRANSPORT=remote`) is also implemented + tested
(see `PR_MODEL_QWEN25_VL.md` §8).

## Tests
`services/vlm-worker/test_inference.py` (8, CPU) · `backend/tests/test_qwen_vision.py`
(15, CPU, worker mocked). Run: `pytest .../test_inference.py -q` and
`pytest .../test_qwen_vision.py -q --noconftest`.

## Global
No Egypt/Cairo hard-coding, no local paths, no sandbox-only behavior, no dev
credentials in the module. Worker is a standalone Modal service (reproducible
bootstrap, no laptop cache, no `/tmp`).
