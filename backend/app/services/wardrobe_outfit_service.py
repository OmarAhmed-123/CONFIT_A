"""Saved wardrobe looks (migration 0048).

A recommendation is only a suggestion until the user keeps it. Saving one
re-runs the same trust rules as recommending (FR-08/FR-09/FR-16):

* every ``wardrobe_item_id`` must belong to the caller, be ``ready`` and not
  be in the bin — anything else is rejected and reported, never stored;
* ``role`` is derived from the garment's *stored* category (which the user can
  correct), not from whatever the client or the model claimed;
* provenance (``source``/``ai_generated``/``model_id``/``prompt_version``) is
  stored verbatim so a saved look keeps saying who assembled it (FR-14);
* reading a look hides garments the user has since binned and reports how
  many were dropped (``dropped_item_count``) instead of showing a stale photo.

Nothing here talks to a model; it is pure persistence + validation.
"""

from __future__ import annotations

import builtins
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError
from backend.app.core.logging import logger
from backend.app.models.wardrobe import WardrobeItem, WardrobeOutfit, WardrobeOutfitItem
from backend.app.schemas.wardrobe_stylist import (
    SavedOutfitItemOut,
    SavedWardrobeOutfitOut,
    SaveWardrobeOutfitRequest,
)
from backend.app.services import wardrobe_taxonomy as taxonomy
from backend.app.services.storage_service import storage_public_url
from backend.app.services.wardrobe_stylist_service import CATEGORY_TO_ROLE, CORE_ROLES

MAX_SAVED_PER_USER = 200


