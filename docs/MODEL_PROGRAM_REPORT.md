# CONFIT_A — Self-Hosted AI Model Program Report

**Date:** 2026-09-07 · **Repo:** `github.com/OmarAhmed-123/CONFIT_A`
**Mode:** read‑only discovery + license gates + one model module built (code/spec/tests/docs) **with real GPU execution + a live deployed web worker (verified working)**. See §7, §9, §13.

**Governing principle applied:** ONE FEATURE NEED → ONE APPROPRIATE MODEL → ONE MODEL BRANCH → ALL WORK ON THAT BRANCH → REAL GPU VALIDATION → ONE PR → MERGE. Where a step cannot be physically performed here, it is marked **BLOCKED** (never faked).

**Bottom line:** After full spec + code discovery, the *justified new local model* is **exactly one** — **Qwen2.5‑VL‑7B** (local fallback for the two Gemini‑dependent vision features). The production **VTON is already self‑hosted** (no new model). Every other candidate is **NOT REQUIRED** (no approved feature), **redundant**, or **license‑BLOCKED** (Qwen 3B). I deliberately did **not** build fashionCLIP/SAM2/OCR/etc. — the specs show no approved feature that requires them (building them would violate "do not build merely because popular" / "do not integrate unused models").

---

## 1. COMPLETE AI FEATURE → MODEL MAP

| Feature | Spec / code location | User behavior | AI capability | Existing impl | Existing model/provider | Local model needed? | Priority |
|---|---|---|---|---|---|---|---|
| **Visual Search** | G2_G3 §4.3; `visual_search_service.py` | upload/URL → ranked catalog matches | VLM attribute extraction → attribute ranking | Gemini vision → attributes → keyword/facet scoring | **Gemini Flash** (single, no fallback) | **Yes — Qwen2.5‑VL‑7B** | **P1** |
| **Wardrobe Auto‑Tagging** | G4 §2.2; `wardrobe_service._run_ai_analysis` | upload garment → structured tags | VLM structured attribute extraction | Gemini vision → `wardrobe_taxonomy` | **Gemini Flash** (single, no fallback) | **Yes — Qwen2.5‑VL‑7B** | **P1** |
| **Virtual Try‑On** | G2_G3 §4.1; `tryon_service.py`, `vton-worker/` | photo + garments → try‑on image | diffusion VTON (single + multi) | self‑hosted, Modal | **fashn_vton_segfee** (Apache‑2.0, segmentation‑free) | **No — already self‑hosted** | **P0 (done)** |
| **AI Virtual Stylist** | G2_G3 §2.2; `orchestrator.py`, `stylist_service.py` | chat/voice → outfit advice | text LLM (grounded) | multi‑provider LLM + deterministic `StylingEngine` | NVIDIA/Groq/Gemini/OpenAI(+OpenRouter) | No (deterministic fallback exists) | P0 (no local model req.) |
| **Outfit/Styling/Recommendation** | G2_G3 §2.3; `styling_engine.py`, `styling/` | outfit compatibility, "complete the look" | **none** (rules) | deterministic color‑harmony/slot/occasion rules | none | **No** (rule‑based) | P0 (no model) |
| **No‑Photo Fit** | G2_G3 §4.2; `no_photo_fit_service.py` | anthropometrics → size + zone breakdown | **none** (rules) | BMI/proportion rules; static avatars | none | **No** (rule‑based) | P0 (no model) |
| **Text Search** | `search_service.py` | keyword/autocomplete | **none** | DB `ilike`/facets | none | **No** | P0 (no model) |
| **Measurement / "camera scan"** | G1; `measurement_service.py`, `CameraScanModal` | enter body measurements | **none** (user‑input, Fernet‑encrypted) | user‑submitted anthropometrics | none | **No** | P0 (no model) |
| **Stylist voice (STT)** | G2_G3 §2.2; `useStylistViewModel` | speech → text | speech‑to‑text | browser "simulation" | browser‑native (Web Speech API) | **No server model** (browser‑native) | noted (not a local‑model item) |
| **Weather** | `weather_service.py` | dashboard weather | **none** (external API) | OpenWeather | none | **No** (non‑AI) | P0 (non‑AI) |
| **VTON artifact QA** | `tests/vton_artifact_check.py`, `cv_models/` | (CI) hand/pose QA | pose/hand landmarks | MediaPipe (Apache‑2.0) | **MediaPipe** | **No** (test‑only, present) | P1 (test) |

