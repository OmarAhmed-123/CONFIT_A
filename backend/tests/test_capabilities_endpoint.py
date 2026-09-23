"""J-01 marketing honesty: /catalog/capabilities is the single server-side
source of truth the UI binds commerce/trust claims to. These tests pin the
contract: flags must reflect CONFIGURATION, never assert capabilities.

2026-09-06 remediation regression guard.
"""

import pytest

from backend.app.core.config import settings
from backend.app.providers.payment.capability_registry import (
    MarketPaymentCapabilityRegistry,
)


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
        # Added 2026-09-23 (hardening): the configuration fact and the measured
        # state, so "we have a key" and "a provider answered" stop sharing one
        # boolean.
        "ai_stylist_configured",
        "ai_stylist_state",
        # Added 2026-09-23: Wardrobe gated uploads on `storage_mode` — the
        # provider's NAME — so a deployment configured for s3 with an
        # unreachable bucket offered uploads that could only fail. This flag is
        # the measurement (live probe folded in by storage_status()).
        "photo_upload_available",
        # Added 2026-09-23 (hardening): the measured basis of `payments_live`
        # and the COD fact, so the trust footer can state what is actually
        # available instead of summarising it into one unearned sentence.
        "payments_live_methods",
        "cod_live",
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


def test_payments_live_is_measured_not_the_environment_variable(client, monkeypatch):
    """The trust footer renders `payments_live` as a live-PSP sentence.

    Measured 2026-09-23: the value was `bool(settings.PAYMENTS_LIVE)`, so one
    environment variable — with no provider key and no live adapter, which is
    production's exact shape (`LIVE_PSP_ADAPTERS = {}`) — made the consumer
    footer state "Card payments are processed by a live payment service
    provider." while `payment_method_is_live("card")` was False. Same defect
    class as the catalogue literal, one level up.
    """
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    monkeypatch.setattr(PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {})

    # The switch alone: configured live, but nothing can charge anything.
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", True)
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    caps = _get(client)
    assert caps["payments_mode"] == "live", "precondition: the switch is on"
    assert caps["payments_live"] is False, (
        "the footer would claim a live payment service provider on a "
        "deployment where no PSP method can settle"
    )
    assert caps["payments_live_methods"] == ["cod"]
    assert caps["cod_live"] is True, "cash on delivery is available and must be stated"

    # And the earned case: a method that can really settle.
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk-test-stripe")
    monkeypatch.setattr(PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {"stripe": object()})
    caps = _get(client)
    assert caps["payments_live"] is True
    assert "card" in caps["payments_live_methods"]


def test_payments_demo_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    monkeypatch.setattr(settings, "TAMARA_API_KEY", None)
    caps = _get(client)
    assert caps["payments_live"] is False
    assert caps["payments_mode"] == "demo"
    # BNPL must never claim live without BOTH payments-live mode AND a PSP key.
    assert caps["bnpl_live"] is False


def test_bnpl_live_requires_a_live_adapter_not_just_a_key(client, monkeypatch):
    """REWRITTEN 2026-09-23 — this test used to assert the defect.

    It was `test_bnpl_requires_payments_live_and_psp_key` and its second half
    asserted that `PAYMENTS_LIVE=true` plus `TABBY_API_KEY` makes `bnpl_live`
    True. It does not: both are CONFIGURATION, and the platform still had no
    live PSP adapter to charge an instalment with (`LIVE_PSP_ADAPTERS` is empty
    until an integration is verified against the provider's sandbox). An
    instalment is a regulated financial commitment, so "a key exists" is not
    evidence that one can be made — the same class of claim as the earlier
    `vton_gpu_ready` and `ai_stylist_live` defects.

    The first half (a demo deployment is not live) was always correct and is
    kept. The rest now holds the honest contract, including the case that
    proves the fix is load-bearing: register a real adapter and the flag flips.
    """
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    # PSP key alone is not enough when payments are in demo mode.
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(settings, "TABBY_API_KEY", "sk-test-tabby")
    caps = _get(client)
    assert caps["bnpl_live"] is False

    # Configuration complete, still no adapter -> NOT live. This is the
    # assertion the old test had backwards.
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", True)
    caps = _get(client)
    assert caps["payments_mode"] == "live"
    assert caps["bnpl_live"] is False, (
        "PAYMENTS_LIVE + a key is configuration, not availability: no live PSP "
        "adapter is implemented, so no instalment can actually be charged"
    )

    # Implement an adapter (as a real integration would) -> live.
    monkeypatch.setitem(
        PaymentOrchestrator.LIVE_PSP_ADAPTERS, "tabby", lambda **kw: {"status": "authorized"}
    )
    assert _get(client)["bnpl_live"] is True

    # Remove the provider's credential -> not live again, even with the adapter.
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    assert _get(client)["bnpl_live"] is False


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


