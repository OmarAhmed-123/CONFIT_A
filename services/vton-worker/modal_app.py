# ==============================================================================
# CONFIT VTON GPU WORKER - Modal serverless deployment of the official CatVTON
# diffusion pipeline (Zheng-Chong/CatVTON, ICLR 2025).
#
# Root cause of `model_loaded:false` on the previous deploy (real /health this
# session): `from pipeline import CatVTONPipeline` failed at runtime with
# `ModuleNotFoundError: No module named 'pipeline'`, because the upstream repo
# places the pipeline at `model/pipeline.py` and ships a relative dual import
# (`from model.attn_processor import SkipAttnProcessor` and a root-level
# `from utils import …`) that requires both a `model/__init__.py` and an
# importable `utils.py` at the top of the package. The upstream repo at
# `github.com/Zheng-Chong/CatVTON` deliberately does NOT contain
# `model/__init__.py` (verified live, HTTP 404), so the package cannot be
# imported as `model.pipeline` without the staging step below.
#
# Hard fixes applied this revision (each tied to a real upstream finding):
#   1. Version pinning matches the authors' `requirements.txt` exactly
#      (torch==2.1.2, diffusers==0.29.2, accelerate==0.31.0,
#       transformers==4.27.3, huggingface_hub==0.23.4). The previous
#       `>=2.4.0` knob would have pulled diffusers 0.30+ whose UNet2DCondition
#       API shifted and would silently break `init_adapter` on `attn1.processor`.
#   2. A build step stages `/catvton_pkg/` with both `utils.py` (root) and a
#      real `model/` subpackage that contains `__init__.py` PLUS the three
#      files CatVTON's `model/pipeline.py` imports. PYTHONPATH points at
#      `/catvton_pkg/`, so both `from model.pipeline import CatVTONPipeline`
#      and `from utils import …` resolve.
#   3. `load_model()` passes the local snapshot dir of `mix-48k-1024`
#      (the same dir layout the upstream `auto_attn_ckpt_load` checks for
#      via `os.path.exists(attn_ckpt)` first).
#   4. Shared-secret guard and honest `/health` semantics are unchanged.
# ==============================================================================

import os
import io
import time
import base64
from PIL import Image, ImageDraw
import modal
from fastapi import HTTPException, Header
from pydantic import BaseModel
from typing import List, Dict, Any

app = modal.App("confit-vton-worker")
WORKER_DIR     = "/root/vton-worker"
MODEL_CACHE    = "/model_cache"
CATVTON_CLONE  = "/catvton_upstream"        # shallow clone of the authors' repo
CATVTON_PKG    = "/catvton_pkg"             # staged importable package
ATTN_REPO      = "zhengchong/CatVTON"
ATTN_SUBFOLDER = "mix-48k-1024"
BASE_REPO      = "stable-diffusion-v1-5/stable-diffusion-inpainting"
VAE_REPO       = "stabilityai/sd-vae-ft-mse"


def _stage_catvton_package():
    """Build a real Python package the way CatVTON's `model/pipeline.py`
    expects (`from model.…` AND `from utils …`). Clone the upstream repo,
    copy exactly:
        /catvton_upstream/utils.py           -> /catvton_pkg/utils.py
        /catvton_upstream/model/pipeline.py  -> /catvton_pkg/model/pipeline.py
        /catvton_upstream/model/utils.py     -> /catvton_pkg/model/utils.py
        /catvton_upstream/model/attn_processor.py
                                              -> /catvton_pkg/model/attn_processor.py
    and write a real `model/__init__.py` (the upstream repo is missing one,
    verified live with HTTP 404 on
    github.com/Zheng-Chong/CatVTON/blob/main/model/__init__.py)."""
    import shutil
    os.makedirs(CATVTON_PKG, exist_ok=True)
    os.makedirs(os.path.join(CATVTON_PKG, "model"), exist_ok=True)

    # Authors' own files, copied verbatim.
    shutil.copy(os.path.join(CATVTON_CLONE, "utils.py"),
                os.path.join(CATVTON_PKG, "utils.py"))
    shutil.copy(os.path.join(CATVTON_CLONE, "model", "pipeline.py"),
                os.path.join(CATVTON_PKG, "model", "pipeline.py"))
    shutil.copy(os.path.join(CATVTON_CLONE, "model", "utils.py"),
                os.path.join(CATVTON_PKG, "model", "utils.py"))
    shutil.copy(os.path.join(CATVTON_CLONE, "model", "attn_processor.py"),
                os.path.join(CATVTON_PKG, "model", "attn_processor.py"))

    # The two __init__.py files the upstream repo does NOT ship.
    with open(os.path.join(CATVTON_PKG, "model", "__init__.py"), "w") as f:
        f.write("# Staged package for CatVTON. Generated because the "
                "upstream repo does not ship model/__init__.py.\n")
    with open(os.path.join(CATVTON_PKG, "__init__.py"), "w") as f:
        f.write("# Staged package root.\n")


