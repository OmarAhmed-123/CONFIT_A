#!/usr/bin/env python3
"""Census of the requests a SIGNED-OUT visitor causes, per consumer route.

Result (measured 2026-09-23, production, 13 consumer routes, no credentials)
---------------------------------------------------------------------------
    /wardrobe   1× 401 /api/v1/wardrobe/items   +  1× 401 /api/v1/auth/refresh
    /my-looks   1× 401 /api/v1/outfits          +  1× 401 /api/v1/auth/refresh
    everything else: no failed requests
    TOTAL: 4 failed requests across 13 routes

That is benign and it agrees, independently, with the browser sweep's
no-instrumentation console control (4 × 401). A signed-out shopper opening a
protected page makes ONE protected call, ONE refresh attempt, then the UI shows
the signed-out state. No retry storm, no loop.

Why the number above is written down here
-----------------------------------------
My first version of this census reported 7-9 failed requests per protected route
and I read it as a refresh storm pinning the auth rate limiter. The instrument
was wrong, not the app:

    page.on("response", handler)      # registered ONCE PER ROUTE, never removed

Playwright keeps every registered listener for the page's lifetime, and each of
them appends to the same list. By the time the sweep reached the 7th and 9th
routes, each response was being recorded 7 and 9 times — the "storm" was my own
listener count, replayed as if it were request volume.

The fix is in the loop below: one listener per route, removed before the next
route is visited, so a count can only ever mean what it says. A count without a
location is not evidence, and a count from an instrument with an unbounded
listener set is not a count.

What it measures
----------------
For each route, with NO instrumentation and NO credentials: every response with
status >= 400, grouped by URL. Read-only; nothing is created or mutated.

Usage
-----
    python frontend/scripts/unauth_request_census.py --base-url https://confit-a.vercel.app
"""

from __future__ import annotations

import argparse
import json
from typing import Dict, List, Tuple

from playwright.sync_api import sync_playwright

ROUTES = [
    ("home", "/"),
    ("discover", "/discover"),
    ("product", "/product/silk-slip-column-maxi-dress"),
    ("cart", "/cart"),
    ("checkout", "/checkout"),
    ("stylist", "/stylist"),
    ("wardrobe", "/wardrobe"),
    ("fit_finder", "/fit"),
    ("my_looks", "/my-looks"),
    ("builder", "/builder"),
    ("orders", "/orders"),
    ("profile", "/profile"),
    ("returns", "/returns"),
]

#: A route that rendered nothing is not evidence of a clean route. MEASURED: a
#: real consumer surface renders hundreds of characters of visible text (the
#: smallest observed was the signed-out wardrobe notice); a blank shell, an SPA
#: crash or an offline navigation renders almost none. Without this gate the
#: census would print "(no failed requests)" for a page that never loaded —
#: a clean-looking result produced by measuring nothing.
MIN_RENDERED_TEXT = 120

#: A signed-out visitor is allowed a small, bounded number of failures per route:
#: one protected call that 401s plus the single refresh attempt that answers 401
#: as well. Anything above this is a pattern worth investigating, and the census
#: says so out loud instead of leaving the reader to eyeball the numbers.
BENIGN_FAILURES_PER_ROUTE = 2


def rendered_state(page) -> Dict[str, object]:
    """What the page actually shows — the precondition for counting anything."""
    return page.evaluate(
        """() => {
            const root = document.getElementById('root') || document.body;
            const text = (document.body.innerText || '').trim();
            return {
                readyState: document.readyState,
                title: document.title || '',
                textLength: text.length,
                rootChildren: root.children.length,
            };
        }"""
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:43123")
    ap.add_argument("--json", default="/tmp/unauth-request-census.json")
    ap.add_argument("--language", default="en")
    ap.add_argument("--only", default=None, help="comma-separated route names")
    args = ap.parse_args()

    wanted = {n.strip() for n in args.only.split(",")} if args.only else None
    if wanted:
        unknown = wanted - {name for name, _ in ROUTES}
        if unknown:
            raise SystemExit(f"--only names not in the route table: {sorted(unknown)}")

    out: List[Dict[str, object]] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.context.add_init_script(
            f"localStorage.setItem('confit_lang','{args.language}')"
        )
        for name, route in ROUTES:
            if wanted and name not in wanted:
                continue
            hits: List[Tuple[int, str]] = []

            def handler(response, _hits=hits):
                # No instrumentation inside the page: this listens to the network
                # the app actually produces, so it measures the app and not a probe.
                if response.status >= 400:
                    _hits.append((response.status, response.url))

            page.on("response", handler)
            page.goto(args.base_url + route, wait_until="networkidle")
            page.wait_for_timeout(1200)
            state = rendered_state(page)
            # ONE listener, removed before the next route: Playwright keeps every
            # listener registered on a page for its lifetime, so registering per
            # route without removing multiplies every later measurement by the
            # number of routes visited so far (see the docstring).
            page.remove_listener("response", handler)

            grouped: Dict[str, int] = {}
            for status, url in hits:
                key = f"{status} {url.split('?')[0]}"
                grouped[key] = grouped.get(key, 0) + 1
            entry = {"surface": name, "route": route, "language": args.language,
                     "failures": grouped, "total": len(hits), "rendered": state}
            if (state["textLength"] or 0) < MIN_RENDERED_TEXT or (state["rootChildren"] or 0) < 1:
                entry["error"] = (
                    f"route did not render: {state['textLength']} chars of visible text, "
                    f"{state['rootChildren']} root children, title={state['title']!r}, "
                    f"readyState={state['readyState']}"
                )
            out.append(entry)
            if entry.get("error"):
                print(f"{name:11} {route:44} RUN INVALID — {entry['error']}")
            elif grouped:
                print(f"{name:11} {route:44} {json.dumps(grouped)} "
                      f"(rendered {state['textLength']} chars)")
            else:
                print(f"{name:11} {route:44} (no failed requests; rendered "
                      f"{state['textLength']} chars)")
        browser.close()

    with open(args.json, "w") as fh:
        json.dump(out, fh, indent=2)

    total = sum(e["total"] for e in out)
    refresh_401 = sum(v for e in out for k, v in e["failures"].items() if "/auth/refresh" in k)
    worst = max(out, key=lambda e: e["total"], default={"total": 0, "surface": "-"})
    print(f"\ntotal failed requests, signed-out visitor, {len(out)} route(s): {total}; "
          f"worst route: {worst['surface']} ({worst['total']}); /auth/refresh 401s: {refresh_401}")

    invalid = [e for e in out if e.get("error")]
    if invalid:
        print(f"\nRUN INVALID — {len(invalid)} route(s) never rendered, so their zero "
              f"cannot be read as a pass:")
        for e in invalid:
            print(f"    ! {e['surface']} {e['route']}: {e['error']}")
        return 3

    over = [e["surface"] for e in out if e["total"] > BENIGN_FAILURES_PER_ROUTE]
    if over:
        print(f"PATTERN WORTH INVESTIGATING — above the benign bound of "
              f"{BENIGN_FAILURES_PER_ROUTE} per route: {over}")
        return 2
    print(f"within the benign bound ({BENIGN_FAILURES_PER_ROUTE} per route) — recorded, not alarmed on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
