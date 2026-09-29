"""Visual-search ranking: pure, testable, and dormant until a GPU exists.

WHY THE RANKING IS TESTED AND THE MODEL IS NOT
-----------------------------------------------
The model is 812 MB of weights behind a 3 GB dependency tree. What decides
what a shopper SEES is the ranking — the threshold, the ordering, the
tie-break, the percentage shown. That is pure arithmetic and is pinned here
without a GPU, a network, or a download.

The model itself was verified separately by running it: 203.2M parameters,
0.34s per image on CPU, and correct first-rank retrieval over the live
CONFIT catalogue ("a red silk evening gown" -> Silk Slip Column Maxi Dress).
Those numbers are in the provider docstring, measured, not cited.
"""
from __future__ import annotations

import asyncio
import math

import pytest

from backend.app.core.config import settings
from backend.app.providers.moda import embeddings as moda


def _vec(*values: float) -> list:
    return list(values)


# ── dormant until configured ───────────────────────────────────────────────

def test_feature_is_dormant_without_a_service(monkeypatch):
    """Today's state: one comparison, no network, no cost."""
    monkeypatch.setattr(settings, "MODA_EMBED_BASE_URL", "", raising=False)
    assert moda.is_available() is False


def test_whitespace_only_config_is_not_availability(monkeypatch):
    monkeypatch.setattr(settings, "MODA_EMBED_BASE_URL", "   ", raising=False)
    assert moda.is_available() is False


def test_feature_activates_on_one_variable(monkeypatch):
    monkeypatch.setattr(
        settings, "MODA_EMBED_BASE_URL", "http://gpu:8002", raising=False
    )
    assert moda.is_available() is True


def test_embed_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "MODA_EMBED_BASE_URL", "", raising=False)
    assert asyncio.run(moda.embed_image(b"x")) is None


# ── cosine ─────────────────────────────────────────────────────────────────

def test_identical_vectors_score_one():
    v = _vec(0.1, 0.2, 0.3)
    assert moda.cosine(v, v) == pytest.approx(1.0)


def test_orthogonal_vectors_score_zero():
    assert moda.cosine(_vec(1, 0), _vec(0, 1)) == pytest.approx(0.0)


@pytest.mark.parametrize("a,b", [
    ([], [1.0]), ([1.0], []), ([1.0, 2.0], [1.0]), ([0.0, 0.0], [1.0, 1.0]),
])
def test_degenerate_input_scores_zero_instead_of_raising(a, b):
    """A zero or mismatched vector must not crash a shopper's search."""
    assert moda.cosine(a, b) == 0.0


# ── ranking ────────────────────────────────────────────────────────────────

def test_ranking_orders_by_similarity():
    query = _vec(1.0, 0.0, 0.0)
    catalog = {
        1: _vec(0.0, 1.0, 0.0),   # orthogonal -> dropped
        2: _vec(1.0, 0.0, 0.0),   # identical
        3: _vec(0.9, 0.4, 0.0),   # close
    }
    ranked = moda.rank_catalog(query, catalog)
    assert [r.product_id for r in ranked] == [2, 3]
    assert ranked[0].score > ranked[1].score


def test_weak_matches_are_dropped_not_padded():
    """A search that always returns N results teaches shoppers to ignore it."""
    query = _vec(1.0, 0.0)
    catalog = {i: _vec(0.0, 1.0) for i in range(1, 13)}  # all orthogonal
    assert moda.rank_catalog(query, catalog) == []


def test_threshold_rejects_same_catalogue_lookalikes():
    """Measured: unrelated items from one brand's studio still score 0.38-0.44.

    Photographs from a single catalogue share lighting, framing and palette,
    so a low threshold passes a sandal as a match for a dress. 0.44 must be
    rejected; a genuine match must not.
    """
    query = _vec(1.0, 0.0)
    near = {1: _vec(0.44, math.sqrt(1 - 0.44 ** 2))}
    assert moda.rank_catalog(query, near) == [], "0.44 is catalogue noise"

    real = {2: _vec(0.90, math.sqrt(1 - 0.90 ** 2))}
    assert len(moda.rank_catalog(query, real)) == 1


