"""Feature 06 — CONFIT outfit compatibility worker on Modal (CPU).

App `confit-outfit-worker` — the ONE app for the outfit-compatibility
capability (no duplicates; one Modal app per capability is a standing
constraint).

Model (CPU-only, commercial-safe, MIT):
  OutfitCLIPTransformer (bigohofone/outfit-transformer @ eef4be5, vendored
  at vendor/outfit-transformer): frozen FashionCLIP item encoder
  (patrickjohncyh/fashion-clip — same model family as the tagging worker,
  no new embedding stack) + 6-layer transformer, Polyvore-trained.
  CP AUC 0.95 / FITB 69.24 (upstream-reported, +CLIP variant).

Endpoints (same shell contract as the other CONFIT workers):
  GET  /health           — model/load status, no auth
  GET  /readiness        — ready flag for probes, no auth
  POST /compatibility    — X-VTON-Admin shared secret (Modal secret
                           `confit-outfit-admin-token`, env
                           OUTFIT_WORKER_ADMIN_TOKEN)
  POST /fill-in-the-blank — same auth

Requests:
  /compatibility   {job_id, items: [{image_base64_or_url, slot?, title?}],
                    include_axes?}
  /fill-in-the-blank {job_id, outfit: [item…], candidates: [{id, …item}],
                      target_slot?, top_k?}

Checkpoints (769MB each) are NOT in the image: they live on the Modal
volume `confit-outfit-weights`, mounted read-only. The image bakes only the
FashionCLIP encoder weights from HF (needed by from_pretrained at model
construction). Cold start ≈ 20-40s (one 769MB torch.load from the volume);
the complementary model loads lazily on the first FITB call. Scaled to zero
between calls — no idle burn, no GPU.
"""
from __future__ import annotations

import base64
import binascii
import io
import os
import time
import urllib.request
from typing import List, Optional

import modal
from fastapi import HTTPException, Header
from pydantic import BaseModel, field_validator

_HERE = os.path.dirname(os.path.abspath(__file__))
# _HERE = <repo>/services/outfit-worker  ->  <repo>
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_VENDOR_DIR = os.path.join(_REPO_ROOT, "vendor", "outfit-transformer")


def _bake_models():
    """Bake the FashionCLIP encoder weights into the image.

    OutfitCLIPTransformer construction calls from_pretrained on
    patrickjohncyh/fashion-clip (vision+text projection towers); the
    trained transformer head then loads from the volume checkpoint at
    runtime. Baking the HF side means container starts never touch the
    network.
    """
    from transformers import (
        CLIPVisionModelWithProjection,
        CLIPTextModelWithProjection,
        CLIPImageProcessor,
        CLIPTokenizer,
    )

    CLIPVisionModelWithProjection.from_pretrained("patrickjohncyh/fashion-clip")
    CLIPTextModelWithProjection.from_pretrained("patrickjohncyh/fashion-clip")
    CLIPImageProcessor.from_pretrained("patrickjohncyh/fashion-clip")
    CLIPTokenizer.from_pretrained("patrickjohncyh/fashion-clip")


_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # Same validated CPU set as confit-tagging-worker (2026-10-03):
        # torch cpu 2.14.1 + transformers 5.16.1 run FashionCLIP correctly.
        # opencv-python-headless: the vendored upstream imports cv2 at
        # module level (src/models/outfit_transformer.py, polyvore.py).
        "torch==2.14.1",
        "torchvision==0.29.1",
        "transformers==5.16.1",
        "pillow>=10.4.0",
        "opencv-python-headless>=4.9.0",
        "numpy>=1.26,<3",
        "fastapi>=0.115.0",
        "pydantic>=2.9.0",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .run_function(_bake_models)
    # vendor/outfit-transformer/{upstream/, UPSTREAM_PROVENANCE.txt} — the
    # pristine upstream tree (its `src` package) is one level below the
    # vendor root, so the path pinned here includes /upstream.
    .add_local_dir(_VENDOR_DIR, remote_path="/root/vendor/outfit-transformer", copy=True)
    .add_local_dir(_HERE, remote_path="/root/outfit-worker", copy=True)
    .env({"PYTHONPATH": "/root/outfit-worker:/root/vendor/outfit-transformer/upstream:"})
)

