"""Regression tests for D10 and D11 (docs/qa/WARDROBE_STYLIST_QUALITY_REPORT.md).

D10 — after the server-side colour filter removes garments the model chose, the
       summary / limitations / notes / reasons must not keep describing them.
D11 — when nothing in the wardrobe is tagged for the requested occasion or
       activity, the response must say so first, must not present the closest
       pieces as suitable, and must not carry fabricated performance claims.

The mocked model outputs below are the *actual* raw outputs captured from
ibm/granite-4-h-small on 2026-10-27 (docs/qa/eval/wardrobe_stylist_eval_live_20261027.json,
scenarios S10 and S16), so each test reproduces the original defect verbatim.
No real network: the IAM URL is pointed at an invalid host by the autouse fixture.
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.app.core.config import settings
from backend.app.providers.watsonx import client as wx_client_mod
from backend.tests.test_watsonx_stylist import (
    WX_URL,
    _add_item,
    _chat_response,
    _install_chat,
    _register,
    iam_ok,
)

URL = "/api/v1/wardrobe/outfit-recommendation"


@pytest.fixture(autouse=True)
def _never_touch_real_ibm(monkeypatch):
    monkeypatch.setattr(wx_client_mod, "IAM_TOKEN_URL", "https://iam.invalid/identity/token")


@pytest.fixture
def wx_env(monkeypatch):
    """Configured watsonx (mock transport installed per test), fallback allowed."""
    monkeypatch.setattr(settings, "WATSONX_APIKEY", "test-key")
    monkeypatch.setattr(settings, "WATSONX_PROJECT_ID", "proj-1")
    monkeypatch.setattr(settings, "WATSONX_URL", WX_URL)
    monkeypatch.setattr(settings, "WATSONX_REASONING_MODEL_ID", "ibm/granite-4-h-small")
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "auto")
    wx_client_mod.reset_watsonx_client()
    yield
    wx_client_mod.reset_watsonx_client()


def _model_returns(monkeypatch, payload: dict):
    def handler(req):
        return iam_ok(req) or httpx.Response(200, json=_chat_response(json.dumps(payload)))
    _install_chat(monkeypatch, handler)


# ───────────────────────── D10 ─────────────────────────
def _black_tie_closet(client, headers):
    jacket = _add_item(client, headers, title="Black Tuxedo Jacket", category="Outerwear", subcategory="Tuxedo Jacket",
                       color_name="Black", occasions=["Black Tie", "Formal"])
    shirt = _add_item(client, headers, title="White Dress Shirt", category="Tops", subcategory="Dress Shirt",
                      color_name="White", occasions=["Black Tie", "Formal"])
    trousers = _add_item(client, headers, title="Navy Dress Trousers", category="Bottoms", subcategory="Trousers",
                         color_name="Navy", occasions=["Formal"])
    shoes = _add_item(client, headers, title="Black Patent Shoes", category="Footwear", subcategory="Oxfords",
                      color_name="Black", occasions=["Black Tie", "Formal"])
    return jacket, shirt, trousers, shoes


def _s10_raw(jacket, shirt, trousers, shoes):
    return {
        "title": "Black Tie Ensemble",
        "summary": "A classic black-tie look using the available tuxedo jacket, trousers, and shirt, paired with elegant footwear.",
        "items": [
            {"wardrobe_item_id": shoes["id"], "role": "footwear",
             "reason": "Black patent shoes are the only formal footwear available and match the black-tie dress code."},
            {"wardrobe_item_id": trousers["id"], "role": "bottom",
             "reason": "Navy dress trousers provide a formal bottom option, though not ideal for black tie."},
            {"wardrobe_item_id": shirt["id"], "role": "top",
             "reason": "White dress shirt offers a crisp, formal top that pairs well with a tuxedo jacket."},
            {"wardrobe_item_id": jacket["id"], "role": "outerwear",
             "reason": "Black tuxedo jacket completes the formal look, adhering to the black-tie requirement."},
        ],
        "styling_notes": ["Ensure the tuxedo jacket and trousers are well-pressed for a polished appearance.",
                          "Consider adding a black bow tie and cummerbund if available to enhance the formal look."],
        "limitations": ["The navy trousers are not the ideal color for black tie, but no other formal bottoms are available.",
                        "Footwear options are limited; the black patent shoes are the closest match to the dress code."],
        "missing_categories": [],
        "assumptions": ["The user prefers to use existing wardrobe items rather than suggest new purchases."],
    }


def test_d10_prose_never_describes_items_removed_by_colour_filter(client, wx_env, monkeypatch):
    headers = _register(client)
    jacket, shirt, trousers, shoes = _black_tie_closet(client, headers)
    _model_returns(monkeypatch, _s10_raw(jacket, shirt, trousers, shoes))

    res = client.post(URL, headers=headers, json={
        "occasion": "Black Tie", "season": "winter", "time_of_day": "evening",
        "excluded_colors": ["black", "navy", "grey"],
    })
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["source"] == "watsonx"
    # Server-side enforcement still holds: only the white shirt survives.
    assert [i["wardrobe_item_id"] for i in out["items"]] == [shirt["id"]]
    assert out["is_complete"] is False
    # Bottoms/footwear exist in the wardrobe (so they are not "missing"), but the
    # filter emptied those positions — the response must say so explicitly.
    assert out["missing_categories"] == []
    assert any("No bottoms left once the colours" in lim for lim in out["limitations"])
    assert any("No footwear left once the colours" in lim for lim in out["limitations"])

    prose = " ".join([out["summary"], *out["styling_notes"], *out["limitations"], *out["assumptions"],
                      *(i["reason"] for i in out["items"])]).lower()
    for removed in ("tuxedo", "navy trousers", "patent"):
        assert removed not in prose, f"explanation still mentions removed garment {removed!r}: {prose}"
    assert "white dress shirt" in out["summary"].lower()
    assert "incomplete" in out["summary"].lower()
    assert any("colour you asked to avoid" in lim for lim in out["limitations"])
    # The remaining item's reason referenced the (removed) tuxedo jacket → neutralised.
    assert "tuxedo" not in out["items"][0]["reason"].lower()
    # Generic styling advice that does not name a removed item is kept.
    assert any("bow tie" in n for n in out["styling_notes"])


def test_d10_no_rewrite_when_nothing_was_filtered(client, wx_env, monkeypatch):
    headers = _register(client)
    jacket, shirt, trousers, shoes = _black_tie_closet(client, headers)
    _model_returns(monkeypatch, _s10_raw(jacket, shirt, trousers, shoes))

    res = client.post(URL, headers=headers, json={"occasion": "Black Tie", "season": "winter"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert len(out["items"]) == 4
    assert out["summary"].startswith("A classic black-tie look")  # model prose preserved verbatim
    assert out["fit_status"] == "partial"  # navy trousers are tagged Formal only, not Black Tie


def test_d10_arabic_rewrite_is_arabic(client, wx_env, monkeypatch):
    headers = _register(client)
    jacket, shirt, trousers, shoes = _black_tie_closet(client, headers)
    _model_returns(monkeypatch, _s10_raw(jacket, shirt, trousers, shoes))
    res = client.post(URL, headers=headers, json={
        "occasion": "Black Tie", "language": "ar", "excluded_colors": ["أسود", "كحلي"],
    })
    assert res.status_code == 200, res.text
    out = res.json()
    assert [i["wardrobe_item_id"] for i in out["items"]] == [shirt["id"]]
    assert "tuxedo" not in out["summary"].lower()
    assert "الاختيار النهائي" in out["summary"] and "غير مكتملة" in out["summary"]


# ───────────────────────── D11 ─────────────────────────
def _formal_only_closet(client, headers):
    shirt = _add_item(client, headers, title="White Dress Shirt", category="Tops", subcategory="Dress Shirt",
                      color_name="White", occasions=["Formal", "Business"])
    trousers = _add_item(client, headers, title="Black Suit Trousers", category="Bottoms", subcategory="Trousers",
                         color_name="Black", occasions=["Formal", "Business"])
    shoes = _add_item(client, headers, title="Black Oxfords", category="Footwear", subcategory="Oxfords",
                      color_name="Black", occasions=["Formal", "Business"])
    return shirt, trousers, shoes


def _s16_raw(shirt, trousers, shoes):
    return {
        "title": "Gym-Ready Black & White Workout",
        "summary": "A sleek, monochrome gym outfit that balances professionalism and comfort for an evening workout.",
        "items": [
            {"wardrobe_item_id": shirt["id"], "role": "top",
             "reason": "Breathable white shirt provides a clean base and wicks sweat."},
            {"wardrobe_item_id": trousers["id"], "role": "bottom",
             "reason": "Tailored black trousers offer a smart silhouette while allowing full movement."},
            {"wardrobe_item_id": shoes["id"], "role": "footwear",
             "reason": "Black oxfords are versatile; choose a low-profile, cushioned version for gym use."},
        ],
        "styling_notes": ["Roll the sleeves for a sporty feel."],
        "limitations": ["No dedicated gym shoes; oxfords are a compromise.", "Limited color palette restricts visual interest."],
        "missing_categories": [],
        "assumptions": ["User prefers a smart-casual look suitable for gym environments."],
    }


def test_d11_unsuitable_wardrobe_is_reported_honestly(client, wx_env, monkeypatch):
    headers = _register(client)
    shirt, trousers, shoes = _formal_only_closet(client, headers)
    _model_returns(monkeypatch, _s16_raw(shirt, trousers, shoes))

    res = client.post(URL, headers=headers, json={
        "occasion": "Active", "activity": "gym workout", "season": "summer", "time_of_day": "evening",
    })
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["source"] == "watsonx"
    assert out["fit_status"] == "unsuitable"
    # First limitation is the insufficiency statement.
    assert out["limitations"][0].startswith("Nothing in your wardrobe is tagged for Active")
    # Summary no longer sells the suit as a gym outfit.
    assert "gym outfit" not in out["summary"].lower()
    assert "not a recommended outfit" in out["summary"]
    # Fabricated performance claims are gone from every reason/note.
    prose = " ".join([*out["styling_notes"], *out["assumptions"], *(i["reason"] for i in out["items"])]).lower()
    for claim in ("wick", "breathable", "cushion", "sporty"):
        assert claim not in prose, prose
    # The honest, non-fabricated reason (silhouette/movement) was kept as-is.
    assert "smart silhouette" in out["items"][1]["reason"]
    assert out["items"][0]["reason"].startswith("Closest available Tops")


def test_d11_suitable_wardrobe_keeps_model_prose_and_is_suitable(client, wx_env, monkeypatch):
    headers = _register(client)
    tee = _add_item(client, headers, title="Grey Training Tee", category="Tops", subcategory="T-Shirt",
                    color_name="Grey", occasions=["Active", "Casual"])
    shorts = _add_item(client, headers, title="Black Running Shorts", category="Bottoms", subcategory="Shorts",
                       color_name="Black", occasions=["Active"])
    shoes = _add_item(client, headers, title="White Trainers", category="Footwear", subcategory="Sneakers",
                      color_name="White", occasions=["Active", "Casual"])
    _model_returns(monkeypatch, {
        "title": "Evening gym set", "summary": "A simple training set from your wardrobe.",
        "items": [
            {"wardrobe_item_id": tee["id"], "role": "top", "reason": "Training tee tagged for active use."},
            {"wardrobe_item_id": shorts["id"], "role": "bottom", "reason": "Running shorts tagged for active use."},
            {"wardrobe_item_id": shoes["id"], "role": "footwear", "reason": "Trainers tagged for active use."},
        ],
        "styling_notes": [], "limitations": [], "missing_categories": [], "assumptions": [],
    })
    res = client.post(URL, headers=headers, json={"occasion": "Active", "activity": "gym workout"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["fit_status"] == "suitable"
    assert out["summary"] == "A simple training set from your wardrobe."
    assert not any("Nothing in your wardrobe" in lim for lim in out["limitations"])


def test_d11_deterministic_fallback_marks_unsuitable_too(client, monkeypatch):
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "deterministic")
    headers = _register(client)
    _formal_only_closet(client, headers)
    res = client.post(URL, headers=headers, json={"occasion": "Active", "activity": "gym workout", "language": "ar"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["source"] == "deterministic_fallback" and out["fit_status"] == "unsuitable"
    assert "لا تحتوي خزانتك على قطع مناسبة" in out["summary"]
    assert any("موسومة لمناسبة" in lim for lim in out["limitations"])


def test_d13_deterministic_fallback_never_attributes_items_to_the_model(client, monkeypatch):
    """D13 (found 2026-10-29 during the local PostgreSQL end-to-end run): in
    deterministic mode every item was tagged ``selected_by="model"`` via the
    schema default, although no language model was involved. The whole outfit
    is rule-built, so every piece must say so."""
    monkeypatch.setattr(settings, "WARDROBE_STYLIST_PROVIDER", "deterministic")
    headers = _register(client)
    _formal_only_closet(client, headers)
    res = client.post(URL, headers=headers, json={"occasion": "Business", "time_of_day": "morning"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["source"] == "deterministic_fallback" and out["ai_generated"] is False
    assert out["items"], "fallback should still pick the tagged business pieces"
    assert {it["selected_by"] for it in out["items"]} == {"rule_matcher"}


# ───────────────────────── D12 (id/description mix-up) ─────────────────────────
def test_d12_role_collision_is_explained(client, wx_env, monkeypatch):
    """Live eval 2026-10-28 S01: the model cited the tee's id while describing the
    jeans. The server keeps trusting stored categories (no second top) and must
    tell the user why a position is empty instead of silently returning 3 pieces."""
    headers = _register(client)
    flannel = _add_item(client, headers, title="Plaid Flannel Shirt", category="Tops", color_name="Navy", occasions=["Casual"])
    tee = _add_item(client, headers, title="White Cotton Tee", category="Tops", color_name="White", occasions=["Casual"])
    _add_item(client, headers, title="Dark Wash Jeans", category="Bottoms", subcategory="Jeans", color_name="Blue", occasions=["Casual"])
    boots = _add_item(client, headers, title="Brown Leather Boots", category="Footwear", subcategory="Boots", color_name="Brown", occasions=["Casual"])
    _model_returns(monkeypatch, {
        "title": "Park look", "summary": "Layered casual look.",
        "items": [
            {"wardrobe_item_id": flannel["id"], "role": "top", "reason": "Flannel for autumn warmth."},
            {"wardrobe_item_id": tee["id"], "role": "bottom", "reason": "Dark wash jeans provide a relaxed base."},
            {"wardrobe_item_id": boots["id"], "role": "footwear", "reason": "Boots suit autumn."},
        ],
        "styling_notes": [], "limitations": [], "missing_categories": [], "assumptions": [],
    })
    res = client.post(URL, headers=headers, json={"occasion": "Casual", "season": "autumn"})
    assert res.status_code == 200, res.text
    out = res.json()
    # The duplicate top is dropped, the empty bottom position is completed by the
    # rule matcher with the real jeans, and every piece says who selected it.
    by_role = {i["role"]: i for i in out["items"]}
    assert set(by_role) == {"top", "bottom", "footwear"} and out["is_complete"] is True
    assert by_role["bottom"]["title"] == "Dark Wash Jeans" and by_role["bottom"]["selected_by"] == "rule_matcher"
    assert by_role["top"]["selected_by"] == "model" and by_role["footwear"]["selected_by"] == "model"
    assert "Dark Wash Jeans" in by_role["bottom"]["reason"]  # rule reason names the actual garment
    assert any("duplicated a position" in lim for lim in out["limitations"])
    assert any("added by CONFIT's rule-based matcher" in lim and "not chosen by the AI stylist" in lim for lim in out["limitations"])


def test_d12_mismatched_reason_never_shown_next_to_wrong_item(client, wx_env, monkeypatch):
    """Model cites the tee's id as 'top' but the reason describes the jeans and
    the role it claimed does not match the stored category → the reason is
    replaced by a rule note; the tee keeps its real identity."""
    headers = _register(client)
    tee = _add_item(client, headers, title="White Cotton Tee", category="Tops", color_name="White", occasions=["Casual"])
    _add_item(client, headers, title="Dark Wash Jeans", category="Bottoms", subcategory="Jeans", color_name="Blue", occasions=["Casual"])
    boots = _add_item(client, headers, title="Brown Leather Boots", category="Footwear", subcategory="Boots", color_name="Brown", occasions=["Casual"])
    _model_returns(monkeypatch, {
        "title": "Look", "summary": "Casual look.",
        "items": [
            {"wardrobe_item_id": tee["id"], "role": "bottom", "reason": "Dark wash jeans give a relaxed denim base."},
            {"wardrobe_item_id": boots["id"], "role": "footwear", "reason": "Boots for autumn."},
        ],
        "styling_notes": [], "limitations": [], "missing_categories": [], "assumptions": [],
    })
    res = client.post(URL, headers=headers, json={"occasion": "Casual", "season": "autumn"})
    out = res.json()
    top = next(i for i in out["items"] if i["wardrobe_item_id"] == tee["id"])
    assert top["role"] == "top" and "jeans" not in top["reason"].lower() and "White Cotton Tee" in top["reason"]
    assert any("described a different garment" in lim for lim in out["limitations"])
    bottom = next(i for i in out["items"] if i["role"] == "bottom")
    assert bottom["title"] == "Dark Wash Jeans" and bottom["selected_by"] == "rule_matcher"


def test_d12_completion_respects_colour_exclusion_and_reports_impossible(client, wx_env, monkeypatch):
    headers = _register(client)
    top = _add_item(client, headers, title="White Oxford Shirt", category="Tops", color_name="White", occasions=["Smart Casual"])
    _add_item(client, headers, title="Black Jeans", category="Bottoms", subcategory="Jeans", color_name="Black", occasions=["Smart Casual"])
    _add_item(client, headers, title="Navy Chinos", category="Bottoms", subcategory="Chinos", color_name="Navy", occasions=["Smart Casual"])
    shoes = _add_item(client, headers, title="Tan Loafers", category="Footwear", subcategory="Loafers", color_name="Tan", occasions=["Smart Casual"])
    _model_returns(monkeypatch, {
        "title": "Look", "summary": "Shirt and loafers.",
        "items": [
            {"wardrobe_item_id": top["id"], "role": "top", "reason": "Crisp shirt."},
            {"wardrobe_item_id": shoes["id"], "role": "footwear", "reason": "Loafers."},
        ],
        "styling_notes": [], "limitations": [], "missing_categories": [], "assumptions": [],
    })
    # Navy allowed → chinos are completed in; black jeans never considered.
    out = client.post(URL, headers=headers, json={"occasion": "Smart Casual", "excluded_colors": ["black"]}).json()
    bottom = next(i for i in out["items"] if i["role"] == "bottom")
    assert bottom["title"] == "Navy Chinos" and bottom["selected_by"] == "rule_matcher" and out["is_complete"] is True
    # Both bottoms excluded → nothing is inserted; the outfit is explicitly incomplete.
    out = client.post(URL, headers=headers, json={"occasion": "Smart Casual", "excluded_colors": ["black", "navy"]}).json()
    assert [i["role"] for i in out["items"]] == ["top", "footwear"] and out["is_complete"] is False
    assert all(i["selected_by"] == "model" for i in out["items"])
    assert not any("rule-based matcher" in lim for lim in out["limitations"])


def test_d12_model_claim_that_filled_position_is_missing_is_dropped(client, wx_env, monkeypatch):
    """Live eval S07/S09/S14 (2026-10-28): the model wrote "No suitable footwear in
    the wardrobe" and the server then added the heels. Contradictory claims about a
    position the matcher filled must not survive; unrelated limitations must."""
    headers = _register(client)
    dress = _add_item(client, headers, title="Emerald Satin Midi Dress", category="Dresses", color_name="Green", occasions=["Cocktail"])
    _add_item(client, headers, title="Black Strappy Heels", category="Footwear", subcategory="Heels", color_name="Black", occasions=["Cocktail"])
    _model_returns(monkeypatch, {
        "title": "Cocktail", "summary": "Emerald dress.",
        "items": [{"wardrobe_item_id": dress["id"], "role": "dress", "reason": "Cocktail-appropriate silhouette."}],
        "styling_notes": [], "limitations": ["No suitable footwear in the wardrobe for the occasion; consider bringing heels.",
                                             "No outerwear for a cool evening."],
        "missing_categories": ["Footwear"], "assumptions": [],
    })
    out = client.post(URL, headers=headers, json={"occasion": "Cocktail", "season": "summer"}).json()
    roles = {i["role"]: i for i in out["items"]}
    assert roles["footwear"]["selected_by"] == "rule_matcher" and out["is_complete"] is True
    assert out["missing_categories"] == []
    assert not any("footwear" in lim.lower() and "no suitable" in lim.lower() for lim in out["limitations"])
    assert any("No outerwear" in lim for lim in out["limitations"])


def test_d12_completion_arabic_labels(client, wx_env, monkeypatch):
    headers = _register(client)
    top = _add_item(client, headers, title="قميص أبيض", category="Tops", color_name="White", occasions=["Business"])
    _add_item(client, headers, title="بنطلون كحلي", category="Bottoms", color_name="Navy", occasions=["Business"])
    _add_item(client, headers, title="حذاء بني", category="Footwear", color_name="Brown", occasions=["Business"])
    _model_returns(monkeypatch, {
        "title": "إطلالة", "summary": "قميص فقط.",
        "items": [{"wardrobe_item_id": top["id"], "role": "top", "reason": "قميص أنيق."}],
        "styling_notes": [], "limitations": [], "missing_categories": [], "assumptions": [],
    })
    out = client.post(URL, headers=headers, json={"occasion": "Business", "language": "ar"}).json()
    assert out["is_complete"] is True
    assert sum(1 for i in out["items"] if i["selected_by"] == "rule_matcher") == 2
    assert any("المُطابِق القاعدي" in lim and "لم يخترها المصمم الذكي" in lim for lim in out["limitations"])


# ───────────────────────── D14 (colour-family aliases) ─────────────────────────
@pytest.mark.parametrize("raw,family", [("Indigo", "Navy"), ("Dark indigo", "Navy"), ("Teal", "Blue"),
                                        ("Denim", "Blue"), ("Bordeaux", "Red"), ("Lime", "Green")])
def test_d14_common_colours_do_not_collapse_to_black(raw, family):
    """D14 (found 2026-10-29 in the local PostgreSQL browser run): 'Dark indigo
    jeans' were persisted and reasoned about as *Black* because the alias table
    had no entry and the fallback family is Black. A user excluding black would
    silently lose their indigo jeans."""
    from backend.app.services import wardrobe_taxonomy as taxonomy
    assert taxonomy.normalize_color(raw) == family
