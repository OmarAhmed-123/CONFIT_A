#!/usr/bin/env python3
"""Repair the catalogue's product imagery so the database only describes files that exist.

Background (audited 2026-10-09 on production, read-only):
  * product_images held 120 rows (10 per product) whose public_url returned HTTP 404 and whose
    width/height/bytes/checksum described files that were never uploaded. No code path in the
    repository reads that table, and the /api/v1/media route does not exist in main.
  * 4 of 12 products showed a photo that did not depict the product (e.g. floral stilettos for
    "metallic strappy sandals", a T-shirt for a "polo shirt").

What this script does:
  * Reads backend/scripts/data/product_image_plan_2026-10-09.json (keyed by slug, not id).
  * Re-fetches every rendition and aborts unless HTTP 200, decodes, and matches the plan's
    dimensions, byte count and MD5 exactly. Nothing is written if any file has changed upstream.
  * Refuses to write unless the database is at the audited Alembic revision and holds the
    expected 12 products (prevents an accidental run against another environment).
  * Backs up the current rows to JSON, then applies in ONE transaction: replace product_images rows
    for the 12 products, set products.thumbnail_url / images to the verified renditions (or to an
    empty string for products without a verified match, which the storefront renders as an
    explicit placeholder).
  * --verify is read-only: checks the live catalogue and every stored row the same way.
  * --rollback restores the products and product_images rows from a backup file.

Usage (DATABASE_URL must be a PostgreSQL DSN; it is never printed):
    python backend/scripts/repair_product_images.py            # dry run (default)
    python backend/scripts/repair_product_images.py --apply --backup docs/data-repairs/<file>.json
    python backend/scripts/repair_product_images.py --verify
    python backend/scripts/repair_product_images.py --rollback docs/data-repairs/<file>.json
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO / "backend/scripts/data/product_image_plan_2026-10-09.json"
AUDITED_REVISION = "0035_product_images"
EXPECTED_PRODUCTS = 12
UA = {"User-Agent": "CONFIT-catalog-verifier/1.0"}
RATIO_TARGET = {"4x5": 0.8, "1x1": 1.0, "3x2": 1.5, "16x9": 16 / 9}


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def fetch_check(rendition: dict) -> dict:
    """Return the live measurements for one rendition and whether they match the plan."""
    import requests
    from PIL import Image

    out = {"url": rendition["url"], "ratio": rendition["ratio"]}
    try:
        resp = requests.get(rendition["url"], headers=UA, timeout=30)
        out["http"] = resp.status_code
        if resp.status_code != 200:
            out["ok"] = False
            return out
        im = Image.open(io.BytesIO(resp.content))
        im.load()
        out.update(width=im.size[0], height=im.size[1], bytes=len(resp.content),
                   md5=hashlib.md5(resp.content).hexdigest(), format=(im.format or "").lower())
        out["ok"] = (out["width"], out["height"], out["bytes"], out["md5"]) == (
            rendition["width"], rendition["height"], rendition["bytes"], rendition["md5"])
    except Exception as exc:  # network or decode failure is a verification failure, never a silent pass
        out.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:120]}")
    return out


def verify_plan_against_upstream(plan: dict) -> list[dict]:
    jobs = [(slug, r) for slug, p in plan["products"].items() for r in p["renditions"]]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda j: fetch_check(j[1]) | {"slug": j[0]}, jobs))
    bad = [r for r in results if not r["ok"]]
    if bad:
        raise SystemExit(f"ABORT: {len(bad)} rendition(s) differ from the plan upstream, e.g. {bad[0]}")
    return results


def connect(dsn: str):
    import psycopg2
    return psycopg2.connect(dsn, connect_timeout=15)


def guard(cur, plan: dict) -> None:
    cur.execute("select version_num from alembic_version")
    revs = [r[0] for r in cur.fetchall()]
    if revs != [plan["db_revision_audited"]]:
        raise SystemExit(f"ABORT: database revision {revs} != audited {plan['db_revision_audited']}")
    cur.execute("select count(*) from products where is_active")
    n = cur.fetchone()[0]
    if n != EXPECTED_PRODUCTS:
        raise SystemExit(f"ABORT: {n} active products, expected {EXPECTED_PRODUCTS}")


def snapshot(cur) -> dict:
    cur.execute("select id, slug, thumbnail_url, images from products order by id")
    products = [{"id": r[0], "slug": r[1], "thumbnail_url": r[2], "images": r[3]} for r in cur.fetchall()]
    cols = ["id", "product_id", "storage_key", "public_url", "ratio", "format", "width", "height", "bytes", "role",
            "is_primary", "source_type", "provider", "source_ref", "attribution", "checksum", "created_at"]
    cur.execute(f"select {', '.join(cols)} from product_images order by id")
    rows = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        d["created_at"] = d["created_at"].isoformat()
        rows.append(d)
    return {"taken_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "products": products, "product_images": rows}


def planned_rows(plan: dict, id_by_slug: dict) -> list[tuple]:
    """One product_images row per (product, ratio, format): schema constraint uq_product_image_ratio_format.

    The 800x1000 card thumbnail is a second 4:5 JPEG, so it cannot be a product_images row; it is stored
    in products.thumbnail_url and verified there (verify_live checks both fields).
    """
    rows = []
    for slug, p in plan["products"].items():
        if not p["source"]:
            continue
        pid = id_by_slug[slug]
        for r in p["renditions"]:
            if r["role"] == "thumb":
                continue
            rows.append((pid, f"{p['source']['provider']}:{p['source']['photo_id']}:{r['ratio']}:{r['role']}", r["url"],
                         r["ratio"], r["format"], r["width"], r["height"], r["bytes"], r["role"], r["is_primary"],
                         "stock", p["source"]["provider"], p["source"]["source_ref"], p["source"]["attribution"], r["md5"]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--rollback", metavar="BACKUP_JSON")
    ap.add_argument("--backup", metavar="PATH", help="where --apply writes the pre-change snapshot")
    args = ap.parse_args()
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise SystemExit("DATABASE_URL is not set")
    plan = load_plan()

    if args.verify:
        return verify_live(plan, dsn)

    if args.rollback:
        return rollback(Path(args.rollback), dsn, plan)

    results = verify_plan_against_upstream(plan)
    print(f"upstream check: {len(results)} renditions match the plan (HTTP 200, dims, bytes, md5)")
    with connect(dsn) as conn:
        cur = conn.cursor()
        guard(cur, plan)
        snap = snapshot(cur)
        id_by_slug = {p["slug"]: p["id"] for p in snap["products"]}
        missing = [s for s in plan["products"] if s not in id_by_slug]
        if missing:
            raise SystemExit(f"ABORT: plan slugs not in database: {missing}")
        rows = planned_rows(plan, id_by_slug)
        print(f"current: {len(snap['product_images'])} product_images rows; planned: {len(rows)} rows for "
              f"{sum(1 for p in plan['products'].values() if p['source'])} products; "
              f"{sum(1 for p in plan['products'].values() if not p['source'])} placeholders")
        if not args.apply:
            print("dry run: nothing written. Re-run with --apply --backup <path> to write.")
            return 0
        if not args.backup:
            raise SystemExit("ABORT: --apply requires --backup <path>")
        Path(args.backup).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"backup written: {args.backup}")
        try:
            cur.execute("delete from product_images where product_id = any(%s)", ([p["id"] for p in snap["products"]],))
            deleted = cur.rowcount
            cur.executemany(
                "insert into product_images (product_id, storage_key, public_url, ratio, format, width, height, bytes, role, "
                "is_primary, source_type, provider, source_ref, attribution, checksum) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
            for slug, p in plan["products"].items():
                hero = next((r["url"] for r in p["renditions"] if r["role"] == "hero"), None)
                thumb = next((r["url"] for r in p["renditions"] if r["role"] == "thumb"), None)
                cur.execute("update products set thumbnail_url = %s, images = %s where id = %s",
                            (thumb or "", json.dumps([hero]) if hero else "[]", id_by_slug[slug]))
            cur.execute("select count(*) from product_images where product_id = any(%s)", ([p["id"] for p in snap["products"]],))
            assert cur.fetchone()[0] == len(rows), "row count after insert differs from plan"
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print(f"committed: deleted {deleted} phantom rows, inserted {len(rows)} verified rows, updated 12 products")
    return 0


def verify_live(plan: dict, dsn: str) -> int:
    with connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("select id, slug, thumbnail_url, images from products where is_active order by id")
        products = cur.fetchall()
        cur.execute("select product_id, public_url, ratio, width, height, bytes, checksum from product_images")
        rows = cur.fetchall()
    import requests
    from PIL import Image
    failures = []
    checked = 0

    def probe(url, want=None):
        nonlocal checked
        checked += 1
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code != 200:
                return {"url": url, "http": r.status_code}
            im = Image.open(io.BytesIO(r.content))
            im.load()
            return {"url": url, "http": 200, "width": im.size[0], "height": im.size[1], "bytes": len(r.content),
                    "md5": hashlib.md5(r.content).hexdigest()}
        except Exception as exc:
            return {"url": url, "error": type(exc).__name__}

    for pid, slug, thumb, images in products:
        imgs = json.loads(images or "[]")
        if not thumb and not imgs:
            continue  # honest placeholder: intentionally no image
        for url in filter(None, [thumb, *imgs]):
            m = probe(url)
            if m.get("http") != 200:
                failures.append({"slug": slug, "field": "products", **m})
            elif m["width"] < 600:
                failures.append({"slug": slug, "field": "products", "small": m["width"]})
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda row: (row, probe(row[1])), rows))
    for (pid, url, ratio, w, h, nbytes, cks), m in results:
        if m.get("http") != 200 or (m.get("width"), m.get("height"), m.get("bytes"), m.get("md5")) != (w, h, nbytes, cks):
            failures.append({"product_id": pid, "ratio": ratio, "field": "product_images", **m})
        elif ratio in RATIO_TARGET and abs(m["width"] / m["height"] - RATIO_TARGET[ratio]) > 0.01:
            failures.append({"product_id": pid, "ratio": ratio, "field": "aspect", **m})
    report = {"checked_urls": checked, "products": len(products), "product_images_rows": len(rows),
              "placeholders": [s for _, s, t, i in products if not t and json.loads(i or "[]") == []],
              "failures": failures}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if failures else 0


def rollback(backup: Path, dsn: str, plan: dict) -> int:
    snap = json.loads(backup.read_text(encoding="utf-8"))
    with connect(dsn) as conn:
        cur = conn.cursor()
        guard(cur, plan)
        try:
            cur.execute("delete from product_images where product_id = any(%s)", ([p["id"] for p in snap["products"]],))
            cols = ["id", "product_id", "storage_key", "public_url", "ratio", "format", "width", "height", "bytes", "role",
                    "is_primary", "source_type", "provider", "source_ref", "attribution", "checksum", "created_at"]
            cur.executemany(f"insert into product_images ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                            [tuple(r[c] for c in cols) for r in snap["product_images"]])
            for p in snap["products"]:
                cur.execute("update products set thumbnail_url = %s, images = %s where id = %s",
                            (p["thumbnail_url"], p["images"], p["id"]))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    print(f"rolled back to snapshot taken {snap['taken_utc']}: {len(snap['product_images'])} rows restored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
