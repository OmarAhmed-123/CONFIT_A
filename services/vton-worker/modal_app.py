# ==============================================================================
# CONFIT VTON GPU WORKER — Modal.com Serverless GPU Deployment
# Hardware: NVIDIA A10G (24GB VRAM) / L4 (24GB VRAM)
# ==============================================================================

import modal
from pydantic import BaseModel
from typing import List, Dict, Any

app = modal.App("confit-vton-worker")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch>=2.4.0",
        "torchvision>=0.19.0",
        "diffusers>=0.30.0",
        "transformers>=4.44.0",
        "accelerate>=0.33.0",
        "Pillow>=10.4.0",
        "numpy>=1.26.0",
        "rembg>=2.0.57",
        "fastapi>=0.115.0",
        "pydantic>=2.9.0"
    )
)


class VTONJobRequest(BaseModel):
    job_id: str
    user_image_base64_or_url: str
    garments: List[Dict[str, Any]]
    gender_mode: str = "infer_from_image"
    output_aspect: str = "9:16"


@app.cls(gpu="A10G", image=image, container_idle_timeout=300)
class VTONInferenceService:
    @modal.enter()
    def load_model(self):
        # HONEST STATUS: no CatVTON weights are loaded yet (Phase 3 of the VTON
        # remediation plan: bake Zheng-Chong/CatVTON weights into the image and
        # load the pipeline here). A flag alone loads nothing.
        self.model_loaded = False

    @modal.fastapi_endpoint(method="POST")
    def process(self, payload: VTONJobRequest) -> dict:
        # Never echo the input back as a "completed" render with fabricated
        # metrics. Until the real diffusion pipeline is loaded in load_model(),
        # every request fails truthfully with 503 VTON_ENGINE_UNAVAILABLE.
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "VTON_ENGINE_UNAVAILABLE",
                    "message": "GPU worker is deployed but no diffusion model is loaded yet.",
                    "details": {"reason": "model_weights_not_loaded"},
                }
            },
        )
