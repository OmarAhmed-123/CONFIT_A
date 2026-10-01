"""The embedding client must authenticate to the worker.

The worker runs a 203M-parameter model behind a PUBLIC Modal URL. Without a
credential on every /embed call that is a free, anonymous compute endpoint
attached to a metered account — the straightforward way for a stranger to
drain a subscription that is explicitly scarce.

Verified against the live worker 2026-10-01:
    POST /embed  with no header   -> 401 UNAUTHORIZED
    POST /embed  with the header  -> 200, 768-d, L2 norm 1.0, 0.77s (CPU)
"""
from __future__ import annotations

import pytest

from backend.app.providers.moda import embeddings as moda


def _set(monkeypatch, **kw):
    for k, v in kw.items():
        monkeypatch.setattr(f"backend.app.core.config.settings.{k}", v, raising=False)


def test_header_is_sent_when_a_token_is_configured(monkeypatch):
    _set(monkeypatch, MODA_EMBED_TOKEN="tok-123")
    assert moda._worker_headers() == {"X-Worker-Token": "tok-123"}


def test_falls_back_to_the_shared_worker_token(monkeypatch):
    """One rotated secret must cover both workers rather than drifting into
    two that silently diverge."""
    _set(monkeypatch, MODA_EMBED_TOKEN=None, VTON_WORKER_ADMIN_TOKEN="shared-tok")
    assert moda._worker_headers() == {"X-Worker-Token": "shared-tok"}


def test_no_header_when_nothing_is_configured(monkeypatch):
    """Absent is absent — never an empty string, which would look like an
    attempted credential and muddy the worker's logs."""
    _set(monkeypatch, MODA_EMBED_TOKEN=None, VTON_WORKER_ADMIN_TOKEN=None,
         CONFIT_WORKER_ADMIN_TOKEN=None)
    assert moda._worker_headers() == {}


@pytest.mark.asyncio
async def test_embed_image_actually_attaches_the_header(monkeypatch):
    """The unit that matters: a helper nobody calls protects nothing."""
    _set(monkeypatch, MODA_EMBED_BASE_URL="https://worker.test", MODA_EMBED_TOKEN="tok-xyz")
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"embedding": [0.0] * 768, "model": "m", "dim": 768}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, files=None, headers=None):
            seen["url"] = url
            seen["headers"] = headers or {}
            return _Resp()

    monkeypatch.setattr(moda.httpx, "AsyncClient", _Client)
    await moda.embed_image(b"x" * 500)
    assert seen["headers"].get("X-Worker-Token") == "tok-xyz"


@pytest.mark.asyncio
async def test_an_embedding_outage_returns_none_not_an_exception(monkeypatch):
    """Visual search has a working keyword path. An optional accelerator
    going down must degrade the ranking, never take the feature offline."""
    _set(monkeypatch, MODA_EMBED_BASE_URL="https://worker.test", MODA_EMBED_TOKEN="t")

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise OSError("worker down")

    monkeypatch.setattr(moda.httpx, "AsyncClient", _Client)
    assert await moda.embed_image(b"x" * 500) is None


@pytest.mark.asyncio
async def test_unconfigured_worker_is_a_no_op(monkeypatch):
    _set(monkeypatch, MODA_EMBED_BASE_URL="")
    assert await moda.embed_image(b"x" * 500) is None


def test_ranking_drops_weak_matches_instead_of_padding_to_a_full_page():
    """A visual search that always returns twelve results teaches shoppers the
    ranking is meaningless."""
    q = [1.0] + [0.0] * 767
    catalog = {1: [1.0] + [0.0] * 767, 2: [0.0, 1.0] + [0.0] * 766}
    out = moda.rank_catalog(q, catalog, limit=12)
    assert [r.product_id for r in out] == [1]


def test_identical_vectors_score_100_percent():
    q = [0.6, 0.8] + [0.0] * 766
    out = moda.rank_catalog(q, {7: list(q)}, limit=5)
    assert out[0].similarity_percent == 100.0
