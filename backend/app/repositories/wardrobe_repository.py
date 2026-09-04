import json
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.wardrobe import WardrobeItem, WardrobeGapAnalysis


class WardrobeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_items(self, user_id: int, category: Optional[str] = None) -> List[WardrobeItem]:
        query = self.db.query(WardrobeItem).filter(WardrobeItem.user_id == user_id)
        if category and category.lower() != "all":
            query = query.filter(WardrobeItem.category.ilike(category))
        return query.order_by(WardrobeItem.created_at.desc()).all()

    def get_item_by_id(self, item_id: int, user_id: int) -> Optional[WardrobeItem]:
        return self.db.query(WardrobeItem).filter(WardrobeItem.id == item_id, WardrobeItem.user_id == user_id).first()

    def get_item_by_image_hash(self, user_id: int, image_hash: str) -> Optional[WardrobeItem]:
        """Duplicate-upload protection: same owner + same bytes = same item.
        Always scoped to the caller — one user's upload can never match or
        leak another user's image hash."""
        return (
            self.db.query(WardrobeItem)
            .filter(WardrobeItem.user_id == user_id, WardrobeItem.image_hash == image_hash)
            .first()
        )

    def get_item_by_source_order_item(self, order_item_id: int) -> Optional[WardrobeItem]:
        """FLOW E idempotency read: the wardrobe piece synchronised from a
        given persisted OrderItem, if any.

        Deliberately NOT scoped by user_id: ``order_items.id`` is globally
        unique and an OrderItem belongs to exactly one Order with at most one
        owner, so the lineage key alone identifies the row. Scoping by user
        would let a re-parented order (guest checkout later attached to an
        account) silently create a second copy of the same purchased piece."""
        return (
            self.db.query(WardrobeItem)
            .filter(WardrobeItem.source_order_item_id == order_item_id)
            .first()
        )

    def add_item(
        self,
        user_id: int,
        title: str,
        category: str,
        subcategory: Optional[str],
        color_name: str,
        color_hex: str,
        pattern: str,
        brand_name: str,
        image_url: str,
        ai_tags: List[str],
        occasions: List[str],
        wear_frequency: str = "regular",
        purchase_price: Optional[float] = None,
        is_favorite: bool = False,
        seasonality: str = "All-Season",
        processing_status: str = "ready",
        image_hash: Optional[str] = None,
        source_order_item_id: Optional[int] = None
    ) -> WardrobeItem:
        item = WardrobeItem(
            user_id=user_id,
            title=title,
            category=category,
            subcategory=subcategory,
            color_name=color_name,
            color_hex=color_hex,
            pattern=pattern,
            brand_name=brand_name,
            image_url=image_url,
            ai_tags=json.dumps(ai_tags),
            occasions=json.dumps(occasions),
            wear_frequency=wear_frequency,
            purchase_price=purchase_price,
            is_favorite=is_favorite,
            seasonality=seasonality,
            processing_status=processing_status,
            image_hash=image_hash,
            # FLOW E: set only by the post-purchase sync; the unique index
            # uq_wardrobe_items_source_order_item makes a second insert of the
            # same purchased line raise IntegrityError instead of duplicating.
            source_order_item_id=source_order_item_id
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_item(self, item: WardrobeItem) -> WardrobeItem:
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_item(self, item: WardrobeItem) -> None:
        self.db.delete(item)
        self.db.commit()

    def get_gap_analyses(self, user_id: int) -> List[WardrobeGapAnalysis]:
        return self.db.query(WardrobeGapAnalysis).filter(WardrobeGapAnalysis.user_id == user_id).all()

    def save_gap_analysis(
        self,
        user_id: int,
        missing_category: str,
        missing_subcategory: str,
        suggested_colors: List[str],
        rationale: str,
        unlocks_outfit_count: int,
        recommended_products: List[Dict[str, Any]]
    ) -> WardrobeGapAnalysis:
        gap = WardrobeGapAnalysis(
            user_id=user_id,
            missing_category=missing_category,
            missing_subcategory=missing_subcategory,
            suggested_colors=json.dumps(suggested_colors),
            rationale=rationale,
            unlocks_outfit_count=unlocks_outfit_count,
            recommended_products_json=json.dumps(recommended_products)
        )
        self.db.add(gap)
        self.db.commit()
        self.db.refresh(gap)
        return gap
