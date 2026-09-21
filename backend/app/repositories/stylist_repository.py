import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from backend.app.models.stylist import StylistSession, StylistMessage, Outfit, OutfitItem
from backend.app.models.catalog import Product


class StylistRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_session(self, user_id: Optional[int], session_id: Optional[int] = None) -> StylistSession:
        if session_id:
            query = self.db.query(StylistSession).filter(StylistSession.id == session_id)
            if user_id is not None:
                query = query.filter(StylistSession.user_id == user_id)
            session = query.first()
            if session:
                return session
        new_session = StylistSession(user_id=user_id, session_title="Personal AI Styling")
        self.db.add(new_session)
        self.db.commit()
        self.db.refresh(new_session)
        return new_session

    def get_session_history(self, session_id: int) -> Optional[StylistSession]:
        return (
            self.db.query(StylistSession)
            .options(joinedload(StylistSession.messages))
            .filter(StylistSession.id == session_id)
            .first()
        )

    def add_message(
        self,
        session_id: int,
        sender: str,
        content: str,
        audio_url: Optional[str] = None,
        intent_json: Optional[Dict[str, Any]] = None,
        recommendations_json: Optional[List[Dict[str, Any]]] = None
    ) -> StylistMessage:
        msg = StylistMessage(
            session_id=session_id,
            sender=sender,
            content=content,
            audio_url=audio_url,
            intent_json=json.dumps(intent_json or {}, default=str),
            recommendations_json=json.dumps(recommendations_json or [], default=str)
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_user_outfits(self, user_id: int, saved_only: bool = False) -> List[Outfit]:
        query = self.db.query(Outfit).options(
            joinedload(Outfit.items).joinedload(OutfitItem.product).joinedload(Product.brand),
            joinedload(Outfit.items).joinedload(OutfitItem.product).joinedload(Product.category)
        ).filter(Outfit.user_id == user_id)
        if saved_only:
            query = query.filter(Outfit.is_saved == True)
        return query.order_by(Outfit.created_at.desc()).all()

    def get_outfit_by_share_token(self, share_token: str) -> Optional[Outfit]:
        """Look up a shared outfit by its public token (items eager-loaded)."""
        return (
            self.db.query(Outfit)
            .options(joinedload(Outfit.items))
            .filter(Outfit.share_token == share_token)
            .first()
        )

    def get_outfit_by_id(self, outfit_id: int) -> Optional[Outfit]:
        return (
            self.db.query(Outfit)
            .options(
                joinedload(Outfit.items).joinedload(OutfitItem.product).joinedload(Product.brand),
                joinedload(Outfit.items).joinedload(OutfitItem.product).joinedload(Product.category),
                joinedload(Outfit.items).joinedload(OutfitItem.sku)
            )
            .filter(Outfit.id == outfit_id)
            .first()
        )

    def replace_outfit_items(
        self,
        outfit_id: int,
        items: List[Dict[str, Any]],
        total_price,
        compatibility_score: int,
        color_palette: List[str],
    ) -> Optional[Outfit]:
        """Swap an outfit's entire item set atomically.

        One transaction: delete the old rows, insert the new ones, refresh the
        derived aggregates (price, palette, score) and stamp updated_at. A
        failure anywhere rolls the whole thing back, so the canvas can never
        observe a half-edited look. sort_order comes pre-computed from the
        shared composition policy.
        """
        outfit = self.db.query(Outfit).filter(Outfit.id == outfit_id).first()
        if not outfit:
            return None
        try:
            # Expire the loaded collection before the bulk delete so the
            # identity map cannot resurrect stale OutfitItem instances during
            # the subsequent flush (SAWarning: identity map already had ...).
            self.db.query(OutfitItem).filter(
                OutfitItem.outfit_id == outfit_id
            ).delete(synchronize_session="fetch")
            self.db.expire(outfit, ["items"])
            for idx, item in enumerate(items):
                self.db.add(OutfitItem(
                    outfit_id=outfit_id,
                    product_id=item["product_id"],
                    product_sku_id=item.get("product_sku_id"),
                    position=item.get("position", "top"),
                    sort_order=item.get("sort_order", idx),
                ))
            outfit.total_price = total_price
            outfit.compatibility_score = compatibility_score
            outfit.color_palette = json.dumps(color_palette)
            outfit.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(outfit)
        return outfit

    def delete_outfit(self, outfit_id: int) -> bool:
        outfit = self.db.query(Outfit).filter(Outfit.id == outfit_id).first()
        if not outfit:
            return False
        self.db.delete(outfit)  # OutfitItem rows cascade (all, delete-orphan)
        self.db.commit()
        return True

    def save_outfit(
        self,
        user_id: Optional[int],
        title: str,
        occasion: str,
        compatibility_score: int,
        total_price: float,
        color_palette: List[str],
        style_tags: List[str],
        items: List[Dict[str, Any]],
        is_saved: bool = True,
        is_system_curated: bool = False,
        description: Optional[str] = None
    ) -> Outfit:
        outfit = Outfit(
            user_id=user_id,
            title=title,
            description=description,
            occasion=occasion,
            compatibility_score=compatibility_score,
            total_price=total_price,
            color_palette=json.dumps(color_palette),
            style_tags=json.dumps(style_tags),
            is_saved=is_saved,
            is_system_curated=is_system_curated
        )
        self.db.add(outfit)
        self.db.flush()

        for idx, item in enumerate(items):
            outfit_item = OutfitItem(
                outfit_id=outfit.id,
                product_id=item["product_id"],
                product_sku_id=item.get("product_sku_id"),
                position=item.get("position", "top"),
                sort_order=idx
            )
            self.db.add(outfit_item)

        self.db.commit()
        self.db.refresh(outfit)
        return outfit
