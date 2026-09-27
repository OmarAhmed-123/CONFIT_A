# Virtual Try-On — provider evaluation, 2026-09-27

Measured, not surveyed. Every claim below was produced by running the thing
from this workspace on 2026-09-27. Where something could not be run, that is
stated as *unverified* rather than filled in from documentation.

---

## 1. Why production currently cannot render

`GET /api/v1/try-on/capabilities` on <https://confit-a.vercel.app> returns:

```
error_code: VTON_ENGINE_UNAVAILABLE
```

Root cause, confirmed in `backend/app/services/tryon_service.py:557`:

```python
raise RuntimeError("VTON_ENGINE_UNAVAILABLE: No GPU worker configured (VTON_WORKER_URL)")
```

`VTON_WORKER_URL` is **unset** in the deployed environment. The architecture is
sound and expects a self-hosted GPU worker (`services/vton-worker`); the worker
is simply not deployed. This is also why `/api/v1/health` reports
`ready: false` with `blocking_capabilities: ["virtual_try_on"]`.

**Nothing in the storefront code is at fault.** The try-on gate
(`useTryOnAvailability`) correctly degrades every entry point to the
measurement path while this is true, which is the behaviour shoppers see today.

---

## 2. The suggested source repository contains no try-on models

<https://github.com/open-free-llm-api/awesome-freellm-apis> was reviewed at
commit `46985b3`. It is a directory of **free LLM (text) APIs** — 31 providers
including Google Gemini, NVIDIA NIM, Groq, Cloudflare Workers AI and Hugging
Face.

Verification performed (shallow clone, whole repo):

```
grep -rioE "virtual.?try.?on|vton|idm-vton|ootd|catvton|leffa|garment|image-to-image|inpaint"
  -> 0 matches
grep -ioE "flux|stable.?diffusion|dall-?e|imagen|sdxl" README.md
  -> 0 matches
```

Modality keywords present in the README: text (30), chat (14), video (11),
audio (8), vision (7), embedding (1). **Zero image-generation entries.**

Virtual try-on is an image-to-image garment-transfer task. It is not an LLM
capability, and that catalogue cannot supply it. The useful indirect link is
that the catalogue lists **Hugging Face**, whose Spaces *do* host try-on models
— see §3.

---

## 3. What was actually tested

### 3.1 Hugging Face Spaces — WORKS

| Space | Reachable | Endpoint | Result |
|---|---|---|---|
| `yisol/IDM-VTON` | yes | `/tryon` | **rendered successfully, 24.0 s** |
| `franciszzj/Leffa` | yes | `/leffa_predict_vt`, `/leffa_predict_pt` | reachable, not rendered |
| `zhengchong/CatVTON` | no | — | space in `RUNTIME_ERROR` |

The IDM-VTON run used a real CONFIT catalogue garment (product #5, *Silk Slip
Column Maxi Dress*) and a stock person photo. Inputs and output were inspected
visually:

- input person: black sheer top
- input garment: red dress
- output: **same person** — face, hair, pose and background preserved — wearing
  the red dress

So the garment transfer genuinely happened; it was not an echo of the input.
No Hugging Face token was required.

### 3.2 Google Gemini image models — AVAILABLE, QUOTA EXHAUSTED

The project's Gemini key lists six image-output models, including
`gemini-2.5-flash-image`, `gemini-3-pro-image` and `gemini-3.1-flash-image`.

A try-on call could **not** be completed:

```
HTTP 429 RESOURCE_EXHAUSTED
quota: GenerateRequestsPerDayPerProjectPerModel-FreeTier
```

The **daily** free-tier quota is spent. Retried after the advised 30 s delay —
still 429. Gemini therefore remains **unverified for try-on from this
workspace**, despite independent benchmarking (Allure Commerce, 2026-07)
rating Gemini 3.1 the overall quality winner against dedicated VTON APIs.

### 3.3 Not testable from here

- **Fitroom** (`FITROOM_API_KEY` is set) — Cloudflare `error code: 1010`
  blocks this sandbox's egress IP. Not a key problem; re-probing is a dead end.
- **fal.ai / Replicate** — no credentials present (`FAL_KEY`,
  `REPLICATE_API_TOKEN` unset). FASHN v1.6 ($0.075/image), Kling Kolors v1.5
  ($0.07) and Leffa ($0.10) are the documented options if a key is added.

---

## 4. The licensing constraint that decides this

`backend/app/core/config.py` already maintains `VTON_ENGINE_LICENSES`, and it
is more rigorous than most of what is written publicly about these models. It
records, correctly, that a permissive repo badge does not describe the whole
dependency chain.

| Engine | Commercial | Note |
|---|---|---|
| `fashn_vton_segfee` | **yes** | CONFIT's own fork; the NVIDIA non-commercial human-parser is removed from the runtime. Verified on a real A10 GPU. |
| `fashn_vton_1_5` | no | upstream Apache-2.0 but hard-depends on the restricted parser |
| `catvton` | no | CC BY-NC-SA 4.0 |
| `leffa` | unverified | MIT repo, but SCHP / DensePose / Detectron2 chain unverified |

**IDM-VTON is CC BY-NC-SA 4.0 — non-commercial.** It demonstrably works and is
free, but wiring it in as a production provider for a storefront that takes
payments would contradict the licensing discipline this project has already
established. It is suitable as a **development/demo** engine only, and must be
labelled as such if added.

This is the substantive finding: the blocker on try-on is **not** model
availability. A working free model was found and run in 24 seconds. The blocker
is that the commercially-clean path (`fashn_vton_segfee`) needs a GPU worker
deployed and `VTON_WORKER_URL` set.

---

## 5. Honest limits on "flawless try-on for every garment"

Stated plainly because the request asked for no failure modes at all:

1. **No diffusion try-on model available today guarantees identity
   preservation.** The published benchmarks describe identity and silhouette
   drift as a live problem across CatVTON, Leffa and IDM-VTON. Accepting a
   requirement of "zero facial change, zero failures" would be committing to
   something the state of the art does not deliver.
2. **Accessories are not covered by garment VTON models.** IDM-VTON, CatVTON
   and Leffa are trained on upper body / lower body / dresses. Clutches,
   jewellery, eyewear and shoes need either a general image-editing model
   (Gemini) or an accessory-specific pipeline. A category-aware router is
   required; a single endpoint will not do it.
3. **Multi-garment outfits** require either OOTDiffusion (purpose-built, still
   non-commercial) or sequential application, which compounds artefacts with
   each pass.

---

## 6. Recommended order of work

1. **Deploy the GPU worker** and set `VTON_WORKER_URL` to the
   `fashn_vton_segfee` engine. This is the only change that makes try-on live
   on a commercially clean footing, and the code for it already exists.
2. **Add a paid hosted fallback** (fal.ai FASHN v1.6 or Gemini on a paid tier)
   behind the same capability probe, so a worker cold-start or outage degrades
   to a second renderer instead of to the ruler.
3. **Route by garment category** before rendering, so accessories are not sent
   to a model trained only on clothing.
4. Keep `useTryOnAvailability` as the single gate. It is already correct and is
   why today's outage is visible to shoppers as an honest fit-check rather than
   a dead button.

No provider was wired into the runtime in this pass, because every candidate is
either non-commercial (IDM-VTON, CatVTON), quota-blocked (Gemini),
network-blocked from here (Fitroom) or uncredentialled (fal.ai). Shipping an
unverifiable provider chain would have been the opposite of what this document
is for.
