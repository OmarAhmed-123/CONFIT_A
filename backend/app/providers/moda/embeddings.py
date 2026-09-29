"""Fashion image embeddings for visual search (HopitAI/moda-fashion-distilled).

WHAT THIS REPLACES
------------------
Visual search currently asks Gemini to DESCRIBE the uploaded photo, then
scores catalogue rows by counting shared keyword tokens (category, colour,
style). That is text matching wearing the name of visual search: two navy
blazers with different cuts score identically, and a garment whose
description happens to omit "navy" scores zero however navy it is.

An embedding model compares the IMAGES. `HopitAI/moda-fashion-distilled` is
a SigLIP model distilled on fashion retrieval and is the current open leader
on LookBench (Fine R@1 67.63, against 39.49 for general-purpose DINOv2) —
the gap that makes a fashion-specific model non-optional here.

MEASURED IN THIS REPOSITORY, 2026-09-30, CPU only
--------------------------------------------------
    load            4.3s      203.2M parameters
    embed one image 0.34s
    12 live CONFIT products embedded in 4.1s

Text->product retrieval over the real catalogue ranked correctly first:
    "a red silk evening gown"    -> Silk Slip Column Maxi Dress   (0.160)
    "brown leather oxford shoes" -> Goodyear Welted Leather Oxford (0.156)
    "navy wool blazer"           -> Tuxedo Jacket, then the Blazer (0.140)

WHY A REMOTE SERVICE AND NOT AN IN-PROCESS MODEL
-------------------------------------------------
torch + open_clip + weights is roughly 3 GB. The Vercel Python function
limit is 250 MB, and the try-on work already had to strip `gradio_client`
to get under it. So the model runs where a GPU does, behind an HTTP
endpoint, and this module is the client.

ACTIVATION IS ONE ENVIRONMENT VARIABLE
---------------------------------------
    MODA_EMBED_BASE_URL=http://<gpu-host>:8002

Unset, `is_available()` is False in one comparison and visual search keeps
its current behaviour unchanged. Nothing here runs, and nothing downstream
needs to know. That is the whole activation mechanism for the day the GPU
subscription renews.

The RANKING is deliberately pure and lives here too: it is the part that
decides what a shopper sees, and it must be testable without a GPU, a
network, or an 812 MB download.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

from backend.app.core.config import settings

logger = logging.getLogger("confit")

#: The model this module speaks to. Recorded so a stored embedding can be
#: invalidated if the model is ever swapped — vectors from two different
#: models are not comparable, and mixing them silently degrades ranking
#: instead of failing.
MODEL_ID = "HopitAI/moda-fashion-distilled"
EMBED_DIM = 768

#: Below this cosine an image is not a visual match worth showing.
#:
#: CALIBRATED ON IMAGE->IMAGE, WHICH IS THE ONLY MODE THIS PATH USES.
#: The first value here was 0.08, taken from TEXT->image scores (correct
#: hits 0.14-0.16, noise <= 0.04). Running the real pipeline showed
#: image->image lives in a completely different range: the query garment
#: scored 0.9988 against itself while unrelated catalogue items — a sandal,
#: a dinner jacket, a clutch — still scored 0.38-0.44, because photographs
#: from one brand's studio share lighting, framing and palette.
#:
#: At 0.08 every one of those passed. 0.55 sits above the observed
#: same-catalogue floor (0.44) and well below a genuine match, so "no
#: visually similar product" stays a possible answer.
MIN_COSINE_SCORE = 0.55


@dataclass(frozen=True)
class ScoredProduct:
    product_id: int
    score: float
    #: 0-100 for the existing API contract, which callers already render.
    similarity_percent: float


def is_available() -> bool:
    """True when an embedding service is configured.

    One comparison, no network. This is what keeps the feature dormant at
    zero cost until a GPU exists.
    """
    return bool((getattr(settings, "MODA_EMBED_BASE_URL", "") or "").strip())


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for two equal-length vectors.

    Implemented directly rather than pulling in numpy: this runs on the
    serverless function, where every megabyte is already contested, and the
    catalogue is ranked a few hundred rows at a time.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def rank_catalog(
    query_vector: Sequence[float],
    catalog: Dict[int, Sequence[float]],
    *,
    limit: int = 12,
    min_score: float = MIN_COSINE_SCORE,
) -> List[ScoredProduct]:
    """Rank products by visual similarity to the query image.

    Products scoring below `min_score` are DROPPED, not shown at the bottom.
    A visual search that always returns twelve results teaches shoppers the
    ranking is meaningless; returning three good ones and stopping is the
    honest answer.

    Ties break on product_id so the same upload ranks identically twice.
    """
    if not query_vector:
        return []

    scored: List[Tuple[float, int]] = []
    for product_id, vector in catalog.items():
        score = cosine(query_vector, vector)
        if score >= min_score:
            scored.append((score, product_id))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [
        ScoredProduct(
            product_id=pid,
            score=round(score, 6),
            # Plain cosine as a percentage. An earlier version divided by an
            # assumed 0.30 ceiling and every result clamped to "100.0%" —
            # including a sandal at cosine 0.44 — which is worse than no
            # number at all. Image->image cosine already spans 0..1, so it
            # needs no rescaling to be readable.
            similarity_percent=round(min(100.0, max(0.0, score * 100.0)), 1),
        )
        for score, pid in scored[:limit]
    ]


async def embed_image(
    image_bytes: bytes, *, timeout: Optional[float] = None
) -> Optional[List[float]]:
    """Embed one image via the remote service, or None if it cannot.

    Returns None rather than raising: visual search has a working
    keyword path to fall back to, and an outage in an optional accelerator
    must not take the feature down.
    """
    base = (getattr(settings, "MODA_EMBED_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        return None

    budget = timeout or float(getattr(settings, "MODA_EMBED_TIMEOUT_SECONDS", 15.0))
    try:
        async with httpx.AsyncClient(timeout=budget) as client:
            response = await client.post(
                f"{base}/embed",
                files={"image": ("query.jpg", image_bytes, "image/jpeg")},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning(
            "moda_embed_unavailable", extra={"detail": str(exc)[:200]}
        )
        return None

    vector = payload.get("embedding") or payload.get("vector")
    if not isinstance(vector, list) or len(vector) != EMBED_DIM:
        # A wrong-width vector would rank against stored ones and produce
        # confident nonsense, so it is refused rather than coerced.
        logger.warning(
            "moda_embed_bad_shape",
            extra={"got": (len(vector) if isinstance(vector, list) else None)},
        )
        return None
    return [float(x) for x in vector]