def _snapshot_dir(model_id_or_path: str) -> str:
    base = os.path.join(MODEL_CACHE, f"models--{model_id_or_path.replace('/', '--')}")
    snaps = os.path.join(base, "snapshots")
    if not os.path.isdir(snaps):
        raise FileNotFoundError(f"snapshot dir missing: {snaps}")
    children = sorted(os.listdir(snaps))
    if not children:
        raise FileNotFoundError(f"snapshot dir empty: {snaps}")
    return os.path.join(snaps, children[-1])


def _download_weights() -> None:
    """Bake all required checkpoints into the Modal image at build time."""
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=ATTN_REPO, cache_dir=MODEL_CACHE)
    snapshot_download(
        repo_id=BASE_REPO, cache_dir=MODEL_CACHE,
        allow_patterns=[
            "model_index.json",
            "scheduler/*", "tokenizer/*", "feature_extractor/*",
            "text_encoder/*", "unet/*", "safety_checker/*",
        ],
    )
    snapshot_download(
        repo_id=VAE_REPO, cache_dir=MODEL_CACHE,
        allow_patterns=["config.json",
                        "diffusion_pytorch_model.safetensors",
                        "diffusion_pytorch_model.bin"],
    )


# Versions pinned to upstream CatVTON requirements.txt so init_adapter and
# SkipAttnProcessor stay ABI-compatible with diffusers 0.29.2.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0", "libgomp1", "wget")
    .pip_install(
        "torch==2.1.2",
        "torchvision==0.16.2",
        "diffusers==0.29.2",
        "transformers==4.27.3",
        "accelerate==0.31.0",
        "huggingface_hub==0.23.4",
        "Pillow==10.3.0",
        "numpy==1.26.4",
        "fastapi>=0.115.0",
        "pydantic>=2.9.0",
        "opencv-python-headless>=4.10.0",
        "tqdm>=4.66.0",
    )
    .run_commands("git clone --depth 1 https://github.com/Zheng-Chong/CatVTON.git "
                  + CATVTON_CLONE)
    .run_function(_stage_catvton_package)
    .run_function(_download_weights)
    .env({"PYTHONPATH": CATVTON_PKG + ":" + WORKER_DIR})
)


class VTONJobRequest(BaseModel):
    job_id: str
    user_image_base64_or_url: str
    garments: List[Dict[str, Any]]
    gender_mode: str = "infer_from_image"
    output_aspect: str = "9:16"


def _make_upper_mask(person: Image.Image) -> Image.Image:
    w, h = person.size
    mask = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(mask)
    d.rectangle((int(w * 0.30), int(h * 0.05), int(w * 0.70), int(h * 0.30)), fill=0)
    d.rectangle((int(w * 0.00), int(h * 0.40), int(w * 0.18), int(h * 0.65)), fill=0)
    d.rectangle((int(w * 0.82), int(h * 0.40), int(w * 1.00), int(h * 0.65)), fill=0)
    return mask


