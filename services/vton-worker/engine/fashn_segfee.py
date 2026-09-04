"""FASHN segmentation-free VTON engine adapter.

Wraps the CONFIT_A fork `fashn-vton-segfee` (a segmentation-free-only fork of
`fashn-AI/fashn-vton-1.5`, which removes the non-commercial human-parser from
the runtime). The adapter:

  * never imports `fashn_human_parser` (the fork guarantees this),
  * enforces single-category semantics (never naive multi-garment compositing),
  * enforces segmentation-free + flat-lay (the fork's safe operating envelope),
  * validates output (no echo, not blank, real change).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from PIL import Image

from .base import VTONEngine


class FashnSegfeeVTONEngine(VTONEngine):
    name = "fashn_vton_segfee"
    model_revision = "fashn-AI/fashn-vton-1.5 @ 7c0f10af (fork: vendor/fashn-vton-segfee)"
    license_summary = "Apache-2.0 (model/DWPose/YOLOX); fashn-human-parser removed"
    commercially_usable = True
    supports_multigarment = False  # single-category per call — never naive-composite

    _VENDOR_PATH = "/root/fashn-vton-segfee"

    def __init__(self, weights_dir: str, device: str = "cuda", **kwargs: Any) -> None:
        self._weights_dir = weights_dir
        self._device = device
        self._pipe: Any = None
        self._load_error: str | None = None

    def load(self) -> None:
        """Load the segmentation-free pipeline onto the device.

        The parser is provably absent: the fork never imports `fashn_human_parser`
        at any point (see vendor/fashn-vton-segfee + its tests).
        """
        try:
            from fashn_vton import TryOnPipeline  # type: ignore  # vendored fork

            self._pipe = TryOnPipeline(weights_dir=self._weights_dir, device=self._device)
        except Exception as e:  # keep the worker's honest VTON_ENGINE_UNAVAILABLE semantics
            self._load_error = f"{type(e).__name__}: {e}"
            raise

    @property
    def _ready(self) -> bool:
        return self._pipe is not None

    def validate_inputs(self, person_image: Image.Image, garment_image: Image.Image, category: str) -> None:
        super().validate_inputs(person_image, garment_image, category)
        if category not in {"tops", "bottoms", "one-pieces"}:
            raise ValueError(
                f"fashn_vton_segfee supports category in {{tops, bottoms, one-pieces}}, got {category!r}"
            )

    def render(
        self,
        person_image: Image.Image,
        garment_image: Image.Image,
        *,
        category: Literal["tops", "bottoms", "one-pieces"] = "tops",
        garments: List[Dict[str, Any]] | None = None,
        seed: int = 42,
        num_timesteps: int = 30,
        **kwargs: Any,
    ) -> Image.Image:
        if not self._ready:
            raise RuntimeError("engine not loaded; call load() first")
        if garments:
            # Refuse naive multi-garment compositing rather than pretend it works.
            if len(garments) > 1:
                raise ValueError(
                    "fashn_vton_segfee is single-category. Provide exactly one "
                    "garment per job; no naive multi-garment stacking."
                )
        out = self._pipe(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            garment_photo_type="flat-lay",  # fork enforces flat-lay (no parser)
            segmentation_free=True,  # fork enforces segmentation-free (no parser)
            num_timesteps=num_timesteps,
            seed=seed,
        )
        return out.images[0].convert("RGB")
