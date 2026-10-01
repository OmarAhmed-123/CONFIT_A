# =============================================================================
# CONFIT MODA EMBEDDING WORKER — Modal deployment of the visual-search encoder.
#
# Model: HopitAI/moda-fashion-distilled (open_clip, 203.2M params, 768-d).
#
# WHY THIS FILE EXISTS
# --------------------
# `services/moda-embed/server.py` already implements the whole contract and is
# the only place that owns the model. What was missing was a way to RUN it:
# the docstring says "on whatever host has the GPU", and no such host was
# deployed, so `MODA_EMBED_BASE_URL` stayed empty and visual search silently
# fell back to keyword matching forever.
#
# This module is deployment only. It imports `server.app` and serves it
# unchanged — the inference code, the L2 normalisation and the 422 guards are
# NOT re-implemented here. A second copy of the embedding path is how the
# query vector and the catalogue vectors end up produced by subtly different
# code and every ranking quietly degrades.
#
# ---------------------------------------------------------------------------
# WHY CPU AND NOT GPU — a measured decision, not a preference
# ---------------------------------------------------------------------------
# The sidecar's own measurement, recorded in its docstring:
#
#     MEASURED (CPU, 2026-09-30): load 4.3s, 203.2M params, 0.34s per image.
#
# Visual search embeds ONE query image per user action. 0.34 s is well inside
# an interactive budget, and the catalogue side is a one-off backfill of a few
# hundred rows. A T4 would cut 0.34 s to roughly 0.03 s — an improvement no
# shopper can perceive, bought with GPU-seconds from a subscription that is
# explicitly scarce and reserved for try-on, which genuinely needs it.
#
# So: CPU by default, with `MODA_GPU` as an env override if the catalogue ever
# grows enough that batch backfill time matters. This is the cheapest correct
# answer, and it is reversible with one variable.
#
# COLD START
# ----------
# Weights are baked into the image at BUILD time, not downloaded at run time.
# A 812 MB download on every cold container would dominate the latency budget
# and make the first query of the day look broken.
# =============================================================================
from __future__ import annotations

import os

import modal

APP_NAME = "confit-moda-embed"
MODEL_ID = os.environ.get("MODA_MODEL_ID", "HopitAI/moda-fashion-distilled")
#: Override to "T4" only if batch backfill time ever becomes the bottleneck.
#: Empty string = CPU, which is the measured-correct default (see header).
WORKER_GPU = os.environ.get("MODA_GPU", "").strip() or None

app = modal.App(APP_NAME)

HERE = os.path.dirname(os.path.abspath(__file__))


def _bake_weights() -> None:
    """Resolve the weights during the image build so no cold start pays for them.

    open_clip caches into the HF hub cache; calling create_model_and_transforms
    here is the cheapest way to guarantee the exact artefacts the runtime will
    ask for are already present, rather than guessing at filenames.
    """
    import open_clip  # noqa: F401

    open_clip.create_model_and_transforms(f"hf-hub:{MODEL_ID}")


image = (
    modal.Image.debian_slim(python_version="3.11")
    # CPU wheels: the CUDA build of torch is ~2.5 GB and would be dead weight
    # in a CPU deployment, slowing every image pull for no benefit.
    .pip_install(
        "torch==2.4.1",
        "torchvision==0.19.1",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install(
        "open_clip_torch==2.26.1",
        "transformers==4.44.2",
        "pillow==10.4.0",
        "fastapi[standard]==0.115.0",
        "huggingface_hub==0.25.2",
    )
    .run_function(_bake_weights)
    # The sidecar is the single source of truth for the contract; it is added
    # last so editing it does not invalidate the expensive weight layer.
    .add_local_file(os.path.join(HERE, "server.py"), "/root/server.py")
)


@app.function(
    image=image,
    gpu=WORKER_GPU,
    # ONE WARM CONTAINER — and this is a CPU container, so it costs no GPU.
    #
    # MEASURED 2026-10-01: with min_containers=0 the first production query hit
    # a cold container, paid container boot + a 4.3 s model load, and blew
    # through the client's 15 s MODA_EMBED_TIMEOUT_SECONDS. embed_image then
    # returns None BY DESIGN (an optional accelerator must not take the feature
    # down), so visual search silently fell back to keyword scoring and the
    # embeddings were never used. The failure was invisible: HTTP 200, results
    # returned, ranking quietly wrong.
    #
    # The try-on worker keeps min_containers=0 because it is a GPU container
    # and idle GPU is exactly what must not be paid for. This one is CPU; the
    # trade is a few cents of idle CPU against a feature that only works after
    # someone has already used it.
    min_containers=1,
    scaledown_window=300,
    timeout=600,
    secrets=[modal.Secret.from_name("confit-worker-admin-token")],
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def fastapi_app():
    """Serve the existing sidecar, with an auth gate added around /embed.

    AUTH IS NOT OPTIONAL HERE. A Modal web endpoint is public, and `/embed`
    runs a 203M-parameter model on every call. Shipping it unauthenticated
    would put a free, anonymous compute endpoint on the internet attached to a
    metered account — the exact way a scarce subscription gets drained by
    someone who is not the owner.

    `/health` stays public so uptime probes and the capability layer can read
    it without holding a credential, exactly like the try-on worker.
    """
    import sys

    sys.path.insert(0, "/root")
    from fastapi import HTTPException, Request
    from server import app as sidecar_app  # the ONE implementation

    expected = (
        os.environ.get("MODA_EMBED_TOKEN")
        or os.environ.get("VTON_WORKER_ADMIN_TOKEN")
        or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
        or ""
    )

    @sidecar_app.middleware("http")
    async def _require_token(request: Request, call_next):
        # Public: health/readiness and the generated docs. Everything that
        # spends compute requires the shared worker token.
        if request.url.path in ("/health", "/healthz", "/docs", "/openapi.json"):
            return await call_next(request)
        if expected and request.headers.get("X-Worker-Token") != expected:
            # Deliberately terse: an unauthenticated caller learns nothing
            # about why, only that it is refused.
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHORIZED",
                                   "message": "Missing or wrong X-Worker-Token header."}},
            )
        return await call_next(request)

    @sidecar_app.get("/readiness")
    def readiness():
        """503 until the model is loaded, so a probe cannot report a cold
        container as ready and route a query into a 30-second load."""
        import server as s

        if s._model is None:
            raise HTTPException(status_code=503, detail={"error": {
                "code": "MODA_NOT_READY", "message": "model not loaded yet"}})
        return {"ready": True, "model": s.MODEL_ID, "dim": s.EMBED_DIM}

    @sidecar_app.post("/warm")
    def warm():
        """Load the model without embedding anything.

        Lets the backfill job pay the load cost once, deliberately, instead of
        the first real shopper paying it inside their query.
        """
        import server as s

        s._load()
        return {"ready": True, "model": s.MODEL_ID, "device": s._device}

    return sidecar_app
