import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.profile import UserStyleProfile
from backend.app.core.security import encrypt_sensitive_data, decrypt_sensitive_data


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: int) -> Optional[UserStyleProfile]:
        return self.db.query(UserStyleProfile).filter(UserStyleProfile.user_id == user_id).first()

    def create_or_update_profile(self, user_id: int, profile_data: Dict[str, Any]) -> UserStyleProfile:
        usp = self.get_by_user_id(user_id)
        if not usp:
            usp = UserStyleProfile(user_id=user_id)
            self.db.add(usp)

        if "style_archetypes" in profile_data:
            usp.style_archetypes = json.dumps(profile_data["style_archetypes"])
        if "preferred_colors" in profile_data:
            usp.preferred_colors = json.dumps(profile_data["preferred_colors"])
        if "avoided_colors" in profile_data:
            usp.avoided_colors = json.dumps(profile_data["avoided_colors"])
        if "fashion_aesthetics" in profile_data:
            usp.fashion_aesthetics = json.dumps(profile_data["fashion_aesthetics"])
        if "budget_monthly_min" in profile_data:
            usp.budget_monthly_min = profile_data["budget_monthly_min"]
        if "budget_monthly_max" in profile_data:
            usp.budget_monthly_max = profile_data["budget_monthly_max"]
        if "budget_per_outfit_max" in profile_data:
            usp.budget_per_outfit_max = profile_data["budget_per_outfit_max"]
        if "preferred_brands" in profile_data:
            usp.preferred_brands = json.dumps(profile_data["preferred_brands"])
        if "occasion_weights" in profile_data:
            usp.occasion_weights = json.dumps(profile_data["occasion_weights"])
        if "size_tops" in profile_data:
            usp.size_tops = profile_data["size_tops"]
        if "size_bottoms" in profile_data:
            usp.size_bottoms = profile_data["size_bottoms"]
        if "size_shoes" in profile_data:
            usp.size_shoes = profile_data["size_shoes"]
        if "fit_preference" in profile_data:
            usp.fit_preference = profile_data["fit_preference"]
        if "privacy_consent_tryon_storage" in profile_data:
            usp.privacy_consent_tryon_storage = profile_data["privacy_consent_tryon_storage"]
        if "privacy_consent_share_with_brands" in profile_data:
            usp.privacy_consent_share_with_brands = profile_data["privacy_consent_share_with_brands"]

        # Handle Encrypted Body Data (G1.3)
        if "body_attributes" in profile_data and profile_data["body_attributes"]:
            body_dict = profile_data["body_attributes"]
            if hasattr(body_dict, "model_dump"):
                body_dict = body_dict.model_dump()
            usp.encrypted_body_data = encrypt_sensitive_data(json.dumps(body_dict))
            if "body_shape" in body_dict and body_dict["body_shape"]:
                usp.body_shape_tag = body_dict["body_shape"]

        usp.onboarding_completed = True
        self.db.commit()
        self.db.refresh(usp)
        return usp

    def get_decrypted_body_data(self, usp: UserStyleProfile) -> Dict[str, Any]:
        if not usp.encrypted_body_data:
            return {}
        try:
            raw = decrypt_sensitive_data(usp.encrypted_body_data)
            return json.loads(raw)
        except Exception:
            return {}
