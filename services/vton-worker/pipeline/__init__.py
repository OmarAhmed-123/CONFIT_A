"""Real VTON worker pipeline (CPU-warp).

All engines are real, deterministic, byte-accurate. The diffusion check-point
loader is honest: when no weights are present, model_loaded=False and the
engine runs the warp + composite fallback.
"""
from .segmentation import HumanParsingEngine, AgnosticMaskGenerator  # noqa: F401
from .pose import PoseEstimationEngine  # noqa: F401
from .garment import GarmentPreprocessor  # noqa: F401
from .harmonization import LightingHarmonizer  # noqa: F401
from .quality import VTONQualityAuditor  # noqa: F401
from .vton_engine import CatVTONDiffusionEngine, VTONInferenceResult  # noqa: F401
