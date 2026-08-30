"""GROUP 2 remaining-gate coverage: C8 public share, S1 Alembic, S5 weather,
and C7 (no fabricated PNG URL anywhere in the runtime path)."""
import os
import re
import subprocess
from unittest.mock import patch

import httpx
import pytest

from backend.app.services.weather_service import (
    NullWeatherProvider,
    OpenWeatherProvider,
    get_weather_provider,
)


# --------------------------------------------------------------------------
# Helpers (mirrors existing suite conventions)
# --------------------------------------------------------------------------

def _register(client, email, password="Sup3rSecret!"):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Gate Tester"},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_outfit(client, token, title="Gate Look"):
    # Resolve two real SKUs from the seeded catalog — never fabricated ids.
    products = client.get("/api/v1/catalog/products", headers=_auth(token)).json()
    assert products, "seeded catalog must not be empty"
    detail = client.get(f"/api/v1/catalog/products/{products[0]['id']}", headers=_auth(token)).json()
    sku_id = detail["skus"][0]["id"]
    resp = client.post(
        "/api/v1/outfits",
        headers=_auth(token),
        json={"title": title, "occasion": "Casual", "product_sku_ids": [sku_id]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------
# C8 — Public Share View
# --------------------------------------------------------------------------

class TestPublicShare:
    def test_share_returns_strong_token_and_no_fake_png_url(self, client):
        token = _register(client, "c8a@example.com")
        outfit = _create_outfit(client, token)
        resp = client.post(f"/api/v1/outfits/{outfit['id']}/share", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        share_token = body["share_token"]
        # Entropy: secrets.token_urlsafe(24) -> 32 chars + 'look_' prefix.
        assert share_token.startswith("look_")
        assert len(share_token) >= 37
        # C7: no fabricated server-side PNG URL may remain.
        assert "card_image_url" not in body
        assert "api.confit.io" not in str(body)

    def test_public_look_valid_token_no_auth(self, client):
        token = _register(client, "c8b@example.com")
        outfit = _create_outfit(client, token, title="C8 Public Look")
        share = client.post(f"/api/v1/outfits/{outfit['id']}/share", headers=_auth(token)).json()
        # Unauthenticated request must succeed.
        resp = client.get(f"/api/v1/public/looks/{share['share_token']}")
        assert resp.status_code == 200, resp.text
        look = resp.json()
        assert look["title"] == "C8 Public Look"
        assert isinstance(look["items"], list) and look["items"]
        assert look["total_price"] > 0

    def test_public_look_invalid_and_nonexistent_tokens_404(self, client):
        assert client.get("/api/v1/public/looks/look_doesnotexist0000000000000000").status_code == 404
        assert client.get("/api/v1/public/looks/not-a-real-token").status_code == 404

    def test_public_look_redacts_private_fields(self, client):
        token = _register(client, "c8c@example.com")
        outfit = _create_outfit(client, token)
        share = client.post(f"/api/v1/outfits/{outfit['id']}/share", headers=_auth(token)).json()
        look = client.get(f"/api/v1/public/looks/{share['share_token']}").json()
        forbidden = {"user_id", "id", "email", "share_token", "is_saved", "owner", "user"}
        assert forbidden.isdisjoint(look.keys()), f"leaked private fields: {forbidden & look.keys()}"
        assert "c8c@example.com" not in str(look)

    def test_share_token_is_unique_per_outfit(self, client):
        token = _register(client, "c8d@example.com")
        a = _create_outfit(client, token, title="Look A")
        b = _create_outfit(client, token, title="Look B")
        ta = client.post(f"/api/v1/outfits/{a['id']}/share", headers=_auth(token)).json()["share_token"]
        tb = client.post(f"/api/v1/outfits/{b['id']}/share", headers=_auth(token)).json()["share_token"]
        assert ta != tb
        # Re-sharing the same outfit is idempotent (same token returned).
        ta2 = client.post(f"/api/v1/outfits/{a['id']}/share", headers=_auth(token)).json()["share_token"]
        assert ta == ta2

    def test_share_requires_ownership(self, client):
        token_a = _register(client, "c8e@example.com")
        token_b = _register(client, "c8f@example.com")
        outfit = _create_outfit(client, token_a)
        # User B cannot mint a share token for User A's outfit (IDOR).
        resp = client.post(f"/api/v1/outfits/{outfit['id']}/share", headers=_auth(token_b))
        assert resp.status_code == 404
        # Guests cannot share at all.
        assert client.post(f"/api/v1/outfits/{outfit['id']}/share").status_code in (401, 403)


# --------------------------------------------------------------------------
# S5 — Weather provider
# --------------------------------------------------------------------------

OPENWEATHER_PAYLOAD = {
    "weather": [{"main": "Clear", "description": "clear sky"}],
    "main": {"temp": 24.5},
}


class TestWeatherProvider:
    def test_disabled_by_default_returns_null_provider(self):
        with patch("backend.app.services.weather_service.settings") as s:
            s.OPENWEATHER_ENABLED = False
            s.OPENWEATHER_API_KEY = None
            provider = get_weather_provider()
            assert isinstance(provider, NullWeatherProvider)
            assert provider.get_current_weather(30.0, 31.0) is None

    def test_missing_key_falls_back_to_null(self):
        with patch("backend.app.services.weather_service.settings") as s:
            s.OPENWEATHER_ENABLED = True
            s.OPENWEATHER_API_KEY = None
            assert isinstance(get_weather_provider(), NullWeatherProvider)

    def test_success_parses_real_response_shape(self):
        provider = OpenWeatherProvider(api_key="test-key")
        with patch("backend.app.services.weather_service.httpx.get") as mock_get:
            mock_get.return_value.json.return_value = OPENWEATHER_PAYLOAD
            mock_get.return_value.raise_for_status.return_value = None
            out = provider.get_current_weather(30.0444, 31.2357)
        assert out is not None
        assert out.temperature_c == 24.5
        assert out.condition == "Clear"
        assert out.provider == "openweather"

    def test_timeout_degrades_to_none(self):
        provider = OpenWeatherProvider(api_key="test-key")
        with patch("backend.app.services.weather_service.httpx.get", side_effect=httpx.TimeoutException("t")):
            assert provider.get_current_weather(30.0, 31.0) is None

    def test_http_error_degrades_to_none(self):
        provider = OpenWeatherProvider(api_key="test-key")
        with patch(
            "backend.app.services.weather_service.httpx.get",
            side_effect=httpx.HTTPStatusError("401", request=None, response=None),
        ):
            assert provider.get_current_weather(30.0, 31.0) is None

    def test_malformed_response_degrades_to_none(self):
        provider = OpenWeatherProvider(api_key="test-key")
        with patch("backend.app.services.weather_service.httpx.get") as mock_get:
            mock_get.return_value.json.return_value = {"unexpected": True}
            mock_get.return_value.raise_for_status.return_value = None
            assert provider.get_current_weather(30.0, 31.0) is None

    def test_invalid_coordinates_never_call_provider(self):
        provider = OpenWeatherProvider(api_key="test-key")
        with patch("backend.app.services.weather_service.httpx.get") as mock_get:
            assert provider.get_current_weather(91.0, 0.0) is None
            assert provider.get_current_weather(0.0, 181.0) is None
            mock_get.assert_not_called()


class TestDashboardWeather:
    def test_dashboard_without_coordinates_has_no_weather(self, client):
        resp = client.get("/api/v1/catalog/dashboard")
        assert resp.status_code == 200
        assert resp.json().get("weather") is None

    def test_dashboard_with_coordinates_still_works_when_provider_fails(self, client):
        with patch(
            "backend.app.services.weather_service.httpx.get",
            side_effect=httpx.TimeoutException("t"),
        ), patch("backend.app.services.weather_service.settings") as s:
            s.OPENWEATHER_ENABLED = True
            s.OPENWEATHER_API_KEY = "test-key"
            s.OPENWEATHER_BASE_URL = "https://api.openweathermap.org"
            s.OPENWEATHER_TIMEOUT_SECONDS = 10.0
            s.OPENWEATHER_UNITS = "metric"
            resp = client.get("/api/v1/catalog/dashboard?lat=30.04&lon=31.23")
        assert resp.status_code == 200
        body = resp.json()
        assert body["weather"] is None  # graceful degradation, never fabricated
        assert "todays_picks" in body

    def test_dashboard_rejects_out_of_range_coordinates(self, client):
        assert client.get("/api/v1/catalog/dashboard?lat=91&lon=0").status_code == 422


# --------------------------------------------------------------------------
# S1 — Alembic round-trip on a clean database
# --------------------------------------------------------------------------

ALEMBIC_TEST_DB = "sqlite:///./backend/data/confit_alembic_test.db"


def _alembic(*args):
    env = {**os.environ, "ALEMBIC_DATABASE_URL": ALEMBIC_TEST_DB}
    return subprocess.run(
        ["python3", "-m", "alembic", "-c", "backend/alembic.ini", *args],
        capture_output=True, text=True, env=env,
    )


@pytest.fixture
def clean_alembic_db():
    path = "./backend/data/confit_alembic_test.db"
    if os.path.exists(path):
        os.remove(path)
    yield
    if os.path.exists(path):
        os.remove(path)


class TestAlembic:
    def test_upgrade_downgrade_round_trip(self, clean_alembic_db):
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
        # Verify real tables exist after upgrade.
        import sqlite3
        conn = sqlite3.connect("./backend/data/confit_alembic_test.db")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert {"users", "products", "outfits", "outfit_items", "recently_viewed"} <= tables

        down = _alembic("downgrade", "base")
        assert down.returncode == 0, down.stderr
        conn = sqlite3.connect("./backend/data/confit_alembic_test.db")
        remaining = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "outfits" not in remaining

        up2 = _alembic("upgrade", "head")
        assert up2.returncode == 0, up2.stderr


# --------------------------------------------------------------------------
# C7 — no fabricated PNG/card URL anywhere in the runtime path
# --------------------------------------------------------------------------

class TestNoFabricatedCardUrl:
    def test_no_fake_card_url_in_source(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        offenders = []
        for root, dirs, files in os.walk(repo_root):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", "dist"}]
            for fname in files:
                if not fname.endswith((".py", ".ts", ".tsx")):
                    continue
                path = os.path.join(root, fname)
                if os.path.abspath(path) == os.path.abspath(__file__):
                    continue  # this test names the pattern it searches for
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                # Only the security-sensitive patterns the mandate prohibits:
                # the fabricated server card URL, and a weak truncated-uuid
                # used specifically as an outfit SHARE token. Truncated uuids
                # for order/tracking/job reference numbers are legitimate
                # business identifiers and out of scope.
                if "api.confit.io/cards" in content or re.search(
                    r"look_\{?\s*f?['\"]?.*uuid4\(\)\.hex\[", content
                ):
                    offenders.append(path)
        assert not offenders, f"fabricated URL / weak token pattern remains: {offenders}"