app = modal.App("confit-outfit-worker", image=_image)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
VALID_MIMES = {"image/jpeg", "image/png", "image/webp"}
#: total request budget across ALL images (compat: ≤16, fitb: ≤16+64)
MAX_TOTAL_IMAGE_BYTES = 40 * 1024 * 1024


class ItemSpec(BaseModel):
    """One garment: image (required) + honest metadata (optional)."""
    image_base64_or_url: str
    slot: Optional[str] = None        # CONFIT slot (upper_inner, lower, …)
    category: Optional[str] = None    # or a raw category name
    title: Optional[str] = None

    @field_validator("image_base64_or_url")
    @classmethod
    def validate_image_ref(cls, v):
        if not v or len(v) > 25_000_000:
            raise ValueError("image reference missing or too large")
        return v


class CandidateSpec(ItemSpec):
    id: str  # backend product id (stringified); echoed back in ranking


class CompatibilityRequest(BaseModel):
    job_id: str
    items: List[ItemSpec]
    include_axes: bool = True

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("job_id must be 1-100 chars")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("job_id contains invalid characters")
        return v


class FillInTheBlankRequest(BaseModel):
    job_id: str
    outfit: List[ItemSpec]
    candidates: List[CandidateSpec]
    target_slot: Optional[str] = None
    top_k: int = 5

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("job_id must be 1-100 chars")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("job_id contains invalid characters")
        return v

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v):
        if not 1 <= v <= 20:
            raise ValueError("top_k must be 1-20")
        return v


