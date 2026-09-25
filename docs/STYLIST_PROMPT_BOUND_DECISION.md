# AI stylist prompt bound — decision record

**Date:** 2026-09-24 · **Commit:** `70221b2` (+ the trim/blank rules added later the same
day) · **Status:** implemented, tested, mutation-controlled, **in production pending merge**

This record exists because the brief (§21–§23) requires the classification to be
explicit. It is:

> ## ENGINEERING SAFETY DEFAULT — not a product requirement.

If a product owner later disagrees, this document is the thing to change, not the code
comment alone.

---

## 1. Problem

`StylistPromptRequest.prompt` was `str` with **no maximum**:

```python
prompt: str = Field(description="Natural language request or occasion text …")
```

The endpoint accepts **anonymous** callers, spends **provider quota** per call, and
writes a **row** per accepted call. An unbounded string fields means a single request
can carry an arbitrarily large body, and `max_tokens` bounds only the *response*.

## 2. Existing state, measured

| Thing | Value | Source |
|---|---|---|
| Rate limit on `/stylist/chat` | `20/hour`, keyed per endpoint function | `backend/app/controllers/stylist_controller.py`, `core/rate_limit.py` |
| Provider chain | `nvidia,groq,gemini,openai,unorouter` | `settings.AI_PROVIDERS` |
| Fallback | deterministic grounded engine when every provider fails | `stylist_service`, `grounding.py` |
| Request body ceiling | ~4.5 MB (serverless) | platform |
| `prompt` maximum | **none** | this defect |
| Production user prompts | 71 rows: p50 **53**, p95 **146**, p99 **240**, max **240** chars, none > 1000 | `stylist_messages` read-only, 2026-09-24 |

## 3. Research

* **Repository requirements.** No prompt length appears in the BRD, the API contract
  checklist, the UX specification or the analytics definitions. The only trace of the
  gap is the consumer acceptance report, which lists it as an open item. → nothing to
  inherit; a bound would be an engineering decision.
* **Provider context windows.** Every configured provider accepts far more text than
  this endpoint would ever receive; the context window is therefore *not* the binding
  constraint. Cost per token and the abuse surface are.
* **OWASP API4:2023 (Unrestricted Resource Consumption)** — recommend bounding every
  parameter that costs money per unit: "Unrestricted resource consumption … can lead
  to denial of service or increased operational costs". Prompt length is exactly such
  a parameter here.
* **The deterministic engine** walks the prompt text; its cost grows with input
  length, though the character bound is what removes the pathological case.

## 4. Alternatives considered

| Option | Why not |
|---|---|
| No bound | The defect. |
| Bound at the median (53) | Would reject the p95 and the longest real prompt (240). |
| Bound at 500 | 2× the longest observed prompt — a single new legitimate use (a detailed brief) hits a wall with no product reason. |
| Truncate silently at N | Silent truncation changes the user's request without telling them; the shopper would see advice for a different question. |
| Bound only in the frontend | Convenience, not a security boundary — the endpoint is public. |
| **Reject above 2000 characters (chosen)** | 8.3× the longest observed prompt, ~37× the median; cannot truncate observed usage; caps the abuse surface ~2 orders of magnitude below the body ceiling. |

## 5. Decision

* `STYLIST_PROMPT_MAX_CHARS = 2000`, `min_length=1`, whitespace trimmed **before**
  length validation, whitespace-only refused (a blank prompt is not a request and
  answering it spends a provider call on nothing).
* Enforced in the **schema**, so a rejected request never reaches the service, the
  parser, the provider or the database. Verified by a test that counts
  `stylist_messages` rows across a rejected request.
* Mirrored in the UI (`frontend/src/i18n/promptBounds.ts`, `maxLength` on the input,
  localized remaining-character hint) so a shopper cannot type a request the server
  refuses. A test compares the TypeScript constant with the Python one.
* Rejected with **422** — the same status the endpoint already uses for invalid
  structured constraints, so clients need no new error handling.

## 6. Cost and abuse review (§23)

| Vector | Current control | Evidence |
|---|---|---|
| Request size | 2000-char bound; 422 before any side effect | `test_an_over_long_prompt_is_refused_without_writing_anything`, 1 MB payload test |
| Token budget | `max_tokens` per provider call, set in `orchestrator` | `backend/app/providers/orchestrator.py::_max_tokens` |
| Rate limit | `20/hour`, endpoint-keyed so URL aliases cannot multiply it | `test_rate_limit_store.py` (30 accepted → 429 + `Retry-After`), alias-sharing test |
| Provider timeout | per-provider timeout in the orchestrator; Gemini measured 2.9 s to answer, >4 s when failing | orchestrator comments (measured 2026-08) |
| Retry count | provider chain fallback, **not** per-request retry loops | orchestrator; no client retry in `apiClient` except the 401 refresh path |
| Cooldown | none per caller beyond the hourly limit | **gap, recorded** |
| Duplicate requests | no deduplication — a user can press send twice; each call spends quota | **gap, recorded** |
| Concurrent requests | bounded by the rate limit; concurrency measured on the limiter only | `test_rate_limit_store.py::test_concurrent_requests_against_a_shared_store_do_not_over_admit` |
| Persistence growth | one `stylist_messages` row per accepted call, `Text` column | measured: 71 user prompts total in production |

The two recorded gaps (per-caller cooldown, duplicate suppression) are **not** fixed
here: both are product-behaviour decisions (how long is too soon? should an identical
prompt reuse the previous answer?), and inventing either would be exactly the kind of
silent product decision this cycle is meant to avoid.

## 7. Verification

| Check | Result |
|---|---|
| Boundary accepted / refused | 2000 ok, 2001 → 422 |
| Characters not bytes | 2000 Arabic characters accepted (payload asserted multibyte first) |
| Whitespace | trimmed before length validation; whitespace-only refused |
| Input matrix | 1 char, Arabic letter, emoji only, mixed script, repeated chars, punctuation, newlines — accepted |
| Large payload | 1 MB → 422 |
| No side effect on refusal | message-row count unchanged |
| Frontend cap == API cap | asserted cross-language |
| Mutation: remove `max_length` | 2 tests fail |
| Mutation: lower the bound below the Arabic payload | 2 tests fail |
| Mutation: restore | 20 passed |

Evidence: `CONFIT_evidence/45-mutation-controls-prompt-bound.txt`.

## 8. What a product owner should decide

1. Is a hard rejection the right UX, or truncation with a visible notice?
2. Should the bound differ for authenticated users (a saved stylist session may
   legitimately carry a longer brief)?
3. Is a per-caller cooldown wanted, and what value?
4. Should an identical repeated prompt reuse the cached answer instead of spending
   another provider call?
