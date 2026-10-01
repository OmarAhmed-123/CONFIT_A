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


# ── provenance: a silent degradation must become a visible one ──────────────

@pytest.mark.asyncio
async def test_skip_reason_records_not_configured(monkeypatch):
    """MEASURED ON PRODUCTION 2026-10-01: a self-match query (cosine 1.0,
    impossible to drop by threshold) came back scored 56 from the keyword
    band, and NOTHING in the response said the visual path had not run. An
    operator could not distinguish a working visual search from a broken one.
    """
    from backend.app.services.visual_search_service import VisualSearchService

    _set(monkeypatch, MODA_EMBED_BASE_URL="")
    svc = VisualSearchService(db=None)
    out = await svc._embedding_matches("data:image/jpeg;base64,xx", limit=5, in_stock_only=False)
    assert out == {}
    assert svc._embedding_skip_reason == "not_configured"


@pytest.mark.asyncio
async def test_skip_reason_records_an_unreadable_query_image(monkeypatch):
    from backend.app.services.visual_search_service import VisualSearchService

    _set(monkeypatch, MODA_EMBED_BASE_URL="https://w.test", MODA_EMBED_TOKEN="t")
    svc = VisualSearchService(db=None)
    out = await svc._embedding_matches("not-a-url-at-all", limit=5, in_stock_only=False)
    assert out == {} and svc._embedding_skip_reason == "query_image_unreadable"


@pytest.mark.asyncio
async def test_skip_reason_records_a_failed_embed_call(monkeypatch):
    """Covers timeout, 401, 5xx and malformed payload alike — embed_image
    swallows them all by design."""
    from backend.app.services.visual_search_service import VisualSearchService

    _set(monkeypatch, MODA_EMBED_BASE_URL="https://w.test", MODA_EMBED_TOKEN="t")
    svc = VisualSearchService(db=None)

    async def _none(*a, **k):
        return None

    monkeypatch.setattr(moda, "embed_image", _none)
    out = await svc._embedding_matches(
        "data:image/jpeg;base64," + ("QQ" * 80), limit=5, in_stock_only=False)
    assert out == {} and svc._embedding_skip_reason == "embed_call_failed"


def test_measured_threshold_separates_signal_from_noise():
    """Calibration recorded against the LIVE worker, 2026-10-01, 48 pairs:

        noise (cross-category)      0.29 - 0.41
        genuine same-category match 0.55 - 0.66
        identical image             1.00

    MIN_COSINE_SCORE must sit between the noise ceiling and the match floor,
    or visual search either returns nothing or returns everything.
    """
    assert 0.41 < moda.MIN_COSINE_SCORE <= 0.55, (
        "threshold must exclude the measured noise band (<=0.41) and admit "
        "genuine matches (>=0.55)"
    )
