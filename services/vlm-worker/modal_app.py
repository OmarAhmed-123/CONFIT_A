# =============================================================================
# CONFIT SELF-HOSTED VLM WORKER (Qwen2.5-VL-7B, Apache-2.0) — Modal deployment.
#
# Purpose: local, self-hosted vision FALLBACK for Visual Search + Wardrobe
# Auto-Tagging. Removes the per-request Gemini credit dependency for that
# capability. It is a SEPARATE Modal service (not the VTON worker) so the two
# large GPU models do not share a process/VRAM (resource isolation).
#
# Self-hosted != free: this consumes a GPU (Modal GPU-hours) + VRAM +
# ~16.6 GB disk (weights in a Modal Volume). No per-request provider credit.
#
# Endpoints:
#   * GET  /health    (public) -> service/model/device/license metadata
#   * GET  /readiness (public) -> 200 only when model loaded, else 503 VLM_NOT_READY
#   * POST /analyze   -> {image, prompt, mode} -> Gemini-compatible structured JSON
#
# Auth: X-VLM-Admin header == Modal secret `confit-vlm-admin-token`.
# Weights: Modal Volume `confit-qwen25vl-weights` mounted at /weights.
# =============================================================================
import base64
import os
from urllib.parse import urlparse

import httpx
import modal
from fastapi import Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from inference import InferenceError, OutputInvalidError, analyze_image, load_model
from model_spec import LICENSE, MODEL_REVISION, MODEL_REPO_ID

app = modal.App("confit-vlm-worker")

WEIGHTS_DIR = "/weights"
MODEL_ID = MODEL_REPO_ID
MODEL_DEVICE = os.environ.get("QWEN_VL_DEVICE", "auto")
MODEL_DTYPE = os.environ.get("QWEN_VL_TORCH_DTYPE", "bfloat16")
# Optional 4-bit NF4 (OFF by default) reduces served VRAM (~6-8 GB vs the MEASURED
# 15.45 GB BF16) so the worker can fit a cheaper GPU tier. It does NOT fix the web
# cold start (the container BOOT — image pull + CUDA init — is the bottleneck here,
# not the model load). Set QWEN_VL_LOAD_4BIT=1 to enable; keep BF16 (default) to
# match the measured benchmark numbers.
MODEL_LOAD_4BIT = os.environ.get("QWEN_VL_LOAD_4BIT", "0") == "1"
WORKER_GPU = os.environ.get("VLM_GPU", "A10G")

# Image mirrors the proven VTON worker pattern (debian_slim + torch/CUDA stack).
# PyPI torch bundles the NVIDIA CUDA runtime; A10G (CUDA 12) compatible.
#
# CRITICAL (root cause of the earlier crash-loop): `modal deploy modal_app.py`
# ships ONLY modal_app.py to /root in the container. The top-level
#   from inference import ...
#   from model_spec import ...
# would therefore crash every container at import with
#   ModuleNotFoundError: No module named 'inference'
# (observed in the deployed app logs: "QwenInferenceService.* is crash-looping").
# The sibling modules MUST be baked into the image. We ship exactly the two files
# modal_app.py imports (deterministic: same git tree, no weights, no /tmp).
_HERE = os.path.dirname(os.path.abspath(__file__))
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch",
        "torchvision",  # required by Qwen2VLVideoProcessor
        "transformers>=4.50.0",
        "accelerate>=0.33.0",
        "bitsandbytes>=0.43.0",
        "qwen-vl-utils>=0.0.8",
        "huggingface_hub>=0.24.0",
        "Pillow>=10.4.0",
        "numpy>=1.26.0",
        "httpx>=0.27.2",
        "fastapi>=0.115.0",
        "uvicorn>=0.32.0",
        "pydantic>=2.9.0",
    )
    .add_local_file(os.path.join(_HERE, "inference.py"), "/root/inference.py")
    .add_local_file(os.path.join(_HERE, "model_spec.py"), "/root/model_spec.py")
)


class AnalyzeRequest(BaseModel):
    image: str
    prompt: str
    mode: str = "visual_search"
    model_id: str | None = None

    @field_validator("image")
    @classmethod
    def _image_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("image is required")
        return v

    @field_validator("prompt")
    @classmethod
    def _prompt_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt is required")
        return v


_BLOCKED_HOST_PREFIXES = (
    "127.", "10.", "192.168.", "169.254.", "0.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
    "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
)


