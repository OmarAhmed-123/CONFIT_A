# Virtual Try-On: GPU availability strategy

**Date:** 2026-09-22
**Status:** design + operator runbook. The code half shipped in the same branch;
the *funding* half is a business decision this document exists to make explicit.

---

## 1. The actual failure mode

Try-on did not fail because of a bug in the rendering pipeline. It failed
because the GPU host was disabled at the billing layer:

```
$ modal billing summary
  Metered Cost: 30.85   Credits: -30.00   Billed Cost: $0.02
$ curl -s -o /dev/null -w "%{http_code}" https://omarsafealden--confit-vton-worker-segfee-*.modal.run
404   modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled
```

`modal app list` shows all five apps `deployed` — the apps are fine; the
workspace that hosts them is out of credit. **Metered apps keep costing money
while idle**, because the container definitions are live even with zero tasks
(`29.91` of the `30.85` is "Deployed Apps").

So the failure is not "the worker broke". It is "the worker was free and then
was not, and the platform kept advertising it". The second half was the real
product defect and is fixed; this document is about the first half.

### Why the fallback is the fit check, and not a smaller model

A tempting "fallback" is to route to a cheaper local model. Rejected, and the
reasons are structural rather than cost:

* **Quality collapse is invisible to the user.** A weaker engine produces a
  plausible-looking but wrong render. The repo already treats that as a first
  class problem — `test_vton_mask_quality`, the pose/hand artifact regression
  harness, and the worker's own echo-detection (`VTON_OUTPUT_INVALID`) all exist
  precisely to stop the platform from shipping a render that looks like success.
  A degraded engine would defeat all three at once.
* **The commercial licence question is already settled in one direction.**
  `VTON_ENGINE=fashn_vton_segfee` is the commercial fork; CatVTON is
  non-commercial and is documented as never the production default. A "cheaper
  fallback" that silently swaps to a non-commercial engine would be a licensing
  incident triggered by an outage — the worst possible time to discover it.
* **It would not actually be cheaper.** The cost driver is a warm container
  holding a ~1GB+ model, not the choice of model.

Therefore the honest degradation is a **different capability, correctly named**:
the no-photo fit check (`/tryon/no-photo-fit`, `FitFinderView`, `openRuler` in
the UI), which is CPU-only, needs no GPU, and answers a question the user
actually has. This is what the shipped code does, with the label changed from
"Try On" to "Fit Check" so the user is never told they are getting a render.

---

## 2. Options for restoring real try-on

| Option | Real cost | Time to restore | Risk | Notes |
|---|---|---|---|---|
| **A. Renew the Modal workspace** | ~$30/mo minimum to stay out of the disabled state; metered by warm-container time | minutes (`modal deploy`) | app definitions are already correct | No code change. The probe flips to `ready` and every gate re-opens automatically. |
| **B. Scale-to-zero the worker** | Lower idle cost | needs a deploy + a probe-tolerant UX | cold starts: `cold_start_seconds_budget: 120` already in the SLA contract | `VERDICT_COLD_START` is already modelled end-to-end, including the amber "warming up" banner. The UX for this exists. |
| **C. Add a second provider behind the same contract** | new provider's pricing | days | two engines to keep honest | The abstraction already supports it — see §3. |
| **D. Retire try-on** | 0 | immediate | honest, and permanent | Unset `VTON_WORKER_URL`: the platform reports `misconfigured` ("not offered") rather than a permanent outage, and the UI keeps offering the fit check. |

**Recommendation:** A or D now (both are one config change), C only if try-on is
strategically required and the GPU budget is recurring. B is a cost optimization
on top of A, not an alternative to it.

The important property: **every option is safe to choose at any time**, because
the platform's advertised capability is derived from a live probe. Choosing A
re-opens the feature automatically; choosing D closes it honestly. There is no
option left that produces the 2026-09-22 state, where the platform advertised a
capability it could not deliver.

---

## 3. Adding a second provider (option C), concretely

The abstraction is already in place and correctly scoped:

```python
class VTONEngine(ABC):          # services/vton-worker/engine/base.py
    name: str
    commercially_usable: bool
    @abstractmethod
    def load(self) -> None: ...
    @abstractmethod
    def render(self, person_image, garment_image, *, category, **kwargs) -> Image.Image: ...
    @property
    def supports_multigarment(self) -> bool: ...
```

Because `SUPPORTED_VTON_ENGINES` gates `VTON_ENGINE` at startup
(`backend/app/core/config.py:480`), adding a provider is:

1. implement `VTONEngine` for the new backend (one model, no network, no auth —
   the ABC's docstring is explicit that business logic stays outside);
2. add its identifier to `SUPPORTED_VTON_ENGINES`;
3. **add it to `MODEL_REGISTRY.json` with its licence**, so
   `commercially_usable` stays checkable rather than asserted.

What must NOT be done: a provider-level failover that silently substitutes one
engine for another mid-flight. A render that came from an unexpected engine is
indistinguishable to the user from a correct one, which is the same class of
defect as the echo-detection gate. If failover is ever wanted, the response must
carry which engine rendered it, and the disclosure must reach the UI.

---

## 4. Operator runbook

**Diagnose (no credentials needed):**

```bash
curl -s https://confit-a.vercel.app/api/v1/try-on/capabilities | python3 -m json.tool
#   engine_state / engine.error_code / engine.detail / engine.circuit_state
curl -s https://confit-a.vercel.app/api/v1/health | python3 -m json.tool
#   ready, blocking_capabilities
```

`engine.error_code` distinguishes the situations the old string conflated:

| `error_code` | Meaning | Action |
|---|---|---|
| `VTON_ENGINE_UNAVAILABLE` | workspace disabled / spend limit / app stopped | fund or retire the workspace (§2) |
| `VTON_WORKER_NOT_READY` | reachable, model not loaded yet | retry; expect warm-up |
| `VTON_WORKER_COLD_START` | reachable, cold | first job slow; not an outage |
| `VTON_AUTH_FAILURE` | admin token mismatch | check `VTON_WORKER_ADMIN_TOKEN` vs the Modal secret |

**Cost control (the actual root cause):**

```bash
modal billing summary          # metered vs credits
modal app list                 # which apps still cost money
```

Deployed-but-idle apps are billed. If a workspace is not being used, stop the
apps — leaving them deployed is what produced this outage.

---

## 5. What was changed in code, and what was not

**Changed:** the platform's advertised try-on capability is derived from a live
probe on every surface; the UI degrades to the fit check under its own name; the
sentence the user reads is authored once and localized.

**Deliberately not changed:** the rendering pipeline, the engine selection, the
`VTONEngine` contract, the delivery/retention rules. Nothing about *how* a
try-on renders was touched, because nothing about it was shown to be wrong —
and changing a working pipeline while its host is offline would have meant
shipping unverifiable code.

That last point is the honest limit of this work: **the rendering path cannot be
end-to-end verified in production right now**, because there is no production
engine to render with. The verification that exists is the probe contract, the
cross-surface agreement invariant, and the mutation gates — all of which are
testable without a GPU. Everything beyond that is explicitly listed as unproven
in `CONSUMER_ROLE_REMEDIATION_20260922.md` §3.
