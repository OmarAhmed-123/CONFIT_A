# ==============================================================================
# CONFIT VTON WORKER — Cerebrium build shim (feature 03, multi-garment)
#
# One line, on purpose: this Dockerfile re-hosts the EXACT image the Baseten
# path uses — built by .github/workflows/build-vton-baseten-image.yml from
# services/vton-worker/baseten/Dockerfile and pushed to GHCR as a PUBLIC
# package (anonymous pull verified 2026-10-04):
#
#     ghcr.io/omarahmed-123/confit-vton-worker-baseton:main
#
# The image is self-contained: CUDA 12.4 runtime, pip deps, vendored pristine
# fashn-vton-1.5 (pip-installed), the CONFIT engine/server layers, and ~2.2GB
# of weights baked at build time (HF_HUB_OFFLINE=1 at runtime). Everything
# this shim needs — EXPOSE 8000, CMD uvicorn baseten_server:app, ENV
# PYTHONPATH/VTON_WEIGHTS_DIR — is inherited from the base image, so nothing
# is repeated here. One artifact, multiple deployment targets, zero drift.
#
# (Why a shim at all: Cerebrium CLI 2.9.0 requires `dockerfile_path` in
# [cerebrium.runtime.custom] for a custom runtime; entrypoint-only configs are
# rejected with "main.py not found". A bare FROM satisfies the check while
# keeping the real build definition in exactly one place.)
# ==============================================================================

FROM ghcr.io/omarahmed-123/confit-vton-worker-baseton:main
