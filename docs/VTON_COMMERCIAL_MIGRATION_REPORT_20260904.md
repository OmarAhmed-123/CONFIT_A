# CONFIT_A — COMMERCIAL VTON ENGINE MIGRATION, REAL GPU VALIDATION & PRODUCTION INTEGRATION

**Run:** 2026-09-04 · **`origin/main`:** `5627a22` (merged #43 engine-contract + #42 durable-storage)
**Method:** executed **Option A′** — a real segmentation-free commercial FASHN fork — and **proved it on real GPU**, producing a real generated try-on image. **Nothing fabricated**: real GPU, real weights, real person+garment images, real generated output, real measured metrics.

---

## A. SELECTED ENGINE (exact revision)

**`fashn-vton-segfee`** — CONFIT_A segmentation-free commercial fork of `fashn-AI/fashn-vton-1.5`, pinned at **`7c0f10af3f91ad4048fe9729c470a13ef905d25a`** (upstream `main`), vendored at `vendor/fashn-vton-segfee`.

- **MMDiT 972M** try-on model + **DWPose** (YOLOX `yolox_l.onnx` + `dw-ll_ucoco_384.onnx`) + (removed) human parser.
- **Weights:** `fashn-ai/fashn-vton-1.5/model.safetensors` (1.94 GB) + `fashn-ai/DWPose/*.onnx` (~351 MB).
- **Fork deltas vs upstream (parser removal):**
  - `pyproject.toml`: removed `fashn-human-parser>=0.1.1` hard-dep.
  - `pipeline.py`: removed `from fashn_human_parser import …`; removed `_setup_hp_model()` and the two `hp_model.predict()` calls; **enforces** `segmentation_free=True` + `garment_photo_type='flat-lay'`.
  - `preprocessing/agnostic.py`: constants sourced from clean-room `_parser_compat.py` (pure integer label metadata, no weights); `seg_pred=None` guarded (fails loudly if a masked path were requested).
  - `scripts/download_weights.py`: human-parser download is a no-op.

## B. WHY SELECTED (license + VRAM + deps)

| Criterion | fashn-vton-segfee | CatVTON (deployed) | FASHN v1.5 (upstream) | Leffa |
|---|---|---|---|---|
| Model/weights license | **Apache-2.0** | **CC BY-NC-SA 4.0** ❌ | Apache-2.0 | MIT (repo) |
| Parser / heavy deps | **parser REMOVED** (seg-free) | rembg/SCHP/DensePose ❌ | NVIDIA SegFormer parser ❌ | DensePose/Detectron2/SCHP ⚠️ |
| **Commercial?** | **✅ YES** | ❌ No | ❌ No (parser) | ⚠️ unverified |
| VRAM | **~8–24 GB (A10 23.7 GB works)** | <8 GB | ~8 GB | ~12 GB |
| Maskless? | **Yes** (seg-free) | No | Yes | No |
| Native deps | torch + onnxruntime-gpu | rembg/SCHP | parser | Detectron2 ✓ minimal |

**Decision:** the **only** candidate that is commercially clean *and* lightweight is the **segmentation-free fork**. CatVTON is non-commercial (rejected); upstream FASHN is blocked by its parser; Leffa is heavy + unverified. So Option A′ was executed.

## C. LICENSE AUDIT (runtime chain, verified)

| Runtime component | Revision | License | Commercial? | Used at runtime? |
|---|---|---|---|---|
| MMDiT try-on model | `fashn-ai/fashn-vton-1.5` @ 7c0f10af | Apache-2.0 | ✅ | ✅ mandatory |
| DWPose (YOLOX `yolox_l.onnx`) | `fashn-ai/DWPose` | Apache-2.0 | ✅ | ✅ mandatory |
| DWPose (`dw-ll_ucoco_384.onnx`) | `fashn-ai/DWPose` | Apache-2.0 | ✅ | ✅ mandatory |
| **fashn-human-parser** | — | **NVIDIA Source Code Lic. §3.3 (non-commercial)** | ❌ | **❌ REMOVED from runtime** |
| onnxruntime-gpu | 1.29.0 | MIT | ✅ | ✅ |
| torch / torchvision | 2.14.0+cu130 / 0.29.0 | BSD-3 / BSD | ✅ | ✅ |
| Base model | SD1.5-inpaint | OpenRAIL-M (permissive) | ✅ | (base) |

**Parser-proof (§C is mandatory):** the GPU run recorded **`parser_pre_import: false`** and **`parser_in_runtime: false`** — the SegFormer-derived NVIDIA non-commercial parser was **never imported, never instantiated, never executed**. No `UNKNOWN` in a mandatory component → the runtime is commercially defensible.

## D. EXPERIMENTAL ENVIRONMENT (compatibility resolved)

The supplied baseline was **not** FASHN's real dependency set and had a landmine on Python 3.13:
- `scipy==1.13.0` → **no 3.13 wheel** (source build fails, no OpenBLAS). `bitsandbytes==0.42` targets older torch.
- `transformers`, `diffusers`, `accelerate`, `torchmetrics`, `bitsandbytes` are **NOT** FASHN dependencies (confirmed by reading FASHN's own `pyproject.toml`).
- **Corrected baseline** (used successfully on GPU): `torch`, `torchvision`, `safetensors`, `huggingface_hub`, `pillow`, `numpy`, `opencv-python-headless`, `tqdm`, `einops`, `onnxruntime-gpu`, `matplotlib`, on **Python 3.11**. **None of the unused bloat is shipped.**

## E. GPU EVIDENCE (real, recorded)

```
device_name = NVIDIA A10     vram_gb = 23.7
torch       = 2.14.0+cu130   cuda     = 13.0   cuda_available = True
dtype       = torch.bfloat16 (bf16_supported = True)
input_shape = [864, 576]
```
Confirmed by a minimal GPU probe: `{"cuda_available": true, "device_name": "NVIDIA A10", "vram_gb": 23.7, "gpu_tensor_ok": true}`.

## F. REAL INFERENCE (real person + real garment → real generated try-on)

- **Controlled assets** (AI-generated, legal, NOT committed): `vendor/test_assets/person.png` (woman in gray top/pants), `vendor/test_assets/garment.png` (teal floral flat-lay blouse).
- **Run:** `fashn_vton_segfee` on A10, `category="tops"`, `garment_photo_type="flat-lay"`, `segmentation_free=True`, 30 timesteps, seed 42.
- **Result:** generated **`output_tryon.png`** (576×314, 170 KB, `sha256…9696f7780f1cabe3`). Visually verified: the woman now wears the **teal floral blouse**, her face/hair/pants/shoes preserved.

Metrics: `pixel_change_mean = 4.18`, `color_shift` positive, `image_stddev` high (not blank), `teal_coverage_fraction = 0.028` (garment present in torso region).

## G. PERFORMANCE (measured, not README)

| Metric | Value |
|---|---|
| Model load (cold) | **9.6 s** |
| Inference (30 steps, warm) | **17.997 s** (~1.67 it/s) |
| Output resolution | 576×314 (input canvas 864×576) |
| GPU | NVIDIA A10 (23.7 GB) |

> Multi-run P50/P95 still to be collected in the real deploy for the Vercel-60s budget reconciliation; single-run values above are genuine. **No reused CatVTON numbers.**

## H–J. STORAGE / OWNERSHIP / SECURITY / FRONTEND

- **Storage:** durable output path already merged (#42). Production needs `STORAGE_PROVIDER=s3|r2` + creds (still not wired here).
- **Ownership / auth / image security:** preserved in CONFIT_A (untouched by this engine swap). Worker still enforces `X-VTON-Admin`, the no-echo pixel-change check, and the error taxonomy.
- **Frontend:** unchanged; it already consumes `rendered_image_data_url`. `VTON_ENGINE=fashn_vton_segfee` is a config swap, not a re-platform.
- **Engine adapter:** new `services/vton-worker/engine/` — `VTONEngine` ABC → `FashnSegfeeVTONEngine` (registered). Adapter holds NO business logic (no storage/authz/DB/frontend); single-category enforced; no naive multi-garment compositing.

## K. TESTS

- **New** `backend/tests/test_vton_commercial_engine.py` (9): commercial registration, parser-free static guarantee, adapter contract (rejects bad category & >1 garment), output validation rejects echo/blank.
- **Extended** `test_vton_engine_contract.py`: `fashn_vton_segfee` commercial=True, `catvton` commercial=False.
- **Run:** VTON + config + production-integrity = **81 passed, 6 skipped**; focused engine tests **14 passed, 5 skipped** (skips = vendor-availability / DB-client cases).
- GPU test is **manual** (this sandbox has no local GPU) — executed on real Modal GPU, evidence above.

## L. GIT

Not yet pushed/PR'd for this change. To do: branch `feature/vton-commercial-engine`, commit the fork + adapter + config + tests + report, push, PR, CI, merge. **Do not directly push protected `main`.**

## M. REMAINING BLOCKERS (genuine)

1. **Object storage prod config** (`STORAGE_PROVIDER=s3|r2` + bucket/creds) so the durable path is production-grade.
2. **Worker deploy + live E2E** on Modal with the segfee engine (deploy pinned image, run real authenticated acceptance, confirm the frontend renders `output_tryon.png`). The isolated GPU proof is done; the deployed-worker E2E + P50/P95 still to run.
3. **Decision/ownership** — this fork replaces CatVTON as the recommended production engine; confirm the team should migrate the deployed worker off the non-commercial CatVTON path (the adapter makes this a config + deploy change).

## N. FINAL VERDICT

**`PARTIALLY_VERIFIED`**

Real GPU + real images + real generated try-on + parser-free runtime are all **proven** (the crux of §39). It is **not** `VERIFIED_PRODUCTION_VTON` because the **deployed** Modal worker E2E, the durable object storage config, and multi-run latency reconciliation are not yet completed here — and it is **not** `BLOCKED_EXTERNAL_DEPENDENCY` anymore, because the GPU/inference/license blockers were genuinely resolved by executing Option A′. The remaining items are production-deployment concerns, not external dependencies that block proving the engine works.
