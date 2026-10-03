# ==============================================================================
# CONFIT VTON WORKER (fashn_v15, multi-garment) — Baseten custom Docker image
#
# Built by .github/workflows/build-vton-baseten-image.yml and pushed to GHCR;
# deployed with `truss push` in no_build mode (see ./config.yaml). The image is
# self-contained: deps + vendored pristine upstream + engine layer + shared
# HTTP layer + weights downloaded at BUILD time from public Hugging Face
# (fashn-ai/fashn-vton-1.5 model.safetensors, fashn-ai/DWPose ONNX,
# fashn-ai/fashn-human-parser snapshot) so a cold replica never waits on the
# network, and HF_HUB_OFFLINE=1 keeps runtime hermetic.
#
# No secrets are baked in: the X-VTON-Admin token is injected at runtime via
# the Baseten secret `confit-worker-admin-token` (env or /secrets file mount).
#
# Context: repository root (docker build -f services/vton-worker/baseten/Dockerfile .)
# ==============================================================================

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TORCH_CUDA_ARCH_LIST="8.9" \
    CUDA_HOME=/usr/local/cuda \
    HF_HOME=/app/weights/hf-cache \
    HF_HUB_OFFLINE=1 \
    VTON_WEIGHTS_DIR=/app/weights

WORKDIR /app

# --- system deps (same set the Modal image installs) --------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3-pip git curl ffmpeg \
        libgl1-mesa-glx libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 && ln -sf /usr/bin/python3 /usr/bin/python

# --- python deps ---------------------------------------------------------------
# torch/torchvision from the CUDA 12.4 index (matches the base image); the rest
# mirrors the Modal image's pip set (modal_app_v15.py) minus Modal itself.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124 \
    && pip install --no-cache-dir \
        safetensors huggingface_hub pillow numpy opencv-python-headless \
        tqdm einops onnxruntime-gpu matplotlib "transformers>=4.30" \
        fashn-human-parser==0.1.1 "fastapi>=0.115.0" "pydantic>=2.9.0" \
        "httpx>=0.27.2" uvicorn

# --- code: pristine upstream (unmodified) + CONFIT layers ----------------------
COPY vendor/fashn-vton-1.5 /app/vendor/fashn-vton-1.5
COPY services/vton-worker/engine /app/vton-worker/engine
COPY services/vton-worker/server_core.py /app/vton-worker/server_core.py
COPY services/vton-worker/baseten_server.py /app/vton-worker/baseten_server.py
RUN pip install --no-deps /app/vendor/fashn-vton-1.5

# --- weights at BUILD time (public HF repos; ~2.2GB total) ---------------------
# Parity with the Modal volume: model.safetensors + dwpose ONNX + parser
# snapshot. hf_transfer for fast parallel download.
RUN pip install --no-cache-dir hf_transfer \
    && HF_HUB_ENABLE_HF_TRANSFER=1 python3 /app/vendor/fashn-vton-1.5/scripts/download_weights.py --weights-dir /app/weights \
    && python3 -c "from huggingface_hub import snapshot_download; snapshot_download('fashn-ai/fashn-human-parser')" \
    && pip uninstall -y hf_transfer \
    && ls -la /app/weights /app/weights/dwpose

# --- build provenance (same honesty as the Modal deploy) -----------------------
ARG CONFIT_GIT_SHA=unknown
ENV CONFIT_GIT_SHA=${CONFIT_GIT_SHA} \
    PYTHONPATH=/app/vton-worker:/app/vendor/fashn-vton-1.5

# Baseten runs the container as a non-root user (default uid 60000 `app`);
# everything the server needs is world-readable, no runtime writes required.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

WORKDIR /app/vton-worker
CMD ["uvicorn", "baseten_server:app", "--host", "0.0.0.0", "--port", "8000"]
