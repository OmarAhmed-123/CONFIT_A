# CONFIT_A — Self-Hosted Qwen2.5-VL Vision Provider (local fallback)

A **lightweight client** for the self-hosted Qwen2.5-VL inference worker.

* **No torch / transformers / weights** in this package — safe in the Vercel
  serverless function. The model lives on the worker (`services/vlm-worker`),
  reached over HTTP.
* **Local vision fallback** for Visual Search + Wardrobe Auto-Tagging. It is used
  ONLY when Gemini is exhausted/unavailable. `QWEN_VL_WORKER_URL` unset ⇒
  `is_configured() == False` ⇒ existing Gemini-only behaviour unchanged.
* **Honest failure**: every failure is an explicit `QwenVisionError(reason=...)`
  (`not_configured / worker_unavailable / worker_not_ready / worker_error /
  invalid_response / auth / timeout / bad_input`). It never invents detections.

## Model (license-gated)

| | 7B‑Instruct (SELECTED) | 3B‑Instruct (BLOCKED) |
|---|---|---|
| HF | `Qwen/Qwen2.5-VL-7B-Instruct` | `Qwen/Qwen2.5-VL-3B-Instruct` |
| License | **Apache‑2.0** (commercial ✅) | Qwen RESEARCH — **non‑commercial only** ❌ |
| Revision (pinned) | `cc594898137f460bfe9f0759e9844b3ce807cfb5` | `66285546d2b821cf421d4f5eb2576359d3770cd3` |

## Integration

`VisualSearchAIProvider` (used by both Visual Search and Wardrobe Auto‑Tagging)
routes `Gemini → Qwen (when configured) → honest analysis_available=False`.
The service layers and prompts are **unchanged**.

See `docs/model-qwen25-vl.md` (full doc) and `PR_MODEL_QWEN25_VL.md`.