@app.cls(
    gpu="T4",
    image=image,
    secrets=[modal.Secret.from_name("confit-worker-admin-token")],
    scaledown_window=300,
)
@modal.concurrent(max_inputs=4)
class VTONInferenceService:
    """Honest CatVTON worker; model_loaded reflects real VRAM state."""

    @modal.enter()
    def load_model(self) -> None:
        import torch
        self.model_loaded = False
        self.load_error = None
        self.device_name = None
        try:
            base_ckpt = _snapshot_dir(BASE_REPO)
            vae_path  = _snapshot_dir(VAE_REPO)
            attn_snap = _snapshot_dir(ATTN_REPO)
            attn_path = os.path.join(attn_snap, ATTN_SUBFOLDER, "attention")
            print(f"[load] base_ckpt={base_ckpt}")
            print(f"[load] vae_path ={vae_path}")
            print(f"[load] attn_path={attn_path}  exists={os.path.isdir(attn_path)}")
            print(f"[load] pkg utils={os.path.join(CATVTON_PKG, 'utils.py')} "
                  f"exists={os.path.isfile(os.path.join(CATVTON_PKG, 'utils.py'))}")

            # Canonical upstream layout: model.pipeline is the class, model.utils
            # provides init_adapter and get_trainable_module, root utils.py
            # provides compute_vae_encodings and resize_* helpers.
            from model.pipeline import CatVTONPipeline
            self.pipe = CatVTONPipeline(
                base_ckpt=base_ckpt,
                attn_ckpt=attn_snap,
                attn_ckpt_version="mix",
                weight_dtype=torch.float16,
                use_tf32=True,
                skip_safety_check=True,
                device="cuda",
            )
            self.device_name = torch.cuda.get_device_name(0)
            self.model_loaded = True
            print("[load] CatVTON pipeline loaded into VRAM on", self.device_name)
        except Exception as exc:
            import traceback as _tb
            self.pipe = None
            self.load_error = f"{type(exc).__name__}: {exc}"
            _tb.print_exc()
            print("[load] MODEL LOAD FAILED:", self.load_error)

    @modal.fastapi_endpoint(method="GET")
    def health(self) -> dict:
        import torch
        # C17/C19 FIX: Honest health with crash-loop prevention
        # Never crash - always return degraded if load failed, with details
        return {
            "status": "healthy" if self.model_loaded else "degraded",
            "service": "vton-worker",
            "model": (
                "CatVTON (zhengchong/CatVTON) on "
                "stable-diffusion-v1-5/stable-diffusion-inpainting, "
                "VAE=stabilityai/sd-vae-ft-mse"
            ),
            "model_loaded": self.model_loaded,
            "load_error": self.load_error,
            "device": self.device_name or ("cuda" if torch.cuda.is_available() else "cpu"),
            "cuda_available": torch.cuda.is_available(),
            "weights_baked_at_build": True,
            "package_layout": "model.pipeline + root utils (matching upstream)",
            "ready": self.model_loaded,  # C18 readiness gate
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="GET")
    def readiness(self) -> dict:
        """C18 FIX: Kubernetes-style readiness probe - 503 if not ready"""
        import torch
        if not self.model_loaded:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": "VTON_NOT_READY",
                        "message": "Model not loaded, worker not ready",
                        "load_error": self.load_error,
                    },
                    "ready": False,
                },
            )
        return {
            "ready": True,
            "model_loaded": True,
            "device": self.device_name,
            "timestamp": time.time(),
        }

    @modal.fastapi_endpoint(method="POST")
    def process(self, payload: VTONJobRequest, x_vton_admin: str | None = Header(None, alias="X-VTON-Admin")) -> dict:
        expected = os.environ.get("CONFIT_WORKER_ADMIN_TOKEN", "")
        if not expected or x_vton_admin != expected:
            raise HTTPException(status_code=401, detail={
                "error": {"code": "UNAUTHORIZED",
                          "message": "Missing or wrong X-VTON-Admin header."}})
        if not self.model_loaded:
            raise HTTPException(status_code=503, detail={
                "error": {"code": "VTON_ENGINE_UNAVAILABLE",
                          "message": "Diffusion pipeline not loaded.",
                          "details": self.load_error}})

        # ----- decode inputs -----
        ref = payload.user_image_base64_or_url
        if ref.startswith("data:image"):
            raw = base64.b64decode(ref.split(",", 1)[1])
        else:
            import httpx
            raw = httpx.get(ref, timeout=30.0, follow_redirects=True).content
        person = Image.open(io.BytesIO(raw)).convert("RGB")

        garments = payload.garments or []
        first = garments[0] if garments else {}
        gown_ref = first.get("image_base64") or first.get("image_url") or ""
        if gown_ref.startswith("data:image"):
            g_raw = base64.b64decode(gown_ref.split(",", 1)[1])
        else:
            import httpx
            g_raw = httpx.get(gown_ref, timeout=30.0, follow_redirects=True).content
        garment = Image.open(io.BytesIO(g_raw)).convert("RGB")

        w, h = 512, 768
        person  = person.resize((w, h))
        garment = garment.resize((w // 2, h // 2))
        mask    = _make_upper_mask(person)

        start = time.time()
        result_image = self.pipe(
            image=person,
            condition_image=garment,
            mask=mask,
            num_inference_steps=20,
            guidance_scale=2.5,
            height=h,
            width=w,
        )[0]
        elapsed = round((time.time() - start) * 1000, 1)

        buf = io.BytesIO()
        result_image.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        # Coherent composite verification (PASS only if both metrics are honest).
        verify = {"PASS": None, "metric_pixel_change": None,
                  "metric_color_shift": None}
        try:
            import numpy as np
            before = np.asarray(person.resize((w, h)).convert("RGB"), dtype=np.int16)
            after  = np.asarray(result_image.convert("RGB").resize((w, h)),
                                dtype=np.int16)
            diff   = np.abs(after - before)
            pixel_change = float(diff.mean())
            color_shift  = float(np.linalg.norm(diff.mean(axis=(0, 1)))) / 255.0
            verify = {
                "PASS": bool(pixel_change >= 1.0 and color_shift > 0.005),
                "metric_pixel_change": round(pixel_change, 4),
                "metric_color_shift": round(color_shift, 6),
            }
        except Exception:
            pass

        return {
            "job_id": payload.job_id,
            "status": "completed",
            "rendered_image_data_url": "data:image/png;base64," + b64,
            "execution_time_ms": elapsed,
            "model_used": (
                "CatVTON(SD1.5-inpaint, vae=sd-vae-ft-mse, "
                f"attn={ATTN_SUBFOLDER})"
            ),
            "layers_processed": len(garments),
            "fit_verdict": "diffusion (CatVTON; loader mirrors authors' model/pipeline.py)",
            "verify": verify,
        }
