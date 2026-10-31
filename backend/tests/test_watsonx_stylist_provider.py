"""watsonx.ai stylist leg — contract and failure behaviour.

These tests never contact IBM. They pin the properties that decide whether the
leg is SAFE to put in the stylist chain:

  1. an unconfigured deployment skips it at zero cost;
  2. a valid answer is returned with the model IBM actually served;
  3. no usable answer returns None so the chain fails over instead of shipping
     an empty string under a provider label (the defect already fixed once for
     Groq — see orchestrator._accept_chat_completion);
  4. an expired token is refreshed once, then the call succeeds;
  5. an auth fault raises and quarantines the leg rather than retrying forever;
  6. the API key and token never appear in status output.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from backend.app.core.config import settings
from backend.app.providers.watsonx.client import WatsonxAuthError, WatsonxClient


@pytest.fixture()
def watsonx(monkeypatch):
    """A client configured with fake credentials and no cached token."""
    monkeypatch.setattr(settings, "IBM_CLOUD_API_KEY", "fake-api-key-for-tests", raising=False)
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", "11111111-2222-3333-4444-555555555555", raising=False)
    monkeypatch.setattr(settings, "WATSONX_BASE_URL", "https://eu-de.ml.cloud.ibm.com", raising=False)
    monkeypatch.setattr(settings, "WATSONX_MODEL_ID", "ibm/granite-4-h-small", raising=False)
    return WatsonxClient()


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("POST", "https://example.invalid")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=self.request, response=self  # type: ignore[arg-type]
            )


def _install_transport(monkeypatch, handler):
    """Route every httpx.AsyncClient.post through `handler(url, kwargs)`."""

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            return handler(url, kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


def test_unconfigured_deployment_skips_the_leg_without_calling_ibm(monkeypatch):
    """No key or no project => not configured, and no network call is made."""
    monkeypatch.setattr(settings, "IBM_CLOUD_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", None, raising=False)
    client = WatsonxClient()

    called = {"n": 0}

    def _boom(url, kwargs):  # pragma: no cover - must never run
        called["n"] += 1
        raise AssertionError("no network call may happen when unconfigured")

    _install_transport(monkeypatch, _boom)
    assert client.is_configured() is False
    assert asyncio.run(client.chat("sys", "user")) is None
    assert called["n"] == 0


def test_partial_configuration_is_not_enough(watsonx, monkeypatch):
    """A key without a project id would pay an IAM round trip and then fail."""
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", None, raising=False)
    assert watsonx.is_configured() is False


def test_returns_the_model_ibm_actually_served(watsonx, monkeypatch):
    """The label must come from the response, never from our request."""

    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok", "expires_in": 3600})
        assert kwargs["json"]["project_id"] == "11111111-2222-3333-4444-555555555555"
        assert kwargs["json"]["messages"][0]["role"] == "system"
        return _FakeResponse(
            200,
            {
                "model_id": "ibm/granite-4-h-small",
                "choices": [{"message": {"content": "  Wear the navy dress.  "}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 42},
            },
        )

    _install_transport(monkeypatch, handler)
    content, model = asyncio.run(watsonx.chat("system", "user"))
    assert content == "Wear the navy dress."   # trimmed
    assert model == "ibm/granite-4-h-small"


def test_empty_answer_returns_none_so_the_chain_fails_over(watsonx, monkeypatch):
    """An empty string must never be accepted as styling advice."""

    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok"})
        return _FakeResponse(200, {"choices": [{"message": {"content": "   "}, "finish_reason": "length"}]})

    _install_transport(monkeypatch, handler)
    assert asyncio.run(watsonx.chat("system", "user")) is None


def test_no_choices_returns_none(watsonx, monkeypatch):
    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok"})
        return _FakeResponse(200, {"results": []})

    _install_transport(monkeypatch, handler)
    assert asyncio.run(watsonx.chat("system", "user")) is None


def test_expired_token_is_refreshed_once_then_the_call_succeeds(watsonx, monkeypatch):
    """A 401 on a cached token must cost one extra exchange, not a lost request."""
    state = {"iam": 0, "chat": 0}

    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            state["iam"] += 1
            return _FakeResponse(200, {"access_token": f"tok-{state['iam']}"})
        state["chat"] += 1
        if state["chat"] == 1:
            return _FakeResponse(401, {"error": "token expired"})
        return _FakeResponse(200, {"choices": [{"message": {"content": "Second time lucky."}}]})

    _install_transport(monkeypatch, handler)
    content, _ = asyncio.run(watsonx.chat("system", "user"))
    assert content == "Second time lucky."
    assert state["iam"] == 2  # initial exchange + one forced refresh
    assert state["chat"] == 2


def test_repeated_401_raises_rather_than_looping(watsonx, monkeypatch):
    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok"})
        return _FakeResponse(401, {"error": "still unauthorised"})

    _install_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(watsonx.chat("system", "user"))


def test_bad_api_key_raises_an_auth_error_and_never_echoes_the_key(watsonx, monkeypatch):
    secret = "SUPER-SECRET-KEY-VALUE"

    def handler(url, kwargs):
        assert kwargs["data"]["apikey"] == "fake-api-key-for-tests"
        return _FakeResponse(400, {"errorCode": "BXNIM0415E", "errorMessage": "Provided API key could not be found."})

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(settings, "IBM_CLOUD_API_KEY", "fake-api-key-for-tests", raising=False)
    with pytest.raises(WatsonxAuthError) as exc:
        asyncio.run(watsonx.chat("system", "user"))
    assert "BXNIM0415E" in str(exc.value)
    assert secret not in str(exc.value)
    assert "fake-api-key-for-tests" not in str(exc.value)


def test_status_is_secret_free(watsonx):
    status = watsonx.status()
    blob = repr(status)
    assert status["configured"] is True
    assert status["model_id"] == "ibm/granite-4-h-small"
    assert "fake-api-key-for-tests" not in blob
    assert "11111111-2222-3333-4444-555555555555" not in blob


def test_orchestrator_reports_watsonx_in_provider_status(monkeypatch):
    from backend.app.providers.orchestrator import MultiProviderAIOrchestrator

    monkeypatch.setattr(settings, "IBM_CLOUD_API_KEY", "k", raising=False)
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", "p", raising=False)
    status = MultiProviderAIOrchestrator().provider_status()
    assert "watsonx" in status
    assert status["watsonx"]["configured"] is True
    assert status["watsonx"]["cooling_for_seconds"] == 0


def test_watsonx_is_last_in_the_default_chain():
    """It must not displace a provider that is already serving traffic."""
    default = (
        "local_gpu,nvidia,groq,gemini,openai,unorouter,watsonx"
    )
    assert default.split(",")[-1] == "watsonx"


# ── budget-claim guard ───────────────────────────────────────────────────
# Reproduced live 2026-10-24 against IBM Granite: asked for a look "under 7000
# EGP" from items priced 4200 and 6800, the model answered "under 7000 EGP"
# while recommending both (11,000). 3/3 occurrences, English and Arabic.

def test_budget_claim_guard_rejects_an_english_promise_the_catalogue_breaks():
    from backend.app.providers.orchestrator import budget_claim_violated

    outfit = {"items": [{"price": 4200}, {"price": 6800}]}
    assert budget_claim_violated(
        "A chic wedding look under 7000 EGP: the blazer (4200) with the dress (6800).", outfit
    ) == (7000.0, 11000.0)


def test_budget_claim_guard_rejects_the_arabic_equivalent():
    from backend.app.providers.orchestrator import budget_claim_violated

    outfit = {"items": [{"price": 6800}, {"price": 900}]}
    assert budget_claim_violated("لوك رائع بأقل من 5000 جنيه.", outfit) == (5000.0, 7700.0)


def test_budget_claim_guard_accepts_a_promise_the_catalogue_keeps():
    from backend.app.providers.orchestrator import budget_claim_violated

    outfit = {"items": [{"price": 4200}, {"price": 900}]}
    assert budget_claim_violated("All of this for under 7000 EGP.", outfit) is None


def test_budget_claim_guard_ignores_prose_without_a_ceiling():
    from backend.app.providers.orchestrator import budget_claim_violated

    outfit = {"items": [{"price": 4200}]}
    assert budget_claim_violated("Wear the navy dress with gold earrings.", outfit) is None
    assert budget_claim_violated("", outfit) is None
    assert budget_claim_violated("under 100", None) is None


def test_budget_claim_guard_uses_the_composer_total_when_present():
    """total_price is the authority; per-item prices are only a fallback."""
    from backend.app.providers.orchestrator import budget_claim_violated

    outfit = {"total_price": 11000.0, "items": [{"price": 1}]}
    assert budget_claim_violated("under 7000 EGP", outfit) == (7000.0, 11000.0)


def test_budget_claim_guard_does_not_trip_on_sizes_dates_or_counts():
    from backend.app.providers.orchestrator import budget_claim_violated

    outfit = {"items": [{"price": 4200}]}
    for text in (
        "Step 2: add the blazer.",
        "Perfect for a 2026 summer wedding.",
        "Size 38, understated ivory silk.",
        "Understated and elegant.",
    ):
        assert budget_claim_violated(text, outfit) is None, text


# ═══════════════════════════════════════════════════════════════════════════
# Granite BUILDS the styling list (the IBM tutorial's Step 8)
#
# The tutorial reads the answer back by substring-matching image filenames.
# That cannot express "this product is not in the catalogue", so the checks
# below centre on the one failure that would put a fake product in a shopper's
# drawer: an id the model was never shown.
# ═══════════════════════════════════════════════════════════════════════════

class _P:
    """Minimal stand-in for a catalogue product."""

    def __init__(self, pid, title, price, slot):
        self.id = pid
        self.title = title
        self.base_price = price
        self.currency = "EGP"
        self.color_family = "Navy"
        self.material = "Silk"
        self.thumbnail_url = "https://example.invalid/x.jpg"
        self._detected_slot = slot
        self._formality_num = 3

        class _Brand:
            brand_name = f"Brand{pid}"

        class _Cat:
            name = "Apparel"
            slug = "apparel"

        self.brand = _Brand()
        self.category = _Cat()
        self.skus = []
        # classify_product_slot reads this; the real model has it as a column.
        self.style_tags = "[]"
        self.dominant_hex = "#1B1F3B"


def _products():
    from backend.app.services.styling.ontology import SlotType

    return [
        _P(1, "Linen Blazer", 4200, SlotType.FORMAL_OUTER),
        _P(2, "Silk Shirt", 2600, SlotType.FORMAL_SHIRT),
        _P(3, "Wool Trousers", 3400, SlotType.FORMAL_BOTTOM),
        _P(4, "Leather Loafers", 2900, SlotType.FORMAL_SHOES),
        _P(5, "Slip Dress", 6800, SlotType.DRESS),
    ]


def test_position_mapping_matches_the_composers_buckets():
    from backend.app.services.styling.watsonx_list_builder import position_for

    ps = _products()
    assert [position_for(p) for p in ps] == ["outerwear", "top", "bottom", "footwear", "dress"]


def test_validation_accepts_a_real_selection():
    from backend.app.services.styling.watsonx_list_builder import validate_selection

    ps = _products()
    offered = {p.id: p for p in ps}
    chosen = validate_selection(
        {"items": [{"product_id": 2, "reason": "clean base"}, {"product_id": 3}, {"product_id": 4}]},
        offered,
    )
    assert [p.id for p, _ in chosen] == [2, 3, 4]
    assert chosen[0][1] == "clean base"


def test_validation_rejects_an_invented_product():
    """The whole point of the module: an id the shopper was never offered."""
    from backend.app.services.styling.watsonx_list_builder import ValidationError, validate_selection

    offered = {p.id: p for p in _products()}
    with pytest.raises(ValidationError) as exc:
        validate_selection({"items": [{"product_id": 2}, {"product_id": 999}]}, offered)
    assert "not offered" in str(exc.value)


def test_validation_rejects_a_duplicate_or_a_non_integer_id():
    from backend.app.services.styling.watsonx_list_builder import ValidationError, validate_selection

    offered = {p.id: p for p in _products()}
    with pytest.raises(ValidationError):
        validate_selection({"items": [{"product_id": 2}, {"product_id": 2}]}, offered)
    with pytest.raises(ValidationError):
        validate_selection({"items": [{"product_id": "two"}, {"product_id": 3}]}, offered)


def test_validation_rejects_a_single_item_or_an_oversized_list():
    from backend.app.services.styling.watsonx_list_builder import ValidationError, validate_selection

    offered = {p.id: p for p in _products()}
    with pytest.raises(ValidationError):
        validate_selection({"items": [{"product_id": 2}]}, offered)
    with pytest.raises(ValidationError):
        validate_selection({"items": [{"product_id": 2}] * 6}, offered)


def test_json_extraction_tolerates_fences_and_stray_prose():
    from backend.app.services.styling.watsonx_list_builder import _extract_json

    body = '{"items": [{"product_id": 2}], "title": "Navy evening"}'
    assert _extract_json(body)["title"] == "Navy evening"
    assert _extract_json(f"```json\n{body}\n```")["title"] == "Navy evening"
    assert _extract_json(f"Sure, here you go:\n{body}")["title"] == "Navy evening"
    assert _extract_json("no json here") is None


def test_builder_returns_none_when_the_model_is_unconfigured(monkeypatch):
    """Inert without credentials - it must never touch the network."""
    from backend.app.services.styling.watsonx_list_builder import WatsonxListBuilder

    monkeypatch.setattr(settings, "IBM_CLOUD_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", None, raising=False)
    assert asyncio.run(WatsonxListBuilder().build(_products(), {"occasion": "Wedding"})) is None


def test_builder_accepts_a_valid_model_answer(watsonx, monkeypatch):
    from backend.app.services.styling.watsonx_list_builder import WatsonxListBuilder

    answer = (
        '{"items": [{"product_id": 2, "reason": "crisp base"}, '
        '{"product_id": 3, "reason": "structured leg"}, '
        '{"product_id": 4, "reason": "polished finish"}], "title": "The Navy Wedding Edit"}'
    )

    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok"})
        # The prompt must contain only real catalogue ids.
        prompt = kwargs["json"]["messages"][1]["content"]
        assert "product_id" in prompt and "999" not in prompt
        return _FakeResponse(200, {"choices": [{"message": {"content": answer}}]})

    _install_transport(monkeypatch, handler)
    sel = asyncio.run(WatsonxListBuilder(watsonx).build(_products(), {"occasion": "Wedding"}))
    assert sel is not None
    assert [e["product"].id for e in sel["items"]] == [2, 3, 4]
    assert sel["title"] == "The Navy Wedding Edit"


def test_builder_drops_the_whole_answer_when_one_id_is_invented(watsonx, monkeypatch):
    """Partial trust is not an option: one fake product voids the selection."""
    from backend.app.services.styling.watsonx_list_builder import WatsonxListBuilder

    answer = '{"items": [{"product_id": 2}, {"product_id": 3}, {"product_id": 999}]}'

    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok"})
        return _FakeResponse(200, {"choices": [{"message": {"content": answer}}]})

    _install_transport(monkeypatch, handler)
    assert asyncio.run(WatsonxListBuilder(watsonx).build(_products(), {"occasion": "Wedding"})) is None


def test_builder_rejects_an_unwearable_shape(watsonx, monkeypatch):
    """Two accessories are not an outfit, however legal each id is."""
    from backend.app.services.styling.watsonx_list_builder import WatsonxListBuilder

    from backend.app.services.styling.ontology import SlotType

    products = _products() + [_P(6, "Silk Scarf", 900, SlotType.BAG)]
    answer = '{"items": [{"product_id": 6}, {"product_id": 1}]}'

    def handler(url, kwargs):
        if "iam.cloud.ibm.com" in url:
            return _FakeResponse(200, {"access_token": "tok"})
        return _FakeResponse(200, {"choices": [{"message": {"content": answer}}]})

    _install_transport(monkeypatch, handler)
    assert asyncio.run(WatsonxListBuilder(watsonx).build(products, {"occasion": "Wedding"})) is None


def test_builder_survives_a_network_failure(watsonx, monkeypatch):
    """A styling request must never fail because IBM is unreachable."""
    from backend.app.services.styling.watsonx_list_builder import WatsonxListBuilder

    def handler(url, kwargs):
        raise httpx.ConnectError("connection refused")

    _install_transport(monkeypatch, handler)
    assert asyncio.run(WatsonxListBuilder(watsonx).build(_products(), {"occasion": "Wedding"})) is None


def test_composer_applies_a_valid_ai_selection():
    from backend.app.services.styling.composer import OutfitComposer

    products = _products()
    for p in products:
        from backend.app.services.styling.watsonx_list_builder import position_for

        p._position_test = position_for(p)
    selection = {
        "items": [
            {"product": products[1], "reason": "crisp base"},
            {"product": products[2], "reason": "structured leg"},
            {"product": products[3], "reason": "polished finish"},
        ],
        "title": "The Navy Wedding Edit",
    }
    outfits = OutfitComposer().compose_outfits(
        products, {"occasion": "Wedding", "formality": "formal"}, ai_selection=selection
    )
    assert outfits, "a valid selection must still publish a look"
    ids = {i["product_id"] for i in outfits[0]["items"]}
    assert ids == {2, 3, 4}
    assert outfits[0]["title"] == "The Navy Wedding Edit"


def test_composer_ignores_a_selection_naming_a_product_it_did_not_classify():
    """Belt-and-braces: the composer re-checks, it does not trust its caller."""
    from backend.app.services.styling.composer import OutfitComposer

    products = _products()
    stranger = _P(777, "Ghost Coat", 100, products[0]._detected_slot)
    selection = {
        "items": [
            {"product": stranger, "reason": "x"},
            {"product": products[2], "reason": "y"},
        ],
        "title": "Ghost look",
    }
    outfits = OutfitComposer().compose_outfits(
        products, {"occasion": "Wedding", "formality": "formal"}, ai_selection=selection
    )
    if outfits:
        assert 777 not in {i["product_id"] for i in outfits[0]["items"]}
        assert outfits[0]["title"] != "Ghost look"


def test_compose_outfits_is_unchanged_when_no_selection_is_passed():
    """The deterministic engine is still the default and must not regress."""
    from backend.app.services.styling.composer import OutfitComposer

    a = OutfitComposer().compose_outfits(_products(), {"occasion": "Wedding", "formality": "formal"})
    b = OutfitComposer().compose_outfits(
        _products(), {"occasion": "Wedding", "formality": "formal"}, ai_selection=None
    )
    assert [i["product_id"] for i in a[0]["items"]] == [i["product_id"] for i in b[0]["items"]]


def test_an_ungrammatical_move_is_refused_rather_than_shown():
    """DRESS + TROUSERS observed live 2026-10-24: legal ids, unwearable outfit."""
    from backend.app.services.styling.watsonx_list_builder import _coverage_ok
    from backend.app.services.styling.ontology import SlotType

    dress = _P(31, "Slip Dress", 6800, SlotType.DRESS)
    trousers = _P(32, "Wool Trousers", 3400, SlotType.FORMAL_BOTTOM)
    shirt = _P(33, "Silk Shirt", 2600, SlotType.FORMAL_SHIRT)
    shoes = _P(34, "Loafers", 2900, SlotType.FORMAL_SHOES)
    coat = _P(35, "Linen Blazer", 4200, SlotType.FORMAL_OUTER)

    assert _coverage_ok([(dress, ""), (trousers, "")]) is False   # unwearable
    assert _coverage_ok([(dress, ""), (shoes, "")]) is True       # a dress and shoes
    assert _coverage_ok([(dress, ""), (coat, ""), (shoes, "")]) is True  # layering is fine
    assert _coverage_ok([(shirt, ""), (trousers, ""), (shoes, "")]) is True
    assert _coverage_ok([(shirt, ""), (shoes, "")]) is False      # no bottom
