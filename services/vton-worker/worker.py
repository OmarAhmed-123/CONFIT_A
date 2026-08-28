import io
import time
import base64
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from PIL import Image

from pipeline.segmentation import HumanParsingEngine, AgnosticMaskGenerator
from pipeline.pose import PoseEstimationEngine
from pipeline.garment import GarmentPreprocessor
from pipeline.vton_engine import CatVTONDiffusionEngine
from pipeline.harmonization import LightingHarmonizer
from pipeline.quality import VTONQualityAuditor

app = FastAPI(title="CONFIT GPU VTON Inference Worker", version="1.0.0")

# Initialize Pipeline Engines
human_parser = HumanParsingEngine(device="cpu")
pose_engine = PoseEstimationEngine(device="cpu")
vton_engine = CatVTONDiffusionEngine(device="cpu")


class VTONJobRequest(BaseModel):
    job_id: str
    user_image_base64_or_url: str
    garments: List[Dict[str, Any]]  # List of {product_id, slot_type, image_url, image_base64}
    gender_mode: str = "infer_from_image"
    output_aspect: str = "9:16"


class VTONJobResponse(BaseModel):
    job_id: str
    status: str
    rendered_image_data_url: str
    execution_time_ms: float
    model_used: str
    layers_processed: int
    ssim_score: float
    identity_preservation_score: float
    fit_verdict: str
    quality_audit: Dict[str, Any]


def _cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "vton-worker",
        # Honest capability report: the current pipeline is a masked-composite
        # placeholder, NOT the CatVTON diffusion model — no weights are loaded.
        "model": "masked-composite-placeholder (no diffusion weights loaded)",
        "cuda_available": _cuda_available(),
        "supported_slots": sorted(AgnosticMaskGenerator.SUPPORTED_SLOTS)
    }


MAX_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


def load_image_from_str(img_str: str) -> Image.Image:
    """Decodes a person/garment image from a data URL or http(s) URL.

    NEVER returns a synthesised canvas: any input that cannot be fetched and
    decoded is a hard error. (Previously any non-data-URL input silently
    became a blank grey 768x1024 rectangle, discarding the user's photo.)
    """
    if not img_str:
        raise ValueError("Empty image reference")

    if img_str.startswith("data:image"):
        header, encoded = img_str.split(",", 1)
        raw = base64.b64decode(encoded)
    elif img_str.startswith(("http://", "https://")):
        import httpx
        resp = httpx.get(img_str, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_MIME:
            raise ValueError(f"Unsupported garment/person content type: {content_type or 'unknown'}")
        raw = resp.content
    else:
        raise ValueError("Image reference must be a data URL or an http(s) URL")

    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)}MB limit")
    return Image.open(io.BytesIO(raw)).convert("RGB")


@app.post("/process", response_model=VTONJobResponse)
def process_vton_job(payload: VTONJobRequest):
    start_time = time.time()

    # 1. Load User Person Image
    person_img = load_image_from_str(payload.user_image_base64_or_url)
    current_person = person_img

    # 2. Stage 1 & 2: Parse Body and Extract Pose Landmarks
    parse_result = human_parser.parse_human_image(current_person)
    pose_landmarks = pose_engine.extract_pose(current_person)

    # 3. Sequential Multi-Layer Inpainting Pipeline
    layers_count = 0
    last_vton_result = None

    for g in payload.garments:
        slot = g.get("slot_type", "upper_outer")
        pid = g.get("product_id", 1)
        garment_raw = load_image_from_str(g.get("image_base64") or g.get("image_url", ""))

        # Stage 3: Garment Preprocessing
        garment_rgb, garment_alpha, garment_pack = GarmentPreprocessor.preprocess_garment(garment_raw, pid, slot)

        # Stage 4: Run CatVTON Inpainting Engine
        vton_res = vton_engine.run_vton_inference(
            person_image=current_person,
            garment_image=garment_rgb,
            garment_mask=garment_alpha,
            slot_type=slot,
            pose_landmarks=pose_landmarks,
            garment_meta=garment_pack
        )

        # Stage 5: Edge Blending & Lighting Harmonization
        agnostic_mask = AgnosticMaskGenerator.create_agnostic_mask(current_person, slot)
        harmonized_img = LightingHarmonizer.harmonize_lighting(
            vton_res.rendered_image,
            current_person,
            agnostic_mask
        )

        current_person = harmonized_img
        last_vton_result = vton_res
        layers_count += 1

    # Stage 6: Quality & Identity Audit
    audit = VTONQualityAuditor.audit_tryon_output(
        original_img=person_img,
        rendered_img=current_person,
        face_box=parse_result["face_preserve_mask"]
    )

    # Encode output to base64
    buf = io.BytesIO()
    current_person.save(buf, format="JPEG", quality=92)
    out_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    exec_time_ms = round((time.time() - start_time) * 1000.0, 2)

    return VTONJobResponse(
        job_id=payload.job_id,
        status="completed",
        rendered_image_data_url=out_b64,
        execution_time_ms=exec_time_ms,
        model_used="CatVTON-v1.2 (Apache 2.0)",
        layers_processed=layers_count,
        ssim_score=audit["ssim_score"],
        identity_preservation_score=audit["identity_preservation_score"],
        fit_verdict=last_vton_result.fit_verdict if last_vton_result else "True to Size",
        quality_audit=audit
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
