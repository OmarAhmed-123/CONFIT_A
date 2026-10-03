# ==============================================================================
# CONFIT WARDROBE WORKER (FEATURE 04) — CPU Modal deployment.
#
# Models (owner assignment 2026-10-01, both MIT):
#   * SCHP-ATR-18  — pirocheto/schp-atr-18 (Self-Correction Human Parsing,
#     ATR 18 classes, mIoU 82.29, 66.8M params) — garment parsing.
#   * BiRefNet_lite — ZhengPeng7/BiRefNet_lite (44.4M params) — high-quality
#     per-garment matting/cutouts.
#
# WHY CPU (2026-10-02): Modal's payment gate blocks every GPU deployment on
# this workspace (new AND existing apps) while CPU deployments are allowed.
# Both models are light enough for CPU inference (SCHP 512² ~2-5s,
# BiRefNet_lite 1024² ~3-8s per garment) — a wardrobe import taking 10-30s
# is an acceptable product trade for real (not illusory) extraction. When a
# payment method lands, flipping gpu="A10G" on this app is a one-line change.
#
# Contract (same hardened shell as the VTON workers):
#   POST /extract  X-VTON-Admin auth -> {job_id, image(base64|url), max_items}
#     -> items[{slot_type, category, label_names, bbox, area_fraction,
#               confidence, cutout_data_url}], person_detected, skipped[],
#     honest per-item provenance; NO fabricated items (below-threshold
#     regions are reported as skipped, never promoted).
#   GET /health | /readiness (public)
#
# Deploy: modal deploy services/wardrobe-worker/modal_app.py
# ==============================================================================

import base64
import io
import os
import subprocess
import time
from typing import Any, Dict, List

import modal
from fastapi import HTTPException, Header
from pydantic import BaseModel, field_validator

# Pure logic lives in extraction.py (importable without modal/torch for
# tests). Imported lazily/defensively: Modal introspects THIS file during
# the image build (before add_local_dir lands), so a hard module-level
# import would break the build. The runtime image ships extraction.py on
# PYTHONPATH (/root/wardrobe-worker).
try:
    import extraction as ex  # noqa: E402
except ImportError:  # build-time introspection context
    ex = None

# Local dir containing extraction.py. In the builder's introspection context
# __file__ points at /root/modal_app.py; the serialized Image from the client
# import (correct local path) is what actually gets built (same pattern as
# modal_app_v15.py, which builds fine).
_HERE = os.path.dirname(os.path.abspath(__file__))

# Request-level bound for max_items (the grouping cap extraction.MAX_ITEMS
# governs how many grouped items may be returned; keep both in sync).
MAX_ITEMS_REQUEST = 6

app = modal.App("confit-wardrobe-worker")

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MIN_IMAGE_BYTES = 100
MAX_IMAGE_DIMENSION = 4096
MIN_IMAGE_DIMENSION = 32

SCHP_MODEL_ID = "pirocheto/schp-atr-18"
BIREFNET_MODEL_ID = "ZhengPeng7/BiRefNet_lite"


def _resolve_build_git_sha() -> str:
    explicit = os.environ.get("CONFIT_GIT_SHA", "").strip()
    if explicit:
        return explicit
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here, capture_output=True, text=True, timeout=10).stdout.strip()
        if not sha:
            return "unknown"
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=here, capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except Exception:
        return "unknown"


BUILD_GIT_SHA = _resolve_build_git_sha()


def _bake_weights() -> None:
    """Resolve both models during the image build so cold starts never pay
    for downloads (same pattern as the moda-embed worker)."""
    from transformers import AutoModelForSemanticSegmentation, AutoModelForImageSegmentation, AutoImageProcessor

    AutoModelForSemanticSegmentation.from_pretrained(SCHP_MODEL_ID, trust_remote_code=True)
    AutoImageProcessor.from_pretrained(SCHP_MODEL_ID, trust_remote_code=True)
    AutoModelForImageSegmentation.from_pretrained(BIREFNET_MODEL_ID, trust_remote_code=True)


_image = (
    # Stack verified locally 2026-10-02 (see session memory): pirocheto/schp-atr-18
    # was modernized 2026-04 for transformers>=5.5.3 / torch>=2.11 / pillow>=12.2
    # (its config.json says transformers_version 5.5.0) and FAILS to import on
    # the old 4.46.3 stack ("ImportError: configuration_schp"). BiRefNet_lite's
    # custom code loads fine on transformers 5.18 but needs einops+kornia+timm.
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch>=2.11", "torchvision>=0.26",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install(
        "transformers>=5.5.3", "pillow>=12.2", "numpy<3",
        "huggingface_hub>=0.25", "fastapi>=0.115.0", "pydantic>=2.9.0",
        "httpx>=0.27.2", "einops", "kornia", "timm",
    )
    .run_function(_bake_weights)
    .add_local_dir(_HERE, remote_path="/root/wardrobe-worker", copy=True)
    .env({"PYTHONPATH": "/root/wardrobe-worker:", "CONFIT_GIT_SHA": BUILD_GIT_SHA})
)


