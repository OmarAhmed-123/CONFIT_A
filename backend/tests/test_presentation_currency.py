"""Contract tests for multi-currency presentation.

The defect these lock down was measured on production 2026-09-30:
``GET /commerce/payment-methods`` said ``EGP`` for market EG while
``GET /commerce/cart`` returned ``"currency": "USD"`` for the same shopper,
and the catalogue served raw price-book numbers labelled USD. A 289.00 shown
as "$289" but charged as "EGP 289" is a ~48x error, so every rule here is
about the LABEL and the NUMBERS agreeing — or the request honestly reporting
that it could not honour the choice.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.services import pricing_presentation as pp
from backend.app.services.pricing_presentation import (
    present,
    presentation_meta,
    resolve_presentation,
    supported_currencies,
)

RATES = '{"EGP": "48.5", "SAR": "3.75", "AED": "3.6725", "QAR": "3.64", "KWD": "0.307"}'


@pytest.fixture
def rates(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.MARKET_FX_RATES", RATES, raising=False)
    monkeypatch.setattr("backend.app.core.config.settings.PRICING_CURRENCY", "USD", raising=False)


@pytest.fixture
def no_rates(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.MARKET_FX_RATES", "", raising=False)
    monkeypatch.setattr("backend.app.core.config.settings.PRICING_CURRENCY", "USD", raising=False)


# ── resolution ───────────────────────────────────────────────────────────────

def test_explicit_choice_is_honoured(rates):
    r = resolve_presentation("EGP")
    assert (r.code, r.converted, r.rate) == ("EGP", True, Decimal("48.5"))
    assert presentation_meta(r)["honoured"] is True


def test_pricing_currency_choice_is_an_exact_noop(rates):
    r = resolve_presentation("USD")
    assert r.code == "USD" and r.is_noop and r.rate == Decimal("1")


def test_market_default_applies_without_an_explicit_choice(rates):
    assert resolve_presentation(None, "EG").code == "EGP"
    assert resolve_presentation(None, "SA").code == "SAR"
    # Country aliases resolve through the same market authority, not a
    # second lookup table.
    assert resolve_presentation(None, "UAE").code == "AED"


def test_unrated_currency_is_refused_not_faked(rates):
    """The dangerous case: offering a currency we cannot convert into."""
    r = resolve_presentation("JPY", "EG")
    assert r.code != "JPY"
    meta = presentation_meta(r)
    assert meta["honoured"] is False
    assert meta["requested_currency"] == "JPY"
    assert r.reason == "requested_currency_unavailable"


def test_no_configured_rate_falls_back_to_the_price_book(no_rates):
    """Without a rate, EGP labelling would be a 48x lie — so we stay in USD."""
    r = resolve_presentation(None, "EG")
    assert r.code == "USD" and r.is_noop
    assert r.reason == "fx_rate_not_configured"


def test_supported_currencies_reports_availability_truthfully(rates):
    by_code = {c["currency"]: c for c in supported_currencies()}
    assert by_code["EGP"]["available"] is True
    assert by_code["USD"]["is_pricing_currency"] is True
    # OMR/BHD are registry markets with no configured rate today.
    assert by_code["OMR"]["available"] is False
    assert by_code["OMR"]["rate_from_pricing_currency"] is None


# ── conversion ───────────────────────────────────────────────────────────────

def test_money_fields_convert_and_label_follows(rates):
    fx = resolve_presentation("EGP")
    out = present({"base_price": 289.0, "compare_at_price": 412.86, "currency": "USD"}, fx)
    assert out["base_price"] == 14016.50      # 289.00 * 48.5
    assert out["compare_at_price"] == 20023.71
    assert out["currency"] == "EGP"


def test_non_money_numbers_are_never_touched(rates):
    """The reason MONEY_FIELDS is an allowlist and not a name heuristic."""
    fx = resolve_presentation("EGP")
    out = present(
        {"rating": 4.5, "ai_fit_score": 92, "stock_level": 7, "size": "42", "base_price": 10.0},
        fx,
    )
    assert out["rating"] == 4.5
    assert out["ai_fit_score"] == 92
    assert out["stock_level"] == 7
    assert out["size"] == "42"
    assert out["base_price"] == 485.0


def test_none_price_stays_none(rates):
    """A missing prior price must not become a free product."""
    fx = resolve_presentation("EGP")
    assert present({"compare_at_price": None}, fx)["compare_at_price"] is None


def test_nested_and_list_payloads_convert_all_the_way_down(rates):
    fx = resolve_presentation("SAR")
    payload = {
        "currency": "USD",
        "subtotal": 100.0,
        "items": [
            {"unit_price": 20.0, "subtotal": 40.0, "currency": "USD",
             "meta": {"original_price": 25.0}},
        ],
        "price_range": {"min_price": 10.0, "max_price": 90.0, "avg_price": 50.0},
    }
    out = present(payload, fx)
    assert out["subtotal"] == 375.0
    assert out["items"][0]["unit_price"] == 75.0
    assert out["items"][0]["meta"]["original_price"] == 93.75
    assert out["items"][0]["currency"] == "SAR"
    assert out["price_range"]["max_price"] == 337.5


def test_noop_presentation_does_not_perturb_a_single_value(no_rates):
    fx = resolve_presentation(None, "US")
    payload = {"base_price": 289.99, "subtotal": 1234.56, "currency": "USD"}
    assert present(payload, fx) == payload


def test_inbound_filters_are_converted_back_to_the_price_book(rates):
    """A shopper browsing in EGP who filters "under 5000" means EGP 5000."""
    fx = resolve_presentation("EGP")
    assert fx.to_pricing(5000) == pytest.approx(103.09, abs=0.01)
    assert fx.to_pricing(None) is None


def test_round_trip_is_stable_within_the_money_scale(rates):
    fx = resolve_presentation("AED")
    assert fx.to_pricing(fx.convert(100.0)) == pytest.approx(100.0, abs=0.01)


def test_booleans_are_not_mistaken_for_amounts(rates):
    fx = resolve_presentation("EGP")
    # `total` is in MONEY_FIELDS; a bool there would be a schema bug, and
    # silently multiplying True by 48.5 would hide it.
    assert present({"total": True}, fx)["total"] is True


# ── declared-field completeness ──────────────────────────────────────────────

def test_cart_schema_money_fields_are_all_declared():
    """A new money field added to CartOut without registering it here would
    render unconverted next to converted siblings. Catch it at test time."""
    from backend.app.schemas.commerce import CartOut

    money_like = {
        name for name in CartOut.model_fields
        if any(tok in name for tok in ("price", "total", "amount", "subtotal", "quote"))
    }
    missing = money_like - pp.MONEY_FIELDS
    assert not missing, f"money fields not registered in MONEY_FIELDS: {sorted(missing)}"


def test_product_schema_money_fields_are_all_declared():
    from backend.app.schemas.catalog import ProductSummaryOut

    money_like = {
        name for name in ProductSummaryOut.model_fields
        if any(tok in name for tok in ("price", "total", "amount"))
    }
    missing = money_like - pp.MONEY_FIELDS
    assert not missing, f"money fields not registered in MONEY_FIELDS: {sorted(missing)}"
