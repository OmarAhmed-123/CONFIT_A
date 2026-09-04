"""API contract alignment guard (release brief §22, regression test T7).

Production truth that motivated this file: POST /api/v1/tryon/visual-search
returned HTTP 500 on https://confit-a.vercel.app because the controller read
``payload.limit`` while the request schema defines ``top_k``. The endpoint had
no test, so a pure attribute typo shipped to production.

Two guards:

1. STATIC: for every registered route whose handler receives a Pydantic
   request model, every ``<param>.<attr>`` access in the handler body must be
   a declared field (or a real attribute/method) of that model. This catches
   the whole class of controller/schema drift for every endpoint at once, not
   just the one that already failed.

2. RUNTIME: the visual-search endpoint itself is exercised end-to-end through
   the real app with a real (tiny) image and NO vision key configured, so the
   honest-degradation path must return 200 with the documented response shape.
"""

from __future__ import annotations

import ast
import base64
import inspect
import io
import textwrap

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from backend.app.main import app


def _pydantic_params(endpoint):
    """Return {param_name: model_cls} for BaseModel-typed handler params."""
    out = {}
    try:
        sig = inspect.signature(endpoint)
    except (TypeError, ValueError):
        return out
    for name, p in sig.parameters.items():
        ann = p.annotation
        if inspect.isclass(ann) and issubclass(ann, BaseModel):
            out[name] = ann
    return out


def _attribute_accesses(func, param_names):
    """Collect ``param.attr`` names read inside the handler body."""
    try:
        src = textwrap.dedent(inspect.getsource(func))
        tree = ast.parse(src)
    except (OSError, TypeError, SyntaxError):
        return {}
    found: dict[str, set[str]] = {n: set() for n in param_names}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in found:
                found[node.value.id].add(node.attr)
    return found


def iter_api_routes(router):
    """Walk the real route tree. ``app.include_router`` wraps sub-routers in
    ``_IncludedRouter`` objects, so ``app.routes`` alone only exposes the two
    routes declared directly on the app."""
    for r in router.routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from iter_api_routes(r.original_router)


def _handlers():
    seen = set()
    for route in iter_api_routes(app.router):
        fn = route.endpoint
        if fn in seen:
            continue
        seen.add(fn)
        params = _pydantic_params(fn)
        if params:
            yield route.path, fn, params


_CASES = list(_handlers())


class TestControllerSchemaAlignment:
    def test_app_registers_pydantic_backed_handlers(self):
        # Sanity: if this ever drops to zero the static guard below is vacuous.
        assert len(_CASES) >= 20, len(_CASES)

    @pytest.mark.parametrize(
        "path,fn,params", _CASES, ids=[f"{c[0]}::{c[1].__name__}" for c in _CASES]
    )
    def test_every_payload_attribute_exists_on_its_schema(self, path, fn, params):
        accesses = _attribute_accesses(fn, params.keys())
        problems = []
        for pname, attrs in accesses.items():
            model = params[pname]
            declared = set(model.model_fields)
            for attr in sorted(attrs):
                if attr in declared:
                    continue
                # real methods/properties on the model (model_dump, dict, ...)
                if hasattr(model, attr):
                    continue
                problems.append(f"{path} {fn.__name__}: {pname}.{attr} is not a field of {model.__name__}")
        assert problems == [], "\n".join(problems)

    def test_visual_search_handler_reads_top_k_not_limit(self):
        """Pin the specific production defect so it cannot regress silently."""
        from backend.app.controllers import tryon_controller
        from backend.app.schemas.tryon import VisualSearchRequest

        src = inspect.getsource(tryon_controller.visual_style_match)
        # AST-level check: no ``payload.limit`` attribute READ in executable code
        # (the explanatory comment in the handler mentions the old name).
        tree = ast.parse(textwrap.dedent(src))
        reads = {
            n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "payload"
        }
        assert "limit" not in reads, reads
        assert "top_k" in reads, reads
        assert "top_k" in VisualSearchRequest.model_fields
        assert "limit" not in VisualSearchRequest.model_fields


def _tiny_png_data_url() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 96), (30, 40, 120)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class TestVisualSearchEndpointRuntime:
    """Exercise the real endpoint (was 500 in production)."""

    def test_visual_search_returns_200_and_documented_shape(self, client, monkeypatch):
        from backend.app.core.config import settings

        # No vision key: the provider must degrade honestly, never 500.
        monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
        r = client.post(
            "/api/v1/tryon/visual-search",
            json={"image_base64": _tiny_png_data_url(), "top_k": 3, "in_stock_only": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("query_id", "analysis_available", "results_count", "matches"):
            assert key in body, body
        assert body["analysis_available"] is False
        assert isinstance(body["matches"], list)
        assert body["results_count"] == len(body["matches"])
        assert len(body["matches"]) <= 3
        for m in body["matches"]:
            for key in ("product_id", "title", "brand_name", "price", "similarity_score", "match_type"):
                assert key in m, m

    def test_visual_search_default_top_k_honoured(self, client, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
        r = client.post(
            "/api/v1/tryon/visual-search",
            json={"image_base64": _tiny_png_data_url(), "in_stock_only": False},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["matches"]) <= 8  # schema default top_k=8

    def test_visual_search_rejects_out_of_range_top_k(self, client):
        r = client.post(
            "/api/v1/tryon/visual-search",
            json={"image_base64": _tiny_png_data_url(), "top_k": 21},
        )
        assert r.status_code == 422

    def test_visual_search_requires_an_image(self, client):
        r = client.post("/api/v1/tryon/visual-search", json={"top_k": 3})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"
