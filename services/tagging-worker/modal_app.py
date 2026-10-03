"""Feature 07 — CONFIT product auto-tagging worker on Modal (CPU).

App `confit-tagging-worker` — the ONE app for the tagging capability
(no duplicates; one Modal app per capability is a standing constraint).

Models (both CPU-friendly, both commercial-safe):
  * FashionCLIP  patrickjohncyh/fashion-clip   (MIT)          ViT-B/32
  * GLiNER v2.1  urchade/gliner_multi-v2.1     (Apache-2.0)   289M multilingual

Endpoints (same shell contract as the other CONFIT workers):
  GET  /health    — model/load status, no auth
  GET  /readiness — ready flag for probes, no auth
  POST /tag       — X-VTON-Admin shared secret (Modal secret
                    `confit-tagging-admin-token`, env TAGGING_WORKER_ADMIN_TOKEN)

Request:  {job_id, image_base64_or_url?, title?, description?,
           title_ar?, description_ar?}
Response: honest tagging contract — see tagging_core.ProductTagger.tag().
          Refusals raise 422 with {detail:{error:{code,message}}}.

Cold start: both models load at container start (~20-40s CPU, weights are
baked into the image so no runtime downloads); calls are ~1-3s. Scaled to
zero between calls — no idle burn.
"""
from __future__ import annotations

import base64
import binascii
import os
import time
import urllib.request
from typing import Optional

import modal
from fastapi import HTTPException, Header
from pydantic import BaseModel, field_validator

_HERE = os.path.dirname(os.path.abspath(__file__))


def _bake_models():
    """Bake both models' weights into the image (runs once at image build,
    so container cold starts never download ~1.7GB from HuggingFace)."""
    from transformers import CLIPModel, CLIPProcessor
    from gliner import GLiNER

    CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")
    CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")
    GLiNER.from_pretrained("urchade/gliner_multi-v2.1")


_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # CPU-only torch wheel (small, no CUDA payload). Versions are the
        # exact set validated on the reference host (2026-10-03): torch cpu
        # 2.14.1 + transformers 5.16.1 + gliner 0.2.29 run FashionCLIP and
        # gliner_multi-v2.1 correctly together.
        "torch==2.14.1",
        "transformers==5.16.1",
        "pillow>=10.4.0",
        "gliner==0.2.29",
        "numpy>=1.26,<3",
        "fastapi>=0.115.0",
        "pydantic>=2.9.0",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .run_function(_bake_models)
    .add_local_dir(_HERE, remote_path="/root/tagging-worker", copy=True)
    .env({"PYTHONPATH": "/root/tagging-worker:"})
)

app = modal.App("confit-tagging-worker", image=_image)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
VALID_MIMES = {"image/jpeg", "image/png", "image/webp"}


class TagRequest(BaseModel):
    job_id: str
    image_base64_or_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    title_ar: Optional[str] = None
    description_ar: Optional[str] = None

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("job_id must be 1-100 chars")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("job_id contains invalid characters")
        return v

    @field_validator("image_base64_or_url")
    @classmethod
    def validate_image(cls, v):
        if v is None:
            return v
        if len(v) > 25_000_000:  # ~18MB binary after base64 inflation
            raise ValueError("image payload too large")
        return v


