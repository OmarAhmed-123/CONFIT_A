# CONFIT_A — Consumer Role: Evidence-Based Verification Report

**Date:** 2026-09-23 · **Scope lock:** Consumer Role only (no brand/admin/partner scope was entered)
**Branch used:** `fix/consumer-role-capability-honesty` (single branch, sequential PRs)
**Supersedes:** `docs/CONSUMER_ROLE_FINAL_REPORT_20260922.md` — that report is a starting point, not the source of truth. Every fact below was re-measured or re-fetched; nothing was carried over on trust.

**Truth sources used:** code (read + executed), runtime (local server + production HTTP), tests (executed), database (schema revision + integrity script), deployment (Vercel API), external dependencies (live probes), Git history and CI (GitHub API).

**Status vocabulary used in this document:** `VERIFIED` · `PARTIALLY VERIFIED` · `BLOCKED` · `NOT TESTED` · `NOT APPLICABLE`. No "perfect", "100%", "fully complete", "everything works".

**Environment separation is enforced throughout:** LOCAL (this sandbox), STAGING (a Vercel *preview* deployment), PRODUCTION (`confit-a.vercel.app`). Statements are never mixed across environments.

---

## 1. Current State

### 1.1 Local (this sandbox)

| Item | Value |
|---|---|
| HEAD | `87a242eb` (branch `fix/consumer-role-capability-honesty`) |
| Backend suite (executed) | **2490 passed / 4 failed / 8 skipped** (442.56s) |
| Baseline on clean `origin/main` (`353f7b0`, worktree at `/tmp/baseline-main`) | **2484 passed / 4 failed / 8 skipped** (421.10s) |
| Delta vs baseline | **+6 passing tests, the same 4 failures** — the 4 are pre-existing and reproduce on the baseline, not on my change |
| Frontend suite (executed) | **33 files / 280 tests passed** |
| `tsc --noEmit` | exit 0 |
| `i18n:check` | PASSED |
| Mutation gates, all of them (executed) | **23 killed / 0 survived / 0 not applicable** |

The 4 failures are `backend/tests/test_vton_pose_artifact_regression.py`, which imports `mediapipe`; mediapipe publishes no Python 3.13 wheels (sandbox is 3.13.14). They fail identically on unmodified `origin/main` — environmental, not a regression from this work. Stated as an environment gap, not excused away.

### 1.2 Production

| Item | Value |
|---|---|
| Vercel production deployment | **READY at `66fdf5f7`** = merge commit of PR #172 = `main` HEAD |
| `main` HEAD | `66fdf5f7` |
| `/api/v1/health` | `ready=false`, blocking `["virtual_try_on"]`, degraded `["buy_now_pay_later","payments"]` |
| `/api/v1/catalog/capabilities` | `vton_gpu_ready=false`, `vton_engine_state=temporarily_unavailable`, `vton_offered=true`, `vton_renderable=false`, `payments_mode=demo`, `payments_live=false`, `ai_stylist_live=true` |
| `/api/v1/try-on/capabilities` | `production_ready=false`, `VTON_ENGINE_UNAVAILABLE`, `probe_age_seconds≈5`, honest user message |
| Public API schema | `/api/v1/openapi.json` → **404** (not exposed) |

**Cross-surface contradiction check: RESOLVED.** Catalog, try-on capabilities and health now agree: try-on is offered, cannot render, and says so.

The single reason the platform reports `ready=false` is the VTON GPU path, and the single reason for that is external (§6).

---

## 2. Defects Found (this cycle)

Each defect below was **measured**, not inferred from a component existing. Defects D1–D4 were found in this cycle; D5 is carried from the same engagement with its severity **corrected downward** (§9).

### D1 — `ai_stylist_live` was a false negative (config read from the wrong field)

`capability_service._ai_provider_keys()` read the deprecated `GROK_API_KEY` **field**. The orchestrator resolves the same slot through the `groq_api_key` **property** (`backend/app/core/config.py:488`), which prefers the documented `GROQ_API_KEY`.

Measured, with only the documented variable set:

```
settings.groq_api_key  -> True     # the key the system actually uses
_ai_provider_keys()    -> []       # what the capability contract reported
```

So a deployment with a working Groq key advertised `ai_stylist_live: false`. A false negative is still a lie — it is the same failure as the earlier `vton_gpu_ready` defect, pointed the other way.

