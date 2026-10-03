# ==============================================================================
# CONFIT VTON WORKER — SHARED HTTP LAYER (feature 03, multi-garment)
#
# Single source of truth for the worker's external contract, shared by BOTH
# deployment shells:
#   * modal_app_v15.py   — Modal serverless (GPU class endpoints delegate here)
#   * baseten_server.py  — Baseten custom Docker container (uvicorn + FastAPI
#                          app factory below; A/B comparison target 2026-10-03)
#
# Everything here is deployment-agnostic: no `modal` / no `baseten` imports.
# The "holder" protocol (duck-typed) is whatever object owns the loaded engine:
#
#     holder.engine        -> loaded VTONEngine instance (or None)
#     holder.model_loaded  -> bool
#     holder.load_error    -> str | None
#     holder.device_name   -> str | None
#
# External contract (unchanged from the Modal deployment — the API service
# keeps working against either host):
#   * POST /process  with X-VTON-Admin auth -> VTONJobRequest (garments 1-3)
#     -> rendered_image_data_url + layers[] + verify + parser metadata
#   * GET  /health   (public) -> service/model_loaded/device/engine/parser
#   * GET  /readiness(public) -> 200 only when model loaded, else 503
#   * input validation (size/dim/decompression-bomb/format) + SSRF guard
#   * strict per-layer output validation (no echo, not blank, real change)
#   * error taxonomy: UNAUTHORIZED / VTON_ENGINE_UNAVAILABLE / INPUT_INVALID
#     / GPU_OOM / INFERENCE_FAILED / OUTPUT_INVALID / VTON_NOT_READY
# ==============================================================================

from __future__ import annotations

import base64
import io
import ipaddress
import os
import socket
import time
import urllib.parse as _urlparse
from typing import Any, Dict, List, Optional, Protocol

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel, field_validator

# Security and resource limits (identical bars on every host)
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB per image
MIN_IMAGE_BYTES = 100
MAX_IMAGE_DIMENSION = 4096
MIN_IMAGE_DIMENSION = 32
MAX_GARMENTS = 3  # fashn_v15 composes multi-garment outfits (tops+bottoms)
OVERLAY_MODES = {"masked", "segfree"}

# Blocked networks for SSRF protection
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


# ==============================================================================
# Holder protocol (whatever object owns the loaded engine)
# ==============================================================================
class EngineHolder(Protocol):
    engine: Any
    model_loaded: bool
    load_error: Optional[str]
    device_name: Optional[str]