class ExtractionRequest(BaseModel):
    job_id: str
    image_base64_or_url: str
    max_items: int = 4

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("job_id must be 1-100 chars")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("job_id contains invalid characters")
        return v

    @field_validator("max_items")
    @classmethod
    def validate_max_items(cls, v):
        if not 1 <= v <= MAX_ITEMS_REQUEST:
            raise ValueError(f"max_items must be 1..{MAX_ITEMS_REQUEST}")
        return v

    @field_validator("image_base64_or_url")
    @classmethod
    def validate_image(cls, v):
        if not v or len(v) > MAX_IMAGE_BYTES * 1.4:
            raise ValueError("image required (and within size limits)")
        return v


def _is_safe_url(raw: str) -> bool:
    """SSRF guard (same policy as the VTON workers)."""
    import ipaddress
    import socket
    import urllib.parse as _urlparse

    if not isinstance(raw, str) or not raw:
        return False
    try:
        u = _urlparse.urlparse(raw)
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    host = u.hostname
    if not host or host.lower() in {"localhost", "metadata.google.internal", "169.254.169.254"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        for _, _, _, _, sockaddr in infos:
            try:
                ip = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                return False
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False
    return True


def _validate_and_decode_image(raw: bytes, context: str = "image"):
    from PIL import Image

    if len(raw) < MIN_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} too small"}})
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} too large"}})
    try:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w * h > MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION or w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"{context} dimensions invalid"}})
        img.verify()
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Invalid {context}: {type(e).__name__}: {str(e)[:200]}"}})


