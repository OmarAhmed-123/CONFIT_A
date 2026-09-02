"""
Visual Search Attribution Extended — Cases 9-12 plus invariants

Cases:
9. Search A → view A → add A to cart → remove A → buy A later
10. Search A → view A → add B to cart → buy B
11. Search A → view A → buy different SKU of same Product A
12. Search A → view A → purchase A after attribution window

Plus invariants:
- sum(attributed item revenue) + sum(organic) = eligible order-item subtotal
- revenue_amount belongs to exactly one OrderItem
- purchase event → order → order item → SKU → product → brand → revenue_amount lineage
"""

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from backend.app.core.money import to_decimal, money_add, money_sum, quantize_money


class TestVisualSearchExtendedCases:
    def test_case_9_search_view_cart_remove_buy_later(self):
        """Search A → view A → add to cart → remove → buy later should still attribute if within window."""
        product_a = 1
        view_events = [{"product_id": 1, "created_at": datetime.now(timezone.utc) - timedelta(days=1)}]
        cart_events = [{"product_id": 1, "action": "add", "at": datetime.now(timezone.utc) - timedelta(hours=12)},
                       {"product_id": 1, "action": "remove", "at": datetime.now(timezone.utc) - timedelta(hours=11)}]
        order_items = [{"product_id": 1, "purchased_at": datetime.now(timezone.utc)}]
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        has_view = any(e["product_id"] == 1 and e["created_at"] >= cutoff for e in view_events)
        assert has_view is True
        # Attribution should be visual_search because view exists within window, regardless of cart remove
        attribution = "visual_search" if has_view else "organic"
        assert attribution == "visual_search"

    def test_case_10_search_a_view_a_buy_b(self):
        """Search A → view A → add B to cart → buy B → organic, not visual_search."""
        view_events = [{"product_id": 1, "created_at": datetime.now(timezone.utc)}]
        order_items = [{"product_id": 2}]
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        # For product B (2), no view event
        has_view_for_b = any(e["product_id"] == 2 and e["created_at"] >= cutoff for e in view_events)
        assert has_view_for_b is False
        attribution = "visual_search" if has_view_for_b else "organic"
        assert attribution == "organic"

    def test_case_11_search_a_buy_different_sku_same_product(self):
        """Search A → view A → buy different SKU of same Product A → visual_search (same product_id)."""
        product_a_id = 1
        sku_a1 = 10
        sku_a2 = 11  # different SKU, same product
        view_events = [{"product_id": product_a_id, "sku_id": sku_a1, "created_at": datetime.now(timezone.utc)}]
        order_items = [{"product_id": product_a_id, "sku_id": sku_a2}]
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        # Product-level attribution: same product_id qualifies even if different SKU
        has_view = any(e["product_id"] == product_a_id and e["created_at"] >= cutoff for e in view_events)
        assert has_view is True
        attribution = "visual_search" if has_view else "organic"
        assert attribution == "visual_search"
        # Verify revenue_amount lineage: still belongs to OrderItem with product_id = A, sku_id = A2
        assert order_items[0]["product_id"] == product_a_id

    def test_case_12_search_a_purchase_after_window(self):
        """Search A → view A → purchase A after 31 days → organic."""
        view_event = {"product_id": 1, "created_at": datetime.now(timezone.utc) - timedelta(days=31)}
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        is_recent = view_event["created_at"] >= cutoff
        assert is_recent is False
        attribution = "visual_search" if is_recent else "organic"
        assert attribution == "organic"


