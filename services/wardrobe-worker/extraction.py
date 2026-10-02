"""Wardrobe extraction — pure logic (model-free, unit-testable on CPU).

Feature 04 (Smart Wardrobe) core semantics, kept free of Modal/torch imports
so the tests pin the behaviour with zero model downloads:

  * ATR-18 label → CONFIT wardrobe slot mapping (by LABEL NAME, never by
    hardcoded index — the model's id2label is the source of truth);
  * region grouping (merge left/right shoes, keep garments separate);
  * honest minimum-area threshold (a 0.3% speck is noise, not a garment);
  * person-detection from body labels (face/hair/arms/legs);
  * cutout compositing math (BiRefNet mask → RGBA transparent PNG).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ATR-18 label NAMES (pirocheto/schp-atr-18 id2label values). Mapping is by
# name so a reordered label table can never silently swap meanings.
ATR_LABEL_TO_SLOT: Dict[str, str] = {
    "Hat": "accessory",
    "Upper-clothes": "upper_outer",
    "Skirt": "lower",
    "Pants": "lower",
    "Dress": "dress",
    "Belt": "accessory",
    "Left-shoe": "footwear",
    "Right-shoe": "footwear",
    "Bag": "accessory",
    "Scarf": "accessory",
}
# Body labels (never wardrobe items, but they prove a person is in the photo).
ATR_BODY_LABELS = {"Hair", "Face", "Left-arm", "Right-arm", "Left-leg", "Right-leg", "Sunglass"}
ATR_BACKGROUND_LABELS = {"Background", "background"}

# CONFIT wardrobe slot -> renderable category vocabulary (shared with VTON).
SLOT_TO_CATEGORY: Dict[str, str] = {
    "upper_outer": "tops",
    "upper_inner": "tops",
    "lower": "bottoms",
    "dress": "one-pieces",
    "footwear": "footwear",
    "accessory": "accessory",
}

# A region smaller than this fraction of the photo is honestly NOT a garment.
MIN_AREA_FRACTION = 0.005
MAX_ITEMS = 6


def group_regions(
    seg_map_labels: List[Tuple[str, Any]],  # (label_name, mask) pairs
    image_area: int,
    min_area_fraction: float = MIN_AREA_FRACTION,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Group per-label masks into wardrobe items + skip report.

    Returns (items, report). Each item: {slot_type, label_names, mask, area}.
    Labels mapping to the same slot with adjacent roles merge (both shoes =
    one footwear item). Regions below the honest threshold are REPORTED as
    skipped — never silently dropped, never promoted to items.
    """
    by_slot: Dict[str, Dict[str, Any]] = {}
    skipped: List[Dict[str, Any]] = []
    person_labels: List[str] = []

    for label, mask in seg_map_labels:
        if label in ATR_BACKGROUND_LABELS:
            continue
        if label in ATR_BODY_LABELS:
            person_labels.append(label)
            continue
        slot = ATR_LABEL_TO_SLOT.get(label)
        if slot is None:
            skipped.append({"label": label, "reason": "unmapped_label"})
            continue
        area = int((mask != 0).sum()) if hasattr(mask, "__ne__") else 0
        if area < max(1, int(image_area * min_area_fraction)):
            skipped.append({"label": label, "reason": "below_min_area", "area": area})
            continue
        if slot in by_slot:
            by_slot[slot]["area"] += area
            by_slot[slot]["label_names"].append(label)
            by_slot[slot]["masks"].append(mask)
        else:
            by_slot[slot] = {
                "slot_type": slot,
                "category": SLOT_TO_CATEGORY.get(slot, "accessory"),
                "label_names": [label],
                "area": area,
                "masks": [mask],
            }

    items = sorted(by_slot.values(), key=lambda i: -i["area"])[:MAX_ITEMS]
    report = {
        "person_detected": len(person_labels) > 0,
        "person_labels": sorted(set(person_labels)),
        "skipped": skipped,
    }
    return items, report


def item_confidence(area: int, image_area: int) -> float:
    """Honest, bounded confidence: region prominence (area fraction), scaled
    so a garment covering ≥30% of the photo reads ~0.9. Never fabricated."""
    frac = (area / image_area) if image_area else 0.0
    return round(min(0.95, 0.35 + 2.0 * frac), 3)


def compose_cutout(crop_rgb, mask, threshold: float = 0.5) -> Any:
    """BiRefNet sigmoid mask + RGB crop -> RGBA cutout (transparent bg).

    ``crop_rgb``: PIL image; ``mask``: HxW float in [0,1] (resized to the
    crop if needed). Alpha is CONTINUOUS (mask*255) — the soft edge is
    BiRefNet's core quality and binarising it throws that away; below
    ``threshold`` the pixel counts as background and alpha is forced to 0
    so faint halo regions never bleed into the gallery render.
    """
    import numpy as np
    from PIL import Image

    rgb = np.asarray(crop_rgb.convert("RGB")).astype(np.uint8)
    m = np.asarray(mask, dtype=np.float32)
    if m.shape != rgb.shape[:2]:
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((rgb.shape[1], rgb.shape[0])), dtype=np.float32) / 255.0
    m = np.clip(m, 0.0, 1.0)
    alpha = (m * 255).astype(np.uint8)
    alpha[m < threshold] = 0
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgba, "RGBA")


def bbox_of_mask(mask) -> Tuple[int, int, int, int]:
    """Tight bounding box (left, top, right, bottom) of a binary mask."""
    import numpy as np

    m = np.asarray(mask) != 0
    rows = np.any(m, axis=1)
    cols = np.any(m, axis=0)
    if not rows.any():
        return (0, 0, 0, 0)
    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]
    return (int(left), int(top), int(right), int(bottom))
