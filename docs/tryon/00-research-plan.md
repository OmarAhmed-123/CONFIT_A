# Virtual Try-On — Research & Benchmark Plan + Acceptance Rubric

- **Date:** 2026-10-22
- **Owner:** principal engineer (onboarding)
- **Status:** plan + rubric for sign-off. No model shipped, no benchmark run yet.
- **Builds on existing repo work** (reviewed, not restarted): `MODEL_REGISTRY.json`,
  `docs/vton-model-decision.md`, `docs/VTON_PROVIDER_EVALUATION_20260927.md`,
  `backend/app/core/config.py::VTON_ENGINE_LICENSES`, `services/vton-worker/`,
  `vendor/fashn-vton-segfee/`.

> Evidence rule: current model versions, licenses and vendor pricing change fast and
> are **to be re-verified from primary sources at execution time** (§2.2). Everything
> below marked MEASURED comes from a run recorded in the repo; everything else is a
> plan or a documented (not independently reproduced) figure.

---

## 1. Current verified state (so we extend, not restart)

- **Selected production engine: `fashn_vton_segfee`** — CONFIT's segmentation-free fork
  of `fashn-AI/fashn-vton-1.5` @ `7c0f10af`, vendored at `vendor/fashn-vton-segfee`.
  Runtime chain Apache-2.0 (MMDiT 972M + DWPose + YOLOX); the non-commercial
  SegFormer human-parser is removed from the runtime (`parser_in_runtime=False`,
  MEASURED on a real A10). Commercially clean per repo documentation.
- **MEASURED (A10, 2026-09-06):** real generated try-on, load ~9.6 s, inference ~18 s
  (30 steps), ~3.8 GB VRAM class; `pixel_change_mean=4.18` (real transfer, not echo).
- **The blocker is deployment, not the model:** `VTON_WORKER_URL` is unset in
  production, so `tryon_service.py` raises `VTON_ENGINE_UNAVAILABLE` and `/health`
  reports `ready:false, blocking:["virtual_try_on"]`. Honest-failure behaviour is
  correct; the feature is simply not live. (Tracked as finding F-009.)
- **Also measured (2026-09-27):** IDM-VTON renders on its HF Space in ~24 s but is
  **CC BY-NC-SA 4.0 (non-commercial)**; Gemini image models are available but the
  project key is daily-quota-exhausted; Fitroom is egress-IP-blocked from here;
  fal.ai/Replicate are uncredentialled.
- **Gap:** there is **no in-repo, reproducible benchmark harness** and no scored run
  against measurable acceptance thresholds on a diverse, consented, modest-wear-inclusive
  test set. That is the core of Phase 2 work below.

## 2. Try-on assets inventory (from code)

| Asset | What it is |
|---|---|
| `services/vton-worker/modal_app_segfee.py` | Modal GPU worker for the segmentation-free engine (production path) |
| `services/vton-worker/modal_app_v15.py` | Modal worker for the full v1.5 (multigarment) engine |
| `services/vton-worker/engine/` | `VTONEngine` ABC + `FashnSegfeeVTONEngine` (swap seam) |
| `services/vton-worker/pipeline/` | segmentation/pose/mask stages |
| `services/vton-worker/baseten/`, `cerebrium/` | alternate hosting shells |
| `services/vton-worker/_bundled_catvton/` | legacy CatVTON bundle (non-commercial) |
| `backend/app/providers/vton/registry.py` | `resolve_chain` + license-tier filtering (`pilot`/`commercial`) |
| `backend/app/services/tryon_service.py` | job orchestration, worker URL derivation, honest 503 |
| `vendor/fashn-vton-segfee/`, `vendor/fashn-vton-1.5/` | vendored forks |
| `MODEL_REGISTRY.json` | one-model-per-branch registry (VTON + Qwen VL) |
| `services/vton-worker/benchmarks/` | **does not exist — to be created (§2.3)** |

## 3. Phase 2.1 — Acceptance rubric (write thresholds before testing)

A candidate passes only if it meets **all** gates on the benchmark set (§2.3). Scores
are the mean over the set unless noted; variance is reported, never hidden.

### 3.1 Quality gates (functionality-first)
| Dimension | Metric | Threshold |
|---|---|---|
| Garment fidelity | human rubric 1–5 on pattern/logo/texture/drape; SSIM↑, LPIPS↓ as supporting | mean ≥ 4.0/5; no category mean < 3.5 |
| Identity preservation | face/skin-tone unchanged (human rubric + face-landmark drift) | mean ≥ 4.0/5; hard-fail any identity swap |
| Body & background preservation | pose/body/background intact | mean ≥ 4.0/5 |
| Modest-wear & cultural fit | long sleeves, abaya, hijab-compatible (head covering **not** distorted or removed) | mean ≥ 4.0/5; hard-fail any hijab/head-covering distortion |
| Multi-garment / layering | top+bottom, dress, outerwear composed correctly | mean ≥ 3.5/5; artefact growth per layer bounded |
| Robustness | real user photos: varied lighting, pose, EXIF orientation, body types | failure rate ≤ 10% on the standard set |

