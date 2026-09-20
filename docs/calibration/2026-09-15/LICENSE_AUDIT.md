# LICENSE AUDIT — Phase 0.5 §12/§29

Every dependency, weight, and model used by the evaluation stack. Verification
dates 2026-09-15. "Verified" = checked against the actual artifact/metadata,
not README claims alone where a stronger source existed.

## Code dependencies (evaluation runtime)
| Dependency | Version | License (verified) | Source of verification | Commercial use |
|-----------|---------|--------------------|------------------------|----------------|
| modal (CLI/client) | 1.5.5 | Apache-2.0 | pip metadata + repo | yes |
| torch (CPU, sandbox only) | 2.14.0+cpu | BSD-3 | pip metadata | yes |
| torchvision (CPU) | 0.29.0+cpu | BSD-3 | pip metadata | yes |
| transformers | installed w/ deps | Apache-2.0 | pip metadata + HF | yes |
| easyocr | 1.7.x | **Apache License 2.0** | `importlib.metadata` License field of installed package, 2026-09-15 | yes |
| mediapipe | 1.0.1 | Apache-2.0 | pip metadata (empty field) + MediaPipe repo LICENSE; model files from official google storage bucket | yes |
| opencv-python-headless | installed | Apache-2.0 | pip metadata | yes |
| scikit-image / scipy / scikit-learn / numpy | installed | BSD / 3-clause | pip metadata | yes |
| Pillow / PyYAML / requests / httpx / pytest | installed | Python/PSF/MIT/Apache-2.0 | pip metadata | yes |
| Qwen2.5-VL-7B-Instruct (judge, eval VLM worker) | revision cc594898137f460bfe9f0759e9844b3ce807cfb5 | **Apache-2.0** | HF model card (production vlm-worker model_spec + HF API) | yes |

## Weights / model files (gitignored; sha256 manifests)
| Artifact | Size | sha256 (first 16) | License | Manifest |
|----------|------|-------------------|---------|----------|
| face_landmarker.task (478 lm) | 3,758,596 B | 64184e229b263107… | Apache-2.0 (MediaPipe) | `evaluation/weights_local/model_manifest.json` |
| pose_landmarker_lite.task | 5,777,746 B | 59929e1d1ee95287… | Apache-2.0 (MediaPipe) | same |
| dinov2-base (ViT-B/14, 86.6M params) @ f9e44c814b77203eaa57a6bdbbd535f21ede1415 | 1 safetensors | recorded | **Apache-2.0** (HF API license tag, 2026-09-15; repo README) | `evaluation/weights_local/dino_manifest.json` |
| EasyOCR craft_mlt_25k.pth | 83,152,330 B | 4a5efbfb48b40811… | Apache-2.0 (EasyOCR) | recorded in this audit; in ~/.EasyOCR/model (outside repo) |
| EasyOCR english_g2.pth | 15,143,997 B | e2272681d9d67a04… | Apache-2.0 (EasyOCR) | same |
| FASHN v1.5 segfee weights | Modal volume `confit-vton-fashn-weights` (shared, read-only) | volume-managed | Apache-2.0 (fashn fork @ 7c0f10af) | not in git |
| Qwen2.5-VL-7B weights | Modal volume `confit-qwen25vl-weights` | volume-managed | Apache-2.0 | not in git |

## Pre-existing repo files (NOT Phase 0.5 changes — documented for completeness)
- `backend/cv_models/hand_landmarker.task`, `backend/cv_models/pose_landmarker_lite.task`
  are tracked in origin/main (repo fact; Apache-2.0 MediaPipe models). Phase 0.5
  does not modify or redistribute them; noted so the "no weights in git" test is
  correctly scoped to `evaluation/` + `fixtures/`.

## OCR engine decision (recorded)
Tesseract (first candidate) was NOT installable in this sandbox (uid 1000, no
root, dpkg lock). **EasyOCR (Apache-2.0) used instead** — license re-verified
at install from package metadata. Documented substitution, not a silent swap.

## Excluded (license blockers — do NOT integrate)
- OpenAI CLIP: model card excludes ANY deployed use case + face recognition → excluded.
- InsightFace: code MIT, weights NC research-only, commercial license sold → excluded unless licensed.
- FastFit: NOASSERTION/NC (LavieAI contract-only) → TRACK 2 LICENSE-GATED, not in this phase.
- DINOv2 derivatives XRay-DINO/Cell-DINO: NC research-only → not used (base ViT-B/14 is Apache-2.0).

## No-NC-weights-in-runtime check
`_parser_in_runtime()` fail-closed check exists in the worker (repo-attested);
eval worker verified `parser_present: false` in every run record. No NC
fashion parsers, no NC weights, in the eval runtime.
