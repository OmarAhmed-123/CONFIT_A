# CONFIT_A — Release Audit V8 (Authoritative)

**Date:** 2026-09-03 · **Branch:** `final-no-excuses-release-gate` · **Head:** `66bb2dd`

This report supersedes V3–V7. Every prior "final" report was treated as untrusted input and re-derived from primary evidence. Where I could not obtain primary evidence, the claim is labelled `UNVERIFIED — EXTERNAL BLOCKER` and is **not** upgraded on the strength of code review, configuration, or a green CI badge.

---

## 1. FINAL DECISION

> ## **NOT PRODUCTION READY**

The blocking item is **VTON BRD compliance** (§9). Everything else in the brief is now resolved, and four real defects — three of them previously undetected by any report or test — were found and fixed during this audit.

This is a *downgrade* from prior reports, and it is driven by one honest question: does the try-on feature do what the BRD says it does? It does not, and no amount of green tests changes that.

---

## 2. GIT STATE — the contradiction resolved

Prior reports circulated four different "final SHAs". They were conflating three distinct things. Disambiguated:

| Question | Answer |
|---|---|
| **FINAL MAIN SHA** | **`5c366565a143516da349250829c0463b66567283`** |
| Latest **code-changing** PR | **#28** |
| Latest **documentation** PR | **#27** |
| **Code** merge SHA | `5c36656` (PR #28) |
| **Documentation** merge SHA | `7bad184` (PR #27) |

Notes that matter:

- `7bad184` is a **documentation** merge and an **ancestor** of `5c36656`. Reports that named it "final" were naming a docs commit as the release SHA.
- `2debcdc` and `f8b10ad` appear in prior reports as final SHAs. **Neither is main's HEAD.** Per your standing instruction they were not trusted, and inspection confirms they are not the tip.
- `1e52bc3` is the head of `fix/final-truth-audit-remediation` (PR #29, still open, `mergeable_state=unstable`). Not on main.
- **This audit's work is `66bb2dd`**, 7 commits ahead of main on `final-no-excuses-release-gate`. Not merged. Nothing in this report claims to be main.

---

## 3. TEST ACCOUNTING — Local vs CI, reported separately

Counted from run output, never inferred, never carried over from a prior report.

### Local (this sandbox, `66bb2dd`)

```
466 passed, 1 skipped, 19 warnings in 79.00s
```

| | |
|---|---|
| Collected | 467 |
| Passed | 466 |
| Failed | 0 |
| Skipped | 1 |
| xfail / xpass | 0 |
| Deselected | 0 |
| Timeout | **0** (was ~120s — root cause fixed, §4) |

The 1 skip is `TestRealSegmentationModelPath`, opt-in by design (§8).

### CI (GitHub Actions run `33737205759`, `66bb2dd`)

```
466 passed, 1 skipped, 20 warnings in 92.40s
```

`ci` = **success**. `gitleaks` = **failure**, intentionally (§11).

**Local and CI agree exactly at 466/1.** That agreement is itself a finding — before this audit they did not agree, and §8 explains why.

CI success is reported here as `CI-VERIFIED` only for *the fact that the job passed*. The per-test counts above come from parsing the pytest summary line in the downloaded job log, not from the badge.

---

## 4. The 120s local timeout — ROOT CAUSE FOUND AND FIXED

Prior reports dismissed this as environmental, or waved at CI passing. It was neither. It was a **real production latency defect**.

**Mechanism.** `WardrobeService.bulk_upload` calls `auto_tag_wardrobe_task.delay()`, which is synchronous. With Redis unreachable, kombu's default policy retries **20 times at 1s intervals** before raising. Every upload therefore blocked its HTTP request for ~20 seconds, emitting `Connection to Redis lost: Retry (n/20)`. Several upload tests each paid that cost; together they blew the budget.

The caller already had an inline-analysis fallback for an unavailable broker. It simply took 20 seconds to find out.

**The subtle part, and why an obvious fix silently failed.** The redis result backend **ignores `max_retries` at the top level** of `result_backend_transport_options`. `RedisBackend.retry_policy` merges only a *nested* `"retry_policy"` key over `Backend.retry_policy` (`max_retries=20`, `interval_step=1`). My first attempt set it top-level, looked correct, and changed nothing — the storm continued at exactly 20×1s. Verified by reading `celery/backends/redis.py:391-397` and `celery/backends/base.py:130`.

**Measured, RUNTIME-VERIFIED:**

| | Before | After |
|---|---|---|
| Enqueue vs dead broker | 19.1s | **0.6s** |
| `test_group4_wardrobe_smart_reuse.py` | 106s | **15s** |
| Full backend suite | 170s | **79s** |

No test was skipped, weakened, or retimed. The work itself is gone. `test_broker_unavailable_latency.py` asserts the *resolved* `celery_app.backend.retry_policy`, so a regression to the ineffective top-level form fails the build.

Commit `66bb2dd`.

---

## 5. Decimal domain boundary — TEST-VERIFIED, with one documented limitation

| Requirement | Status | Evidence |
|---|---|---|
| `backend/app/core/money.py` canonical | ✅ VERIFIED | Sole definition of the rounding policy |
| Single money utility, no duplicates | ✅ VERIFIED | `ROUND_HALF_UP` appears in only 2 other files, each a single legitimate minor-unit conversion, not a parallel utility. (`composer.py` imports it without using it — dead import, cosmetic.) |
| One rounding policy: prec 28, ROUND_HALF_UP, 2dp | ✅ VERIFIED | `money.py` |
| `to_float()` only at serialization/presentation | ✅ VERIFIED | 32 call sites, **0 in financial arithmetic** |
| NUMERIC(12,2) range validation | ✅ VERIFIED | `MAX_MONEY = 9999999999.99`, `MIN_MONEY` symmetric, explicit raise on overflow (`money.py:89-107`) |
| No float re-entry | ⚠️ **PARTIALLY VERIFIED** | see below |

**The limitation, stated plainly.** Two Pydantic schemas type `price_override` as `Optional[float]` (`schemas/brand.py:29`, `schemas/catalog.py:23`). A B2B price edit therefore crosses the API boundary as an IEEE-754 double before reaching `to_decimal()`.

This is **not** currently corrupting data: `to_decimal()` converts via `str()`, so `0.1+0.2 → 0.30` and `8.475 → 8.48` quantize correctly. But it is a float in the money path, and the invariant "no float re-entry" is therefore *not* absolute. Typing these as `Decimal` or `condecimal` would close it. I did not change it in this pass because it touches the public API contract and warrants its own review.

**`toFixed(2)` is formatting, not arithmetic.** 28 occurrences in the frontend, all presentational. No frontend code performs money arithmetic; the server is authoritative. Frontend money safety: **BUILD-VERIFIED** + CODE-VERIFIED.

---

## 6. Migrations 0012 / 0013 — one real defect found and fixed

**0012** (money → NUMERIC): historical CAST semantics validated. CODE-VERIFIED.

**0013** (audit + quarantine): I ran the actual `upgrade()` against a throwaway database rather than reading it. **RUNTIME-VERIFIED.**

**Defect found.** 0013 had two quarantine paths. The first (rows carrying 0011's invented `0.5`/`50.0` defaults) wrote a `migration_audit_log` row before pausing. The second — the `invalid_checks` loop covering `bid <= 0`, `budget <= 0`, `bid > budget`, `bid > 100`, `budget > 10000`, `spent < 0`, `spent > budget` — issued a **bare UPDATE and wrote nothing**. A placement could be paused with no record of why, or of the value that triggered it.

Demonstrated on a 4-row fixture: rows 2 and 3 were paused with **zero** audit rows. After the fix, every quarantined row is audited with its offending field and value, logged *before* mutation.

**Data-integrity language, precisely.** I will not say "no data loss".

- **Row count is preserved.** Rows are paused, never deleted. ✅
- **`original_value` is the value 0013 OBSERVED.** Where migration 0011 already overwrote an operator's figure with an invented default, that original input is **IRRECOVERABLE from this table and requires a backup.**
- 0013 does not and cannot restore it. It quarantines the row for operator review. The audit row for such a placement records the `status: active → paused` transition — **not** a fabricated pre-0011 bid.
- What exists is **audit metadata**, not a recovery mechanism.

`test_migration_0013_quarantine_audit.py` (6 tests) runs the real migration; confirmed to fail 2/6 against the pre-fix version. Commit `feebf18`.

---

## 7. Attribution & analytics — item grain now proven end-to-end

**Gap in prior verification.** `test_attribution_behavioral_e2e.py` drives `BrandRepository` directly. That proves the repository, **not** the instrumentation inside `CommerceService.checkout()`. The item-grain claim rested on tests that never invoked the code path that emits the events.

I added `test_attribution_item_grain_e2e.py`, which POSTs a real multi-brand, multi-quantity cart to `/api/v1/commerce/checkout` and asserts against the rows it wrote:

- exactly **one purchase event per OrderItem**;
- each event carries **its own item subtotal** and **its own brand**;
- **exact-Decimal conservation**: `Σ event revenue == Σ item subtotals`;
- **no event inflated to the order total**.

**Mutation-tested — both mutations killed:**

| Mutation | Result |
|---|---|
| `revenue_amount=order.total_amount` instead of item subtotal | **KILLED** (1 failed) |
| idempotency key collapsed to `purchase_{order.id}` | **KILLED** (2 failed) |

**`BrandAnalyticsEvent` granularity — a structural weakness, documented not hidden.** The model has **no `order_item_id`**. Purchase → OrderItem is reconstructed via `(order_id, product_id, sku_id)`. That reconstruction is sound *only because* the cart deduplicates by SKU (`commerce_repository.py:157`), so an order cannot hold two lines with the same SKU. The new test asserts that uniqueness explicitly and **fails loudly** if the invariant ever breaks, rather than silently mis-attributing. Adding `order_item_id` would make this structural instead of circumstantial; recommended, not blocking.

`log_audit()`: **19 real call sites**, not stubs. Visual-search matrix: covered by `test_visual_search_extended.py` plus the behavioural suite, with correct product/user identity semantics (attribution requires a `visual_search` view event for the **same product and same user** within 30 days).

Commit `2dfe354`.

---

## 8. VTON — four defects, three of them found by *running* the code

This is where the audit diverged hardest from every prior report.

### Finding #1 — Three competing implementations; Docker shipped the fake one

| Path | Engine | Reachable how | Real diffusion? |
|---|---|---|---|
| `modal_app.py` | CatVTON + SD1.5-inpainting | Modal deploy | **Yes** |
| `worker.py` | affine warp + composite | **`Dockerfile` CMD** | **No** — `model_loaded=False` |
| `pipeline/segmentation.py` | rembg U2Net masks | `worker.py` + tests | n/a |

The container entrypoint selected a placeholder that returns `status="completed"` while performing no inference. It was reachable in production: `_get_worker_config()` gates solely on `VTON_WORKER_URL` and **never consults `settings.VTON_PROVIDER`** (default `"hybrid"`, `config.py:86`). The echo-guard (`rendered == person_image`) cannot catch a warp-composite.

Mitigating: no compose/CI/deploy script builds that Dockerfile. Aggravating: **20 passing mask tests validated code the Modal deployment never loaded** — `rembg` was absent from the Modal image entirely.

Fixed: placeholder and its four placeholder engines deleted; Dockerfile no longer defines a server CMD; `pipeline/__init__.py` exports only the three real engines. Commit `8ee73de`.

### Finding #2 — Inverted mask polarity in the only real-diffusion path

Upstream CatVTON computes `masked_image = image * (mask < 0.5)` (`model/pipeline.py:132`) — **WHITE means REGENERATE**. `modal_app.py` built a rectangle that filled the garment region **black**. It preserved the garment and regenerated everything around it.

Verified against a fresh clone of upstream, not against our own reports. CODE-VERIFIED (GPU runtime unavailable). Fixed in `73c1e0c`.

### Finding #3 — rembg session leak (found by running it, not reading it)

`_try_rembg_person_mask` called `new_session()` on **every** mask request, inside a per-slot loop. A five-garment try-on loaded the ~176MB ONNX model five times. Reproduced as a pytest **OOM kill (exit 137)**.

Fixed with a process-wide session plus a content-hash parse cache. **Measured: five-slot masking 15s → 3ms; first parse 2910ms → 0ms cached.** RUNTIME-VERIFIED.

### Finding #4 — Degenerate segmentation trusted blindly

rembg returned a **2.2%-coverage** mask on out-of-distribution input and the result was used unchecked — which would hand CatVTON a near-empty agnostic mask and regenerate nothing. Added a coverage plausibility gate (4%–97%); implausible output now falls back and reports `fallback_used=True` **honestly**, rather than passing off a broken mask as a good one. Commit `0dbe26b`.

### Masking quality — RUNTIME-VERIFIED

`rembg[cpu]` + `onnxruntime` were installed in this sandbox, so masking is genuinely runtime-verifiable here. Real `rembg-u2net_human_seg` inference on a real photograph (800×800), all 6 slots `valid=True` with correct y-bands:

| slot | white ratio |
|---|---|
| upper_inner | 0.094 |
| upper_outer | 0.251 |
| lower | 0.102 |
| footwear | 0.009 |
| accessory | 0.048 |
| dress | 0.293 |

Visually inspected contact sheet: `/home/user/vton_mask_evidence.png`. Masks are person-shaped and correctly localised.

### Why the test suite now pins the heuristic path

The ONNX session costs **~900MB RSS** (measured). That OOM-kills small runners, and it made mask geometry depend on whether an optional dependency happened to be installed.

This was not hypothetical. **On pristine main with rembg present, 3 mask tests FAIL** (`384 passed, 3 failed`). CI passed only because rembg was absent. The suite was green for the wrong reason.

`conftest.py` now pins `CONFIT_VTON_DISABLE_REMBG=1` by default so assertions are reproducible everywhere, and the real model path is retained as an **opt-in** class (the 1 skip in §3). This is not weakening a test — it is removing a hidden environmental dependency, and adding coverage that did not exist before.

### VTON BRD compliance — THE BLOCKING DECISION

| BRD requirement | Reality |
|---|---|
| Photorealistic garment warping | CatVTON diffusion exists in `modal_app.py` — **never executed in any verifiable environment** |
| Deep-learning segmentation | rembg U2Net — **RUNTIME-VERIFIED** ✅ |
| Production try-on output | Heuristic Otsu+skin fallback whenever rembg is unavailable |

Segmentation is genuinely good and now genuinely proven. **The diffusion step is not.** The only path that performs real garment synthesis requires Modal GPU infrastructure that I have no access to, and until this audit that path shipped with an **inverted mask** — meaning even if it had run, it would have regenerated the wrong region.

Per your standing instruction, I will not call heuristic masking production-quality, and I will not upgrade Modal GPU inference to verified on the strength of code review. **This decides the release: NOT PRODUCTION READY.**

---

## 9. Security, secrets, build

| Check | Result |
|---|---|
| Security / auth / RBAC / rate-limit regression | **104 passed** (1 order-dependent failure under `-k` selection only; passes in the full suite — flagged as a test-isolation nit, not a security finding) |
| Mutation-style release-contract tests | 10/10 previously + **2/2 new attribution mutations killed** |
| Frontend money safety | CODE-VERIFIED (`toFixed(2)` presentational only) |
| `npm run build --prefix frontend` | ✅ **BUILD-VERIFIED** — `tsc && vite build`, 162 modules, exit 0 |
| `gitleaks` | ❌ **RED, correctly** |

**gitleaks is red on purpose and must stay red.** `leaks found: 1` — a real Neon Postgres DSN with an embedded password at commit `6a821de`, `backend/app/core/database.py`, rule `database-dsn-with-password`. **The credential is in immutable git history. The only correct remediation is to rotate the Neon credential**, not to allowlist the finding.

The allowlist was reviewed and is **narrowly scoped**: placeholders (`YOUR_PASSWORD`, `CHANGE_ME`), one local docker-compose dev password, a truncated JWT *header* example, and two doc phrases. It does **not** allowlist the real DSN. I did not extend it.

---

## 10. External blockers — genuinely absent access

Not upgraded on the basis of code compatibility, configuration, or CI.

| System | Status |
|---|---|
| Neon / Postgres (production) | `UNVERIFIED — EXTERNAL BLOCKER` |
| Redis (live broker) | `UNVERIFIED — EXTERNAL BLOCKER` — though *broker-down* behaviour is now RUNTIME-VERIFIED (§4) |
| Modal GPU / CatVTON inference | `UNVERIFIED — EXTERNAL BLOCKER` — **the release-blocking gap** |
| Gemini / NVIDIA APIs | `UNVERIFIED — EXTERNAL BLOCKER` |
| Browser E2E | `UNVERIFIED — EXTERNAL BLOCKER` |

Claude Opus 4.8 TD was **not** available and was **not** used. No claim in this report depends on it.

---

## 11. What changed (7 commits, `main..66bb2dd`, 28 files, +1624 / −652)

| SHA | Change |
|---|---|
| `8ee73de` | Remove the non-diffusion placeholder worker that Docker actually ran |
| `73c1e0c` | Correct inverted mask polarity in the deployed diffusion worker |
| `0dbe26b` | Stop leaking an ONNX session per mask; reject degenerate masks |
| `a8b4728` | Gate the single production path; make mask tests deterministic |
| `2dfe354` | Prove item-grain revenue through the real checkout endpoint |
| `feebf18` | Audit every quarantined placement, not just the invented-default ones |
| `66bb2dd` | Bound broker retries so enqueue fails fast when Redis is down |

Branched from actual current main. No work on main. No documentation-only "final" PR.

Also removed one piece of test theater: `assert True  # verified via code inspection` is now a real AST assertion that every per-layer diffusion failure reports `failed_layer`.

---

## 12. What must happen before this can be PRODUCTION READY

1. **Deploy `modal_app.py` to Modal and produce real try-on output** with the corrected mask polarity. Until a human looks at a generated image, VTON is unverified. *(blocking)*
2. **Rotate the Neon credential** exposed at `6a821de`. Do not allowlist it. *(blocking)*
3. Decide `VTON_PROVIDER` semantics — it is currently defined but never consulted.
4. Type `price_override` as `Decimal` to close the last float ingress (§5).
5. Add `order_item_id` to `BrandAnalyticsEvent` to make item grain structural (§7).
6. Fix the order-dependence in `test_platform_admin_has_global_oversight`.

Items 3–6 are not release-blocking on their own.

---

## Verification labels — summary

| Claim | Label |
|---|---|
| Mask geometry & segmentation quality | **RUNTIME-VERIFIED** |
| Session-leak and degenerate-mask fixes | **RUNTIME-VERIFIED** |
| Broker fast-fail (19.1s → 0.6s) | **RUNTIME-VERIFIED** |
| Migration 0013 quarantine + audit population | **RUNTIME-VERIFIED** |
| Item-grain attribution & revenue conservation | **TEST-VERIFIED** (mutation-killed) |
| Decimal boundary / rounding / NUMERIC range | **TEST-VERIFIED** |
| No float re-entry | **PARTIALLY VERIFIED** (§5) |
| Frontend build | **BUILD-VERIFIED** |
| 466 passed / 1 skipped in CI | **CI-VERIFIED** |
| Mask polarity vs upstream CatVTON | **CODE-VERIFIED** |
| Fallback policy (`VTON_ENGINE_UNAVAILABLE` only) | **CODE-VERIFIED** |
| Migration 0012 CAST semantics | **CODE-VERIFIED** |
| Modal GPU diffusion output | **UNVERIFIED — EXTERNAL BLOCKER** |
| Neon / Redis / Gemini / NVIDIA / browser E2E | **UNVERIFIED — EXTERNAL BLOCKER** |

---

**FINAL: NOT PRODUCTION READY** — blocked on unverified VTON diffusion output (§8) and an unrotated production database credential (§9).
