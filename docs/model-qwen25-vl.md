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

## Endpoints
`GET /health`, `GET /readiness` (503 `VLM_NOT_READY` until loaded), `POST /analyze`
(auth `X-VLM-Admin` = `confit-vlm-admin-token`; SSRF-gated image URL; data URL or
http(s); ≤15 MB).

## Failure taxonomy
`not_configured / worker_unavailable / worker_not_ready / worker_error /
invalid_response / auth / timeout / bad_input` (client); `GPU_OOM / INFERENCE_FAILED
/ VLM_NOT_READY` (worker). Non-JSON model output → `analysis_available=False`
(never invents fields). Never fakes success; no permanent user-image storage.

## Deployment
```bash
modal secret create confit-vlm-admin-token QWEN_VL_WORKER_TOKEN=<random>
# populate the volume once (deterministic), then:
modal deploy services/vlm-worker/modal_app.py      # default GPU: A10G 24GB
export QWEN_VL_WORKER_URL=https://<modal-fn>       # + token, in prod
```
Separate from the VTON worker (resource isolation). `QWEN_VL_WORKER_URL` unset ⇒
existing behaviour unchanged.

## Status (HONEST)
✅ license-gated · ✅ unit/contract-tested (CPU) · ❌ **real GPU validation BLOCKED**
(no GPU/Modal in the build sandbox). NOT MEASURED: latency/VRAM/accuracy (not
invented). Do **not** claim "verified/production-ready" or advertise the fallback
until the PR merge gate (`PR_MODEL_QWEN25_VL.md` §6) is green.

## Tests
`services/vlm-worker/test_inference.py` (8, CPU) · `backend/tests/test_qwen_vision.py`
(15, CPU, worker mocked). Run: `pytest .../test_inference.py -q` and
`pytest .../test_qwen_vision.py -q --noconftest`.

## Global
No Egypt/Cairo hard-coding, no local paths, no sandbox-only behavior, no dev
credentials in the module. Worker is a standalone Modal service (reproducible
bootstrap, no laptop cache, no `/tmp`).
