"""Contract tests for the live FX rate provider.

The rate table sits on the money path for BOTH display and settlement, so the
rules under test are mostly about failure: an external vendor must never be
able to take checkout down, mislabel an amount, or make CI depend on its
uptime.

No test here performs real network I/O — the transport is injected.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.services import fx_rates as fxmod
from backend.app.services.fx_rates import FxRateProvider, _parse_rate_table

LIVE_BODY = {
    "result": "success",
    "base_code": "USD",
    "time_last_update_utc": "Wed, 30 Sep 2026 00:02:31 +0000",
    "time_next_update_utc": "Thu, 01 Oct 2026 00:09:01 +0000",
    "rates": {"USD": 1, "EGP": 52.092039, "SAR": 3.75, "AED": 3.6725, "EUR": 0.88152},
}


@pytest.fixture
def provider(monkeypatch):
    """A provider with live fetching ENABLED and the transport stubbed."""
    monkeypatch.setenv("CONFIT_IGNORE_DOTENV", "0")
    monkeypatch.setattr("backend.app.core.config.settings.FX_LIVE_RATES_ENABLED", True, raising=False)
    monkeypatch.setattr("backend.app.core.config.settings.PRICING_CURRENCY", "USD", raising=False)
    monkeypatch.setattr("backend.app.core.config.settings.MARKET_FX_RATES", "", raising=False)
    return FxRateProvider()


def _stub_fetch(provider, body=None, fail=False, calls=None):
    """Replace the transport, keeping the production parse/validate path.

    ``fail=True`` models what the real ``_fetch`` does when the vendor is
    unreachable: it swallows the exception and returns ``None``. That contract
    is asserted separately in
    ``test_real_fetch_swallows_transport_errors``.
    """
    import time as _t

    from backend.app.services.fx_rates import RateSnapshot

    def _fetch(base):
        if calls is not None:
            calls.append(base)
        if fail:
            return None
        if not isinstance(body, dict) or body.get("result") != "success":
            return None
        table = _parse_rate_table(body.get("rates"), "live")
        if not table or table.get(body.get("base_code", base).upper()) != Decimal("1"):
            return None
        return RateSnapshot(base=base, rates=table, source="live",
                            as_of=body.get("time_last_update_utc"),
                            next_update=body.get("time_next_update_utc"),
                            fetched_at=_t.monotonic())

    provider._fetch = _fetch  # type: ignore[assignment]


# ── happy path ───────────────────────────────────────────────────────────────

def test_live_rates_are_served_with_provenance(provider):
    _stub_fetch(provider, LIVE_BODY)
    snap = provider.snapshot()
    assert snap.source == "live"
    assert snap.rates["EGP"] == Decimal("52.092039")
    assert snap.as_of == "Wed, 30 Sep 2026 00:02:31 +0000"
    # 166 currencies upstream; the point is that it is not limited to the
    # eight registry markets.
    assert "EUR" in snap.rates


def test_second_call_is_served_from_cache(provider):
    calls = []
    _stub_fetch(provider, LIVE_BODY, calls=calls)
    provider.snapshot()
    provider.snapshot()
    provider.snapshot()
    assert len(calls) == 1, "TTL cache must not re-dial on every request"


# ── failure must degrade, never raise ────────────────────────────────────────

def test_upstream_failure_falls_back_to_the_configured_table(provider, monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.MARKET_FX_RATES",
                        '{"EGP": "48.5"}', raising=False)
    _stub_fetch(provider, fail=True)
    snap = provider.snapshot()
    assert snap.source == "configured"
    assert snap.rates["EGP"] == Decimal("48.5")


def test_upstream_failure_with_no_configured_table_is_reported_empty(provider):
    _stub_fetch(provider, fail=True)
    snap = provider.snapshot()
    assert snap.source == "unavailable"
    assert snap.rates == {}
    # Upstream, an empty table means "settle in the price-book currency",
    # which is the honest degradation — not a crash.


def test_a_previously_good_snapshot_survives_an_outage_as_stale(provider, monkeypatch):
    _stub_fetch(provider, LIVE_BODY)
    assert provider.snapshot().source == "live"
    monkeypatch.setattr("backend.app.core.config.settings.FX_RATE_TTL_SECONDS", 60, raising=False)
    provider._cached = provider._cached.__class__(  # force expiry
        base=provider._cached.base, rates=provider._cached.rates, source="live",
        as_of=provider._cached.as_of, next_update=provider._cached.next_update,
        fetched_at=0.0,
    )
    _stub_fetch(provider, fail=True)
    snap = provider.snapshot()
    assert snap.source == "stale_live", "real-but-old numbers beat no numbers, and say so"
    assert snap.rates["EGP"] == Decimal("52.092039")


def test_a_dead_upstream_is_not_re_dialled_on_every_request(provider):
    calls = []
    _stub_fetch(provider, fail=True, calls=calls)
    for _ in range(5):
        provider.snapshot()
    assert len(calls) == 1, "an outage must not become our latency problem"


# ── payload validation ───────────────────────────────────────────────────────

def test_a_payload_whose_base_is_not_1_is_rejected(provider):
    bad = dict(LIVE_BODY, rates={"USD": 0.97, "EGP": 50})
    _stub_fetch(provider, bad)
    assert provider.snapshot().source == "unavailable", (
        "a table not denominated in the base we asked for would skew every "
        "conversion; it must be refused, not used"
    )


def test_result_error_is_rejected(provider):
    _stub_fetch(provider, dict(LIVE_BODY, result="error"))
    assert provider.snapshot().source == "unavailable"


def test_real_fetch_swallows_transport_errors(provider, monkeypatch):
    """The production transport must degrade, never propagate — money
    resolution is on the checkout critical path."""
    class _Boom:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): raise OSError("dns failure")

    import httpx
    monkeypatch.setattr(httpx, "Client", _Boom)
    assert provider._fetch("USD") is None      # no exception escapes
    assert provider.snapshot().source == "unavailable"


@pytest.mark.parametrize("value", ["abc", -1, 0, float("nan"), None])
def test_invalid_entries_are_dropped_never_treated_as_one(value):
    table = _parse_rate_table({"EGP": value, "SAR": "3.75"}, "test")
    assert "EGP" not in table, "a bad rate must be dropped, never defaulted to 1.0"
    assert table["SAR"] == Decimal("3.75")


def test_non_iso_keys_are_ignored():
    table = _parse_rate_table({"E": 1, "EGPP": 2, "1EG": 3, "EGP": "52.09"}, "test")
    assert list(table) == ["EGP"]


# ── test hermeticity ─────────────────────────────────────────────────────────

def test_live_fetching_is_disabled_under_the_hermetic_test_contract(monkeypatch):
    """CONFIT_IGNORE_DOTENV=1 is set by conftest. CI must not depend on an
    external vendor being up."""
    monkeypatch.setenv("CONFIT_IGNORE_DOTENV", "1")
    assert FxRateProvider._live_enabled() is False


def test_kill_switch_pins_the_storefront_to_the_static_table(monkeypatch):
    monkeypatch.setenv("CONFIT_IGNORE_DOTENV", "0")
    monkeypatch.setattr("backend.app.core.config.settings.FX_LIVE_RATES_ENABLED", False, raising=False)
    assert FxRateProvider._live_enabled() is False


# ── single-authority guarantee ───────────────────────────────────────────────

def test_settlement_and_presentation_read_the_same_table(monkeypatch):
    """The lesson from the 2026-09-30 double-conversion incident: one snapshot
    for display AND settlement, or the storefront can disagree with checkout."""
    from backend.app.providers.payment.capability_registry import (
        MarketPaymentCapabilityRegistry as Registry,
    )
    from backend.app.services.pricing_presentation import rate_snapshot

    monkeypatch.setattr(fxmod.fx_rates, "rates", lambda: {"EGP": Decimal("52.0")})
    monkeypatch.setattr(
        fxmod.fx_rates, "snapshot",
        lambda: fxmod.RateSnapshot(base="USD", rates={"EGP": Decimal("52.0")}, source="live"),
    )
    assert Registry.fx_rates()["EGP"] == Decimal("52.0")
    assert rate_snapshot().rates["EGP"] == Decimal("52.0")
