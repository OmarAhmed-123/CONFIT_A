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
        # Added 2026-09-22: the UI must distinguish "not offered on this
        # deployment" from "offered and currently broken" without parsing
        # English prose out of a detail string.
        "vton_engine_state",
        "vton_offered",
        "vton_renderable",
        "ai_stylist_live",
        "bopis_live",
        "bopis_store_count",
        "storage_mode",
        "returns_window_days",
    }
    assert isinstance(caps["bopis_store_count"], int)
    assert caps["payments_mode"] in ("live", "demo")
    assert caps["vton_engine_state"] in (
        "available",
        "cold_start",
        "temporarily_unavailable",
        "misconfigured",
    )


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


def test_stylist_flag_follows_configuration(client, monkeypatch):
    """``ai_stylist_live`` means "a provider key exists", and says so.

    Kept honest by naming: this flag answers a *configuration* question. It is
    not a claim that the provider answered a request, and no probe exists for
    it — see the note on ``vton_gpu_ready`` below for why conflating the two
    caused a production incident.
    """
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(settings, "GROK_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    assert _get(client)["ai_stylist_live"] is False

    monkeypatch.setattr(settings, "GROK_API_KEY", "gsk-test")
    assert _get(client)["ai_stylist_live"] is True


def test_vton_gpu_ready_does_not_follow_configuration(client, monkeypatch):
    """REWRITTEN 2026-09-22 — this test used to assert the production defect.

    As ``test_vton_and_stylist_flags_follow_configuration`` it asserted:

        monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://modal.example/process")
        assert caps["vton_gpu_ready"] is True

    That is the bug, written down as an expectation. It is why the defect
    survived: the suite defended it, so the contradiction with
    ``/try-on/capabilities`` (which probed the worker for real) read as a
    passing state rather than a regression. Green tests are not evidence that
    the thing being tested is true — they are evidence that code matches
    whatever the test author believed.

    Setting an environment variable is not a GPU becoming reachable. The flag
    must track the live probe.
    """
    from backend.app.services import vton_worker_observability as vwo

    monkeypatch.setattr(settings, "VTON_WORKER_URL", None)
    caps = _get(client)
    assert caps["vton_gpu_ready"] is False
    assert caps["vton_offered"] is False
    assert caps["vton_engine_state"] == "misconfigured"

    # Configured but nothing measured: offered, NOT ready.
    monkeypatch.setattr(settings, "VTON_WORKER_URL", "https://modal.example/process")
    monkeypatch.setattr(
        vwo, "vton_health_summary", lambda: {"verdict": vwo.VERDICT_UNAVAILABLE}
    )
    caps = _get(client)
    assert caps["vton_offered"] is True, "the deployment offers try-on"
    assert caps["vton_gpu_ready"] is False, (
        "presence of VTON_WORKER_URL is not GPU readiness — 2026-09-22 defect"
    )
    assert caps["vton_renderable"] is False

    # Only a live `ready` verdict may set it true.
    monkeypatch.setattr(
        vwo, "vton_health_summary", lambda: {"verdict": vwo.VERDICT_READY}
    )
    caps = _get(client)
    assert caps["vton_gpu_ready"] is True
    assert caps["vton_engine_state"] == "available"
