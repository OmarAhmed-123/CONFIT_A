# StyleList live-provider evaluation protocol (T016)

Status: **PROTOCOL ONLY. NOT EXECUTED.** No live-provider quality, latency, or
availability result exists. This document defines what an authorized run must
do and what evidence it must produce before production activation. It does not
authorize any paid call.

## 1. What is already verified (offline, not quality evidence)

`backend/tests/test_stylist_eval_harness.py` runs eight golden cases (scorecard: "cases run 8")
through the real endpoint with every provider mocked. Run on Python 3.12, exit 0:

| Property | Offline result | What it does NOT show |
| --- | --- | --- |
| Grounded in catalogue | 8/8 | Whether the model picks sensible products |
| Mode A names the served model | 3/3 | That the named model really answered in production |
| Honest fallback when vision is down | 1/1 | Real provider failure modes and their frequency |

These check the code's contract. They are not model-quality measurements.

## 2. Provider configuration (variable names only; never record values)

| Role | Config | Notes |
| --- | --- | --- |
| Text (Mode B and Mode A text leg) | `NVIDIA_API_KEY`, optional `NVIDIA_CHAT_KEY_2` | Primary `nvidia/nemotron-3-super-120b-a12b`, failover `nvidia/nemotron-3-ultra-550b-a55b` |
| Vision (Mode A photos) | same NVIDIA key(s) | Primary `google/diffusiongemma-26b-a4b-it`, failover `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` |
| Content safety | same NVIDIA key(s) | `nvidia/nemotron-3.5-content-safety`, fails closed |
| Gemini | `GEMINI_API_KEY` | **Not a vision leg.** Not wired. Do not evaluate as vision. |
| Feature switch | `STYLIST_VISION_ENABLED` | Must be true for the Mode A arm |

Routing source of truth: `backend/app/providers/nvidia/registry.py` and
`docs/STYLIST_MODEL_ROUTING.md`. The routing report prints chains with no
credential values.

## 3. Budgets and cost control (existing settings)

| Setting | Value in code | Purpose |
| --- | --- | --- |
| `AI_PROVIDER_TIMEOUT_SECONDS` | 4.0 | Text provider budget per attempt |
| `STYLIST_VISION_TIMEOUT_SECONDS` | 15.0 | Vision budget per attempt |
| `STYLIST_IMAGE_TURNS_PER_HOUR` | 5 | Per-user cap on photo turns |
| `key_attempts=1` per model (stylist) | code | No stacked retries per shopper turn |

Required before a run: a spend cap on the provider account, a staging-only
database, and written authorization naming the maximum number of paid calls.
Suggested ceiling for the first run: 4 text prompts × 2 repetitions (1 text
call each) plus 3 photo prompts × 2 repetitions (1 text call and up to 2 vision
calls each, counting failover). That is at most 4×2 + 3×2×3 = 26 provider
calls. The owner sets the real ceiling.

## 4. Dataset and test protocol

* **Text cases:** the four `TEXT_PROMPTS` and the three `PHOTO_PROMPTS` in
  `test_stylist_eval_harness.py`. Plain text needs no image.
* **Photo cases:** a small set of **synthetic or licensed** garment photos
  created for this purpose. **No customer images.** Store only the images' hashes
  and labels, never the images, in any repo or artifact.
* **Repetitions:** at least 2 per case, so variance is visible.
* **Environment:** staging, a copy of the schema at the release head, and a
  seeded test catalogue. Never production data.

## 5. Metrics and acceptance (thresholds to be agreed by the owner before the run)

| Metric | How measured | Evidence needed |
| --- | --- | --- |
| Catalogue grounding | Every recommended product id exists in the catalogue | 100% required (SC-001) |
| Served-model truth | Response `engine` matches the model that actually answered (provider logs) | 100% required |
| Honest fallback | Forced vision failure gives Mode B plus a reason | 100% required |
| Colour coordination | Human rating on a fixed rubric (blind, two raters) | Agreement reported; no automatic pass |
| Latency p50 / p95 | Wall clock per turn, text and vision separately | Reported; compared with the budgets in §3 |
| Failure rate by class | Timeouts, 5xx, empty or non-JSON, safety blocks | Reported per provider and model |
| Cost | Calls and tokens per turn from provider usage fields | Reported; compared with the cap |

Colour quality and reasoning quality are **human-rated**. An automatic score
does not stand in for that rating.

## 6. Fallback expectations

* A timeout or 5xx from one model moves to its failover, then to Mode B.
* A failed provider call is **never** reported as a successful analysis.
* The shopper sees the localized reason (FR-012), not a raw provider error.

## 7. Evidence required before production activation

1. Written authorization naming the staging target, call ceiling, and spend cap.
2. The run log with per-call provider, model, latency, status, and token usage (no keys, no images).
3. The scorecard for §5, with raw counts and the rating sheet.
4. Results for all §6 fallback paths, including a forced failure.
5. A decision record approving the failover order and the budgets, or a change to them.
6. Confirmation that no paid call was made outside the authorized window.

Until items 1–6 exist, T016 stays **partial**.
