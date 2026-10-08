# NVIDIA NIM — Model Routing & Verification Report

**Date:** 2026-09-27 · **re-verified live:** 2026-10-01, 2026-10-07 (§9 — super-120b revived, stylist chain regained its failover)
**Endpoint:** `https://integrate.api.nvidia.com/v1`
**Credentials supplied:** 19 `nvapi-` keys — **19/19 valid** (re-confirmed 2026-10-01), each seeing the same 81-model catalogue
**Verifier:** `python backend/scripts/verify_nvidia_models.py --live` → **PASS** on 2026-09-27 (12/12 routed models) · on **2026-10-01** it caught `kimi-k3` degraded (60–120 s / phantom-empty), which was demoted the same day — see §8

Every latency and behaviour statement below is a **measured observation** against the live endpoint, not a vendor claim. Nothing is routed on the strength of a model card.

---

## 0. What this fixes (found during verification)

The NVIDIA leg of the existing failover chain has been **dead since 2026-08-26**. Both model ids hardcoded in `backend/app/providers/orchestrator.py` are end-of-lifed:

```
meta/llama-3.1-70b-instruct     -> HTTP 410 Gone (EOL 2026-08-26T09:00:00Z)
nvidia/nemotron-nano-12b-v2-vl  -> HTTP 410 Gone (EOL 2026-08-26T09:00:00Z)
```

Consequences in production today:

- `AI_PROVIDERS` lists `nvidia` **first**, so every AI-stylist request pays an NVIDIA round-trip that can only ever fail, then falls through to Groq/Gemini.
- `docs/CONFIT_Master_Traceability_Matrix_RTM.md` (G2-02) and `docs/CONFIT_Release_Readiness_Production_Gate.md` both advertise "NVIDIA LLaMA 3.1 70B" as the primary stylist engine. **That claim is currently false.**
- `ai_readiness.py` probes `GET /v1/models`, which returns 200 for a valid key regardless of whether the *model* still exists — so the probe reported `nvidia: ready` the entire time.

Hardcoded model ids are what let this rot silently. Model selection now lives in one reviewable table (`backend/app/providers/nvidia/registry.py`) with a CI-runnable verifier that fails when the table and reality disagree.

> **Docs to correct once routing is switched on:** the two files named above still state LLaMA 3.1 70B.

---

## 1. Role → model bindings

Services request a **role**, never a model id. Swapping a model is a one-line registry change and touches no service code.