class WardrobeOutfitService:
    def __init__(self, db: Session):
        self.db = db

    # ── write ─────────────────────────────────────────────────────────
    def save(self, user_id: int, req: SaveWardrobeOutfitRequest) -> SavedWardrobeOutfitOut:
        requested_ids: list[int] = []
        for entry in req.items:
            if entry.wardrobe_item_id not in requested_ids:
                requested_ids.append(entry.wardrobe_item_id)

        owned = {
            it.id: it
            for it in self.db.query(WardrobeItem)
            .filter(
                WardrobeItem.user_id == user_id,
                WardrobeItem.id.in_(requested_ids),
                WardrobeItem.deleted_at.is_(None),
            )
            .all()
            if (getattr(it, "processing_status", "ready") or "ready") == "ready"
        }
        rejected = [i for i in requested_ids if i not in owned]
        if rejected:
            # Ids only — never echo titles/paths of rows that are not the caller's.
            logger.warn("wardrobe_outfit_save_rejected_refs", user_id=user_id, count=len(rejected))
        valid_ids = [i for i in requested_ids if i in owned]
        if not valid_ids:
            raise ValidationDomainError(
                "None of the pieces in this look are in your wardrobe any more, so it was not saved."
            )

        count = self.db.query(WardrobeOutfit).filter(WardrobeOutfit.user_id == user_id).count()
        if count >= MAX_SAVED_PER_USER:
            raise ValidationDomainError(
                f"You have reached the limit of {MAX_SAVED_PER_USER} saved wardrobe looks. Delete one to save another."
            )

        reasons = {e.wardrobe_item_id: (e.reason or "").strip()[:400] for e in req.items}
        outfit = WardrobeOutfit(
            user_id=user_id,
            title=req.title.strip(),
            occasion=req.occasion.strip(),
            summary=req.summary.strip(),
            styling_notes_json=json.dumps(req.styling_notes),
            limitations_json=json.dumps(req.limitations),
            missing_categories_json=json.dumps(req.missing_categories),
            context_json=json.dumps(_safe_context(req.context)),
            source=req.source,
            ai_generated=bool(req.ai_generated) if req.source == "watsonx" else False,
            model_id=req.model_id if req.source == "watsonx" else None,
            prompt_version=req.prompt_version if req.source == "watsonx" else None,
            created_at=datetime.now(UTC),
        )
        roles_present: set = set()
        for order, item_id in enumerate(valid_ids):
            it = owned[item_id]
            role = CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory")
            roles_present.add(role)
            outfit.items.append(
                WardrobeOutfitItem(wardrobe_item_id=item_id, role=role, reason=reasons.get(item_id, ""), sort_order=order)
            )
        outfit.is_complete = _is_complete(roles_present)
        self.db.add(outfit)
        self.db.commit()
        self.db.refresh(outfit)
        logger.info(
            "wardrobe_outfit_saved", user_id=user_id, outfit_id=outfit.id, items=len(valid_ids),
            source=outfit.source, model_id=outfit.model_id,
        )
        return self._to_out(outfit, rejected=rejected)

    def delete(self, user_id: int, outfit_id: int) -> None:
        outfit = self._owned(user_id, outfit_id)
        self.db.delete(outfit)
        self.db.commit()
        logger.info("wardrobe_outfit_deleted", user_id=user_id, outfit_id=outfit_id)

    # ── read ──────────────────────────────────────────────────────────
    def list(self, user_id: int, limit: int = 50) -> builtins.list[SavedWardrobeOutfitOut]:
        rows = (
            self.db.query(WardrobeOutfit)
            .options(joinedload(WardrobeOutfit.items).joinedload(WardrobeOutfitItem.wardrobe_item))
            .filter(WardrobeOutfit.user_id == user_id)
            .order_by(WardrobeOutfit.created_at.desc(), WardrobeOutfit.id.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return [self._to_out(o) for o in rows]

    def get(self, user_id: int, outfit_id: int) -> SavedWardrobeOutfitOut:
        return self._to_out(self._owned(user_id, outfit_id))

    # ── internals ─────────────────────────────────────────────────────
    def _owned(self, user_id: int, outfit_id: int) -> WardrobeOutfit:
        outfit = (
            self.db.query(WardrobeOutfit)
            .options(joinedload(WardrobeOutfit.items).joinedload(WardrobeOutfitItem.wardrobe_item))
            .filter(WardrobeOutfit.id == outfit_id, WardrobeOutfit.user_id == user_id)
            .first()
        )
        if outfit is None:
            # Same 404 whether the id is foreign or absent (no existence oracle).
            raise ResourceNotFoundError("Saved look", outfit_id)
        return outfit

    @staticmethod
    def _to_out(outfit: WardrobeOutfit, rejected: builtins.list[int] | None = None) -> SavedWardrobeOutfitOut:
        items: list[SavedOutfitItemOut] = []
        dropped = 0
        for row in sorted(outfit.items, key=lambda r: r.sort_order):
            it = row.wardrobe_item
            if it is None or it.deleted_at is not None:
                dropped += 1
                continue
            items.append(
                SavedOutfitItemOut(
                    wardrobe_item_id=it.id,
                    role=row.role if row.role in CATEGORY_TO_ROLE.values() else "accessory",
                    category=taxonomy.normalize_category(it.category),
                    title=it.title,
                    subcategory=it.subcategory,
                    color_name=it.color_name,
                    color_hex=it.color_hex or "#000000",
                    image_url=storage_public_url(it.image_url),
                    reason=row.reason or "",
                    analysis_source=getattr(it, "analysis_source", None),
                )
            )
        created = outfit.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return SavedWardrobeOutfitOut(
            id=outfit.id,
            title=outfit.title,
            occasion=outfit.occasion,
            summary=outfit.summary or "",
            items=items,
            styling_notes=_loads(outfit.styling_notes_json, []),
            limitations=_loads(outfit.limitations_json, []),
            missing_categories=_loads(outfit.missing_categories_json, []),
            context=_loads(outfit.context_json, {}),
            is_complete=bool(outfit.is_complete) and dropped == 0,
            source=outfit.source,
            ai_generated=bool(outfit.ai_generated),
            model_id=outfit.model_id,
            prompt_version=outfit.prompt_version,
            created_at=(created or datetime.now(UTC)).isoformat(),
            dropped_item_count=dropped,
            rejected_references=list(rejected or []),
        )


def _is_complete(roles: set) -> bool:
    if "dress" in roles:
        return "footwear" in roles
    return all(r in roles for r in CORE_ROLES)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        value = json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


_CONTEXT_KEYS = (
    "occasion", "time_of_day", "season", "location", "activity", "dress_code",
    "style_preferences", "color_preferences", "comfort_needs", "exclusions", "language",
)


def _safe_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Keep only the styling inputs (bounded), never arbitrary client blobs."""
    out: dict[str, Any] = {}
    for k in _CONTEXT_KEYS:
        v = ctx.get(k) if isinstance(ctx, dict) else None
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:200]
        elif isinstance(v, list):
            out[k] = [str(x).strip()[:60] for x in v[:8] if str(x).strip()]
    return out
