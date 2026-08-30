"""GROUP 2.4 Home Dashboard regression tests: personalization, recently-viewed
isolation (no cross-user leakage), and new-from-your-brands grounding."""
from fastapi.testclient import TestClient


def _register(client, email):
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": "T U"})
    assert r.status_code in (200, 201)
    return r.json()["access_token"]


def test_dashboard_guest_is_not_personalized_and_has_no_history(client: TestClient):
    r = client.get("/api/v1/catalog/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["personalized"] is False
    assert d["recently_viewed"] == []
    assert len(d["todays_picks"]) > 0          # catalog-grounded picks exist
    assert d["occasion_shortcuts"] == ["Work", "Wedding", "Party", "Casual"]
    assert d["quick_actions"] == ["build_outfit", "try_it_on", "find_my_style"]


def test_dashboard_recently_viewed_is_per_user(client: TestClient):
    # User A views products.
    tok_a = _register(client, "dash_a@confit.io")
    ha = {"Authorization": f"Bearer {tok_a}"}
    for pid in (1, 5, 3):
        client.get(f"/api/v1/catalog/products/{pid}", headers=ha)

    da = client.get("/api/v1/catalog/dashboard", headers=ha).json()
    rv_ids = [p["id"] for p in da["recently_viewed"]]
    assert rv_ids == [3, 5, 1]  # newest-first ordering
    assert da["personalized"] is True

    # User B must NOT see A's history (no cross-user leakage).
    client.cookies.clear()
    tok_b = _register(client, "dash_b@confit.io")
    db = client.get("/api/v1/catalog/dashboard", headers={"Authorization": f"Bearer {tok_b}"}).json()
    assert db["recently_viewed"] == []


def test_dashboard_new_from_your_brands_uses_real_brands(client: TestClient):
    tok = _register(client, "dash_c@confit.io")
    h = {"Authorization": f"Bearer {tok}"}
    d = client.get("/api/v1/catalog/dashboard", headers=h).json()
    # Bootstrapped profile has preferred brands; new-from-brands must be grounded
    # in those brand names only.
    assert d["personalized"] is True
    assert len(d["preferred_brands"]) > 0
    for p in d["new_from_your_brands"]:
        assert p["brand_name"] in d["preferred_brands"]