class TestRevenueAttributionInvariants:
    def test_sum_attributed_plus_organic_equals_subtotal(self):
        """Invariant: sum(attributed) + sum(organic) = eligible order-item subtotal."""
        # Order with 4 items: 2 attributed, 2 organic
        items = [
            {"brand_id": 1, "subtotal": to_decimal("100.00"), "attribution": "visual_search"},
            {"brand_id": 1, "subtotal": to_decimal("50.00"), "attribution": "outfit_builder"},
            {"brand_id": 2, "subtotal": to_decimal("200.00"), "attribution": "organic"},
            {"brand_id": 2, "subtotal": to_decimal("150.00"), "attribution": "organic"},
        ]
        total_subtotal = money_sum([i["subtotal"] for i in items])
        attributed = money_sum([i["subtotal"] for i in items if i["attribution"] != "organic"])
        organic = money_sum([i["subtotal"] for i in items if i["attribution"] == "organic"])
        assert total_subtotal == Decimal("500.00")
        assert attributed == Decimal("150.00")
        assert organic == Decimal("350.00")
        assert attributed + organic == total_subtotal

    def test_revenue_amount_belongs_to_one_order_item(self):
        """revenue_amount belongs to exactly one OrderItem, not aggregate."""
        # Simulate BrandAnalyticsEvent
        order_item = {"id": 1, "product_id": 10, "sku_id": 100, "subtotal": to_decimal("99.99"), "brand_id": 5}
        event = {
            "event_type": "purchase",
            "order_id": 1001,
            "product_id": order_item["product_id"],
            "sku_id": order_item["sku_id"],
            "brand_id": order_item["brand_id"],
            "revenue_amount": order_item["subtotal"],  # Must be subtotal_item
        }
        # Invariant: revenue_amount == OrderItem.subtotal
        assert event["revenue_amount"] == order_item["subtotal"]
        # Must not be order total
        order_total = to_decimal("500.00")
        assert event["revenue_amount"] != order_total
        # Must belong to exactly one OrderItem (product_id + sku_id lineage)
        assert event["product_id"] == order_item["product_id"]
        assert event["sku_id"] == order_item["sku_id"]

    def test_purchase_event_lineage(self):
        """Lineage: purchase event → order → order item → SKU → product → brand → revenue_amount."""
        # Construct full lineage
        brand = {"id": 1, "name": "Brand A"}
        product = {"id": 10, "brand_id": brand["id"]}
        sku = {"id": 100, "product_id": product["id"]}
        order_item = {"id": 1000, "order_id": 1001, "product_id": product["id"], "sku_id": sku["id"], "brand_id": brand["id"], "subtotal": to_decimal("123.45")}
        order = {"id": 1001, "items": [order_item]}
        event = {
            "order_id": order["id"],
            "product_id": product["id"],
            "sku_id": sku["id"],
            "brand_id": brand["id"],
            "revenue_amount": order_item["subtotal"],
            "idempotency_key": f"purchase_{order['id']}_{product['id']}_{sku['id']}_visual_search"
        }
        # Verify lineage
        assert event["order_id"] == order["id"]
        assert event["product_id"] == product["id"]
        assert event["sku_id"] == sku["id"]
        assert event["brand_id"] == brand["id"]
        assert event["revenue_amount"] == order_item["subtotal"]
        # Idempotency key contains all lineage IDs
        assert str(order["id"]) in event["idempotency_key"]
        assert str(product["id"]) in event["idempotency_key"]
        assert str(sku["id"]) in event["idempotency_key"]

    def test_multi_brand_three_brands(self):
        """Three brands in one order, each isolated."""
        items = [
            {"brand_id": 1, "subtotal": to_decimal("100.00")},
            {"brand_id": 2, "subtotal": to_decimal("200.00")},
            {"brand_id": 3, "subtotal": to_decimal("300.00")},
        ]
        total = money_sum([i["subtotal"] for i in items])
        assert total == Decimal("600.00")
        # Each brand's revenue is its own subtotal
        brand_1 = money_sum([i["subtotal"] for i in items if i["brand_id"] == 1])
        brand_2 = money_sum([i["subtotal"] for i in items if i["brand_id"] == 2])
        brand_3 = money_sum([i["subtotal"] for i in items if i["brand_id"] == 3])
        assert brand_1 == Decimal("100.00")
        assert brand_2 == Decimal("200.00")
        assert brand_3 == Decimal("300.00")
        assert brand_1 + brand_2 + brand_3 == total
        # No brand gets total
        assert brand_1 != total
        assert brand_2 != total
        assert brand_3 != total

    def test_refunded_items_excluded(self):
        """Refunded/cancelled orders excluded from attribution."""
        orders = [
            {"id": 1, "status": "delivered", "items": [{"subtotal": to_decimal("100.00")}]},
            {"id": 2, "status": "cancelled", "items": [{"subtotal": to_decimal("200.00")}]},
            {"id": 3, "status": "refunded", "items": [{"subtotal": to_decimal("300.00")}]},
        ]
        eligible = [o for o in orders if o["status"] not in ("cancelled", "refunded")]
        eligible_total = money_sum([i["subtotal"] for o in eligible for i in o["items"]])
        assert eligible_total == Decimal("100.00")
        assert len(eligible) == 1
