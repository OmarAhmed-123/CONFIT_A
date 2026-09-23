# CONFIT_A — Consumer Role: Final Evidence Report (Part 2b, structure A–M)

**Date:** 2026-09-23 · **Repository:** `OmarAhmed-123/CONFIT_A` · **Production:** `https://confit-a.vercel.app/`
**Scope lock:** Consumer Role only. Brand/Partner/Admin were not redesigned; shared infrastructure was touched only where the consumer path depended on it.
**Branch discipline:** exactly one branch for this engagement — `fix/consumer-role-capability-honesty`. No second branch was created. `tmp-later` is local-only and was never pushed.
**This document supersedes:** the 10-section Part-2 report that occupied this path at commit `d2ddb1b` / PR #173. This is not a cosmetic rewrite: every number, PR, commit, deployment and production string below was re-fetched or re-measured on 2026-09-23 **after** PR #176 and PR #177 were merged.

**Truth sources used:** code (read + executed), runtime (local HTTP + production HTTP, read-only), tests (executed), CI (GitHub API), deployment (Vercel API), external infrastructure (live probes), git history.
**Status vocabulary, and nothing else:** `VERIFIED` · `PARTIALLY VERIFIED` · `BLOCKED` · `NOT TESTED` · `NOT APPLICABLE`.
**Standing rule:** the implementation must earn the claim; the claim must never invent the implementation. Where a previous claim and a current measurement disagree, the measurement wins and the claim is corrected in §L.

---

## A. Executive Summary

**What was asked.** Deep audit → deep remediation → verification of the consumer role, with an Evidence Ledger per capability, pattern-hunting across defect classes, mutation gates that must *kill* a reverted defect, production verification under read-only constraints, and a final report that is honest about what is unverified.

**What this cycle actually found.** The consumer path had a **class** of defect that no amount of green tests had caught: *configuration published as capability*. The deployment told shoppers three mutually contradictory things at the same time:

| Surface | What it said (production, before) | What was true |
|---|---|---|
| `/catalog/capabilities` | `payments_mode=demo`, `bnpl_live=false` | true |
| `/commerce/payment-methods?country=EG` | `bnpl_tabby.is_live=true`, "Tabby — Split in 4", "Sharia compliant" | false |
| `/catalog/products/1` | `bnpl.provider="Tabby"`, `"4 payments of 72.25 USD with Tabby"` | false — no lender made that offer |

Behind it: a hardcoded `is_live=True` literal on every entry of `PAYMENT_CATALOG`, an unsafe `PaymentMethodOption.is_live` default, and a product teaser that named a lender unconditionally. The deployment held no `PAYMENTS_LIVE`, no `TABBY_API_KEY`, no `TAMARA_API_KEY`, and `LIVE_PSP_ADAPTERS` was empty by design.

**What was fixed and merged.** PR **#176** (three commits) removed the literal and replaced it with a measurement; PR **#177** (one commit) removed a *second* unearned claim found in the same audit (PCI-DSS / central-bank compliance wording served for markets where no card or instalment rail could settle) and repaired a defect **in the test suite itself** — a helper that sent a query parameter the endpoint did not have, so market-aware tests were silently always answered for the default market.

| Question | Answer | Evidence |
|---|---|---|
| Does production still publish a lender's offer the deployment cannot honour? | **No.** `bnpl.provider=null`, `is_estimate=true`, disclaimer "not an offer and not a payment plan" | §I.2 |
| Does production still claim PCI-DSS/central-bank compliance where nothing but cash can settle? | **No.** The compliance sentence now appears only when a PSP method is measured live | §I.2 |
| Can a client be answered for a market it did not ask for, silently? | **No.** AE resolves to AED + Tamara; `XX` is echoed as `XX` with "No payment method is enabled for XX" | §I.2, gate M29 |
| Is every regression test able to fail? | **30 of 30 mutations killed, 0 survived, 0 not applicable** | §H |
| Is the deployed artifact the merged one? | **Yes** — Vercel production `READY` at `edea4ccc` = `origin/main` HEAD | §I.1 |
| Can a real payment settle in production? | **No — `BLOCKED`, external PSP credentials required.** COD only | §J.2 |

**What is deliberately not claimed.** No live PSP settlement, no VTON render, no production write path exercised, no Arabic/RTL visual pass of the tracking page in a browser, no production PostgreSQL internals (local tests run on SQLite; the PostgreSQL contract is enforced by the CI parity gate, which is a different kind of evidence and is labelled as such in §M).

---

## B. Current Baseline

### B.1 Local environment (measured this cycle)

| Item | Value |
|---|---|
| Python | 3.13.14 (`/home/user/.venv`) |
| pytest / FastAPI / SQLAlchemy | 9.1.1 / 0.141.1 / 2.0.54 |
| Node / npm | v20.20.2 / 10.8.2 |
| Test database | SQLite (in-process) — see §K.7 for why this is *not* evidence about production PostgreSQL |
| Backend suite | **4 failed / 2527 passed / 9 skipped in 366.14s** |
| Frontend suite | **36 files / 294 tests passed** (40.27s) |
| `tsc --noEmit` | exit 0 |
| `i18n:check` | PASSED |
| Mutation gates | **M1–M30: 30 killed / 0 survived / 0 not applicable** |

The 4 failures are `test_vton_pose_artifact_regression.py`, which imports `mediapipe`; mediapipe publishes no Python 3.13 wheels. They fail **identically on unmodified `origin/main`** (§G) — an environment gap, reported as such, never excused as "passing anyway".

### B.2 Repository baseline