**Status:** VERIFIED as a defect (reproduced locally and against the production configuration shape) → fixed (#172).

### D2 — `ai_stylist` reported configuration as readiness

The capability returned `STATE_READY` whenever provider keys existed, with the detail `"N live provider key(s)"` — calling a key that had **never been used** "live", against this project's own published contract:

```
STATE_READY = "probed and working"
STATE_NOT_PROBED = "no probe exists — an honest gap, never a silent ok"
```

`backend/tests/test_health_readiness_contract.py:244` asserted the defect (`STATE_READY` + `"2 live provider key(s)"`), so the suite defended it.

**Status:** VERIFIED as a defect → fixed (#172). The test was **rewritten, not deleted and not loosened**.

### D3 — Checkout returned another shopper's order (idempotency replay had no ownership check)

`orders.idempotency_key` is `UNIQUE` table-wide, and `CommerceRepository.get_order_by_idempotency` filters on **the key alone**:

```python
return self.db.query(Order).filter(Order.idempotency_key == key).first()
```

`POST /checkout` then returned `self.get_order(existing.order_number)` — the full order (items, recipient, phone, address, totals) — with **no ownership assertion**, in two places:

1. the pre-flight replay check;
2. the `except IntegrityError` branch, i.e. the loser of a concurrent race on that key.

The project already treats this as a defect class: `GET /orders/{n}` calls `assert_order_access` ("Access denied: You cannot view order details of another customer."), and `get_order_tracking` asserts the same. The checkout replay path asserted nothing.

**Status:** VERIFIED as a defect (two call sites read in code; behaviour reproduced end-to-end in tests) → fixed (#172). Exploitation against a real shopper was **not attempted** (§7).

### D4 — The product specification taught the unsafe token pattern

`docs/CONFIT_Feature_Spec_G5_Commerce_Payments_Fulfillment.md:178` specified the reference implementation as:

```js
idempotency_key: 'idemp_' + Math.random().toString(36).substring(2, 12),
```

— the exact pattern removed from the product code in #168. Left in the normative spec, the next implementation of this flow reintroduces it.

**Status:** VERIFIED (read) → corrected (#172). The specified behaviour is unchanged; only the generator was corrected. This is not documentation used to cover a defect.

### D5 — Guest session token was generated with `Math.random()` (carried; severity corrected)

`frontend/src/services/apiClient.ts` minted the guest session token — a capability that resolves carts — with `Math.random()`. Measured with the PRNG and the clock pinned: **50 calls produced 1 unique token**, i.e. zero input-derived entropy.

**Status:** VERIFIED as a weakness → fixed (#168). The previous report's description of its impact was overstated and is corrected in §9.

---

## 3. Changes Made

All changes are code + tests + one specification correction. No requirement was bent to fit the code.

| # | File | Change | Evidence |
|---|---|---|---|
| 1 | `backend/app/services/capability_service.py` | `_ai_provider_keys()` reads `settings.groq_api_key` (the property the system uses) instead of the deprecated field | Measured before/after in §D1 |
| 2 | `backend/app/services/capability_service.py` | New `_ai_stylist_capability()`: keys present + nothing measured → `not_probed`; a **measured** quarantine of all known providers → `degraded`; no keys → `degraded` (deterministic grounded fallback). Supporting criticality, so an AI outage can never set platform readiness false | `test_health_readiness_contract.py` (3 tests), gates M19/M20/M21 |
| 3 | `backend/app/services/capability_service.py` | New `_ai_quarantine_state()` — the one place the module reads runtime state; quarantine records are **no longer discarded** when the provider's `configured` flag is false (that flag is configuration; dropping the record threw away the only real measurement) | gate M21 kills the older behaviour; a read failure falls through to `not_probed`, never to `ready` |
| 4 | `backend/app/services/commerce_service.py` | `_is_caller_own_idempotent_order(order, user_id, session_token, guest_email)` — signed-in shopper: only their own account's orders; guest: only orders carrying their own guest session token (the credential the cart already uses), e-mail fallback for legacy rows only | `test_group5_commerce.py` (4 tests), gates M22/M23 |
| 5 | `backend/app/services/commerce_service.py` | Both replay call sites now apply rule 4; a foreign key raises `IdempotencyKeyConflictError` | same |
| 6 | `backend/app/core/exceptions.py` | New `IdempotencyKeyConflictError` → HTTP **409**, code `IDEMPOTENCY_KEY_CONFLICT`, deliberately generic message (must not confirm that the key matches a real order, whose it is, or what it contains) | asserted in 3 tests, including that the victim's order number, phone and address never appear in the response body |
| 7 | `backend/tests/test_health_readiness_contract.py` | Defect-asserting test **rewritten** to the honest contract; added the measured-failure case and the documented-variable case | readiness + capabilities-endpoint + single-source suites: **52 passed** |
| 8 | `backend/tests/test_group5_commerce.py` | 4 new idempotency-ownership tests: another account's key; guest-session isolation (with the original session still replaying); the signed-in/guest boundary; the lost-race branch | all pass; M22 and M23 both kill |
| 9 | `backend/scripts/run_mutation_gates.py` | Gates **M19–M23** added (M20 covers the wrong-field read) | full set: 23 killed / 0 survived |
| 10 | `docs/CONFIT_Feature_Spec_G5_Commerce_Payments_Fulfillment.md` | Reference implementation corrected to the CSPRNG helper | §D4 |

**Deliberate non-changes.** No design pattern was added for display; no algorithm was changed without a cause; no new VTON provider was added; no test assertion was weakened; no document was edited to hide a defect. The 409 is a purpose-built error because the existing 409 (`InvalidStateTransitionError`) means "order state transition", which is a different fact and would have mislabelled the condition.

---

## 4. Tests

All numbers below were produced by commands run in this cycle. Baseline rule: every "after" number is paired with a **measured** "before" number on clean `origin/main`, never with arithmetic or assumption.

| Suite | Before (clean `origin/main` `353f7b0`) | After (merged content `87a242eb`) |
|---|---|---|
| Full backend | **2484 passed / 4 failed / 8 skipped** | **2490 passed / 4 failed / 8 skipped** |
| Frontend (vitest) | 33 files / 280 tests passed | 33 files / 280 tests passed (no frontend change this cycle) |
| `tsc --noEmit` | exit 0 | exit 0 |
| `i18n:check` | PASSED | PASSED |
| Mutation gates | M1–M18 existing (M17/M18 killed) | **M1–M23: 23 killed / 0 survived / 0 not applicable** |

The 4 failures are identical in both columns and are the mediapipe/Python-3.13 environment gap (§1.1).

**Regression tests added and what each one holds:**

* `test_the_ai_stylist_state_does_not_follow_the_provider_keys` — keys configured, nothing measured ⇒ `not_probed`; and the honest gap must **not** make the platform unready.
* `test_the_ai_stylist_state_degrades_from_a_measured_failure` — a real failure (quarantine entry) ⇒ `degraded`, visible in `degraded_capabilities`, never in `blocking_capabilities`.
* `test_ai_provider_keys_honours_the_documented_groq_variable` — the documented variable is visible; the legacy spelling still works; a whitespace-only value is unset, not a key.
* `test_idempotency_key_does_not_disclose_another_shoppers_order` — 409 + `IDEMPOTENCY_KEY_CONFLICT`, and the victim's order number, phone and address must not appear anywhere in the response.
* `test_guest_idempotency_key_does_not_cross_guest_sessions` — a different guest session is refused **while the original session still replays its own order** (no over-blocking).
* `test_signed_in_shopper_cannot_replay_a_guest_orders_key` — documented boundary.
* `test_concurrent_key_race_does_not_disclose_another_shoppers_order` — the `except IntegrityError` branch, with the interleaving scripted.

**Honest note on my own test.** The first version of the race test posted a duplicate key and asserted 409. That assertion passes via the **pre-flight** path alone, so the test proved nothing about the branch it was named after — and mutation **M23 survived it**, which is how the weakness was caught. It now scripts the interleaving (pre-flight sees nothing → insert loses the race → handler sees the winner's row) and asserts the handler was actually reached. A surviving mutant is the test suite telling the truth about a test; it was fixed at the cause, not by relaxing the assertion.

**Not tested this cycle:** the manual keyboard pass of the accessibility audit, the live AI Stylist provider path against a real provider (would consume quota and write a message row), and production write paths (deliberately, §5.3).

---

## 5. Production Evidence

### 5.1 What was verified in production (read-only)

* **Deployment:** Vercel API reports production `READY` at `66fdf5f7`, the merge commit of PR #172 — i.e. `main` HEAD and the deployed artifact are the same commit.
* **Read-only HTTP probes, anonymous, no writes:** `/catalog/products` 200 · `/catalog/products/1` 200 · `/catalog/categories` 200 · `/catalog/capabilities` 200 · `/try-on/capabilities` 200 · `/health` 200 · `/orders/CONF-000000` 404 · `/api/v1/openapi.json` 404.
* **Product detail honesty:** `ai_fit_score=null`, `style_compatibility_score=null`, `fit_available=false` — the surface does not invent fit or style scores.
* **Capability agreement** across catalog / try-on / health: consistent (§1.2).

### 5.2 What could have gone wrong and did not

`/commerce/cart` → **422** is **not** evidence of protection and is not reported as one: the route resolves the caller with `get_current_user_optional` (guest carts are intentional) and requires an `X-Session-Token` header, so 422 is a **missing-header validation rejection**. A 404 on `/api/v1/openapi.json` is a non-exposed schema, not an outage. A 404 on `/api/v1/liveness` and `/stylist/recommendations` reflects **no such routes** (the stylist router exposes `POST /stylist/chat` and `POST /stylist/compatibility`) — I checked the route table instead of filing a false finding.

### 5.3 What is explicitly NOT verified in production

* The **new 409 idempotency behaviour** was not exercised in production: doing so requires placing orders, which is production data mutation. It is verified by local end-to-end tests, mutation gates, and the deployed commit — **NOT VERIFIED IN PRODUCTION**, and the reason is stated rather than hidden.
* The **AI Stylist live provider path** was not invoked in production (would consume provider quota and write a message row without operational authorization) — **NOT VERIFIED IN PRODUCTION**.
* `/health/ready` (the admin surface publishing `unprobed_capabilities`) was not read in production — it requires an admin bearer token; anonymous access is refused by design — **NOT VERIFIED IN PRODUCTION**.

---

## 6. Remaining Blockers

### B1 — Virtual Try-On GPU capacity: BLOCKED (external, not code)

Re-measured this cycle, because a billing cause must not be assumed to still hold:

* Live probes of both workers → **HTTP 404 `workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled`**.
* Modal: **all apps `deployed`, 0 tasks** running; metered cost 30.85, deployed apps 29.91, credits −30.00, billed $0.02.
* Interpretation: the workspace is disabled for spend. `deployed` with zero tasks is exactly the shape of "the app exists but nothing can run" — configuration is not availability, and "deployed" was read here as status text, not as capacity.

**Blocking condition:** restoring the Modal workspace (spend limit / credits) — an operational, external action. No code change restores it. **Decision honoured:** stay honest about the offline state (offered + not renderable + `VTON_ENGINE_UNAVAILABLE` + a fit-check fallback), and do not substitute anything for a render.

### B2 — AI Stylist has no availability probe: honest gap, open

`ai_stylist` now reports `not_probed` when keys exist and nothing has been measured. That is truthful, and it is also a **gap**: nothing yet tells the platform whether the stylist can actually answer. A bounded probe (strict timeout, bounded retry, classified failures, recorded state) would close it. **Not implemented** — listed as remaining work rather than described as done.

### B3 — Payments live settlement: BLOCKED — external PSP credentials required

`payments_mode=demo`, `payments_live=false`. Demo is Demo; it is not called a live transaction anywhere in this document. Live settlement claims require live PSP credentials, which are not present.

### B4 — Open PR not mine, reported only

**PR #119** `feature/vton-complete-gap-closure` is open: 243 files, +29193/−150, base `10d80a12`, opened 2026-09-19. Also open: **#150** `fix/brand-partner-portal`, **#141** `feat/i18n-ux-privacy-terms-remediation`. None were touched. Risk noted for the repository owner: a 243-file branch based on a commit far behind `main` is a merge hazard.

### B5 — Unverified surfaces

`/health/ready` admin readiness payload, CSRF cookie flags, and rate-limit behaviour were **NOT TESTED** in this cycle (§5.3 for the first; the other two were not re-measured here and are not claimed).

---

## 7. Security Findings

Graded as required: **theoretical risk** vs **demonstrated weakness** vs **demonstrated exploitability** vs **confirmed impact**. Where exploitation was not attempted, that is stated, with the reason.

### S1 — Guest session token was not a CSPRNG value (fixed, #168)

* **Theoretical risk:** a non-CSPRNG token used as a capability is predictable in principle.
* **Demonstrated weakness:** yes — with `Math.random` and the clock pinned, 50 calls produced **1 unique token**; the input-derived entropy was zero. The token is a capability: it resolves carts for unauthenticated callers, and `/cart/merge` accepts a `guest_token` from an authenticated caller.
* **Demonstrated exploitability:** **no.** I did not predict or guess any real token, observe any real cart, or touch any account. Whether the PRNG state can be recovered across browsers/sessions is **not established**.
* **Confirmed impact:** none observed.
* **Fix:** `frontend/src/lib/secureId.ts` (CSPRNG, 128-bit, fail-closed), 11 tests including "pin `Math.random()`, assert 50 distinct tokens".

### S2 — Checkout idempotency replay returned another shopper's order (fixed, #172)

* **Demonstrated weakness:** yes, in code and in end-to-end tests: a global unique-key lookup plus no ownership assertion on both replay paths, while the sibling order routes do assert ownership.
* **Demonstrated exploitability:** requires knowing the victim's idempotency key. I did not attempt it against any real account, and no production order data was read or written from another identity.
* **Confirmed impact:** none observed; the potential impact if a key were known was disclosure of another customer's order (items, recipient, phone, address, totals).
* **Fix:** ownership-scoped replay + generic 409; gates M22/M23.

### S3 — Cart merge trusts knowledge of the guest token (residual, reported)

`/cart/merge` merges the cart named by the caller-supplied `guest_token` into the authenticated caller's account. Authority is derived from **possessing the token**, not from a server-issued association. This cycle's CSPRNG fix makes *prediction* infeasible, but the design still treats token possession as sufficient authority, so the residual risk is **token leakage** (shared device, logs, referrer), not prediction. Grade: **theoretical risk**; no exploit attempted; not re-architected this cycle.

### S4 — Positive findings (verified this cycle)

* Order-detail and tracking routes enforce ownership via `assert_order_access` (admin bypass / owner / other-user refused / guest capability by unguessable order number) — read in code and covered by tests.
* Public API schema is not exposed in production (`/openapi.json` → 404).
* Anonymous probes of protected consumer surfaces returned 401/404 as designed; the one 422 is a header-validation rejection and is not reported as protection (§5.2).
* Payment path fails closed: `PAYMENTS_LIVE=true` without live provider support yields a fabricated "authorized" only under mutation M13, which the suite kills.

---

## 8. Git / PR / Deployment Evidence

Every PR number, commit and check status below was **re-fetched from the GitHub API in this cycle**. None was reused from the previous report on trust.

| PR | Title | Merged | Merge commit |
|---|---|---|---|
| #163 | Single-source capability contract | true | `1204757a7c1557ecf9dc3879dcf016783411558b` |
| #165 | 8 consumer try-on CTAs gated | true | `c540920be8b1f9895d270a25b0ed5ada3786a8ed` |
| #166 | Evidence + GPU strategy docs | true | `c56d63e7d9cbb57968385c51cb26ed98746febd6` |
| #168 | CSPRNG session token (security) | true | `0a72b8ce4e9b3159018d433f14ee8855cd6354f2` |
| #170 | Final report (previous cycle) | true | `353f7b06c77114b48af2f03a5447940d34ceef70` |
| #172 | Honest `ai_stylist` capability + caller-scoped idempotency replay | true | `66fdf5f78fdf7c556a2a1b7547bf025d667b34cb` |

* **Branch discipline:** exactly one branch, `fix/consumer-role-capability-honesty`, used for every PR in this engagement. No second branch was created. `tmp-later` was never pushed.
* **Required checks** (`backend`, `frontend`, `release gate (production schema parity)`) were all **success** on PR #172 before merging (measured by polling the check-runs API).
* **`Workers Builds: confit-a` fails on every branch, including untouched ones** (0s, zero annotations) — Cloudflare build infrastructure, not a code failure, and not a required check. Reported, not hidden, not blamed on code.
* **Merge mechanics:** a `behind` PR returns HTTP 405 ("3 of 3 required status checks are expected") under `strict=true`. Each time, `origin/main` was merged into the branch, the checks re-run, and the merge retried. This happened three times this cycle (#168, #170, #172) and is documented rather than presented as a token or policy problem.
* **Deployment:** production `READY` at `66fdf5f7` (= `main` HEAD). The merged artifact is the deployed artifact.
* **Self-correction:** my PR #172 body first stated `2486 passed` — the number from an intermediate commit. It was corrected to the measured final `2490 passed / 4 failed / 8 skipped` with the measured baseline, because a stale number in a merged PR is still a false claim.

---

## 9. False-Claim Audit

Includes findings against **my own** previous report. Where the previous report conflicts with Git/measurement, the measurement wins and the report is corrected.

| Previous claim | Current measurement | Verdict |
|---|---|---|
| PRs #163/#165/#166/#168/#170 merged, with those merge SHAs | Re-fetched from the GitHub API: all `merged=true`, SHAs identical | **Confirmed** |
| Production deployment matched `main` HEAD (`353f7b06`) | Vercel API at the time: READY at `353f7b06` | **Confirmed then**; superseded now by `66fdf5f7` |
| "8 consumer try-on CTAs gated" | Re-verified by grep + hook tests in this cycle | **Confirmed** |
| Mutation gates M17/M18 killed | Re-executed this cycle: both killed again (and 21 more) | **Confirmed** |
| `ai_stylist_live` "is configuration-derived — latent risk" | Upgraded to a **confirmed defect**: a false negative *and* a configuration-as-readiness claim (D1, D2) | **Corrected upward** — the risk was real and worse than described |
| "…a predicted token would allow cart theft" | Conditional consequence, not a measured exploit. The weakness is demonstrated (1 unique token from 50 calls with the PRNG pinned); cross-user predictability was **not** demonstrated and was not attempted | **Overstated → corrected.** The measurement stands; the impact claim was stronger than the evidence |
| Test count quoted while a commit was still in flight | Final measured number differs by 4 | **Self-corrected** in the PR body |
| "/cart 422 shows the route is protected" | It is a missing `X-Session-Token` header rejection; guest carts are by design | **Never claimed as protection** — checked and avoided |

**Standing rule applied throughout:** "exists in code" ≠ "proven in production". Every production sentence above names the probe and its result, or is marked NOT VERIFIED.

---

## 10. Final Status

| Area | Status | Basis |
|---|---|---|
| Consumer capability contract (single source, honest states) | **VERIFIED** | Local tests + production probes agree; gates M17–M21 |
| `ai_stylist` configuration read (documented variable) | **VERIFIED** | Measured before/after; regression test; gate M20 |
| `ai_stylist` state honesty (`not_probed` vs measured `degraded`) | **VERIFIED** | Tests + gate M19/M21 |
| `ai_stylist` live availability | **NOT TESTED** | No probe exists (B2); not invoked in production |
| Checkout idempotency ownership | **VERIFIED (local/staging evidence)** | 4 end-to-end tests + gates M22/M23 |
| Same, in production | **NOT VERIFIED IN PRODUCTION** | Would require placing orders (B5, §5.3) |
| Guest session token entropy | **VERIFIED** | 11 tests incl. pinned-PRNG distinctness |
| Cart merge authority model | **PARTIALLY VERIFIED** | CSPRNG mitigates prediction; token-possession-as-authority remains (S3) |
| Virtual Try-On rendering | **BLOCKED** | External: Modal workspace disabled (B1) |
| Try-on UX honesty (offered, not renderable, no fake output) | **VERIFIED** | Production payloads + gated CTAs |
| Payments | **BLOCKED — external PSP credentials required** | `payments_mode=demo` |
| Orders / tracking ownership | **VERIFIED** | Code + tests + production 404 on unknown order |
| Database integrity script / schema revision | **PARTIALLY VERIFIED** | `/health` reports revision `0019_brand_tenant_integrity_and_ad_ledger`, schema verdict `ok`; full integrity script not re-run this cycle |
| Accessibility (automation) | **PARTIALLY VERIFIED** | 53 tests passed earlier in this engagement; manual keyboard pass NOT TESTED |
| Localization EN/AR/RTL | **PARTIALLY VERIFIED** | `i18n:check` PASSED (172→164); RTL visual pass NOT TESTED |
| Error-state engineering (401/403/404/409/422/5xx/timeout) | **PARTIALLY VERIFIED** | Exercised in tests; 409 for idempotency conflict added; no infinite-spinner evidence collected this cycle |
| Security posture | **PARTIALLY VERIFIED** | See §7: two demonstrated weaknesses fixed; three lines of enquiry NOT TESTED this cycle |
| CI / merge / deployment discipline | **VERIFIED** | GitHub API + Vercel API evidence in §8 |

**Bottom line.** The consumer role's *honesty* is now verified end to end: the platform says try-on is offered but cannot render, and it is true; it says the stylist's keys exist but are unprobed, and that is true; checkout refuses to replay another shopper's order and cannot leak it in the refusal. The one thing that would make try-on actually work is an external payment to a GPU provider, and no amount of code addresses it — which is why the code was changed to stop pretending, and the report says so.

*Nothing in this document is asserted to work beyond the evidence cited beside it. Where the evidence is missing, the words "NOT TESTED" or "NOT VERIFIED IN PRODUCTION" are used instead of an adjective.*
