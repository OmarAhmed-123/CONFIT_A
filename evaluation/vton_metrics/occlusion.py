"""Occlusion-aware region state classification (Phase 0.5, §18).

Per-garment occlusion state is derived from deterministic pose+region geometry
plus expected garment extent from fixture metadata:

  FULLY_VISIBLE     — garment region fully inside image, pose not blocking it.
  PARTIALLY_VISIBLE — region clipped by image border or partial pose overlap.
  OCCLUDED_VERIFIED — significant self/other-layer occlusion expected from the
                       outfit configuration (e.g. outer over inner); verified by
                       layer-order logic, not by a learned occlusion model.
  NOT_APPLIED       — garment not in the outfit (e.g. bottom evaluated on a
                       top-only chain step).
  UNDETERMINED      — pose missing / geometry unusable.

Partial hiding is NOT an automatic failure: downstream metrics switch to
lenient regimes (see ocr_metrics, color metrics note) based on state.
"""
from __future__ import annotations

STATE = ("FULLY_VISIBLE", "PARTIALLY_VISIBLE", "OCCLUDED_VERIFIED", "NOT_APPLIED", "UNDETERMINED")


def region_in_image(box, img_w: int, img_h: int, threshold: float = 0.98) -> bool:
    x0, y0, x1, y1 = box
    area = max(0, x1 - x0) * max(0, y1 - y0)
    full = max(0, min(img_w, x1) - max(0, x0)) * max(0, min(img_h, y1) - max(0, y0))
    return area > 0 and (full / area) >= threshold


def classify(region_status: str, in_image: bool | None, occlusion_expected: bool) -> str:
    if occlusion_expected:
        return "OCCLUDED_VERIFIED"
    if region_status == "OK" and in_image:
        return "FULLY_VISIBLE"
    if region_status == "OK" and in_image is False:
        return "PARTIALLY_VISIBLE"
    return "UNDETERMINED"


def outfit_occlusion_map(layers: list[str]) -> dict[str, bool]:
    """Given ordered layers (first = applied first, i.e. innermost), which garments
    are occlusion-expected at each chain step.

    Rule: a garment is occluded if ANY garment applied AFTER it covers the same
    slot family (upper over upper, lower over lower, dress over anything).
    Chain semantics: at step k, only layers[0..k] exist; occlusion is judged for
    the FINAL composition (conservative for per-step metric leniency).
    """
    slot_family = {"upper_inner": "upper", "upper_outer": "upper", "lower": "lower",
                  "dress": "dress", "one_piece": "dress"}
    fam = [slot_family.get(l, "upper") for l in layers]
    out = {}
    for i, l in enumerate(layers):
        occluded = False
        for j in range(i + 1, len(layers)):
            if fam[j] == fam[i] or fam[j] == "dress":
                occluded = True
                break
        out[l] = occluded
    return out