| Item | Value |
|---|---|
| `origin/main` HEAD | `edea4ccc66331a5a231479fd6ab935437d182f94` (merge of PR #177) |
| Merged this engagement | #176 → `8f0a9117`; #177 → `edea4ccc` (both re-fetched from the GitHub API) |
| Open PRs (not mine, untouched) | #119, #150, #141 |
| Required checks | `backend`, `frontend`, `release gate (production schema parity)`; `strict=true`; 0 required reviews |
| `Workers Builds: confit-a` | fails instantly on every branch (Cloudflare build infrastructure); **not a required check**; reported, not hidden |

### B.3 Evidence Ledger (per capability)

Confidence is one of the five mandated values. "LOCAL" = this sandbox; "PROD" = `confit-a.vercel.app`, read-only.

| Capability | Claim being checked | Evidence source | Env | Test / probe | Result | Confidence |
|---|---|---|---|---|---|---|
| Payment method liveness | "Only COD can settle here" | `capability_service.payment_method_is_live()` | PROD | `GET /commerce/payment-methods?country_code=EG` | `live=['cod']`; card/tabby/tamara/vodafone/instapay `false` | VERIFIED |
| BNPL product teaser | "No lender is named; the figure is illustrative" | `product_context_service._bnpl_teaser()` | PROD | `GET /catalog/products/1` | `provider=null`, `is_estimate=true`, "not an offer and not a payment plan" | VERIFIED |
| Cart BNPL flag | "The cart also labels the figure an estimate" | `commerce_service` + test | LOCAL | `test_cart_marks_the_instalment_figure_as_an_estimate_when_not_live` | passed (16/16 in file) | VERIFIED (local). PROD **NOT TESTED** — reading a cart requires creating a guest session (write) |
| Payment disclaimer | "No compliance claim without a rail" | `capability_service.payment_disclaimer()` | PROD | EG / AE / XX probes | "PCI-DSS" absent; COD-only wording; XX: "No payment method is enabled for XX" | VERIFIED |
| Market resolution | "The requested market is the answered market" | controller + registry | PROD + LOCAL | AE probe; gate M29 | AE→AED+Tamara; EG→no Tamara; XX echoed | VERIFIED |
| Photo upload availability | "Uploads are offered only where they can be measured writable" | `capability_service.uploads_ready()` | PROD (flag) / LOCAL (rule) | `photo_upload_available=true`, `storage_mode=s3`; unit tests | flag measured; end-to-end upload write not exercised in PROD | PARTIALLY VERIFIED |
| Order tracking localization | "No raw machine tokens; Arabic exists" | `src/i18n/orderState.ts` + drift test | LOCAL | i18n suite (35), cross-layer drift guard | passed; M28 kills a state without a translation | VERIFIED (local). Browser AR/RTL visual pass **NOT TESTED** |
| API-error localization (money path) | "No backend English diagnostic shown to the shopper" | `src/i18n/apiErrors.ts` | LOCAL | `apiErrors.test.ts` (5) | passed | VERIFIED (local) |
| Capabilities contract | "13 keys, config-derived" | `catalog_controller` | PROD | `GET /catalog/capabilities` | 13 keys; `payments_mode=demo`; `bnpl_live=false`; `photo_upload_available=true` | VERIFIED |
| Health readiness | "Honest blocking/degraded lists" | `capability_service` + `readiness` | PROD | `GET /health` | `ready=false`, blocking `["virtual_try_on"]`, degraded `["buy_now_pay_later","payments"]` | VERIFIED |
| Virtual Try-On | "Offered, not renderable, nothing faked" | try-on capabilities + Modal probes | PROD | `GET /try-on/capabilities` | `production_ready=false`, `VTON_ENGINE_UNAVAILABLE`; Modal workspace disabled | VERIFIED as unavailable; **BLOCKED** externally |
| AI Stylist | "`ai_stylist_live=true`" | capability contract | PROD (flag) | field + contract tests | flag is configuration-derived; no availability probe exists | PARTIALLY VERIFIED — live provider call **NOT TESTED** (would consume quota and write a row) |
| Live PSP settlement | "Real payment" | Vercel env + code | PROD config | env names; `LIVE_PSP_ADAPTERS = {}` | no `PAYMENTS_LIVE`, no PSP key, no adapter | **BLOCKED** — external credentials required |
| Order/cart ownership | "A shopper cannot read another shopper's object" | `assert_order_access` + tests | LOCAL | `test_cart_item_idor_blocked`, ownership tests | passed; exploitation deliberately not attempted | VERIFIED (local) |
| Idempotency replay ownership | "A foreign key returns a generic 409" | `commerce_service` + 4 tests | LOCAL | gate M22/M23 | killed → tests can fail | VERIFIED (local). PROD **NOT TESTED** (requires placing orders) |
| Deployment identity | "Merged artifact = deployed artifact" | GitHub API + Vercel API | PROD | `READY at edea4ccc` = `origin/main` | equal | VERIFIED |
| Accessibility (consumer) | "Consumer surfaces are keyboard/screen-reader sane" | — | LOCAL | — | no browser pass this cycle | **NOT TESTED** |
| Production PostgreSQL | "Schema/constraints behave as tested" | CI parity gate | CI | `release gate (production schema parity)` | green on #177 | PARTIALLY VERIFIED — local suite is SQLite; no direct PROD DB query |

---

## C. Defects Found

Severity is graded to the evidence, never to the drama: **Observation** (a gap, no incorrect behaviour) · **Weakness** (incorrect behaviour, no exploit shown) · **Exploitability** (a path exists, not exercised) · **Demonstrated exploit** · **Impact** (measured harm). None of the defects below has a measured impact on a person; two of them published **false statements to shoppers in production**, which this project treats as a defect of the first order, not a cosmetic one.

### C.1 Defect D6 — Payment methods published `is_live=True` as a literal *(fixed, PR #176)*

**Severity:** false claim published in production (demonstrated); no exploit path, no user harm measured.
**Evidence (production, read-only, before the fix):** `GET /api/v1/commerce/payment-methods?country=EG` → `{"id":"bnpl_tabby","title_en":"Tabby — Split in 4","description_en":"Split in 4 interest-free monthly payments. Sharia compliant.","is_live":true}` on a deployment whose own `/catalog/capabilities` answered `payments_mode=demo`, `bnpl_live=false`, and whose environment contained no `PAYMENTS_LIVE`, `TABBY_API_KEY` or `TAMARA_API_KEY`.
**Root cause:** `PAYMENT_CATALOG` hardcoded `is_live=True` on every entry and `PaymentMethodOption.is_live` defaulted to `True`. Configuration (a catalogue entry exists) was published as capability (this deployment can charge this method).
**Impact if unfixed:** a regulated financing claim — "Sharia compliant instalment financing, live" — with nothing behind it; a shopper could select a method that must fail.
**Fix:** `capability_service.payment_method_is_live()` — one rule in one place: `cod` engages no PSP and is live where offered; every other method requires `PAYMENTS_LIVE` **and** an implemented live adapter **and** that provider's credential. `PaymentOrchestrator.get_market_methods()` stamps the measured value with `model_copy` (the catalogue holds module-level singletons; stamping in place would leak one deployment's state into another response).
**Regression protection:** `test_payment_method_is_live_is_measured_not_a_literal`, `test_payment_method_live_requires_key_adapter_and_live_mode`, `test_stamping_is_live_does_not_mutate_the_shared_catalog`; gate **M24** kills the reverted stamping.

