"""DINOv2 ViT-B/14 similarity (Phase 0.5).

License: facebook/dinov2-base — Apache-2.0 (verified from repo README,
2026-09-15). Used ONLY as a similarity/DRIFT PROXY (face crops, garment
regions), never as a validated face-recognition system.

Model is downloaded ONCE to evaluation/weights_local/ (gitignored) with a
pinned revision and recorded sha256. Lazy-loaded, torch CPU.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .imaging import to_array

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights_local"
MODEL_NAME = "facebook/dinov2-base"
MODEL_REVISION = "f9e44c814b77203eaa57a6bdbbd535f21ede1415"  # pinned main sha (HF API, 2026-09-15); see LICENSE_AUDIT.md
_model = None


def _get_model():
    global _model
    if _model is None:
        import torch
        from transformers import AutoModel, AutoProcessor
        cache = WEIGHTS_DIR / "dino"
        cache.mkdir(parents=True, exist_ok=True)
        _model = (AutoModel.from_pretrained(MODEL_NAME, revision=MODEL_REVISION,
                                            cache_dir=str(cache)),
                  AutoProcessor.from_pretrained(MODEL_NAME, revision=MODEL_REVISION,
                                                cache_dir=str(cache)),
                  torch)
    return _model


def embed(img_or_path, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    model, proc, torch = _get_model()
    from PIL import Image
    img = Image.open(img_or_path).convert("RGB") if isinstance(img_or_path, (str, Path)) else img_or_path
    if box is not None:
        img = img.crop(box)
    inputs = proc(images=img, return_tensors="pt")
    with torch.no_grad():
        f = model(**inputs).last_hidden_state[:, 0]  # CLS token
    v = f.numpy()[0]
    v = v / (np.linalg.norm(v) + 1e-12)
    return v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def similarity_report(img_ref, ref_box, img_out, out_box) -> dict:
    """Garment/region semantic similarity between reference garment and output region.

    KNOWN LIMITATIONS (documented, expected to fail or degrade on): warping,
    occlusion, lighting change, perspective, partial visibility, texture change.
    Treat as a SOFT signal pending calibration.
    """
    v1 = embed(img_ref, ref_box)
    v2 = embed(img_out, out_box)
    return {
        "metric": "dinov2_region_similarity",
        "cosine": round(cosine(v1, v2), 4),
        "proxy_only": True,
    }


def face_similarity(img_ref, img_out) -> dict:
    """DINOv2 cosine on IOD-aligned face crops (DRIFT PROXY, not recognition)."""
    from .face_metrics import aligned_face_crop, landmarks
    import numpy as np
    p1 = landmarks(img_ref)
    p2 = landmarks(img_out)
    if p1 is None or p2 is None:
        return {"metric": "dinov2_face_similarity", "cosine": None}
    c1 = aligned_face_crop(img_ref, p1)
    c2 = aligned_face_crop(img_out, p2)
    from PIL import Image
    v1 = embed(Image.fromarray(c1.astype(np.uint8)), None)
    v2 = embed(Image.fromarray(c2.astype(np.uint8)), None)
    return {"metric": "dinov2_face_similarity", "cosine": round(cosine(v1, v2), 4)}
