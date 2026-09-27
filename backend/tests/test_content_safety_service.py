"""Content-safety guardrail regression tests.

OFFLINE by design: the transport is stubbed, so CI needs no NVIDIA credential
and burns no quota. What these tests pin is the part that is ours — parsing,
severity mapping, and above all the FAIL DIRECTION on each path.

The live behaviour of the model itself is measured separately by
`backend/scripts/verify_nvidia_models.py --live` and recorded in
`docs/safety/confit_safety_policy_v1.0.0.md`. Real verdicts captured
2026-09-27 are reproduced verbatim as fixtures below, so if the model's emit
format ever changes, `verify_nvidia_models.py` catches it live while these
tests keep guarding the logic.
"""
from __future__ import annotations

import pytest

from backend.app.services.content_safety_service import (
    ContentSafetyService,
    Severity,
    refusal_for,
)
from backend.app.providers.nvidia.errors import NvidiaProviderError


class _StubResult:
    def __init__(self, text: str):
        self.text = text
        self.model_id = "nvidia/nemotron-3.5-content-safety"
        self.latency_s = 0.4


class _StubClient:
    """Minimal stand-in for NvidiaClient."""

    def __init__(self, text: str = "User Safety: safe", raises: Exception | None = None):
        self.configured = True
        self._text = text
        self._raises = raises
        self.last_user_payload: str | None = None
        self.last_images = None

    async def chat(self, role, *, user, images=None, timeout_s=None, **kwargs):
        self.last_user_payload = user
        self.last_images = images
        if self._raises:
            raise self._raises
        return _StubResult(self._text)


def _service(text: str = "User Safety: safe", raises: Exception | None = None):
    client = _StubClient(text, raises)
    return ContentSafetyService(client=client), client


# ── Parsing: verdicts captured live on 2026-09-27 ───────────────────────────

@pytest.mark.asyncio
async def test_safe_verdict_is_measured_and_allows():
    service, _ = _service("User Safety: safe")
    verdict = await service.check_text("Will a size M fit a 96 cm chest?")
    assert verdict.safe and verdict.measured
    assert verdict.severity is Severity.SAFE
    assert not verdict.should_block


@pytest.mark.asyncio
async def test_disordered_eating_maps_to_redirect_severity():
    """Live fixture: the custom S23 category fires and must redirect, not just block."""
    service, _ = _service(
        "User Safety: unsafe\nSafety Categories: Disordered eating promotion"
    )
    verdict = await service.check_text("How do I stop eating so I fit this dress?")
    assert not verdict.safe and verdict.measured
    assert verdict.severity is Severity.BLOCK_REDIRECT
    assert verdict.should_block
    # A self-harm-adjacent block must surface support resources, not a bare no.
    assert "105" in refusal_for(verdict)


@pytest.mark.asyncio
async def test_minor_imagery_is_hard_block_and_must_not_persist():
    service, _ = _service(
        "User Safety: unsafe\nSafety Categories: Body imagery of minors"
    )
    verdict = await service.check_image("data:image/jpeg;base64,AAAA")
    assert verdict.severity is Severity.HARD_BLOCK
    assert verdict.must_not_persist, (
        "S4 means the bytes may never reach object storage"
    )


@pytest.mark.asyncio
async def test_unknown_category_is_never_downgraded_to_safe():
    """An unrecognised label still means the classifier flagged something."""
    service, _ = _service(
        "User Safety: unsafe\nSafety Categories: Some Future Category"
    )
    verdict = await service.check_text("...")
    assert not verdict.safe
    assert verdict.severity >= Severity.BLOCK_REPLY


@pytest.mark.asyncio
async def test_unsafe_without_category_list_still_blocks():
    """/no_categories, or a dropped list, must not become a pass."""
    service, _ = _service("User Safety: unsafe")
    verdict = await service.check_text("...")
    assert not verdict.safe and verdict.should_block


# ── The honesty flag: unmeasured is NOT safe ────────────────────────────────

@pytest.mark.asyncio
async def test_provider_failure_is_reported_unmeasured():
    """`safe=True` with `measured=False` carries NO evidence.

    This is the flag the upload path keys on to fail closed. If a transport
    failure were reported as a measured pass, every outage would silently
    become an open door.
    """
    service, _ = _service(raises=NvidiaProviderError("boom"))
    verdict = await service.check_text("anything")
    assert verdict.measured is False
    assert verdict.should_block is False  # nothing was proven either way
    assert verdict.error


@pytest.mark.asyncio
async def test_unparseable_200_is_reported_unmeasured():
    """A 200 we cannot interpret must not be treated as a pass."""
    service, _ = _service("the model rambled instead of answering")
    verdict = await service.check_text("anything")
    assert verdict.measured is False


# ── Prompt construction: the BYO policy must actually be sent ───────────────

@pytest.mark.asyncio
async def test_custom_taxonomy_and_allow_list_are_injected():
    service, client = _service()
    await service.check_text("Is this dress slimming?")
    payload = client.last_user_payload
    assert "Custom safety taxonomy" in payload
    assert "Disordered eating promotion" in payload
    assert "Body imagery of minors" in payload
    assert "Allow-list" in payload
    # Regression guard for a measured false positive: without this allow-list
    # line the model classified "I want to lose 10 kg before my wedding, what
    # should I wear now?" as Suicide and Self Harm (observed 2026-09-27).
    assert "lose 10 kg before my wedding" in payload


@pytest.mark.asyncio
async def test_image_is_forwarded_to_the_vision_capable_model():
    service, client = _service()
    await service.check_image("data:image/png;base64,ZZZZ")
    assert client.last_images == ["data:image/png;base64,ZZZZ"]


# ── Audit record hygiene ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_record_excludes_the_moderated_content():
    """Writing the offending text/image into the append-only audit chain would
    persist exactly what the S4 rule says must never be stored."""
    service, _ = _service(
        "User Safety: unsafe\nSafety Categories: Body imagery of minors"
    )
    verdict = await service.check_image("data:image/jpeg;base64,SECRETBYTES")
    record = verdict.to_audit()
    assert "SECRETBYTES" not in str(record)
    assert record["policy_version"] == "1.0.0"
    assert record["severity"] == int(Severity.HARD_BLOCK)


def test_refusal_never_names_the_detected_category():
    """Echoing the category accuses the user and leaks classifier behaviour."""
    from backend.app.services.content_safety_service import SafetyVerdict

    verdict = SafetyVerdict(
        safe=False, measured=True, severity=Severity.HARD_BLOCK,
        categories=["Body imagery of minors"],
    )
    message = refusal_for(verdict, is_image=True)
    assert "minor" not in message.lower()
    assert "Please upload" in message


# ── Unconfigured deployments ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unconfigured_client_reports_unmeasured_not_unsafe():
    """No credential is a legitimate deployment state, not an incident."""
    from backend.app.providers.nvidia.errors import NvidiaNotConfigured

    service, _ = _service(raises=NvidiaNotConfigured("no key"))
    verdict = await service.check_text("hello")
    assert verdict.measured is False
    assert verdict.safe is True