### C.2 Defect D7 — The product page named a lender unconditionally *(fixed, PR #176)*

**Severity:** false claim published in production (demonstrated).
**Evidence:** `GET /catalog/products/1` → `bnpl.provider="Tabby"`, `installment_amount=72.25`, `disclaimer="4 payments of 72.25 USD with Tabby"`. The quote is computed locally — `BNPLProvider._fetch_remote_quote()` never contacts a provider — so no lender had offered anything.
**Root cause:** `_bnpl_teaser()` attached the brand whenever a BNPL *catalogue entry* existed; the only liveness check in the flow lived elsewhere (and the two "can we offer BNPL?" truths had drifted apart).
**Fix:** the brand is attached only when `bnpl_is_live()`; otherwise `provider=None`, `is_estimate=True`, and a disclosure that instalments are not enabled. Two authority functions (`bnpl_is_live()`, `payment_method_is_live("bnpl_<provider>")`) now answer the same question from the same inputs; a drift guard asserts they agree.
**Regression protection:** rewritten `test_bnpl_requires_payments_live_and_psp_key` (the old one *asserted the defect*: config present ⇒ live); group-5 lender-name assertion rewritten; gates **M25**, **M26**.

### C.3 Defect D8 — Uploads were gated on a provider's **name** *(fixed, PR #176)*

**Severity:** Weakness — UI offering an action that can only fail.
**Root cause:** the wardrobe decided "can the shopper upload?" from `storage_mode == "local"`. `storage_mode` is the provider's *name*; a deployment configured for S3 with a revoked credential or an unreachable bucket still reports `s3`.
**Fix:** `capability_service.uploads_ready()` measures; the capability payload publishes `photo_upload_available`; the wardrobe gates on it (13th capability key). Production: `storage_mode=s3`, `photo_upload_available=true`.
**Regression protection:** gate **M27** restores the name-based gate and is killed.

### C.4 Defect D9 — Raw machine enums on the order-tracking surface *(fixed, PR #176)*

**Severity:** Weakness (a shopper reads `awaiting_customs`, `payment_pending`), no data harm.
**Fix:** `src/i18n/orderState.ts` — literal maps for 22 order statuses, 9 payment statuses, 8 payment methods, plus helpers; unknown tokens fall back to the raw token by design (visibility over silence). The BNPL estimate/disclaimer copy lives in the locale files, not in components.
**Regression protection:** a cross-layer drift test reads `ORDER_TRANSITIONS` (Python) and the TypeScript maps **together** and fails if a lifecycle state has no localized copy — proven able to fail by injecting `"awaiting_customs": set(),` and observing the failure (then reverted; grep count 0). Gate **M28** makes it permanent.

### C.5 Defect D10 — English backend diagnostics on the money path *(fixed, PR #176)*

**Severity:** Observation → Weakness (an Arabic-first shopper receives an English server string on checkout failure).
**Fix:** `src/i18n/apiErrors.ts` — `API_ERROR_KEYS` + `localizeApiError(error, t)`; known codes localize, unknown codes show the server message, and a missing key is detected rather than rendered (`errors.some_key` must never appear). Wired into the checkout catch.
**Self-caught defect in my own map:** the first version lacked `errors.validation`; my own new test failed on it (`apiErrors.test.ts`). Fixed in both locales rather than by loosening the test.

### C.6 Defect D11 — The API asserted a compliance claim no rail could back *(fixed, PR #177)*

**Severity:** false claim published in production (demonstrated).
**Evidence:** `GET /commerce/payment-methods?country=EG` → *"All transactions in EG are processed in compliance with local central bank regulations and PCI-DSS tokenization standards."* on the same endpoint that answered `is_live=false` for card, Tabby, Vodafone Cash and InstaPay. The same sentence was served for markets the platform does not serve at all (`?country_code=XX` → *"All transactions in XX are processed…"*).
**Root cause:** `MarketPaymentCapabilityRegistry.get_capabilities_for_market()` produced one hardcoded sentence per market from the *catalogue*, while liveness was measured in a different layer. Nothing tied the sentence to the measurement.
**Impact if unfixed:** a regulated compliance claim (PCI-DSS tokenization, central-bank compliance) for transactions that never occur, served on a public endpoint, in a market that may not even be served.
**Fix:** the sentence is now derived from the same two inputs as `is_live`, in one place — a PSP method measured live earns it; a cash-only deployment says so and names COD; an unserved market is told no payment method is enabled. The catalogue layer now makes no compliance claim at all, because it is also called directly (`product_context_service`) and describes what the platform supports *in principle*. Both languages are derived; the Arabic states the same fact rather than echoing the English.
**Regression protection:** 3 new tests; gate **M30** restores the unconditional sentence and is killed.
**Consistency with project convention:** the project already requires that a disclaimer describe what actually happened (`test_fit_finder_api.py::test_measurement_disclaimer_matches_the_real_source`).

### C.7 Defect D12 — A market-aware test that never exercised a market *(fixed, PR #177)*

**Severity:** Weakness — **in the test suite**, i.e. a missing protection, not a product defect. This one is mine.
**Evidence:** `_methods()` in `test_capabilities_endpoint.py` requested `?country={code}`; the endpoint's parameter is `country_code`. FastAPI ignores unknown query parameters, so every call was answered for the default market (EG) while the helper looked market-aware — a test that passes without executing the branch it appears to exercise (the exact class this engagement was told to hunt).
**Blast radius, measured:** no assertion was invalidated (all callers used the EG default, and the default *is* EG), so no green result was a lie — but any future non-EG use would have been one.
**Fix:** the helper sends the real parameter **and** asserts the echoed `market_code`, so a silent fallback to the default now fails instead of hiding inside the test; a new test pins that AE resolves to the AE catalogue (Tamara present) and EG does not (D12 vs. prod: `?country_code=XX` is echoed as `XX`, so a client can detect an unserved market).
**Regression protection:** gate **M29** hardcodes the controller's market default and is killed.

### C.8 Carried defects (previous cycle, status unchanged)

