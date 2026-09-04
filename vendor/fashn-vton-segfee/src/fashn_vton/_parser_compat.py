"""Clean-room label metadata for the FASHN segmentation-free fork.

This module replaces the *constant surface* that upstream FASHN re-exports
from the (non-commercial) ``fashn_human_parser`` package. It contains only
pure label-id integer metadata and category/coverage mappings — **no model
weights, no neural network, no inference code, and no import of**
``fashn_human_parser`` at any point.

Because the commercial fork runs **exclusively segmentation-free** (person
agnostic image is returned unchanged, and garments are flat-lay product
shots that are returned unchanged), the segmentation arrays that upstream's
parser produces are **never consumed**. These constants exist only so the
category → body-coverage → label plumbing (which upstream computes but, in
segmentation-free mode, does not use) remains faithful and future-proof.

License note: these are numerical label/schema constants (interoperability
metadata), not weights or a derivative of the SegFormer network. They do not
copy or invoke the restricted model.
"""

from typing import Dict, List

# 18-class label schema (integer ids only — no network).
IDS_TO_LABELS: Dict[int, str] = {
    0: "background",
    1: "face",
    2: "hair",
    3: "top",
    4: "dress",
    5: "skirt",
    6: "pants",
    7: "belt",
    8: "bag",
    9: "hat",
    10: "scarf",
    11: "glasses",
    12: "arms",
    13: "hands",
    14: "legs",
    15: "feet",
    16: "torso",
    17: "jewelry",
}

LABELS_TO_IDS: Dict[str, int] = {v: k for k, v in IDS_TO_LABELS.items()}

CATEGORY_TO_BODY_COVERAGE: Dict[str, str] = {
    "tops": "upper",
    "bottoms": "lower",
    "one-pieces": "full",
}

BODY_COVERAGE_TO_LABELS: Dict[str, List[str]] = {
    "upper": ["top", "dress", "scarf"],
    "lower": ["skirt", "pants", "belt"],
    "full": ["top", "dress", "scarf", "skirt", "pants", "belt"],
}

IDENTITY_LABELS: List[str] = ["face", "hair", "jewelry", "bag", "glasses", "hat"]
