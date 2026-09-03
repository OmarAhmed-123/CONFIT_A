"""Canonical VTON worker pipeline modules.

SINGLE authoritative masking implementation for CONFIT_A VTON.

`segmentation` is imported by the production Modal entrypoint
(`modal_app.py::_make_slot_mask`) and is the only masking code path that runs
in production.

Historical note (final release gate): this package previously also exported
`CatVTONDiffusionEngine`, `PoseEstimationEngine`, `LightingHarmonizer` and
`VTONQualityAuditor`, which together with `worker.py` formed a SECOND,
CPU-only "geometric warp + composite" VTON implementation. That implementation
performed no diffusion, yet returned `status="completed"`, and the service
Dockerfile launched it via `CMD ["python", "worker.py"]`. It has been removed
so that exactly one VTON implementation exists and no placeholder engine can
be reached from any deployment path.
"""

from .segmentation import HumanParsingEngine, AgnosticMaskGenerator  # noqa: F401
from .garment import GarmentPreprocessor  # noqa: F401

__all__ = ["HumanParsingEngine", "AgnosticMaskGenerator", "GarmentPreprocessor"]
