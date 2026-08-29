"""ProfileRepository — Group 1 USP persistence.

Fixes across the audit findings:
 - No side-effecting write on read (spec §33). Missing profile → None.
 - Body attributes only written when the payload contains at least one
   real value (§18/§25). No fabricated defaults.
 - `blacklisted_brands` and `fashion_aesthetics` actually persisted — the
   previous repo silently dropped them (audit §2.4 PREF-03, §2.2 STY-05).
 - Server-side value validation via canonical registries (§22).
 - `get_decrypted_body_data` propagates decryption failures as
   EncryptionError instead of returning garbled ciphertext (§19).
"""
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.profile import UserStyleProfile
from backend.app.core.security import encrypt_sensitive_data, decrypt_sensitive_data
from backend.app.core.exceptions import EncryptionError, ValidationDomainError
from backend.app.core.logging import logger
from backend.app.schemas.profile import (
    SUPPORTED_STYLE_ARCHETYPES,
    SUPPORTED_FASHION_AESTHETICS,
    SUPPORTED_FIT,
    SUPPORTED_BODY_SHAPES,
    SUPPORTED_OCCASIONS,
    _validate_subset,
)


def _validate_payload(profile_data: Dict[str, Any]) -> None:
    if "style_archetypes" in profile_data and profile_data["style_archetypes"] is not None:
        _validate_subset(profile_data["style_archetypes"], SUPPORTED_STYLE_ARCHETYPES, "style_archetypes")
    if "fashion_aesthetics" in profile_data and profile_data["fashion_aesthetics"] is not None:
        _validate_subset(profile_data["fashion_aesthetics"], SUPPORTED_FASHION_AESTHETICS, "fashion_aesthetics")
    if "fit_preference" in profile_data and profile_data["fit_preference"] is not None:
        if profile_data["fit_preference"] not in SUPPORTED_FIT:
            raise ValidationDomainError(
                f"Unsupported fit_preference: {profile_data['fit_preference']!r}",
                field_errors={"fit_preference": profile_data["fit_preference"]},
            )
    if "occasion_weights" in profile_data and profile_data["occasion_weights"] is not None:
        unknown = [k for k in profile_data["occasion_weights"].keys() if k not in SUPPORTED_OCCASIONS]
        if unknown:
            raise ValidationDomainError(
                f"Unsupported occasion keys: {unknown}",
                field_errors={"occasion_weights": unknown},
            )
    if "body_attributes" in profile_data and profile_data["body_attributes"]:
        body_shape = profile_data["body_attributes"].get("body_shape") if isinstance(profile_data["body_attributes"], dict) else None
        if body_shape and body_shape not in SUPPORTED_BODY_SHAPES:
            raise ValidationDomainError(
                f"Unsupported body_shape: {body_shape!r}",
                field_errors={"body_shape": body_shape},
            )


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    # ---- reads --------------------------------------------------------------
    def get_by_user_id(self, user_id: int) -> Optional[UserStyleProfile]:
        return self.db.query(UserStyleProfile).filter(UserStyleProfile.user_id == user_id).first()

    def get_decrypted_body_data(self, usp: UserStyleProfile) -> Dict[str, Any]:
        """Return the plaintext body dict for an authorized caller.

        On decryption failure this raises EncryptionError, which the outer
        exception handler turns into a controlled 500 response. Previously
        it silently returned the ciphertext, which leaked base64 blobs
        into API bodies pretending to be plaintext body measurements
        (audit finding G1.BODY-02).
        """
        if not usp.encrypted_body_data:
            return {}
        try:
            raw = decrypt_sensitive_data(usp.encrypted_body_data)
        except EncryptionError:
            # Log a diagnostic marker without any ciphertext content, then
            # propagate so the caller does not silently succeed.
            logger.error(
                "Body-data decryption failed", user_id=usp.user_id, profile_id=usp.id
            )
            raise
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise EncryptionError(reason=f"body_payload_not_json:{type(exc).__name__}") from exc

    # ---- writes -------------------------------------------------------------
    def create_or_update_profile(
        self, user_id: int, profile_data: Dict[str, Any]
    ) -> UserStyleProfile:
        _validate_payload(profile_data)

        usp = self.get_by_user_id(user_id)
        created_now = False
        if not usp:
            usp = UserStyleProfile(user_id=user_id)
            self.db.add(usp)
            created_now = True

        # JSON list columns
        for key in (
            "style_archetypes",
            "preferred_colors",
            "avoided_colors",
            "fashion_aesthetics",
            "preferred_brands",
            "blacklisted_brands",
        ):
            if key in profile_data and profile_data[key] is not None:
                setattr(usp, key, json.dumps(profile_data[key]))

        # Scalar columns
        for key in (
            "budget_monthly_min",
            "budget_monthly_max",
            "budget_per_outfit_max",
            "size_tops",
            "size_bottoms",
            "size_shoes",
            "fit_preference",
            "privacy_consent_tryon_storage",
            "privacy_consent_share_with_brands",
        ):
            if key in profile_data and profile_data[key] is not None:
                setattr(usp, key, profile_data[key])

        # occasion_weights is JSON but the model column is Text — dump it
        if "occasion_weights" in profile_data and profile_data["occasion_weights"] is not None:
            usp.occasion_weights = json.dumps(profile_data["occasion_weights"])

        # Body attributes — only encrypt when at least one real value present.
        if "body_attributes" in profile_data and profile_data["body_attributes"]:
            body_dict = profile_data["body_attributes"]
            if hasattr(body_dict, "model_dump"):
                body_dict = body_dict.model_dump(exclude_unset=True)
            body_dict = {k: v for k, v in body_dict.items() if v is not None}
            if body_dict:
                # Merge with prior encrypted values so a PATCH to `waist_cm`
                # alone does not wipe `height_cm`.
                if usp.encrypted_body_data:
                    try:
                        prior = json.loads(decrypt_sensitive_data(usp.encrypted_body_data))
                    except EncryptionError:
                        prior = {}
                    merged = {**prior, **body_dict}
                else:
                    merged = body_dict
                usp.encrypted_body_data = encrypt_sensitive_data(json.dumps(merged))
                if "body_shape" in merged and merged["body_shape"]:
                    usp.body_shape_tag = merged["body_shape"]

        # Onboarding completed only when the caller actually submitted the
        # full quiz (POST /profile/onboarding-quiz uses `OnboardingQuizInput`
        # which always includes at least one of the wizard steps). A pure
        # single-field PATCH (e.g. `/me/budget`) does NOT mark onboarding
        # as complete — respect the state the user explicitly reached.
        if profile_data.get("_mark_onboarding_completed"):
            usp.onboarding_completed = True

        usp.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(usp)
        return usp

    def delete_body_attributes(self, user_id: int) -> None:
        usp = self.get_by_user_id(user_id)
        if not usp:
            return
        usp.encrypted_body_data = None
        usp.body_shape_tag = None
        usp.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    # ---- consent ------------------------------------------------------------
    def get_consent_state(self, user_id: int) -> Dict[str, Any]:
        usp = self.get_by_user_id(user_id)
        if not usp:
            return {
                "user_id": user_id,
                "photo_storage": False,
                "ai_personalization": False,
                "marketing_analytics": False,
                "share_with_brands": False,
                "policy_version": 3,
                "last_agreed_at": None,
            }
        return {
            "user_id": user_id,
            "photo_storage": bool(usp.privacy_consent_tryon_storage),
            "ai_personalization": bool(getattr(usp, "consent_ai_personalization", True)),
            "marketing_analytics": bool(getattr(usp, "consent_marketing_analytics", False)),
            "share_with_brands": bool(usp.privacy_consent_share_with_brands),
            "policy_version": int(getattr(usp, "consent_policy_version", 3) or 3),
            "last_agreed_at": getattr(usp, "consent_last_agreed_at", None) or usp.updated_at,
        }

    def update_consent_state(self, user_id: int, changes: Dict[str, Any]) -> Dict[str, Any]:
        usp = self.get_by_user_id(user_id)
        if not usp:
            usp = UserStyleProfile(user_id=user_id)
            self.db.add(usp)

        if "photo_storage" in changes and changes["photo_storage"] is not None:
            usp.privacy_consent_tryon_storage = bool(changes["photo_storage"])
        if "share_with_brands" in changes and changes["share_with_brands"] is not None:
            usp.privacy_consent_share_with_brands = bool(changes["share_with_brands"])
        if hasattr(usp, "consent_ai_personalization") and "ai_personalization" in changes:
            usp.consent_ai_personalization = bool(changes["ai_personalization"])
        if hasattr(usp, "consent_marketing_analytics") and "marketing_analytics" in changes:
            usp.consent_marketing_analytics = bool(changes["marketing_analytics"])
        if hasattr(usp, "consent_last_agreed_at"):
            usp.consent_last_agreed_at = datetime.now(timezone.utc)

        usp.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(usp)
        return self.get_consent_state(user_id)
