"""Offline guards for the verified product-image plan (no network, no database).

The live checks (HTTP, decode, md5) live in backend/scripts/repair_product_images.py --verify.
These tests pin the invariants the plan must always satisfy, and that the seed agrees with it.
"""
import ast
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLAN = json.loads((REPO / "backend/scripts/data/product_image_plan_2026-10-09.json").read_text(encoding="utf-8"))
SEED_SRC = (REPO / "backend/app/seed_data.py").read_text(encoding="utf-8")
# exact pixel size per (ratio, role) for every cropped rendition; "master" keeps the native aspect
EXPECTED_SIZE = {("4x5", "hero"): (1200, 1500), ("4x5", "thumb"): (800, 1000), ("1x1", "gallery"): (800, 800),
                 ("3x2", "gallery"): (1200, 800), ("16x9", "gallery"): (1280, 720)}
PLACEHOLDERS = {"structured-metallic-evening-box-clutch", "brand-4-57ad561648ff0fe831b25730"}
PROVIDER_HOSTS = {"pexels": "https://images.pexels.com/photos/", "unsplash": "https://images.unsplash.com/photo-"}


def _sourced():
    return {s: p for s, p in PLAN["products"].items() if p["source"]}


def test_plan_covers_twelve_products_and_placeholders_are_exactly_the_documented_two():
    assert len(PLAN["products"]) == 12
    assert {s for s, p in PLAN["products"].items() if not p["source"]} == PLACEHOLDERS


def test_placeholders_have_no_renditions():
    for slug in PLACEHOLDERS:
        assert PLAN["products"][slug]["renditions"] == []


@pytest.mark.parametrize("slug", sorted(_sourced()))
def test_sourced_product_has_one_row_per_ratio_plus_thumbnail(slug):
    renditions = PLAN["products"][slug]["renditions"]
    roles = sorted((r["ratio"], r["role"]) for r in renditions)
    assert roles == sorted([("4x5", "hero"), ("4x5", "thumb"), ("1x1", "gallery"), ("3x2", "gallery"),
                            ("16x9", "gallery"), ("master", "gallery")])
    # schema constraint uq_product_image_ratio_format: at most one non-thumb row per ratio
    stored = [r["ratio"] for r in renditions if r["role"] != "thumb"]
    assert len(stored) == len(set(stored))
    assert sum(1 for r in renditions if r["is_primary"]) == 1


@pytest.mark.parametrize("slug", sorted(_sourced()))
def test_cropped_renditions_have_exact_requested_dimensions_and_ratio(slug):
    for r in PLAN["products"][slug]["renditions"]:
        assert r["format"] == "jpeg"
        assert len(r["md5"]) == 32 and r["bytes"] > 0
        key = (r["ratio"], r["role"])
        if key in EXPECTED_SIZE:
            assert (r["width"], r["height"]) == EXPECTED_SIZE[key] == (r["requested_w"], r["requested_h"])
            assert abs(r["width"] / r["height"] - {"4x5": 0.8, "1x1": 1.0, "3x2": 1.5, "16x9": 16 / 9}[r["ratio"]]) < 0.01
        else:
            assert r["ratio"] == "master" and r["width"] == r["requested_w"]
        assert r["url"].startswith(PROVIDER_HOSTS[PLAN["products"][slug]["source"]["provider"]])


def test_each_stock_photo_is_used_by_at_most_one_product():
    ids = [p["source"]["photo_id"] for p in _sourced().values()]
    assert len(ids) == len(set(ids))


def _seed_thumbnails_and_images():
    tree = ast.parse(SEED_SRC)
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        kv = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if isinstance(kv.get("slug"), ast.Constant) and "thumbnail_url" in kv:
            thumb = kv["thumbnail_url"].value if isinstance(kv["thumbnail_url"], ast.Constant) else None
            imgs = None
            call = kv.get("images")
            if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.List):
                imgs = [e.value for e in call.args[0].elts if isinstance(e, ast.Constant)]
            found[kv["slug"].value] = (thumb, imgs)
    return found


@pytest.mark.parametrize("slug", sorted(set(PLAN["products"]) & set(_seed_thumbnails_and_images())))
def test_seed_agrees_with_plan_for_seeded_products(slug):
    thumb, imgs = _seed_thumbnails_and_images()[slug]
    renditions = PLAN["products"][slug]["renditions"]
    want_thumb = next((r["url"] for r in renditions if r["role"] == "thumb"), "")
    want_hero = next((r["url"] for r in renditions if r["role"] == "hero"), None)
    assert thumb == want_thumb
    assert imgs == ([want_hero] if want_hero else [])


def test_csp_img_src_allows_every_image_host_used_by_the_plan():
    """A host missing from vercel.json img-src makes browsers block the image (found live on 2026-10-09)."""
    vercel = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    csp = next(h["value"] for entry in vercel.get("headers", []) for h in entry["headers"]
               if h["key"].lower() == "content-security-policy")
    img_src = next(d for d in csp.split(";") if d.strip().startswith("img-src")).split()
    for slug, p in _sourced().items():
        host = PROVIDER_HOSTS[p["source"]["provider"]].split("/photos/")[0].split("/photo-")[0]
        assert host in img_src, f"{slug}: {host} is not allowed by img-src"
