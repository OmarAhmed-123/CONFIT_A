# Consumer role — capability honesty remediation

**Date:** 2026-09-22
**Scope:** the `consumer` role only (home, discover, stylist, try-on/fit,
wardrobe, looks, checkout, orders, profile), and only the parts that were
actually reachable and measurable.
**Branch:** `fix/consumer-role-capability-honesty` (one branch, sequential PRs)
**Merged as:** [#163](https://github.com/OmarAhmed-123/CONFIT_A/pull/163)
(backend capability single-source) →
[#165](https://github.com/OmarAhmed-123/CONFIT_A/pull/165) (consumer CTA
gating) → this document.

This document separates three things that are easy to blur:

1. **Measured now** — reproduced live, with the command and its output.
2. **Fixed and proven** — changed in code, with a test that fails if the defect
   returns (a mutation gate, not just a green suite).
3. **Blocked, and honest about it** — cannot be fixed by code; the platform is
   changed to report it truthfully instead of promising otherwise.

---

## 1. The audit's two headline findings, verified

Both were still live on 2026-09-22:

```
$ curl -s https://confit-a.vercel.app/api/v1/try-on/capabilities
{"engine_state":"temporarily_unavailable","engine":{"verdict":"unavailable",
 "production_ready":false,"error_code":"VTON_ENGINE_UNAVAILABLE", ...}}

$ curl -s https://confit-a.vercel.app/api/v1/catalog/capabilities
{"payments_live":false,"payments_mode":"demo","bnpl_live":false,
 "vton_gpu_ready":true, ...}

$ curl -s https://confit-a.vercel.app/api/v1/health
{"status":"healthy","ready":false,"blocking_capabilities":["virtual_try_on"], ...}
```

Three surfaces, two answers. The audit reported the contradiction; what it could
not see is **why it survived**, which turned out to be the more useful finding.

### 1.1 Root cause of the contradiction: two derivations, and a test defending the wrong one

`capability_flags()` computed:

```python
"vton_gpu_ready": bool(settings.VTON_WORKER_URL),
```

with the comment *"Unchanged wire contract"* — eighty lines below a function in
the same file that derives the identical fact from a live probe and explains at
length why *"configuration is not availability"*. `get_vton_capabilities()`
probed the worker over the network. So the two endpoints were not disagreeing
about a value; they were answering from different sources while both being
described as sharing "one source of truth".

The worse half: the frontend binds its commerce/trust claims to
`/catalog/capabilities` via `useCapabilities()`. **The one surface that drove
user-visible promises was the one that lied**, and the other two were honest.

And it was protected by a test:

```python
# test_capabilities_endpoint.py, before this change
def test_vton_and_stylist_flags_follow_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://modal.example/process")
    assert caps["vton_gpu_ready"] is True      # <-- the defect, as an expectation
```

A green suite defended the bug. This is the reason to state the lesson plainly:
**passing tests are evidence that code matches what the test author believed,
not that the belief was true.** That test is now rewritten to assert the honest
contract (`test_vton_gpu_ready_does_not_follow_configuration`).

### 1.2 Root cause of P0: the GPU workspace is disabled at the billing level

The audit said the GPU worker was unreachable. The mechanism, measured:

```
$ curl -s -o /dev/null -w "%{http_code}" \
    https://omarsafealden--confit-vton-worker-segfee-fashninferences-2a7124.modal.run
404
modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled

$ modal billing summary
  Metered Cost:        30.85
    Deployed Apps:     29.91
    Volumes:            0.83
    Ephemeral Apps:     0.11
  Credits:            -30.00      <-- exhausted
  Free Storage:        -0.83
  Billed Cost:         $0.02
```

`modal app list` shows all five apps in state `deployed`, so the apps exist and
were never deleted. The **workspace** is disabled because metered usage
($30.85) passed the free-credit allowance ($30.00).

This is important for the remediation plan, because it means:

* no code change, redeploy, or URL fix can bring try-on back;
* the new probe classifier is *already correct* — it reports exactly this;
* the honest requirement on the platform is therefore **not** "make try-on
  work" but "stop advertising try-on while it cannot work", which **is**
  fixable in code and is what this change does.

---

## 2. What was fixed, and how it is proven

### 2.1 One classifier, called by every surface

`engine_state_from_probe()` in `backend/app/services/vton_worker_observability.py`
is now the only place the question *"can try-on render right now?"* is answered.
It returns the canonical wire states (`available`, `cold_start`,
`temporarily_unavailable`, `misconfigured`) plus `engine_can_render()` and the
backend-authored user sentence.

Callers, all of which previously derived the answer themselves:

| Surface | Before | After |
|---|---|---|
| `capability_flags` (`/catalog/capabilities`) | `bool(settings.VTON_WORKER_URL)` | `engine_state_from_probe(probe)` |
| `_vton_capability` (`/health`, `/health/ready`) | private re-derivation | `engine_state_from_probe(probe)` |
| `get_vton_capabilities` (`/try-on/capabilities`) | inline if/elif chain | `engine_state_from_probe(probe)` |
| user-facing sentence | duplicated in the service | `engine_state_user_message()` |

Unifying the *probe* was not enough last time — each surface had the probe and
still derived its own verdict. Unifying the *derivation* is the actual fix.

### 2.2 The payload now distinguishes "broken" from "not offered"

`/catalog/capabilities` gained three fields (the original nine are unchanged in
name and type):

* `vton_engine_state` — canonical state, identical to `/try-on/capabilities`
* `vton_offered` — `false` means this deployment does not offer try-on
* `vton_renderable` — whether a job submitted now can render

Without these, a UI that wants to be honest about an offline engine has to
parse English prose out of `engine.detail`, which is how honesty labels drift.

### 2.3 The consumer UI can no longer route into a render that cannot happen

`frontend/src/hooks/useTryOnAvailability.ts` is the single gate. Eight consumer
entry points now use it, each of which previously opened a try-on flow
unconditionally:

| File | Entry point |
|---|---|
| `ProductDetailView.tsx` | primary image overlay CTA, "buy box" CTA |
| `HomeView.tsx` | hero CTA, editorial product card, product grid icon |
| `DiscoverView.tsx` | product grid icon, card CTA |
| `TryOnFitView.tsx` | studio feature card, per-product grid CTA |

Behaviour when the engine cannot render:

* the control **keeps the working capability** — it routes to the no-photo fit
  check (`openRuler`), which needs no GPU;
* the **label changes** (`Try On` → `Fit Check`), because a control that says
  "Try On" and does not try on is exactly the defect being closed;
* where no honest fallback exists the control is `disabled`, never a dead click.

It also fixes a bilingual gap in the same area: `engine_state` is a
language-neutral discriminator, so the UI now localizes its own sentence
(English **and** Arabic) instead of rendering the backend's English
`user_message` into an Arabic page. The upstream prose is retained as
`upstreamDetail` for support, never as the shopper's message.

### 2.4 Proof: mutation gates, not just passing tests

Two mutations were added to `backend/scripts/run_mutation_gates.py` and each
reverts one half of the fix. The suite must **kill** them:

```
$ PYTHONPATH=. python3 backend/scripts/run_mutation_gates.py --only M17,M18 --skip-baseline
[M17] KILLED   VTON: catalog capability flags derive GPU readiness from configuration
               presence instead of the live probe
[M18] KILLED   VTON: try-on capabilities re-derive engine_state locally instead of
               using the shared classifier

MUTATION GATES: 2 killed, 0 survived, 0 not applicable
```

* **M17** restores `"vton_gpu_ready": bool(settings.VTON_WORKER_URL)`.
* **M18** restores the local `engine_state` derivation in `tryon_service`.

This is the difference between *fixed* and *protected*: without M17/M18 the fix
could be reverted by the next refactor and the suite would stay green — which is
precisely how the original defect shipped.

The new backend test file `tests/test_capability_single_source.py` asserts the
**agreement invariant between surfaces** rather than any single surface's value,
so it stays meaningful as the probe implementation changes. The new frontend
test `useTryOnAvailability.test.tsx` (15 cases) pins the CTA rule, including
that a failed probe is reported as *unmeasured*, never as "the feature is
broken".

### 2.5 Local verification

```
backend  : 2 mutation gates KILLED; 50 tests green across the three affected
           files (capabilities endpoint, single-source invariant, health contract)
frontend : i18n gate PASSED — locales in parity, 0 newly untranslated strings
           (baselined backlog shrank 172 → 164)
           tsc --noEmit → exit 0
           vitest → 31 files / 254 tests passed, plus 15 new cases
```

---

## 3. What is still not fixed, stated plainly

The audit's own rule applies to this document: *"present in the code" is not
"proven in production".*

| Item | Status | Why |
|---|---|---|
| Try-on cannot render | **Still true** | Modal workspace disabled by billing. Requires funding the workspace; no code path can substitute. The platform now says so instead of advertising `true`. |
| Payments not live | **Still true** | `payments_mode=demo`, `payments_live=false`, `bnpl_live=false`. Correctly reported; not falsely advertised. A separate scope. |
| Wardrobe / look / cart mutation persistence | **Not yet proven** | Reads prove endpoints exist, not that a new item survives a refresh or is visible to another account. Needs a staging UAT run. |
| AI endpoint latency/loading states | **Not yet proven** | Needs per-route timeout and slow-API behaviour tests. |

Two further honest notes:

* `ai_stylist_live` is still derived from *the presence of a provider key*
  (`bool(_ai_provider_keys())`) — the same class of configuration-vs-availability
  conflation that caused this incident. It is **not** currently contradicted by
  another surface, so it is a latent risk rather than a live defect, and it is
  named accordingly in the test that pins it. It should get a probe of its own.
* The `_vton_capability()` docstring still reasons correctly that *"not offered
  is not broken"*, but that reasoning was never applied to the flag the UI
  reads. The new `vton_offered` field is where it now lives.

---

## 4. Recommended next steps, in order

1. **Fund or retire the GPU worker.** If the Modal workspace is renewed,
   `modal deploy services/vton-worker/modal_app_segfee.py` restores service with
   no code change: the probe will report `ready` and every gate re-opens
   automatically. If it is retired, set `VTON_WORKER_URL` unset so the platform
   reports `misconfigured` (not offered) rather than a permanent outage.
2. **Give the AI stylist a probe**, so no capability is advertised on
   configuration evidence alone (closes the latent risk in §3).
3. **Staging UAT for mutation lifecycle** — create a wardrobe item, a look and a
   cart item; verify persistence after refresh and cross-account visibility.
4. **Separate demo checkout from live settlement** and pin the copy.
5. **Per-route latency budget tests** for try-on and stylist.

---

## 5. Reproducing the evidence

```bash
# the contradiction (before the fix):
curl -s https://confit-a.vercel.app/api/v1/catalog/capabilities
curl -s https://confit-a.vercel.app/api/v1/try-on/capabilities

# the billing cause:
modal app list && modal billing summary

# the proof that the fix is protected:
PYTHONPATH=. python3 backend/scripts/run_mutation_gates.py --only M17,M18 --skip-baseline

# the affected suites:
PYTHONPATH=. python3 -m pytest backend/tests/test_capability_single_source.py \
    backend/tests/test_capabilities_endpoint.py \
    backend/tests/test_health_readiness_contract.py -q
```

*If you find a claim in this document that does not reproduce, the claim is
wrong and the document should be corrected — not the measurement.*
