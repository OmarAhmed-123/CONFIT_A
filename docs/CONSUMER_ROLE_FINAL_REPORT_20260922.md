# Consumer Role — Final Engineering Report

**Repository:** [OmarAhmed-123/CONFIT_A](https://github.com/OmarAhmed-123/CONFIT_A)
**Production:** https://confit-a.vercel.app/
**Date:** 2026-09-22
**Branch:** `fix/consumer-role-capability-honesty` (one branch, sequential PRs, as requested)

> This report is written so that every claim can be checked. Where I could not
> verify something, it says so instead of implying success. The rule I held
> myself to: **the project should actually work, and the report should reflect
> what actually happened** — not the reverse.

---

## A. What was found

Five real defects in the consumer path. Two were in the audit report; three were
found by reading the code against the runtime.

| # | Severity | Defect | Where |
|---|---|---|---|
| 1 | **P1** | `/catalog/capabilities` advertised `vton_gpu_ready: true` while `/try-on/capabilities` said `temporarily_unavailable` — same GPU, same second | `capability_service.capability_flags` |
| 2 | **P1** | Eight consumer try-on entry points opened a render flow unconditionally — they never read any capability flag at all | `HomeView`, `DiscoverView`, `ProductDetailView`, `TryOnFitView` |
| 3 | **P1 security** | The guest session token — a *credential* for an unauthenticated shopper's cart — was generated with `Math.random()` | `frontend/src/services/apiClient.ts` |
| 4 | **P0** | Try-on cannot render at all: the Modal GPU workspace is disabled at the **billing** layer | infrastructure, not code |
| 5 | **Process** | A test asserted defect #1 as correct behaviour, which is why it survived review | `test_capabilities_endpoint.py` |

### Defect 4 — verified root cause, not the assumed one

The audit said the worker was unreachable. True, but the cause is more specific
and it changes the remedy:

```
$ curl -s -o /dev/null -w "%{http_code}" \
    https://omarsafealden--confit-vton-worker-segfee-fashninferences-2a7124.modal.run
404    modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled

$ modal app list        # all five apps: state "deployed"  (0 tasks)
$ modal billing summary
  Metered Cost: 30.85    Credits: -30.00    Billed Cost: $0.02
```

The apps exist and were never deleted. The **workspace** is over its free-credit
allowance (`29.91` of the `30.85` is "Deployed Apps" — deployed-but-idle apps are
billed). **No code change, redeploy or URL fix brings try-on back.** So the
fixable requirement was never "make try-on work"; it was **"stop advertising a
capability that cannot render"** — which is fixable, and is what shipped.

---

## B. Root causes

**#1 — a second *derivation*, not a missing probe.** `get_vton_capabilities()`
and the readiness probe both already used the live probe. `capability_flags()`
derived the same fact from `bool(settings.VTON_WORKER_URL)` — eighty lines below
a function in the same file that explains at length why *"configuration is not
availability"*. Unifying the probe was therefore **not** the fix. The defect was
the second derivation, so the fix unifies the derivation.

**#2 — nothing read the flag.** The honest backend verdict and the dishonest
flag were both inert: the UI opened a render flow regardless. The audit phrased
the requirement precisely — *"the presence of a Try-On button does not mean the
implementation works"* — but the button was never wired to the answer.

**#3 — a non-cryptographic PRNG on a credential.** Measured: with the PRNG
pinned and the clock pinned, 50 calls produce **one** value — the token's only
real input was a clock reading, so every token minted in the same millisecond
was byte-identical. The backend treats this value as a capability:
`get_or_create_cart` resolves the cart *by token* for unauthenticated callers,
and `POST /cart/merge` merges an arbitrary `guest_token` into an authenticated
caller's own account. A predictable token is therefore an IDOR waiting for the
arithmetic to be done.

**#5 — the test encoded the bug.** Green tests are evidence that code matches
what the author believed, not that the belief was true. This is the single most
transferable lesson from the whole exercise.

---

## C. What was changed

| PR | Files | Change |
|---|---|---|
| [#163](https://github.com/OmarAhmed-123/CONFIT_A/pull/163) | `vton_worker_observability`, `capability_service`, `tryon_service`, `catalog_controller`, +2 tests, mutation gates | One `engine_state_from_probe()` classifier called by **every** surface; catalog flags measured, not configured; `vton_engine_state` / `vton_offered` / `vton_renderable` added (nine original keys unchanged) |
| [#165](https://github.com/OmarAhmed-123/CONFIT_A/pull/165) | `useTryOnAvailability` (new), 4 consumer views, `useCapabilities`, `apiServices`, `queryClient`, `en/ar` | **One** gate for all 8 CTAs; degrades to the working no-photo fit check under its own label; blocked where no honest fallback exists; user message localized from the machine state, not the backend's English prose |
| [#166](https://github.com/OmarAhmed-123/CONFIT_A/pull/166) | 2 docs | Evidence report + GPU availability strategy / operator runbook |
| [#168](https://github.com/OmarAhmed-123/CONFIT_A/pull/168) | `secureId` (new), `apiClient`, `CheckoutView`, +11 tests | CSPRNG capability identifiers, fail-closed; unifies the duplicated idempotency-key pattern |

Design discipline applied: the gate is **one** module rather than eight copies
(DRY); the classifier is a pure function, so the honesty rule is unit-testable
without a DOM or a network; no pattern was introduced for decoration.

---

## D. What was tested

**Regression guards that fail if the defect returns** (the important ones):

```
$ python3 backend/scripts/run_mutation_gates.py --only M17,M18 --skip-baseline
[M17] KILLED  catalog flags derive GPU readiness from configuration presence
[M18] KILLED  try-on re-derives engine_state locally instead of the shared classifier
MUTATION GATES: 2 killed, 0 survived, 0 not applicable
```

Without M17/M18 the fix could be reverted by the next refactor and the suite
would stay green — exactly how this defect shipped the first time.

For the security fix, the decisive test does not check that the token "looks
random". It **pins `Math.random()` and asserts 50 tokens are still distinct**,
with an inverse guard proving the legacy derivation collapses to one value under
the same pin (so the assertion is not vacuous).

**Full runs (local):**

| Suite | Result |
|---|---|
| Backend full suite | **2432 passed, 8 skipped**, 4 pre-existing mediapipe env failures (see below) |
| Frontend `vitest run` | **33 files / 280 tests passed** |
| `npx tsc --noEmit` | exit 0 |
| `npm run i18n:check` | PASSED — locales in parity; untranslated backlog **shrank** 172 → 164 |
| Consumer lifecycle + isolation (`g4_wardrobe`, `outfit_composer`, `cart_returning_guest`, `flow_e`, `tryon_session_idor`) | **66 passed** |
| AI stylist grounding / failover / timeout / truthfulness | **44 passed** |
| Accessibility + i18n parity | **53 passed** |

The 4 backend failures are `test_vton_pose_artifact_regression`, reproduced
**identically on the unmodified baseline**: `mediapipe` has no wheel for the local
Python 3.13 (CI installs it on 3.12). They are environmental, and I am not
claiming otherwise.

---

## E. Evidence

**The contradiction is resolved in production** (measured after #163/#165
deployed):

```
$ curl -s https://confit-a.vercel.app/api/v1/catalog/capabilities
{"vton_gpu_ready": false, "vton_engine_state": "temporarily_unavailable",
 "vton_offered": true, "vton_renderable": false, "payments_mode": "demo", ...}

SURFACE                                        gpu_ready   engine_state               renderable
--------------------------------------------------------------------------------------------
/catalog/capabilities                          False       temporarily_unavailable    False
/try-on/capabilities                           False       temporarily_unavailable    False
/health                                        False       (blocking)                 False
--------------------------------------------------------------------------------------------
ALL THREE SURFACES AGREE: True
```

**Server-side auth/RBAC (no credentials sent, production):**

```
GET /auth/me                       -> 401 PROTECTED
GET /wardrobe, POST /wardrobe/items-> 401/404 PROTECTED
GET /orders, GET /looks            -> 401/404 PROTECTED
GET /brand/profile, /brand/products-> 401 PROTECTED
GET /partner/analytics/conversion  -> 401 PROTECTED
GET /cart                          -> 422  = missing required X-Session-Token
```

That last line is stated as it is: a 422 is a *validation* rejection of a
missing session header (guest carts are deliberate — `get_current_user_optional`),
**not** an authentication check. Calling it "protected" would have been the kind
of rounding-up this report is supposed to avoid.

**No unconditional try-on claim remains** in the consumer UI:

```
$ grep -rn '">Try On<|Launch Virtual Try-On|Try on digitally' frontend/src/views/consumer/*.tsx
(no matches)
```

**CI:** every required status check (`backend`, `frontend`, `release gate
(production schema parity)`) passed on each merged PR. `Workers Builds:
confit-a` fails — it also fails on PR #162's unrelated branch, with a 0-second
duration and zero annotations, so it is environmental, not caused by these
changes. It is not a required check.

---

## F. Environment status

| Capability | LOCAL | PRODUCTION |
|---|---|---|
| Capability contract consistency | PASS (invariant tests + mutation gates) | **PASS — verified live, all three surfaces agree** |
| Consumer try-on CTA honesty | PASS (15 tests) | **PASS — no unconditional claim remains** |
| Session token entropy (CSPRNG) | PASS (11 tests) | Deployed via #168 |
| Virtual Try-On **rendering** | Not verifiable (no GPU locally) | **BLOCKED — workspace disabled at billing layer** |
| Wardrobe / looks / cart lifecycle | PASS (66 tests) | Not exercised against production accounts |
| AI stylist grounding + failover | PASS (44 tests) | Endpoint live; not exercised end-to-end here |
| Payments | Demo mode by design | **`payments_mode=demo`, `payments_live=false`, `bnpl_live=false`** |
| Auth / RBAC server-side | PASS | **PASS — 401/403 observed** |
| Arabic / RTL | PASS (i18n parity + a11y) | Bundles deployed |
| Accessibility | PASS (53 tests) | Not re-run against production DOM |

---

## G. Remaining blockers

Only genuine external/infrastructure blockers, with exact next steps.

1. **VTON rendering — BLOCKED (billing).** Fund the Modal workspace, or retire
   the feature. Both are one action and both are safe, because advertised
   capability is now derived from a live probe: funding re-opens every gate
   automatically; unsetting `VTON_WORKER_URL` reports `misconfigured` (not
   offered) instead of a permanent outage. Operator runbook:
   `docs/VTON_GPU_AVAILABILITY_STRATEGY_20260922.md`.
2. **Live payments — BLOCKED (no live PSP credentials).** Demo mode is honestly
   labelled; I did **not** claim live settlement.
3. **Production mutation UAT (scenarios F/G/H/I/J) — NOT DONE.** Read-only probes
   plus the local lifecycle suites are what exist. Creating wardrobe items,
   looks, carts and orders under real consumer accounts is a write operation
   against production data and a product decision; I did not perform it.
4. **AI Stylist end-to-end in production — NOT DONE** (would consume live
   provider credits and needs its own latency budget).
5. **Token rotation for previously issued tokens.** The CSPRNG fix stops *new*
   tokens being predictable; it does not invalidate already-issued low-entropy
   ones. Rotating them would orphan live guest carts (`carts.session_token` is
   UNIQUE and is the order join key), so it is a product decision — flagged, not
   silently skipped.
6. **`ai_stylist_live` is still configuration-derived** (`bool(_ai_provider_keys())`)
   — the same *class* of issue as defect #1, though not currently contradicted by
   another surface. Latent risk; it deserves a probe. Named rather than hidden.

---

## H. False-claim audit

Places where the project asserted a capability it could not deliver, and how each
was corrected.

| Claim | Was it a lie? | Correction |
|---|---|---|
| `/catalog/capabilities` → `vton_gpu_ready: true` | **Yes.** Derived from an env var while the GPU was unreachable. The worst offender, because `useCapabilities` binds the consumer UI's trust claims to this payload | #163 — measured from the live probe |
| Test `test_vton_and_stylist_flags_follow_configuration` | **Yes — the defect formalized as an expectation.** `VTON_WORKER_URL` set ⇒ asserts `vton_gpu_ready is True` | #163 — rewritten as `test_vton_gpu_ready_does_not_follow_configuration` |
| `Math.random()` session token | **Yes, by implication** — treated as a credential while generated by a non-CSPRNG | #168 — CSPRNG, fail-closed |
| Try-on CTAs ("Try On", "Launch Virtual Try-On", "Try on digitally") | **Yes, in effect** — advertised a render that could not happen | #165 — all 8 gated; label changes with the capability |
| `/health` → `"vton_pipeline": "configured: …"` | **Was** a configuration-vs-availability claim | Already corrected before this work (2026-09-21); verified still probe-driven |
| `payments_mode=demo` / `payments_live=false` | **No** — honestly reported, correctly disclosed in the UI footer | No change needed |
| `ai_stylist_live` | **Not currently contradicted**, but configuration-derived | Flagged as latent risk (§G.6) |

The pattern across almost all of these is one mistake: **an environment variable
being treated as a measurement.** That is the thing worth remembering.

---

## I. On the human note

The report is not here to blame anyone, and I have deliberately written it that
way. Two things are both true:

* the code had a real defect that shipped, and
* the surrounding engineering was strong enough that the fix took a day, was
  verifiable end to end, and could be **proven** not to regress.

That did not happen by accident. The existing probe, the mutation-gate harness,
the readiness/criticality model, and the i18n ratchet are all things this project
already had — they are what made the defects *findable and provable*. The
mutation gates in particular are the reason this fix is protected rather than
merely present, and they were pre-existing infrastructure.

The most valuable finding is not any single bug. It is that **a green test suite
can defend a bug**, and the countermeasure is asking of every test not "does it
pass?" but **"what would it take for this to fail?"** A test that cannot fail is
documentation of an assumption, not a check.

Everything here is falsifiable. If a claim in this report does not reproduce, the
claim is wrong — correct the report, not the measurement.
