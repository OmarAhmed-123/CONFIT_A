import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from backend.app.models.tryon import TryOnSession, VisualSearchQuery
from backend.app.models.catalog import Product


class TryOnRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_tryon_session(
        self,
        product_id: Optional[int],
        input_user_image_url: str,
        garment_image_url: Optional[str] = None,
        rendered_result_url: Optional[str] = None,
        applied_items: Optional[List[Dict[str, Any]]] = None,
        slot_mapping: Optional[Dict[str, int]] = None,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None,
        outfit_id: Optional[int] = None,
        fit_verdict: str = "True to Size",
        fit_confidence_score: int = 95,
        body_scaling_factor: float = 1.0,
        consent_retained: bool = False,
        expiry_hours: int = 24
    ) -> TryOnSession:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours) if not consent_retained else None
        session = TryOnSession(
            user_id=user_id,
            guest_session_token=guest_token,
            product_id=product_id,
            outfit_id=outfit_id,
            input_user_image_url=input_user_image_url,
            garment_image_url=garment_image_url or (applied_items[0]["image_url"] if applied_items else None),
            rendered_result_url=rendered_result_url,
            applied_items_json=json.dumps(applied_items or []),
            slot_mapping_json=json.dumps(slot_mapping or {}),
            layering_order_json=json.dumps([it.get("position") for it in (applied_items or [])]),
            status="completed",
            body_fit_verdict=fit_verdict,
            fit_confidence_score=fit_confidence_score,
            body_scaling_factor=body_scaling_factor,
            consent_retained=consent_retained,
            expires_at=expires_at
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_tryon_session(self, session_id: int) -> Optional[TryOnSession]:
        return (
            self.db.query(TryOnSession)
            .filter(TryOnSession.id == session_id)
            .first()
        )

    def purge_session(self, session_id: int) -> bool:
        sess = self.get_tryon_session(session_id)
        if sess:
            self.db.delete(sess)
            self.db.commit()
            return True
        return False

    def log_visual_search(
        self,
        input_image_url: str,
        user_id: Optional[int],
        detected_category: str,
        detected_color: str,
        detected_pattern: str,
        detected_style: str,
        detected_attributes: Dict[str, Any],
        matches: List[Dict[str, Any]]
    ) -> VisualSearchQuery:
        query = VisualSearchQuery(
            user_id=user_id,
            input_image_url=input_image_url,
            detected_category=detected_category,
            detected_color=detected_color,
            detected_pattern=detected_pattern,
            detected_style=detected_style,
            detected_attributes_json=json.dumps(detected_attributes),
            matches_json=json.dumps(matches)
        )
        self.db.add(query)
        self.db.commit()
        self.db.refresh(query)
        return query
