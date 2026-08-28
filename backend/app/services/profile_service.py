import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.profile import UserStyleProfile
from backend.app.repositories.profile_repository import ProfileRepository


class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.profile_repo = ProfileRepository(db)

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        usp = self.profile_repo.get_by_user_id(user_id)
        if not usp:
            return None
        return self._format_usp(usp)

    def save_quiz_and_preferences(self, user_id: int, quiz_data: Dict[str, Any]) -> Dict[str, Any]:
        usp = self.profile_repo.create_or_update_profile(user_id, quiz_data)
        return self._format_usp(usp)

    def _format_usp(self, usp: UserStyleProfile) -> Dict[str, Any]:
        body_dict = self.profile_repo.get_decrypted_body_data(usp)

        try:
            archetypes = json.loads(usp.style_archetypes)
        except Exception:
            archetypes = []

        try:
            colors = json.loads(usp.preferred_colors)
        except Exception:
            colors = []

        try:
            avoided = json.loads(usp.avoided_colors)
        except Exception:
            avoided = []

        try:
            aesthetics = json.loads(usp.fashion_aesthetics)
        except Exception:
            aesthetics = []

        try:
            brands = json.loads(usp.preferred_brands)
        except Exception:
            brands = []

        try:
            blacklisted = json.loads(usp.blacklisted_brands)
        except Exception:
            blacklisted = []

        try:
            occ_weights = json.loads(usp.occasion_weights)
        except Exception:
            occ_weights = {"work": 0.35, "casual": 0.35, "party": 0.2, "sports": 0.1}

        return {
            "id": usp.id,
            "user_id": usp.user_id,
            "style_archetypes": archetypes,
            "preferred_colors": colors,
            "avoided_colors": avoided,
            "fashion_aesthetics": aesthetics,
            "budget_monthly_min": usp.budget_monthly_min,
            "budget_monthly_max": usp.budget_monthly_max,
            "budget_per_outfit_max": usp.budget_per_outfit_max,
            "preferred_brands": brands,
            "blacklisted_brands": blacklisted,
            "occasion_weights": occ_weights,
            "size_tops": usp.size_tops,
            "size_bottoms": usp.size_bottoms,
            "size_shoes": usp.size_shoes,
            "fit_preference": usp.fit_preference,
            "body_shape_tag": usp.body_shape_tag,
            "body_attributes": {**body_dict, "is_encrypted": True} if body_dict else None,
            "onboarding_completed": usp.onboarding_completed,
            "privacy_consent_tryon_storage": usp.privacy_consent_tryon_storage,
            "privacy_consent_share_with_brands": usp.privacy_consent_share_with_brands,
            "updated_at": usp.updated_at
        }