def _fetch_image(spec: Optional[str]) -> Optional[bytes]:
    """Resolve the image spec (data: URL or http(s) URL) to raw bytes."""
    if not spec:
        return None
    s = str(spec)
    if s.startswith("data:"):
        header, _, b64 = s.partition(",")
        mime = header[5:].split(";")[0].strip().lower()
        if mime not in VALID_MIMES:
            raise HTTPException(422, detail={"error": {
                "code": "INVALID_IMAGE",
                "message": f"Unsupported image type '{mime}'. Use JPEG, PNG or WebP."}})
        try:
            blob = base64.b64decode(b64, validate=False)
        except (binascii.Error, ValueError):
            raise HTTPException(422, detail={"error": {
                "code": "INVALID_IMAGE", "message": "The image data URL is not valid base64."}})
        if len(blob) > MAX_IMAGE_BYTES:
            raise HTTPException(422, detail={"error": {
                "code": "IMAGE_TOO_LARGE", "message": "Image exceeds the 15MB limit."}})
        return blob
    if s.startswith(("http://", "https://")):
        req = urllib.request.Request(s, headers={"User-Agent": "confit-tagging-worker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                blob = r.read(MAX_IMAGE_BYTES + 1)
        except Exception:
            raise HTTPException(422, detail={"error": {
                "code": "IMAGE_FETCH_FAILED",
                "message": "The image URL could not be fetched. Check it is public."}})
        if len(blob) > MAX_IMAGE_BYTES:
            raise HTTPException(422, detail={"error": {
                "code": "IMAGE_TOO_LARGE", "message": "Image exceeds the 15MB limit."}})
        return blob
    raise HTTPException(422, detail={"error": {
        "code": "INVALID_IMAGE",
        "message": "image_base64_or_url must be a data: URL or an http(s) URL."}})


@app.cls(
    image=_image,
    # GLiNER multi-v2.1 (289M, F32 ≈1.2GB) + FashionCLIP ViT-B/32 + torch
    # runtime ≈ 3GB RSS. 4GB headroom avoids the OOM the 2GB reference
    # host hit; CPU-only, still far cheaper than any GPU minute.
    cpu=2.0,
    memory=4096,
    scaledown_window=300,
    secrets=[modal.Secret.from_name("confit-tagging-admin-token")],
    timeout=120,
)
class ProductTaggingService:
    @modal.enter()
    def load(self):
        import tagging_core

        self.core = tagging_core
        self.tagger = tagging_core.ProductTagger()
        self.load_error = None
        t0 = time.time()
        try:
            self.tagger.load()
        except Exception as exc:  # pragma: no cover - surfaced via /health
            self.load_error = str(exc)[:300]
        self.load_seconds = round(time.time() - t0, 1)
        self.ready = self.tagger.models_loaded

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        return {
            "status": "healthy" if self.ready else "degraded",
            "service": "tagging-worker",
            "models": {
                "fashionclip": "patrickjohncyh/fashion-clip (MIT, ViT-B/32)",
                "gliner": "urchade/gliner_multi-v2.1 (Apache-2.0, 289M multilingual)",
            },
            "models_loaded": self.ready,
            "load_error": self.load_error,
            "device": "cpu",
            "commercial": True,
            "engine": "fashionclip_gliner2_cpu",
            "load_seconds": self.load_seconds,
            "ready": self.ready,
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="GET")
    def readiness(self) -> dict:
        if not self.ready:
            raise HTTPException(503, detail={
                "error": {"code": "TAGGING_NOT_READY", "message": "Models not loaded",
                          "load_error": self.load_error},
                "ready": False})
        return {"ready": True, "engine": "fashionclip_gliner2_cpu"}

    @modal.fastapi_endpoint(method="POST")
    def tag(self, payload: TagRequest,
            x_vton_admin: Optional[str] = Header(None, alias="X-VTON-Admin")) -> dict:
        expected = os.environ.get("TAGGING_WORKER_ADMIN_TOKEN", "")
        if not expected or x_vton_admin != expected:
            raise HTTPException(401, detail={"error": {
                "code": "UNAUTHORIZED",
                "message": "Missing or wrong X-VTON-Admin header."}})
        if not self.ready:
            raise HTTPException(503, detail={"error": {
                "code": "TAGGING_ENGINE_UNAVAILABLE",
                "message": "Models not loaded", "details": self.load_error}})

        image = _fetch_image(payload.image_base64_or_url)

        try:
            return self.tagger.tag(
                image=image,
                title=payload.title or "",
                description=payload.description or "",
                title_ar=payload.title_ar or "",
                description_ar=payload.description_ar or "",
            )
        except self.core.TaggingRefused as exc:
            raise HTTPException(422, detail={
                "error": {"code": exc.code, "message": exc.message}}) from exc