| ID | Defect | Fix | Current status |
|---|---|---|---|
| D1 | `ai_stylist_live` was a false **negative** — config read from the deprecated `GROK_API_KEY` field instead of the `groq_api_key` property | #172 | fixed; contract tests pass in this tree |
| D2 | `ai_stylist` reported configuration as readiness (`STATE_READY` + "N live provider key(s)") | #172 — now `not_probed` / `measured degraded` | fixed; probe still absent (§J.3) |
| D3 | Checkout idempotency replay returned **another shopper's order** (global unique key, no ownership assertion) | #172 — caller-scoped replay, generic 409 `IDEMPOTENCY_KEY_CONFLICT` | fixed; gates M22/M23 kill the reverted code |
| D4 | The G5 specification **taught** the unsafe `Math.random()` token pattern | #172 — spec corrected | fixed (docs); the code fix is S1 |
| D5 | Guest session token minted with `Math.random()` (capability for cart resolution) | #168 — CSPRNG helper, fail-closed | fixed; impact description in the previous report was **overstated** and corrected |

---

## D. Architectural Findings

**D-1. The root pattern was "several owners of one truth".** Before this cycle the answer to "can this deployment charge with method X?" existed in three places at once: a hardcoded literal in the catalogue, a `bool(KEY)` check scattered in controllers, and a separate BNPL-specific check. They disagreed, and the shopper saw the most optimistic of the three. **Fix:** one authority module (`capability_service`) with a documented split — *configuration* (`_bnpl_configured`) is reported as configuration, *capability* (`bnpl_is_live`, `payment_method_is_live`, `uploads_ready`) requires a measurement, and *self-description* (`/catalog/capabilities`) publishes the capability. Adding a method now means adding it in one place.

**D-2. Catalogue vs. deployment separation is now explicit.** `MarketPaymentCapabilityRegistry` answers "what does the platform support in principle"; `PaymentOrchestrator.get_market_methods()` answers "what can *this* deployment settle". The response the client receives is the second one, stamped at a single boundary.

**D-3. A latent trap remains, reported rather than hidden.** `PAYMENT_CATALOG` still ships `is_live=True` literals; honesty depends on the orchestrator's total rewrite of every entry. A future caller that reads the registry directly and publishes `is_live` would reintroduce D6. This is **not** theoretical: `product_context_service` *does* call the registry directly — it happens not to read `is_live` (verified by search: the only consumer of `PaymentMethodOption.is_live` is the orchestrator's own `model_copy` rewrite; the frontend consumes it only from the endpoint). Graded **Weakness (latent)**, evidence: code read + the passing stamping test + gate M24. Removing the literals from the catalogue is the clean end-state; it was not done here because it would have widened a merged, verified change set for no consumer-visible gain — it is recorded as follow-up, not as done.

**D-4. Shared singletons must not be mutated per request.** `PAYMENT_CATALOG` holds module-level instances shared by every request; the measured stamp uses `model_copy`, so one deployment's state cannot leak into another response. Asserted, not assumed (`test_stamping_is_live_does_not_mutate_the_shared_catalog`; gate M24).

**D-5. Cross-layer contracts need cross-layer tests.** The order-state contract spans Python (`ORDER_TRANSITIONS`) and TypeScript (literal maps). A one-sided test cannot see drift, so the guard imports both and compares. Same idea for the payment rule: the capability flags, the orchestrator stamp and the disclaimer now read the *same* two inputs, which is why they cannot disagree.

**D-6. i18n architecture: per-domain map modules, not per-component strings.** `orderState.ts` and `apiErrors.ts` are literal maps with total functions (`localizeApiError`) and explicit unknown-token behaviour. Unknown order states show the raw token (visibility) and unknown API codes show the server message (no fake translation) — chosen deliberately and tested.

**D-7. No new abstraction was added for display.** No new table, cache, queue, provider, microservice or design pattern was introduced for this work. The two new functions are pure and testable; the disclaimer is a pure function of two sets.

---

## E. Security Findings

Graded: theoretical risk · demonstrated weakness · exploitability · confirmed impact. **No exploitation was attempted against any real account, order, cart or payment, and no production data was created, modified or deleted.**

### E.1 New in this cycle: none, and that is the finding

The two defects fixed in #176/#177 are **honesty/consistency** defects, not authorization or disclosure defects. Stated explicitly so the absence is not read as an untested area: the payment-capability work changed *labels and wording only*; it did not change who may read what. No new attack surface was introduced (no new endpoint, parameter, credential or provider adapter — `LIVE_PSP_ADAPTERS` remains empty).

### E.2 Carried, re-checked in this tree

