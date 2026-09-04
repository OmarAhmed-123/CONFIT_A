# VTON ENGINE — FASHN SOURCE AUDIT & ENVIRONMENT COMPATIBILITY (2026-09-04)

**Repo:** `origin/main @ 5627a22` (VTON engine-contract #43 + durable-storage #42 merged; no open PRs)
**Audit method:** read the **actual source** of `fashn-AI/fashn-vton-1.5` (commit `main`, `7c0f10a`), not the README. Environment compatibility probed with pip wheel-resolution on the sandbox (Python 3.13.14, no GPU).
**Nothing here is inferred; every claim is cited to a file/line of the real source.** No fabricated inference, no invented licenses, no fake GPU.

---

## 1. THE SINGLE MOST IMPORTANT FINDING (§7 / §8) — ANSWERED FROM SOURCE

> **The FASHN human parser is a MANDATORY runtime component and CANNOT be bypassed by supplying `category`.**

Previously (in the v1 report) I listed "supply `category` from the catalog" as a viable remediation for FASHN's non-commercial parser. **That hypothesis is now disproven by reading the code.**

### Evidence
`src/fashn_vton/pipeline.py`:
- **Module-level import (line 7):** `from fashn_human_parser import CATEGORY_TO_BODY_COVERAGE, FashnHumanParser` — importing `fashn_vton.pipeline` imports the restricted package.
- **`_setup_hp_model()` (lines 136–143):** called unconditionally from `__init__` → `self.hp_model = FashnHumanParser(device=hp_device)`. The parser model is **always instantiated**, independent of any flag.
- **`__call__()` (lines 261–262):**
  ```python
  person_seg_pred  = self.hp_model.predict(person_image_np)
  garment_seg_pred = self.hp_model.predict(garment_image_np)
  ```
  These two `.predict()` calls are **unconditional** — they run **on every single inference**, regardless of `segmentation_free`.
- **`segmentation_free=True` only sets `disable_masking=True`**, which changes behavior in `create_clothing_agnostic_image()`/`create_garment_image()`:
  - `src/fashn_vton/preprocessing/agnostic.py` `create_clothing_agnostic_image` begins `if disable_masking: return img_np` → returns the image **unchanged**.
  - So `segmentation_free` merely discards *masking*, it does **not** skip the parser's `predict()`.

### Conclusion
The non-commercial parser is invoked at **install-time** (`pip` hard-dep), **import-time** (module-level `from fashn_human_parser import …`), **init-time** (`FashnHumanParser(device=…)`), and **every-inference-time** (`hp_model.predict(...)` ×2). Supplying `category` (which FASHN does NOT use to infer — `category` is a required caller arg) does **not** avoid the parser. **FASHN VTON v1.5 is NOT commercially clean as-is.**

---

## 2. FASHN EXECUTION GRAPH / DEPENDENCY TREE (traced)

```
fashn-vton (TryOnPipeline, Apache-2.0 repo)
 ├── TryOnModel  (MMDiT 972M)  ← fashn-ai/fashn-vton-1.5/model.safetensors   [Apache-2.0]  MANDATORY
 ├── DWposeDetector             ← YOLOX `yolox_l.onnx` + DWPose `dw-ll_ucoco_384.onnx`
 │                                 (fashn-ai/DWPose)                          [Apache-2.0]  MANDATORY
 │                               (onnxruntime-gpu at runtime)
 ├── FashnHumanParser           ← fashn-human-parser (SegFormer-Derivative)   [NVIDIA Source
 │   .predict() ×2 every call     auto-cached weights                          Code License
 │                                                                             §3.3 NON-COMMERCIAL]
 │                                                                             MANDATORY, BYPASS-IMPOSSIBLE-AS-IS
 ├── preprocessing (agnostic / masks / transforms)   imports fashn_human_parser constants
 └── postprocessing (unpad, tensor→PIL)
```

- **Mandatory, commercially-compatible:** MMDiT model, DWPose (YOLOX + ONNX pose).
- **Mandatory, NON-COMMERCIAL:** `fashn-human-parser` (SegFormer under NVIDIA Source Code License §3.3).
- **Optional/unused:** none of `bitsandbytes`, `transformers`, `diffusers`, `accelerate`, `torchmetrics`, `scipy` **appear in FASHN's own `pyproject.toml`** (see §4).

---

## 3. CORRECTED REMEDIATION (what it actually takes)

Since bypassing the parser by supplying `category` is objectively impossible, the only paths to a commercially-defensible FASHN are:

- **Option A — Replace the parser (API-compatible drop-in).** Provide a commercially-licensed network that satisfies the exact import contract: `FashnHumanParser(device=...).predict(img)->seg`, plus constants `CATEGORY_TO_BODY_COVERAGE`, `BODY_COVERAGE_TO_LABELS`, `LABELS_TO_IDS`, `IDENTITY_LABELS`, and the FASHN `LABELS_TO_IDS`/`BODY_COVERAGE_TO_FASHN_LABELS` re-exports. **High effort, but keeps FASHN stock.**
- **Option A′ — Vendor-fork FASHN to run segmentation-free.** Patch `pipeline.py`/`agnostic.py` to drop the module-level parser imports, skip `hp_model.predict()` and pass a dummy `seg_pred`, and run `segmentation_free=True` + `garment_photo_type="flat-lay"` so the (unused) seg maps are never consumed (the `if disable_masking: return img_np` early-returns make `seg_pred=None` safe). Must still be **validated on GPU** and maintained as a fork. **Moderate effort; changes the model's data path to segmentation-free only.**
- **Option C — switch engine** (verify Leffa's full chain; or another model).

> Either A/A′ yields a build whose runtime is commercially clean **only if validated and version-pinned**. This is exactly the "must be proven on a real GPU" gate.

---

## 4. ENVIRONMENT COMPATIBILITY PROBE (§5/§16/§17) — REAL RESULTS

Sandbox = **Python 3.13.14**, no GPU (`nvidia-smi` absent, `torch` absent), no local `python3.11`/`python3.12`. Probe used pip binary-wheel resolution in an isolated venv.

| Supplied baseline dep | Pinned | Result on Python 3.13 | Verdict |
|---|---|---|---|
| `torch` | (unpinned) | resolves → **2.14.0** (cp313 wheel) | OK, but **no wheel pins torch 2.x**; old pins assume ≤ torch 2.3 |
| `torchvision` | (unpinned) | → 0.29.0 (cp313) | OK |
| `scipy` | `==1.13.0` | **NO 3.13 wheel** → source build fails (OpenBLAS missing) | ✗ **not installable on py3.13** |
| `bitsandbytes` | `==0.42` | wheel `py3-none-any` exists, but targets torch ≤2.3-era CUDA; **no GPU**; not a FASHN dep | **add only if proven; below it is NOT needed** |
| `transformers` | `==4.40.2` | py3-none-any | installable, but **not a FASHN dep** |
| `diffusers` | `==0.27.2` | py3-none-any | installable, but **not a FASHN dep** |
| `accelerate` | `==0.30.0` | py3-none-any | installable, but **not a FASHN dep** |
| `torchmetrics` | `==1.4.0` | installable | **not a FASHN dep** |
| `tqdm`, `opencv-python` | — | installable | (tqdm IS a FASHN dep) |

### §16/§17/§18 verdict — do NOT copy the supplied dset into the worker
The supplied baseline is **not** FASHN's requirement list. FASHN's **own** `pyproject.toml` deps are:
`torch>=2.0.0`, `torchvision>=0.15.0`, `safetensors>=0.3.0`, `huggingface_hub>=0.20.0`, `pillow>=9.0.0`, `numpy>=1.21.0`, `opencv-python>=4.5.0`, `tqdm>=4.65.0`, `einops>=0.6.0`, `onnxruntime-gpu>=1.14.0`, `matplotlib>=3.5.0`, `fashn-human-parser>=0.1.1`.
- The supplied baseline adds **`bitsandbytes`, `torchmetrics`, `scipy`, `transformers`, `diffusers`, `accelerate`** — none of which FASHN uses. **Do not ship them.**
- A production image should use **Python 3.11/3.12** (FASHN classifiers list 3.10–3.12; 3.13 breaks `scipy==1.13.0` which isn't needed anyway), a GPU `torch` build, `onnxruntime-gpu`, FASHN's real dep set, and the **replacement for `fashn-human-parser`**.
- Pin exact revisions at the commit SHA for the worker image (determinism; no `latest`).

---

## 5. REAL-GPU OPTION (honest)

- `modal` CLI present (v1.5.5), authenticated as workspace **`omarsafealden`**; PyPI/HF/Modal APIs reachable. So a Modal GPU run is **technically reachable** in principle.
- **BUT** the engine to run is **not yet commercially selected** (FASHN needs a parser replacement/fork first). Running a real GPU E2E now would (a) burn the account's GPU time/credits, and (b) validate a **vendor fork** whose license-cleanliness depends on the remediation route the owner still has to choose. Per §11/§34 I will not start a cost-incurring GPU run or claim inference until the route is decided.
- **`BLOCKED_EXTERNAL_DEPENDENCY`** remains the honest verdict for real (generated-image) inference in this sandbox: no GPU locally; and the commercial engine itself is unresolved.

---

## 6. NEXT DECISION REQUIRED

Pick the route, then I can execute it (and, if you want, run it for real on Modal GPU):

1. **Option A** — build a commercial drop-in parser + keep FASHN stock. (most work, cleanest licensing)
2. **Option A′** — vendor-fork FASHN to drop the parser (segmentation-free). (less work, fork to maintain)
3. **Option C** — audit + validate **Leffa** (MIT repo) full chain; if its Detectron2/DensePose/SCHP/weights are commercial, use it.
4. **Hold** — complete remaining GPU-independent Scenario-B work (engine adapter, `verify_vton_production.py`, tests, honest metadata) and leave real inference as an external blocker for you to run.
