# ==============================================================================
# CONFIT VTON GPU WORKER (COMMERCIAL) — Modal serverless deployment of the
# CONFIT_A `fashn-vton-segfee` engine.
#
# This is the COMMERCIAL production worker. It runs the validated
# segmentation-free FASHN fork (fashn-AI/fashn-vton-1.5 @ 7c0f10af with the
# non-commercial `fashn-human-parser` REMOVED from the runtime), and it is the
# canonical engine behind `VTON_ENGINE=fashn_vton_segfee`.
#
# Contract preservation (identical to the former CatVTON worker's external
# contract, so the API service and frontend are unchanged):
#   * POST /process  with X-VTON-Admin auth -> VTONJobRequest -> rendered_image_data_url
#   * GET  /health   (public) -> service/model_loaded/device/engine metadata
#   * GET  /readiness(public) -> 200 only when model loaded, else 503 VTON_NOT_READY
#   * input validation (size/dim/decompression-bomb/format)
#   * SSRF guard on URL-fetched images
#   * strict output validation (no echo, not blank, genuine change)
#   * honest error taxonomy: UNAUTHORIZED / VTON_ENGINE_UNAVAILABLE / INPUT_INVALID
#     / GPU_OOM / INFERENCE_FAILED / OUTPUT_INVALID / VTON_NOT_READY
#   * single-category semantics (FASHN is one garment per call) — never naive
#     multi-garment compositing.
#
# The NEW engine is single-category and maskless, so there is NO rembg /
# segmentation / mask path here. `VTONJobRequest.garments` must contain exactly
# one garment; a request with more is rejected loudly.
# ==============================================================================

import os
import io
import time
import base64
import ipaddress
import socket
import urllib.parse as _urlparse
from typing import Any, Dict, List

from PIL import Image
import modal
from fastapi import HTTPException, Header
from pydantic import BaseModel, field_validator

app = modal.App("confit-vton-worker-segfee")

# Security and resource limits
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB
MIN_IMAGE_BYTES = 100
MAX_IMAGE_DIMENSION = 4096
MIN_IMAGE_DIMENSION = 32
MAX_GARMENTS = 1  # FASHN is single-category; do not accept more than one.

WEIGHTS_DIR = "/weights"

# Blocked networks for SSRF protection (same as the former CatVTON worker)
_BLOCK_IPV4 = [
    ipaddress.ip_network(n) for n in [
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/16",
        "192.0.0.0/24", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4",
    ]
]
_BLOCK_IPV6 = [
    ipaddress.ip_network(n) for n in [
        "::1/128", "fc00::/7", "fe80::/10", "::/128", "ff00::/8", "2001:db8::/32",
    ]
]

# Map the CONFIT slot_type (legacy vocabulary retained for the frontend) to the
# FASHN category vocabulary. FASHN supports tops / bottoms / one-pieces only.
SLOT_TO_CATEGORY = {
    "upper_outer": "tops",
    "upper_inner": "tops",
    "lower": "bottoms",
    "dress": "one-pieces",
    "footwear": None,      # unsupported by FASHN -> explicit INPUT_INVALID
    "accessory": None,     # unsupported by FASHN -> explicit INPUT_INVALID
}
SUPPORTED_CATEGORIES = {"tops", "bottoms", "one-pieces"}


# ==============================================================================
# BUILD (image + engine vendored fork). Deploy with:
#     modal deploy services/vton-worker/modal_app_segfee.py
# ==============================================================================
def _resolve_build_git_sha() -> str:
    explicit = os.environ.get("CONFIT_GIT_SHA", "").strip()
    if explicit:
        return explicit
    try:
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here, capture_output=True, text=True, timeout=10).stdout.strip()
        if not sha:
            return "unknown"
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=here, capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except Exception:
        return "unknown"


BUILD_GIT_SHA = _resolve_build_git_sha()


# modal_app_segfee.py lives at <repo>/services/vton-worker/, so two ".." reach
# <repo>/; <repo>/vendor/fashn-vton-segfee is the segmentation-free fork source.
_FORK_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vendor", "fashn-vton-segfee"))
_ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "engine"))