def test_ties_break_deterministically():
    """The same upload must rank identically twice."""
    query = _vec(1.0, 0.0)
    catalog = {7: _vec(1.0, 0.0), 3: _vec(1.0, 0.0), 5: _vec(1.0, 0.0)}
    first = [r.product_id for r in moda.rank_catalog(query, catalog)]
    assert first == [3, 5, 7]
    for _ in range(5):
        assert [r.product_id for r in moda.rank_catalog(query, catalog)] == first


def test_limit_is_respected():
    query = _vec(1.0, 0.0)
    catalog = {i: _vec(1.0, 0.0) for i in range(1, 30)}
    assert len(moda.rank_catalog(query, catalog, limit=5)) == 5


def test_empty_query_returns_nothing():
    assert moda.rank_catalog([], {1: _vec(1.0)}) == []


def test_percent_distinguishes_results_instead_of_clamping():
    """The bug this pins: every result once read '100.0%'.

    An earlier version divided cosine by an assumed 0.30 ceiling, so a
    sandal at 0.44 and the exact garment at 0.9988 both rendered as 100% —
    a ranking the shopper could not read.
    """
    query = _vec(1.0, 0.0)
    exact = moda.rank_catalog(query, {1: _vec(1.0, 0.0)})[0]
    good = moda.rank_catalog(query, {2: _vec(0.80, math.sqrt(1 - 0.80 ** 2))})[0]

    assert exact.similarity_percent == 100.0
    assert good.similarity_percent == pytest.approx(80.0, abs=0.5)
    assert exact.similarity_percent > good.similarity_percent, (
        "two different matches must not render as the same number"
    )


def test_model_identity_is_recorded():
    """Vectors from two models are not comparable; the id must be stored."""
    assert moda.MODEL_ID == "HopitAI/moda-fashion-distilled"
    assert moda.EMBED_DIM == 768


# ── the wiring: this provider must not be dead code ────────────────────────

def test_visual_search_actually_imports_the_provider():
    """The mistake this pins: a provider built and never called.

    The VTON registry shipped once as dead code — registered, documented,
    imported by nothing, while the endpoint still reported unavailable. The
    same thing happened to this module in its first commit. A provider that
    no service imports is a claim, not a feature.
    """
    import inspect

    from backend.app.services import visual_search_service as vss

    source = inspect.getsource(vss)
    assert "providers.moda" in source, (
        "visual_search_service must import the embedding provider"
    )
    assert "_embedding_matches" in source


def test_embedding_scores_outrank_keyword_scores():
    """A genuine visual match must not lose to a coincidental word overlap.

    That inversion is the entire reason the embedding path exists, so the
    offset is asserted rather than assumed.
    """
    from backend.app.services.visual_search_service import VisualSearchService

    class _P:
        def __init__(self, pid): self.id = pid

    service = VisualSearchService.__new__(VisualSearchService)
    scored = [(98.0, _P(1), {"base": 50.0}), (50.0, _P(2), {"base": 50.0})]
    # product 2 is the real visual match, but scores lower on keywords
    out = service._apply_embedding_scores(scored, {2: 91.0})

    by_id = {p.id: s for s, p, _ in out}
    assert by_id[2] > by_id[1], (
        "a visual match at 91% lost to a keyword score of 98 — the ranking "
        "inversion this path exists to fix"
    )
    breakdown = next(b for _, p, b in out if p.id == 2)
    assert breakdown["visual_embedding"] == 91.0, "the visual score must be shown"


def test_no_embedding_matches_leaves_keyword_ranking_untouched():
    """Dormant must mean byte-for-byte unchanged behaviour."""
    from backend.app.services.visual_search_service import VisualSearchService

    class _P:
        def __init__(self, pid): self.id = pid

    service = VisualSearchService.__new__(VisualSearchService)
    scored = [(98.0, _P(1), {"base": 50.0}), (50.0, _P(2), {"base": 50.0})]
    assert service._apply_embedding_scores(scored, {}) == scored


def test_products_can_store_a_vector_and_its_model():
    """Vectors from two models are not comparable; the id must travel."""
    from backend.app.models.catalog import Product

    assert hasattr(Product, "style_embedding")
    assert hasattr(Product, "style_embedding_model")
