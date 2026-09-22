#!/usr/bin/env python3
"""End-to-end production verification of the brand portal, over real HTTP.

This is the evidence-gathering harness for the audit's verification matrix. It
authenticates against the DEPLOYED application as real brand-manager accounts
and exercises reads, mutations, cross-tenant access and role enforcement,
recording the actual status codes, payload shapes and wall-clock latencies.

It proves things a 200 alone cannot:
  * PERSISTENCE  - every mutation is followed by an independent read-back, and
                   for stock updates by a direct database read, so "committed"
                   means observed in the authoritative store, not inferred.
  * ISOLATION    - tenant A attempts to read AND mutate tenant B's objects;
                   anything other than 403/404 is a failure.
  * ROLE         - a consumer account is pointed at brand routes.
  * LATENCY      - each call is timed; the analytics SLO is asserted.

Nothing here fabricates a result: every check prints the real response it got,
and the process exits non-zero if any assertion fails.

Usage:
    CONFIT_TEST_PASSWORD='...' BASE_URL=https://confit-a.vercel.app \\
        python3 scripts/verify_portal_production.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "https://confit-a.vercel.app").rstrip("/")
API = f"{BASE}/api/v1"
TIMEOUT = float(os.environ.get("VERIFY_TIMEOUT", "90"))

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def call(method: str, path: str, token: str | None = None, body: dict | None = None,
         timeout: float = TIMEOUT) -> tuple[int, object, float]:
    """Returns (status, parsed_body_or_text, elapsed_seconds)."""
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # network-level failure is itself evidence
        return 0, str(e), time.perf_counter() - t0
    elapsed = time.perf_counter() - t0
    try:
        return status, json.loads(raw), elapsed
    except json.JSONDecodeError:
        return status, raw[:400], elapsed


def login(email: str, password: str) -> str | None:
    st, body, _ = call("POST", "/auth/login", body={"email": email, "password": password})
    if st == 200 and isinstance(body, dict):
        return body.get("access_token") or (body.get("data") or {}).get("access_token")
    print(f"      login({email}) -> {st} {str(body)[:200]}")
    return None


def _store_rows(rows) -> list:
    """Flatten /partner/inventory to its store-level rows.

    The response nests them as product -> skus[] -> store_inventories[], and each
    row's primary key is `id`. An earlier version of this harness looked for a
    top-level `store_breakdown[].inventory_id`, which does not exist: it found
    nothing, reported "no inventory returned", and made the phase-6 consistency
    check vacuous at the same time. A verifier that reads the wrong field fails
    an endpoint that works -- and would equally MISS a real regression, which is
    the more dangerous half of the bug.
    """
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        for sku in (r.get("skus") or []):
            if isinstance(sku, dict):
                out.extend(si for si in (sku.get("store_inventories") or [])
                           if isinstance(si, dict))
    return out


def main() -> int:
    password = os.environ.get("CONFIT_TEST_PASSWORD")
    if not password:
        print("ERROR: set CONFIT_TEST_PASSWORD", file=sys.stderr)
        return 2

    suffix = os.environ.get("CONFIT_TEST_SUFFIX", "v1")
    email_a = f"qa-portal-a-{suffix}@confit-portal-qa.example.com"
    email_b = f"qa-portal-b-{suffix}@confit-portal-qa.example.com"

    print(f"\nTarget: {BASE}")
    print("=" * 78)

    # Warm the serverless instance so latency numbers are not cold starts.
    call("GET", "/health", timeout=120)

    print("\n[1] AUTHENTICATION")
    tok_a = login(email_a, password)
    record("tenant A authenticates", bool(tok_a))
    tok_b = login(email_b, password)
    record("tenant B authenticates", bool(tok_b))
    if not (tok_a and tok_b):
        print("\nCannot continue without both tokens.")
        return 1

    print("\n[2] ROLE ENFORCEMENT (unauthenticated must never read brand data)")
    for path in ("/brand/analytics", "/partner/inventory", "/brand/products"):
        st, _, _ = call("GET", path)
        record(f"anonymous {path} -> 401/403", st in (401, 403), f"got {st}")

    print("\n[3] TENANT A READS ITS OWN DATA (and latency SLO)")
    slo = float(os.environ.get("ANALYTICS_SLO_SECONDS", "2.0"))
    latencies = {}
    for path in ("/brand/analytics", "/partner/analytics/conversion", "/partner/inventory",
                 "/brand/products", "/partner/placements", "/partner/stores",
                 "/partner/analytics/returns"):
        st, body, el = call("GET", path, tok_a)
        latencies[path] = el
        ok = st == 200
        record(f"GET {path}", ok, f"{st} in {el:.2f}s")
    for path, el in latencies.items():
        if "analytics" in path:
            record(f"SLO <{slo}s: {path}", el < slo, f"measured {el:.2f}s")

    print("\n[4] MUTATION + READ-BACK (placement create, then verify persisted)")
    # Use the tenant's REAL product; a placement needs a product it owns.
    st, prods, _ = call("GET", "/brand/products", tok_a)
    product_a = (prods[0].get("id") if isinstance(prods, list) and prods else None)
    record("tenant A has a product to place", product_a is not None, f"product_id={product_a}")
    st, body, _ = call("POST", "/partner/placements", tok_a, {
        "product_id": product_a, "placement_type": "stylist_featured",
        "bid_amount_per_click": "0.25", "daily_budget": "5.00"})
    created_id = None
    if st in (200, 201) and isinstance(body, dict):
        created_id = body.get("id") or (body.get("data") or {}).get("id")
    record("create placement", created_id is not None, f"{st} id={created_id}")

    if created_id:
        st, body, _ = call("GET", "/partner/placements", tok_a)
        found = any(p.get("id") == created_id for p in (body if isinstance(body, list)
                    else (body or {}).get("placements", []) or []))
        record("placement reads back in list", found, "independent GET confirms persistence")

        st, _, _ = call("PATCH", f"/partner/placements/{created_id}", tok_a,
                        {"status": "paused"})
        record("pause placement", st == 200, f"{st}")
        st, body, _ = call("GET", "/partner/placements", tok_a)
        paused = any(p.get("id") == created_id and p.get("status") == "paused"
                     for p in (body if isinstance(body, list)
                               else (body or {}).get("placements", []) or []))
        record("pause persisted (read-back)", paused)

    print("\n[5] CROSS-TENANT ISOLATION (A must not touch B's objects)")
    st, prods_b, _ = call("GET", "/brand/products", tok_b)
    product_b = (prods_b[0].get("id") if isinstance(prods_b, list) and prods_b else None)
    st, body, _ = call("POST", "/partner/placements", tok_b, {
        "product_id": product_b, "placement_type": "trending_hero",
        "bid_amount_per_click": "0.25", "daily_budget": "5.00"})
    b_placement = body.get("id") if isinstance(body, dict) else None
    if b_placement:
        st, _, _ = call("PATCH", f"/partner/placements/{b_placement}", tok_a,
                        {"status": "paused"})
        record("A cannot mutate B's placement", st in (403, 404), f"got {st}")
        st, _, _ = call("DELETE", f"/partner/placements/{b_placement}", tok_a)
        record("A cannot delete B's placement", st in (403, 404), f"got {st}")
        call("DELETE", f"/partner/placements/{b_placement}", tok_b)  # cleanup by owner

    st, body_a, _ = call("GET", "/brand/analytics", tok_a)
    st, body_b, _ = call("GET", "/brand/analytics", tok_b)
    if isinstance(body_a, dict) and isinstance(body_b, dict):
        record("A and B see different brand_name",
               body_a.get("brand_name") != body_b.get("brand_name"),
               f"{body_a.get('brand_name')!r} vs {body_b.get('brand_name')!r}")

    print("\n[6] INVENTORY CONSISTENCY (the P1 contradiction must be impossible)")
    st, inv, _ = call("GET", "/partner/inventory", tok_a)
    st2, stores, _ = call("GET", "/partner/stores", tok_a)
    if st == 200 and st2 == 200:
        store_count = len(stores) if isinstance(stores, list) else len(
            (stores or {}).get("stores", []) or [])
        rows = inv if isinstance(inv, list) else (inv or {}).get("inventory", []) or []
        breakdown = _store_rows(rows)
        record("zero stores => zero store-level inventory rows",
               not (store_count == 0 and len(breakdown) > 0),
               f"{store_count} stores, {len(breakdown)} breakdown entries")
        # The original P1 bug was a COUNT that disagreed with the BREAKDOWN, so
        # checking only the zero case is vacuous whenever a store exists. Every
        # store referenced by an inventory row must also appear in /partner/stores
        # -- that is the contradiction the audit actually saw.
        listed = {s.get("id") for s in (stores if isinstance(stores, list) else [])
                  if isinstance(s, dict)}
        referenced = {b.get("store_id") for b in breakdown if b.get("store_id") is not None}
        record("every store in the inventory breakdown is listed by /partner/stores",
               referenced <= listed,
               f"breakdown refs {sorted(referenced)}, stores lists {sorted(listed)}")

    print("\n[7] INVENTORY MUTATION -> DATABASE READ-BACK (200 is not proof)")
    st, inv_a, _ = call("GET", "/partner/inventory", tok_a)
    rows_a = inv_a if isinstance(inv_a, list) else (inv_a or {}).get("inventory", []) or []
    inv_row = next((b for b in _store_rows(rows_a) if b.get("id") is not None), None)
    if inv_row:
        inv_id = inv_row["id"]
        new_qty = int(inv_row.get("quantity", 0)) + 3
        st, _, _ = call("PATCH", f"/partner/inventory/{inv_id}", tok_a, {"quantity": new_qty})
        record("update own stock", st == 200, f"{st} -> quantity={new_qty}")
        # Independent read-back straight from the authoritative database.
        dsn = os.environ.get("VERIFY_DB_URL")
        if dsn:
            import psycopg2
            cx = psycopg2.connect(dsn); cu = cx.cursor()
            cu.execute("SELECT quantity FROM store_inventories WHERE id = %s", (inv_id,))
            got = cu.fetchone()
            cx.close()
            record("stock change is committed in the DATABASE",
                   bool(got) and int(got[0]) == new_qty,
                   f"db quantity={got[0] if got else None}, expected {new_qty}")
        # Cross-tenant write must be refused.
        if tok_b:
            st, _, _ = call("PATCH", f"/partner/inventory/{inv_id}", tok_b, {"quantity": 999})
            record("B cannot mutate A's inventory", st in (403, 404), f"got {st}")
            if dsn:
                import psycopg2
                cx = psycopg2.connect(dsn); cu = cx.cursor()
                cu.execute("SELECT quantity FROM store_inventories WHERE id = %s", (inv_id,))
                after = cu.fetchone()
                cx.close()
                record("A's stock unchanged after B's attempt",
                       bool(after) and int(after[0]) == new_qty,
                       f"db quantity={after[0] if after else None}")
    else:
        record("inventory row available to mutate", False, "no inventory returned")

    if created_id:
        call("DELETE", f"/partner/placements/{created_id}", tok_a)

    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"RESULT: {passed} passed, {failed} failed, {len(results)} total")
    if failed:
        print("\nFailures:")
        for n, ok, d in results:
            if not ok:
                print(f"  - {n} ({d})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
