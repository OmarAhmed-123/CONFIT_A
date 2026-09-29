"""Embedding sidecar for HopitAI/moda-fashion-distilled.

WHY A SIDECAR
-------------
torch + open_clip + the 812 MB weights is roughly 3 GB. The Vercel Python
function limit is 250 MB — the try-on work already had to strip
`gradio_client` to fit. So the model runs here, on whatever host has the
GPU, and the application holds only an HTTP client
(`backend/app/providers/moda/embeddings.py`).

RUN IT
------
    pip install torch open_clip_torch transformers pillow fastapi uvicorn
    uvicorn server:app --host 0.0.0.0 --port 8002

Then point the app at it and visual search switches over with no redeploy:

    MODA_EMBED_BASE_URL=http://<this-host>:8002

CONTRACT
--------
    POST /embed   multipart image  -> {"embedding": [768 floats], "model": ...}
    GET  /health                   -> {"ready": bool, "model": ..., "dim": 768}

The vector is L2-NORMALISED here, at the only place that owns the model, so
the caller's cosine is a plain dot product and no consumer can forget to
normalise and silently skew every ranking.

MEASURED (CPU, 2026-09-30): load 4.3s, 203.2M params, 0.34s per image.
"""
from __future__ import annotations

import io
import logging
import os

import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

MODEL_ID = os.environ.get("MODA_MODEL_ID", "HopitAI/moda-fashion-distilled")
EMBED_DIM = 768

logger = logging.getLogger("moda-embed")
app = FastAPI(title="CONFIT MODA embedding sidecar")

_model = None
_preprocess = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def _load():
    """Load once, lazily. A cold start must not be paid per request."""
    global _model, _preprocess
    if _model is None:
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            f"hf-hub:{MODEL_ID}"
        )
        model.eval().to(_device)
        _model, _preprocess = model, preprocess
        logger.info("moda_model_loaded device=%s", _device)
    return _model, _preprocess


@app.get("/health")
def health():
    return {
        "ready": _model is not None,
        "model": MODEL_ID,
        "dim": EMBED_DIM,
        "device": _device,
        "cuda": torch.cuda.is_available(),
    }


@app.post("/embed")
async def embed(image: UploadFile = File(...)):
    raw = await image.read()
    if len(raw) < 100:
        # Refuse rather than embed noise: a garbage vector ranks confidently
        # against real ones and the shopper cannot tell.
        raise HTTPException(422, "image too small to embed")
    try:
        pil = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(422, f"not a decodable image: {exc}") from exc

    model, preprocess = _load()
    with torch.no_grad():
        vector = model.encode_image(preprocess(pil).unsqueeze(0).to(_device))
        vector = torch.nn.functional.normalize(vector, dim=-1)
    return {
        "embedding": vector.squeeze(0).cpu().tolist(),
        "model": MODEL_ID,
        "dim": EMBED_DIM,
    }