### 3.2 Non-functional gates (the other SPECS dimensions)
| Dimension | Metric | Threshold |
|---|---|---|
| Performance | warm latency per render (stated GPU) | ≤ 20 s warm (target), cold-start recorded |
| Performance | cost per render | recorded; within the build-vs-buy budget (§2.5) |
| Security/Privacy | user photo: encrypted at rest, scoped access, retention limit, deletion on request, no photo in logs | all verified (abuse-case test) |
| Integrity | honest failure preserved (503, never a substitute image); idempotent jobs | verified |
| Scalability | concurrency cap, queue depth, cost ceiling, graceful degradation | defined + load-tested |
| Compatibility | EN/AR + RTL + a11y on the full upload→preview journey | verified on real devices |

**Thresholds are fixed before testing and are not lowered to pass** (brief §2.6.1).
A published benchmark asserts no VTON model guarantees zero identity drift or covers
accessories; the rubric reflects that reality (hard-fails are the floor, not perfection).

## 4. Phase 2.2 — Landscape research scope (run live, primary sources)

Re-verify version/license/pricing from primary sources at execution (papers, official
repos, model cards, vendor docs, independent benchmarks) — not from memory. Candidates:

- **Self-hosted open-weight:** `fashn_vton_segfee` (incumbent), FASHN v1.5/v1.6, Leffa,
  CatVTON (+ newer variants), IDM-VTON, OOTDiffusion, FitDiT, and any 2026 entrants.
- **Hosted APIs (commercial terms):** FASHN API, Kling Kolors VTON, fal.ai, Replicate,
  Google Gemini image models; cloud-provider offerings.
- **General image-editing foundation models** usable for try-on (e.g. Gemini image).
- **Supporting components:** human parsing/segmentation, pose (DWPose), garment masking,
  background handling, upscaling / face restoration.
- **Repo-specific:** confirm exactly what `vendor/fashn-vton-segfee` and
  `MODEL_REGISTRY.json` are and how they are wired (done — see §1–2) and keep current.

## 5. Phase 2.3 — Benchmark harness (to build)

- **Location:** `services/vton-worker/benchmarks/` (NOT in the production path).
- **Test set:** fixed, diverse, documented **source and consent status** — varied body
  types, skin tones, poses, lighting, garment categories **including modest wear**, plus
  hard cases (busy patterns, logos, sheer fabric, layering). No invented ground truth.
- **Protocol:** identical inputs across candidates; **pinned versions + seeds**; record
  raw outputs, cold/warm latency, VRAM, cost/render, failure rate, and the §3 rubric
  (blind/second-reviewer scoring where practical). Report variance. State the exact GPU.
- **Reproducibility:** a single command re-runs a candidate; outputs and scores are
  committed as artefacts (no cherry-picking).
- **Resource gate:** requires real GPU time and, for hosted APIs, **paid credentials** —
  both are approval/cost items (see §8). Not runnable in this environment.

## 6. Phase 2.4 — Licensing protocol

Rank on functionality first; record license for **every** candidate. Comparison columns:
license name, link, exact commercial-use position, share-alike/attribution duties, and
the licenses of training data and bundled dependencies (try-on weights often inherit
non-commercial dataset terms). Reuse the repo's `VTON_ENGINE_LICENSES` (already more
rigorous than most public write-ups). Benchmarking any model is fine; **shipping a
commercially-restricted model to production requires your recorded decision** (options:
commercial license / hosted service / best clean alternative with the quality gap
quantified / written risk acceptance). License notes are "from public documentation, not
legal advice; recommend legal review for the final choice."

## 7. Phase 2.5 — Decision (ADR) + build-vs-buy

Deliver `docs/tryon/ADR-model-selection.md`: scored comparison, recommendation, rejected
options with reasons, risks, fallback plan, and a **build-vs-buy** model — self-hosted
GPU cost at expected render volume vs per-call API pricing, with the break-even point.
Current incumbent (`fashn_vton_segfee`) is the default unless a candidate beats it on §3
with acceptable license/cost.

## 8. Phase 2.6 — Integration (largely built; verify + close gaps)

Already present: `VTONEngine` ABC + swap seam, async job model, honest 503, license-tier
registry, worker URL derivation. **To verify/complete against the rubric:** input
validation (type/size/dimensions/EXIF/decompression-bomb), user-photo encryption +
retention + deletion + no-logging, per-user/global rate limits + cost ceiling +
concurrency cap, observability (latency/failure/queue/GPU-cost/provider-error + alerts),
the full EN/AR + a11y upload→progress→before/after→"visual preview" UI, and
multi-garment composition end to end.

## 9. Resources / approvals needed to execute (gates)

1. **GPU access** for the benchmark (and to deploy the worker): a real GPU (state the
   type) — Modal/RunPod/cloud. Spending money → your approval.
2. **Paid API credentials** to benchmark hosted options (FASHN API, Kling, fal.ai,
   Gemini paid tier). Adopting a paid service → your approval.
3. **A consented, diverse test set** (incl. modest wear) with documented provenance.
4. **Production deploy** of the worker + setting `VTON_WORKER_URL` → your approval
   (and blocked until F-001, the DB outage, is resolved).

## 10. Immediate recommendation

The fastest route to live, commercially-clean try-on is **not** more model research — it
is **deploying the existing `fashn_vton_segfee` worker and setting `VTON_WORKER_URL`**
(the code exists and is GPU-proven). Run the §2.3 benchmark in parallel to (a)
independently validate the incumbent against the §3 thresholds, especially modest-wear
and multi-garment, and (b) decide on a paid hosted fallback for cold-start/outage. Both
need GPU/credentials/approval per §9, and both sit behind F-001 for anything touching
production.
