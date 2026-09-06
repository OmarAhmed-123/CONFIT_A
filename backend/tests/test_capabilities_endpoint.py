"""J-01 marketing honesty: /catalog/capabilities is the single server-side
source of truth the UI binds commerce/trust claims to. These tests pin the
contract: flags must reflect CONFIGURATION, never assert capabilities.

2026-09-06 remediation regression guard.
"""

from backend.app.core.config import settings


def _get(client):
    res = client.get("/api/v1/catalog/capabilities")
    assert res.status_code == 200
    return res.json()


def test_capabilities_contract_shape(client):
    caps = _get(client)
    assert set(caps.keys()) == {
        "payments_live",
        "payments_mode",
        "bnpl_live",
        "vton_gpu_ready",
        "ai_stylist_live",
        "bopis_live",
        "bopis_store_count",
        "storage_mode",
        "returns_window_days",
    }
    assert isinstance(caps["bopis_store_count"], int)
    assert caps["payments_mode"] in ("live", "demo")


def test_payments_demo_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    monkeypatch.setattr(settings, "TAMARA_API_KEY", None)
    caps = _get(client)
    assert caps["payments_live"] is False
    assert caps["payments_mode"] == "demo"
    # BNPL must never claim live without BOTH payments-live mode AND a PSP key.
    assert caps["bnpl_live"] is False


def test_bnpl_requires_payments_live_and_psp_key(client, monkeypatch):
    # PSP key alone is not enough when payments are in demo mode.
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(settings, "TABBY_API_KEY", "sk-test-tabby")
    caps = _get(client)
    assert caps["bnpl_live"] is False

    monkeypatch.setattr(settings, "PAYMENTS_LIVE", True)
    caps = _get(client)
    assert caps["bnpl_live"] is True
    assert caps["payments_mode"] == "live"


def test_bopis_reflects_real_store_count(client, monkeypatch):
    from backend.app.models.catalog import StoreLocation
    from backend.app.core.database import get_db

    db = next(client.app.dependency_overrides[get_db]()) if get_db in client.app.dependency_overrides else None
    if db is None:
        # fall back to querying through the same session factory tests use
        import pytest
        pytest.skip("no db override available")

    count_before = db.query(StoreLocation).count()
    caps = _get(client)
    assert caps["bopis_store_count"] == count_before
    assert caps["bopis_live"] == (count_before > 0)

    # Adding a store must flip the flag — the UI must never claim boutiques
    # the database does not contain.
    if count_before == 0:
        db.add(StoreLocation(brand_id=1, name="Probe Boutique", city="Dubai", country="UAE",
                             address="probe", phone=None))
        db.commit()
        caps = _get(client)
        assert caps["bopis_store_count"] == 1
        assert caps["bopis_live"] is True


def test_vton_and_stylist_flags_follow_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "VTON_WORKER_URL", None)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(settings, "GROK_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    caps = _get(client)
    assert caps["vton_gpu_ready"] is False
    assert caps["ai_stylist_live"] is False

    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://modal.example/process")
    monkeypatch.setattr(settings, "GROK_API_KEY", "gsk-test")
    caps = _get(client)
    assert caps["vton_gpu_ready"] is True
    assert caps["ai_stylist_live"] is True
