# ==============================================================================
# CONFIT VTON GPU WORKER (FEATURE 03: MULTI-GARMENT) — Modal serverless
# deployment of the CONFIT_A `fashn_v15` engine.
#
# Runs the PRISTINE upstream fashn-vton-1.5 pipeline (Apache-2.0, @ 7c0f10af)
# WITH the fashn-human-parser, delivering:
#   * MULTI-GARMENT outfits in ONE call: tops + bottoms composed sequentially
#     (layer 1 segmentation-free, layer k>1 parser-masked so earlier layers
#     stay pixel-exact), honest per-layer verification in the response.
#   * MODEL-PHOTO garments: the parser segments a garment out of a worn
#     catalogue photo (auto-detected per garment) — no flat-lay-only limit.
#
# LICENSE RECORD (honest, owner-approved): the pipeline/DWPose/YOLOX are
# Apache-2.0; fashn-human-parser is NVIDIA SegFormer NON-COMMERCIAL. Project
# owner approved its early-stage use on 2026-10-01 with a licensed-parser swap
# planned before commercial scale. The parser is injectable via the engine's
# `parser_impl` seam (engine/fashn_v15.py) — the swap is one class.
#
# External contract (same endpoints/auth/error taxonomy as the segfee worker,
# so the API service keeps working unchanged during cutover):
#   * POST /process  with X-VTON-Admin auth -> VTONJobRequest (garments 1-3)
#     -> rendered_image_data_url + layers[] + verify + parser metadata
#   * GET  /health   (public) -> service/model_loaded/device/engine/parser
#   * GET  /readiness(public) -> 200 only when model loaded, else 503
#   * input validation (size/dim/decompression-bomb/format) + SSRF guard
#   * strict per-layer output validation (no echo, not blank, real change)
#   * error taxonomy: UNAUTHORIZED / VTON_ENGINE_UNAVAILABLE / INPUT_INVALID
#     / GPU_OOM / INFERENCE_FAILED / OUTPUT_INVALID / VTON_NOT_READY
#
# Deploy:  modal deploy services/vton-worker/modal_app_v15.py
# Weights: same shared Modal volume `confit-vton-fashn-weights` as the segfee
#          worker (model.safetensors + dwpose/ are identical). The parser
#          weights (~244 MB) live in HF_HOME inside the same volume; warm them
#          once with:  modal run services/vton-worker/modal_app_v15.py::warm_parser_cache
# ==============================================================================

import os

import modal
from fastapi import Header

# SHARED HTTP LAYER (2026-10-03): the external contract — validation, SSRF
# guard, auth, handlers — lives in server_core.py so the Modal shell and the
# Baseten custom-Docker shell (baseten_server.py) serve byte-identical
# behaviour. This file keeps ONLY what is Modal-specific: the app/image/GPU/
# volume/secrets configuration and the engine lifecycle.
import server_core

# Re-exports: the module surface is unchanged for tests/tooling while the
# implementation lives once, in server_core (shared with the Baseten shell).
VTONJobRequest = server_core.VTONJobRequest
_parser_info = server_core._parser_info
_is_safe_url = server_core._is_safe_url
MAX_GARMENTS = server_core.MAX_GARMENTS

app = modal.App("confit-vton-worker")  # canonical name (feature-03 cutover target)

WEIGHTS_DIR = "/weights"


# ==============================================================================
# BUILD (image + vendored pristine upstream + engine layer)
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

# modal_app_v15.py lives at <repo>/services/vton-worker/, so two ".." reach
# <repo>/; <repo>/vendor/fashn-vton-1.5 is the PRISTINE upstream source and
# <repo>/services/vton-worker/engine is the CONFIT engine adapter layer.
_UPSTREAM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vendor", "fashn-vton-1.5"))
_ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "engine"))
_SERVER_CORE = os.path.abspath(os.path.join(os.path.dirname(__file__), "server_core.py"))

