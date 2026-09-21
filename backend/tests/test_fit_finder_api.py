"""API-level tests for the Fit Finder endpoints against the real app.

The engine's maths is covered by ``test_fit_engine_acceptance.py`` (pure, no
DB). This file proves the *wiring*: the routes exist, the contract matches the
schema, units are handled at the boundary, product/inventory state reaches the
engine, refusals surface as honest 200s, invalid measurements are 422s, and the
measurement-session → profile path the frontend has always called actually
works.

Audit reference: "لم أشغّل توصية بمقاسات حقيقية لأن الحسابات تبدأ بملف فارغ" —
the auditor could not exercise a real recommendation without polluting the
production database. These tests do it against the seeded test database, so the
computation is now demonstrated end-to-end rather than assumed.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.catalog import Product, ProductSKU
from backend.tests.conftest import TestingSessionLocal as SessionLocal

API = "/api/v1"
FIT_ROUTES = [
    f"{API}/tryon/no-photo-fit",
    f"{API}/try-on/no-photo-fit",
    f"{API}/tryon/fit/recommend",
    f"{API}/try-on/fit/recommend",
    f"{API}/fit/recommend",
]
MEAS = f"{API}/measurements/sessions"
PW = "Sec!Test#Pass2026x9"

BODY = {
    "units": "metric",
    "height": 178,
    "weight": 78,
    "chest": 102,
    "waist": 88,
    "hip": 104,
    "preferred_fit": "regular",
}

CHART = {
    "unit": "cm",
    "measurement_type": "body",
    "updated_at": "2026-06-01",
    "rows": [
        {"size": "S", "chest": [90, 98], "waist": [76, 84], "hip": [92, 100]},
        {"size": "M", "chest": [98, 106], "waist": [84, 92], "hip": [100, 108]},
        {"size": "L", "chest": [106, 114], "waist": [92, 100], "hip": [108, 116]},
    ],
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def charted_product():
    """A DEDICATED product with a known chart and known stock.

    Deliberately creates its own product instead of mutating a seeded one:
    an earlier version of this fixture edited seed product #1's SKUs and the
    restore was not perfect, which broke unrelated search-ranking and
    inventory-invariant tests whenever the suite ran in full. Tests must not
    leave the shared fixture database different from how they found it.
    """
    with SessionLocal() as db:
        template = db.query(Product).first()
        assert template is not None, "seed data missing"
        marker = uuid.uuid4().hex[:10]
        product = Product(
            brand_id=template.brand_id,
            category_id=template.category_id,
            title=f"Fit Engine Test Garment {marker}",
            title_ar=f"قطعة اختبار {marker}",
            slug=f"fit-engine-test-garment-{marker}",
            description="Fixture product owned by test_fit_finder_api.py.",
            description_ar="منتج اختباري.",
            base_price=100,
            currency="USD",
            material="100% cotton poplin",
            color_family="Navy Blue",
            thumbnail_url="https://example.invalid/fixture.jpg",
            style_tags=json.dumps(["shirt"]),
            occasion_tags=json.dumps(["work"]),
            images=json.dumps([]),
            size_chart_json=json.dumps(CHART),
            is_active=True,
        )
        db.add(product)
        db.flush()
        pid = product.id
        for size in ("S", "M", "L"):
            db.add(
                ProductSKU(
                    product_id=pid,
                    sku_code=f"FITTEST-{marker}-{size}",
                    size=size,
                    color="Test",
                    stock_level=7,
                    is_in_stock=True,
                )
            )
        db.commit()

    yield pid

    with SessionLocal() as db:
        db.query(ProductSKU).filter(ProductSKU.product_id == pid).delete()
        db.query(Product).filter(Product.id == pid).delete()
        db.commit()


def _register(client: TestClient, name: str) -> dict:
    email = f"fit.{name}.{uuid.uuid4().hex[:10]}@fittest.dev"
    res = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": PW, "full_name": name, "role": "consumer"},
    )
    assert res.status_code == 201, res.text
    login = client.post(f"{API}/auth/login", json={"email": email, "password": PW})
    assert login.status_code == 200, login.text
    return {
        "token": login.json()["access_token"],
        "id": res.json()["user"]["id"],
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


# ── routing ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("route", FIT_ROUTES)
def test_every_documented_fit_route_computes(client, charted_product, route):
    res = client.post(route, json={"product_id": charted_product, **BODY})
    assert res.status_code == 200, f"{route}: {res.text}"
    body = res.json()
    assert body["recommended"] is True
    assert body["recommended_size"] == "M", body


def test_all_routes_agree(client, charted_product):
    payload = {"product_id": charted_product, **BODY}
    answers = {
        client.post(route, json=payload).json()["recommended_size"] for route in FIT_ROUTES
    }
    assert len(answers) == 1, answers


# ── the recommendation is computed from the product's real data ────────────
def test_recommendation_uses_the_products_own_chart(client, charted_product):
    res = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY})
    body = res.json()
    assert body["size_chart_source"]["source"] == "brand_published"
    assert body["size_chart_source"]["is_brand_published"] is True
    assert body["size_chart_source"]["updated_at"] == "2026-06-01"
    # The ranges shown must be the ones we stored, not a hardcoded table.
    row = next(r for r in body["size_comparison_table"] if r["size"] == "M")
    assert row["ranges_cm"]["chest"] == [98.0, 106.0]


def test_changing_the_chart_changes_the_answer(client, charted_product):
    """The strongest proof that the chart is actually read."""
    before = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).json()

    shifted = {
        "unit": "cm",
        "measurement_type": "body",
        "updated_at": "2026-06-02",
        "rows": [
            {"size": "S", "chest": [70, 78], "waist": [56, 64], "hip": [72, 80]},
            {"size": "M", "chest": [78, 86], "waist": [64, 72], "hip": [80, 88]},
            {"size": "L", "chest": [86, 94], "waist": [72, 80], "hip": [88, 96]},
        ],
    }
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == charted_product).first()
        p.size_chart_json = json.dumps(shifted)
        db.commit()

    after = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).json()

    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == charted_product).first()
        p.size_chart_json = json.dumps(CHART)
        db.commit()

    assert before["recommended_size"] == "M"
    # Against a chart that runs far smaller, the same body cannot still be M.
    assert after["recommended_size"] != "M" or after["recommended"] is False


def test_out_of_stock_size_is_never_recommended(client, charted_product):
    with SessionLocal() as db:
        sku = (
            db.query(ProductSKU)
            .filter(ProductSKU.product_id == charted_product, ProductSKU.size == "M")
            .first()
        )
        sku.stock_level = 0
        sku.is_in_stock = False
        db.commit()

    res = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).json()

    with SessionLocal() as db:
        sku = (
            db.query(ProductSKU)
            .filter(ProductSKU.product_id == charted_product, ProductSKU.size == "M")
            .first()
        )
        sku.stock_level = 7
        sku.is_in_stock = True
        db.commit()

    if res["recommended"]:
        assert res["recommended_size"] != "M", res
        recommended_row = next(
            r for r in res["size_comparison_table"] if r["is_recommended"]
        )
        assert recommended_row["in_stock"] is True


def test_no_chart_and_no_mappable_size_refuses(client, charted_product):
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == charted_product).first()
        p.size_chart_json = "{}"
        db.query(ProductSKU).filter(ProductSKU.product_id == charted_product).delete()
        db.add(
            ProductSKU(
                product_id=charted_product,
                sku_code=f"NUM-{uuid.uuid4().hex[:8]}",
                size="52",
                color="Test",
                stock_level=3,
                is_in_stock=True,
            )
        )
        db.commit()

    res = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY})

    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == charted_product).first()
        p.size_chart_json = json.dumps(CHART)
        db.query(ProductSKU).filter(ProductSKU.product_id == charted_product).delete()
        for size in ("S", "M", "L"):
            db.add(
                ProductSKU(
                    product_id=charted_product,
                    sku_code=f"FITTEST-R-{size}-{uuid.uuid4().hex[:8]}",
                    size=size,
                    color="Test",
                    stock_level=7,
                    is_in_stock=True,
                )
            )
        db.commit()

    # A refusal is a successful, honest response — never a 500 and never a guess.
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["recommended"] is False
    assert body["recommended_size"] is None
    assert body["reason_code"] == "NO_SIZE_CHART"
    assert body["confidence_score"] == 0
    assert len(body["confidence_disclosure"]) > 30


# ── units at the API boundary ──────────────────────────────────────────────
def test_imperial_request_matches_the_metric_one(client, charted_product):
    metric = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).json()
    imperial = client.post(
        FIT_ROUTES[0],
        json={
            "product_id": charted_product,
            "units": "imperial",
            "height": 70.1,
            "weight": 172,
            "chest": 40.2,
            "waist": 34.6,
            "hip": 40.9,
            "preferred_fit": "regular",
        },
    ).json()
    assert imperial["recommended_size"] == metric["recommended_size"]


def test_legacy_metric_field_names_still_work(client, charted_product):
    """Already-deployed clients must not break on the new contract."""
    res = client.post(
        FIT_ROUTES[0],
        json={
            "product_id": charted_product,
            "height_cm": 178,
            "weight_kg": 78,
            "chest_cm": 102,
            "waist_cm": 88,
            "hip_cm": 104,
            "body_shape": "Athletic",
            "preferred_fit": "regular",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["recommended_size"] == "M"


def test_legacy_cm_fields_with_imperial_units_is_rejected_not_guessed(client, charted_product):
    res = client.post(
        FIT_ROUTES[0],
        json={"product_id": charted_product, "units": "imperial", "height_cm": 178},
    )
    assert res.status_code == 422, res.text


@pytest.mark.parametrize(
    "payload",
    [
        {"height": 70, "weight": 78},                      # inches sent as cm
        {"height": 178, "weight": 78, "chest": 400},       # impossible chest
        {"height": 178, "weight": 900},                    # impossible weight
        {"height": 400, "weight": 78},                     # impossible height
    ],
)
def test_implausible_measurements_are_422_not_a_recommendation(
    client, charted_product, payload
):
    res = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **payload})
    assert res.status_code == 422, res.text


def test_unknown_fit_preference_is_rejected(client, charted_product):
    res = client.post(
        FIT_ROUTES[0],
        json={"product_id": charted_product, **BODY, "preferred_fit": "banana"},
    )
    assert res.status_code == 422, res.text


def test_missing_product_is_404(client):
    res = client.post(FIT_ROUTES[0], json={"product_id": 99999999, **BODY})
    assert res.status_code == 404, res.text


# ── the response tells the truth about itself ──────────────────────────────
def test_response_reports_the_measurements_it_used(client, charted_product):
    body = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).json()
    used = body["measurements_used"]
    assert used["height_cm"] == 178
    assert used["chest_cm"] == 102
    assert used["estimated_fields"] == []
    assert set(used["sections_scored"]) <= {"chest", "waist", "hip", "shoulder", "neck", "inseam"}


def test_height_weight_only_is_flagged_as_estimated(client, charted_product):
    body = client.post(
        FIT_ROUTES[0],
        json={"product_id": charted_product, "units": "metric", "height": 178, "weight": 78},
    ).json()
    if body["recommended"]:
        assert body["is_estimated"] is True
        assert body["measurements_used"]["estimated_fields"]
        assert body["confidence_score"] <= 70
    else:
        assert body["reason_code"] == "INSUFFICIENT_EVIDENCE"


def test_no_fabricated_claims_in_the_live_response(client, charted_product):
    """The exact strings the audit flagged must not appear in production output."""
    body = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).text
    for phrase in [
        "Optimal contour (98% match)",
        "< 3.2% estimated return probability",
        "True to standard international sizing",
        "modern European tailoring",
        "Ultra Low",
    ]:
        assert phrase not in body, phrase


def test_confidence_is_explained_not_asserted(client, charted_product):
    body = client.post(FIT_ROUTES[0], json={"product_id": charted_product, **BODY}).json()
    assert body["confidence_factors"], body
    assert str(body["confidence_score"]) in body["confidence_factors"][-1]
    assert body["engine_version"].startswith("fit-engine/")


# ── measurement sessions → profile ─────────────────────────────────────────
def test_save_to_profile_round_trip(client):
    """The route the frontend has always called and the backend never had."""
    user = _register(client, "save")
    h = user["headers"]

    sid = client.post(
        MEAS, json={"capture_mode": "manual", "consent_granted": True}, headers=h
    ).json()["id"]

    submitted = client.post(
        f"{MEAS}/{sid}/results",
        json={
            "units": "metric",
            "height_cm": 178,
            "chest_cm": 102,
            "waist_cm": 88,
            "hip_cm": 104,
            "body_shape": "Athletic",
            "confidence_score": 90,
            "calibration_method": "manual_entry",
            "source": "fit_finder_manual",
        },
        headers=h,
    )
    assert submitted.status_code == 201, submitted.text

    saved = client.post(f"{MEAS}/{sid}/save-to-profile", headers=h)
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["status"] == "saved"
    assert "height_cm" in payload["saved_fields"]
    # The values themselves must NOT be echoed — they are encrypted at rest.
    assert "178" not in json.dumps(payload["saved_fields"])

    profile = client.get(f"{API}/profile/me", headers=h)
    if profile.status_code == 200:
        attributes = profile.json().get("body_attributes") or {}
        if attributes:
            assert attributes.get("height_cm") == 178


def test_save_to_profile_requires_authentication(client):
    res = client.post(f"{MEAS}/1/save-to-profile")
    assert res.status_code in (401, 403), res.text


def test_save_to_profile_rejects_a_foreign_session(client):
    owner = _register(client, "owner2")
    attacker = _register(client, "attacker2")
    sid = client.post(
        MEAS,
        json={"capture_mode": "manual", "consent_granted": True},
        headers=owner["headers"],
    ).json()["id"]
    client.post(
        f"{MEAS}/{sid}/results",
        json={"height_cm": 170, "confidence_score": 80},
        headers=owner["headers"],
    )
    res = client.post(f"{MEAS}/{sid}/save-to-profile", headers=attacker["headers"])
    assert res.status_code == 404, res.text


def test_save_to_profile_without_results_is_a_conflict_not_a_silent_success(client):
    user = _register(client, "empty")
    sid = client.post(
        MEAS,
        json={"capture_mode": "manual", "consent_granted": True},
        headers=user["headers"],
    ).json()["id"]
    res = client.post(f"{MEAS}/{sid}/save-to-profile", headers=user["headers"])
    assert res.status_code == 409, res.text


def test_measurement_results_reject_implausible_values(client):
    user = _register(client, "bounds")
    sid = client.post(
        MEAS,
        json={"capture_mode": "manual", "consent_granted": True},
        headers=user["headers"],
    ).json()["id"]
    res = client.post(
        f"{MEAS}/{sid}/results",
        json={"height_cm": 178, "waist_cm": 700},
        headers=user["headers"],
    )
    assert res.status_code == 422, res.text


def test_measurement_disclaimer_matches_the_real_source(client):
    """The stored disclaimer must describe what actually happened."""
    user = _register(client, "disclaimer")
    sid = client.post(
        MEAS,
        json={"capture_mode": "manual", "consent_granted": True},
        headers=user["headers"],
    ).json()["id"]
    res = client.post(
        f"{MEAS}/{sid}/results",
        json={
            "height_cm": 178,
            "confidence_score": 60,
            "calibration_method": "manual_entry",
            "source": "manual",
        },
        headers=user["headers"],
    )
    assert res.status_code == 201, res.text
    disclaimer = res.json()["stored_measurements"]["disclaimer"]
    assert "Self-reported" in disclaimer
    assert "pose landmarks" not in disclaimer
