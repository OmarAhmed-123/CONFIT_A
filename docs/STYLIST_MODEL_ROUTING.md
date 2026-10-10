# StyleList model routing (Mode A / Mode B)

Owner: `backend/app/providers/nvidia/registry.py` (single source of truth).
Workstream: `specs/009-stylelist-ai-modes` · tasks T002, T005 · findings STY-04, STY-07, STY-16.

Callers ask the registry for a **role**; they never name a raw model id. The
routing report (`stylist_model_routing_report()` in `backend/app/services/stylist_vision.py`)
prints the chains without any credential value.

## Roles used by the stylist

| Role | Used for | Chain (primary → failover) |
| --- | --- | --- |
| `STYLIST_CHAT` | Mode B text advice, and the text leg of Mode A | `nvidia/nemotron-3-super-120b-a12b` → `nvidia/nemotron-3-ultra-550b-a55b` |
| `GARMENT_VISION` | Mode A: what garments/colours are visible in the shopper's photos | `google/diffusiongemma-26b-a4b-it` → `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` |
| `CONTENT_SAFETY` | Screening every uploaded image before analysis (fail closed) | `nvidia/nemotron-3.5-content-safety` |

## Why these placements (measured evidence, not model cards)

* **Text primary = `nemotron-3-super-120b-a12b`.** Measured 2026-10-07 on the
  production-shaped payload: 2.71 s and 3.58 s, grounded, EGP preserved. The
  ultra-550b model answered the same payload in 21.89 s after a 503, which exceeds the
  4 s provider budget. Ultra stays as the failover.
* **Vision primary = `google/diffusiongemma-26b-a4b-it`, not
  `nemotron-3-nano-omni`.** The original plan (`STYLELIST_AI_REPAIR_PLAN.md` §8.1)
  proposed nano-omni as the Mode A primary. The registry's measurements rule that out:
  nano-omni returned HTTP 503 `ResourceExhausted: Worker local total request limit
  reached (16/16)` on concurrent runs and took 24.6 s on a correct answer. Diffusiongemma
  answered a real garment photo in 1.7 s with bare, parseable JSON. Nano-omni is kept as
  the failover. The plan's model choice is superseded by this evidence.
* **Gemini / OpenAI are not vision legs.** The spec allows "NVIDIA and/or Gemini". Only
  the NVIDIA vision chain is wired, because it is the verified path. A Gemini vision leg
  needs a new integration and a model-ID verification pass, so it is deferred. Gemini's
  documented image formats are PNG, JPEG and WebP, which match the accepted set.

## Routing rules enforced in code

* `NvidiaClient.chat(..., images=...)` skips any model with `supports_vision=False`, so
  a text model can never receive an image.
* Stylist text and vision use `key_attempts=1` per model. A shopper turn cannot stack
  key rotations on top of model failover.
* Each stylist text attempt is bounded by `AI_PROVIDER_TIMEOUT_SECONDS` (default 4 s).
  Each vision attempt is bounded by `STYLIST_VISION_TIMEOUT_SECONDS` (default 15 s).
  Worst case for vision is therefore two attempts, about 30 s.
* The served model is reported from the response, not from the request. The label
  (`NVIDIA <served model>`) names the model that actually answered.
* A model that is not in the registry cannot be called (`find_spec`), and
  `backend/tests/test_stylist_model_registry.py` fails if a stylist model is missing from
  this document.

## Re-verification

Model ids change. Before pinning or changing any id, re-run
`backend/scripts/verify_nvidia_models.py` against the live catalogue and update the
registry evidence strings. Do not change a model id from this document alone.
