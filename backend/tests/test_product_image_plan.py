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
# exact pixel size per (ratio, role) for licensed stock photos; "master" keeps the native aspect
EXPECTED_SIZE = {("4x5", "hero"): (1200, 1500), ("4x5", "thumb"): (800, 1000), ("1x1", "gallery"): (800, 800),
                 ("3x2", "gallery"): (1200, 800), ("16x9", "gallery"): (1280, 720)}
RATIO_VALUE = {"4x5": 0.8, "1x1": 1.0, "3x2": 1.5, "16x9": 16 / 9}
PROVIDER_HOSTS = {"pexels": "https://images.pexels.com/photos/", "unsplash": "https://images.unsplash.com/photo-",
                  "generated": "https://confit-a.vercel.app/product-media/"}
STOCK_ROLES = sorted([("4x5", "hero"), ("4x5", "thumb"), ("1x1", "gallery"), ("3x2", "gallery"),
                      ("16x9", "gallery"), ("master", "gallery")])
# generated visuals are published only in sizes that exist without upscaling or cropping the product
GENERATED_ROLES = sorted([("4x5", "hero"), ("4x5", "thumb"), ("master", "gallery")])


def _sourced():
    return {s: p for s, p in PLAN["products"].items() if p["source"]}


def test_every_product_has_an_image_source():
    assert len(PLAN["products"]) == 12
    assert [s for s, p in PLAN["products"].items() if not p["source"]] == []


def test_each_source_is_used_by_at_most_one_product():
    ids = [p["source"]["photo_id"] for p in _sourced().values()]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("slug", sorted(_sourced()))
def test_roles_match_provider_and_respect_one_row_per_ratio(slug):
    p = PLAN["products"][slug]
    want = GENERATED_ROLES if p["source"]["provider"] == "generated" else STOCK_ROLES
    assert sorted((r["ratio"], r["role"]) for r in p["renditions"]) == want
    stored = [r["ratio"] for r in p["renditions"] if r["role"] != "thumb"]
    assert len(stored) == len(set(stored))  # schema: uq_product_image_ratio_format
    assert sum(1 for r in p["renditions"] if r["is_primary"]) == 1


@pytest.mark.parametrize("slug", sorted(_sourced()))
def test_renditions_have_consistent_dimensions_and_hosts(slug):
    p = PLAN["products"][slug]
    generated = p["source"]["provider"] == "generated"
    for r in p["renditions"]:
        assert r["format"] == "jpeg"
        assert len(r["md5"]) == 32 and r["bytes"] > 0
        key = (r["ratio"], r["role"])
        if generated:
            assert (r["width"], r["height"]) == (r["requested_w"], r["requested_h"])
            if r["ratio"] == "4x5":
                assert abs(r["width"] / r["height"] - 0.8) < 0.01
        elif key in EXPECTED_SIZE:
            assert (r["width"], r["height"]) == EXPECTED_SIZE[key] == (r["requested_w"], r["requested_h"])
            assert abs(r["width"] / r["height"] - RATIO_VALUE[r["ratio"]]) < 0.01
        else:
            assert r["ratio"] == "master" and r["width"] == r["requested_w"]
        assert r["url"].startswith(PROVIDER_HOSTS[p["source"]["provider"]])


def test_csp_img_src_allows_every_image_host_used_by_the_plan():
    """A host missing from vercel.json img-src makes browsers block the image (found live on 2026-10-09)."""
    vercel = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    csp = next(h["value"] for entry in vercel.get("headers", []) for h in entry["headers"]
               if h["key"].lower() == "content-security-policy")
    img_src = next(d for d in csp.split(";") if d.strip().startswith("img-src")).split()
    for slug, p in _sourced().items():
        if p["source"]["provider"] == "generated":
            assert "'self'" in img_src, "generated visuals are served same-origin from frontend/public"
            continue
        host = PROVIDER_HOSTS[p["source"]["provider"]].split("/photos/")[0].split("/photo-")[0]
        assert host in img_src, f"{slug}: {host} is not allowed by img-src"


def _load_repair_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("repair_product_images", REPO / "backend/scripts/repair_product_images.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_planned_rows_label_generated_visuals_as_generated_not_stock():
    """Regression: planned_rows used to write source_type='stock' for every row, including AI visuals."""
    rows = _load_repair_module().planned_rows(PLAN, {slug: i + 1 for i, slug in enumerate(PLAN["products"])})
    source_type_by_provider = {}
    for row in rows:
        provider, source_type = row[11], row[10]
        source_type_by_provider.setdefault(provider, set()).add(source_type)
    assert source_type_by_provider.get("generated") == {"generated"}
    assert all(v == {"stock"} for k, v in source_type_by_provider.items() if k != "generated")
    generated_products = [s for s, p in PLAN["products"].items() if p["source"] and p["source"]["provider"] == "generated"]
    assert sum(1 for row in rows if row[11] == "generated") == 2 * len(generated_products)  # hero + master


def _seed_thumbnails_and_images():
    tree = ast.parse(SEED_SRC)
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        kv = {k.value: v for k, v in zip(node.keys, node.values)
              if isinstance(k, ast.Constant) and isinstance(k.value, str)}
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