def test_stylist_flag_is_measured_and_configuration_has_its_own_name(client, monkeypatch):
    """REWRITTEN 2026-09-23 — this test used to assert the defect.

    It was written to keep the *configuration* semantics of `ai_stylist_live`
    honest by naming ("it answers a configuration question"), and the name lied
    anyway: the flag is called `_live`. A key is not a measurement, so the flag
    now means measured readiness, and the configuration fact is published as
    `ai_stylist_configured`.

    Measured 2026-09-23: production reports `ai_stylist_live: true` derived from
    `bool(provider key)`; no provider had ever been contacted by that code path.
    """
    import httpx

    from backend.app.services import ai_readiness

    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None)
    monkeypatch.setattr(settings, "GROK_API_KEY", None)
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    ai_readiness.reset_cache_for_tests()

    caps = _get(client)
    assert caps["ai_stylist_live"] is False
    assert caps["ai_stylist_configured"] is False
    assert caps["ai_stylist_state"] == "not_configured"

    # A key is now CONFIGURATION: it does not make the flag live by itself.
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test")
    caps = _get(client)
    assert caps["ai_stylist_configured"] is True, "the key must be visible as configuration"
    assert caps["ai_stylist_live"] is False, (
        "a configured key published as `live` is the defect this test used to assert"
    )
    assert caps["ai_stylist_state"] == "not_probed"

    # Only a MEASUREMENT makes it live.
    monkeypatch.setattr(
        ai_readiness, "_configured_providers",
        lambda: {"groq": {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer k"}},
    )
    ai_readiness._cache.store(
        ai_readiness.probe_now(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    )
    caps = _get(client)
    assert caps["ai_stylist_live"] is True
    assert caps["ai_stylist_state"] == "ready"
    ai_readiness.reset_cache_for_tests()


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


# ---------------------------------------------------------------------------
# 2026-09-23 — the payment-method list claimed "live" from a literal
#
# `PaymentMethodOption.is_live` defaulted to True and every entry of
# PAYMENT_CATALOG hardcoded `is_live=True`, so production served
#   {"id": "bnpl_tabby", "title_en": "Tabby — Split in 4",
#    "description_en": "Split in 4 interest-free monthly payments. Sharia
#    compliant.", "is_live": true}
# on the same deployment whose /catalog/capabilities answered
# `bnpl_live=false`, `payments_mode=demo`, and which held no Tabby key.
# ---------------------------------------------------------------------------


def _methods(client, country_code="EG"):
    res = client.get(f"/api/v1/commerce/payment-methods?country_code={country_code}")
    assert res.status_code == 200, res.text
    body = res.json()
    expected_market = MarketPaymentCapabilityRegistry.market_code(country_code)
    assert body["market_code"] == expected_market, (
        f"asked for {country_code!r} and was answered for {body['market_code']!r} — "
        "a request for one market must never be silently answered with another"
    )
    return {m["id"]: m for m in body["available_methods"]}


def test_payment_methods_answer_for_the_requested_market(client):
    """A client asking for one market must not be answered for another.

    Regression guard for a defect this suite carried itself: the helper used to
    send ``?country=`` while the endpoint's parameter is ``country_code``.
    FastAPI ignores unknown query parameters, so every call was silently served
    the default market (EG) while looking market-aware — a test that passes
    without executing the branch it appears to exercise. The helper now asserts
    the echoed market, and the assumption that the branches differ is pinned
    here: Tamara is an AE/SA method and must not appear for EG.
    """
    ae = _methods(client, "AE")
    assert "bnpl_tamara" in ae, "AE must resolve to the AE catalogue, not the default"
    eg = _methods(client, "EG")
    assert "bnpl_tamara" not in eg, "EG must not be served the AE catalogue"


def test_payment_method_is_live_is_measured_not_a_literal(client, monkeypatch):
    """A demo deployment must not label any PSP method live."""
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    monkeypatch.setattr(PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {})

    methods = _methods(client)
    assert methods["bnpl_tabby"]["is_live"] is False, (
        "Tabby was reported live by a deployment that cannot charge an "
        "instalment — a regulated financing claim with nothing behind it"
    )
    assert methods["card"]["is_live"] is False
    # COD engages no PSP, so it stays live wherever it is offered.
    assert methods["cod"]["is_live"] is True


def test_payment_method_live_requires_key_adapter_and_live_mode(client, monkeypatch):
    """All three conditions, and each one alone is not enough."""
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    monkeypatch.setattr(PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {})

    # live mode + key, but no adapter -> not live (the missing third condition)
    monkeypatch.setattr(settings, "PAYMENTS_LIVE", True)
    monkeypatch.setattr(settings, "TABBY_API_KEY", "sk-test-tabby")
    assert _methods(client)["bnpl_tabby"]["is_live"] is False

    # adapter + live mode, but the provider's credential was revoked -> not live
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    monkeypatch.setitem(
        PaymentOrchestrator.LIVE_PSP_ADAPTERS, "tabby", lambda **kw: {"status": "authorized"}
    )
    assert _methods(client)["bnpl_tabby"]["is_live"] is False

    # all three -> live
    monkeypatch.setattr(settings, "TABBY_API_KEY", "sk-test-tabby")
    assert _methods(client)["bnpl_tabby"]["is_live"] is True


def test_catalog_cannot_carry_a_liveness_claim_and_stamping_never_mutates_it(client):
    """The latent trap: a catalogue entry able to publish liveness again.

    PR #176 measured `is_live` at the endpoint boundary, but `PAYMENT_CATALOG`
    still held `is_live=True` on seven entries and the shared model still
    defaulted it to `True` — an internal source of truth that could reproduce
    the false claim the moment a caller stopped stamping. The catalogue is now a
    different model that has no liveness field at all, and this test fails if
    the concept is ever reintroduced there.

    It also keeps the shared-singleton invariant it was written for:
    `PAYMENT_CATALOG` holds module-level instances shared by every request, so
    stamping must produce new objects, never edit the shared ones.
    """
    entries = list(MarketPaymentCapabilityRegistry.PAYMENT_CATALOG.values())
    assert entries, "precondition: the catalogue is not empty"

    for entry in entries:
        assert not hasattr(entry, "is_live"), (
            f"catalogue entry {entry.id!r} exposes `is_live`: liveness is a "
            "property of a deployment, not of a catalogue entry — a literal "
            "here can be serialised into a shopper-visible claim"
        )

    ids_before = sorted(MarketPaymentCapabilityRegistry.PAYMENT_CATALOG)
    snapshots = {i: MarketPaymentCapabilityRegistry.PAYMENT_CATALOG[i].model_dump() for i in ids_before}

    res = client.get("/api/v1/commerce/payment-methods?country_code=EG")
    assert res.status_code == 200, res.text
    served = {m["id"]: m for m in res.json()["available_methods"]}
    assert served["cod"]["is_live"] is True  # the measured layer does publish it

    assert sorted(MarketPaymentCapabilityRegistry.PAYMENT_CATALOG) == ids_before
    for i in ids_before:
        after = MarketPaymentCapabilityRegistry.PAYMENT_CATALOG[i].model_dump()
        assert after == snapshots[i], (
            f"a request mutated the shared catalogue entry {i!r}: one "
            "deployment's measured state would leak into another response"
        )


def test_a_forgotten_liveness_stamp_is_an_error_not_a_false_claim():
    """The unsafe default, gone: omission must fail loudly.

    `is_live: bool = True` on the shared model is what let a forgotten stamp
    become a regulated claim. The measured model has no default, so building one
    without a measurement is a ValidationError — verified here rather than
    asserted in prose.
    """
    from pydantic import ValidationError

    from backend.app.providers.payment.schemas import (
        PaymentMethodAvailability,
        PaymentMethodOption,
    )

    option = MarketPaymentCapabilityRegistry.PAYMENT_CATALOG["bnpl_tabby"]
    with pytest.raises(ValidationError):
        PaymentMethodAvailability(**option.model_dump())

    stamped = PaymentMethodAvailability(**option.model_dump(), is_live=False)
    assert stamped.is_live is False
    # The two concepts stay separate: the catalogue type is not the wire type.
    assert not issubclass(PaymentMethodOption, PaymentMethodAvailability)
    assert issubclass(PaymentMethodAvailability, PaymentMethodOption)


def _payment_body(client, country_code="EG"):
    res = client.get(f"/api/v1/commerce/payment-methods?country_code={country_code}")
    assert res.status_code == 200, res.text
    return res.json()


def test_payment_disclaimer_makes_no_compliance_claim_nothing_can_back(client, monkeypatch):
    """PCI-DSS and central-bank wording require a rail that can actually settle.

    Production served "All transactions in EG are processed in compliance with
    local central bank regulations and PCI-DSS tokenization standards." while
    card, Tabby, Vodafone Cash and InstaPay were all ``is_live=false`` and the
    deployment held no PSP credential. Nothing was tokenized; nothing was
    regulated; the sentence was decoration on the money path.
    """
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(settings, "TABBY_API_KEY", None)
    monkeypatch.setattr(settings, "TAMARA_API_KEY", None)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", None)
    monkeypatch.setattr(PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {})

    body = _payment_body(client, "EG")
    live = [m["id"] for m in body["available_methods"] if m["is_live"]]
    assert live == ["cod"], f"precondition: only COD may settle here, got {live}"

    for field in ("disclaimer_en", "disclaimer_ar"):
        assert "PCI-DSS" not in body[field], f"{field} still claims tokenization: {body[field]}"
        assert "central bank" not in body[field].lower()
    assert "not enabled" in body["disclaimer_en"]
    assert "Cash on delivery is the only live payment method in EG" in body["disclaimer_en"]
    assert "الاستلام" in body["disclaimer_ar"], "the Arabic must say it, not just the English"


def test_payment_disclaimer_keeps_the_compliance_line_when_a_psp_method_is_live(
    client, monkeypatch
):
    """The sentence is kept where it is earned — otherwise it is only deleted."""
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    monkeypatch.setattr(settings, "PAYMENTS_LIVE", True)
    monkeypatch.setattr(settings, "TABBY_API_KEY", "sk-test-tabby")
    # The adapter registry is keyed by PROVIDER ("tabby"), not by method id —
    # `live_adapter_for` maps method -> provider first.
    monkeypatch.setattr(
        PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {"tabby": object()}
    )

    body = _payment_body(client, "EG")
    assert _methods(client, "EG")["bnpl_tabby"]["is_live"] is True, (
        "precondition: this is the live case"
    )
    assert "PCI-DSS" in body["disclaimer_en"]
    assert "PCI-DSS" in body["disclaimer_ar"]


def test_payment_disclaimer_speaks_for_markets_with_no_method_at_all(client, monkeypatch):
    """`?country_code=XX` was told "All transactions in XX are processed...".

    An unserved market now gets an unserved-market sentence — not the EG one,
    and not a compliance claim about a country the platform does not operate in.
    """
    from backend.app.providers.payment.orchestrator import PaymentOrchestrator

    monkeypatch.setattr(settings, "PAYMENTS_LIVE", False)
    monkeypatch.setattr(PaymentOrchestrator, "LIVE_PSP_ADAPTERS", {})

    body = _payment_body(client, "XX")
    live = [m["id"] for m in body["available_methods"] if m["is_live"]]
    assert live == [], f"precondition: nothing may settle in XX, got {live}"
    assert "No payment method is enabled for XX" in body["disclaimer_en"]
    assert "PCI-DSS" not in body["disclaimer_en"]


def test_photo_upload_available_is_measured_while_storage_mode_is_a_name(client, monkeypatch):
    """Wardrobe gated uploads on `storage_mode == "local"`.

    That is the provider's NAME. A deployment configured for object storage with
    an unreachable bucket or a revoked credential reports "s3" and offers
    uploads that can only fail. The gate must read the measurement.
    """
    from backend.app.services import capability_service

    # A deployment that says "s3" but cannot actually write: the case the old
    # gate got wrong. Both the reported name and the probe are set here so the
    # scenario is coherent (name says object storage, probe says unwritable).
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "s3")
    monkeypatch.setattr(
        capability_service,
        "storage_status",
        lambda: {"provider": "s3", "production_grade": False, "writable": True,
                 "detail": "object storage is configured but the live probe failed"},
    )
    caps = _get(client)
    assert caps["storage_mode"] == "s3"
    assert caps["photo_upload_available"] is False, (
        "storage_mode reads 's3' while every upload would fail — the flag must "
        "come from the probe, not the provider name"
    )

    # A genuinely writable object store.
    monkeypatch.setattr(
        capability_service,
        "storage_status",
        lambda: {"provider": "s3", "production_grade": True, "writable": True},
    )
    assert _get(client)["photo_upload_available"] is True


# ---------------------------------------------------------------------------
# Cross-layer drift guard: a new backend state must not reach the UI untranslated
#
# `ORDER_TRANSITIONS` is the backend's state space; the frontend renders those
# states on the post-purchase page. Before 2026-09-23 it rendered the raw enum
# ("pending_delivery", "credit_due") as English text in a bilingual product.
# A state added to the backend would have shipped untranslated with no gate
# noticing, because a `.replace()` on a runtime value is invisible to a text
# scan. This test reads BOTH sides so a new state cannot slip through.
# ---------------------------------------------------------------------------


def _frontend_state_map(name: str) -> dict:
    """Parse a literal map out of frontend/src/i18n/orderState.ts."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "frontend/src/i18n/orderState.ts"
    if not src.exists():  # pragma: no cover - defensive, kept explicit
        raise AssertionError(f"frontend state map not found at {src}")
    text = src.read_text(encoding="utf-8")
    block = re.search(rf"{name}[^=]*= \{{(.*?)\}};", text, re.S)
    assert block, f"{name} not found in orderState.ts"
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"(\w+):\s*'([^']+)'", block.group(1))
    }


def test_every_order_state_has_a_frontend_translation_key():
    from backend.app.services.commerce_service import ORDER_TRANSITIONS

    backend_states = set(ORDER_TRANSITIONS)
    for targets in ORDER_TRANSITIONS.values():
        backend_states |= set(targets)

    mapped = _frontend_state_map("ORDER_STATUS_KEYS")
    missing = sorted(s for s in backend_states if s not in mapped)
    assert not missing, (
        "these order states would render untranslated on the tracking page: "
        f"{missing}. Add them to frontend/src/i18n/orderState.ts and both locale "
        "files, or the shopper sees a raw machine token."
    )

    # And every key must exist in both locales (the vitest covers the values;
    # this covers a key renamed on one side only).
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "frontend/src/i18n"
    locales = {
        loc: json.loads((root / f"{loc}.json").read_text(encoding="utf-8"))
        for loc in ("en", "ar")
    }
    for state, key in mapped.items():
        node: object = locales["en"]
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        assert isinstance(node, str) and node.strip(), f"en.json is missing {key} ({state})"


def test_every_payment_status_and_method_has_a_translation_key():
    import re
    from pathlib import Path

    from backend.app.providers.payment.capability_registry import (
        MarketPaymentCapabilityRegistry,
    )

    service_src = (
        Path(__file__).resolve().parents[2] / "backend/app/services/commerce_service.py"
    ).read_text(encoding="utf-8")
    # Every literal `payment_status="x"` / `payment_status = "x"` assignment.
    statuses = set(re.findall(r'payment_status\s*=\s*"([a-z_]+)"', service_src))
    statuses |= set(re.findall(r'return "([a-z_]+)"', service_src.split("_map_provider_status")[1][:600]))

    mapped_status = _frontend_state_map("PAYMENT_STATUS_KEYS")
    missing = sorted(s for s in statuses if s not in mapped_status)
    assert not missing, f"payment states rendered untranslated: {missing}"

    mapped_methods = _frontend_state_map("PAYMENT_METHOD_KEYS")
    missing_methods = sorted(
        m for m in MarketPaymentCapabilityRegistry.PAYMENT_CATALOG if m not in mapped_methods
    )
    assert not missing_methods, f"payment methods rendered untranslated: {missing_methods}"
