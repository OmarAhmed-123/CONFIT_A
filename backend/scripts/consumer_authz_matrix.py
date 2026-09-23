"""Consumer authorization matrix — BOLA / BFLA / mass-assignment / property exposure.

Why this file exists
--------------------
§13–§17 of the engagement: an authorization audit has to *exercise* the object-level
path, not just assert that a route has a dependency. Reading `HTTPBearer` on a route
tells you authentication exists. It does not tell you whether User B can read, modify
or delete User A's object, whether a consumer token can reach a brand/admin route via
an alias, or whether a client can set `user_id` / `role` / `status` on its own record.

What it does (all against a LOCAL sqlite instance — never production)
--------------------------------------------------------------------
1. Registers two throwaway users (A, B) and logs them in.
2. Builds request payloads from the live OpenAPI schema, so the paths and bodies are
   the ones the server actually declares — not a hand-written guess that silently
   404s and "proves" nothing.
3. As A, creates objects (wardrobe item, outfit, cart item, …).
4. As B, attempts to read / modify / delete each of A's objects and records the status.
   As of v4 that includes the ORDER read matrix: owned order vs guest order vs anonymous
   vs invalid token, each with the expectation written down, so the guest capability
   cannot be silently dropped by a later authorization fix.
5. As B (consumer), attempts brand/admin routes (BFLA).
6. Attempts mass assignment: privileged fields sent from the client on create/update.
7. Dumps the property names returned for A's own object (object-property exposure).

Probe integrity (§4)
--------------------
The harness fails LOUD:
  * a create that does not return 2xx makes its dependent checks SKIPPED, never PASS;
  * a setup error raises instead of reporting a clean matrix;
  * any cross-user access that returns 2xx is a finding and sets exit code 2;
  * a request that cannot be sent is reported as ERROR, not as a pass.

Usage
-----
    python backend/scripts/consumer_authz_matrix.py --base-url http://localhost:8000 \
        --json /tmp/authz-matrix.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

PASSWORD = "Audit!Passw0rd123"

#: Consumer-visible object endpoints: (label, method, path template, body or None)
#: Templates use {id} which is substituted with the id A's object got back.
OBJECT_CHECKS: List[Tuple[str, str, str, Optional[Dict[str, Any]]]] = [
    ("wardrobe item", "GET", "/wardrobe/items/{id}", None),
    ("wardrobe item", "PATCH", "/wardrobe/items/{id}", {"notes": "modified-by-B"}),
    ("wardrobe item", "DELETE", "/wardrobe/items/{id}", None),
    ("outfit", "GET", "/outfits/{id}", None),
    ("outfit", "PATCH", "/outfits/{id}", {"name": "modified-by-B"}),
    ("outfit", "DELETE", "/outfits/{id}", None),
    ("cart item", "PATCH", "/cart/items/{id}", {"quantity": 5}),
    ("cart item", "DELETE", "/cart/items/{id}", None),
    ("order", "GET", "/commerce/orders/{id}", None),
    ("order", "GET", "/commerce/orders/{id}/tracking", None),
]

#: Brand/Partner/Admin routes a consumer token must never reach (BFLA).
BFLA_CHECKS: List[Tuple[str, str, str]] = [
    ("brand catalog jobs", "GET", "/brand/catalog/jobs"),
    ("brand dashboard", "GET", "/brand/dashboard"),
    ("partner placements", "GET", "/partner/placements"),
    ("admin analytics", "GET", "/admin/analytics/overview"),
    ("admin users", "GET", "/admin/users"),
]

#: Fields a consumer must not be able to set on its own records.
PRIVILEGED_FIELDS = {
    "user_id": "00000000-0000-0000-0000-000000000000",
    "role": "admin",
    "is_admin": True,
    "status": "delivered",
    "total": 0.01,
    "is_live": True,
    "is_paid": True,
    "brand_id": "00000000-0000-0000-0000-000000000001",
}


class Loud(Exception):
    """A setup failure that must abort the run instead of producing a clean matrix."""


class Client:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/") + "/api/v1"
        self.token: Optional[str] = None
        self.rate_limited: List[Dict[str, Any]] = []

    def call(self, method: str, path: str, body: Any = None,
             token: Optional[str] = None, guest: Optional[str] = None) -> Tuple[int, Any]:
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        tok = token if token is not None else self.token
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        if guest:
            # The guest cart/session path is keyed on the app-wide X-Session-Token
            # header (see backend/app/core/rate_limit.py and the guest flow notes in
            # measurement_service/tryon_service). Testing cart ownership requires
            # speaking that protocol, not the bearer one.
            headers["X-Session-Token"] = guest
        req = urllib.request.Request(url, method=method, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
                try:
                    return r.status, json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    return r.status, raw[:300]
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if e.code == 429:
                # Rate limiting is part of what is being audited, not a nuisance to
                # hide: record whether the response tells the caller when to retry
                # (Retry-After, §20) before backing off.
                retry_after = e.headers.get("Retry-After")
                self.rate_limited.append({"path": path, "retry_after": retry_after})
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, raw[:300]
        except urllib.error.URLError as e:
            raise Loud(f"{method} {url} could not be sent: {e}") from e


def build_payload(schema: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal request body from an OpenAPI schema, resolving $ref/anyOf/allOf."""
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        schema = spec["components"]["schemas"].get(name, {})
    for key in ("allOf", "anyOf", "oneOf"):
        if key in schema:
            for sub in schema[key]:
                merged = build_payload(sub, spec)
                if merged:
                    return merged
            return {}
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    out: Dict[str, Any] = {}
    for name in required:
        prop = props.get(name, {})
        if "$ref" in prop:
            out[name] = build_payload(prop, spec)
            continue
        t = prop.get("type")
        enum = prop.get("enum")
        if enum:
            out[name] = enum[0]
        elif t == "integer":
            out[name] = int(prop.get("minimum") or 1)
        elif t == "number":
            out[name] = float(prop.get("minimum") or 1)
        elif t == "boolean":
            out[name] = True
        elif t == "array":
            out[name] = []
        elif t == "object":
            out[name] = {}
        else:
            out[name] = "audit-value"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--json", default="/tmp/authz-matrix.json")
    ap.add_argument("--reuse", default=None,
                    help="JSON with {a,b,pw} to log in with existing accounts instead of registering")
    args = ap.parse_args()

    try:
        spec = json.load(urllib.request.urlopen(
            urllib.request.Request(args.base_url.rstrip("/") + "/openapi.json",
                                   headers={"User-Agent": "confit-authz-audit"}), timeout=60))
    except Exception as e:  # noqa: BLE001 - any failure here invalidates the run
        raise Loud(f"OpenAPI schema unreachable at {args.base_url}: {e}") from e

    a, b = Client(args.base_url), Client(args.base_url)
    stamp = int(time.time())
    results: Dict[str, Any] = {"generated_at": stamp, "checks": [], "setup": {}}

    # ---- register + login -------------------------------------------------
    reuse = {}
    if args.reuse:
        try:
            reuse = json.load(open(args.reuse))
        except OSError as e:
            raise Loud(f"--reuse file unreadable: {e}") from e
    for label, c in (("A", a), ("B", b)):
        if reuse.get(label.lower()):
            email, pw = reuse[label.lower()], reuse.get("pw", PASSWORD)
            st, body = c.call("POST", "/auth/login", {"email": email, "password": pw}, token="")
        else:
            email, pw = f"authz.{label.lower()}.{stamp}@example.com", PASSWORD
            st, body = c.call("POST", "/auth/register", {
                "email": email, "password": pw, "full_name": f"Authz {label}"}, token="")
            if st == 429:
                wait = 65
                print(f"   [429 on register {label}] waiting {wait}s for the auth window")
                time.sleep(wait)
                st, body = c.call("POST", "/auth/register", {
                    "email": email, "password": pw, "full_name": f"Authz {label}"}, token="")
        if st not in (200, 201) or not isinstance(body, dict) or not body.get("access_token"):
            raise Loud(f"auth for {label} failed: {st} {str(body)[:200]}")
        c.token = body["access_token"]
        results["setup"][label] = {"email": email, "user_id": (body.get("user") or {}).get("id")}

    # ---- a real SKU id (payloads must reference real rows, not "audit-value") ---
    sku_id: Optional[int] = None
    try:
        st, prods = a.call("GET", "/catalog/products?limit=1")
        items = prods if isinstance(prods, list) else (prods or {}).get("items") or []
        if items and items[0].get("slug"):
            st, detail = a.call("GET", f"/catalog/products/{items[0]['slug']}")
            skus = (detail or {}).get("skus") or []
            if skus:
                sku_id = skus[0].get("id")
    except Loud:
        raise
    results["setup"]["sku_id"] = sku_id

    # ---- A creates objects -------------------------------------------------
    creations = [
        ("wardrobe", "POST", "/wardrobe/items"),
        ("outfit", "POST", "/outfits"),
        ("cart", "POST", "/cart/items"),
    ]
    created_ids: Dict[str, Any] = {}
    for label, method, path in creations:
        op = spec["paths"].get(path, {}).get(method.lower())
        if op is None:
            results["setup"][label] = "ROUTE ABSENT in schema"
            continue
        payload = build_payload((op.get("requestBody") or {}).get("content", {})
                                .get("application/json", {}).get("schema", {}), spec)
        # Endpoints declare real ids/enums; a placeholder string only produces a 422
        # and a "SKIPPED" that proves nothing.
        if label == "outfit":
            payload = {"title": "Audit Look", "product_sku_ids": [sku_id] if sku_id else []}
        if label == "cart":
            payload = {"product_sku_id": sku_id, "quantity": 1}
            # The cart endpoints are keyed on X-Session-Token as well as the bearer:
            # measured, POST /cart/items without the header answers 422 naming the
            # missing header. Sending it is the difference between testing cart
            # ownership and testing a validation error.
            a_cart_session = f"audit-cart-a-{stamp}"
            st, body = a.call(method, path, payload, guest=a_cart_session)
        else:
            st, body = a.call(method, path, payload)
        results["setup"][label] = {"status": st, "payload_keys": sorted(payload)}
        if 200 <= st < 300 and isinstance(body, dict):
            for key in ("id", "item_id", "outfit_id"):
                if body.get(key):
                    created_ids[label] = body[key]
                    break
            # POST /cart/items answers with the CART, not the item, so the top-level id
            # is the cart's. The cross-actor checks below need the ITEM, which lives in
            # `items[]` — reading only the top level left two checks permanently SKIPPED.
            if label == "cart":
                for item in (body.get("items") or []):
                    if item.get("id"):
                        created_ids[label] = item["id"]
                        break
            results["setup"][label]["id"] = created_ids.get(label)
            results["setup"][label]["response_fields"] = sorted(body.keys())

    # ---- OWNERSHIP CONTROL: the owner must be able to read its own object ----
    # Without this, a 404 for B proves nothing: it could simply mean "no such row".
    for label, tmpl in (("wardrobe item", "/wardrobe/items/{id}"),
                        ("outfit", "/outfits/{id}")):
        oid = created_ids.get({"wardrobe item": "wardrobe", "outfit": "outfit"}[label])
        if not oid:
            continue
        st, _ = a.call("GET", tmpl.replace("{id}", str(oid)))
        results["checks"].append({
            "check": f"CONTROL: owner A GET {tmpl}", "label": label, "status": st,
            "verdict": "OK — owner can read the object" if 200 <= st < 300
            else "INCONCLUSIVE — owner cannot read what it created"})

    # ---- guest cart: two different X-Session-Token values ------------------
    if sku_id:
        guest_a, guest_b = f"audit-ga-{stamp}", f"audit-gb-{stamp}"
        st, body = a.call("POST", "/cart/items", {"product_sku_id": sku_id, "quantity": 1},
                          token="", guest=guest_a)
        guest_item = None
        if 200 <= st < 300 and isinstance(body, dict):
            for item in (body.get("items") or []):
                guest_item = item.get("id") or item.get("item_id")
                if guest_item:
                    break
        results["setup"]["guest_cart_item"] = {"status": st, "id": guest_item}
        if guest_item:
            for method, payload in (("GET", None), ("PATCH", {"quantity": 3}), ("DELETE", None)):
                st_b, _ = b.call(method, f"/cart/items/{guest_item}", payload, token="", guest=guest_b)
                results["checks"].append({
                    "check": f"GUEST B {method} /cart/items/{{id}} (A's guest cart)",
                    "label": "guest cart", "status": st_b,
                    "verdict": "FAIL — guest cart reachable with another session token"
                    if 200 <= st_b < 300 else "BLOCKED"})
            st_a, _ = a.call("GET", "/cart/items", token="", guest=guest_a)
            results["checks"].append({
                "check": "CONTROL: guest A GET /cart/items", "label": "guest cart", "status": st_a,
                "verdict": "OK — owner session sees its cart" if 200 <= st_a < 300
                else "INCONCLUSIVE — owner session cannot read its own cart"})

    # ---- ORDER READ AUTHORIZATION (added 2026-09-23, harness v4) -----------
    # Found by hand before it was instrumented; the point of adding it here is that a
    # defect which took a manual probe to discover must not need another manual probe to
    # stay fixed. Three claims are measured separately, because "anonymous is denied" and
    # "anonymous is denied everything" are different statements:
    #   * an order that belongs to a REGISTERED CUSTOMER must not be readable with no
    #     credentials (this was the defect: 200 + recipient name, address, items);
    #   * a GENUINE GUEST order must stay readable by its number with no credentials —
    #     if the fix removes that, the harness must fail, not applaud;
    #   * a different authenticated user must stay denied (403/404), as before.
    order_owned = order_guest = None
    order_session = f"audit-order-{stamp}"
    checkout_body = {
        "payment_method": "cod", "fulfillment_type": "delivery",
        "recipient_name": "Authz Buyer", "phone": "+201000000000",
        "address_line": "1 Audit Street", "city": "Giza", "country": "EG",
    }
    if sku_id:
        a.call("POST", "/cart/items", {"product_sku_id": sku_id, "quantity": 1},
               guest=order_session)
        st, body = a.call("POST", "/checkout", checkout_body, guest=order_session)
        if 200 <= st < 300 and isinstance(body, dict):
            order_owned = body.get("order_number")
        results["setup"]["owned_order"] = {"status": st, "order_number": order_owned}

        guest_order_session = f"audit-guest-order-{stamp}"
        anon_guest = Client(args.base_url)
        anon_guest.token = ""
        anon_guest.call("POST", "/cart/items", {"product_sku_id": sku_id, "quantity": 1},
                        token="", guest=guest_order_session)
        st, body = anon_guest.call(
            "POST", "/checkout",
            dict(checkout_body, guest_email=f"authz.guest.{stamp}@example.com"),
            token="", guest=guest_order_session)
        if 200 <= st < 300 and isinstance(body, dict):
            order_guest = body.get("order_number")
        results["setup"]["guest_order"] = {"status": st, "order_number": order_guest}

    # A client that has never authenticated: no bearer, no session token, no cookie jar.
    anon = Client(args.base_url)
    anon.token = ""

    def order_check(check: str, path: str, client_obj, expected: tuple,
                    fail_below: bool = False, **kw) -> None:
        """Record one order-read probe with an explicit expectation, not a vibe.

        ``fail_below`` flips the verdict for the guest-capability controls: there a
        non-2xx is the failure, because it means a working feature was removed.
        """
        st, resp = client_obj.call("GET", path, **kw)
        if fail_below:
            ok = st in expected
            verdict = ("OK — guest capability intact" if ok else
                       f"FAIL — guest order is no longer readable anonymously ({st})")
        else:
            ok = st in expected
            verdict = (f"OK — {st} as expected" if ok else
                       f"FAIL — expected {expected}, got {st}")
        entry = {"check": check, "label": "ORDER AUTHZ", "status": st, "verdict": verdict}
        if isinstance(resp, dict):
            entry["response_fields"] = sorted(resp.keys())[:12]
        results["checks"].append(entry)

    if order_owned:
        order_check("CONTROL: owner A GET /orders/{n} (owned)", f"/orders/{order_owned}", a, (200,))
        order_check("anonymous GET /orders/{n} (owned) — must be denied",
                    f"/orders/{order_owned}", anon, (401, 403))
        order_check("anonymous GET /orders/{n}/tracking (owned) — must be denied",
                    f"/orders/{order_owned}/tracking", anon, (401, 403))
        order_check("anonymous GET /commerce/orders/{n} (owned) — must be denied",
                    f"/commerce/orders/{order_owned}", anon, (401, 403))
        order_check("other user B GET /orders/{n} (owned) — must be denied",
                    f"/orders/{order_owned}", b, (403, 404))
    else:
        results["checks"].append({
            "check": "OWNED ORDER: anonymous read must be denied", "label": "ORDER AUTHZ",
            "status": "SKIPPED",
            "why": "no owned order was created (checkout unavailable or SKU missing)"})

    # The cross-actor OBJECT_CHECKS address an order by number; give them a real one.
    if order_owned:
        created_ids["order"] = order_owned

    if order_guest:
        order_check("CONTROL: anonymous GET /orders/{n} (GUEST order) — capability must survive",
                    f"/orders/{order_guest}", anon, (200,), fail_below=True)
        order_check("anonymous GET /orders/{n}/tracking (GUEST order) — capability must survive",
                    f"/orders/{order_guest}/tracking", anon, (200,), fail_below=True)
    else:
        results["checks"].append({
            "check": "GUEST ORDER: anonymous capability must survive", "label": "ORDER AUTHZ",
            "status": "SKIPPED", "why": "no guest order was created"})

    order_check("nonexistent number is 404 for everyone (control)",
                "/orders/CONF-00000000", anon, (404,))

    # ---- cross-user access attempts (B against A's objects) ----------------
    for label, method, tmpl, body in OBJECT_CHECKS:
        oid = created_ids.get({"wardrobe item": "wardrobe", "outfit": "outfit",
                               "cart item": "cart", "order": "order"}.get(label, ""), None)
        if not oid:
            results["checks"].append({"check": f"B {method} {tmpl}", "label": label,
                                      "status": "SKIPPED", "why": f"no '{label}' object was created"})
            continue
        path = tmpl.replace("{id}", str(oid))
        # A cross-actor cart attempt must speak the cart protocol as B: B's own session
        # token alongside B's bearer. Omitting the session header would produce a 422
        # about a missing header, which is not the claim under test.
        kw = {"guest": f"audit-cart-b-{stamp}"} if "cart" in tmpl else {}
        st, resp = b.call(method, path, body, **kw)
        leaked = 200 <= st < 300
        results["checks"].append({
            "check": f"B {method} {tmpl}", "label": label, "status": st,
            "verdict": "FAIL — cross-user access allowed" if leaked else "BLOCKED",
            "response_fields": sorted(resp.keys()) if isinstance(resp, dict) else str(resp)[:120],
        })

    # ---- cart merge across actors (measured by hand 2026-09-23) ------------
    # A authenticated + POST /cart/merge {"guest_token": <B's guest token>} returned 200
    # and moved the guest cart's item into A. Recorded with its precondition, because the
    # classification turns on it: this requires POSSESSION of the other session's token
    # (an app-wide X-Session-Token minted client-side), so it is an observation about a
    # capability transfer, not a demonstrated cross-user read. The harness states the
    # precondition in the entry rather than leaving it to a reader to infer.
    if sku_id:
        merge_guest = f"audit-merge-{stamp}"
        victim = Client(args.base_url)
        victim.token = ""
        victim.call("POST", "/cart/items", {"product_sku_id": sku_id, "quantity": 1},
                    token="", guest=merge_guest)
        carrier_session = f"audit-merge-carrier-{stamp}"
        st, body = b.call("POST", "/cart/merge", {"guest_token": merge_guest},
                          guest=carrier_session)
        results["checks"].append({
            "check": "B POST /cart/merge {guest_token: <A's guest token>}", "label": "CART MERGE",
            "status": st,
            "verdict": ("OBSERVATION — the guest cart was absorbed by the caller; "
                        "precondition: the caller already held that guest session token"
                        if 200 <= st < 300 else f"BLOCKED ({st})"),
            "precondition": "possession of the other session's X-Session-Token",
            "response_fields": sorted(body.keys())[:12] if isinstance(body, dict) else str(body)[:120],
        })

    # ---- BFLA: consumer token against brand/admin routes -------------------
    for label, method, path in BFLA_CHECKS:
        st, resp = b.call(method, path)
        declared = path in spec["paths"]
        if 200 <= st < 300:
            verdict = "FAIL — consumer reached privileged surface"
        elif st == 403:
            verdict = "BLOCKED — route exists, role denied (403)"
        elif st == 404:
            verdict = ("BLOCKED — not routable for this caller (404; route IS declared: "
                       "matches the app's not-found-for-unauthorised pattern)"
                       if declared else "BLOCKED — route absent (404, not in schema)")
        else:
            verdict = f"BLOCKED ({st})"
        results["checks"].append({
            "check": f"consumer→{label} ({method} {path})", "label": "BFLA", "status": st,
            "verdict": verdict, "declared_in_schema": declared,
            "response_fields": sorted(resp.keys()) if isinstance(resp, dict) else str(resp)[:120],
        })

    # ---- mass assignment ---------------------------------------------------
    for label, path, method in (("wardrobe", "/wardrobe/items", "POST"),
                                ("outfit", "/outfits", "POST")):
        op = spec["paths"].get(path, {}).get(method.lower())
        if op is None:
            continue
        base = build_payload((op.get("requestBody") or {}).get("content", {})
                             .get("application/json", {}).get("schema", {}), spec)
        st, resp = b.call(method, path, {**base, **PRIVILEGED_FIELDS})
        echoed = {}
        if isinstance(resp, dict):
            echoed = {k: resp.get(k) for k in PRIVILEGED_FIELDS if k in resp}
        # A server that echoes `user_id` is not necessarily accepting it. The FIRST
        # version of this check called that "REVIEW — privileged fields honoured",
        # which was wrong: the echoed value was the actor's OWN id, i.e. the field
        # had been ignored and replaced from the token. Only a value equal to the
        # INJECTED value counts as accepted.
        actor_id = str(results["setup"]["B"]["user_id"])
        accepted = [k for k, v in echoed.items()
                    if str(v) == str(PRIVILEGED_FIELDS.get(k)) and str(v) != actor_id]
        results["checks"].append({
            "check": f"mass assignment: {method} {path} with {len(PRIVILEGED_FIELDS)} privileged fields",
            "label": "MASS-ASSIGNMENT", "status": st,
            "verdict": ("FAIL — server accepted injected value(s): " + ", ".join(sorted(accepted)))
            if accepted else "BLOCKED — injected values ignored; server used the token's identity",
            "echoed": echoed, "actor_id": actor_id,
        })

    # ---- verdict + exit code ----------------------------------------------
    fails = [c for c in results["checks"] if str(c.get("verdict", "")).startswith("FAIL")]
    skipped = [c for c in results["checks"] if c.get("status") == "SKIPPED"]
    results["rate_limits_observed"] = {
        "A": a.rate_limited, "B": b.rate_limited,
        "note": "429s seen during setup; Retry-After presence recorded verbatim",
    }
    results["summary"] = {"checks": len(results["checks"]), "failures": len(fails),
                          "skipped": len(skipped),
                          "rate_limited_responses": len(a.rate_limited) + len(b.rate_limited)}
    json.dump(results, open(args.json, "w"), indent=1, default=str)

    print(f"{'check':58} {'status':>7}  verdict")
    for c in results["checks"]:
        print(f"{c['check'][:58]:58} {str(c['status']):>7}  {c.get('verdict','')[:60]}")
    print(f"\nsummary: {results['summary']}")
    if fails:
        print("\nFAILURES:")
        for c in fails:
            print("  ", c)
        return 2
    if skipped:
        print(f"\n{len(skipped)} check(s) SKIPPED — a skipped check is not a pass.")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Loud as exc:
        print(f"MEASUREMENT INVALID — {exc}", file=sys.stderr)
        sys.exit(3)
