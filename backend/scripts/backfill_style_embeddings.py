"""Embed catalogue product images for visual search.

WHY A SCRIPT AND NOT A REQUEST-TIME JOB
----------------------------------------
Embedding is a forward pass per product (0.34s measured on CPU, faster on
GPU). Doing it during a shopper's search would make the first search after
any catalogue change pay for the whole catalogue. It is done once, offline,
and refreshed when products change.

IDEMPOTENT. A product is re-embedded only when it has no vector, or when
its stored vector came from a DIFFERENT model — vectors from two models are
not comparable, so a model change must invalidate rather than mix.
Re-running after a completed pass writes nothing.

RUN IT
------
    MODA_EMBED_BASE_URL=http://<host>:8002 \
    ALEMBIC_DATABASE_URL=<owner dsn> \
    PYTHONPATH=. python3 backend/scripts/backfill_style_embeddings.py

The sidecar (services/moda-embed) holds the model; this script holds no
torch, so it runs anywhere the database is reachable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Optional

import httpx

from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product
from backend.app.providers.moda import embeddings as moda


async def _embed_url(client: httpx.Client, base: str, image_url: str) -> Optional[list]:
    """Fetch a product image and embed it. None on any failure."""
    try:
        image = client.get(image_url, timeout=30.0, follow_redirects=True)
        image.raise_for_status()
    except Exception as exc:
        print(f"      image fetch failed: {str(exc)[:80]}")
        return None
    try:
        response = client.post(
            f"{base}/embed",
            files={"image": ("p.jpg", image.content, "image/jpeg")},
            timeout=120.0,
        )
        response.raise_for_status()
        vector = (response.json() or {}).get("embedding")
    except Exception as exc:
        print(f"      embed failed: {str(exc)[:80]}")
        return None
    if not isinstance(vector, list) or len(vector) != moda.EMBED_DIM:
        # A wrong-width vector would rank against correct ones and produce
        # confident nonsense, so it is refused rather than stored.
        print(f"      rejected: wrong width {len(vector) if isinstance(vector, list) else None}")
        return None
    return vector


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="re-embed even rows already on the current model")
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    base = (moda.settings.MODA_EMBED_BASE_URL or "").strip().rstrip("/")
    if not base:
        print("MODA_EMBED_BASE_URL is not set — nothing to do.", file=sys.stderr)
        return 2

    embedded = skipped = failed = 0
    with SessionLocal() as db, httpx.Client() as client:
        products = db.query(Product).filter(Product.is_active.is_(True)).all()
        if args.limit:
            products = products[: args.limit]
        print(f"catalogue: {len(products)} active products | model {moda.MODEL_ID}")

        for product in products:
            current = product.style_embedding_model
            if not args.force and product.style_embedding and current == moda.MODEL_ID:
                skipped += 1
                continue
            if not product.thumbnail_url:
                failed += 1
                continue

            print(f"  #{product.id} {product.title[:44]}")
            vector = asyncio.run(_embed_url(client, base, product.thumbnail_url))
            if vector is None:
                failed += 1
                continue
            product.style_embedding = json.dumps(vector)
            # Written together so a row can never claim a model it was not
            # embedded with.
            product.style_embedding_model = moda.MODEL_ID
            embedded += 1

        db.commit()

    print(f"\nEMBEDDINGS: {embedded} written, {skipped} already current, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