def _err(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    detail: Dict[str, Any] = {"error": {"code": code, "message": message}}
    detail["error"].update(extra)
    return HTTPException(status_code=status, detail=detail)


# ==============================================================================
# Validation / SSRF / image decoding (verbatim from the Modal deployment)
# ==============================================================================
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
        raise _err(422, "INPUT_INVALID", f"{context} too small")
    if len(raw) > MAX_IMAGE_BYTES:
        raise _err(422, "INPUT_INVALID", f"{context} too large, max {MAX_IMAGE_BYTES} bytes")
    try:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w * h > MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION:
            raise _err(422, "INPUT_INVALID", f"{context} dimensions too large")
        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
            raise _err(422, "INPUT_INVALID", f"{context} dimensions too small")
        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            raise _err(422, "INPUT_INVALID", f"{context} dimension exceeds {MAX_IMAGE_DIMENSION}")
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        return img
    except HTTPException:
        raise
    except Exception as e:
        raise _err(422, "INPUT_INVALID", f"Invalid {context} data: {type(e).__name__}: {str(e)[:200]}")


def _fetch_image(ref: str, context: str) -> Image.Image:
    """Decode a data-URL base64 or SSRF-safe URL fetch into a validated image."""
    if ref.startswith("data:image"):
        header, b64_data = ref.split(",", 1)
        raw = base64.b64decode(b64_data)
        return _validate_and_decode_image(raw, context)
    if not _is_safe_url(ref):
        raise _err(422, "INPUT_INVALID", f"Unsafe {context} URL")
    import httpx
    try:
        r = httpx.get(ref, timeout=30.0, follow_redirects=True, headers={"User-Agent": "CONFIT-VTON/1.0"})
        r.raise_for_status()
        if len(r.content) > MAX_IMAGE_BYTES:
            raise _err(422, "INPUT_INVALID", f"{context} too large")
        return _validate_and_decode_image(r.content, context)
    except HTTPException:
        raise
    except Exception as e:
        raise _err(422, "INPUT_INVALID", f"Failed to fetch {context}: {type(e).__name__}: {str(e)[:200]}")


def _parser_info() -> Dict[str, Any]:
    """Honest runtime report about the (non-commercial) parser presence."""
    return {
        "present": True,  # by design in this worker (owner-approved 2026-10-01)
        "model": "fashn-ai/fashn-human-parser (SegFormer fine-tune)",
        "license": "NVIDIA Source Code License for SegFormer (non-commercial)",
        "owner_decision": "approved for early-stage use 2026-10-01; licensed "
                          "swap planned before commercial scale",
        "swappable_via": "engine.FashnV15MultiGarmentEngine(parser_impl=...)",
    }


def _expected_admin_token() -> str:
    """The X-VTON-Admin token, from env (Modal/Baseten env) or the Baseten
    secrets file mount (/secrets/<name>, read-only file with the raw value)."""
    tok = (
        os.environ.get("VTON_WORKER_ADMIN_TOKEN")
        or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
        or ""
    )
    if tok:
        return tok.strip()
    for candidate in (
        "/secrets/confit-worker-admin-token/VTON_WORKER_ADMIN_TOKEN",
        "/secrets/confit-worker-admin-token/CONFIT_WORKER_ADMIN_TOKEN",
    ):
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                val = fh.read().strip()
            if val:
                return val
        except OSError:
            continue
    return ""


# ==============================================================================
# Request model (same wire contract as the Modal deployment)
# ==============================================================================
class VTONJobRequest(BaseModel):
    job_id: str
    user_image_base64_or_url: str
    garments: List[Dict[str, Any]]
    gender_mode: str = "infer_from_image"
    output_aspect: str = "9:16"
    overlay_mode: str = "masked"  # layer 2+ composition: masked | segfree

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
            raise ValueError(f"fashn_v15 composes at most {MAX_GARMENTS} garments per job (got {len(v)})")
        for g in v:
            slot = (g.get("slot_type", "") or g.get("category", "") or "").lower()
            if slot not in {"upper_outer", "upper_inner", "inner_layer", "knit_layer", "lower", "dress"} \
                    and slot not in {"tops", "bottoms", "one-pieces"}:
                raise ValueError(f"unsupported slot_type/category: {slot}")
            if not (g.get("image_base64") or g.get("image_url")):
                raise ValueError("each garment needs image_base64 or image_url")
        return v

    @field_validator("overlay_mode")
    @classmethod
    def validate_overlay_mode(cls, v):
        if v not in OVERLAY_MODES:
            raise ValueError(f"overlay_mode must be one of {sorted(OVERLAY_MODES)}, got {v!r}")
        return v

    @field_validator("user_image_base64_or_url")
    @classmethod
    def validate_person_image(cls, v):
        if not v:
            raise ValueError("person image required")
        if len(v) > MAX_IMAGE_BYTES * 1.4 * MAX_GARMENTS:
            raise ValueError("person image too large")
        return v


# ==============================================================================
# Handlers (deployment-agnostic; take the engine holder)
# ==============================================================================
def handle_health(holder: EngineHolder) -> dict:
    # torch is optional HERE only so CPU-only hosts (contract tests, local
    # dev) can serve/report health; the real deployments always ship torch.
    try:
        import torch
    except ImportError:  # pragma: no cover - CPU-only host
        torch = None
    cuda = bool(torch is not None and torch.cuda.is_available())
    status = "healthy" if holder.model_loaded else "degraded"
    device = holder.device_name or ("cuda" if cuda else "cpu")
    gpu_mem = {}
    if cuda:
        try:
            gpu_mem = {
                "allocated_gb": round(torch.cuda.memory_allocated() / 1024**3, 2),
                "reserved_gb": round(torch.cuda.memory_reserved() / 1024**3, 2),
            }
        except Exception:
            pass
    meta = holder.engine.metadata() if holder.engine else {}
    return {
        "status": status,
        "service": "vton-worker (fashn_v15, multi-garment)",
        "engine": "fashn_v15",
        "model": meta.get("model", "fashn-vton-v1.5 (MMDiT 972M, pristine upstream 7c0f10af)"),
        "model_loaded": holder.model_loaded,
        "load_error": holder.load_error,
        "device": device,
        "cuda_available": cuda,
        "gpu_memory": gpu_mem,
        "git_sha": os.environ.get("CONFIT_GIT_SHA", "unknown"),
        "parser": _parser_info(),
        "multigarment": True,
        "max_garments": MAX_GARMENTS,
        "garment_photo_types": ["flat-lay", "model"],
        "commercial": False,  # honest: parser is non-commercial until swapped
        "ready": holder.model_loaded,
        "timestamp": time.time(),
    }


def handle_readiness(holder: EngineHolder) -> dict:
    if not holder.model_loaded:
        raise _err(
            503, "VTON_NOT_READY", "Model not loaded, worker not ready",
            load_error=holder.load_error, ready=False,
        )
    return {"ready": True, "engine": "fashn_v15", "model_loaded": True, "multigarment": True}


def handle_process(
    holder: EngineHolder,
    payload: VTONJobRequest,
    x_vton_admin: Optional[str],
) -> dict:
    # Authentication — same token convention as the Modal deployment
    # (env or Baseten secrets file; never logged, never returned).
    expected = _expected_admin_token()
    if not expected or x_vton_admin != expected:
        raise _err(401, "UNAUTHORIZED", "Missing or wrong X-VTON-Admin header.")
    if not holder.model_loaded:
        raise _err(
            503, "VTON_ENGINE_UNAVAILABLE", "Reason: engine not loaded",
            details=holder.load_error,
        )

    start_total = time.time()
    request_id = payload.job_id

    # Person image (validated, SSRF-safe)
    try:
        person = _fetch_image(payload.user_image_base64_or_url, "person image")
    except HTTPException:
        raise
    except Exception as e:
        raise _err(422, "INPUT_INVALID", f"Invalid person image: {type(e).__name__}: {str(e)[:200]}")

    # Garment images (validated, SSRF-safe, per garment)
    garments: List[Dict[str, Any]] = []
    for gi, g in enumerate(payload.garments):
        g_ref = g.get("image_base64") or g.get("image_url") or ""
        try:
            image = _fetch_image(g_ref, f"garment {gi} image")
        except HTTPException:
            raise
        except Exception as e:
            raise _err(422, "INPUT_INVALID", f"Invalid garment {gi} image: {type(e).__name__}: {str(e)[:200]}")
        garments.append({
            "image": image,
            "slot_type": g.get("slot_type") or g.get("category"),
            "product_id": g.get("product_id"),
            "photo_type": g.get("photo_type"),
        })

    # Multi-garment composition (single GPU call, honest per-layer verify)
    try:
        import torch
    except ImportError:
        # A host without torch cannot run inference — honest, named, and
        # classified exactly like any other engine-unavailable condition.
        raise _err(503, "VTON_ENGINE_UNAVAILABLE", "torch is not available on this host")
    start_inference = time.time()
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        rendered, layers_meta = holder.engine.render_outfit(
            person_image=person,
            garments=garments,
            seed=42,
            num_timesteps=30,
            overlay_mode=payload.overlay_mode,
        )
        inference_s = round(time.time() - start_inference, 3)
    except ValueError as e:
        # Conflicting/unsupported garment combinations from the engine
        raise _err(422, "INPUT_INVALID", str(e)[:300], job_id=request_id)
    except torch.cuda.OutOfMemoryError as e:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        raise _err(503, "GPU_OOM", f"GPU OOM: {e}", job_id=request_id)
    except RuntimeError as e:
        # A layer failed honest output verification — the outfit was NOT
        # genuinely applied; report it, never fake a success.
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        raise _err(500, "OUTPUT_INVALID", f"Layer verification failed: {str(e)[:300]}", job_id=request_id)
    except Exception as e:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        raise _err(500, "INFERENCE_FAILED", f"Inference failed: {type(e).__name__}: {str(e)[:300]}", job_id=request_id)

    # Encode output
    try:
        buf = io.BytesIO()
        rendered.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        rendered_data_url = "data:image/png;base64," + b64
    except Exception as e:
        raise _err(500, "OUTPUT_INVALID", f"Failed to encode output: {e}", job_id=request_id)

    if rendered_data_url == payload.user_image_base64_or_url:
        raise _err(500, "OUTPUT_INVALID", "Model returned input unchanged (echo)", job_id=request_id)

    # Final-image verification vs the ORIGINAL person (whole-outfit change)
    verify: Dict[str, Any] = {"PASS": None}
    try:
        verify = verify_output(person, rendered)
    except Exception as e:
        print(f"[process] verify failed job {request_id}: {e}", flush=True)

    all_layers_verified = all(
        (l.get("verify") or {}).get("PASS") for l in layers_meta
    ) and len(layers_meta) == len(payload.garments)

    total_ms = round((time.time() - start_total) * 1000, 1)
    print(
        f"[process] SUCCESS job={request_id} garments={len(payload.garments)} "
        f"categories={[l['category'] for l in layers_meta]} overlay={payload.overlay_mode} "
        f"inference_s={inference_s} total_ms={total_ms} "
        f"all_layers_verified={all_layers_verified} verify_pass={verify.get('PASS')}",
        flush=True,
    )

    return {
        "job_id": payload.job_id,
        "status": "completed",
        "rendered_image_data_url": rendered_data_url,
        "execution_time_ms": round(inference_s * 1000, 1),
        "total_time_ms": total_ms,
        "model_used": "fashn-vton-v1.5 (fashn_v15 multi-garment, parser-enabled; upstream 7c0f10af)",
        "engine": "fashn_v15",
        "layers_processed": len(layers_meta),
        "layers": layers_meta,
        "all_layers_verified": all_layers_verified,
        "verify": verify,
        "parser": _parser_info(),
        "commercial": False,
        "overlay_mode": payload.overlay_mode,
    }


def verify_output(original: Image.Image, rendered: Image.Image) -> dict:
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


# ==============================================================================
# FastAPI app factory (Baseten custom-Docker deployment; uvicorn serves this)
# ==============================================================================
def create_app(holder: EngineHolder) -> FastAPI:
    app = FastAPI(title="CONFIT VTON worker (fashn_v15)", version="1.0")

    @app.get("/health")
    def health() -> JSONResponse:
        # Never a 500 on health: a failed load reports degraded, not a crash —
        # the Baseten liveness probe must not kill an honestly-degraded pod.
        return JSONResponse(handle_health(holder))

    @app.get("/readiness")
    def readiness() -> JSONResponse:
        payload = handle_readiness(holder)  # raises HTTPException 503 if cold
        return JSONResponse(payload)

    @app.post("/process")
    def process(
        payload: VTONJobRequest,
        x_vton_admin: Optional[str] = Header(None, alias="X-VTON-Admin"),
    ) -> dict:
        return handle_process(holder, payload, x_vton_admin)

    return app
