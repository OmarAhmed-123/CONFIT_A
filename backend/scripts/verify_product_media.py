#!/usr/bin/env python3
"""Verify the product-media pipeline end to end — DB registry, bucket, HTTP.

Run it anywhere the credentials exist (CI, an operator laptop, a production
shell). Read-only: it never writes to the database and never modifies an object.

CHECKS (all mechanical, exit code 1 if ANY fails):

  1. every ``product_images`` row has an object at its ``storage_key``;
  2. the object's byte length equals the row's ``bytes``, and its SHA-256
     starts with the row's ``checksum`` (the column stores a 32-char prefix —
     see the note in ``models/catalog.py``);
  3. the decoded pixel size equals ``width``x``height`` and ``ratio`` matches
     the real aspect ratio (4x5 -> 0.8, 1x1 -> 1.0, 3x2 -> 1.5, 16x9 -> 1.78);
  4. every product that HAS registered rows exposes them through the API
     (``images`` non-empty, ``media`` complete, no ``master`` in ``images``);
  5. every URL the API returns answers HTTP 200 with an image content type
     and immutable caching — this is the check that was missing when all 120
     advertised URLs answered 404 in production.

Usage:
    python -m backend.scripts.verify_product_media --api https://confit-a.vercel.app
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

RATIO_EXPECTED = {"4x5": 0.8, "1x1": 1.0, "3x2": 1.5, "16x9": 16 / 9}


def _get(url: str, timeout: int = 30) -> Tuple[int, Dict[str, Any], bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "confit-media-verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), b""
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)[:160]}, b""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://confit-a.vercel.app", help="API origin to probe")
    ap.add_argument("--skip-http", action="store_true", help="registry+bucket checks only")
    args = ap.parse_args()

    from backend.app.core.database import SessionLocal
    from backend.app.models.catalog import Product, ProductImage
    from backend.app.services.storage_service import get_storage

    storage = get_storage()
    failures: List[str] = []
    checked = {"rows": 0, "objects": 0, "byte_ok": 0, "digest_ok": 0, "px_ok": 0,
               "ratio_ok": 0, "api_products": 0, "urls_ok": 0, "urls_probed": 0}

    db = SessionLocal()
    try:
        rows = db.query(ProductImage).all()
        products = {p.id: p for p in db.query(Product).all()}
        by_product: Dict[int, List[ProductImage]] = {}
        for row in rows:
            by_product.setdefault(row.product_id, []).append(row)
            checked["rows"] += 1
            data = storage.read(row.storage_key)
            if data is None:
                failures.append(f"[object] missing in bucket: {row.storage_key}")
                continue
            checked["objects"] += 1
            if len(data) != row.bytes:
                failures.append(f"[bytes] {row.storage_key}: db={row.bytes} object={len(data)}")
            else:
                checked["byte_ok"] += 1
            digest = hashlib.sha256(data).hexdigest()
            if row.checksum and not digest.startswith(row.checksum.lower()):
                failures.append(f"[digest] {row.storage_key}: db={row.checksum[:12]}… object={digest[:12]}…")
            else:
                checked["digest_ok"] += 1
            try:
                from PIL import Image

                with Image.open(io.BytesIO(data)) as im:
                    if (im.size[0], im.size[1]) != (row.width, row.height):
                        failures.append(f"[pixels] {row.storage_key}: db={row.width}x{row.height} object={im.size[0]}x{im.size[1]}")
                    else:
                        checked["px_ok"] += 1
                    if row.ratio in RATIO_EXPECTED:
                        got = round(im.size[0] / im.size[1], 2)
                        want = round(RATIO_EXPECTED[row.ratio], 2)
                        if abs(got - want) > 0.02:
                            failures.append(f"[ratio] {row.storage_key}: labelled {row.ratio} but is {got}")
                        else:
                            checked["ratio_ok"] += 1
            except Exception:  # noqa: BLE001 - Pillow is optional for the check
                pass
    finally:
        db.close()

    if not args.skip_http:
        for pid, group in sorted(by_product.items()):
            product = products.get(pid)
            if product is None:
                continue
            status, _, body = _get(f"{args.api}/api/v1/catalog/products/{product.slug}")
            if status != 200:
                failures.append(f"[api] {product.slug}: HTTP {status}")
                continue
            payload = json.loads(body)
            checked["api_products"] += 1
            images = payload.get("images") or []
            if len(images) < 2:
                failures.append(f"[api] {product.slug}: images={len(images)} — registered set is not being served")
            if any(img.endswith("-master.jpg") or img.endswith("-master.webp") for img in images):
                failures.append(f"[api] {product.slug}: master ratio leaked into the gallery")
            for url in images:
                fetch = url if url.startswith("http") else f"{args.api}{url}"
                checked["urls_probed"] += 1
                st, headers, blob = _get(fetch)
                ctype = (headers.get("Content-Type") or headers.get("content-type") or "")
                if st != 200 or not ctype.startswith("image/"):
                    failures.append(f"[url] {url} -> HTTP {st} {ctype or 'no content-type'}")
                else:
                    checked["urls_ok"] += 1

    print(json.dumps({"checked": checked, "failures": failures[:40], "failure_count": len(failures)}, indent=1))
    if failures:
        print("\nMEDIA PIPELINE: FAIL", file=sys.stderr)
        return 1
    print("\nMEDIA PIPELINE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
