"""P0 garment-asset gate (ghost-hands remediation) — backend side.

The production "ghost hands" incident happened because a catalog photo in
which a model WEARS the garment was sent to the segmentation-free engine as
if it were a flat-lay: the engine's garment conditioning then contained the
catalog model's hands/skin and the render reproduced them on the user.

This guard makes that impossible at the API layer: before any GPU time is
spent, every garment image is classified on CPU (PIL+numpy only — no torch,
no parser, Vercel-safe) and a worn ("model") photo is rejected UNLESS a
validated clean asset (``garment_assets.tryon_ready``) exists for it.

Classification heuristic (deliberately conservative, mirroring the
conservative-model rule of the worker-side gate in
engine/fashn_v15.classify_garment_photo):

  1. skin-ratio detector: fraction of pixels inside YCrCb skin chroma
     bounds; worn photos contain hands/neck/face, flat-lays essentially none
     (>= 1.5% skin => 'model');
  2. background-uniformity detector: flat-lays/ghost-mannequin shots are
     dominated by one uniform backdrop (>= 45% of one quantised colour =>
     'flat-lay');
  3. both inconclusive => 'model' (conservative). Mislabelling a flat-lay
     as worn costs one loud, actionable rejection; mislabelling a worn
     photo as flat-lay silently contaminates the render.

Every verdict carries its evidence (detector + measurements) so the
rejection message and the job metrics show WHY, never assumed.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image

SKIN_RATIO_MODEL_THRESHOLD = 0.015   # >=1.5% skin pixels => a person is in frame
BG_UNIFORM_FLATLAY_THRESHOLD = 0.45  # >=45% single quantised colour => studio backdrop


def _skin_ratio(rgb: np.ndarray) -> float:
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    cr = 128 + ((r * 112 - g * 94 - b * 18) >> 8)
    cb = 128 + ((-r * 38 - g * 74 + b * 112) >> 8)
    mask = (cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127)
    return float(mask.mean())


def _bg_uniformity(rgb: np.ndarray) -> float:
    """Fraction of pixels equal to the dominant quantised colour."""
    q = (rgb // 32).astype(np.uint32)
    keys = (q[..., 0] << 8) | (q[..., 1] << 4) | q[..., 2]
    vals, counts = np.unique(keys, return_counts=True)
    return float(counts.max() / keys.size)


def classify_garment_photo(image: Image.Image) -> Tuple[str, Dict]:
    """Return ('model' | 'flat-lay', evidence). CPU-only, deterministic."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    # Cap work: classify on a 512px-side preview (deterministic downscale)
    side = max(rgb.shape[:2])
    if side > 512:
        image = image.convert("RGB").resize(
            (int(rgb.shape[1] * 512 / side), int(rgb.shape[0] * 512 / side))
        )
        rgb = np.asarray(image, dtype=np.uint8)

    skin = _skin_ratio(rgb)
    bg = _bg_uniformity(rgb)

    if skin >= SKIN_RATIO_MODEL_THRESHOLD:
        verdict, detector = "model", "skin-ratio"
    elif bg >= BG_UNIFORM_FLATLAY_THRESHOLD:
        verdict, detector = "flat-lay", "background-uniformity"
    else:
        verdict, detector = "model", "conservative-default"

    return verdict, {
        "detector": detector,
        "skin_ratio": round(skin, 4),
        "bg_uniformity": round(bg, 4),
        "thresholds": {
            "skin_ratio_model": SKIN_RATIO_MODEL_THRESHOLD,
            "bg_uniformity_flatlay": BG_UNIFORM_FLATLAY_THRESHOLD,
        },
    }


def asset_gate_error(
    photo_type: str,
    evidence: Dict,
    product_id: int,
    product_title: str,
    has_prepared_asset: bool,
) -> Optional[str]:
    """Non-None message means the product must NOT enter a VTON job.

    A worn catalog photo may only render through a validated clean asset
    (garment_assets.tryon_ready=True, produced by the P1 prep pipeline).
    """
    if photo_type != "model":
        return None
    if has_prepared_asset:
        return None
    return (
        f"VTON_GARMENT_ASSET_INVALID: product {product_id} "
        f"({product_title!r}) catalog photo is an ON-MODEL shot "
        f"(detector={evidence['detector']}, skin_ratio={evidence['skin_ratio']}, "
        f"bg_uniformity={evidence['bg_uniformity']}). The segmentation-free "
        "engine only accepts clean flat-lay garment assets; feeding a worn "
        "photo reproduces the catalog model's body (the 'ghost hands' "
        "incident). Prepare a clean garment asset (P1 prep pipeline) or "
        "upload a flat-lay product photo to enable try-on for this item."
    )
