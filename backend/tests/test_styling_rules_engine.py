import pytest
from backend.app.services.styling.ontology import SlotType, FormalityLevel, classify_product_slot
from backend.app.services.styling.color_harmony import ColorHarmonyEngine
from backend.app.services.styling.rules import (
    CategoryCompatibilityRule,
    FormalityCoherenceRule,
    OccasionAppropriatenessRule,
    CompletenessRule,
    BudgetRule,
    StylingRulesEngine
)
from backend.app.services.styling.composer import OutfitComposer
from backend.app.services.styling.grounding import GroundingGenerator


def test_category_compatibility_rule():
    rule = CategoryCompatibilityRule()

    # Case 1: Valid formal combination
    valid_items = [
        {"position": "outerwear", "product_title": "Tailored Wool Blazer", "slot_type": "formal_outer"},
        {"position": "top", "product_title": "Crisp Poplin Shirt", "slot_type": "formal_shirt"},
        {"position": "bottom", "product_title": "Matching Wool Suit Trousers", "slot_type": "formal_bottom"},
        {"position": "footwear", "product_title": "Goodyear-Welted Oxford Shoes", "slot_type": "formal_shoes"}
    ]
    res1 = rule.evaluate(valid_items, {"formality": "formal", "occasion": "Formal & Wedding"})
    assert res1.passed is True
    assert res1.penalty == 0

    # Case 2: Sneaker conflict in formal wedding
    sneaker_conflict = [
        {"position": "outerwear", "product_title": "Tailored Wool Blazer", "slot_type": "formal_outer"},
        {"position": "top", "product_title": "Crisp Poplin Shirt", "slot_type": "formal_shirt"},
        {"position": "bottom", "product_title": "Matching Wool Suit Trousers", "slot_type": "formal_bottom"},
        {"position": "footwear", "product_title": "Low-Top Leather Sneaker", "slot_type": "casual_shoes"}
    ]
    res2 = rule.evaluate(sneaker_conflict, {"formality": "formal", "occasion": "Formal & Wedding"})
    assert res2.passed is False
    assert res2.penalty > 0
    assert "sneaker" in res2.explanation.lower()

    # Case 3: Dress + separate trousers contradiction
    dress_trousers_conflict = [
        {"position": "dress", "product_title": "Silk Maxi Dress", "slot_type": "dress"},
        {"position": "bottom", "product_title": "Suit Trousers", "slot_type": "formal_bottom"}
    ]
    res3 = rule.evaluate(dress_trousers_conflict, {"formality": "formal", "occasion": "Evening & Party"})
    assert res3.passed is False
    assert "dress cannot be worn" in res3.explanation.lower()


def test_formality_coherence_rule():
    rule = FormalityCoherenceRule()

    # Uniform high formality
    formal_items = [
        {"formality_num": 5, "product_title": "Tailored Wool Blazer"},
        {"formality_num": 5, "product_title": "Dress Shirt"},
        {"formality_num": 5, "product_title": "Suit Trousers"},
        {"formality_num": 5, "product_title": "Oxford Shoes"}
    ]
    res1 = rule.evaluate(formal_items, {"formality": "formal"})
    assert res1.passed is True
    assert res1.penalty == 0

    # Formality divergence (Formal blazer with casual shorts)
    divergent_items = [
        {"formality_num": 5, "product_title": "Tailored Wool Blazer"},
        {"formality_num": 1, "product_title": "Casual Shorts"}
    ]
    res2 = rule.evaluate(divergent_items, {"formality": "formal"})
    assert res2.passed is False
    assert res2.penalty > 0


def test_color_harmony_engine():
    # Navy + Ivory + Emerald (Classic complementary contrast)
    items = [
        {"color_family": "Navy Blue", "dominant_hex": "#1B1F3B", "position": "outerwear"},
        {"color_family": "Ivory Cream", "dominant_hex": "#F5F2EB", "position": "top"},
        {"color_family": "Emerald Green", "dominant_hex": "#1E4D3B", "position": "accessory"},
        {"color_family": "Ebony Black", "dominant_hex": "#111111", "position": "footwear"}
    ]
    eval_res = ColorHarmonyEngine.evaluate_palette(items)
    assert eval_res["color_harmony_score"] >= 90
    assert "Complementary" in eval_res["harmony_type"] or "Tonal" in eval_res["harmony_type"]


def test_completeness_rule_and_honest_labeling():
    rule = CompletenessRule()

    # Complete look
    complete_set = [
        {"position": "outerwear"},
        {"position": "top"},
        {"position": "bottom"},
        {"position": "footwear"}
    ]
    res1 = rule.evaluate(complete_set, {})
    assert res1.passed is True

    # Incomplete look (missing footwear)
    partial_set = [
        {"position": "outerwear"},
        {"position": "top"},
        {"position": "bottom"}
    ]
    res2 = rule.evaluate(partial_set, {})
    assert res2.passed is False
    assert "footwear" in res2.explanation


def test_grounding_generator_precision():
    outfit = {
        "title": "The Essential Formal & Wedding Tailored Look",
        "total_price": 850.0,
        "items": [
            {"position": "outerwear", "product_title": "Italian Wool Blazer", "brand_name": "Massimo Dutti", "color_family": "Navy Blue"},
            {"position": "top", "product_title": "Organic Poplin Shirt", "brand_name": "COS", "color_family": "Optic White"},
            {"position": "bottom", "product_title": "Pleated Suit Trousers", "brand_name": "Massimo Dutti", "color_family": "Navy Blue"},
            {"position": "footwear", "product_title": "Calfskin Oxford Shoes", "brand_name": "Massimo Dutti", "color_family": "Ebony Black"},
            {"position": "accessory", "product_title": "Mulberry Silk Tie", "brand_name": "Massimo Dutti", "color_family": "Emerald Green"}
        ]
    }
    intent = {"occasion": "Formal & Wedding", "aesthetic": "Quiet Luxury"}
    text = GroundingGenerator.generate_grounded_text("Navy suit with green tie for wedding", outfit, intent)

    assert "Massimo Dutti" in text
    assert "Italian Wool Blazer" in text
    assert "Organic Poplin Shirt" in text
    assert "Calfskin Oxford Shoes" in text
    assert "Mulberry Silk Tie" in text
    assert "850.00" in text
