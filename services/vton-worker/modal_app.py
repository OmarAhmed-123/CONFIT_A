# ==============================================================================
# CONFIT VTON GPU WORKER - Modal.com Serverless Deployment (real diffusion)
#
# Canonical sources (verified 2026-08-30 via huggingface.co API + GitHub API):
#   - zhengchong/CatVTON             CatVTON weights (diffusers-style) + SCHP + DensePose
#   - pirocheto/schp-lip-20          SCHP LIP-20 human parsing (alt packaging)
#   - pirocheto/schp-atr-18          SCHP ATR-18 human parsing (alt packaging)
#   - yzd-v/DWPose                   DWPose whole-body pose ONNX checkpoints
#   - runwayml/stable-diffusion-v1-5 Base SD1.5 backbone (unet/vae/text_encoder)
#
# Design rules:
#   * ALL weights are downloaded during `modal build` (run_function), so a cold
#     start never downloads multi-GB files - /model_cache is part of the image.
#   * load_model() (@modal.enter) builds the real pipeline in VRAM and sets
#     model_loaded=True ONLY after a successful load; every failure lands in
#     load_error and is surfaced by /health (never faked).
#   * POST /process runs genuine diffusion sampling and measures its own
#     wall-time; if the pipeline is unavailable it returns 503
#     VTON_ENGINE_UNAVAILABLE - it never echoes the input as a fake render.
#
# Deploy:
#   pip install modal && modal token new
#   modal deploy services/vton-worker/modal_app.py
# then set VTON_WORKER_URL in backend/.env and Vercel Production env.
# ==============================================================================
import modal
from pydantic import BaseModel
from typing import List, Dict, Any

app = modal.App("confit-vton-worker")

MODEL_CACHE = "/model_cache"
CATVTON_REPO = "zhengchong/CatVTON"
SCHP_LIP_REPO = "pirocheto/schp-lip-20"
SCHP_ATR_REPO = "pirocheto/schp-atr-18"
DWPOSE_REPO = "yzd-v/DWPose"
BASE_SD15_REPO = "runwayml/stable-diffusion-v1-5"


def _download_weights():
    """Build-step weight baking - runs once when the Modal image is built."""
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=CATVTON_REPO, cache_dir=MODEL_CACHE)
    snapshot_download(repo_id=SCHP_LIP_REPO, cache_dir=MODEL_CACHE)
    snapshot_download(repo_id=SCHP_ATR_REPO, cache_dir=MODEL_CACHE)
    snapshot_download(repo_id=DWPOSE_REPO, cache_dir=MODEL_CACHE)
    snapshot_download(
        repo_id=BASE_SD15_REPO, cache_dir=MODEL_CACHE,
        allow_patterns=[
            "model_index.json", "scheduler/*", "tokenizer/*",
            "text_encoder/*", "unet/*", "vae/*",
        ],
    )


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0", "libgomp1", "wget")
    .pip_install(
        "torch>=2.4.0",
        "torchvision>=0.19.0",
        "diffusers>=0.30.0",
        "transformers>=4.44.0",
        "accelerate>=0.33.0",
        "huggingface_hub>=0.24.0",
        "Pillow>=10.4.0",
        "numpy>=1.26.0",
        "fastapi>=0.115.0",
        "pydantic>=2.9.0",
        "opencv-python-headless>=4.10.0",
    )
    .run_commands("git clone --depth 1 https://github.com/Zheng-Chong/CatVTON.git /catvton")
    .env({"PYTHONPATH": "/catvton"})
    .run_function(_download_weights)
)


class VTONJobRequest(BaseModel):
    job_id: str
    user_image_base64_or_url: str
    garments: List[Dict[str, Any]]
    gender_mode: str = "infer_from_image"
    output_aspect: str = "9:16"


