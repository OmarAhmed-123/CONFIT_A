import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from backend.app.models.wardrobe import WardrobeItem, WardrobeGapAnalysis


def live(query):
    """Restrict a WardrobeItem query to items that are NOT in the bin.

    ONE definition of "live", applied by every read path. A second copy of
    `deleted_at IS NULL` in a service or controller is how a binned item
    eventually reappears on one screen and not another — the acceptance
    criterion "no duplicates in the list" is really a single-source-of-truth
    requirement.
    """
    return query.filter(WardrobeItem.deleted_at.is_(None))


class WardrobeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_items(self, user_id: int, category: Optional[str] = None) -> List[WardrobeItem]:
        query = live(self.db.query(WardrobeItem).filter(WardrobeItem.user_id == user_id))
        if category and category.lower() != "all":
            query = query.filter(WardrobeItem.category.ilike(category))
        return query.order_by(WardrobeItem.created_at.desc()).all()

    def get_item_by_id(self, item_id: int, user_id: int) -> Optional[WardrobeItem]:
        """A LIVE item. Binned items are invisible to every normal read, which
        is what makes the bin safe: nothing downstream can accidentally style,
        export or analyse something the user deleted."""
        return live(
            self.db.query(WardrobeItem).filter(
                WardrobeItem.id == item_id, WardrobeItem.user_id == user_id
            )
        ).first()

    def get_binned_item_by_id(self, item_id: int, user_id: int) -> Optional[WardrobeItem]:
        """The explicit opposite, for restore and permanent delete only."""
        return (
            self.db.query(WardrobeItem)
            .filter(
                WardrobeItem.id == item_id,
                WardrobeItem.user_id == user_id,
                WardrobeItem.deleted_at.isnot(None),
            )
            .first()
        )

    def get_item_by_image_hash(self, user_id: int, image_hash: str,
                               include_binned: bool = False) -> Optional[WardrobeItem]:
        """Duplicate-upload protection: same owner + same bytes = same item.
        Always scoped to the caller — one user's upload can never match or
        leak another user's image hash."""
        query = self.db.query(WardrobeItem).filter(
            WardrobeItem.user_id == user_id, WardrobeItem.image_hash == image_hash
        )
        # `include_binned` exists for ONE caller: the upload path. The unique
        # index on (user_id, image_hash) is still enforced against binned
        # rows, so re-uploading a photo that is sitting in the bin would raise
        # IntegrityError and surface as a 500. The upload path looks for the
        # binned row and revives it instead — one row per (user, image) at all
        # times, which is the invariant the constraint actually protects.
        return (query if include_binned else live(query)).first()

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

    def soft_delete_item(self, item: WardrobeItem) -> WardrobeItem:
        """Move to the bin. The row and its stored image both survive."""
        item.deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(item)
        return item

    def restore_item(self, item: WardrobeItem) -> WardrobeItem:
        item.deleted_at = None
        self.db.commit()
        self.db.refresh(item)
        return item

    def purge_item(self, item: WardrobeItem) -> None:
        """Irreversible row removal. Callers must delete the stored image
        themselves — the repository does not reach into object storage."""
        self.db.delete(item)
        self.db.commit()

    def expired_binned_items(self, user_id: int, retention: timedelta) -> List[WardrobeItem]:
        """Binned items whose grace window has elapsed.

        Returned rather than deleted here so the caller can remove the stored
        image in the same unit of work; a repository that silently called out
        to S3 would be doing two jobs.
        """
        cutoff = datetime.now(timezone.utc) - retention
        return (
            self.db.query(WardrobeItem)
            .filter(
                WardrobeItem.user_id == user_id,
                WardrobeItem.deleted_at.isnot(None),
                WardrobeItem.deleted_at < cutoff,
            )
            .all()
        )
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
