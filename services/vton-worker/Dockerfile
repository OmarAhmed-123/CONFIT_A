# ==============================================================================
# CONFIT VTON WORKER — build/inspection image
#
# IMPORTANT (final release gate):
# The AUTHORITATIVE production VTON deployment is Modal, defined in
# `modal_app.py` and deployed with:
#
#     modal deploy services/vton-worker/modal_app.py
#
# This Dockerfile previously launched a legacy placeholder module as its CMD, which
# launched a CPU-only "geometric warp + composite" placeholder that performed no
# diffusion at all yet returned status="completed". That placeholder has been
# deleted; there is now exactly ONE VTON implementation.
#
# This image therefore has NO default server command. It exists for dependency
# builds and offline inspection only. It intentionally cannot start a VTON
# service, so it can never shadow the Modal production path.
# ==============================================================================

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0" \
    CUDA_HOME=/usr/local/cuda

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    git \
    curl \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && ln -sf /usr/bin/python3 /usr/bin/python

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# No CMD / ENTRYPOINT server: production VTON runs on Modal (modal_app.py).
# Fail loudly if anyone tries to run this image as a service.
CMD ["python", "-c", "import sys; sys.exit('CONFIT: this image does not serve VTON. Deploy modal_app.py to Modal instead.')"]
