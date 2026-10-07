"""Occasion filtering must be case-insensitive, and the occasion filter
vocabulary must come from the DATA, not from a hardcoded UI list.

WHY THIS EXISTS
---------------
Observed in production on 2026-10-07 while auditing /discover (C02 pass):
`GET /catalog/products?occasion=Work` returned an EMPTY list while
`?occasion=work` returned 8 products. Tags are stored lowercase
("work", "wedding"); the repository filtered with case-SENSITIVE
`LIKE`, while the UI sent capitalized tokens ("Work") — so every
occasion pill on the storefront rendered an empty catalogue.

Compounding it, the UI's pill list was hardcoded and included tokens
("evening", "everyday") that exist on NO product at all — pills that
could never return anything even with matching fixed.

These tests pin both fixes:
1. `ilike` matching in catalog listing AND search paths.
2. `GET /catalog/occasions`: the real tag vocabulary with counts, so
   the storefront can only ever offer filters the data can answer.
"""


class TestOccasionCaseInsensitivity:
    def test_capitalized_token_matches_lowercase_tags(self, client):
        lower = client.get("/api/v1/catalog/products?occasion=work").json()
        upper = client.get("/api/v1/catalog/products?occasion=Work").json()
        assert len(lower) > 0, "seed data must contain 'work' tagged products"
        assert {p["id"] for p in upper} == {p["id"] for p in lower}

    def test_uppercase_token_matches_too(self, client):
        lower = client.get("/api/v1/catalog/products?occasion=wedding").json()
        upper = client.get("/api/v1/catalog/products?occasion=WEDDING").json()
        assert len(lower) > 0
        assert {p["id"] for p in upper} == {p["id"] for p in lower}

    def test_search_path_is_case_insensitive_as_well(self, client):
        # /catalog/search runs through SearchService, a separate query
        # builder that carried the same case-sensitive LIKE.
        lower = client.get("/api/v1/catalog/search?q=wool&occasion=work").json()
        upper = client.get("/api/v1/catalog/search?q=wool&occasion=Work").json()
        ids = lambda payload: {p["id"] for p in payload.get("products", payload.get("items", []))}
        assert ids(upper) == ids(lower)

    def test_unknown_occasion_returns_empty_not_error(self, client):
        res = client.get("/api/v1/catalog/products?occasion=nonexistent_tag_xyz")
        assert res.status_code == 200
        assert res.json() == []


class TestOccasionVocabularyEndpoint:
    def test_returns_lowercase_values_with_positive_counts(self, client):
        res = client.get("/api/v1/catalog/occasions")
        assert res.status_code == 200
        vocab = res.json()
        assert len(vocab) > 0
        for entry in vocab:
            assert set(entry.keys()) == {"value", "count"}
            assert entry["value"] == entry["value"].lower()
            assert entry["value"].strip() == entry["value"]
            assert entry["count"] >= 1

    def test_sorted_most_stocked_first(self, client):
        vocab = client.get("/api/v1/catalog/occasions").json()
        counts = [e["count"] for e in vocab]
        assert counts == sorted(counts, reverse=True)

    def test_no_duplicate_values(self, client):
        vocab = client.get("/api/v1/catalog/occasions").json()
        values = [e["value"] for e in vocab]
        assert len(values) == len(set(values))

    def test_every_advertised_value_actually_filters_to_products(self, client):
        """The whole point of the endpoint: a pill built from this list
        must never promise a filter the catalogue cannot answer."""
        vocab = client.get("/api/v1/catalog/occasions").json()
        for entry in vocab:
            res = client.get(
                f"/api/v1/catalog/products?occasion={entry['value']}"
            )
            assert res.status_code == 200
            assert len(res.json()) >= 1, (
                f"occasion '{entry['value']}' is advertised by "
                "/catalog/occasions but filters to zero products"
            )

    def test_counts_match_actual_product_tags(self, client):
        vocab = {e["value"]: e["count"] for e in client.get("/api/v1/catalog/occasions").json()}
        products = client.get("/api/v1/catalog/products?limit=100").json()
        recount: dict = {}
        for p in products:
            for tag in p.get("occasion_tags") or []:
                recount[tag.lower()] = recount.get(tag.lower(), 0) + 1
        # Every recounted tag must be advertised with at least that count
        # (vocab counts can exceed the page if the catalogue outgrows limit).
        for tag, n in recount.items():
            assert tag in vocab, f"tag '{tag}' on a live product missing from vocabulary"
            assert vocab[tag] >= n
