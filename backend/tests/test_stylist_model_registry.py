"""Model IDs are centrally declared, validated and documented — FR-010, STY-16.

The stylist may only call models that exist in the NVIDIA registry, the vision
chain may only contain vision-capable models, and the routing document must name
every model the registry routes to. The routing report must never expose a key.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.app.providers.nvidia import ModelRole, find_spec, get_chain
from backend.app.services.stylist_vision import stylist_model_routing_report

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "STYLIST_MODEL_ROUTING.md"


def test_every_stylist_text_model_is_registered():
    for spec in get_chain(ModelRole.STYLIST_CHAT):
        assert find_spec(spec.model_id) is not None


def test_vision_chain_contains_only_vision_capable_models():
    chain = get_chain(ModelRole.GARMENT_VISION)
    assert chain, "the stylist vision role must have at least one candidate"
    for spec in chain:
        assert spec.supports_vision, f"{spec.model_id} is routed for images but is not vision-capable"


def test_routing_document_names_every_routed_stylist_model():
    assert DOC.exists(), "docs/STYLIST_MODEL_ROUTING.md must document the stylist routing"
    text = DOC.read_text(encoding="utf-8")
    for role in (ModelRole.STYLIST_CHAT, ModelRole.GARMENT_VISION):
        for spec in get_chain(role):
            assert spec.model_id in text, f"{spec.model_id} is routed but undocumented"


def test_routing_report_never_contains_a_credential(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-SECRET-VALUE-DO-NOT-LEAK")
    report = stylist_model_routing_report()
    blob = repr(report)
    assert "SECRET-VALUE" not in blob
    assert not re.search(r"nvapi-[A-Za-z0-9_-]{8,}", blob)
    assert report["stylist_text"][0]["model_id"] == get_chain(ModelRole.STYLIST_CHAT)[0].model_id
    assert all("supports_vision" in row for row in report["stylist_vision"])
