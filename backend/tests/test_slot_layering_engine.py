from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine


class MockProduct:
    def __init__(self, pid, title, cat_slug, price=100.0, brand="CONFIT"):
        self.id = pid
        self.title = title
        class Cat:
            def __init__(self, s):
                self.slug = s
                self.name = s.capitalize()
        self.category = Cat(cat_slug)
        class Brand:
            def __init__(self, b):
                self.brand_name = b
        self.brand = Brand(brand)
        self.base_price = price
        self.thumbnail_url = f"https://img.confit.io/{pid}.jpg"
        self.dominant_hex = "#1B1F3B"
        self.color_family = "Navy"
        self.material = "Wool"
        self.skus = []


def test_slot_engine_scenario_1_upper_inner_replace():
    shirt_a = MockProduct(1, "Poplin Shirt A", "tops", 90.0)
    shirt_b = MockProduct(2, "Oxford Shirt B", "tops", 95.0)

    # 1. Apply Shirt A
    res1 = SlotLayeringEngine.resolve_and_apply([], shirt_a)
    assert res1.normalized_slot == "upper_inner"
    assert len(res1.final_applied_items) == 1
    assert res1.final_applied_items[0]["product_id"] == 1

    # 2. Apply Shirt B -> Should replace Shirt A
    res2 = SlotLayeringEngine.resolve_and_apply(res1.final_applied_items, shirt_b)
    assert res2.normalized_slot == "upper_inner"
    assert len(res2.final_applied_items) == 1
    assert res2.final_applied_items[0]["product_id"] == 2
    assert len(res2.replaced_items) == 1
    assert res2.replaced_items[0]["product_id"] == 1


def test_slot_engine_scenario_2_outerwear_layering():
    shirt = MockProduct(1, "Poplin Shirt", "tops", 90.0)
    blazer = MockProduct(2, "Double-Breasted Wool Blazer", "outerwear", 280.0)

    res1 = SlotLayeringEngine.resolve_and_apply([], shirt)
    res2 = SlotLayeringEngine.resolve_and_apply(res1.final_applied_items, blazer)

    assert len(res2.final_applied_items) == 2
    positions = [it["position"] for it in res2.final_applied_items]
    assert positions == ["upper_inner", "upper_outer"]


def test_slot_engine_scenario_3_lower_body_replace():
    jeans = MockProduct(3, "Straight Denim Jeans", "bottoms", 120.0)
    trousers = MockProduct(4, "Pleated Wool Trousers", "bottoms", 160.0)

    res1 = SlotLayeringEngine.resolve_and_apply([], jeans)
    res2 = SlotLayeringEngine.resolve_and_apply(res1.final_applied_items, trousers)

    assert len(res2.final_applied_items) == 1
    assert res2.final_applied_items[0]["product_id"] == 4
    assert res2.final_applied_items[0]["position"] == "lower"


def test_slot_engine_scenario_4_dress_override():
    shirt = MockProduct(1, "Poplin Shirt", "tops", 90.0)
    trousers = MockProduct(2, "Suit Trousers", "bottoms", 150.0)
    dress = MockProduct(5, "Silk Column Maxi Dress", "dresses", 340.0)

    # 1. Dress shirt + trousers
    res1 = SlotLayeringEngine.resolve_and_apply([], shirt)
    res2 = SlotLayeringEngine.resolve_and_apply(res1.final_applied_items, trousers)
    assert len(res2.final_applied_items) == 2

    # 2. Dress overrides both top and bottom
    res3 = SlotLayeringEngine.resolve_and_apply(res2.final_applied_items, dress)
    assert len(res3.final_applied_items) == 1
    assert res3.final_applied_items[0]["product_id"] == 5
    assert res3.final_applied_items[0]["position"] == "dress"
    assert len(res3.removed_conflicts) == 2


def test_slot_engine_scenario_5_footwear_replacement():
    shoes_a = MockProduct(6, "Penny Loafers A", "footwear", 220.0)
    shoes_b = MockProduct(7, "Leather Oxfords B", "footwear", 240.0)

    res1 = SlotLayeringEngine.resolve_and_apply([], shoes_a)
    res2 = SlotLayeringEngine.resolve_and_apply(res1.final_applied_items, shoes_b)

    assert len(res2.final_applied_items) == 1
    assert res2.final_applied_items[0]["product_id"] == 7
    assert res2.final_applied_items[0]["position"] == "footwear"


def test_slot_engine_scenario_6_unsupported_accessory():
    hat = MockProduct(8, "Heavy Winter Fedora Hat", "accessories", 45.0)

    res = SlotLayeringEngine.resolve_and_apply([], hat)
    assert res.support_level == "unsupported"
    assert res.requires_render is False
    assert len(res.final_applied_items) == 0
    assert "deferred from 3D try-on" in res.unsupported_reason


def test_slot_engine_scenario_7_remove_item():
    shirt = MockProduct(1, "Shirt", "tops", 90.0)
    blazer = MockProduct(2, "Blazer", "outerwear", 280.0)
    trousers = MockProduct(3, "Trousers", "bottoms", 150.0)

    items = [
        {"product_id": 1, "position": "upper_inner", "slot_type": "upper_inner"},
        {"product_id": 2, "position": "upper_outer", "slot_type": "upper_outer"},
        {"product_id": 3, "position": "lower", "slot_type": "lower"}
    ]

    res = SlotLayeringEngine.resolve_and_remove(items, product_id=2)
    assert len(res.final_applied_items) == 2
    positions = [it["position"] for it in res.final_applied_items]
    assert "upper_outer" not in positions
    assert "upper_inner" in positions
    assert "lower" in positions


def test_slot_engine_scenario_8_replace_after_full_look():
    items = [
        {"product_id": 1, "position": "upper_inner", "slot_type": "upper_inner"},
        {"product_id": 2, "position": "upper_outer", "slot_type": "upper_outer"},
        {"product_id": 3, "position": "lower", "slot_type": "lower"},
        {"product_id": 4, "position": "footwear", "slot_type": "footwear"},
        {"product_id": 5, "position": "accessory", "slot_type": "accessory"}
    ]
    new_chinos = MockProduct(10, "Pleated Chinos", "bottoms", 140.0)

    res = SlotLayeringEngine.resolve_and_apply(items, new_chinos)
    assert len(res.final_applied_items) == 5
    lower_item = next(it for it in res.final_applied_items if it["position"] == "lower")
    assert lower_item["product_id"] == 10
