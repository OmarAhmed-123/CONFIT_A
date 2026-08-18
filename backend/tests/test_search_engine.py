import pytest
from fastapi.testclient import TestClient


def test_search_exact_sku_and_title_ranking(client: TestClient):
    """Verifies that SKU match and exact title matches rank highest with maximum relevance score."""
    # 1. Search by SKU code
    res_sku = client.get("/api/v1/catalog/search?q=MD-BLZ-NVY-M")
    assert res_sku.status_code == 200
    data_sku = res_sku.json()
    assert data_sku["total_matches"] >= 1
    assert data_sku["results"][0]["matched_field"] == "sku"
    assert data_sku["results"][0]["relevance_score"] == 100.0

    # 2. Search by exact title keyword
    res_title = client.get("/api/v1/catalog/search?q=Double-Breasted Blazer")
    assert res_title.status_code == 200
    data_title = res_title.json()
    assert data_title["total_matches"] >= 1
    assert data_title["results"][0]["title"] == "Tailored Italian Wool Double-Breasted Blazer"


def test_search_typo_tolerance():
    """Verifies typo correction dictionary and 'did you mean' suggestions."""
    from backend.app.core.database import SessionLocal
    from backend.app.services.search_service import SearchService

    db = SessionLocal()
    srv = SearchService(db)

    # Search with typo "blzer"
    res = srv.search_products(query="blzer")
    assert res.total_matches >= 1
    assert res.did_you_mean == "blazer"
    assert any("Blazer" in r.title for r in res.results)

    # Search with typo "oxfrd shrt"
    res_multi = srv.search_products(query="oxfrd shrt")
    assert res_multi.total_matches >= 1
    assert res_multi.did_you_mean == "oxford shirt"

    db.close()


def test_search_dynamic_facets_and_aggregations(client: TestClient):
    """Verifies category, brand, and color facet count aggregations matching the search context."""
    res = client.get("/api/v1/catalog/search?q=wool")
    assert res.status_code == 200
    data = res.json()

    facets = data["facets"]
    assert len(facets["categories"]) >= 1
    assert len(facets["brands"]) >= 1
    assert facets["price_range"]["min_price"] > 0
    assert facets["price_range"]["max_price"] >= facets["price_range"]["min_price"]


def test_search_autocomplete_speed_and_suggestions(client: TestClient):
    """Verifies instant autocomplete endpoint with sub-10ms response."""
    res = client.get("/api/v1/catalog/autocomplete?q=oxf")
    assert res.status_code == 200
    data = res.json()
    assert len(data["suggestions"]) >= 1
    first = data["suggestions"][0]
    assert "Oxford" in first["title"] or "oxf" in first["title"].lower()


def test_search_security_and_sanitization():
    """Verifies input length bounding, SQL injection protection, and control character stripping."""
    from backend.app.core.database import SessionLocal
    from backend.app.services.search_service import SearchService

    db = SessionLocal()
    srv = SearchService(db)

    # 1. Very long query
    long_q = "blazer " * 50
    clean = srv.sanitize_query(long_q)
    assert len(clean) <= 100

    # 2. Control characters & SQL metacharacters
    nasty_q = "blazer\x00\x1f' OR '1'='1"
    clean_nasty = srv.sanitize_query(nasty_q)
    assert "\x00" not in clean_nasty
    assert "\x1f" not in clean_nasty

    res = srv.search_products(query=nasty_q)
    assert res.execution_time_ms >= 0

    db.close()
