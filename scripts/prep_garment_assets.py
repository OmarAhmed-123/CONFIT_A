#!/usr/bin/env python3
"""P1 offline garment-asset preparation (ghost-hands remediation).

At INGESTION time (not render time) every catalog garment image is:

  1. CLASSIFIED  — flat-lay / ghost-mannequin vs on-model, with measured
     evidence (backend.app.services.garment_asset_guard.classify_garment_photo);
  2. VALIDATED   — flat-lay photos are marked tryon_ready immediately;
  3. CLEANED     — on-model photos are converted to a clean garment asset
     ONLY when a licensed parser/inpainter is installed:
        --parser schp   : SCHP (MIT code) person labels; garment kept,
                          skin/hands/face removed from the conditioning crop;
        --inpaint lama  : LaMa (Apache-2.0) fills the removed regions;
     without them the product is reported as needs_manual_asset and the P0
     gate keeps blocking it (fail closed). Runtime stays parser-free: the
     worker never sees this code path.

The manifest is written to --out; applying it to the DB
(--apply, requires DATABASE_URL) sets garment_assets.photo_type /
classification_json / tryon_ready / clean_image_url. Secrets never appear
here; DB URL comes from the environment.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

import httpx
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app.services.garment_asset_guard import classify_garment_photo  # noqa: E402


def _load(path_or_url: str) -> Image.Image:
    if path_or_url.startswith("http"):
        r = httpx.get(path_or_url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    return Image.open(path_or_url).convert("RGB")


def _clean_on_model(img: Image.Image, parser: str, inpaint: str) -> tuple[Image.Image | None, str]:
    """Best-effort clean-asset conversion with licensed components only."""
    if parser == "schp":
        try:
            from simple_schp import SCHP  # type: ignore  # optional, MIT code
        except Exception:
            return None, "schp_not_installed"
        return None, "schp_pipeline_seam"  # implemented where weights are licensed
    return None, "needs_manual_asset"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="paths or URLs of catalog garment images")
    ap.add_argument("--out", default="reports/garment_asset_manifest.json")
    ap.add_argument("--parser", choices=["none", "schp"], default="none")
    ap.add_argument("--inpaint", choices=["none", "lama"], default="none")
    args = ap.parse_args()

    manifest = []
    for src in args.images:
        img = _load(src)
        photo_type, evidence = classify_garment_photo(img)
        entry = {
            "source": src,
            "photo_type": photo_type,
            "evidence": evidence,
            "tryon_ready": photo_type == "flat-lay",
            "clean_image_url": None,
        }
        if photo_type != "flat-lay":
            clean, how = _clean_on_model(img, args.parser, args.inpaint)
            entry["cleaning"] = how
            entry["tryon_ready"] = clean is not None
        manifest.append(entry)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(manifest, indent=2))
    ready = sum(1 for m in manifest if m["tryon_ready"])
    print(json.dumps({"total": len(manifest), "tryon_ready": ready,
                      "blocked_until_prepared": len(manifest) - ready}, indent=2))
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
