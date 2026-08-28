import time
import numpy as np
from PIL import Image
from typing import List, Optional
from pydantic import BaseModel
from .segmentation import AgnosticMaskGenerator
from .pose import BodyLandmarks
from .garment import GarmentAssetPack


class VTONInferenceResult(BaseModel):
    rendered_image: Image.Image
    model_name: str
    inference_time_seconds: float
    fit_verdict: str
    # Quality metrics are NOT produced here. They are measured on the actual
    # output by pipeline.quality.VTONQualityAuditor — never hard-coded.
    ssim_score: Optional[float] = None
    identity_preservation_score: Optional[float] = None
    layers_applied: List[str]

    class Config:
        arbitrary_types_allowed = True


class CatVTONDiffusionEngine:
    """Stage 4: garment compositing engine.

    HONEST STATUS: this is a masked-alpha-composite placeholder, not the
    CatVTON diffusion model — no UNet/VAE/scheduler weights are loaded.
    It exists so the worker pipeline is exercisable end-to-end; replacing it
    with real CatVTON inference is the Phase-3 work tracked in the VTON
    remediation plan. Until then, quality scores come only from real
    measurement (pipeline/quality.py) and fit claims are reported as
    not measured.
    """

    def __init__(self, device: str = "cpu", model_weights_path: Optional[str] = None):
        self.device = device
        self.model_weights_path = model_weights_path or "weights/CatVTON-v1.2-fp16"
        # No weights are loaded in this placeholder implementation.
        self.model_loaded = False

    def run_vton_inference(
        self,
        person_image: Image.Image,
        garment_image: Image.Image,
        garment_mask: Image.Image,
        slot_type: str,
        pose_landmarks: BodyLandmarks,
        garment_meta: Optional[GarmentAssetPack] = None,
        num_inference_steps: int = 25,
        guidance_scale: float = 2.5
    ) -> VTONInferenceResult:
        """Executes CatVTON spatial-concatenation diffusion inpainting."""
        start_time = time.time()
        w, h = person_image.size

        # 1. Build Clothing-Agnostic Inpainting Mask
        agnostic_mask = AgnosticMaskGenerator.create_agnostic_mask(person_image, slot_type)

        # 2. Deform and wrap garment tensor conditioned on shoulder angle and body landmarks
        angle = pose_landmarks.shoulder_angle_deg
        # Rotate garment slightly to match shoulder slant
        rotated_garment = garment_image.rotate(-angle, resample=Image.BICUBIC, expand=False)

        # Fit the garment into the masked region's bounding box — NOT the full
        # person frame (previously the catalogue thumbnail was stretched over
        # the entire photo and then masked, producing an unfitted paste).
        bbox = agnostic_mask.getbbox()
        if bbox:
            bw, bh = max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])
            garment_fitted = rotated_garment.resize((bw, bh), Image.Resampling.LANCZOS)
            garment_resized = Image.new("RGB", (w, h))
            garment_resized.paste(garment_fitted, (bbox[0], bbox[1]))
        else:
            garment_resized = rotated_garment.resize((w, h), Image.Resampling.LANCZOS)

        # 3. Masked composite: preserve untouched regions (face, hair,
        # background, arms) from the raw user photo, blend the fitted garment
        # into the agnostic region only.
        person_rgb = person_image.convert("RGB")
        mask_np = np.array(agnostic_mask) / 255.0
        mask_3d = np.repeat(mask_np[:, :, np.newaxis], 3, axis=2)

        person_np = np.array(person_rgb, dtype=np.float32)
        garment_np = np.array(garment_resized.convert("RGB"), dtype=np.float32)

        composite_np = person_np * (1.0 - mask_3d) + garment_np * mask_3d
        composite_img = Image.fromarray(np.clip(composite_np, 0, 255).astype(np.uint8))

        exec_time = time.time() - start_time

        return VTONInferenceResult(
            rendered_image=composite_img,
            model_name="masked-composite-placeholder",
            inference_time_seconds=round(exec_time, 3),
            # No fit measurement is performed by this engine — say so.
            fit_verdict="Not Measured (composite placeholder, no diffusion model)",
            layers_applied=[slot_type]
        )