def _fetch_image(ref: str, context: str):
    from PIL import Image

    if ref.startswith("data:image"):
        header, b64 = ref.split(",", 1)
        return _validate_and_decode_image(base64.b64decode(b64), context)
    if not _is_safe_url(ref):
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Unsafe {context} URL"}})
    import httpx
    try:
        r = httpx.get(ref, timeout=30.0, follow_redirects=True, headers={"User-Agent": "CONFIT-WARDROBE/1.0"})
        r.raise_for_status()
        return _validate_and_decode_image(r.content, context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Failed to fetch {context}: {str(e)[:200]}"}})


@app.cls(
    cpu=4.0,
    # 16GB: BiRefNet_lite at 1024² on CPU OOM-killed a small-RAM probe
    # process; this leaves honest headroom for a parse + up to 6 mattes.
    memory=16384,
    image=_image,
    # Dedicated credential for feature 04: rotating/inspecting the wardrobe
    # token can never affect the frozen VTON workers (and vice versa). The
    # backend sends it via WARDROBE_WORKER_ADMIN_TOKEN / X-VTON-Admin.
    secrets=[modal.Secret.from_name("confit-wardrobe-admin-token")],
    scaledown_window=300,
    # min_containers=0: wardrobe imports are occasional; a CPU cold start
    # (~20-40s model load from the baked image) is honest and cheap. Setting
    # a warm container would burn ~$10+/month of the starter credits idle.
)
@modal.concurrent(max_inputs=1)  # one extraction per container; scale out, not in
class WardrobeExtractionService:
    """Feature 04 — SCHP-ATR-18 parsing + BiRefNet_lite cutouts on CPU."""

    @modal.enter()
    def load_models(self) -> None:
        import torch
        from transformers import AutoModelForSemanticSegmentation, AutoModelForImageSegmentation, AutoImageProcessor
        from torchvision import transforms

        self.ready = False
        self.load_error = None
        try:
            self.schp = AutoModelForSemanticSegmentation.from_pretrained(SCHP_MODEL_ID, trust_remote_code=True)
            self.schp.eval()
            self.schp_processor = AutoImageProcessor.from_pretrained(SCHP_MODEL_ID, trust_remote_code=True)
            self.birefnet = AutoModelForImageSegmentation.from_pretrained(BIREFNET_MODEL_ID, trust_remote_code=True)
            self.birefnet.eval()
            self.birefnet_transform = transforms.Compose([
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])
            self.id2label = self.schp.config.id2label
            self.ready = True
            print(f"[load] SCHP-ATR-18 + BiRefNet_lite loaded on CPU (labels={len(self.id2label)})", flush=True)
        except Exception as exc:
            import traceback as _tb
            self.load_error = f"{type(exc).__name__}: {exc}"
            _tb.print_exc()
            print(f"[load] MODEL LOAD FAILED: {self.load_error}", flush=True)

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        return {
            "status": "healthy" if self.ready else "degraded",
            "service": "wardrobe-worker",
            "engine": "schp_atr_18_birefnet_lite_cpu",
            "models": {
                "parser": SCHP_MODEL_ID,
                "matting": BIREFNET_MODEL_ID,
                "parser_license": "MIT (pirocheto/schp-atr-18 packaging; SCHP ATR)",
                "matting_license": "MIT (ZhengPeng7/BiRefNet_lite)",
            },
            "model_loaded": self.ready,
            "load_error": self.load_error,
            "device": "cpu",
            "git_sha": os.environ.get("CONFIT_GIT_SHA", "unknown"),
            "commercial": True,  # both MIT
            "ready": self.ready,
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="GET")
    def readiness(self) -> dict:
        if not self.ready:
            raise HTTPException(status_code=503, detail={"error": {"code": "WARDROBE_NOT_READY", "message": "Models not loaded", "load_error": self.load_error}, "ready": False})
        return {"ready": True, "engine": "schp_atr_18_birefnet_lite_cpu"}

    @modal.fastapi_endpoint(method="POST")
    def extract(self, payload: ExtractionRequest, x_vton_admin: str | None = Header(None, alias="X-VTON-Admin")) -> dict:
        expected = os.environ.get("VTON_WORKER_ADMIN_TOKEN") or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN", "")
        if not expected or x_vton_admin != expected:
            raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Missing or wrong X-VTON-Admin header."}})
        if not self.ready:
            raise HTTPException(status_code=503, detail={"error": {"code": "WARDROBE_ENGINE_UNAVAILABLE", "message": "Models not loaded", "details": self.load_error}})

        start = time.time()
        try:
            image = _fetch_image(payload.image_base64_or_url, "wardrobe image")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Invalid image: {str(e)[:200]}"}})

        import numpy as np
        import torch
        from PIL import Image

        W, H = image.size
        image_area = W * H

        # ── 1. SCHP-ATR-18 parse ─────────────────────────────────────────
        t0 = time.time()
        try:
            inputs = self.schp_processor(images=image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.schp(**inputs)
            logits = getattr(outputs, "logits", None)
            if logits is None:
                raise RuntimeError("SCHP returned no logits")
            seg = logits.argmax(dim=1).squeeze(0).byte().numpy()  # (512,512)
            # Resize the label map back to the image size (nearest = no label bleeding)
            seg_full = np.asarray(
                Image.fromarray(seg).resize((W, H), Image.NEAREST)
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error": {"code": "INFERENCE_FAILED", "message": f"SCHP parse failed: {type(e).__name__}: {str(e)[:200]}", "job_id": payload.job_id}})
        parse_s = round(time.time() - t0, 2)

        # ── 2. group ATR regions into wardrobe items (pure logic) ────────
        label_masks = [
            (str(self.id2label[int(l)]), (seg_full == int(l)).astype(np.uint8))
            for l in np.unique(seg_full)
        ]
        items, report = ex.group_regions(label_masks, image_area)

        # ── 3. BiRefNet cutout per item ─────────────────────────────────
        out_items: List[Dict[str, Any]] = []
        matting_s = 0.0
        for it in items[: payload.max_items]:
            # combined mask for the (possibly multi-label) item
            combined = np.zeros((H, W), dtype=np.uint8)
            for m in it["masks"]:
                combined |= m
            left, top, right, bottom = ex.bbox_of_mask(combined)
            if right <= left or bottom <= top:
                continue
            pad = int(0.05 * max(right - left, bottom - top))
            left, top = max(0, left - pad), max(0, top - pad)
            right, bottom = min(W, right + pad), min(H, bottom + pad)

            t1 = time.time()
            crop = image.crop((left, top, right, bottom))
            try:
                with torch.no_grad():
                    res = self.birefnet(self.birefnet_transform(crop).unsqueeze(0))
                # BiRefNet returns a list/tuple of predictions under inference
                pred = res[-1] if isinstance(res, (list, tuple)) else getattr(res, "logits", res)
                mask = torch.sigmoid(pred).squeeze().cpu().numpy()
                if mask.ndim == 3:
                    mask = mask[0]
            except Exception as e:
                raise HTTPException(status_code=500, detail={"error": {"code": "INFERENCE_FAILED", "message": f"BiRefNet matting failed: {type(e).__name__}: {str(e)[:200]}", "job_id": payload.job_id}})
            matting_s += time.time() - t1

            cutout = ex.compose_cutout(crop, mask)
            buf = io.BytesIO()
            cutout.save(buf, format="PNG")
            data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

            out_items.append({
                "slot_type": it["slot_type"],
                "category": it["category"],
                "label_names": it["label_names"],
                "bbox": [left, top, right, bottom],
                "area_fraction": round(it["area"] / image_area, 4),
                "confidence": ex.item_confidence(it["area"], image_area),
                "cutout_data_url": data_url,
            })

        total_s = round(time.time() - start, 2)
        print(
            f"[extract] job={payload.job_id} items={len(out_items)} person={report['person_detected']} "
            f"skipped={len(report['skipped'])} parse_s={parse_s} matting_s={round(matting_s,2)} total_s={total_s}",
            flush=True,
        )
        return {
            "job_id": payload.job_id,
            "status": "completed",
            "items": out_items,
            "person_detected": report["person_detected"],
            "person_labels": report["person_labels"],
            "skipped": report["skipped"],
            "engine": "schp_atr_18_birefnet_lite_cpu",
            "model_used": f"{SCHP_MODEL_ID} + {BIREFNET_MODEL_ID} (MIT)",
            "parse_seconds": parse_s,
            "matting_seconds": round(matting_s, 2),
            "total_seconds": total_s,
            "commercial": True,
        }