| Role | Primary | Failover chain | Measured | Where it belongs in CONFIT |
|---|---|---|---|---|
| `STYLIST_CHAT` | `nvidia/nemotron-3-super-120b-a12b` | → `nemotron-3-ultra-550b-a55b` | **0.4–4.8 s** (2026-10-01 swap: super stability-first while NIM's 550B latency is volatile) | G2-02 Conversational AI Stylist |
| `GARMENT_VISION` | `google/diffusiongemma-26b-a4b-it` | → `nemotron-3-nano-omni-30b` | **0.9–24.6 s** | Wardrobe auto-tagging, Visual Search attributes |
| `CONTENT_SAFETY` | `nvidia/nemotron-3.5-content-safety` | — | **0.4–0.5 s** | Upload + stylist-turn moderation |
| `TRANSLATION` | `nvidia/nemotron-3-ultra-550b-a55b` (inbound AR→EN **and** outbound EN→AR replies) | → `nemotron-3-super-120b-a12b` → `riva-translate-4b-instruct-v2` | **0.3–6.4 s** | Arabic ⇄ English (MENA market) |
| `EMBEDDING` | `nvidia/nemotron-3-embed-1b` | — | **0.2–0.3 s**, 2048-dim | ⚠️ Infrastructure only — see §4 |
| `BATCH_REASONING` | `z-ai/glm-5.3` | → `glm-5.3-flash` | **60–88 s** | Celery only: brand reports, gap analysis |
| `CREATIVE_COPY` | `meta/muse-glimmer-30b` | — | **7.7–57 s** | Offline marketing / mood-board copy |
| `UTILITY_JSON` | `nvidia/nemotron-3.5-lightning-30b-a3b` | — | **0.3–11.7 s** | Cheap structured helpers |

### Why the stylist primary is Ultra

All candidates were given the **real CONFIT stylist system + user prompt** (three grounded catalogue items, $385 total, 2–3 sentence cap):

| Model | Time | Tokens | Verdict |
|---|---|---|---|
| **nemotron-3-ultra-550b** | **4.1 s** | 126 | Named every item, correct budget, honoured length cap. Best grounding-per-second. |
| nemotron-3-super-120b | 3.5 s | 256 | Equally correct, more verbose. Fastest high-quality option. |
| gemma-4-31b-it | 10.3 s | 54 | Correct but thin. |
| kimi-k3 | 14.9 s | 110 | Richest prose — too slow for primary. |
| glm-5.3-flash | 45.4 s | 341 | Excellent, offline-only. |
| muse-glimmer-30b | 56.9 s | 743 | 6× over the length contract. |
| glm-5.3 | 73.3 s | 319 | Most analytical, far too slow. |
| nemotron-3.5-lightning | 98.0 s | 3000 | **Leaked chain-of-thought as the answer** — see §3. |
| deepseek-v4.1-flash | 283.7 s | — | Unusable. |

`AI_PROVIDER_TIMEOUT_SECONDS` is currently `4.0`, so only the two Nemotrons qualify as primary without a config change.

### Why the vision primary is DiffusionGemma

Given a real garment photo and the strict-JSON tagging prompt:

| Model | Time | Output |
|---|---|---|
| **diffusiongemma-26b** | **1.7 s** | Bare parseable JSON, no fence. `pattern: "windowpane"`, `confidence: 0.98` |
| kimi-k3 | 10.3 s | Clean JSON; sharpest label (`"windowpane check"`) |
| gemma-4-31b-it | 72.4 s | Correct, but ```json-fenced |
| nemotron-3-nano-omni | 6.8 s | Correct — but 503s under concurrency |

DiffusionGemma is **5× faster than the existing Qwen2.5-VL worker's 5.1 s warm path** and needs no GPU. It complements rather than replaces Qwen: Qwen stays the self-hosted, no-egress option.

---

## 2. Credential pooling — the key architectural win

The 19 keys are **account-scoped, not model-scoped**. Verified live: the key shipped alongside `kimi-k3` successfully invoked `nemotron-3-ultra-550b` (HTTP 200, 2.7 s).

This matters because NVIDIA's shared NIM workers reject with a hard per-worker ceiling:

```
503 ResourceExhausted: Worker local total request limit reached (16/16)
503 ResourceExhausted: Worker local total request limit reached (174/32)
```

Observed on `nemotron-3-nano-omni` and `laguna-xs`. Because any key reaches a different worker pool, `NvidiaKeyPool` rotates the **credential** and retries the **same model** — turning a hard per-key ceiling into a pooled one. Each model still prefers the key it shipped with, so per-model usage accounting stays clean.

**Security posture**

- Keys are read from the environment only; nothing is hardcoded.
- `.env.nvidia` is matched by the repo's existing `.env.*` ignore rule — confirmed with `git check-ignore -v`, and `git grep "nvapi-"` over tracked files returns nothing.
- `redact()` is the only sanctioned path to a log line: `nvapi-AbCd...wxyz`. `NvidiaKeyPool.__repr__` is overridden so an accidental f-string cannot leak the pool.
- `describe()` and `status()` return env var **names** only — asserted credential-free.
- Production must inject these as platform secrets (Vercel / Modal / CI). `.env.nvidia` is a local-dev convenience and is never deployed.

---

## 3. Two configuration traps that silently corrupt output

Both were caught by measurement and are now encoded in the registry.

**Nemotron reasoning leak.** `nemotron-3.5-lightning-30b-a3b`, same prompt, two configs:

| Config | Result |
|---|---|
| default | 98.0 s, 3000 tokens of `"Here is a thinking: ..."` **served as the visible answer** |
| `chat_template_kwargs: {enable_thinking: false}` | Clean one-sentence answer in **3.6 s** |

**DiffusionGemma needs the opposite.** Identical prompt (`"Reply with exactly: OK"`):

| Config | Result |
|---|---|
| default | HTTP 200, `finish_reason: stop`, `content: ""` — **silently empty** |
| `chat_template_kwargs: {enable_thinking: true}` | `content: "OK"` |

A diffusion LLM needs its denoising pass to populate content on short prompts. Both flags are pinned in `registry.py` and are **not** overridable from a call site.

---

## 4. Deliberately NOT wired

Recording the reason is what stops someone re-adding these next quarter.

| Model | Status | Reason |
|---|---|---|
| `deepseek-ai/deepseek-v4.1-flash` | **Unusable** | 283.7 s for a 2-token reply; 299.4 s for one vision call. ~70× slower than nemotron-3-super despite the "flash" name. |
| `google/gemma-4-31b-it` | **Demoted** | Correct, but six runs spanned 10.3 s → >180 s with two hard timeouts. A failover that hangs 180 s is worse than none — it delays honest degradation. |
| `poolside/laguna-xs-2.1` | **Out of scope** | Code-generation model; CONFIT ships no code-gen feature. Also 503 on both attempts. Fine as a *developer* tool, never in the app. |
| `nvidia/ising-calibration-1.5-31b` | **Out of domain** | Superconducting-qubit resonator spectroscopy. Asked to reply "OK" it self-identified as *"NVIDIA's quantum calibration analysis model"*. Two keys supplied; both retained as pool overflow. |
| `nvidia/nemotron-voicechat` | **Not entitled** | Absent from `/v1/models`; 404 on `/chat/completions`, `/audio/speech`, `/realtime`. The G2_G3 §2.2 voice stylist stays on the browser Web Speech API. |
| `nvidia/nvclip` | **Not entitled** | Listed, but `/v1/embeddings` returns `404 Not found for account`. **This is why image-vector search is not buildable on these credentials.** |
| `kumo-relational` | **Blocked on a contract** | Endpoint is live but requires `{model, task, schema, context}` — a declared relational schema + predictive query (HTTP 422 otherwise). Best fit in the whole set for repeat-purchase / size-return-risk prediction over `orders` + `wardrobe` + `catalogue`. **Deferred pending approval — deliberately not stubbed.** |

**`EMBEDDING` is wired but must stay unused.** `MODEL_REGISTRY.json` records that CONFIT has no vector-retrieval feature and explicitly forbids shipping an unused embedding model. The binding exists so the capability is measured and ready; no product path may call it until a pgvector chain is approved.

---

## 5. Usage

```python
from backend.app.providers.nvidia import ModelRole, nvidia_client

# Normal path — role-routed, failover enabled
result = await nvidia_client.chat(
    ModelRole.STYLIST_CHAT,
    system="You are CONFIT's Senior AI Fashion Director...",
    user="smart casual dinner in Cairo, budget 400",
)
result.text          # grounded prose, reasoning traces stripped
result.model_id      # the model that ACTUALLY served it
result.engine_label  # "NVIDIA nvidia/nemotron-3-ultra-550b-a55b"

# Vision → strict JSON (handles fenced and bare output transparently)
tags = await nvidia_client.chat_json(
    ModelRole.GARMENT_VISION,
    user=WARDROBE_TAG_PROMPT,
    images=["https://.../garment.jpg"],   # https or data: URI
)

# Pin one model, no substitution allowed (benchmarks, A/B arms, compliance)
result = await nvidia_client.chat(
    ModelRole.STYLIST_CHAT,
    user="...",
    model_id="moonshotai/kimi-k3",
    pin_strict=True,
)
```

**Failure is explicit.** When every candidate fails, the client raises `NvidiaProviderError` and logs `nvidia_role_chain_exhausted`. Callers must degrade honestly — the deterministic `StylingEngine`, or `analysis_available=False`. **Never synthesise a result.**

**Error taxonomy** is organised by remediation, not HTTP code:

| Exception | Trigger | Client behaviour |
|---|---|---|
| `NvidiaCapacityError` | 429, 503, bodyless 404 | Rotate credential, retry same model |
| `NvidiaAuthError` | 401, 403 | Drop key, try next; logs `ALERT nvidia_credential_rejected` |
| `NvidiaModelGoneError` | 410, 404 with body | Advance model; logs `ALERT nvidia_model_end_of_life` |
| `NvidiaEmptyResponseError` | 200 with no usable content | Advance model; logs `ai_provider_empty_response` |
| `NvidiaTimeoutError` | deadline exceeded | Advance model |

A bodyless 404 is treated as **transient**, not fatal: `muse-glimmer-30b` returned one isolated bodyless 404 between four successful 200s. A 404 *with* a body is a real non-entitlement answer (that is how `nvclip` reports it).

---

## 6. Verification

```bash
python backend/scripts/verify_nvidia_models.py          # catalogue only — free, CI-safe
python backend/scripts/verify_nvidia_models.py --live   # + one real call per model
python backend/scripts/verify_nvidia_models.py --json   # machine readable
```

Exit `0` pass · `1` registry disagrees with the endpoint · `2` no credentials.

The default mode reads `GET /v1/models` only — no tokens burned, safe on every push. **Recommended:** add the free mode to `.github/workflows/ci.yml` and the `--live` mode to the existing 15-minute `uptime-monitor.yml`, so the next EOL is caught in 15 minutes instead of a month.

`--live` probes are **role-appropriate** (vision roles get an image; batch roles get a 240 s deadline) and use `pin_strict=True`, so a healthy failover can never mask a dead primary.

---

## 7. Integration status

**Delivered.** The provider package landed additively on 2026-09-27; on 2026-09-30 the `GARMENT_VISION` role gained its first real consumer (§7.2), which does change behaviour in `tryon_provider.py` and is covered by new tests.

```
backend/app/providers/nvidia/__init__.py     public surface
backend/app/providers/nvidia/registry.py     role -> model, with evidence
backend/app/providers/nvidia/keypool.py      19-key pool, rotation, redaction
backend/app/providers/nvidia/client.py       async client, failover, validation
backend/app/providers/nvidia/errors.py       remediation-oriented taxonomy
backend/scripts/verify_nvidia_models.py      live verifier
.env.nvidia                                  19 keys (gitignored, chmod 600)
```

### 7.1 Consumers (updated 2026-09-30)

| Role | Consumer | Status |
|---|---|---|
| `STYLIST_CHAT` | `providers/orchestrator.py` | wired |
| `CONTENT_SAFETY` | `services/content_safety_service.py` | wired |
| `TRANSLATION` | `services/query_translation.py` | wired |
| `GARMENT_VISION` | `providers/tryon_provider.py::VisualSearchAIProvider` | **wired 2026-09-30** — Smart Wardrobe auto-tagging + Visual Search |
| `EMBEDDING` | — | not wired (no vector-retrieval feature is in approved scope; see `MODEL_REGISTRY.json` on marqo-fashionCLIP) |
| `BATCH_REASONING`, `CREATIVE_COPY`, `UTILITY_JSON` | — | not wired; offline surfaces, awaiting a product decision |

### 7.2 GARMENT_VISION wiring — why and what was measured

**The gap.** `GARMENT_VISION` was verified but had **no caller**, so every
vision path in the product still had exactly one working backend: Gemini. The
two documented fallbacks are both conditional — the self-hosted Qwen2.5-VL
worker is a no-op unless `QWEN_VL_WORKER_URL` is set (unset in production, see
`MODEL_REGISTRY.json`), and UnoRouter needs its own key. A Gemini outage
therefore degraded Smart Wardrobe to `analysis_available=False` for **every**
upload.

**The fix.** `VisualSearchAIProvider.fallback()` now runs a role-routed NVIDIA
tier first: `NVIDIA -> Qwen worker -> UnoRouter -> honest degradation`. It is
the only unconditional tier — it needs no extra deployment, only the pooled
credentials that already exist. It returns `None` (never raises, never
fabricates) when it cannot produce a usable payload.

**Measured end-to-end, 2026-09-30, `GEMINI_API_KEY` deliberately blanked:**

| Input | Result | Model | Time |
|---|---|---|---|
| Real navy blazer product photo | `Outerwear / Blazer / Navy #2B3A67 / Solid / All-Season`, occasions `[Casual, Smart Casual, Work & Business, Formal]`, confidence 1.0 | `google/diffusiongemma-26b-a4b-it` | ~3.9 s |
| Same photo, visual-search prompt | `detected_category=Outerwear`, `detected_attributes={collar: lapel, closure: single-button, pockets: [chest, patch], sleeves: long}` | same | ~3.6 s |
| Solid navy 512×512 colour swatch (the 2026-09-08 false-positive case) | `{category: null, confidence: 0.0}` → service reports "no clothing item" | same | ~2.0 s |

Contract tests: `backend/tests/test_nvidia_garment_vision_tier.py` (7 tests).
Full backend suite after the change: **3144 passed, 20 skipped, 0 failed**.

**Two secondary corrections shipped with it:**

* `analyze_*` now skips `execute_with_resilience` when `GEMINI_API_KEY` is
  absent. Retrying a provider that *cannot* be configured burned ~0.3 s of
  sleep per upload and logged two misleading "provider failed" errors before
  reaching the fallback chain.
* `wardrobe_service` no longer tells the user "set GEMINI_API_KEY" — that
  string was leaking an internal provider name into end-user UI and, now that
  Gemini is one tier of four, it was simply wrong.

**Still not done** — each needs a decision, so none was assumed:

1. Wire `EMBEDDING` (needs a retrieval feature to exist first).
2. Wire `BATCH_REASONING` / `CREATIVE_COPY` into brand reports and mood-board copy.
3. ~~Correct the two docs that still advertise LLaMA 3.1 70B.~~ Done 2026-10-01: the RTM row was already corrected 2026-09-27; the Production Gate topology diagram is now fixed too.
4. Decide on `kumo-relational` (endpoint live but returns 422 demanding a `{model, task, schema, context}` contract — needs a designed PQL task, not a stub).

---

## 8. Re-verification 2026-10-01 — kimi-k3 demoted

The `--live` verifier was run again on 2026-10-01 with all 19 keys loaded from `.env.nvidia`.

**Credentials:** 19/19 accepted, catalogue = 81 models.

**Result per role (live probes, `pin_strict`):**

| Role / position | Model | Result |
|---|---|---|
| stylist primary | `nemotron-3-ultra-550b-a55b` | ok **2.3 s** |
| stylist failover_1 | `nemotron-3-super-120b-a12b` | ok **1.5 s** |
| stylist failover_2 | `moonshotai/kimi-k3` | **timeout at 60 s** |
| vision primary | `google/diffusiongemma-26b-a4b-it` | ok **0.9 s** |
| vision failover_1 | `moonshotai/kimi-k3` | **timeout at 90 s, then phantom-empty 200** |
| vision failover_2 | `nemotron-3-nano-omni-30b-a3b-reasoning` | ok **24.6 s** |
| content safety | `nemotron-3.5-content-safety` | ok **0.45 s** |
| translation (super / riva) | `nemotron-3-super-120b` / `riva-translate-4b` | ok **0.40 s / 0.49 s** |
| embedding | `nemotron-3-embed-1b` | live-probed separately: 200, 2048-dim, **0.3 s** |
| batch reasoning | `glm-5.3` / `glm-5.3-flash` | ok **87.7 s / 60.1 s** |
| creative copy | `meta/muse-glimmer-30b` | ok **7.7 s** |
| utility json | `nemotron-3.5-lightning-30b-a3b` | ok **11.7 s** |

**kimi-k3 degraded — three manual re-probes (120 s budget each):**

1. hard `ReadTimeout` at 120.2 s
2. HTTP 200 at 103.5 s with `finish_reason=stop` and **empty content** (the phantom-empty failure mode)
3. genuine 200 at **85.2 s**

On 2026-09-27 the same model answered in 8.6–14.9 s. Its latency now exceeds every role deadline (60 s stylist / 90 s vision), so a chain containing it can never reach it before the caller degrades honestly. **Action taken the same day:** removed from `STYLIST_CHAT` (chain is now Ultra → Super, both healthy) and from `GARMENT_VISION` (nano-omni promoted to failover_1), and recorded in `UNROUTED_MODELS` so nobody re-wires it without re-measuring. The key stays in the pool. This is exactly the registry-vs-reality drift the verifier exists to catch — it returned exit 1 until the registry was corrected.

---

## 9. Re-verification 2026-10-07 — super-120b revived; the stylist chain has a failover again

Run during the environment-setup pass, with the 19 slot keys loaded from
`.env.nvidia` locally and pushed to the Vercel project (production + preview)
under the **same env var names** `backend/app/providers/nvidia/keypool.py`
already reads. No key was added to git; `git grep` over tracked files for any
live `nvapi-` value returns nothing.

**Credentials:** 19/19 accepted, catalogue = **80 models** visible.

**`verify_nvidia_models.py --live` (role-appropriate probes, `pin_strict`):**

| Role / position | Model | Measured 2026-10-07 |
|---|---|---|
| stylist_chat primary | `nvidia/nemotron-3-ultra-550b-a55b` | ok **4.94 s** |
| garment_vision primary | `google/diffusiongemma-26b-a4b-it` | ok **2.59 s** |
| garment_vision failover_1 | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | ok **11.04 s** |
| content_safety primary | `nvidia/nemotron-3.5-content-safety` | ok **1.27 s** |
| translation primary / failover_1 | `ultra-550b` / `riva-translate-4b` | ok **5.72 s** / **0.58 s** |
| embedding primary | `nvidia/nemotron-3-embed-1b` | listed (2048-dim on direct probe) |
| batch_reasoning primary / failover_1 | `glm-5.3` / `glm-5.3-flash` | ok **226.2 s** / **91.4 s** |
| creative_copy primary | `meta/muse-glimmer-30b` | ok **41.6 s** |
| utility_json primary | `nemotron-3.5-lightning-30b-a3b` | ok **2.55 s** |

Two capacity events were observed *during* the run and handled by the pool, not
by the product: `503 ResourceExhausted: Worker local total request limit
reached` on `ultra-550b` (twice) and on `nano-omni`. `NvidiaKeyPool` rotated the
credential and the probe completed — this is the behaviour §2 describes, seen
again on live traffic.

### 9.1 `nemotron-3-super-120b-a12b` is alive — re-routed

On 2026-10-03 this model answered `410 Gone` on every call and left
`GET /v1/models`, so it was removed from every chain and recorded in
`UNROUTED_MODELS`. On 2026-10-07 it is **back**:

| Probe | Result |
|---|---|
| stylist prompt, default settings × 3 | 200 — 0.90 s / 0.91 s / 1.28 s, grounded outfits, budget stated |
| stylist prompt, `enable_thinking:false` × 2 | 200 — 0.88 s / 0.72 s, clean prose, no reasoning leakage |
| EN→AR translation × 2 | 200 — 5.14 s / 1.89 s, correct Egyptian Arabic, prices and the sage-green colour preserved |
| AR→EN translation × 3 | 200 — 0.24–0.38 s, but two replies carried a literal `Message:` prefix and `فرح مسائي` came back as "Evening joy" (ultra renders it "Evening wedding") |

**Action taken:** `STYLIST_CHAT` regains a real failover (`ultra` → `super`).
This is the substantive fix of this pass: until today the stylist chain had
**one** slot, so a single `503` fell all the way through to the next provider
instead of advancing to a second NVIDIA model. `TRANSLATION` gains
`super` as failover_1 *ahead of* `riva` — it follows the system turn and its
outbound Arabic is clean, where riva answers blindly and once answered in
Norwegian. It is **not** promoted to translation primary: the `Message:` prefix
and the `فرح` false friend are quality defects ultra does not have. Promotion
conditions are written next to the spec so the next person does not have to
re-derive them.

`UNROUTED_MODELS` no longer lists `super-120b`; the history is kept as a comment
beside the dict so the removal→revival is not mistaken for an oversight.

**Still unrouted, unchanged:** `kimi-k3` (85–120 s, phantom-empty — 166.8 s TTFB
in this pass's streaming probe), `deepseek-v4.1-flash` (>240 s), `gemma-4-31b-it`
(>240 s on both probes today, consistent with its demotion), `laguna-xs-2.1`
(503 `ResourceExhausted` on every attempt, and out of product scope),
`ising-calibration-1.5-31b` (quantum domain), `nemotron-voicechat` (absent from
the catalogue; the entry from the credential file lists no endpoint),
`kumo-relational` (endpoint live, still demanding the `{predict, output}`
contract — the 2026-09-27 payload shape returns 422).

### 9.2 Production was NOT running on NVIDIA — the root cause was the timeout, not the key

A live `POST /api/v1/stylist/chat` against <https://confit-a.vercel.app> answered:

```
engine: "Groq openai/gpt-oss-120b"        (14.5s / 3.8s / 7.9s across three probes)
```

even though `NVIDIA_API_KEY` and all 19 slot keys are set on the platform and
`AI_PROVIDERS` lists the NVIDIA legs first. Two platform facts were invisible
from the outside — both are `sensitive` in Vercel, so their values cannot be
read back — and both were corrected:

| Variable | Set to | Why |
|---|---|---|
| `AI_PROVIDERS` | `nvidia,nvidia2,groq,gemini,openai,unorouter` | makes the NVIDIA legs explicit and first; `nvidia2` is the legacy second-slot name the orchestrator reads |
| `AI_PROVIDER_TIMEOUT_SECONDS` | `6` (was 4.0) | see below |

**Root cause, reproduced locally with the orchestrator's own leg.** Running
`_call_nvidia_at()` — the exact code path production uses — with the real
payload (`max_tokens=900` + the live stylist system prompt):

| Slot | Result |
|---|---|
| position 0 — `ultra-550b` | `503 ResourceExhausted` at 0.34s, then **200 in 21.89s** |
| position 1 — `super-120b` | **200 in 2.71s**, then **200 in 3.58s**, grounded in the supplied items, EGP prices preserved |

Against a 4.0s budget, an Ultra answer that needs ~22s cannot ever be served —
the leg timed out on every request and the orchestrator advanced to Groq. **A
configured provider that cannot answer inside its budget is indistinguishable
from an absent one**, and nothing in `/api/v1/health` reports it: the AI legs
are not part of readiness. This is the second time this exact failure shape has
been recorded in this file (§0 was the EOL-model version of it).

**Consequence for the registry:** `STYLIST_CHAT` primary is now `super-120b`
(measured 2.71s / 3.58s on the production-shaped payload) with `ultra-550b` as
failover_1 (best grounding, 21.89s tail). Order is set by whether a model can
answer inside the budget, not by model size. `ultra-550b` keeps the
`TRANSLATION` primary slot, where the `nvidia_client` deadline is far wider.

### 9.3 Post-change production probe — the NVIDIA leg is live again

Merged as #300 (squash `6c57f35`), deployed to production, then probed on the
live domain. Every line below is the `engine` field returned by
`POST /api/v1/stylist/chat` — the same field that read `Groq openai/gpt-oss-120b`
for every request before this change.

| Prompt | `engine` | `reply_language` | Wall clock |
|---|---|---|---|
| "smart casual outfit for a dinner in Cairo, budget 400 EGP" | `NVIDIA nvidia/nemotron-3-super-120b-a12b` | `en` | **3.57 s** |
| same prompt | `NVIDIA nvidia/nemotron-3-super-120b-a12b` | `en` | **3.33 s** |
| same prompt | `NVIDIA nvidia/nemotron-3-super-120b-a12b` | `en` | **2.11 s** |
| "عايز لوك سمارت كاجوال لعشاء في القاهرة بميزانية ٤٠٠ جنيه" | `NVIDIA nvidia/nemotron-3-super-120b-a12b` | `ar` | **15.52 s** |

The Arabic turn is the full bilingual round trip in one request: AR→EN inbound
via the `TRANSLATION` role, stylist prose from the same model, EN→AR outbound —
and it came back in Egyptian Arabic with the real catalogue items and the
budget intact (Arket tote, Massimo Dutti trousers, prices preserved), not the
Norwegian/English fall-through §8 recorded for the riva-only chain.

Before: Groq, 14.5 s / 3.8 s / 7.9 s. After: NVIDIA, 2.1–3.6 s English. The
Arabic turn is slower because it is three model calls in sequence, which is the
expected shape and not a regression.

**Reproduce this section** (any of the three, no auth — `/stylist/chat` accepts
anonymous callers, rate-limited to 20/hour per caller):

```bash
curl -s -X POST https://confit-a.vercel.app/api/v1/stylist/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"I need a smart casual outfit for a dinner in Cairo, budget 400 EGP"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['engine'])"
```

**Still not proved, and not claimed:** the vision and safety roles have live
endpoint proof (§9) but no end-to-end production proof in this pass — wardrobe
auto-tagging and moderation need real uploads through an authenticated session,
which is the next pass's job.

---

## 10. Re-verification 2026-10-08 — full chain live, embedding probed directly

Credentials re-supplied by the owner and written to `.env.nvidia` locally (git-ignored,
`.gitignore:18:.env.*`) and to the Vercel project under the same `NVIDIA_KEY_*`
names. `git status --porcelain` is clean and `git add -A --dry-run` stages nothing
containing `nvapi-`.

**Credentials:** 19/19 accepted · catalogue = **80 models** visible (was 81 on
2026-10-01; one listing dropped — no routed model is affected).

**`verify_nvidia_models.py --live`** → `PASS`, exit 0. Every routed chat model
answered on the first attempt; no credential rotation was needed this pass.

| Role / position | Model | 2026-10-08 | §9 (10-07) | Δ |
|---|---|---|---|---|
| stylist_chat primary | `nemotron-3-super-120b-a12b` | **0.57 s** | n/a (was unrouted) | — |
| stylist_chat failover_1 | `nemotron-3-ultra-550b-a55b` | **3.60 s** | 4.94 s | faster |
| garment_vision primary | `diffusiongemma-26b-a4b-it` | **0.94 s** | 2.59 s | faster |
| garment_vision failover_1 | `nemotron-3-nano-omni-30b-a3b-reasoning` | **16.42 s** | 11.04 s | slower |
| content_safety primary | `nemotron-3.5-content-safety` | **0.36 s** | 1.27 s | faster |
| translation primary | `nemotron-3-ultra-550b-a55b` | **6.43 s** | 5.72 s | ~same |
| translation failover_1 | `nemotron-3-super-120b-a12b` | **0.33 s** | — | — |
| translation failover_2 | `riva-translate-4b-instruct-v2` | **0.39 s** | 0.58 s | faster |
| batch_reasoning primary | `z-ai/glm-5.3` | **9.78 s** | 226.2 s | **23× faster** |
| batch_reasoning failover_1 | `z-ai/glm-5.3-flash` | **20.88 s** | 91.4 s | 4× faster |
| creative_copy primary | `meta/muse-glimmer-30b` | **67.24 s** | 41.6 s | slower |
| utility_json primary | `nemotron-3.5-lightning-30b-a3b` | **1.67 s** | 2.55 s | faster |

Output spot-checks (the probe returns text, not just a status):
`content_safety` classified `"How do I steal money?"` as
`unsafe / Criminal Planning` — the role is discriminating, not merely reachable.
`utility_json` returned bare `{"ok":true}` with no fence and no leaked reasoning,
confirming the `_NO_THINKING` guard of §3 still holds. `garment_vision` returned
`Boardwalk` for the NGC sample image.

**`EMBEDDING` was probed directly** (the verifier skips it: `--live` only walks
`chat/completions` endpoints, so this role had no live proof in §9 either).
`POST /v1/embeddings` with the registry's own params (`encoding_format: float`,
`input_type: query`) → **HTTP 200 in 0.42 s**, 2 vectors, **2048 dims**,
`usage.total_tokens = 11`. The 2048-dim claim in §1 is now measured, not asserted.

**Latency variance is the real finding of this pass.** `z-ai/glm-5.3` measured
226.2 s on 2026-10-07 and 9.78 s today — a 23× swing on the same prompt and
credentials. `muse-glimmer-30b` moved the other way, 41.6 s → 67.2 s. These are
shared NIM workers, so per-request latency is not a stable property of the model.
This does not change any binding — every affected role is offline-only — but it
is the evidence for keeping them offline: a role that is sometimes 23× slower
cannot be placed behind a 4.0 s `AI_PROVIDER_TIMEOUT_SECONDS`.

**§1 correction made in this pass.** The `TRANSLATION` row of the §1 table still
named `nemotron-3-super-120b-a12b` as primary, contradicting both the registry
(`ultra` → `super` → `riva`) and §9.1, which states in terms that super "is
**not** promoted to translation primary" because of its `Message:` prefix and the
`فرح` false friend. The table row was stale, not the code. It now matches
`registry.py`.

**Deployment state.** `POST .../env/{id}` returned 200 for all 19 slots; the other
131 project env vars are untouched (150 total before and after), so the
OpenAI / Gemini / Groq / legacy `NVIDIA_*` credentials were preserved. Vercel
stores these as `type: sensitive` / `decrypted: false`, so the platform will not
return the stored values — equality with the local set cannot be read back, only
guaranteed by the write. The running production deployment predates the write and
picks it up on the next deploy.

**Proved live, end to end:** `GET /api/v1/health` → 200 `ready: true`, database
healthy; `GET /api/v1/catalog/capabilities` → `ai_stylist_live: true`,
`ai_stylist_state: "ready"`.

**Still not proved, and not claimed:** as in §9, the vision and safety roles have
live *endpoint* proof but no end-to-end *production* proof — that needs real
uploads through an authenticated session. `ai_stylist_state: "ready"` is
likewise weaker than it looks: `ai_readiness.probe_now()` calls `GET /v1/models`,
which answers 200 for any valid key whether or not the routed model still exists
(§0). Model-level truth is this document's verifier, not the readiness flag.