_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch", "torchvision", "safetensors", "huggingface_hub", "pillow",
        "numpy", "opencv-python-headless", "tqdm", "einops",
        "onnxruntime-gpu", "matplotlib",
        "transformers>=4.30", "fashn-human-parser==0.1.1",
        "fastapi>=0.115.0", "pydantic>=2.9.0", "httpx>=0.27.2",
    )
    .add_local_dir(_UPSTREAM_DIR, remote_path="/root/fashn-vton-1.5", copy=True)
    .add_local_dir(_ENGINE_DIR, remote_path="/root/vton-worker/engine", copy=True)
    .add_local_file(_SERVER_CORE, remote_path="/root/vton-worker/server_core.py", copy=True)
    .run_commands("pip install --no-deps /root/fashn-vton-1.5")
    .env({
        "PYTHONPATH": "/root/fashn-vton-1.5:/root/vton-worker:",
        "FASHN_V15_VENDOR_DIR": "/root/fashn-vton-1.5",
        "CONFIT_GIT_SHA": BUILD_GIT_SHA,
        # Parser weights (~244MB) persist in the shared volume -> cold starts
        # do not re-download them. Warm once with warm_parser_cache below.
        "HF_HOME": "/weights/hf-cache",
        "HF_HUB_OFFLINE": "0",
    })
)



@app.cls(
    gpu="L4",  # Ada (24GB): native bf16 — the upstream weights are bfloat16.
    # 2026-10-02: Modal requires a payment method on this workspace for ANY
    # new GPU deployment (A10G/L4/T4 all blocked) — existing deployed apps
    # (moda-embed, vton-worker-segfee) keep running. Once a card is attached:
    #   modal deploy services/vton-worker/modal_app_v15.py
    # L4 is bf16-capable and cheaper per second than the segfee worker's A10G.
    image=_image,  # noqa: F821  (defined above; pydantic/modal resolve at build)
    secrets=[modal.Secret.from_name("confit-worker-admin-token")],
    scaledown_window=300,
    volumes={WEIGHTS_DIR: modal.Volume.from_name("confit-vton-fashn-weights")},
)
@modal.concurrent(max_inputs=1)  # one GPU outfit composition at a time
class FashnV15InferenceService:
    """Production multi-garment VTON worker (feature 03).

    All HTTP behaviour lives in server_core.py (shared with the Baseten
    shell); these endpoints are one-line delegations. The engine lifecycle
    (@modal.enter) is the only Modal-specific logic.
    """

    @modal.enter()
    def load_model(self) -> None:
        import torch
        self.model_loaded = False
        self.load_error = None
        self.engine = None
        self.device_name = None
        try:
            from engine import get_engine

            engine_cls = get_engine("fashn_v15")
            if engine_cls is None:
                raise RuntimeError("fashn_v15 engine is not registered")
            engine = engine_cls(weights_dir=WEIGHTS_DIR, device="cuda")
            engine.load()
            self.engine = engine
            self.device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            self.model_loaded = True
            print(f"[load] fashn_v15 loaded on {self.device_name}", flush=True)
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
        return server_core.handle_health(self)

    @modal.fastapi_endpoint(method="GET")
    def readiness(self) -> dict:
        return server_core.handle_readiness(self)

    @modal.fastapi_endpoint(method="POST")
    def process(self, payload: server_core.VTONJobRequest, x_vton_admin: str | None = Header(None, alias="X-VTON-Admin")) -> dict:
        return server_core.handle_process(self, payload, x_vton_admin)


@app.function(image=_image, volumes={WEIGHTS_DIR: modal.Volume.from_name("confit-vton-fashn-weights")})  # noqa: F821
def warm_parser_cache() -> str:
    """One-time (per weights refresh) CPU-only warm of the parser weights.

    Downloads fashn-ai/fashn-human-parser (~244MB) into HF_HOME inside the
    shared weights volume so GPU cold starts never pay the download. Run:
        modal run services/vton-worker/modal_app_v15.py::warm_parser_cache
    Volume writes are committed automatically when the function exits
    successfully (Modal volumes auto-commit semantics).
    """
    from huggingface_hub import snapshot_download

    path = snapshot_download("fashn-ai/fashn-human-parser")
    return f"parser weights warmed at {path} (HF_HOME={os.environ.get('HF_HOME')})"
