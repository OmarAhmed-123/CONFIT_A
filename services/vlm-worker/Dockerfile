# =============================================================================
# CONFIT SELF-HOSTED VLM WORKER — build/inspection image (Qwen2.5-VL-7B, Apache-2.0)
#
# AUTHORITATIVE production deployment is Modal (modal_app.py):
#     modal deploy services/vlm-worker/modal_app.py
#
# This image has NO default server command (it cannot start the service), so it
# can never shadow the Modal production path.
# =============================================================================

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0" \
    CUDA_HOME=/usr/local/cuda

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3-pip git curl \
    libgl1-mesa-glx libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Intentionally no CMD: the service only runs under `modal deploy`.
