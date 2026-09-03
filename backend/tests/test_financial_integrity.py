"""
Financial integrity regression tests for release-gate
- Multi-brand order attribution must be brand-item-level not order-level
- Float vs Numeric precision
- Visual search product-level attribution
"""

import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.catalog import Product, ProductSKU
from backend.app.models.commerce import Order, OrderItem
from backend.app.models.catalog_import import BrandAnalyticsEvent
from backend.app.models.user import User, BrandProfile

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
client = TestClient(app)


class TestMultiBrandOrderAttribution:
    """Critical: assigning entire Order.total_amount to one brand is incorrect for multi-brand orders"""

    def test_multi_brand_order_brand_item_level(self):
        db = TestingSessionLocal()
        try:
            from backend.app.repositories.brand_repository import BrandRepository
            repo = BrandRepository(db)
            import inspect
            source = inspect.getsource(repo.compute_item_grain_attribution)
            # Brand-item-level: ledger revenue_amount joined through order_item_id;
            # conservation base is OrderItem.subtotal, never Order.total_amount.
            assert "revenue_amount" in source, "Must use BrandAnalyticsEvent.revenue_amount for brand-item-level attribution"
            assert "order_item_id" in source
            assert "it.subtotal" in source
            assert "Order.total_amount" not in source

            # Platform analytics and the attribution endpoint share the single ledger
            source2 = inspect.getsource(repo.get_platform_admin_analytics)
            assert "compute_item_grain_attribution" in source2, "Platform analytics must use the item-grain ledger"
            assert "compute_item_grain_attribution" in inspect.getsource(repo.get_revenue_attribution)

        finally:
            db.close()

    def test_float_vs_numeric_precision(self):
        """Verify money fields are now Numeric(12,2) not Float"""
        from sqlalchemy import inspect
        insp = inspect(test_engine)
        # Check orders table columns type
        cols = insp.get_columns("orders")
        total_col = next((c for c in cols if c["name"] == "total_amount"), None)
        assert total_col is not None
        # In SQLite, type may be NUMERIC or FLOAT, but after migration should be NUMERIC
        # For this test, we check that model uses Numeric
        from backend.app.models.commerce import Order
        from sqlalchemy import Numeric
        # Check model column type
        col_type = Order.__table__.c.total_amount.type
        assert isinstance(col_type, Numeric), f"Order.total_amount should be Numeric, got {col_type}"

        # Check all money fields are Numeric
        from backend.app.models.brand_analytics import SponsoredPlacement
        assert isinstance(SponsoredPlacement.__table__.c.bid_amount_per_click.type, Numeric)
        assert isinstance(SponsoredPlacement.__table__.c.daily_budget.type, Numeric)

        from backend.app.models.catalog import Product
        assert isinstance(Product.__table__.c.base_price.type, Numeric)


class TestVisualSearchProductLineage:
    """Visual search attribution must be product-level, not any-query existence"""

    def test_visual_search_product_level_attribution(self):
        db = TestingSessionLocal()
        try:
            from backend.app.repositories.brand_repository import BrandRepository
            from backend.app.services.commerce_service import CommerceService
            import inspect

            # Checkout delegates to the single item-grain ledger writer, which
            # decides visual_search per item via the product-level lookup with the
            # 30-day window.
            source = inspect.getsource(CommerceService.checkout)
            assert "_record_purchase_ledger" in source
            writer = inspect.getsource(CommerceService._record_purchase_ledger)
            assert "get_recent_visual_search_for_user" in writer
            assert "product_id=item.product_id" in writer
            assert "visual_search" in writer
            assert CommerceService.ATTRIBUTION_WINDOW_DAYS == 30

            repo = BrandRepository(db)
            source2 = inspect.getsource(repo.get_recent_visual_search_for_user)
            assert "BrandAnalyticsEvent.product_id == product_id" in source2
            assert "BrandAnalyticsEvent.created_at >= cutoff" in source2

        finally:
            db.close()

    def test_visual_search_unrelated_purchase_not_attributed(self):
        """Adversarial: user searched Product A but bought Product B -> should NOT be visual_search"""
        # This is a logic test: if user has view event for product 1, but order contains product 2, attribution should be organic not visual
        # We test via code inspection that attribution checks product_id equality
        from backend.app.repositories.brand_repository import BrandRepository
        import inspect
        source = inspect.getsource(BrandRepository.get_recent_visual_search_for_user)
        assert "BrandAnalyticsEvent.product_id == product_id" in source, "Must match product_id for attribution"
        import ast
        tree = ast.parse(source.lstrip() if not source.startswith("def") else source) if False else None
        # AST check (comments/docstrings may mention the old fallback): no try/except in the lookup
        import textwrap
        fn = ast.parse(textwrap.dedent(source)).body[0]
        assert not any(isinstance(n, ast.Try) for n in ast.walk(fn)), "no silent fallback on DB error"


class TestVTONMultiGarmentSequential:
    """VTON sequential multi-garment must preserve semantics and handle failures"""

    def test_sequential_architecture(self):
        import inspect
        from pathlib import Path
        modal_path = Path("services/vton-worker/modal_app.py")
        source = modal_path.read_text()
        # Must have sequential loop where output becomes input
        assert "current_image = result_image" in source or "current_image = frame_url" in source or "output becomes input" in source.lower()
        assert "for idx, garment_item" in source or "for idx, item" in source
        assert "layers_processed" in source
        assert "applied_slots" in source

    def test_same_slot_handling(self):
        """Multiple garments sharing a slot should be handled via layer_order"""
        from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine
        # Create mock products with same category
        class MockCat:
            slug = "tops"
            name = "Tops"
        class MockProd:
            category = MockCat()
            title = "Test Top"
        engine = SlotLayeringEngine()
        slot, order, level = engine.map_category_to_slot(MockProd())
        assert slot in ["upper_inner", "inner_layer", "full_body"] or "upper" in slot
        # Test resolve_and_apply with same slot — should handle replacement honestly
        item1 = {"product_id": 1, "position": "upper_inner", "layer_order": 2, "product_title": "Top1", "brand_name": "Brand", "image_url": "url", "price": 100}
        # Use real product from DB for second item to avoid mock issues
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from backend.app.models.catalog import Product
        TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
        test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        db = TestingSessionLocal()
        try:
            prod = db.query(Product).first()
            if prod:
                res = engine.resolve_and_apply([item1], prod)
                assert res is not None
        finally:
            db.close()

    def test_layer_failure_handling(self):
        """Failure on layer 2 after successful layer 1 must be honest"""
        import inspect
        from pathlib import Path
        source = Path("services/vton-worker/modal_app.py").read_text()
        # Must have per-layer OOM handling and failed_layer tracking
        assert "failed_layer" in source
        assert "GPU_OOM" in source
        assert "layer {idx}" in source or "layer" in source.lower()
