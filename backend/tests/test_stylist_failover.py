"""Provider failover through the NVIDIA registry chain — FR-005, SC-003, STY-04.

The stylist text chain is ``registry.ModelRole.STYLIST_CHAT``: primary, then each
failover. These tests drive the REAL orchestrator and the REAL NVIDIA client; only
the HTTP transport is replaced, so the failure modes are the ones production sees.

Pinned behaviour
----------------
* a failing primary falls through to the next registry candidate, and the answer
  is attributed to the model that actually served it;
* when every NVIDIA candidate fails, the orchestrator moves to the next configured
  provider, and if none answer, the answer is the deterministic grounded engine,
  labelled as such — never a generated answer under a provider's name;
* a capacity error (503) rotates to the next model, not into a retry storm.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.app.core.config import settings
from backend.app.providers.nvidia import ModelRole, get_chain, key_pool
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator

PRIMARY = get_chain(ModelRole.STYLIST_CHAT)[0].model_id
FAILOVER = get_chain(ModelRole.STYLIST_CHAT)[1].model_id
GOOD = "Pair the Arket linen shirt with cream trousers for a calm, polished evening."
DETERMINISTIC_LABEL = "CONFIT Grounded Styling Engine (Grounded & Resilient)"


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _NvidiaTransport:
    """Scripted NVIDIA endpoint. ``behaviour[model]`` is a status code or a text."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.served_models = []   # every model id the client actually requested
        self.calls = 0

    def __call__(self, *args, **kwargs):
        outer = self

        class _Client:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def post(self_inner, url, headers=None, json=None):
                outer.calls += 1
                model = (json or {}).get("model")
                outer.served_models.append(model)
                step = outer.behaviour.get(model, 503)
                if isinstance(step, int):
                    return _Resp(step, {"error": "scripted failure"})
                return _Resp(200, {
                    "model": model,
                    "choices": [{"message": {"content": step}, "finish_reason": "stop"}],
                })

        return _Client()


@pytest.fixture
def nvidia_configured(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-not-a-real-key")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "nvapi-test-not-a-real-key", raising=False)
    monkeypatch.setattr(settings, "AI_PROVIDERS", "nvidia")
    key_pool.reload()
    yield
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", None, raising=False)
    key_pool.reload()


async def _advise(orch=None):
    orch = orch or MultiProviderAIOrchestrator()
    return await orch.generate_styling_advice(
        prompt="smart casual dinner",
        selected_outfit={"items": [
            {"position": "top", "product_title": "Linen Shirt", "brand_name": "Arket", "color_family": "white", "price": 90},
        ], "total_price": 90, "color_palette": ["#FFFFFF"]},
        intent={"occasion": "Smart Casual", "style_source": "default"},
    )


@pytest.mark.asyncio
async def test_registry_chain_is_walked_in_order_when_primary_fails(nvidia_configured):
    transport = _NvidiaTransport({PRIMARY: 503, FAILOVER: GOOD})
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        result = await _advise()
    assert transport.served_models[:2] == [PRIMARY, FAILOVER], "primary first, then the registry failover"
    assert result["provider_used"] == f"NVIDIA {FAILOVER}", "attribution names the model that served"
    assert result["styling_advice_text"] == GOOD


@pytest.mark.asyncio
async def test_primary_success_does_not_touch_the_failover(nvidia_configured):
    transport = _NvidiaTransport({PRIMARY: GOOD, FAILOVER: "should not be used"})
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        result = await _advise()
    assert transport.served_models == [PRIMARY]
    assert result["provider_used"] == f"NVIDIA {PRIMARY}"


@pytest.mark.asyncio
async def test_total_nvidia_failure_degrades_to_deterministic_engine_honestly(nvidia_configured):
    transport = _NvidiaTransport({m.model_id: 503 for m in get_chain(ModelRole.STYLIST_CHAT)})
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        result = await _advise()
    assert result["provider_used"] == DETERMINISTIC_LABEL
    assert not result["provider_used"].startswith("NVIDIA"), "a failed provider must not be credited"
    assert result["styling_advice_text"], "the honest deterministic reply is still a reply"


@pytest.mark.asyncio
async def test_empty_primary_answer_is_a_failure_not_an_answer(nvidia_configured):
    transport = _NvidiaTransport({PRIMARY: "   ", FAILOVER: GOOD})
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        result = await _advise()
    assert result["provider_used"] == f"NVIDIA {FAILOVER}"
    assert result["styling_advice_text"] == GOOD


@pytest.mark.asyncio
async def test_capacity_error_rotates_model_without_retry_storm(nvidia_configured):
    transport = _NvidiaTransport({PRIMARY: 429, FAILOVER: GOOD})
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        await _advise()
    # One attempt per model: the stylist budget does not stack key rotations.
    assert transport.served_models.count(PRIMARY) == 1


@pytest.mark.asyncio
async def test_every_registry_candidate_is_reachable(nvidia_configured):
    chain = [m.model_id for m in get_chain(ModelRole.STYLIST_CHAT)]
    transport = _NvidiaTransport({m: 503 for m in chain})
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        await _advise()
    assert transport.served_models[: len(chain)] == chain, "STY-04: the whole chain is traversed"


@pytest.mark.asyncio
async def test_extra_context_is_appended_to_the_user_turn(nvidia_configured):
    transport = _NvidiaTransport({PRIMARY: GOOD})
    orch = MultiProviderAIOrchestrator()
    captured = {}
    original = orch._call_nvidia_chain

    async def spy(system_prompt, user_prompt):
        captured["user"] = user_prompt
        return await original(system_prompt, user_prompt)

    orch._call_nvidia_chain = spy
    with patch("backend.app.providers.nvidia.client.httpx.AsyncClient", transport):
        await orch.generate_styling_advice(
            prompt="dinner", selected_outfit=None, intent={"occasion": "Smart Casual"},
            extra_context="Dominant colours in the shopper's photo(s): navy.",
        )
    assert "Verified context" in captured["user"]
    assert "navy" in captured["user"]
