# NVIDIA Agent Skills — applicability triage for CONFIT_A

**Source:** <https://github.com/NVIDIA/skills> (Apache-2.0 / CC-BY-4.0)
**Reviewed:** 2026-09-27 · **Catalogue size at review:** 383 skill directories
**Method:** full clone, directory-by-directory pass over every skill's `SKILL.md`
front-matter and prerequisites.

---

## Summary

**One skill was directly applicable and has been used. It is the only one.**

CONFIT_A is a fashion e-commerce and fit web application: FastAPI + SQLAlchemy
on Neon Postgres, a Next.js front end on Vercel, and hosted model inference over
`integrate.api.nvidia.com`. It owns no GPUs, no Kubernetes cluster, no embedded
devices and no robotics, medical, simulation or networking hardware.

The catalogue is overwhelmingly aimed at exactly those things. Reporting a large
number of "relevant" skills would be padding, so this document states plainly
what applied, what could apply if the infrastructure changed, and what cannot.

| Verdict | Count | Meaning |
|---|---:|---|
| **Applied** | 1 | Used in this repository, with committed artefacts |
| **Conditionally applicable** | 8 | Real fit, blocked on infrastructure or entitlement |
| **Not applicable** | 374 | Different hardware or problem domain entirely |

---

## 1. Applied

### `nemotron-policy-generator`

Guides building a **bring-your-own content-safety policy** for
`nvidia/Nemotron-3-Content-Safety`: a custom taxonomy, an allow-list, and the
inference-prompt shape the model expects.

Used for the content-safety work in this change set. Artefacts:

- `docs/safety/confit_safety_policy_v1.0.0.md` — policy, taxonomy S23–S26,
  allow-list, severity/enforcement map, refusal copy.
- `backend/app/services/content_safety_service.py` — enforcement.
- `backend/tests/test_content_safety_service.py` — 12 offline regression tests.

The skill's prescribed workflow — draft taxonomy, write an allow-list, then
**calibrate against real prompts** — earned its keep. Calibration caught a false
positive that a desk review would have shipped: *"I want to lose 10 kg before my
wedding, what should I wear now?"* was classified **Suicide and Self Harm**.
An allow-list clause distinguishing *stating a goal* from *asking for a
dangerous method* fixed it, and a follow-up probe confirmed the genuinely unsafe
variant (*"…how do I starve myself to get there?"*) still blocks. Both cases are
now pinned by tests.

---

## 2. Conditionally applicable — real fit, currently blocked

Listed with the specific blocker, so each can be revisited if that changes.

| Skill | Value to CONFIT | Blocker |
|---|---|---|
| `nemo-retriever` | Semantic search over the product catalogue and size guides | Needs LanceDB locally or a deployed retriever NIM. Feasible; not yet justified at current catalogue size |
| `tao-finetune-clip` | Fine-tune CLIP on garment imagery for visual similarity | Requires GPU + TAO toolkit |
| `tao-generate-image-embeddings` | Image vectors for "find similar items" | Same, **and** `nvidia/nvclip` returned 404 *Not found for account* — no image-embedding entitlement on these keys |
| `tao-mine-nearest-neighbors` | Nearest-neighbour index for visual search | Depends on the two above |
| `rag-blueprint`, `rag-eval`, `rag-perf` | Grounded Q&A over policies and size guides | Docker/Kubernetes plus self-hosted GPU NIMs. Heavy relative to the benefit |
| `data-designer` | Synthetic data for stylist-quality evaluation | Usable, but evaluation sets should be drawn from the real catalogue first |
| `nvidia-skill-finder` | Router over this catalogue | Meta-tool; superseded by this document |

**Note on visual search.** Three of these converge on the same feature, and it is
blocked at the account level, not by effort: no entitled image-embedding model
exists on these keys (`nvclip`, `llama-3.2-nemoretriever-1b-vlm-embed-v1`,
`llama-3.2-nv-embedqa-1b-v1` and `llama-nemotron-embed-vl-1b-v2` were all probed
and all failed). Only `nemotron-3-embed-1b` (text, 2048-dim) works.

---

## 3. Not applicable — 374 skills

Grouped by family, with the reason. These are excluded on domain, not on
difficulty.

| Family | ~Count | Why it does not apply |
|---|---:|---|
| DOCA / BlueField | 60 | SmartNIC and DPU networking |
| TAO training / fine-tuning (beyond the 3 above) | 57 | GPU training infrastructure |
| NeMo (RL, Megatron-bridge, AutoModel, Relay) | 40 | Model training and alignment, not inference consumption |
| Jetson | 35 | Embedded edge devices |
| BioNeMo + medical imaging | 25 | Drug discovery, radiology |
| VSS video analytics | 15 | Multi-camera video pipelines |
| Isaac / i4h robotics | ~30 | Robot control and simulation |
| Holoscan / HoloHub, DeepStream | ~25 | Sensor and streaming pipelines |
| Omniverse, PhysicsNeMo, Warp | ~30 | 3D simulation and physics |
| CUDA / TileGym, cuOpt, cuDF, Dynamo | ~30 | Kernel authoring, OR solvers, GPU dataframes |
| Earth2Studio | ~10 | Weather modelling |
| NVFlare | ~10 | Federated learning across institutions |
| Speech / voice (`nemotron-speech`, `nemotron-voice-agent-builder`) | ~7 | Would fit the voice feature, but `nvidia/nemotron-voicechat` returned **404 not entitled**; voice stays on the browser Web Speech API |

---

## 4. Honest conclusion

The user asked for every skill to be reviewed and the applicable ones used. All
383 were reviewed. **One applied, and it was used end-to-end** — policy, service,
tests, and live calibration that changed the implementation.

Claiming broader adoption would require either inventing use cases or standing
up GPU infrastructure this project does not have and does not need. The eight
conditional entries above are the honest shortlist to revisit if CONFIT ever
adds a GPU tier or gains image-embedding entitlement.
