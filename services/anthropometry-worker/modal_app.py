# ==============================================================================
# CONFIT ANTHROPOMETRY WORKER (FEATURE 05) — CPU Modal deployment.
#
# Pipeline (all real, no fabrication):
#   1. MediaPipe Pose Landmarker heavy (Apache-2.0) — 33 world landmarks from
#      a single full-body photo, on CPU (~1-3s).
#   2. landmark_mapping.py — 33 observed joints -> 73-point CAESAR cloud (mm):
#      direct joints + demo-calibrated scaffolds + girdle widening + mirrored
#      back points. Pure, fully unit-tested.
#   3. Vendored Landmarks2Anthropometry (VISAPP 2024) Bayesian-ridge bundles
#      (male.pkl / female.pkl @ de2df48) — 11 measurements.
#   4. Direct-geometry measurements (stature, inseam, arm lengths) computed
#      purely from the observed landmarks, reported with source labels.
#   5. Honest refusals: no pose / low visibility / out-of-envelope pose /
#      implausible output -> HTTP 422 with actionable guidance. NEVER garbage.
#
# MANDATORY product disclosure on every response: ±2-3 cm accuracy note +
# disclaimer + landmark_source=mediapipe_pose_world_approx +
# license=unlicensed-research-only + commercial=false (upstream has no
# license file — pilot tier only).
#
# Contract (same hardened shell as the wardrobe worker):
#   POST /estimate  X-VTON-Admin auth ->
#     {job_id, image_base64_or_url, sex, height_cm?}
#     -> measurements[{name, value_mm, value_cm, source: model|direct_geometry}],
#        accuracy_note, disclaimer, pose_quality, scale_calibration, engine, timings
#   GET /health | /readiness (public)
#
# Deploy: modal deploy services/anthropometry-worker/modal_app.py
# ==============================================================================

import base64
import io
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

import numpy as np
import modal
from fastapi import HTTPException, Header
from pydantic import BaseModel, field_validator

# Pure logic lives next to this file (importable without modal for tests).
# Modal introspects THIS file during the image build (before add_local_dir
# lands), so imports of the sibling modules are defensive.
try:
    import anthropometry_core as core  # noqa: E402
    import landmark_mapping as lm  # noqa: E402
except ImportError:  # build-time introspection context
    core = None
    lm = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_VENDOR = os.path.join(_REPO, "vendor", "landmarks2anthropometry", "upstream")

# MediaPipe Pose Landmarker heavy (Apache-2.0), float16 bundle (~29MB).
POSE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
                  "pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task")

app = modal.App("confit-anthropometry-worker")

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MIN_IMAGE_BYTES = 100
MAX_IMAGE_DIMENSION = 4096
MIN_IMAGE_DIMENSION = 32


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


def _bake_assets() -> None:
    """Download the pose model during the image build so cold starts never
    pay for downloads."""
    import urllib.request

    os.makedirs("/root/models", exist_ok=True)
    urllib.request.urlretrieve(POSE_MODEL_URL, "/root/models/pose_landmarker_heavy.task")


_image = (
    # Python 3.11: mediapipe ships wheels for <=3.12; the vendored model pins
    # (joblib 1.3.2 / numpy 1.26.2 / scikit-learn 1.3.2 / scipy 1.11.4, the
    # stack the upstream repository declares and that locally reproduces the
    # README demo output) are all 3.11-compatible. numpy<2 keeps mediapipe
    # and the vendored stack on the same ABI.
    modal.Image.debian_slim(python_version="3.11")
    # libgl1/libglib2.0: mediapipe's OpenCV dependency needs them (the slim
    # image ships neither — verified by the first deploy's load error).
    .apt_install("libgl1", "libglib2.0")
    .pip_install(
        "joblib==1.3.2", "numpy==1.26.2", "scikit-learn==1.3.2", "scipy==1.11.4",
        "mediapipe==0.10.14", "pillow>=10.0", "fastapi>=0.115.0",
        "pydantic>=2.9.0", "httpx>=0.27.2",
    )
    .run_function(_bake_assets)
    .add_local_dir(_HERE, remote_path="/root/anthropometry-worker", copy=True)
    .add_local_dir(_VENDOR, remote_path="/root/l2a", copy=True)
    .env({
        "PYTHONPATH": "/root/anthropometry-worker:",
        "CONFIT_ANTHROPOMETRY_VENDOR_DIR": "/root/l2a",
        "CONFIT_GIT_SHA": BUILD_GIT_SHA,
    })
)


class EstimateRequest(BaseModel):
    job_id: str
    image_base64_or_url: str
    sex: str
    height_cm: Optional[float] = None

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("job_id must be 1-100 chars")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("job_id contains invalid characters")
        return v

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v):
        if v not in ("male", "female"):
            raise ValueError("sex must be 'male' or 'female'")
        return v

    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v):
        if v is not None and not 50 <= v <= 260:
            raise ValueError("height_cm must be 50-260 cm")
        return v

    @field_validator("image_base64_or_url")
    @classmethod
    def validate_image(cls, v):
        if not v or len(v) > MAX_IMAGE_BYTES * 1.4:
            raise ValueError("image required (and within size limits)")
        return v


def _is_safe_url(raw: str) -> bool:
    """SSRF guard (same policy as the wardrobe/VTON workers)."""
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