def _fetch_image(spec: str) -> bytes:
    """Resolve one image spec (data: URL or http(s) URL) to raw bytes.

    Same contract as the other CONFIT workers: hard size cap, explicit
    error codes, never a silent placeholder.
    """
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
                "code": "INVALID_IMAGE",
                "message": "The image data URL is not valid base64."}})
        if len(blob) > MAX_IMAGE_BYTES:
            raise HTTPException(422, detail={"error": {
                "code": "IMAGE_TOO_LARGE",
                "message": "Image exceeds the 15MB limit."}})
        return blob
    if s.startswith(("http://", "https://")):
        req = urllib.request.Request(s, headers={"User-Agent": "confit-outfit-worker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                blob = r.read(MAX_IMAGE_BYTES + 1)
        except Exception:
            raise HTTPException(422, detail={"error": {
                "code": "IMAGE_FETCH_FAILED",
                "message": "The image URL could not be fetched. Check it is public."}})
        if len(blob) > MAX_IMAGE_BYTES:
            raise HTTPException(422, detail={"error": {
                "code": "IMAGE_TOO_LARGE",
                "message": "Image exceeds the 15MB limit."}})
        return blob
    raise HTTPException(422, detail={"error": {
        "code": "INVALID_IMAGE",
        "message": "image_base64_or_url must be a data: URL or an http(s) URL."}})


def _decode_images(specs: List[ItemSpec]):
    """Fetch + decode every image, enforcing the TOTAL payload budget."""
    from PIL import Image

    if not specs:
        return []
    total = 0
    images = []
    for spec in specs:
        blob = _fetch_image(spec.image_base64_or_url)
        total += len(blob)
        if total > MAX_TOTAL_IMAGE_BYTES:
            raise HTTPException(422, detail={"error": {
                "code": "PAYLOAD_TOO_LARGE",
                "message": "Combined image payload exceeds the 40MB budget."}})
        try:
            img = Image.open(io.BytesIO(blob))
            img.load()
        except Exception:
            raise HTTPException(422, detail={"error": {
                "code": "INVALID_IMAGE",
                "message": "An image could not be decoded as JPEG/PNG/WebP."}})
        images.append(img)
    return images


@app.cls(
    image=_image,
    # Two 769MB fp32 checkpoints (compat eager + complementary lazy) +
    # torch runtime ≈ 3.5GB RSS → 8GB headroom. CPU-only: the model is a
    # frozen ViT-B/32 + 6-layer transformer; a GPU would be pure burn.
    cpu=2.0,
    memory=8192,
    scaledown_window=300,
    timeout=300,
    secrets=[modal.Secret.from_name("confit-outfit-admin-token")],
    volumes={
        # same pattern as confit-vton-fashn-weights in the segfee worker
        "/volume": modal.Volume.from_name("confit-outfit-weights"),
    },
)
class OutfitCompatibilityService:
    @modal.enter()
    def load(self):
        import outfit_core

        self.core = outfit_core
        self.engine = outfit_core.OutfitEngine(device="cpu")
        self.load_error = None
        t0 = time.time()
        try:
            self.engine.load_compat()
        except Exception as exc:  # pragma: no cover - surfaced via /health
            self.load_error = str(exc)[:300]
        self.load_seconds = round(time.time() - t0, 1)
        self.ready = self.engine.compat_loaded

    @modal.fastapi_endpoint(method="GET", label="confit-outfit-worker-health")
    def health(self) -> dict:
        return {
            "code_version": "feature-06-r1",
            "status": "healthy" if self.ready else "degraded",
            "service": "outfit-worker",
            "engine": "outfit_transformer_clip_cpu",
            "models": {
                "compatibility": {
                    "loaded": self.engine.compat_loaded,
                    "checkpoint": "confit-outfit-weights:checkpoints/"
                                  "compatibility_clip_best.pth (sha256 fb33e811…)",
                },
                "complementary": {
                    "loaded": self.engine.complementary_loaded,
                    "checkpoint": "confit-outfit-weights:checkpoints/"
                                  "complementary_clip_best.pth (sha256 1a41ef5e…)",
                    "note": "lazy — loads on first /fill-in-the-blank call",
                },
                "upstream": "bigohofone/outfit-transformer @ eef4be5 (MIT)",
                "fashionclip": "patrickjohncyh/fashion-clip (MIT)",
            },
            "models_loaded": self.ready,
            "load_error": self.load_error,
            "device": "cpu",
            "commercial": True,
            "benchmark": "TATTOO (arXiv:2509.23242) type-aware axes — advisory block",
            "ready": self.ready,
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="GET", label="confit-outfit-worker-readiness")
    def readiness(self) -> dict:
        if not self.ready:
            raise HTTPException(503, detail={
                "error": {"code": "OUTFIT_ENGINE_NOT_READY",
                          "message": "Compatibility model not loaded",
                          "load_error": self.load_error},
                "ready": False})
        return {"ready": True, "engine": "outfit_transformer_clip_cpu"}

    def _check_auth(self, x_vton_admin: Optional[str]) -> None:
        expected = os.environ.get("OUTFIT_WORKER_ADMIN_TOKEN", "")
        if not expected or x_vton_admin != expected:
            raise HTTPException(401, detail={"error": {
                "code": "UNAUTHORIZED",
                "message": "Missing or wrong X-VTON-Admin header."}})
        if not self.ready:
            raise HTTPException(503, detail={"error": {
                "code": "OUTFIT_ENGINE_UNAVAILABLE",
                "message": "Models not loaded", "details": self.load_error}})

    @modal.fastapi_endpoint(method="POST", label="confit-outfit-worker-compatibility")
    def compatibility(
        self, payload: CompatibilityRequest,
        x_vton_admin: Optional[str] = Header(None, alias="X-VTON-Admin"),
    ) -> dict:
        self._check_auth(x_vton_admin)
        images = _decode_images(payload.items)
        try:
            result = self.engine.score_compatibility(
                [i.model_dump() for i in payload.items],
                images,
                include_axes=payload.include_axes,
            )
        except self.core.OutfitEngineRefused as exc:
            raise HTTPException(422, detail={
                "error": {"code": exc.code, "message": exc.message}}) from exc
        result["job_id"] = payload.job_id
        return result

    @modal.fastapi_endpoint(method="POST", label="confit-outfit-worker-fill-in-the-blank")
    def fill_in_the_blank(
        self, payload: FillInTheBlankRequest,
        x_vton_admin: Optional[str] = Header(None, alias="X-VTON-Admin"),
    ) -> dict:
        self._check_auth(x_vton_admin)
        outfit_images = _decode_images(payload.outfit)
        candidate_images = _decode_images(payload.candidates)
        try:
            result = self.engine.fill_in_the_blank(
                [i.model_dump() for i in payload.outfit], outfit_images,
                [c.model_dump() for c in payload.candidates], candidate_images,
                target_slot=payload.target_slot,
                top_k=payload.top_k,
            )
        except self.core.OutfitEngineRefused as exc:
            raise HTTPException(422, detail={
                "error": {"code": exc.code, "message": exc.message}}) from exc
        result["job_id"] = payload.job_id
        return result
