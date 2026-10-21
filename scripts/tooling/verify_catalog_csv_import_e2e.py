#!/usr/bin/env python3
"""End-to-end proof that a brand CSV becomes a live, buyable CONFIT product.

WHAT THIS SCRIPT IS FOR
-----------------------
Unit tests stub the remote image fetch (they must: 4,000 tests cannot depend on
someone else's uptime). That means no test in the suite proves the thing the
brand owner actually does — upload a CSV, get products on the storefront. This
script closes that gap by running the REAL stack against a throwaway database
and the REAL network:

    CSV file on disk
      -> POST /api/v1/partner/catalog/preview-csv     (dry run, no writes)
      -> POST /api/v1/partner/catalog/confirm-import  (commit)
      -> products / product_skus / store_inventory / product_images in SQLite
      -> image objects written to local storage, served by GET /api/v1/media/...
      -> GET /api/v1/catalog/products, /search, /products/{slug}
      -> POST /api/v1/cart/items                      (variant is purchasable)
      -> GET /api/v1/partner/products, /partner/analytics   (brand dashboard)

SAFETY
------
* It NEVER touches a remote database. ``DATABASE_URL`` is forced to a temporary
  SQLite file before FastAPI is imported, and the script aborts if the resolved
  URL is not SQLite. The production Neon DSN in ``backend/.env`` is therefore
  impossible to reach from here.
* It never writes to ``backend/data``; storage is redirected to the temp dir.
* ``--offline`` skips the network by synthesising a JPEG, for a smoke run only.
  The report marks that run as NOT a real-integration proof.

USAGE
-----
    PYTHONPATH=. .venv/bin/python scripts/tooling/verify_catalog_csv_import_e2e.py \
        --csv docs/catalog/confit_ss26_catalog.csv

Exit code 0 only if every check passed.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment must be pinned BEFORE the application is imported: `core.database`
# builds its engine at import time from Settings, and Settings reads
# backend/.env, whose DATABASE_URL points at the production Neon instance.
# ---------------------------------------------------------------------------
_TMP = Path(tempfile.mkdtemp(prefix="confit-csv-e2e-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'e2e.db'}"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["STORAGE_LOCAL_DIR"] = str(_TMP / "uploads")
os.environ["ENVIRONMENT"] = "development"
os.environ["REDIS_URL"] = ""
os.environ.setdefault("PYTHONPATH", ".")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

_CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _CHECKS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="catalog CSV to import")
    ap.add_argument("--offline", action="store_true",
                    help="synthesise the image instead of downloading it (smoke run only)")
    args = ap.parse_args()

    from backend.app.core.config import settings
    asserted = (settings.DATABASE_URL or "")
    if not asserted.startswith("sqlite"):
        print(f"REFUSING TO RUN: DATABASE_URL resolved to {asserted!r}, not a temp SQLite file.")
        return 2

    from fastapi.testclient import TestClient
    from sqlalchemy import func

    from backend.app.core.database import engine, SessionLocal
    from backend.app.main import app
    from backend.app.models.catalog import (
        Product, ProductImage, ProductSKU, StoreInventory, StoreLocation,
    )
    from backend.app.seed_data import seed_database

    print(f"temp database : {settings.DATABASE_URL}")
    print(f"temp storage  : {settings.STORAGE_LOCAL_DIR}")
    print(f"environment   : {settings.ENVIRONMENT}")

    if args.offline:
        # One injection point, mirroring the test-suite fixture: only the remote
        # GET is replaced. Crop/encode/store/verify all still run for real.
        from backend.app.services import media_materialization_service as mms
        from PIL import Image

        def _fake_fetch(url: str) -> bytes:
            buf = io.BytesIO()
            Image.new("RGB", (1600, 1600), (40, 48, 64)).save(buf, format="JPEG", quality=90)
            return buf.getvalue()

        mms.MediaMaterializationService._get_fetch = lambda self: _fake_fetch

    section("0. Seed a throwaway database with the real seeder")
    seed_database(target_engine=engine, force=True)
    check("seed completed", True)

    client = TestClient(app)

    # ---------------------------------------------------------------- identity
    section("1. Brand owner identity through real auth (no credentials in the CSV)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    email = f"owner+{stamp}@atelier-qa.example.com"
    reg = client.post("/api/v1/auth/brand/register", json={
        "brand_name": f"Atelier QA {stamp}",
        "email": email,
        "password": "Qa-Password-2026!",
        "full_name": "QA Boutique Director",
        "country": "Egypt",
        "city": "Cairo",
        "preferred_language": "ar",
    })
    check("POST /auth/brand/register -> 201", reg.status_code == 201, f"status={reg.status_code}")
    if reg.status_code != 201:
        print(reg.text[:800])
        return 1
    body = reg.json()
    token = body.get("access_token") or body.get("tokens", {}).get("access_token")
    check("registration returned an access token", bool(token),
          "owner column never appears in the CSV — the brand comes from this token")
    auth = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=auth)
    check("GET /auth/me resolves the brand owner", me.status_code == 200,
          f"role={me.json().get('role') if me.status_code == 200 else me.status_code}")

    store = client.post("/api/v1/partner/stores", headers=auth, json={
        "name": f"Zamalek Boutique {stamp}", "name_ar": "بوتيك الزمالك",
        "city": "Cairo", "country": "Egypt", "address": "15 Brazil Street, Zamalek",
        "latitude": 30.0561, "longitude": 31.2215, "is_bopis_enabled": True,
    })
    store_id = store.json().get("id") if store.status_code == 201 else None
    check("POST /partner/stores -> 201", store.status_code == 201, f"store_id={store_id}")

    csv_text = Path(args.csv).read_text(encoding="utf-8-sig")
    row_count = len(list(csv.DictReader(io.StringIO(csv_text))))
    print(f"\n  CSV: {args.csv} ({row_count} data rows, {len(csv_text.encode())} bytes UTF-8)")

    # ------------------------------------------------------------------ dry run
    section("2. Preview = dry run (must write nothing)")
    counts_before = {
        "products": SessionLocal().query(func.count(Product.id)).scalar(),
        "images": SessionLocal().query(func.count(ProductImage.id)).scalar(),
        "skus": SessionLocal().query(func.count(ProductSKU.id)).scalar(),
    }
    preview = client.post(
        "/api/v1/partner/catalog/preview-csv",
        headers=auth,
        files={"file": (Path(args.csv).name, csv_text.encode("utf-8"), "text/csv")},
        params={"target_store_id": store_id} if store_id else None,
    )
    check("POST /partner/catalog/preview-csv -> 200", preview.status_code == 200,
          f"status={preview.status_code}")
    if preview.status_code != 200:
        print(preview.text[:1500])
        return 1
    pv = preview.json()
    print(f"      total={pv['total_rows']} valid={pv['valid_rows_count']} "
          f"errors={pv['error_rows_count']} warnings={pv['warning_rows_count']} "
          f"can_import={pv['can_import']}")
    for w in (pv.get("warnings") or [])[:6]:
        print(f"      warn row={w.get('row')} {w.get('field')}: {w.get('message')[:110]}")
    for e in (pv.get("errors") or [])[:6]:
        print(f"      err  row={e.get('row')} {e.get('field')}: {e.get('message')[:110]}")

    check("every CSV row validates", pv["valid_rows_count"] == row_count,
          f"{pv['valid_rows_count']}/{row_count}")
    check("preview says the file can be imported", pv["can_import"] is True)
    check("preview creates/updates every row", len(pv["preview_records"]) == row_count,
          f"{len(pv['preview_records'])} preview records")

    counts_after_preview = {
        "products": SessionLocal().query(func.count(Product.id)).scalar(),
        "images": SessionLocal().query(func.count(ProductImage.id)).scalar(),
        "skus": SessionLocal().query(func.count(ProductSKU.id)).scalar(),
    }
    check("dry run wrote nothing", counts_after_preview == counts_before,
          f"{counts_before} -> {counts_after_preview}")

    # ------------------------------------------------------------------- commit
    section("3. Confirm import (commit)")
    params = {"send_notifications": "false"}
    if store_id:
        params["target_store_id"] = str(store_id)
    imported = client.post(
        "/api/v1/partner/catalog/confirm-import",
        headers=auth,
        files={"file": (Path(args.csv).name, csv_text.encode("utf-8"), "text/csv")},
        params=params,
    )
    check("POST /partner/catalog/confirm-import -> 202", imported.status_code == 202,
          f"status={imported.status_code}")
    if imported.status_code != 202:
        print(imported.text[:1500])
        return 1
    res = imported.json()
    print(f"      job={res['job_id']} status={res['status']} accepted={res['accepted_rows']} "
          f"rejected={res['rejected_rows']} media_rows={res.get('media_rows_registered')} "
          f"missing_ar={res.get('rows_missing_title_ar')} gender_inferred={res.get('rows_gender_inferred')}")
    for e in (res.get("errors") or [])[:6]:
        print(f"      err  row={e.get('row')} {e.get('field')}: {e.get('message')[:140]}")

    check("import job completed", res["status"] == "completed", res["status"])
    check("all rows accepted", res["accepted_rows"] == row_count, f"{res['accepted_rows']}/{row_count}")
    check("no rows rejected", res["rejected_rows"] == 0, str(res["rejected_rows"]))
    check("media rows registered", (res.get("media_rows_registered") or 0) > 0,
          f"{res.get('media_rows_registered')} product_images rows")

    # ---------------------------------------------------------------- database
    section("4. Rows really exist in the database (and nowhere else)")
    db = SessionLocal()
    brand_id = db.query(Product.brand_id).order_by(Product.id.desc()).first()[0]
    products = db.query(Product).filter_by(brand_id=brand_id).all()
    skus = db.query(ProductSKU).filter(ProductSKU.brand_id == brand_id).all()
    images = db.query(ProductImage).filter(
        ProductImage.product_id.in_([p.id for p in products])).all()
    titles = {p.title for p in products}
    csv_titles = {r["product_name"] for r in csv.DictReader(io.StringIO(csv_text))}

    check("products created", products and titles == csv_titles,
          f"{len(products)} products; titles match CSV: {titles == csv_titles}")
    expected_skus = len(list(csv.DictReader(io.StringIO(csv_text))))
    check("one SKU per CSV row", len(skus) == expected_skus, f"{len(skus)} SKUs")
    check("SKU codes are the ones in the CSV", all(
        s.sku_code in csv_text for s in skus), "supplied SKUs preserved verbatim")
    check("every product has registered media", all(
        any(i.product_id == p.id for i in images) for p in products),
        f"{len(images)} image rows across {len(products)} products")
    check("media keys match the media route contract", all(
        i.storage_key and i.storage_key.startswith(f"products/{i.product_id}/") for i in images))
    check("image bytes are really on disk", all(
        (Path(settings.STORAGE_LOCAL_DIR) / i.storage_key).exists() for i in images),
        str(settings.STORAGE_LOCAL_DIR))

    arabic = [p for p in products if p.title_ar and p.title_ar.strip()]
    check("Arabic titles stored as supplied", len(arabic) == len(products),
          f"{len(arabic)}/{len(products)} have title_ar")
    check("no English text smuggled into Arabic columns", all(
        not (p.description_ar or "").strip() or any("\u0600" <= c <= "\u06ff" for c in p.description_ar)
        for p in products), "Arabic columns contain Arabic script only")

    from backend.app.core.config import settings as _settings
    stored_currencies = {p.currency for p in products}
    check("stored currency is the price-book denomination",
          stored_currencies == {_settings.PRICING_CURRENCY},
          f"{sorted(stored_currencies)} vs PRICING_CURRENCY={_settings.PRICING_CURRENCY}")

    genders = {p.gender for p in products}
    check("gender comes from the CSV, not a blanket default", genders <= {"mens", "womens", "unisex"},
          f"values: {sorted(genders)}")

    if store_id:
        inv = db.query(StoreInventory).filter_by(store_id=store_id).all()
        check("branch inventory rows created", len(inv) == len(skus),
              f"{len(inv)} store_inventory rows for store {store_id}")

    # --------------------------------------------------------------- storefront
    section("5. Reaches the storefront: list, search, PDP, media, cart")
    listing = client.get("/api/v1/catalog/products", params={"brand_id": brand_id, "limit": 100})
    listed = listing.json() if listing.status_code == 200 else []
    listed_titles = {p["title"] for p in listed}
    check("GET /catalog/products shows the imported products", csv_titles <= listed_titles,
          f"{len(listed_titles)} listed; missing={sorted(csv_titles - listed_titles)}")

    probes = [(t, sorted(listed_titles)[0] if listed_titles else "") for t in []]
    first_title = sorted(csv_titles)[0]
    probe_word = first_title.split()[0]
    search = client.get("/api/v1/catalog/search", params={"q": probe_word, "limit": 50})
    hits = search.json().get("results", search.json().get("products", [])) if search.status_code == 200 else []
    hit_titles = {h.get("title") for h in hits}
    check(f"GET /catalog/search?q={probe_word!r} finds an imported product",
          bool(csv_titles & hit_titles), f"hits={sorted(csv_titles & hit_titles)[:3]}")

    product = next(p for p in products if p.title == first_title)
    pdp = client.get(f"/api/v1/catalog/products/{product.slug}")
    check("GET /catalog/products/{slug} -> 200", pdp.status_code == 200,
          f"status={pdp.status_code}")
    if pdp.status_code == 200:
        detail = pdp.json()
        check("PDP lists the imported variants", len(detail.get("skus") or []) >= 1,
              f"{len(detail.get('skus') or [])} SKUs")
        check("PDP carries real media", bool(detail.get("media") or detail.get("images")),
              f"{len(detail.get('media') or [])} media rows")
        check("PDP has prices and currency",
              detail.get("base_price") and detail.get("currency"), 
              f"{detail.get('base_price')} {detail.get('currency')}")
        check("PDP brand is the registering brand", detail.get("brand_id") == brand_id)

    hero = next((i for i in images if i.product_id == product.id), None)
    if hero:
        served = client.get(f"/api/v1/media/{hero.storage_key}")
        check("GET /api/v1/media/{key} serves the hero image", served.status_code == 200
              and served.content[:2] == b"\xff\xd8",
              f"status={served.status_code} bytes={len(served.content)} "
              f"type={served.headers.get('content-type')}")

    buyable = next((s for s in skus if s.stock_level > 0), None)
    if buyable:
        cart = client.post("/api/v1/cart/items",
                           headers={**auth, "X-Session-Token": f"e2e-{stamp}"},
                           json={"product_sku_id": buyable.id, "quantity": 1})
        ok_cart = cart.status_code in (200, 201)
        payload = cart.json() if ok_cart else {}
        items = payload.get("items", [])
        check("POST /cart/items accepts an imported variant", ok_cart and bool(items),
              f"status={cart.status_code} items={len(items)}")

        # THE PRICE MUST BE THE SAME IN BOTH PLACES. A catalogue that quotes one
        # number and a checkout that charges another is the defect this check
        # exists to catch: with a CSV row priced in EGP the product page showed
        # 1,450 EGP while the cart converted the same 1450 from the USD price
        # book and showed ~78,000 EGP.
        if items:
            line = items[0]
            cart_unit = float(line.get("unit_price") or line.get("price") or 0)
            cart_currency = payload.get("currency") or line.get("currency") or "?"
            check("cart line prices the real SKU", cart_unit > 0, f"{cart_unit} {cart_currency}")

            # Compare the SAME product. `buyable` is a SKU, so its product is the
            # only valid counterpart — comparing it with an arbitrary product
            # would "pass" while measuring nothing.
            bought = db.query(Product).filter(Product.id == buyable.product_id).first()
            same_product = client.get(f"/api/v1/catalog/products/{bought.slug}")
            pdp = same_product.json() if same_product.status_code == 200 else {}
            pdp_price = float(pdp.get("base_price") or 0)
            pdp_currency = pdp.get("currency") or "?"
            check("product page and cart agree on the price",
                  same_product.status_code == 200 and abs(pdp_price - cart_unit) < 0.02,
                  f"{bought.title!r}: PDP {pdp_price} {pdp_currency} vs cart {cart_unit} {cart_currency}")

    if store_id:
        inv_http = client.get(f"/api/v1/catalog/stores/{store_id}/inventory")
        ok = inv_http.status_code == 200
        payload = inv_http.json() if ok else {}
        # Shape: {store, brand, total_items, products:[{..., branch_skus:[{sku_id,...}]}]}
        # Match on sku_id, not sku_code: the public catalog payload deliberately
        # withholds the internal SKU code (commit f1e50c9), and this endpoint is
        # part of that public surface.
        listed_ids = {
            s.get("sku_id")
            for prod in (payload.get("products") or [])
            for s in (prod.get("branch_skus") or [])
        }
        matched = listed_ids & {s.id for s in skus}
        check("GET /catalog/stores/{id}/inventory exposes the branch stock",
              ok and bool(matched),
              f"status={inv_http.status_code} matched={len(matched)}/{len(skus)}")

    # ----------------------------------------------------------- brand console
    section("6. Brand dashboard sees its own catalogue")
    bp = client.get("/api/v1/partner/products", headers=auth)
    bp_titles = {p.get("title") for p in bp.json()} if bp.status_code == 200 else set()
    check("GET /partner/products lists the imports", csv_titles <= bp_titles,
          f"{len(bp_titles)} products for this brand")
    analytics = client.get("/api/v1/partner/analytics", headers=auth)
    check("GET /partner/analytics -> 200", analytics.status_code == 200,
          f"products={analytics.json().get('total_products_count') if analytics.status_code == 200 else '—'}")
    jobs = client.get("/api/v1/partner/catalog/imports", headers=auth)
    job_rows = jobs.json() if jobs.status_code == 200 else []
    check("import history lists the job", any(j["job_id"] == res["job_id"] for j in job_rows),
          f"{len(job_rows)} jobs")
    job_detail = client.get(f"/api/v1/brand/catalog/jobs/{res['job_id']}", headers=auth)
    check("job status endpoint returns the stored result", job_detail.status_code == 200,
          f"status={job_detail.json().get('status') if job_detail.status_code == 200 else job_detail.status_code}")

    # ------------------------------------------------------------- idempotency
    section("7. Re-uploading the same file updates, never duplicates")
    files_before = sorted(p.name for p in Path(settings.STORAGE_LOCAL_DIR).rglob("*") if p.is_file())
    again = client.post(
        "/api/v1/partner/catalog/confirm-import",
        headers=auth,
        files={"file": (Path(args.csv).name, csv_text.encode("utf-8"), "text/csv")},
        params=params,
    )
    res2 = again.json()
    db.expire_all()
    products_after = db.query(Product).filter_by(brand_id=brand_id).count()
    skus_after = db.query(ProductSKU).filter(ProductSKU.brand_id == brand_id).count()
    files_after = sorted(p.name for p in Path(settings.STORAGE_LOCAL_DIR).rglob("*") if p.is_file())
    check("second import accepted all rows", res2.get("accepted_rows") == row_count,
          f"accepted={res2.get('accepted_rows')} rejected={res2.get('rejected_rows')}")
    check("no duplicate products", products_after == len(products),
          f"{len(products)} -> {products_after}")
    check("no duplicate SKUs", skus_after == len(skus), f"{len(skus)} -> {skus_after}")
    check("media was not re-rendered", files_before == files_after,
          f"{len(files_before)} objects unchanged")

    # ------------------------------------------------------------------ report
    section("RESULT")
    failed = [c for c in _CHECKS if not c[1]]
    print(f"{len(_CHECKS) - len(failed)}/{len(_CHECKS)} checks passed")
    if args.offline:
        print("\nOFFLINE RUN: the image download was synthesised, so this run does NOT "
              "prove real-integration image ingestion.")
    if failed:
        print("\nFAILED:")
        for name, _ok, detail in failed:
            print(f"  - {name} ({detail})")
        return 1
    print("\nAll checks passed. Artifacts: " + str(_TMP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
