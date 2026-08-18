import pytest
from backend.app.services.styling.prompt_builder import InternalDynamicPromptBuilder, DynamicPromptPackage


def test_prompt_builder_single_item_apply():
    items = [{
        "product_id": 5,
        "product_title": "Relaxed Organic Poplin Oxford Shirt",
        "brand_name": "COS",
        "category_name": "Tops & Shirts",
        "position": "upper_inner",
        "color_family": "Optic White",
        "material": "100% Organic Cotton",
        "price": 95.0,
        "layer_order": 2
    }]

    pkg = InternalDynamicPromptBuilder.build_prompt_package(
        user_image_ref="user_photo_ref.png",
        applied_items=items,
        gender_mode="male",
        operation_type="single_item_apply"
    )

    assert isinstance(pkg, DynamicPromptPackage)
    assert "COS" in pkg.assembled_prompt_text
    assert "Relaxed Organic Poplin Oxford Shirt" in pkg.assembled_prompt_text
    assert "STRICT MANDATORY" in pkg.assembled_prompt_text
    assert "NEGATIVE PROMPT" in pkg.assembled_prompt_text
    assert pkg.truthfulness_flags["is_exact_twin_mode"] is True


def test_prompt_builder_full_outfit_and_animation():
    items = [
        {"product_id": 5, "product_title": "Poplin Shirt", "brand_name": "COS", "position": "upper_inner", "color_family": "White", "material": "Cotton", "price": 95.0, "layer_order": 2},
        {"product_id": 1, "product_title": "Wool Blazer", "brand_name": "Massimo Dutti", "position": "upper_outer", "color_family": "Navy", "material": "Wool", "price": 289.0, "layer_order": 4},
        {"product_id": 10, "product_title": "Suit Trousers", "brand_name": "Massimo Dutti", "position": "lower", "color_family": "Navy", "material": "Wool", "price": 159.0, "layer_order": 10},
        {"product_id": 17, "product_title": "Oxford Shoes", "brand_name": "Massimo Dutti", "position": "footwear", "color_family": "Black", "material": "Leather", "price": 240.0, "layer_order": 20}
    ]

    pkg = InternalDynamicPromptBuilder.build_prompt_package(
        user_image_ref="user_photo_ref.png",
        applied_items=items,
        gender_mode="male",
        animation_mode=True,
        output_aspect="9:16"
    )

    assert "ANIMATION TRY-ON SPECIFICATION" in pkg.assembled_prompt_text
    assert "Step 1" in pkg.assembled_prompt_text
    assert "Step 4" in pkg.assembled_prompt_text
    assert pkg.truthfulness_flags["footwear_calibrated"] is True


def test_prompt_builder_headwear_deferral_for_identity_lock():
    items = [
        {"product_id": 99, "product_title": "Heavy Winter Cap Hat", "brand_name": "CONFIT", "position": "accessory", "color_family": "Black", "material": "Wool", "price": 40.0, "layer_order": 30}
    ]

    pkg = InternalDynamicPromptBuilder.build_prompt_package(
        user_image_ref="user_photo_ref.png",
        applied_items=items
    )

    assert pkg.truthfulness_flags["headwear_deferred"] is True
    assert len(pkg.unsupported_warnings) > 0
    assert "deferred from try-on" in pkg.unsupported_warnings[0]