**Absent (determined by code + spec):** vector DB / embeddings / CLIP / reranker; OCR; face‑embed/identity‑verification; standalone object detection; standalone pose product feature; depth; image moderation; working image‑to‑video.

## 2. COMPLETE MODEL REGISTRY
See **`MODEL_REGISTRY.json`** (canonical, 15‑field per model). Summary: 2 selected (Qwen2.5‑VL‑7B, fashn‑vton‑segfee) + 12 rejected/not‑implemented with evidence‑based reasons.

## 3. HUGGING FACE URL FOR EVERY MODEL
| Model | HF URL |
|---|---|
| Qwen2.5‑VL‑7B‑Instruct (**selected**) | https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct |
| fashn‑vton‑1.5 / segfee fork (**production**) | https://huggingface.co/fashn-ai/fashn-vton-1.5 |
| Qwen2.5‑VL‑3B‑Instruct (**BLOCKED**) | https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct |
| Marqo/marqo‑fashionCLIP (not required) | https://huggingface.co/Marqo/marqo-fashionCLIP |
| valentinafevu/yolos‑fashionpedia (not required) | https://huggingface.co/valentinafevu/yolos-fashionpedia |
| usyd‑community/vitpose‑plus‑small (not required) | https://huggingface.co/usyd-community/vitpose-plus-small |
| facebook/sam2‑hiera‑large (not required) | https://huggingface.co/facebook/sam2-hiera-large |

## 4. EXACT REVISION FOR EVERY MODEL
| Model | Revision |
|---|---|
| Qwen2.5‑VL‑7B | `cc594898137f460bfe9f0759e9844b3ce807cfb5` (pinned in `services/vlm-worker/model_spec.py`) |
| fashn‑vton‑segfee | `7c0f10af3f91ad4048fe9729c470a13ef905d25a` (vendored `vendor/fashn-vton-segfee`) |
| Qwen2.5‑VL‑3B | `66285546d2b821cf421d4f5eb2576359d3770cd3` |

## 5. LICENSE STATUS FOR EVERY MODEL
| Model | License | Commercial | Status |
|---|---|---|---|
| Qwen2.5‑VL‑7B | **Apache‑2.0** | ✅ | **VERIFIED** (HF API `license` + model `LICENSE`) |
| fashn‑vton‑segfee | Apache‑2.0 (model/DWPose/YOLOX); human‑parser removed | ✅ | **VERIFIED** (repo docs + real‑GPU E2E proof) |
| Qwen2.5‑VL‑3B | **Qwen RESEARCH (non‑commercial only)** | ❌ | **BLOCKED** (verified from its `LICENSE`) |
| fashionCLIP / yolos / vitpose / sam2 / ocr / depth / moderation / identity / fashn‑full | — | — | **NOT VERIFIED** (not selected; no approved feature) |

## 6. CURRENT VS FUTURE MODEL STATUS
- **CURRENT + already self‑hosted:** VTON (`fashn_vton_segfee`, Modal, production).
- **CURRENT gap → local fallback (the one justified new model):** Qwen2.5‑VL‑7B for Visual Search + Wardrobe Auto‑Tagging (both Gemini‑only, no failover).
- **FUTURE / approved scope:** none identified that requires a *new* model. (Perceptual retrieval, segmentation, OCR, moderation, identity‑verification, video, standalone pose/detection are **not** in the approved specs.) STT is spec‑approved but **browser‑native** (no server model).
- **Optional P2 (not built):** local LLM for stylist resilience (deterministic fallback already exists).

## 7. MODAL GPU DEPLOYMENT MAP
| Service | GPU | Weights volume | Status |
|---|---|---|---|
| `confit‑vton‑worker` (existing) | A10 (3.83 GB reserved, measured) | `confit‑vton‑fashn‑weights` | **PRODUCTION** |
| `confit‑vlm‑worker` (new, Qwen) | A10G 24 GB (default; `VLM_GPU` override) | `confit‑qwen25vl‑weights` | **DEPLOYED + web endpoint VERIFIED working** (`/health` 200; `/analyze` cold 26.0 s / warm 5.1 s on A10) |
Isolation: the two large models run in **separate** Modal services (no shared process/VRAM). The Vercel function stays lightweight (no torch).

