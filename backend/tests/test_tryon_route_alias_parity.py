"""F-005 regression: the /try-on and /tryon route families must stay in parity.

``tryon_controller.py`` exposes most endpoints under BOTH spellings as a
backward-compatible alias (e.g. ``@router.post("/try-on/jobs")`` plus
``@router.post("/tryon/jobs")``). The alias was applied per handler by hand, and
two endpoints were missed:

  - ``/try-on/garments/{product_id}/asset``  had no ``/tryon`` alias
  - ``/tryon/visual-search``                 had no ``/try-on`` alias

A client that picks the "wrong" spelling for those two gets a 404. This test pins
the alias contract so the two families cannot silently diverge again.

It reads the generated OpenAPI paths, which is the reliable source: this app
registers included routers as ``_IncludedRouter`` wrappers, so ``app.routes`` is
not a flat list of endpoint paths. No database or network is touched.
"""

from backend.app.main import app

PREFIX = "/api/v1"


def _suffixes(spelling: str) -> set[str]:
    base = f"{PREFIX}/{spelling}/"
    paths = app.openapi().get("paths", {})
    return {p[len(base):] for p in paths if p.startswith(base)}


def test_try_on_and_tryon_route_families_are_in_parity():
    try_on = _suffixes("try-on")
    tryon = _suffixes("tryon")
    # Guard against a vacuous pass if the discovery ever stops finding routes.
    assert try_on, "expected /api/v1/try-on/* endpoints to be registered"
    assert tryon, "expected /api/v1/tryon/* endpoints to be registered"
    only_try_on = sorted(try_on - tryon)
    only_tryon = sorted(tryon - try_on)
    assert try_on == tryon, (
        "/try-on and /tryon must expose the same endpoints. "
        f"only /try-on: {only_try_on}; only /tryon: {only_tryon}"
    )