def _fetch_image(ref: str, context: str = "image"):
    from PIL import Image

    if ref.startswith("data:image"):
        header, b64 = ref.split(",", 1)
        return _validate_and_decode_image(base64.b64decode(b64), context)
    if not _is_safe_url(ref):
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Unsafe {context} URL"}})
    import httpx
    try:
        r = httpx.get(ref, timeout=30.0, follow_redirects=True, headers={"User-Agent": "CONFIT-ANTHROPOMETRY/1.0"})
        r.raise_for_status()
        return _validate_and_decode_image(r.content, context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail={"error": {"code": "INPUT_INVALID", "message": f"Failed to fetch {context}: {str(e)[:200]}"}})


@app.cls(
    cpu=2.0,
    # 4GB: pose_landmarker_heavy ~0.5GB peak + sklearn bundles (8MB) — plenty.
    memory=4096,
    image=_image,
    # Dedicated credential for feature 05 (rotatable without touching the
    # wardrobe/VTON workers). The backend sends it via
    # ANTHROPOMETRY_WORKER_ADMIN_TOKEN / X-VTON-Admin.
    secrets=[modal.Secret.from_name("confit-anthropometry-admin-token")],
    scaledown_window=300,
    # min_containers=0: occasional usage; CPU cold start (~10-20s) is honest
    # and cheap. A warm container would burn starter credits idle.
)
@modal.concurrent(max_inputs=1)  # one estimation per container; scale out, not in
class AnthropometryService:
    """Feature 05 — pose landmarks -> CAESAR cloud -> Bayesian-ridge measurements."""

    @modal.enter()
    def load_models(self) -> None:
        self.ready = False
        self.load_error = None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            options = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(
                    model_asset_path="/root/models/pose_landmarker_heavy.task"),
                output_segmentation_masks=False,
            )
            self.detector = vision.PoseLandmarker.create_from_options(options)
            # Warm both vendored bundles now (fail fast at start, not per call).
            core.load_models()
            self.ready = True
            print("[load] pose_landmarker_heavy + Landmarks2Anthropometry (m/f) loaded on CPU", flush=True)
        except Exception as exc:
            import traceback as _tb
            self.load_error = f"{type(exc).__name__}: {exc}"
            _tb.print_exc()
            print(f"[load] MODEL LOAD FAILED: {self.load_error}", flush=True)

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        return {
            "status": "healthy" if self.ready else "degraded",
            "service": "anthropometry-worker",
            "engine": core.ENGINE if core else "landmarks2anthropometry_visapp2024_cpu",
            "models": {
                "pose": "mediapipe pose_landmarker_heavy (Apache-2.0)",
                "measurements": "Landmarks2Anthropometry VISAPP 2024 @ de2df48",
                "license": "unlicensed-research-only",
            },
            "model_loaded": self.ready,
            "load_error": self.load_error,
            "device": "cpu",
            "git_sha": os.environ.get("CONFIT_GIT_SHA", "unknown"),
            "commercial": False,
            "accuracy_note": core.ACCURACY_NOTE if core else "±2-3 cm",
            "ready": self.ready,
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="GET")
    def readiness(self) -> dict:
        if not self.ready:
            raise HTTPException(status_code=503, detail={"error": {"code": "ANTHROPOMETRY_NOT_READY", "message": "Models not loaded", "load_error": self.load_error}, "ready": False})
        return {"ready": True, "engine": core.ENGINE if core else "landmarks2anthropometry_visapp2024_cpu"}

    @modal.fastapi_endpoint(method="POST")
    def estimate(self, payload: EstimateRequest, x_vton_admin: Optional[str] = Header(None, alias="X-VTON-Admin")) -> dict:
        expected = os.environ.get("ANTHROPOMETRY_WORKER_ADMIN_TOKEN", "")
        if not expected or x_vton_admin != expected:
            raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Missing or wrong X-VTON-Admin header."}})
        if not self.ready:
            raise HTTPException(status_code=503, detail={"error": {"code": "ANTHROPOMETRY_ENGINE_UNAVAILABLE", "message": "Models not loaded", "details": self.load_error}})

        image = _fetch_image(payload.image_base64_or_url, "body photo")

        # ── 1. MediaPipe pose ────────────────────────────────────────────
        import mediapipe as mp

        t0 = time.time()
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(image))
        result = self.detector.detect(mp_image)
        pose_s = round(time.time() - t0, 3)

        if not result.pose_world_landmarks:
            raise HTTPException(status_code=422, detail={
                "error": {"code": "NO_USABLE_POSE",
                          "message": "no person detected — please upload a clear full-body photo"}})
        wl = [[l.x, l.y, l.z] for l in result.pose_world_landmarks[0]]
        vis = [float(l.visibility) for l in result.pose_landmarks[0]]

        # ── 2-5. mapping + model + honesty gates (pure core) ─────────────
        try:
            response = core.estimate(wl, vis, payload.sex, payload.height_cm)
        except core.EstimationRefused as e:
            raise HTTPException(status_code=422, detail={
                "error": {"code": e.code, "message": e.message, "details": e.details}})

        response.update({
            "job_id": payload.job_id,
            "pose_seconds": pose_s,
        })
        response["timings"]["total_seconds"] = round(pose_s + response["timings"]["total_seconds"], 3)
        print(
            f"[estimate] job={payload.job_id} sex={payload.sex} n={response['measurement_count']} "
            f"pose_s={pose_s} model_s={response['timings']['model_seconds']} "
            f"scale={'user' if response['scale_calibration']['applied'] else 'mp'}",
            flush=True,
        )
        return response