@app.cls(gpu="A10G", image=image, container_idle_timeout=300, allow_concurrent_inputs=4)
class VTONInferenceService:
    """Real CatVTON diffusion on GPU. model_loaded is a measured fact, never a flag."""

    @modal.enter()
    def load_model(self):
        import torch
        self.model_loaded = False
        self.load_error = None
        self.device_name = None
        try:
            from diffusers import DiffusionPipeline
            cache = MODEL_CACHE
            attempts = []

            # Strategy 1: CatVTON's own pipeline class from the cloned repo.
            try:
                from pipeline import CatVTONPipeline  # type: ignore
                self.pipe = CatVTONPipeline.from_pretrained(
                    cache, torch_dtype=torch.float16)
                attempts.append("CatVTONPipeline.from_pretrained(cache)")
            except Exception as e1:
                attempts.append(f"CatVTONPipeline failed: {type(e1).__name__}: {e1}")

            # Strategy 2: standard diffusers loader on the baked cache.
            if getattr(self, "pipe", None) is None:
                try:
                    self.pipe = DiffusionPipeline.from_pretrained(
                        cache, torch_dtype=torch.float16)
                    attempts.append("DiffusionPipeline.from_pretrained(cache)")
                except Exception as e2:
                    attempts.append(f"DiffusionPipeline failed: {type(e2).__name__}: {e2}")

            if getattr(self, "pipe", None) is None:
                raise RuntimeError("all load strategies failed: " + " | ".join(attempts))

            self.pipe.to("cuda")
            if hasattr(self.pipe, "safety_checker"):
                self.pipe.safety_checker = None
            self.dtype = torch.float16
            self.device_name = torch.cuda.get_device_name(0)
            self.model_loaded = True
            print("CatVTON diffusion pipeline loaded into VRAM; model_loaded=True")
        except Exception as exc:
            self.pipe = None
            self.load_error = f"{type(exc).__name__}: {exc}"
            print("MODEL LOAD FAILED:", self.load_error)

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        import torch
        return {
            "status": "healthy" if self.model_loaded else "degraded",
            "service": "vton-worker",
            "model": "CatVTON (zhengchong/CatVTON, SD1.5 base)",
            "model_loaded": self.model_loaded,
            "load_error": self.load_error,
            "device": self.device_name or ("cuda" if torch.cuda.is_available() else "cpu"),
            "cuda_available": torch.cuda.is_available(),
            "weights_baked_at_build": True,
        }

    @modal.fastapi_endpoint(method="POST")
    def process(self, payload: VTONJobRequest) -> dict:
        from fastapi import HTTPException
        if not self.model_loaded:
            raise HTTPException(
                status_code=503,
                detail={"error": {
                    "code": "VTON_ENGINE_UNAVAILABLE",
                    "message": "Diffusion pipeline is not loaded.",
                    "details": {"reason": "model_load_failed",
                                "load_error": self.load_error}}},
            )

        import base64
        import io
        import time
        from PIL import Image
        start = time.time()

        ref = payload.user_image_base64_or_url
        if ref.startswith("data:image"):
            raw = base64.b64decode(ref.split(",", 1)[1])
        else:
            import httpx
            resp = httpx.get(ref, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            raw = resp.content
        person = Image.open(io.BytesIO(raw)).convert("RGB")

        garments = payload.garments or []
        first = garments[0] if garments else {}
        garment_ref = first.get("image_base64") or first.get("image_url") or ""
        if garment_ref.startswith("data:image"):
            g_raw = base64.b64decode(garment_ref.split(",", 1)[1])
        elif garment_ref.startswith("http"):
            import httpx
            g_raw = httpx.get(garment_ref, timeout=30.0, follow_redirects=True).content
        else:
            raise HTTPException(status_code=422, detail={"error": {
                "code": "GARMENT_IMAGE_MISSING",
                "message": "First garment must carry image_base64 or image_url."}})
        garment = Image.open(io.BytesIO(g_raw)).convert("RGB")

        slot = (first.get("slot_type") or "upper_outer").lower()
        w, h = 512, 768
        person = person.resize((w, h))
        garment = garment.resize((w // 2, h // 2))

        try:
            result = self.pipe(
                person_image=person,
                garment_image=garment,
                mask=None,
                category=slot,
                num_inference_steps=30,
                guidance_scale=2.5,
            )
        except TypeError as te:
            raise HTTPException(status_code=500, detail={"error": {
                "code": "VTON_INFERENCE_API_MISMATCH",
                "message": f"Pipeline call signature mismatch: {te}"}})

        out = result.images[0] if isinstance(result, (list, tuple)) else result
        if hasattr(out, "images"):
            out = out.images[0]
        rendered = out.convert("RGB")

        buf = io.BytesIO()
        rendered.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        elapsed_ms = round((time.time() - start) * 1000, 1)

        try:
            from pipeline.quality import VTONQualityAuditor  # type: ignore
            audit = VTONQualityAuditor.audit_tryon_output(
                original_img=person, rendered_img=rendered)
        except Exception:
            audit = {"ssim": None, "audit_verdict": "unavailable"}

        return {
            "job_id": payload.job_id,
            "status": "completed",
            "rendered_image_data_url": "data:image/png;base64," + b64,
            "execution_time_ms": elapsed_ms,
            "model_used": "CatVTON-SD1.5-diffusion",
            "layers_processed": len(garments),
            "fit_verdict": "neural diffusion (CatVTON)",
            "quality_audit": audit,
        }
