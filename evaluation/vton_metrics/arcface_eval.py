"""ArcFace w600k_r50 identity-verification embedding (EVALUATION component).

Restore of the identity measurement after the 2026-09-15 sandbox recreation
dropped the gitignored AdaFace binary (weights_local is not committed; HF was
unreachable from the sandbox, so the documented re-download path failed).

License status (same class as the AdaFace weights it temporarily replaces):
  - Model: ArcFace iResNet-R50, WebFace600K (WebFace4M subset) trained —
    NO established commercial license for the training data (UNRESOLVED).
  - Distribution: InsightFace model zoo (deepinsight/insightface, GitHub
    release ``model-zoo``, buffalo_l.zip). Code Apache-2.0; weights license
    follows the training data (UNRESOLVED).
  - Classification: LICENSE-GATED / RESEARCH-EVALUATION-ONLY.
    May NOT be a production gate without resolved commercial rights.
  - Source: https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip
  - Weights NEVER committed to git (weights_local/ is gitignored).

Technical: iResNet-R50, 512-d L2-normalized embedding, input 112x112 RGB
normalized (x/255 - 0.5)/0.5. Face crop: IDENTICAL convention to
``adaface_eval`` — axis-aligned similarity crop (scale only), centered on
the eye midpoint, IOD scaled to 35.2 px, from MediaPipe face landmarks
(``face_metrics.landmarks``). Both images of a pair go through the identical
pipeline. Deterministic.

Use ONLY for evaluation (identity measurement evidence in the AT suite).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import torch
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
ARCFACE_DIR = REPO / "evaluation" / "weights_local" / "arcface_w600k"
MODEL_ONNX = ARCFACE_DIR / "w600k_r50.onnx"
SOURCE_URL = "https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip"

_TARGET_IOD_PX = 35.2
_BOX = 112

_SESSION = None
_IO = None


def _session():
    global _SESSION, _IO
    if _SESSION is not None:
        return _SESSION, _IO
    if not MODEL_ONNX.exists():
        raise RuntimeError(
            f"ArcFace weights missing at {MODEL_ONNX} (not committed; re-download from {SOURCE_URL})"
        )
    import onnxruntime as ort

    _SESSION = ort.InferenceSession(str(MODEL_ONNX), providers=["CPUExecutionProvider"])
    _IO = (_SESSION.get_inputs()[0].name, _SESSION.get_outputs()[0].name)
    return _SESSION, _IO


def weights_sha256() -> str:
    return hashlib.sha256(MODEL_ONNX.read_bytes()).hexdigest()


def _face_crop_112(img, pts) -> np.ndarray | None:
    """Axis-aligned 112x112 crop: centered on eye midpoint, IOD -> 35.2 px.

    Identical geometry to ``adaface_eval._face_crop_112`` (kept independent
    so this module has no dependency on the AdaFace weights).
    """
    from .face_metrics import geometry
    from .imaging import to_array

    g = geometry(pts)
    mid = np.array(g["eye_midpoint"], dtype=np.float64)
    iod = g["iod"]
    if iod <= 0:
        return None
    scale = _TARGET_IOD_PX / iod
    w, h = img.size
    arr = to_array(img)
    half = (0.5 * _BOX) / scale
    x0, y0 = mid[0] - half, mid[1] - half
    x1, y1 = mid[0] + half, mid[1] + half
    arr_p = np.zeros((h + 16, w + 16, 3), dtype=np.uint8)
    arr_p[8 : 8 + h, 8 : 8 + w] = arr
    arr_p = Image.fromarray(arr_p)
    box = (max(0.0, x0) + 8, max(0.0, y0) + 8, min(w + 16, x1) + 8, min(h + 16, y1) + 8)
    crop = arr_p.crop(box).resize((_BOX, _BOX), Image.BILINEAR)
    return to_array(crop)


def embedding(img) -> tuple[np.ndarray | None, dict]:
    """L2-normalized 512-d ArcFace embedding of the (landmark-located) face."""
    from .face_metrics import landmarks
    from .imaging import load_image, to_array

    if isinstance(img, (str, Path)):
        img = load_image(img)
    pts = landmarks(img)
    if pts is None:
        return None, {"status": "NO_FACE"}
    crop = _face_crop_112(img, pts)
    if crop is None:
        return None, {"status": "NO_FACE_GEOMETRY"}
    session, (in_name, out_name) = _session()
    x = crop.astype(np.float32) / 255.0
    x = (x - 0.5) / 0.5
    x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
    out = session.run([out_name], {in_name: x})[0].reshape(-1).astype(np.float32)
    n = np.linalg.norm(out)
    if n < 1e-8:
        return None, {"status": "ZERO_EMBEDDING"}
    return out / n, {"status": "OK", "shape": out.shape}


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def identity_cosine(img_ref, img_out) -> dict:
    """Same-identity cosine between reference person and output (pair-level)."""
    e1, s1 = embedding(img_ref)
    e2, s2 = embedding(img_out)
    out = {
        "arcface_w600k_r50": {
            "status": "OK",
            "ref": s1["status"],
            "out": s2["status"],
            "model": "ArcFace iResNet-R50 (WebFace600K)",
            "weights_sha256": weights_sha256(),
            "source": SOURCE_URL,
            "license": "LICENSE-GATED / eval-only (training data license UNRESOLVED)",
        }
    }
    if e1 is not None and e2 is not None:
        out["arcface_w600k_r50"]["cosine"] = round(cosine(e1, e2), 5)
    return out


if __name__ == "__main__":
    import json
    import sys

    ref, outp = sys.argv[1], sys.argv[2]
    print(json.dumps(identity_cosine(ref, outp), indent=2))
