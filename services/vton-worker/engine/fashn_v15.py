"""FASHN VTON v1.5 multi-garment engine (parser-enabled, swappable parser).

WHY THIS ENGINE EXISTS
----------------------
`fashn_vton_segfee` (engine/fashn_segfee.py) is the single-garment,
parser-free commercial fork. This engine drives the PRISTINE upstream
pipeline (vendor/fashn-vton-1.5, Apache-2.0) together with the
fashn-human-parser to deliver feature 03:

  * MULTI-GARMENT outfits (tops + bottoms) composed sequentially in ONE
    worker call — each later layer renders on the previous layer's output,
    with the parser masking only the region it replaces so earlier layers
    stay pixel-exact.
  * MODEL-PHOTO garments: the parser segments a garment out of a worn
    catalogue photo (the segfee fork could only accept flat-lays).

LICENSE HONESTY (do not remove)
-------------------------------
Upstream pipeline + weights + DWPose + YOLOX: Apache-2.0.
fashn-human-parser (SegFormer fine-tune): NVIDIA Source Code License for
SegFormer — NON-COMMERCIAL. Product decision (project owner, 2026-10-01):
ship it while the project is early-stage and SWAP to a licensed parser
before commercial scale. The parser is loaded through `parser_impl` below
(duck-typed ``.predict(np.ndarray) -> np.ndarray``); the swap is one class
with ZERO upstream modification — the upstream pipeline only ever calls
``self.hp_model.predict(...)`` on the object we inject.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image

from .base import VTONEngine

# ---------------------------------------------------------------------------
# Slot → FASHN category mapping. ONE source of truth for the worker + engine:
# the worker maps the request vocabulary, the engine composes by category.
# ---------------------------------------------------------------------------
SLOT_TO_CATEGORY: Dict[str, str] = {
    "upper_outer": "tops",
    "upper_inner": "tops",
    "inner_layer": "tops",
    "knit_layer": "tops",
    "lower": "bottoms",
    "dress": "one-pieces",
}
SUPPORTED_CATEGORIES = ("tops", "bottoms", "one-pieces")

# Canonical composition order: tops first, bottoms second. Rationale: the
# second layer masks ONLY its own lower-body region (parser labels), so the
# top applied first is preserved pixel-exact; and a long top rendered last
# would occlude the freshly-drawn bottoms, whereas bottoms drawn last tuck
# naturally under an existing hem. one-pieces must arrive alone.
_CATEGORY_ORDER = {"tops": 0, "bottoms": 1, "one-pieces": 2}

# Multi-garment guard: these combinations are semantically conflicting —
# a one-piece covers the same regions as tops/bottoms.
_CONFLICTS: Tuple[Tuple[str, ...], ...] = (("one-pieces", "tops"), ("one-pieces", "bottoms"))

MAX_GARMENTS = 3

# Parser label IDs (fashn_human_parser.labels) that indicate a garment photo
# is WORN by a person (model photo) rather than a flat-lay product shot.
_PERSONHOOD_LABEL_IDS = {1, 2, 12, 13}  # face, hair, arms, hands

# DWPose body keypoints (of 18) above the visibility threshold that mean "a
# person is present" in the garment photo. Used by the FALLBACK detector
# when the parser yields no verdict. 4 = face/shoulders minimum silhouette;
# flat-lays and ghost mannequins produce none.
_PERSON_KEYPOINT_MIN = 4


class FashnV15MultiGarmentEngine(VTONEngine):
    """Multi-garment adapter around the pristine fashn-vton-1.5 pipeline."""

    name = "fashn_v15"
    model_revision = "fashn-AI/fashn-vton-1.5 @ 7c0f10af (pristine upstream)"
    license_summary = (
        "Apache-2.0 (pipeline/DWPose/YOLOX); fashn-human-parser is NVIDIA "
        "SegFormer NON-COMMERCIAL — owner-approved for early-stage use "
        "(2026-10-01), licensed parser swap planned before commercial scale"
    )
    commercially_usable = False  # honest: parser is non-commercial until swapped

    def __init__(self, weights_dir: str, device: str = "cuda", parser_impl: Any = None, **kwargs: Any) -> None:
        self._weights_dir = weights_dir
        self._device = device
        self._parser_impl = parser_impl  # None -> upstream default (FashnHumanParser)
        self._pipe = None
        self._ready = False
        self._parser_model = None  # for photo-type auto-detection

    @property
    def supports_multigarment(self) -> bool:
        return True

    # -- lifecycle -----------------------------------------------------------

    def load(self) -> None:
        """Load the upstream pipeline. The parser weights download into
        ``HF_HOME`` on first use; the worker points HF_HOME at the shared
        Modal volume so cold starts do not re-download 244 MB."""
        import sys

        vendor = os.environ.get("FASHN_V15_VENDOR_DIR", "/root/fashn-vton-1.5")
        if vendor not in sys.path:
            sys.path.insert(0, vendor)

        from fashn_vton import TryOnPipeline  # pristine upstream, unmodified

        self._pipe = TryOnPipeline(weights_dir=self._weights_dir, device=self._device)
        if self._parser_impl is not None:
            # Swappable parser seam: the upstream pipeline only ever calls
            # self.hp_model.predict(image_np) — any duck-typed replacement works.
            self._pipe.hp_model = self._parser_impl
        self._parser_model = self._pipe.hp_model
        self._ready = True

    # -- input normalisation (pure, unit-testable without GPU) ---------------

    @staticmethod
    def normalize_garments(garments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate + canonically order a multi-garment request.

        Each garment: {category or slot_type, image (PIL.Image)}. Returns a
        NEW list, tops before bottoms; raises ValueError on any conflict
        (one-pieces mixed with tops/bottoms) or unsupported category.
        Client order is NEVER trusted for composition.
        """
        if not garments:
            raise ValueError("at least one garment required")
        if len(garments) > MAX_GARMENTS:
            raise ValueError(f"too many garments: max {MAX_GARMENTS}, got {len(garments)}")

        normalized: List[Dict[str, Any]] = []
        for idx, g in enumerate(garments):
            raw = (g.get("slot_type") or g.get("category") or "").strip().lower()
            category = SLOT_TO_CATEGORY.get(raw, raw if raw in SUPPORTED_CATEGORIES else None)
            if category is None:
                raise ValueError(
                    f"garment {idx}: unsupported slot_type/category {raw!r}; "
                    f"supported: tops/bottoms/one-pieces "
                    f"(slots: {sorted(SLOT_TO_CATEGORY)})"
                )
            image = g.get("image")
            if image is None:
                raise ValueError(f"garment {idx}: missing image")
            normalized.append(
                {
                    "category": category,
                    "image": image,
                    "photo_type": g.get("photo_type"),  # None -> auto-detect
                    "slot_type": g.get("slot_type") or g.get("category"),
                    "product_id": g.get("product_id"),
                }
            )

        categories = {g["category"] for g in normalized}
        for conflict in _CONFLICTS:
            if all(c in categories for c in conflict):
                raise ValueError(
                    f"conflicting garments: {' + '.join(conflict)} cover the same "
                    "body regions; a one-piece must be tried on alone"
                )

        normalized.sort(key=lambda g: _CATEGORY_ORDER[g["category"]])
        return normalized

    @staticmethod
    def detect_garment_photo_type(seg_pred: Any) -> str:
        """Decide flat-lay vs model photo from parser labels of the GARMENT image.

        ``seg_pred`` is the parser's per-pixel label array (H, W) or None.
        A worn photo contains person labels (face/hair/arms/hands); a flat-lay
        contains none. Returns 'model' or 'flat-lay'.
        """
        if seg_pred is None:
            return "flat-lay"  # no parser verdict: see classify_garment_photo
        try:
            import numpy as np

            labels = set(np.unique(np.asarray(seg_pred)).tolist())
            return "model" if labels & _PERSONHOOD_LABEL_IDS else "flat-lay"
        except Exception:
            return "flat-lay"

    def classify_garment_photo(self, garment) -> "tuple":
        """Two INDEPENDENT detectors decide worn vs flat-lay — the anti-
        contamination gate for garment images.

        WHY THIS EXISTS: when a garment photo is WORN by a person (a model
        shot), the pipeline must know so it masks the garment out of the
        photo before conditioning the diffusion. Treating a worn photo as a
        flat-lay feeds the photo's PERSON (face, hair, background) into the
        composition — the exact "the garment photo's person was pasted onto
        the user" failure. Detection order:

        1. parser labels (primary): person-label pixels present -> 'model';
        2. DWPose body keypoints (independent fallback, used when the parser
           yields no verdict): >= _PERSON_KEYPOINT_MIN visible body
           keypoints -> 'model', else 'flat-lay';
        3. BOTH inconclusive -> 'model' (CONSERVATIVE). Mislabelling a
           flat-lay as 'model' at worst degrades one render that honest
           output verification then fails loudly; mislabelling a worn photo
           as 'flat-lay' silently contaminates the output. Between a loud
           failure and a silent bad image, the loud failure is correct.

        Returns (photo_type, evidence) — the evidence records WHICH detector
        decided, so per-layer metadata shows exactly how the outfit was
        classified (observable, never assumed).
        """
        seg = self._safe_predict(garment)
        if seg is not None:
            return self.detect_garment_photo_type(seg), {"detector": "parser"}

        pose_person = self._safe_pose_person(garment)
        if pose_person is None:
            return "model", {"detector": "none-conservative"}
        return ("model" if pose_person else "flat-lay"), {"detector": "dwpose"}

    def _safe_pose_person(self, garment):
        """DWPose person-presence, degrading to None (inconclusive) instead of
        failing the job. The pose model is the pipeline's own DWPose instance
        — an independent signal that shares no weights with the parser."""
        try:
            import numpy as np

            pose = self._pipe.pose_model(
                np.asarray(garment.convert("RGB"))[..., ::-1]  # RGB -> BGR (DWPose)
            )
            subset = np.asarray(pose["bodies"]["subset"])
            # After DWPose's own thresholding, visible keypoints carry their
            # index and invisible ones are -1: count the visible body ones.
            return int(np.count_nonzero(subset != -1)) >= _PERSON_KEYPOINT_MIN
        except Exception:
            return None

    # -- validation ------------------------------------------------------------

    def validate_inputs(
        self,
        person_image: Image.Image,
        garment_image: Image.Image | None,
        category: str | None,
    ) -> None:
        if person_image is None:
            raise ValueError("person image required")
        if garment_image is None:
            raise ValueError("garment image required")
        if category is not None and category not in SUPPORTED_CATEGORIES:
            raise ValueError(f"unsupported category {category!r}")

    def validate_output(self, output: Image.Image, reference: Image.Image) -> Dict[str, Any]:
        """No echo, not blank, genuinely changed — same bar as the segfee engine."""
        import numpy as np

        a = np.asarray(reference.convert("RGB"), dtype=np.int16)
        b = np.asarray(output.convert("RGB").resize(reference.size), dtype=np.int16)
        diff = np.abs(b - a)
        pixel_change = float(diff.mean())
        stddev = float(b.std())
        verdict = {
            "PASS": pixel_change > 1.5 and stddev > 10.0,
            "metric_pixel_change": round(pixel_change, 3),
            "metric_stddev": round(stddev, 3),
            "no_echo": pixel_change > 0.5,
            "not_blank": stddev > 10.0,
        }
        return verdict

    # -- inference ---------------------------------------------------------------

    def render(
        self,
        person_image: Image.Image,
        garment_image: Image.Image | None = None,
        *,
        category: str | None = None,
        garments: List[Dict[str, Any]] | None = None,
        seed: int = 42,
        num_timesteps: int = 30,
        **kwargs: Any,
    ) -> Image.Image:
        """Base-contract single try-on: returns just the final image."""
        image, _layers = self.render_outfit(
            person_image,
            garment_image=garment_image,
            category=category,
            garments=garments,
            seed=seed,
            num_timesteps=num_timesteps,
            **kwargs,
        )
        return image

    def render_outfit(
        self,
        person_image: Image.Image,
        garment_image: Image.Image | None = None,
        *,
        category: str | None = None,
        garments: List[Dict[str, Any]] | None = None,
        seed: int = 42,
        num_timesteps: int = 30,
        overlay_mode: str = "masked",
    ) -> Tuple[Image.Image, List[Dict[str, Any]]]:
        """Compose a multi-garment outfit onto ``person_image``.

        Layer 1 renders segmentation-free (upstream-recommended: unconstrained
        garment volume, nothing applied yet to preserve). Layer k>1 masks ONLY
        its own body region via the parser (``overlay_mode='masked'``) so
        earlier layers stay pixel-exact; ``overlay_mode='segfree'`` falls back
        to full regeneration per layer (tunable, evidence-driven choice).

        Returns ``(final_image, layers_meta)`` where layers_meta carries the
        honest per-layer verification the backend reports to the user.
        """
        if not self._ready:
            raise RuntimeError("engine not loaded; call load() first")
        if overlay_mode not in ("masked", "segfree"):
            raise ValueError(f"overlay_mode must be 'masked' or 'segfree', got {overlay_mode!r}")

        items = self.normalize_garments(
            garments if garments else [{"image": garment_image, "category": category}]
        )

        import numpy as np

        current = person_image.convert("RGB")
        layers_meta: List[Dict[str, Any]] = []

        for idx, g in enumerate(items):
            garment = g["image"].convert("RGB")
            photo_type = g.get("photo_type")
            if photo_type:
                photo_detector = "explicit"
            else:
                # Anti-contamination gate: two independent detectors decide
                # worn vs flat-lay so a model photo's PERSON never bleeds
                # into the composition (see classify_garment_photo).
                photo_type, photo_evidence = self.classify_garment_photo(garment)
                photo_detector = photo_evidence.get("detector")

            layer_person = current
            segmentation_free = True if idx == 0 else (overlay_mode == "segfree")

            out = self._pipe(
                person_image=layer_person,
                garment_image=garment,
                category=g["category"],
                garment_photo_type=photo_type,
                segmentation_free=segmentation_free,
                num_timesteps=num_timesteps,
                seed=seed,
            )
            rendered = out.images[0].convert("RGB")

            verdict = self.validate_output(rendered, layer_person)
            layers_meta.append(
                {
                    "layer": idx + 1,
                    "category": g["category"],
                    "slot_type": g.get("slot_type"),
                    "product_id": g.get("product_id"),
                    "photo_type": photo_type,
                    "photo_type_detector": photo_detector,
                    "segmentation_free": segmentation_free,
                    "verify": verdict,
                }
            )
            if not verdict["PASS"]:
                # Honest failure: a layer that did not materially change the
                # image was NOT applied — do not keep compositing on top of it.
                raise RuntimeError(
                    f"layer {idx + 1} ({g['category']}) failed output verification: {verdict}"
                )
            current = rendered

        return current, layers_meta

    def _safe_predict(self, image: Image.Image) -> Any:
        """Parser prediction that degrades to None (flat-lay default) instead
        of failing the whole job — the parser is an enhancer, not a gate."""
        try:
            import numpy as np

            return self._parser_model.predict(np.asarray(image))
        except Exception:
            return None

    # -- metadata ------------------------------------------------------------

    def metadata(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "model": "fashn-vton-v1.5 (MMDiT 972M, pristine upstream 7c0f10af)",
            "revision": self.model_revision,
            "license": self.license_summary,
            "commercial": self.commercially_usable,
            "parser": {
                "model": "fashn-ai/fashn-human-parser (SegFormer fine-tune)",
                "license": "NVIDIA Source Code License for SegFormer (non-commercial)",
                "owner_decision": "approved for early-stage use 2026-10-01; "
                "licensed swap planned before commercial scale",
                "swappable_via": "FashnV15MultiGarmentEngine(parser_impl=...)",
            },
            "multigarment": True,
            "max_garments": MAX_GARMENTS,
            "garment_photo_types": ["flat-lay", "model"],
        }
