# ==============================================================================
# CONFIT GPU VTON WORKER — Production Dockerfile
# Base Image: NVIDIA CUDA 12.4 with cuDNN 9 & Ubuntu 22.04
# Model Pipeline: CatVTON (Apache 2.0) + SCHP Human Parser + DWPose + Rembg
# ==============================================================================

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0" \
    CUDA_HOME=/usr/local/cuda

WORKDIR /app

# Install system dependencies & build tools
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

# Upgrade pip and install PyTorch with CUDA 12.4 support
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124

# Install worker requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and model pipeline definitions
COPY . /app

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "worker.py"]