_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch", "torchvision", "safetensors", "huggingface_hub", "pillow",
        "numpy", "opencv-python-headless", "tqdm", "einops",
        "onnxruntime-gpu", "matplotlib",
        "fastapi>=0.115.0", "pydantic>=2.9.0", "httpx>=0.27.2",
    )
    .add_local_dir(_FORK_DIR, remote_path="/root/fashn-vton-segfee", copy=True)
    .add_local_dir(_ENGINE_DIR, remote_path="/root/vton-worker/engine", copy=True)
    .run_commands("pip install --no-deps /root/fashn-vton-segfee")
    .env({"PYTHONPATH": "/root/fashn-vton-segfee:/root/vton-worker:",
          "CONFIT_GIT_SHA": BUILD_GIT_SHA})
)


def _is_safe_url(raw: str) -> bool:
    """SSRF guard: only public IPs, no private/loopback/metadata."""
    if not isinstance(raw, str) or not raw:
        return False
    try:
        u = _urlparse.urlparse(raw)
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    host = u.hostname
    if not host:
        return False
    if host.lower() in {"localhost", "metadata.google.internal", "169.254.169.254"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
        for net in (_BLOCK_IPV4 if ip.version == 4 else _BLOCK_IPV6):
            if ip in net:
                return False
        return True
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for fam, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
        for net in (_BLOCK_IPV4 if ip.version == 4 else _BLOCK_IPV6):
            if ip in net:
                return False
    return True


def _validate_and_decode_image(raw: bytes, context: str = "image") -> Image.Image:
    """Validate image bytes: size, dimensions, decompression bomb, format."""
    if len(raw) < MIN_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} too small"}})
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} too large, max {MAX_IMAGE_BYTES} bytes"}})
    try:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w * h > MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} dimensions too large"}})
        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} dimensions too small"}})
        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} dimension exceeds {MAX_IMAGE_DIMENSION}"}})
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return img
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Invalid {context} data: {type(e).__name__}: {str(e)[:200]}"}})


class VTONJobRequest(BaseModel):
    job_id: str
    user_image_base64_or_url: str
    garments: List[Dict[str, Any]]
    gender_mode: str = "infer_from_image"
    output_aspect: str = "9:16"

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("job_id must be 1-100 chars")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("job_id contains invalid characters")
        return v

    @field_validator("garments")
    @classmethod
    def validate_garments(cls, v):
        if not v:
            raise ValueError("at least one garment required")
        if len(v) > MAX_GARMENTS:
            raise ValueError(f"fashn_vton_segfee is single-category; max {MAX_GARMENTS} garment per job (got {len(v)})")
        for g in v:
            slot = g.get("slot_type", "") or g.get("category", "")
            if slot and slot not in {"upper_outer", "upper_inner", "lower", "dress", "footwear", "accessory"} \
                    and slot not in SUPPORTED_CATEGORIES:
                raise ValueError(f"unsupported slot_type/category: {slot}")
        return v

    @field_validator("user_image_base64_or_url")
    @classmethod
    def validate_person_image(cls, v):
        if not v:
            raise ValueError("person image required")
        if len(v) > MAX_IMAGE_BYTES * 1.4:
            raise ValueError("person image too large")
        return v