| ID | Finding | Degree of proof | Status |
|---|---|---|---|
| S1 | Guest session token was not a CSPRNG value | **Demonstrated weakness**: with `Math.random` and the clock pinned, 50 calls produced 1 unique token (zero input-derived entropy). **Exploitability: not demonstrated** — no real token predicted, no cart observed. **Impact: none observed.** | Fixed (#168); 11 tests incl. "pin `Math.random()`, assert 50 distinct tokens" |
| S2 | Checkout idempotency replay returned another shopper's order | **Demonstrated weakness** in code and end-to-end tests (two call sites). **Exploitability: requires knowing the victim's key — not attempted.** Potential impact if known: disclosure of items, recipient, phone, address, totals. | Fixed (#172); generic 409; gates M22/M23 |
| S3 | `/cart/merge` treats *possession* of the guest token as authority | **Theoretical risk** (residual by design, not a regression). Residual risk is token leakage (shared device, logs, referrer), not prediction. | Reported, not re-architected |
| S4 | Positive findings re-checked | Order/tracking routes assert ownership (`assert_order_access`); anonymous probes of protected consumer surfaces return 401/404 as designed; `/api/v1/openapi.json` → 404 (schema not exposed); live payment path fails closed without an adapter (gate M13 kills the fabricated "authorized") | VERIFIED (local + PROD probes) |

### E.3 One new *test-integrity* finding (D12), reported as such

A test that cannot fail is a security control that does not exist. `_methods()` was such a control for market resolution; it is fixed and now guarded by gate M29. It is recorded here rather than in a footnote because "the test suite lies" is the failure mode this engagement is most exposed to.

---

## F. Changes Implemented

All changes are code + tests + documentation that reflects reality. No requirement was bent to fit the code; no test was loosened to become green.

### F.1 PR #176 → merge `8f0a9117` (three commits)

| Commit | Content |
|---|---|
| `5d35010` | `capability_service`: `payment_method_is_live()` (three-condition rule, COD exempt), `bnpl_is_live()`, `uploads_ready()`; `PaymentOrchestrator.get_market_methods()` stamps measured `is_live` via `model_copy`; `_bnpl_teaser()` names a lender only when measured live, else `is_estimate=True` + disclosure; cart payload gains `bnpl_is_estimate` (`schemas/commerce.py`); `/catalog/capabilities` gains `photo_upload_available` (13 keys) |
| `c47f8e5` | Consumer UI: `BNPLBadge.isEstimate` (required prop), wardrobe gate on `photo_upload_available`, product/cart/detail views consume `is_estimate`, checkout localizes payment-method titles via the existing `isArabic` convention |
| `89e5a4f` | i18n: `src/i18n/orderState.ts` (order/payment status + method maps, estimate copy), `src/i18n/apiErrors.ts` (code → localized message), locale keys in `en.json`/`ar.json`, checkout catch wired through `localizeApiError` |

### F.2 PR #177 → merge `edea4ccc` (one commit + merge)

| Commit | Content |
|---|---|
| `c61d785` | `capability_service.payment_disclaimer()` — the disclaimer becomes a pure function of (offered methods, measured-live methods): compliance sentence only when a PSP method is live; cash-only wording naming COD; "No payment method is enabled for {code}" otherwise. Orchestrator stamps `disclaimer_en/ar` from the same two inputs as `is_live`. The registry no longer makes any compliance claim. Tests: 3 new + helper hardened with a market echo assertion + 1 new market-resolution test. Gates **M29**, **M30** |

### F.3 Deliberate non-changes

* No new PSP provider, adapter, key or credential path (a provider requires license/commercial/VRAM/quality/latency/cost/security evaluation; none was performed).
* No fake VTON output, no sample render, no user image returned as output; the CPU path stays labelled a fit check and is never called "Try-On".
* No new abstraction, table, cache or queue; no design pattern added for display.
* No test assertion weakened; the two tests that *asserted* defects were rewritten to assert the honest contract.
* No documentation edited to cover a defect (the only documentation change is the correction of a normative spec that taught the unsafe token pattern, and this report).

---

## G. Tests (Before / After / Delta)

Every "after" number is paired with a **measured** "before" number on clean `origin/main`; nothing is inferred by arithmetic.

| Suite | Before (clean `origin/main` `c980489`) | After #176 (`8f0a9117` tree) | After #177 (this tree) | Delta vs baseline |
|---|---|---|---|---|
| Backend (full) | **4 failed / 2516 passed / 9 skipped** (360.54s) | 4 failed / 2523 passed / 9 skipped (365.13s) | **4 failed / 2527 passed / 9 skipped** (366.14s) | **+11 passed**; same 4 failures |
| Frontend (vitest) | 34 files / 285 tests | 36 files / 294 tests | **36 files / 294 tests** (40.27s) | **+2 files / +9 tests** |
| `tsc --noEmit` | exit 0 | exit 0 | **exit 0** | no change |
| `i18n:check` | PASSED | PASSED | **PASSED** | no change |
| Mutation gates | M1–M23: 23 killed | M1–M28: 28 killed | **M1–M30: 30 killed / 0 survived / 0 not applicable** | +7 gates |

The 4 backend failures are identical on both sides of every column: `test_vton_pose_artifact_regression.py` cannot import `mediapipe` on Python 3.13. Same count, same tests, no new failure — that is a comparison, not an assertion of "no regressions".

**What the new tests hold (and what each kills):**

| Test | Holds | Killed mutation |
|---|---|---|
| `test_payment_method_is_live_is_measured_not_a_literal` | A demo deployment labels no PSP method live; COD stays live | M24 |
| `test_payment_method_live_requires_key_adapter_and_live_mode` | Each condition alone is insufficient | M25 |
| `test_stamping_is_live_does_not_mutate_the_shared_catalog` | `model_copy`, not in-place mutation of shared singletons | M24 |
| `test_bnpl_requires_payments_live_and_psp_key` (rewritten) | Config + key without an adapter is not an offer | M25 |
| group-5 lender-name assertion (rewritten) | No lender is named when not live | M26 |
| `test_photo_upload_available_is_measured_while_storage_mode_is_a_name` | Provider name ≠ readiness | M27 |
| `test_every_order_state_has_a_frontend_translation_key` | Python lifecycle ↔ TypeScript maps agree | M28 (proven able to fail by injection) |
| `test_cart_marks_the_instalment_figure_as_an_estimate_when_not_live` | The cart is honest too | (covered by M24/M25 path) |
| `test_payment_methods_answer_for_the_requested_market` | A request for one market is never answered for another | **M29** |
| `test_payment_disclaimer_makes_no_compliance_claim_nothing_can_back` | No PCI-DSS/central-bank claim in EN **or AR** without a live rail | **M30** |
| `test_payment_disclaimer_keeps_the_compliance_line_when_a_psp_method_is_live` | The sentence is kept where it is earned (not merely deleted) | M30 (inverse branch) |
| `test_payment_disclaimer_speaks_for_markets_with_no_method_at_all` | Unserved markets are told the truth | M30 |
| `bnplBadge.test.tsx` (5 tests) | The estimate branch names no lender, shows the disclosure, and **cannot** omit `isEstimate` (compile-time `@ts-expect-error` gate) | type-level |
| `apiErrors.test.ts` (5 tests) | Known codes localize; unknown codes fall back; a missing key never renders `errors.x` | n/a (frontend) |
| `orderState.test.ts` (35 i18n tests total) | Total maps, AR present, unknown token behaviour | M28 |

**Honest notes on tests I had to fix (all mine, all disclosed):**

1. **Two new capability tests first failed from my own harness errors** — the "credential revoked" case had not revoked the credential, and the `storage_mode` case patched a probe flag while `storage_mode` reads `settings.STORAGE_PROVIDER`. Fixed at the cause.
2. **My `apiErrors` map lacked `errors.validation`** — caught by my own new test; fixed in both locales.
3. **`BNPLBadge.isEstimate` first shipped with a `false` default** — a forgotten flag would silently render the lender-naming branch, i.e. reintroduce D7 through the back door. Caught by the frontend test; the default was removed (the prop is now required) and the omission is a compile error.
4. **The `?country=` helper (D12)** — a market-aware test that never exercised a market. Caught by reading the endpoint signature while probing production, then fixed and gated.
5. **Mutation gate hygiene:** the runner mutates working-tree files; `git status` during a run can show a backend file as modified. Waited for the run to finish before trusting diffs, and verified zero residue afterwards.

**Not tested this cycle:** browser-level keyboard/screen-reader pass; live AI provider call; production write paths (all prohibited without operational authorization); production PostgreSQL internals; the Arabic/RTL visual rendering of the tracking page in a browser.

---

## H. Mutation Results (exact output)

Runner: `backend/scripts/run_mutation_gates.py` (it reverts a real fix in the working tree and requires the suite to fail; a survivor means the test cannot see the defect).

Full run, this tree (gate titles elided at 95 characters for readability; the summary line is verbatim, and the full titles are in the source):

```
[M24] KILLED    Payments: serve the catalog's hardcoded `is_live=True` instead of the measured ...
[M25] KILLED    BNPL: treat PAYMENTS_LIVE + a provider key as an instalment offer, dropping the ...
[M26] KILLED    Product page: name the lender unconditionally, even when no live provider exist...
[M27] KILLED    Wardrobe: gate photo uploads on the storage provider NAME instead of the measur...
[M28] KILLED    Order states: add a lifecycle state that has no localized copy, so the shopper ...
[M29] KILLED    Payment methods: answer every request with the default market, so a client aski...
[M30] KILLED    Payment disclaimer: restore the unconditional compliance sentence ('All transac...

MUTATION GATES: 30 killed, 0 survived, 0 not applicable
```

Individually re-run while the change was being finalised:

```
[M29] KILLED  ... (5.6s)  -> 1 failed, 2 warnings in 3.93s
[M30] KILLED  ... (5.7s)  -> 1 failed, 2 warnings in 4.02s
MUTATION GATES: 2 killed, 0 survived, 0 not applicable
```

Progression across the engagement: M1–M23 (23 killed) → M1–M28 (28 killed) → **M1–M30 (30 killed)**.

**Survivors found and what happened to them.** One previously surviving mutant (M23 in the earlier cycle) is why the idempotency *race* test now scripts the interleaving instead of passing through the pre-flight path — a real instance of the suite being wrong and being fixed at the cause. In this cycle no mutant survived, and the M28 drift guard was additionally proven able to fail by manual injection before being frozen as a gate.

**Limitation, stated plainly:** the runner executes pytest only. The frontend has **no mutation gate**; its protections are the vitest suite (294 tests) and a compile-time gate (`@ts-expect-error` on the required `isEstimate` prop), which is a type-level mutation kill rather than a runtime one. This is a gap in test *methodology*, not in the results quoted above.

---

## I. Production Evidence (exact probes)

**Constraints honoured:** read-only, anonymous, no orders, no payments, no uploads, no account changes, no deletions. Where a claim would require a write, it is marked NOT TESTED rather than dressed up.

### I.1 Deployment identity

| Item | Value |
|---|---|
| Vercel production deployment | `dpl_B8JcWL6nA7iF4ssi7rJTbo6bXjKJ` — state **READY** at commit `edea4ccc66331a5a231479fd6ab935437d182f94` |
| `origin/main` HEAD (re-fetched after merge) | `edea4ccc66331a5a231479fd6ab935437d182f94` — **identical** |
| Production alias | `confit-a.vercel.app` (the only domain on the project — see §M: there is **no separate staging environment**) |
| Proof the alias serves this build | The probes below return wording that exists only in the `c61d785`/`edea4ccc` artifact (the conditional disclaimer) |

### I.2 Before → after, same endpoints, same kind of deployment (read-only)

| Probe | BEFORE (#173 deployment `018ff2c7`) | AFTER (`edea4ccc`) |
|---|---|---|
| `GET /api/v1/commerce/payment-methods?country_code=EG` | `bnpl_tabby.is_live=true`, "Tabby — Split in 4", "…Sharia compliant."; disclaimer asserted PCI-DSS/central-bank compliance | `live=['cod']`; EN: *"Card and instalment payments are not enabled on this deployment. Cash on delivery is the only live payment method in EG."*; AR: *"الدفع بالبطاقة والتقسيط غير مُفعّل على هذا النشر…"*; **"PCI-DSS" absent from both** |
| `GET /api/v1/catalog/products/1` | `bnpl.provider="Tabby"`, `installment_amount=72.25`, `disclaimer="4 payments of 72.25 USD with Tabby"` | `bnpl.provider=null`, `is_estimate=true`, *"Illustrative only — instalment payments are not enabled on this deployment, so this is not an offer and not a payment plan."* |
| `GET /api/v1/commerce/payment-methods?country_code=AE` | (same literal `is_live=true` class of answer) | `market_code=AE`, `currency_code=AED`, methods `card, bnpl_tabby, bnpl_tamara, apple_pay, cod`, live `['cod']`; same honest COD-only wording |
| `GET /api/v1/commerce/payment-methods?country_code=XX` | *"All transactions in XX are processed in compliance with…"* | `market_code=XX`, `currency_code=USD`, methods `['card']`, live `[]`; *"No payment method is enabled for XX on this deployment."* |
| `GET /api/v1/catalog/capabilities` | 12 keys | **13 keys**; `payments_mode=demo`, `bnpl_live=false`, `photo_upload_available=true`, `storage_mode=s3`, `vton_renderable=false`, `ai_stylist_live=true` |
| `GET /api/v1/health` | `ready=false`, blocking `["virtual_try_on"]`, degraded `["buy_now_pay_later","payments"]` | unchanged |

### I.3 Anonymous HTTP status sweep (read-only, after the merge)

```
/catalog/products                 200      /commerce/cart (no session header)   422
/catalog/categories               200      /orders/CONF-000000 (unknown)        404
/catalog/products/1               200      /wardrobe/items (anonymous)          401
/catalog/capabilities             200      /profile (anonymous)                 404
/commerce/payment-methods (EG)    200      /returns/labels/RA-FAKE000000        404
/commerce/payment-methods (AE)    200      /stylist/chat (GET, route is POST)   405
/commerce/payment-methods (XX)    200
/try-on/capabilities              200
/health                           200
```

**What these statuses are not.** The `422` on `/commerce/cart` is a missing `X-Session-Token` header rejection (guest carts are intentional) and is **not** reported as protection. The `404`s on `/orders/…` and `/returns/labels/…` mean "no such object for this caller", not "ownership proven" — ownership is enforced by `assert_order_access` and its tests, not by this probe. The `405` on `/stylist/chat` confirms the route exists (POST-only); it says nothing about the provider being reachable.

### I.4 What was deliberately not written to production

No order was placed, no payment initiated, no cart mutated, no file uploaded, no account or profile changed, no record deleted. Consequences are listed in §K, not glossed over.

---

## J. Remaining Blockers (external only)

**J.1 Virtual Try-On GPU capacity — BLOCKED (external).** Modal workspace `ac-io3nXB7Q2nuaHHl8mVkeLH` is disabled: live worker probes return HTTP 404 `workspace … is disabled`, apps report `deployed` with **0 tasks** running. "Deployed" is status text, not capacity. Production therefore reports `production_ready=false`, `VTON_ENGINE_UNAVAILABLE`, `vton_renderable=false` while still offering the feature with an honest message, and the CPU path is presented as a **fit check**, never as a render. Restoring the workspace (spend limit/credits) is an operational action outside the code.

**J.2 Live PSP settlement — BLOCKED: external PSP credentials required.** Production has `payments_mode=demo`; `PAYMENTS_LIVE`, `TABBY_API_KEY` and `TAMARA_API_KEY` are absent, and `LIVE_PSP_ADAPTERS` is empty by design until an integration is verified against a provider sandbox. Demo is Demo: nothing in this report calls a demo transaction a live one. When credentials and a verified adapter exist, `payment_method_is_live()` will report the truth without another code change.

**J.3 Repository-level items outside this scope (reported, untouched).** Open PRs #119 (243 files), #150 and #141 remain open as re-fetched from the GitHub API; #119 is based far behind `main` and is a merge hazard for whoever owns it. `Workers Builds: confit-a` fails instantly on all branches (Cloudflare infrastructure) and is not a required check.

---

## K. Not Verified

Ranked by what a reader might most reasonably assume was covered.

1. **Live payment settlement** — no live PSP credentials, no adapter, no sandbox verification. **BLOCKED** (§J.2). Every payment statement in this report is about *labels and measurement*, never about money moving.
2. **Arabic/RTL visual rendering of the tracking page in a browser** — the state maps and locale parity are tested (`VERIFIED` at the code level), but no browser pass was performed this cycle. **NOT TESTED**.
3. **Virtual Try-On output** — cannot be rendered while the Modal workspace is disabled; nothing was faked to fill the gap. **BLOCKED** for the render, VERIFIED for the honest "unavailable" state.
4. **AI Stylist availability** — the capability reports configuration, and no probe exists (open gap from the previous cycle, still open). A live provider call was not made (it consumes quota and writes a message row without operational authorization). **PARTIALLY VERIFIED / NOT TESTED** for the live path.
5. **Production write paths** — cart creation, checkout, order placement, uploads, returns. Verified by local end-to-end tests and the CI schema gate; **NOT VERIFIED IN PRODUCTION** by design, because verification would require creating real production data.
6. **Production PostgreSQL internals** — the local suite runs on SQLite. The PostgreSQL contract is enforced by the CI check `release gate (production schema parity)`, which is a real but *different* kind of evidence: **PARTIALLY VERIFIED**, and local SQLite results are never presented as proof about production PostgreSQL.
7. **`/health/ready` (admin readiness payload, `unprobed_capabilities`)** — requires an admin bearer token; anonymous access is refused by design. **NOT TESTED**.
8. **Accessibility, keyboard and screen-reader pass on consumer surfaces** — not performed this cycle. **NOT TESTED**.
9. **Rate limiting and CSRF cookie flags** — not re-measured this cycle. **NOT TESTED** (not claimed either way).

---

## L. False-Claim Audit

Two directions: what the **product/API** claimed versus what measurement shows, and what **my own reports** claimed versus what re-measurement shows. Findings against my own work are included deliberately.

### L.1 Product / API claims

| Claim (as served or implied) | Measurement | Verdict |
|---|---|---|
| "Tabby — Split in 4 … Sharia compliant", `is_live: true` | No Tabby key, no adapter, `payments_mode=demo` | **False claim → removed (#176)** |
| "4 payments of 72.25 USD with Tabby" (product page) | No provider contacted; quote computed locally | **False claim → removed; now an explicit estimate (#176)** |
| "All transactions in EG are processed in compliance with local central bank regulations and PCI-DSS tokenization standards" | Only COD could settle; no card transaction occurs | **False claim → removed where unearned (#177); kept where a PSP method is measured live** |
| The same sentence served for `XX`, a market the platform does not serve | `XX` is not a supported market | **False claim → replaced (#177)** |
| "Try On" labelled CTA / suggestible render | `vton_renderable=false`, engine unavailable | Wording already corrected in the previous cycle: the CPU path is a **fit check** and is not called Try-On; **no fake render exists** |
| `photo_upload_available` (wardrobe gate) | Measured against storage probes, not the provider name | Now **earned**, not asserted |
| `ai_stylist_live=true` | Keys exist; nothing probed | **Weaker than "live" implies** — the contract says `not_probed` where that is the case; the flag remains configuration-derived and is labelled PARTIALLY VERIFIED (§B.3), not "working" |

### L.2 Claims in my own earlier report (this file's predecessor)

| Earlier claim | Re-measurement | Verdict |
|---|---|---|
| "Cross-surface contradiction check: RESOLVED. Catalog, try-on capabilities and health now agree." | True for those three surfaces — **but a contradiction existed on surfaces the sentence did not name**: `/commerce/payment-methods` and the product BNPL teaser told shoppers a lender was live. A reader would reasonably infer overall consistency from that sentence. | **Previous claim disproven by current measurement.** Corrected by #176/#177; this report states the scope of every consistency claim explicitly |
| Production READY at `66fdf5f7` / `018ff2c7` | Re-fetched: superseded by `8f0a9117` then `edea4ccc` | Confirmed then; superseded now |
| D1–D5 as described (incl. "correction downward" of the token impact) | Carried unchanged; tested in this tree | Confirmed |
| Test counts quoted for the earlier cycle | Re-measured this cycle with a fresh baseline comparison | Confirmed for their tree; new numbers reported in §G |
| (implicit) "the payment capability surface is measured" | True for `is_live` after #176; the **disclaimer** was still an unearned claim, found by auditing the same payload | **Incomplete → completed in #177** |

### L.3 My own mistakes in this engagement (found, explained, fixed, prevented)

| Mistake | How it was caught | What prevents recurrence |
|---|---|---|
| First platform capability test asserted configuration ⇒ live (a test defending the defect) | Reading the contract while auditing D6 | Test rewritten to the honest contract, not deleted or loosened |
| Locale file rebuilt from `git show HEAD:` wiped the `order` group | The i18n gate failed on missing keys | Locale edits now merge into the working copy; the gate is the enforcement |
| Arabic brand names first written in Latin script | The locale-parity test (`ar.json is NOT a copy of en.json`) | Follow the project's transliteration convention; the gate's exception list was **not** widened |
| `errors.validation` missing from my API-error map | My own new test | Tests stay strict; a test that cannot fail is worthless |
| Committed onto local `main`, then a push that silently no-opped ("Everything up-to-date" with 3 new commits) | Comparing the push message with `git log` | `git branch --show-current` before every commit; refs corrected; **no second branch was created** |
| `BNPLBadge.isEstimate` shipped with a `false` default (would silently name a lender) | The frontend test failed on the default branch | Prop is now required; omission is a compile error |
| `?country=` test helper never exercised a market (D12) | Reading the endpoint signature during production probing | Helper asserts the echoed market; gate M29 |
| My own production probe first used `?country=AE` and reported "market: EG" | The response contradicted the request; re-probed with the correct parameter | Probes now assert the echoed value they depend on |
| Quoted a test count from an intermediate commit in a PR body | Re-reading the PR against the final run | PR bodies cite the final measured numbers only |

**Not claimed anywhere in this document:** "perfect", "100%", "fully complete", "everything works", "production ready", or "secure" without the probe that backs it.

---

## M. Final Environment Matrix

**Environment definitions.** LOCAL = this sandbox. STAGING = a Vercel preview deployment of this repository. PRODUCTION = `confit-a.vercel.app`. **Measured fact:** the Vercel project has exactly one domain (`confit-a.vercel.app`) — there is **no standing staging environment**, so STAGING rows are `NOT APPLICABLE` / `NOT TESTED` rather than filled with local results wearing a staging label.

| Surface | LOCAL | STAGING | PRODUCTION | Evidence |
|---|---|---|---|---|
| Backend suite | **PASS** (4 failed / 2527 passed / 9 skipped; failures = mediapipe/Py3.13, identical on baseline) | NOT APPLICABLE (no staging env) | NOT APPLICABLE (no test suite runs against prod) | §G log tails |
| Frontend suite / tsc / i18n gate | **PASS** (36 files / 294 tests; `tsc` exit 0; i18n PASSED) | NOT APPLICABLE | NOT APPLICABLE | §G |
| Mutation gates M1–M30 | **PASS** (30 killed / 0 survived / 0 n/a) | NOT APPLICABLE | NOT APPLICABLE | §H |
| Payment liveness (`is_live`) | PASS (unit + endpoint tests) | NOT TESTED | **PASS** (`live=['cod']` on EG/AE; others false) | §I.2 |
| Payment disclaimer honesty | PASS (3 tests, EN+AR) | NOT TESTED | **PASS** (no PCI-DSS claim; COD-only wording; XX honest) | §I.2 |
| Market resolution | PASS (gate M29) | NOT TESTED | **PASS** (AE→AED+Tamara; XX echoed) | §I.2 |
| BNPL product teaser | PASS (group-5) | NOT TESTED | **PASS** (`provider=null`, `is_estimate=true`) | §I.2 |
| Cart BNPL estimate | PASS | NOT TESTED | **NOT TESTED** (needs a guest cart — a write) | §K.5 |
| Order tracking i18n | PASS (35 i18n tests + drift guard) | NOT TESTED | NOT TESTED (no browser AR/RTL pass) | §K.2 |
| Capabilities contract (13 keys) | PASS | NOT TESTED | **PASS** | §I.2 |
| Health readiness | PASS | NOT TESTED | **PASS** (`ready=false` for the VTON reason only) | §I.2 |
| Virtual Try-On render | NOT APPLICABLE (no GPU locally) | NOT TESTED | **BLOCKED** (Modal workspace disabled; honest unavailable state verified) | §J.1 |
| AI Stylist live call | NOT TESTED (quota + write) | NOT TESTED | **NOT TESTED** | §K.4 |
| Live payment settlement | **BLOCKED** (no credentials/adapter) | BLOCKED | **BLOCKED — external PSP credentials required** | §J.2 |
| Order/cart ownership (IDOR class) | PASS (tests; exploitation not attempted) | NOT TESTED | NOT TESTED (no foreign-object access attempted) | §E.2 |
| Idempotency replay ownership (409) | PASS (4 tests; gates M22/M23) | NOT TESTED | **NOT TESTED** (requires placing orders) | §K.5 |
| Production PostgreSQL parity | NOT APPLICABLE (SQLite locally) | NOT TESTED | **PARTIALLY VERIFIED** — CI check `release gate (production schema parity)` green on #177; no direct prod DB query | §K.6 |
| Deployment identity | — | — | **PASS** — Vercel `READY` at `edea4ccc` = `origin/main` HEAD | §I.1 |
| Accessibility (keyboard/screen-reader) | **NOT TESTED** | NOT TESTED | NOT TESTED | §K.8 |
| Rate limiting / CSRF cookie flags | **NOT TESTED** | NOT TESTED | NOT TESTED | §K.9 |

---

## Final Status

**Merged and verified in production, read-only:**

* PR #176 → `8f0a9117`, PR #177 → `edea4ccc`; `origin/main` HEAD = `edea4ccc` = the deployed artifact (Vercel `READY`).
* Three consumer-visible false claims removed from production (lender-named BNPL offer; `is_live` literal; PCI-DSS/central-bank compliance wording), each replaced by a value derived from a measurement, each guarded by a mutation gate that kills its return.
* 30/30 mutation gates killed; backend `4 failed / 2527 passed / 9 skipped` with the same 4 environment failures on the clean baseline; frontend 36 files / 294 tests; `tsc` clean; i18n gate green.

**Blocked (external only):** VTON GPU capacity (Modal workspace disabled); live PSP settlement (credentials and a verified adapter absent).

**Not verified, and said so:** production write paths, Arabic/RTL browser rendering, AI Stylist live call, admin readiness payload, accessibility pass, rate limiting/CSRF flags, production PostgreSQL internals.

**The engineering outcome, stated without decoration:** the consumer surface no longer says things the deployment cannot do. Where it cannot do something, it says that instead — and the tests that protect that behaviour are able to fail when the defect returns.
