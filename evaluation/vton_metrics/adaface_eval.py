"""AdaFace IR101 identity-verification embedding (EVALUATION component).

License status (audited 2026-09-15, see docs/calibration/2026-09-15/LICENSE_AUDIT):
  - Code: MIT (mk-minchul/AdaFace GitHub repo license — VERIFIED via GitHub API).
  - Weights: distributed on HF by the author; card instructs to "follow the
    license of the training dataset". Trained on MS1MV2 (WebFace4M subset) —
    NO established commercial license for that dataset (UNRESOLVED).
  - Classification: LICENSE-GATED / RESEARCH-EVALUATION-ONLY.
    May NOT be a production gate without resolved commercial rights.
    Weights are NEVER committed to git (weights_local/ is gitignored).

Technical: iResNet-IR101, 512-d L2-normalized embedding, input 112x112 RGB
normalized (x/255 - 0.5)/0.5. Face crop: axis-aligned similarity (scale only,
no rotation — repo convention), centered on the eye midpoint with IOD scaled
to 35.2 px (the IOD implied by the standard 5-point arcface template at
112x112: eye centers ~38.3/73.5 px). Deterministic; both images of a pair go
through the identical pipeline.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from .face_metrics import geometry, landmarks
from .imaging import load_image, to_array

REPO = Path(__file__).resolve().parents[2]
ADAFACE_DIR = REPO / "evaluation" / "weights_local" / "adaface_ir101"
MODEL_PT = ADAFACE_DIR / "pretrained_model" / "model.pt"

_TARGET_IOD_PX = 35.2
_BOX = 112

# 5-point-template provenance (standard arcface alignment template @112)
_TEMPLATE_PROVENANCE = "arcface 5-point template (eye centers x≈38.3/73.5, y≈51.5 @112x112)"

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not MODEL_PT.exists():
        raise RuntimeError(f"AdaFace weights missing at {MODEL_PT} (not committed; "
                           "re-download per LICENSE_AUDIT provenance)")
    # fvcore is only imported for flop counting in the training repo — stub it.
    if "fvcore" not in sys.modules:
        fv = types.ModuleType("fvcore")
        fvn = types.ModuleType("fvcore.nn")
        fvn.flop_count = lambda *a, **k: None
        fv.nn = fvn
        sys.modules["fvcore"] = fv
        sys.modules["fvcore.nn"] = fvn
    sys.path.insert(0, str(ADAFACE_DIR))
    try:
        from omegaconf import OmegaConf
        from models import get_model  # type: ignore

        cfg = OmegaConf.create(
            OmegaConf.load(str(ADAFACE_DIR / "pretrained_model" / "model.yaml")))
        net = get_model(cfg)
        net.load_state_dict_from_path(str(MODEL_PT))
        net.eval()
    finally:
        sys.path.pop(0)
    _MODEL = net
    return _MODEL


def _face_crop_112(img, pts) -> np.ndarray | None:
    """Axis-aligned 112x112 crop: centered on eye midpoint, IOD -> 35.2 px."""
    g = geometry(pts)
    mid = np.array(g["eye_midpoint"], dtype=np.float64)
    iod = g["iod"]
    if iod <= 0:
        return None
    scale = _TARGET_IOD_PX / iod
    w, h = img.size
    arr = to_array(img)
    # build a virtual square window in image coords, resize to 112
    half = (0.5 * _BOX) / scale
    x0 = mid[0] - half
    y0 = mid[1] - half
    x1 = mid[0] + half
    y1 = mid[1] + half
    # pad if out of bounds
    arr_p = np.zeros((h + 16, w + 16, 3), dtype=np.uint8)
    arr_p[8:8 + h, 8:8 + w] = arr
    arr_p = Image.fromarray(arr_p)
    box = (max(0.0, x0) + 8, max(0.0, y0) + 8, min(w + 16, x1) + 8, min(h + 16, y1) + 8)
    crop = arr_p.crop(box).resize((_BOX, _BOX), Image.BILINEAR)
    return to_array(crop)


def embedding(img) -> tuple[np.ndarray | None, dict]:
    """L2-normalized 512-d AdaFace embedding of the (pose-located) face."""
    if isinstance(img, (str, Path)):
        img = load_image(img)
    pts = landmarks(img)
    if pts is None:
        return None, {"status": "NO_FACE"}
    crop = _face_crop_112(img, pts)
    if crop is None:
        return None, {"status": "NO_FACE_GEOMETRY"}
    x = torch.from_numpy(crop.astype(np.float32) / 255.0)
    x = (x - 0.5) / 0.5
    x = x.permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        e = _model().forward(x)
    e = e.squeeze(0).numpy().astype(np.float32)
    n = np.linalg.norm(e)
    if n < 1e-8:
        return None, {"status": "ZERO_EMBEDDING"}
    return e / n, {"status": "OK", "shape": e.shape}


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def identity_cosine(img_ref, img_out) -> dict:
    """Same-identity cosine between reference person and output (pair-level)."""
    e1, s1 = embedding(img_ref)
    e2, s2 = embedding(img_out)
    out = {
        "adaface_ir101": {
            "status": "OK",
            "ref": s1["status"],
            "out": s2["status"],
            "model": "AdaFace iResNet-IR101 (MS1MV2)",
            "weights_sha256": hashlib.sha256(MODEL_PT.read_bytes()).hexdigest(),
            "template": _TEMPLATE_PROVENANCE,
        }
    }
    if e1 is not None and e2 is not None:
        out["adaface_ir101"]["cosine"] = round(cosine(e1, e2), 5)
    return out


if __name__ == "__main__":
    import json
    ref, outp = sys.argv[1], sys.argv[2]
    print(json.dumps(identity_cosine(ref, outp), indent=2))