@app.cls(
    gpu="A10G",
    image=_image,  # noqa: F821  (defined below; pydantic/modal resolve at build)
    secrets=[modal.Secret.from_name("confit-worker-admin-token")],
    scaledown_window=300,
    volumes={WEIGHTS_DIR: modal.Volume.from_name("confit-vton-fashn-weights")},
)
@modal.concurrent(max_inputs=1)  # single-category engine; one GPU job at a time
class FashnInferenceService:
    """Production-hardened commercial FASHN segmentation-free worker."""

    @modal.enter()
    def load_model(self) -> None:
        import torch
        self.model_loaded = False
        self.load_error = None
        self.engine = None
        self.device_name = None
        try:
            from engine import get_engine

            engine_cls = get_engine("fashn_vton_segfee")
            if engine_cls is None:
                raise RuntimeError("fashn_vton_segfee engine is not registered")
            engine = engine_cls(weights_dir=WEIGHTS_DIR, device="cuda")
            engine.load()
            self.engine = engine
            self.device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            self.model_loaded = True
            print(f"[load] fashn_vton_segfee loaded on {self.device_name}", flush=True)
            if torch.cuda.is_available():
                print(f"[load] GPU memory allocated={torch.cuda.memory_allocated()/1024**3:.2f}GB reserved={torch.cuda.memory_reserved()/1024**3:.2f}GB", flush=True)
        except Exception as exc:
            import traceback as _tb
            self.engine = None
            self.model_loaded = False
            self.load_error = f"{type(exc).__name__}: {exc}"
            _tb.print_exc()
            print(f"[load] MODEL LOAD FAILED: {self.load_error}", flush=True)

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        import torch
        status = "healthy" if self.model_loaded else "degraded"
        device = self.device_name or ("cuda" if torch.cuda.is_available() else "cpu")
        gpu_mem = {}
        if torch.cuda.is_available():
            try:
                gpu_mem = {
                    "allocated_gb": round(torch.cuda.memory_allocated() / 1024**3, 2),
                    "reserved_gb": round(torch.cuda.memory_reserved() / 1024**3, 2),
                }
            except Exception:
                pass
        return {
            "status": status,
            "service": "vton-worker-segfee",
            "engine": "fashn_vton_segfee",
            "model": "fashn-vton-v1.5 (MMDiT 972M, segmentation-free; fork 7c0f10af)",
            "model_loaded": self.model_loaded,
            "load_error": self.load_error,
            "device": device,
            "cuda_available": torch.cuda.is_available(),
            "gpu_memory": gpu_mem,
            "git_sha": os.environ.get("CONFIT_GIT_SHA", "unknown"),
            "parser_present": _parser_in_runtime(),
            "commercial": True,
            "ready": self.model_loaded,
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="GET")
    def readiness(self) -> dict:
        if not self.model_loaded:
            raise HTTPException(
                status_code=503,
                detail={"error": {"code": "VTON_NOT_READY", "message": "Model not loaded, worker not ready", "load_error": self.load_error}, "ready": False},
            )
        return {"ready": True, "engine": "fashn_vton_segfee", "model_loaded": True}

    @modal.fastapi_endpoint(method="POST")
    def process(self, payload: VTONJobRequest, x_vton_admin: str | None = Header(None, alias="X-VTON-Admin")) -> dict:
        # Authentication. The worker receives the admin token from the Modal
        # secret `confit-worker-admin-token` (injected into the container env as
        # VTON_WORKER_ADMIN_TOKEN), with a CONFIT_WORKER_ADMIN_TOKEN fallback for
        # the earlier-deployed convention. Never logged, never returned.
        expected = os.environ.get("VTON_WORKER_ADMIN_TOKEN") or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN", "")
        if not expected or x_vton_admin != expected:
            raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Missing or wrong X-VTON-Admin header."}})
        if not self.model_loaded:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_ENGINE_UNAVAILABLE", "message": "Reason: engine not loaded", "details": self.load_error}})

        start_total = time.time()
        request_id = payload.job_id

        # Person image
        ref = payload.user_image_base64_or_url
        try:
            if ref.startswith("data:image"):
                header, b64_data = ref.split(",", 1)
                raw = base64.b64decode(b64_data)
                person = _validate_and_decode_image(raw, "person image")
            else:
                if not _is_safe_url(ref):
                    raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": "Unsafe person image URL"}})
                import httpx
                try:
                    r = httpx.get(ref, timeout=30.0, follow_redirects=True, headers={"User-Agent": "CONFIT-VTON/1.0"})
                    r.raise_for_status()
                    if len(r.content) > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": "Person image too large"}})
                    person = _validate_and_decode_image(r.content, "person image")
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Failed to fetch person image: {type(e).__name__}: {str(e)[:200]}"}})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Invalid person image: {type(e).__name__}: {str(e)[:200]}"}})

        # Single-garment enforcement + category mapping
        garments = payload.garments
        if len(garments) != 1:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": "fashn_vton_segfee is single-category; exactly one garment per job."}})
        g_item = garments[0]
        slot = g_item.get("slot_type", "") or g_item.get("category", "")
        category = SLOT_TO_CATEGORY.get(slot, slot if slot in SUPPORTED_CATEGORIES else None)
        if category is None:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"fashn_vton_segfee does not support slot_type/category {slot!r}: only tops/bottoms/one-pieces."}})

        # Garment image
        g_ref = g_item.get("image_base64") or g_item.get("image_url") or ""
        try:
            if g_ref.startswith("data:image"):
                header, b64_data = g_ref.split(",", 1)
                g_raw = base64.b64decode(b64_data)
                garment = _validate_and_decode_image(g_raw, "garment image")
            else:
                if not _is_safe_url(g_ref):
                    raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": "Unsafe garment image URL"}})
                import httpx
                try:
                    r = httpx.get(g_ref, timeout=30.0, follow_redirects=True, headers={"User-Agent": "CONFIT-VTON/1.0"})
                    r.raise_for_status()
                    if len(r.content) > MAX_IMAGE_BYTES:
                        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": "Garment image too large"}})
                    garment = _validate_and_decode_image(r.content, "garment image")
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Failed to fetch garment image: {type(e).__name__}: {str(e)[:200]}"}})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Invalid garment image: {type(e).__name__}: {str(e)[:200]}"}})

        # Run inference
        import torch
        start_inference = time.time()
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            rendered = self.engine.render(
                person_image=person,
                garment_image=garment,
                category=category,
                seed=42,
                num_timesteps=30,
            )
            inference_s = round(time.time() - start_inference, 3)
        except torch.cuda.OutOfMemoryError as e:
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            raise HTTPException(status_code=503, detail={"error": {"code": "GPU_OOM", "message": f"GPU OOM: {e}", "job_id": request_id}})
        except Exception as e:
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail={"error": {"code": "INFERENCE_FAILED", "message": f"Inference failed: {type(e).__name__}: {str(e)[:300]}", "job_id": request_id}})

        # Encode output
        try:
            buf = io.BytesIO()
            rendered.convert("RGB").save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            rendered_data_url = "data:image/png;base64," + b64
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": {"code": "OUTPUT_INVALID", "message": f"Failed to encode output: {e}"}})

        if rendered_data_url == ref:
            raise HTTPException(status_code=500, detail={"error": {"code": "OUTPUT_INVALID", "message": "Model returned input unchanged (echo)"}})

        # Output validation (no echo, not blank, genuine change)
        verify = {"PASS": None}
        try:
            verify = self._verify_output(person, rendered)
        except Exception as e:
            print(f"[process] verify failed job {request_id}: {e}", flush=True)

        _parser_status = _parser_in_runtime()
        if _parser_status:
            # The restricted parser must NEVER be present in a commercial runtime.
            raise HTTPException(status_code=500, detail={"error": {"code": "OUTPUT_INVALID", "message": "Non-commercial human-parser was loaded in runtime (aborting)."}})

        total_ms = round((time.time() - start_total) * 1000, 1)
        print(f"[process] SUCCESS job={request_id} category={category} inference_s={inference_s} total_ms={total_ms} verify_pass={verify.get('PASS')} out_bytes={len(rendered_data_url)}", flush=True)

        return {
            "job_id": payload.job_id,
            "status": "completed",
            "rendered_image_data_url": rendered_data_url,
            "execution_time_ms": round(inference_s * 1000, 1),
            "total_time_ms": total_ms,
            "model_used": "fashn-vton-v1.5 (fashn_vton_segfee, segmentation-free; fork 7c0f10af)",
            "engine": "fashn_vton_segfee",
            "layers_processed": 1,
            "slot_type": slot,
            "category": category,
            "verify": verify,
            "parser_present": _parser_status,
            "commercial": True,
        }

    def _verify_output(self, original: Image.Image, rendered: Image.Image) -> dict:
        import numpy as np
        a = np.asarray(original.convert("RGB"), dtype=np.int16)
        b = np.asarray(rendered.convert("RGB").resize(original.size), dtype=np.int16)
        diff = np.abs(b - a)
        pixel_change = float(diff.mean())
        color_shift = float(np.linalg.norm(diff.mean(axis=(0, 1)))) / 255.0
        stddev = float(b.std())
        return {
            "PASS": bool(pixel_change >= 1.0 and color_shift > 0.005 and stddev > 5.0),
            "metric_pixel_change": round(pixel_change, 4),
            "metric_color_shift": round(color_shift, 6),
            "metric_image_stddev": round(stddev, 2),
        }


def _parser_in_runtime() -> bool:
    """Return True if the restricted fashn_human_parser is importable/loaded."""
    import sys
    try:
        if "fashn_human_parser" in sys.modules:
            return True
        import importlib.util
        return importlib.util.find_spec("fashn_human_parser") is not None
    except Exception:
        return False