## 8. PROVIDER → LOCAL FALLBACK MAP
| Capability | Primary (provider) | Local fallback | Both unavailable |
|---|---|---|---|
| Visual Search | Gemini Flash | **Qwen2.5‑VL‑7B** (when `QWEN_VL_WORKER_URL` set) | `analysis_available=False` (honest) |
| Wardrobe Auto‑Tagging | Gemini Flash | **Qwen2.5‑VL‑7B** | item marked failed/retryable (honest) |
| Stylist | NVIDIA/Groq/Gemini/OpenAI | deterministic `StylingEngine` (already present) | deterministic grounded output |
| VTON | self‑hosted segfee (local) | — (no external VTON in prod) | `VTON_WORKER_UNAVAILABLE` (fail‑closed) |

## 9. REAL SMOKE-TEST RESULTS (MEASURED on a real A10/A10G — 2026-09-07/08)
**Qwen2.5-VL-7B (MEASURED, not estimated):** GPU NVIDIA A10G 22.1 GiB · model
load ~7–8 s (BF16, 16.59 GB weights from Modal Volume) · peak VRAM **15.45 GiB** ·
inference **3.2–4.9 s/image** (`max_new_tokens≤300`, no sampling). This is a **small real
SMOKE set**, NOT the diverse catalog benchmark (which is **PENDING/BLOCKED**, §13).
Real feature: on‑model blazer photo → **all attributes correct** (Outerwear/Blue/Checkered/Formal
+ full outfit); non‑garment color block → honest `null` (vision). The wardrobe non‑garment
false‑positive is **FIXED + GPU‑verified** (restructured `WARDROBE_TAG_PROMPT`; solid navy swatch
now → `{category: null, confidence: 0.0}`, was `Tops/Sweater` @0.95; blazer unchanged).
(VTON: existing real‑GPU proof `docs/VTON_PRODUCTION_E2E_PROOF_20260906.md`.)

## 10. REMAINING BLOCKERS
| Blocker | What's needed |
|---|---|
| Warm-container *sustainability* | The web endpoint is **VERIFIED working** (root cause of the earlier crash‑loop was a missing `inference` module, now baked into the image — PR §8). A warm container (`min_containers=1`) is not sustained on this free/limited account, so idle→active is a ~15–26 s cold start; set `VLM_MIN_CONTAINERS=1` on a tier that sustains it. A robust `.remote()` transport is also implemented + tested. |
| Full diverse catalog benchmark | a real product catalog (skin tone/body type/pose/flat‑lay/occlusion) for a top‑k relevance gate (only a small real smoke set was run) |
| PR → merge | the ONE PR is **opened** from `feature/model-qwen25-vl` (pushed/durable); web serving verified; merge after review + the catalog benchmark |

