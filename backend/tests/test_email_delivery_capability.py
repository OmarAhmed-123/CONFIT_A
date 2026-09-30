"""The readiness contract must not stay silent about a dead recovery path.

FOUND BY LIVE PRODUCTION TESTING, 2026-09-30
`POST /auth/forgot-password` returns HTTP 501 FEATURE_NOT_CONFIGURED
(email_delivery) on production: EMAIL_PROVIDER is set for the preview
environment only and no SMTP_* variables exist. A locked-out user cannot
recover their account.

The 501 is correct — the platform refuses rather than faking a queued mail.
The defect was one level up: `capability_probes` covered database, uploads,
payments, try-on, stylist, BNPL and click-and-collect, and said NOTHING about
email. `/api/v1/health` therefore reported only
`degraded_capabilities: [buy_now_pay_later, payments]` while account recovery
was entirely dead. A capability that is never probed cannot be missed.
"""
from __future__ import annotations

import pytest

from backend.app.core.readiness import (
    CRITICALITY_SUPPORTING,
    STATE_BLOCKED,
    STATE_READY,
    summarise_capabilities,
)
from backend.app.services.capability_service import _email_delivery_capability


def _set(monkeypatch, **kw):
    for key, value in kw.items():
        monkeypatch.setattr(f"backend.app.core.config.settings.{key}", value, raising=False)


def test_unconfigured_email_is_reported_blocked(monkeypatch):
    _set(monkeypatch, EMAIL_PROVIDER=None)
    cap = _email_delivery_capability()
    assert cap.name == "email_delivery"
    assert cap.state == STATE_BLOCKED


def test_the_detail_names_the_variables_an_operator_must_set(monkeypatch):
    """A blocked capability whose detail does not say how to unblock it is a
    status light, not a diagnostic."""
    _set(monkeypatch, EMAIL_PROVIDER=None)
    detail = _email_delivery_capability().detail
    for var in ("EMAIL_PROVIDER", "SMTP_HOST", "EMAIL_FROM_ADDRESS"):
        assert var in detail
    assert "password reset" in detail.lower()


def test_blocked_email_surfaces_in_degraded_not_silently(monkeypatch):
    """The whole point: it must appear in the health payload."""
    _set(monkeypatch, EMAIL_PROVIDER=None)
    summary = summarise_capabilities([_email_delivery_capability()])
    assert "email_delivery" in summary["degraded_capabilities"]
    assert "email_delivery" in summary["capabilities"]


def test_it_is_supporting_so_it_does_not_flip_readiness(monkeypatch):
    """A deliberate, documented call: browsing and buying still work without
    email, and `core` is reserved for "cannot deliver the product at all"."""
    _set(monkeypatch, EMAIL_PROVIDER=None)
    cap = _email_delivery_capability()
    assert cap.criticality == CRITICALITY_SUPPORTING
    assert summarise_capabilities([cap])["ready"] is True


def test_configured_email_is_ready_but_labelled_not_delivery_verified(monkeypatch):
    _set(monkeypatch, EMAIL_PROVIDER="smtp", SMTP_HOST="smtp.example.test",
         EMAIL_FROM_ADDRESS="no-reply@example.test")
    cap = _email_delivery_capability()
    assert cap.state == STATE_READY
    # Configured != proven. Claiming "delivering" without a send would be the
    # exact overstatement this contract exists to prevent.
    assert "not delivery-verified" in cap.detail


@pytest.mark.parametrize("missing", ["SMTP_HOST", "EMAIL_FROM_ADDRESS"])
def test_half_configured_email_is_blocked_and_says_which_half(monkeypatch, missing):
    _set(monkeypatch, EMAIL_PROVIDER="smtp", SMTP_HOST="smtp.example.test",
         EMAIL_FROM_ADDRESS="no-reply@example.test")
    _set(monkeypatch, **{missing: ""})
    cap = _email_delivery_capability()
    assert cap.state == STATE_BLOCKED
    assert missing in cap.detail


def test_email_delivery_is_actually_wired_into_the_probe_list():
    """Guard against the probe existing but never being called — which is the
    shape of the original defect."""
    import inspect

    from backend.app.services import capability_service

    source = inspect.getsource(capability_service.capability_probes)
    assert "_email_delivery_capability()" in source
