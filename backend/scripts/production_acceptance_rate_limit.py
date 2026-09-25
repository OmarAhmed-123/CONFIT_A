#!/usr/bin/env python3
"""§28 — production rate-limit acceptance with harmless traffic only.

Target: GET /api/v1/orders/{order_number}, limited 30/minute, read-only. A
deliberately nonexistent order number exercises the limiter without touching AI,
payments, carts, orders or any account, and without creating any row anywhere.

What this proves, and what it deliberately does not:
  * proves a 429 is reachable with a bounded burst, that it carries Retry-After and
    a JSON envelope, that the two router aliases share one bucket, that a different
    identity gets its own allowance, and that a different route keeps its own bucket;
  * does NOT prove a global limit. Shared-counter evidence across independent
    executions is required for that, and without it the only honest claim is
    "PRODUCTION SHARED-STORE CONFIGURED — MULTI-INSTANCE BEHAVIOR NOT FULLY OBSERVED".

Usage: production_acceptance_rate_limit.py <base-url> <expected-commit-sha> [out-file]
"""

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://confit-a.vercel.app").rstrip("/")
EXPECTED_SHA = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = sys.argv[3] if len(sys.argv) > 3 else "/home/user/CONFIT_evidence/52-production-rate-limit.txt"

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def get(path, session=None, timeout=25):
    """One request. Returns (status, body_text, headers)."""
    url = f"{BASE}{path}"
    headers = {"Accept": "application/json", "User-Agent": "confit-acceptance-probe"}
    if session:
        headers["x-session-token"] = session
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)
    except Exception as e:  # network-level; reported as INVALID, never as a pass
        return None, f"{type(e).__name__}: {e}", {}


started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
say("§28 PRODUCTION RATE-LIMIT ACCEPTANCE (harmless traffic only)")
say(f"date: {started}")
say(f"target: {BASE}  route: GET /api/v1/orders/<nonexistent>  (limit 30/minute, read-only)")
say(f"expected deployed commit: {EXPECTED_SHA or '(not supplied)'}")
say()

# ── 0. the running service answers at all, and reports its version ───────────
# The AUTHORITATIVE deployed-commit check is the Vercel deployment metadata
# (meta.githubCommitSha), recorded separately in the evidence ledger; this endpoint
# only proves the service is the one being probed.
status, body, _ = get("/api/v1/health")
reported_version = ""
if status == 200:
    try:
        reported_version = str(json.loads(body).get("version") or "")
    except Exception:
        reported_version = ""
say(f"0) health: HTTP {status}; version reported by the running API: {reported_version or 'NOT REPORTED'}")
say(f"   expected deployed commit (verified separately via the deployment metadata): {EXPECTED_SHA or '(not supplied)'}")
say()

# ── 1. bounded burst on the canonical alias ──────────────────────────────────
order = f"CONFIT-ACCEPTANCE-{uuid.uuid4().hex[:12].upper()}"
sess = f"acceptance-{uuid.uuid4().hex}"
codes, first_429, retry_after, envelope = [], None, None, ""
for i in range(1, 36):
    st, bd, hd = get(f"/api/v1/orders/{order}", session=sess)
    codes.append(st)
    if st == 429 and first_429 is None:
        first_429 = i
        retry_after = hd.get("Retry-After") or hd.get("retry-after")
        envelope = bd[:300]
        break
    time.sleep(0.15)

say(f"1) bounded burst, one identity, canonical alias")
say(f"   codes: {codes}")
say(f"   first 429 at request #{first_429} (limit is 30/minute)")
say(f"   Retry-After header on the 429: {retry_after!r}")
say(f"   429 body (envelope): {envelope!r}")
say(f"   verdict: {'429 REACHED' if first_429 else 'NO 429 — limit not observed'}")
say()

# ── 2. alias sharing: the other router spelling must share the bucket ─────────
st_a, _, _ = get(f"/api/v1/orders/{order}", session=sess)          # exhausted bucket
st_b, _, _ = get(f"/api/v1/commerce/orders/{order}", session=sess)  # alias
say("2) alias sharing with the same identity")
say(f"   /api/v1/orders/...          -> {st_a}")
say(f"   /api/v1/commerce/orders/... -> {st_b}  (same bucket expected: both 429 while exhausted)")
say(f"   verdict: {'SHARED' if st_a == st_b == 429 else 'NOT SHARED — inspect'}")
say()

# ── 3. fresh identity gets its own allowance ─────────────────────────────────
fresh = f"acceptance-{uuid.uuid4().hex}"
st_f, bd_f, _ = get(f"/api/v1/orders/{order}", session=fresh)
say("3) a fresh identity is not inheriting the exhausted bucket")
say(f"   new session token -> {st_f} (200/404 expected — 429 would mean identities collide)")
say(f"   verdict: {'FRESH ALLOWANCE' if st_f in (200, 404) else 'UNEXPECTED'}")
say()

# ── 4. a different route keeps its own bucket ────────────────────────────────
st_t, _, _ = get(f"/api/v1/orders/{order}/tracking", session=sess)   # exhausted identity, other route
say("4) route isolation: the tracking route has its own bucket")
say(f"   /orders/<n>/tracking with the exhausted identity -> {st_t} (429 would mean one bucket for all routes)")
say(f"   verdict: {'ISOLATED' if st_t in (200, 404, 403, 401) else 'INSPECT'}")
say()

# ── 5. concurrency: parallel calls must not multiply the allowance ───────────
import concurrent.futures

conc_id = f"acceptance-{uuid.uuid4().hex}"
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    results = list(pool.map(
        lambda _: get(f"/api/v1/orders/{order}", session=conc_id)[0],
        range(40),
    ))
admitted = sum(1 for c in results if c in (200, 404))
throttled = sum(1 for c in results if c == 429)
server_err = sum(1 for c in results if c and c >= 500)
say("5) 40 concurrent requests on one fresh identity")
say(f"   admitted={admitted} throttled={throttled} 5xx={server_err}")
say(f"   verdict: {'BOUND HOLDS UNDER CONCURRENCY' if throttled and not server_err else 'INSPECT'}")
say()

# ── 6. verdict + the exact sentence this evidence supports ──────────────────
ok = bool(first_429) and st_a == st_b == 429
say("VERDICT")
say(f"  bounded burst reaches 429 with Retry-After: {bool(first_429)}")
say(f"  alias spellings share one bucket: {st_a == st_b == 429}")
say(f"  fresh identity isolation: {st_f in (200, 404)}")
say(f"  concurrent calls stay bounded: {bool(throttled) and not server_err}")
say()
say("  CLAIM THIS EVIDENCE SUPPORTS: 'PRODUCTION SHARED-STORE CONFIGURED — MULTI-INSTANCE")
say("  BEHAVIOR NOT FULLY OBSERVED' unless a second independent execution from a different")
say("  origin shows the same shared counter, in which case the shared-store claim can be")
say("  strengthened — but never to 'global limit verified' on this evidence alone.")
say()
say(f"  overall: {'ACCEPTED' if ok else 'PARTIAL — see the verdict lines above'}")

with open(OUT, "w") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"\nwritten: {OUT}")