## 11. MERGED PRs
**Not yet merged.** The Qwen branch is on GitHub: `feature/model-qwen25-vl` (PR #102), with
`PR_MODEL_QWEN25_VL.md`. **Close-out completed this cycle (2026-09-08):** non‑garment wardrobe
false‑positive **FIXED + GPU‑verified** (restructured prompt) + 2 CPU regression tests; local
backend suite **1083/0** (4 pre‑existing Qwen‑branch manifest/parity failures fixed); **GPU capacity
audit** (1 A10G Qwen worker, concurrency 1, `min_containers=0`, VTON isolated); **security scan**
(no credential values; fail‑closed admin auth; SSRF; no image‑byte persistence); **transport
decision** (WEB primary, REMOTE documented alternative); **fallback‑chain proof** (both features).
**Closed after credential re‑provision (2026-09-08):** live `modal app list` re‑run → **all 3 apps
at 0 tasks (0 GPUs held)**, single Qwen worker + 2 distinct VTON workers, all scale to 0
(LIVE‑VERIFIED); the close‑out commits are **pushed** (PR #102 body re‑synced to the updated doc).
**CI (honest):** all in‑repo checks green/running (backend, postgres, production parity, frontend,
**gitleaks full‑history secret scan = success**). The one red check, `Workers Builds: confit-a`, is a
documented **pre‑existing, non‑required third‑party Cloudflare check** that fails in 0 s on branches /
green on main (external to Vercel) — **not a Qwen regression** (PR §15).
**Honest remaining merge gates (NOT all green → do not merge yet):** ① **diverse catalog benchmark
= BLOCKED** (needs an authorized real catalog; ground truth not invented) — the one true merge gate
not yet satisfied; ② code review. VTON segfee is existing production (not a new PR).

## 12. MODELS NOT IMPLEMENTED + EVIDENCE‑BASED REASON
- **Qwen2.5‑VL‑3B** — **BLOCKED**: non‑commercial Qwen Research License.
- **fashionCLIP** — **NOT REQUIRED**: spec visual search is VLM‑attribute‑based (G2_G3 §4.3), no perceptual/CLIP retrieval feature; building = unused embedding model.
- **yolos‑fashionpedia** — **NOT REQUIRED**: no standalone detection feature.
- **vitpose‑plus‑small** — **NOT REQUIRED**: no standalone pose feature (DWPose/MediaPipe cover it).
- **sam2‑hiera‑large** — **NOT REQUIRED**: VTON is diffusion segmentation‑free by design; no segmentation feature.
- **OCR / Depth / Image‑moderation / Identity‑verification** — **NOT REQUIRED**: no approved feature (G1 "biometric" = encrypted measurements, not face‑embed).
- **fashn‑vton‑1.5 (full)** — **DO NOT DOWNLOAD**: redundant + reintroduces non‑commercial human‑parser.
- **image‑to‑video (Kling)** — **NOT REQUIRED**: not in approved specs; commercial API, not a self‑hosted HF model.
- **local LLM (stylist)** — **NOT REQUIRED**: deterministic fallback already handles exhaustion; optional P2.

## 13. NO‑HALLUCINATION VERIFICATION STATEMENT
- **VERIFIED / MEASURED (this session, real execution, cited evidence):** Qwen 7B = Apache‑2.0 (HF `cardData.license` + tag), 3B = non‑commercial; **real A10G GPU load (15.45 GiB, ~7–8 s) + real inference (correct STRICT JSON) + real feature SMOKE test (small N; 3.2–4.9 s/image; blazer photo all‑correct; non‑garment wardrobe false‑positive **FIXED + GPU‑verified** — restructured prompt, solid navy swatch now → `category: null`)**; worker parser **8/8** + backend Qwen client/routing/wardrobe **23/23** (**31/31**; full backend suite **1083/0**); weights in Modal Volume (16.59 GB, 14 files validated); VTON branch/WIP preserved.
- **PARTIALLY VERIFIED:** none.
- **NOT VERIFIED:** Qwen across a *diverse* catalog (skin tone/body type/pose/flat‑lay/occlusion) — only a small real smoke set was run (latency/VRAM **are** measured).
- **VERIFIED (this cycle, live deploy):** the deployed **web endpoint works** — the earlier crash‑loop's root cause was a missing `inference` module, fixed by baking the sibling modules into the image. `GET /health` → **200** (`model_loaded`, NVIDIA A10); `POST /analyze` (real blazer, admin auth) → **200**, cold **26.0 s** / warm **5.1 s**, accurate attributes. Remaining: warm‑container *sustainability* (a tier/account choice; `VLM_MIN_CONTAINERS` default 0 avoids idle burn) + full catalog benchmark + PR merge. **PR push: DONE** (branch durable on GitHub).
- **NOT REQUIRED:** all §12 models (evidence‑based).
- The Qwen web fallback is **implemented, deployed, and verified working** (live `/health` + `/analyze` on a real A10, accurate attributes) and is **GPU‑verified** (model + inference + feature, measured). It is **not** yet called "production‑ready": enable it in prod by setting `QWEN_VL_WORKER_URL` + `QWEN_VL_WORKER_TOKEN` (web) when ready, and finish the diverse‑catalog benchmark before advertising it to users. No invented numbers — every latency/VRAM figure above is **measured on a real A10/A10G**. The **existing** VTON remains the "VERIFIED production" baseline (cited real‑GPU evidence).

**Locale/global:** no Egypt/Cairo hard‑coding, no local‑machine paths, no sandbox‑only behavior, no dev credentials in the module; the worker is a standalone Modal service with pinned HF revision + Modal volume (reproducible, no laptop cache, no `/tmp`).