def _is_safe_image_url(url: str) -> bool:
    """Standalone SSRF gate (loopback / private / link-local targets refused)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host == "localhost" or host.startswith(_BLOCKED_HOST_PREFIXES):
        return False
    return True


def _image_to_bytes(image_ref: str) -> tuple[bytes, str]:
    if image_ref.startswith("data:image"):
        header, encoded = image_ref.split(",", 1)
        mime = header.split(";")[0].replace("data:", "") or "image/jpeg"
        return base64.b64decode(encoded), mime
    if image_ref.startswith(("http://", "https://")):
        if not _is_safe_image_url(image_ref):
            raise ValueError("refused unsafe image URL (private/loopback/link-local target)")
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(image_ref)
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                raise ValueError(f"unsupported image content type: {mime or 'unknown'}")
            if len(resp.content) > 15 * 1024 * 1024:
                raise ValueError("image exceeds 15MB limit")
            return resp.content, mime
    raise ValueError("image must be a data URL or http(s) URL")


@app.cls(
    image=image,
    gpu=WORKER_GPU,
    # Serving note: with the sibling modules now baked into the image (see above), the
    # earlier crash-loop (ModuleNotFoundError: inference) is resolved — the container
    # starts, loads the model on the A10G, and serves /analyze. A warm container
    # (min_containers=1) is NOT sustained on this (free/limited) account, so each
    # idle->active transition is a cold start (container boot + 16.6 GB load).
    # min_containers is env-overridable (VLM_MIN_CONTAINERS, default 0 = scale to 0 when
    # idle to avoid GPU burn). A robust alternative transport is the standalone
    # `vlm_analyze` Modal Function (backend QWEN_VL_TRANSPORT=remote -> .remote(),
    # container held for the call).
    min_containers=int(os.environ.get("VLM_MIN_CONTAINERS", "0")),
    timeout=900,
    secrets=[modal.Secret.from_name("confit-vlm-admin-token2")],
    volumes={WEIGHTS_DIR: modal.Volume.from_name("confit-qwen25vl-weights")},
)
@modal.concurrent(max_inputs=1)
class QwenInferenceService:

    @modal.enter()
    def load(self) -> None:
        """Load the model once per container; report the honest state on failure."""
        self.model_loaded = False
        self.load_error = None
        self.device_name = "cpu"
        try:
            import torch

            self.device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
            os.environ.setdefault("QWEN_VL_WEIGHTS_DIR", WEIGHTS_DIR)
            load_model(device=MODEL_DEVICE, dtype=MODEL_DTYPE, load_in_4bit=MODEL_LOAD_4BIT)
            self.model_loaded = True
            print(f"[vlm-load] {MODEL_ID} ready on {self.device_name} (4bit={MODEL_LOAD_4BIT})", flush=True)
        except Exception as exc:
            self.model_loaded = False
            self.load_error = f"{type(exc).__name__}: {exc}"
            print(f"[vlm-load] MODEL LOAD FAILED: {self.load_error}", flush=True)

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        return {
            "status": "healthy" if self.model_loaded else "degraded",
            "service": "confit-vlm-worker",
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "license": LICENSE,
            "device": self.device_name,
            "model_loaded": self.model_loaded,
            "load_error": self.load_error,
        }

    @modal.fastapi_endpoint(method="GET")
    def readiness(self):
        if not self.model_loaded:
            return JSONResponse(
                status_code=503,
                content={
                    "ready": False,
                    "error": {"code": "VLM_NOT_READY", "message": "model not loaded", "load_error": self.load_error},
                },
            )
        return {"ready": True, "model": MODEL_ID, "model_loaded": True}

    @modal.fastapi_endpoint(method="POST")
    def analyze(
        self,
        payload: AnalyzeRequest,
        x_vlm_admin: str | None = Header(None, alias="X-VLM-Admin"),
    ):
        expected = os.environ.get("QWEN_VL_WORKER_TOKEN") or os.environ.get("CONFIT_VLM_ADMIN_TOKEN", "")
        if expected and x_vlm_admin != expected:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHORIZED", "message": "invalid or missing admin token"}},
            )
        if not self.model_loaded:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "VLM_NOT_READY", "message": "model not loaded", "load_error": self.load_error}},
            )
        try:
            image_bytes, mime = _image_to_bytes(payload.image)
        except Exception as exc:
            return JSONResponse(status_code=422, content={"error": {"code": "BAD_INPUT", "message": str(exc)[:300]}})
        try:
            data = analyze_image(image_bytes, mime, payload.prompt)
        except OutputInvalidError as exc:
            return {
                "analysis_available": False,
                "analysis_source": MODEL_ID,
                "error": "output_invalid",
                "detail": str(exc)[:300],
            }
        except InferenceError as exc:
            code = "GPU_OOM" if "OOM" in str(exc) else "INFERENCE_FAILED"
            return JSONResponse(status_code=500, content={"error": {"code": code, "message": str(exc)[:300]}})
        return {"analysis_available": True, "analysis_source": MODEL_ID, **data}


@app.function(
    image=image,
    gpu=WORKER_GPU,
    timeout=900,
    secrets=[modal.Secret.from_name("confit-vlm-admin-token2")],
    volumes={WEIGHTS_DIR: modal.Volume.from_name("confit-qwen25vl-weights")},
)
def vlm_analyze(image_b64: str, mime: str, prompt: str, mode: str = "visual_search") -> dict:
    """Server-to-server ``.remote()`` entry point (production option (b)).

    The backend references this via ``modal.Function.from_name("confit-vlm-worker",
    "vlm_analyze")`` and calls ``.remote(...)``, so the container is held for the call
    (up to ``timeout``) and the heavy cold start is fine — unlike the stateless web edge.
    Loads the model once per container (inference singleton). No public web auth: the
    Modal invocation channel (MODAL_TOKEN_*) is the trust boundary. Same honest response
    contract as ``/analyze`` (never invents fields).
    """
    import base64 as _b64

    os.environ.setdefault("QWEN_VL_WEIGHTS_DIR", WEIGHTS_DIR)
    try:
        load_model(device=MODEL_DEVICE, dtype=MODEL_DTYPE, load_in_4bit=MODEL_LOAD_4BIT)
    except InferenceError as exc:
        return {"analysis_available": False, "error": "VLM_NOT_READY", "detail": str(exc)[:300]}
    try:
        image_bytes = _b64.b64decode(image_b64)
    except Exception as exc:
        return {"analysis_available": False, "error": "BAD_INPUT", "detail": f"bad image base64: {exc}"[:300]}
    try:
        data = analyze_image(image_bytes, mime, prompt)
    except OutputInvalidError as exc:
        return {"analysis_available": False, "error": "output_invalid", "detail": str(exc)[:300]}
    except InferenceError as exc:
        code = "GPU_OOM" if "OOM" in str(exc) else "INFERENCE_FAILED"
        return {"analysis_available": False, "error": code, "detail": str(exc)[:300]}
    return {"analysis_available": True, "analysis_source": MODEL_ID, **data}
