"""Abstract VTON engine contract.

This is the single canonical interface the worker uses to talk to an engine.
It intentionally contains NO business logic (storage/auth/DB/frontend live
outside the engine and are never duplicated here).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal

from PIL import Image


class VTONEngine(ABC):
    """Base class for a CONFIT VTON engine.

    A subclass runs ONE model. It must never reach the network for the storage
    layer, never authenticate, and never assume it knows how many garments the
    caller intends to composite — multi-garment handling is decided by the
    worker from a whitelist of supported semantics (see ``supports_multigarment``).
    """

    name: str = "unnamed"
    model_revision: str = ""
    license_summary: str = ""
    commercially_usable: bool = False

    @property
    def supports_multigarment(self) -> bool:
        """Whether this engine can composite *arbitrary* multi-garment outfits.

        FASHN/Leffa are single-category per call, so CONFIT must never naively
        stack them. Override to ``False`` for such engines.
        """
        return False

    @abstractmethod
    def load(self) -> None:
        """Load model weights onto the device. Raises on failure (never masks)."""

    @abstractmethod
    def render(
        self,
        person_image: Image.Image,
        garment_image: Image.Image,
        *,
        category: Literal["tops", "bottoms", "one-pieces"],
        garments: List[Dict[str, Any]] | None = None,
        seed: int = 42,
        num_timesteps: int = 30,
        **kwargs: Any,
    ) -> Image.Image:
        """Run one try-on and return a single RGB PIL image."""

    def validate_inputs(self, person_image: Image.Image, garment_image: Image.Image, category: str) -> None:
        """Prepare/validate inputs. Raise ValueError on unsupported input.

        Default: nothing to check beyond image presence. Subclasses over-ride.
        """
        if person_image is None or garment_image is None:
            raise ValueError("person_image and garment_image are required")

    def validate_output(self, original: Image.Image, rendered: Image.Image) -> Dict[str, Any]:
        """Validate a rendered image is a genuine try-on, not an echo/blank.

        Returns a metrics dict. ``PASS`` is True only if EVERY metric passes.
        """
        import numpy as np

        a = np.asarray(original.convert("RGB"), dtype=np.int16)
        b = np.asarray(rendered.convert("RGB"), dtype=np.int16)
        if b.shape[:2] != a.shape[:2]:
            # different size -> resize for comparison
            b = np.asarray(rendered.convert("RGB").resize(original.size), dtype=np.int16)
        diff = np.abs(b - a)
        pixel_change = float(diff.mean())
        color_shift = float(np.linalg.norm(diff.mean(axis=(0, 1)))) / 255.0
        # blank image guard (very low stddev across channels)
        stddev = float(b.std())
        metrics = {
            "pixel_change_mean": round(pixel_change, 4),
            "color_shift": round(color_shift, 6),
            "image_stddev": round(stddev, 2),
            "PASS": bool(pixel_change >= 1.0 and color_shift > 0.005 and stddev > 5.0),
        }
        return metrics

    def metadata(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "model_revision": self.model_revision,
            "license": self.license_summary,
            "commercial": self.commercially_usable,
            "supports_multigarment": self.supports_multigarment,
        }
