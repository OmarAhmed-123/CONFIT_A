"""ProfileService — orchestrates USP reads/writes.

Notably:
 - `get_profile` returns None for missing profiles (spec §33); the
   controller decides whether to redirect to onboarding.
 - `save_quiz_and_preferences` accepts an OnboardingQuizInput payload OR a
   split-DTO payload; the repository writes only fields that are present.
 - Onboarding completion is set only when the caller is the onboarding
   endpoint (we tag the payload internally).
"""
import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.profile import UserStyleProfile, UserWishlistItem
from backend.app.models.catalog import Product
from backend.app.models.catalog_import import BrandAnalyticsEvent
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.core.exceptions import ResourceNotFoundError


class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.profile_repo = ProfileRepository(db)

    # ---- USP ---------------------------------------------------------------
    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        usp = self.profile_repo.get_by_user_id(user_id)
        if not usp:
            return None
        return self._format_usp(usp)

    def save_quiz_and_preferences(
        self, user_id: int, quiz_data: Dict[str, Any], *, is_onboarding: bool = False
    ) -> Dict[str, Any]:
        # Tag the payload so the repository can flip onboarding_completed
        # only for the full-quiz submission path. Split PATCHes to /me/*
        # deliberately do NOT complete onboarding.
        #
        # The default is FAIL-CLOSED (False) on purpose. It used to default to
        # True, and every split PATCH (`/me/budget`, `/me/size-fit`, ...)
        # called this helper without the keyword — so saving a single budget
        # field marked the whole wizard complete. That is the same lie as the
        # `has_profile` gate this slice removes: a shopper who never finished
        # onboarding would be told they had. Only the endpoint that actually
        # receives the full wizard payload may opt in, explicitly.
        payload = dict(quiz_data)
        if is_onboarding:
            payload["_mark_onboarding_completed"] = True
        usp = self.profile_repo.create_or_update_profile(user_id, payload)
        return self._format_usp(usp)

    def delete_body_attributes(self, user_id: int) -> None:
        self.profile_repo.delete_body_attributes(user_id)

    # ---- Consent -----------------------------------------------------------
    def get_consents(self, user_id: int) -> Dict[str, Any]:
        return self.profile_repo.get_consent_state(user_id)

    def update_consents(self, user_id: int, changes: Dict[str, Any]) -> Dict[str, Any]:
        return self.profile_repo.update_consent_state(user_id, changes)

    # ---- Account Wishlist / Favorites ( strictly isolated per user_id ) -----
    def get_wishlist(self, user_id: int) -> list[int]:
        rows = (
            self.db.query(UserWishlistItem.product_id)
            .join(Product, Product.id == UserWishlistItem.product_id)
            .filter(UserWishlistItem.user_id == user_id)
            .order_by(UserWishlistItem.created_at.desc(), UserWishlistItem.id.desc())
            .all()
        )
        return [int(r[0]) for r in rows]

    def add_wishlist_item(self, user_id: int, product_id: int) -> list[int]:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ResourceNotFoundError("Product", product_id)
        existing = (
            self.db.query(UserWishlistItem)
            .filter(
                UserWishlistItem.user_id == user_id,
                UserWishlistItem.product_id == product_id,
            )
            .first()
        )
        if not existing:
            self.db.add(UserWishlistItem(user_id=user_id, product_id=product_id))
            evt_id = f"wishlist:{user_id}:{product_id}"
            if not self.db.query(BrandAnalyticsEvent.id).filter_by(event_id=evt_id).first():
                self.db.add(
                    BrandAnalyticsEvent(
                        event_id=evt_id,
                        brand_id=product.brand_id,
                        product_id=product.id,
                        user_id=user_id,
                        event_type="wishlist_save",
                        attribution_source="wishlist",
                        event_metadata_json="{}",
                    )
                )
            self.db.commit()
        return self.get_wishlist(user_id)

    def remove_wishlist_item(self, user_id: int, product_id: int) -> list[int]:
        (
            self.db.query(UserWishlistItem)
            .filter(
                UserWishlistItem.user_id == user_id,
                UserWishlistItem.product_id == product_id,
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return self.get_wishlist(user_id)

    def sync_wishlist(self, user_id: int, product_ids: list[int]) -> list[int]:
        cleaned: list[int] = []
        seen: set[int] = set()
        for raw in product_ids:
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 and raw not in seen:
                seen.add(raw)
                cleaned.append(raw)
        if cleaned:
            valid_products = (
                self.db.query(Product.id, Product.brand_id)
                .filter(Product.id.in_(cleaned))
                .all()
            )
            valid_map = {int(pid): int(bid) for pid, bid in valid_products}
            already = {
                int(r[0])
                for r in self.db.query(UserWishlistItem.product_id)
                .filter(
                    UserWishlistItem.user_id == user_id,
                    UserWishlistItem.product_id.in_(list(valid_map.keys())),
                )
                .all()
            }
            for pid in cleaned:
                if pid in valid_map and pid not in already:
                    self.db.add(UserWishlistItem(user_id=user_id, product_id=pid))
                    evt_id = f"wishlist:{user_id}:{pid}"
                    if not self.db.query(BrandAnalyticsEvent.id).filter_by(event_id=evt_id).first():
                        self.db.add(
                            BrandAnalyticsEvent(
                                event_id=evt_id,
                                brand_id=valid_map[pid],
                                product_id=pid,
                                user_id=user_id,
                                event_type="wishlist_save",
                                attribution_source="wishlist_sync",
                                event_metadata_json="{}",
                            )
                        )
            self.db.commit()
        return self.get_wishlist(user_id)

    # ---- Formatting --------------------------------------------------------
    def _format_usp(self, usp: UserStyleProfile) -> Dict[str, Any]:
        try:
            body_dict = self.profile_repo.get_decrypted_body_data(usp)
        except Exception:
            # If decryption fails, propagate — this fires a controlled 500
            # rather than serving ciphertext (audit finding G1.BODY-02).
            raise

        def _load(field: str, default):
            raw = getattr(usp, field, None)
            if not raw:
                return default
            try:
                return json.loads(raw)
            except Exception:
                return default

        return {
            "id": usp.id,
            "user_id": usp.user_id,
            "style_archetypes": _load("style_archetypes", []),
            "preferred_colors": _load("preferred_colors", []),
            "avoided_colors": _load("avoided_colors", []),
            "fashion_aesthetics": _load("fashion_aesthetics", []),
            "budget_monthly_min": usp.budget_monthly_min,
            "budget_monthly_max": usp.budget_monthly_max,
            "budget_per_outfit_max": usp.budget_per_outfit_max,
            "preferred_brands": _load("preferred_brands", []),
            "blacklisted_brands": _load("blacklisted_brands", []),
            "occasion_weights": _load("occasion_weights", {}),
            "size_tops": usp.size_tops,
            "size_bottoms": usp.size_bottoms,
            "size_shoes": usp.size_shoes,
            "fit_preference": usp.fit_preference,
            "body_shape_tag": usp.body_shape_tag,
            "body_attributes": {**body_dict, "is_encrypted": True} if body_dict else None,
            "onboarding_completed": bool(usp.onboarding_completed),
            "privacy_consent_tryon_storage": bool(usp.privacy_consent_tryon_storage),
            "privacy_consent_share_with_brands": bool(usp.privacy_consent_share_with_brands),
            "updated_at": usp.updated_at,
        }
