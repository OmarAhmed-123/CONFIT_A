import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.tryon import TryOnSession, VisualSearchQuery


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
            user_image_url=input_user_image_url,
            input_user_image_url=input_user_image_url,
            garment_image_url=garment_image_url or (applied_items[0]["image_url"] if applied_items else None),
            rendered_image_url=rendered_result_url,
            rendered_result_url=rendered_result_url,
            applied_items_json=json.dumps(applied_items or []),
            slot_mapping_json=json.dumps(slot_mapping or {}),
            layering_order_json=json.dumps([it.get("position") for it in (applied_items or [])]),
            status="completed",
            fit_verdict=fit_verdict,
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

    def get_tryon_session(
        self,
        session_id: int,
    ) -> Optional[TryOnSession]:
        """INTERNAL fetch only — returns the row or None.

        This performs NO end-user authorization. It exists solely so an
        already-authorized call site (which has passed
        ``get_owned_tryon_session``) can re-fetch a row it is entitled to.
        Never call this from a controller-facing read/mutation to decide
        access — ``get_owned_tryon_session`` is the single fail-closed
        ownership gate for try-on sessions.
        """
        return (
            self.db.query(TryOnSession)
            .filter(TryOnSession.id == session_id)
            .first()
        )

    def get_owned_tryon_session(
        self,
        session_id: int,
        caller_user_id: Optional[int] = None,
        guest_session_token: Optional[str] = None,
    ) -> TryOnSession:
        """CANONICAL fail-closed ownership resolution for try-on sessions.

        The single authorization path for EVERY try-on session read/mutation
        (GET, apply, remove, reorder, measurements, purge). Mirrors
        MeasurementSessionService._resolve_owned_session: a session is owned by
        the authenticated user it was bound to, or by the holder of the guest
        token it was bound to. Everything else — no identity, a non-owner, a
        mismatched or absent token — is 404 (fail-closed; does not leak
        existence). Never trust a client's claim of ownership other than the
        server-issued guest token the session was actually bound to.
        """
        from backend.app.core.exceptions import ResourceNotFoundError
        sess = (
            self.db.query(TryOnSession)
            .filter(TryOnSession.id == session_id)
            .first()
        )
        if sess is None:
            raise ResourceNotFoundError("TryOnSession", session_id)
        # Authenticated owner.
        if (
            caller_user_id is not None
            and sess.user_id is not None
            and sess.user_id == caller_user_id
        ):
            return sess
        # Guest owner: a user-bound session can never be reached via a token,
        # and a guest session is reachable only with its exact bound token.
        if (
            guest_session_token
            and sess.user_id is None
            and sess.guest_session_token
            and sess.guest_session_token == guest_session_token
        ):
            return sess
        # Fail closed: non-owner, anonymous, cross-guest, cross-user, or a
        # user touching a guest session.
        raise ResourceNotFoundError("TryOnSession", session_id)

    def purge_session(
        self,
        session_id: int,
        caller_user_id: Optional[int] = None,
        guest_session_token: Optional[str] = None,
    ) -> bool:
        # Authorize first via the canonical fail-closed gate (raises 404 if the
        # caller does not own the session); never deletes another's session.
        sess = self.get_owned_tryon_session(
            session_id,
            caller_user_id=caller_user_id,
            guest_session_token=guest_session_token,
        )
        self.db.delete(sess)
        self.db.commit()
        return True

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
