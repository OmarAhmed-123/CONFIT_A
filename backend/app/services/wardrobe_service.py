import base64
import hashlib
import json
import os
import uuid
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, ProviderIntegrationError
from backend.app.core.logging import logger
from backend.app.models.wardrobe import WardrobeItem
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.services import wardrobe_taxonomy as taxonomy

# Image contract shared by single + bulk upload paths.
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB, matches the vision provider limit


class WardrobeService:
    def __init__(self, db: Session):
        self.db = db
        self.wardrobe_repo = WardrobeRepository(db)

    # ────────────────────────── reads ──────────────────────────
    def get_user_wardrobe(self, user_id: int, category: Optional[str] = None) -> List[Dict[str, Any]]:
        items = self.wardrobe_repo.get_user_items(user_id, category)
        return [self._to_dict(it) for it in items]

    def get_item(self, user_id: int, item_id: int) -> WardrobeItem:
        item = self.wardrobe_repo.get_item_by_id(item_id, user_id)
        if not item:
            raise ResourceNotFoundError("WardrobeItem", item_id)
        return item

    # ─────────────────────── manual create ─────────────────────
    def add_item(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an item from user-supplied metadata (no image pipeline).

        Metadata-complete items are born 'ready' — there is nothing to
        process. Category/color/occasions are normalized onto the controlled
        taxonomy so downstream matching (duplicate detection, gap analysis)
        works uniformly regardless of input casing.
        """
        item = self.wardrobe_repo.add_item(
            user_id=user_id,
            title=(data.get("title") or "").strip() or "Wardrobe Item",
            category=taxonomy.normalize_category(data.get("category"), data.get("subcategory")),
            subcategory=(data.get("subcategory") or "").strip() or None,
            color_name=taxonomy.normalize_color(data.get("color_name")),
            color_hex=taxonomy.color_hex_for_family(
                taxonomy.normalize_color(data.get("color_name")), data.get("color_hex")
            ),
            pattern=taxonomy.normalize_pattern(data.get("pattern")),
            brand_name=(data.get("brand_name") or "Own Collection").strip(),
            image_url=data["image_url"],
            ai_tags=taxonomy.normalize_tags(data.get("ai_tags", [])),
            occasions=taxonomy.normalize_occasions(data.get("occasions")),
            wear_frequency=data.get("wear_frequency", "regular"),
            seasonality=taxonomy.normalize_season(data.get("seasonality")),
            purchase_price=data.get("purchase_price"),
            is_favorite=bool(data.get("is_favorite", False)),
            processing_status="ready",
        )
        return self._to_dict(item)

    def update_item(self, user_id: int, item_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        item = self.get_item(user_id, item_id)

        # Normalize controlled fields the same way as create — never persist
        # raw free-form strings into taxonomy-backed columns.
        if "category" in updates and updates["category"]:
            updates["category"] = taxonomy.normalize_category(updates["category"])
        if "color_name" in updates and updates["color_name"]:
            updates["color_name"] = taxonomy.normalize_color(updates["color_name"])
        if "pattern" in updates and updates["pattern"]:
            updates["pattern"] = taxonomy.normalize_pattern(updates["pattern"])
        if "seasonality" in updates and updates["seasonality"]:
            updates["seasonality"] = taxonomy.normalize_season(updates["seasonality"])
        if "wear_frequency" in updates and updates["wear_frequency"]:
            if updates["wear_frequency"] not in taxonomy.WEAR_FREQUENCIES:
                raise ValidationDomainError(
                    f"wear_frequency must be one of {taxonomy.WEAR_FREQUENCIES}"
                )
        if "occasions" in updates and updates["occasions"] is not None:
            updates["occasions"] = taxonomy.normalize_occasions(updates["occasions"])

        for key, val in updates.items():
            if hasattr(item, key) and val is not None:
                if key in ["ai_tags", "occasions", "secondary_colors"] and isinstance(val, list):
                    setattr(item, key, json.dumps(val))
                else:
                    setattr(item, key, val)

        self.wardrobe_repo.update_item(item)
        return self._to_dict(item)

    def delete_item(self, user_id: int, item_id: int) -> None:
        item = self.get_item(user_id, item_id)
        image_url = item.image_url
        self.wardrobe_repo.delete_item(item)
        self._delete_owned_image(image_url)  # no orphaned media (BRD §14)

    # ─────────────────── image upload pipeline ─────────────────
    def _validate_image(self, content_type: Optional[str], data: bytes) -> str:
        """Returns the file extension for a validated image or raises."""
        mime = (content_type or "").split(";")[0].strip().lower()
        if mime not in ALLOWED_IMAGE_TYPES:
            raise ValidationDomainError(
                f"Unsupported image type '{mime or 'unknown'}'. Allowed: JPEG, PNG, WebP."
            )
        if not data:
            raise ValidationDomainError("Uploaded file is empty.")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValidationDomainError("Image exceeds the 15MB size limit.")
        return ALLOWED_IMAGE_TYPES[mime]

    def _store_image(self, user_id: int, data: bytes, ext: str) -> Tuple[str, str]:
        """Persist bytes under the existing local storage root and return
        (public_url, sha256). Files are namespaced per user and content-hash
        is computed for duplicate-upload protection."""
        digest = hashlib.sha256(data).hexdigest()
        uploads_root = os.path.abspath(settings.STORAGE_LOCAL_DIR)
        user_dir = os.path.join(uploads_root, "wardrobe", str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(user_dir, filename)
        with open(path, "wb") as fh:
            fh.write(data)
        return f"/uploads/wardrobe/{user_id}/{filename}", digest

    def _delete_owned_image(self, image_url: Optional[str]) -> None:
        """Best-effort removal of a locally stored wardrobe image. Only paths
        under the configured storage root are ever touched (traversal-safe)."""
        if not image_url or not image_url.startswith("/uploads/"):
            return
        uploads_root = os.path.abspath(settings.STORAGE_LOCAL_DIR)
        rel = image_url[len("/uploads/"):]
        candidate = os.path.abspath(os.path.join(uploads_root, rel))
        if not candidate.startswith(uploads_root + os.sep):
            logger.warn("Refused image deletion outside storage root", path=image_url)
            return
        try:
            if os.path.isfile(candidate):
                os.remove(candidate)
        except OSError as exc:
            logger.warn("Wardrobe image cleanup failed", path=image_url, error=str(exc))

    async def upload_items(
        self, user_id: int, files: List[Tuple[str, Optional[str], bytes]]
    ) -> Dict[str, Any]:
        """Single + bulk image import with per-item isolation.

        Each file is validated, hashed (duplicate-upload protection), stored,
        and analyzed independently: one bad file never rolls back the others
        (BRD §13 partial success). Every result records the original filename
        so the UI can show exactly which item failed and offer retry.
        """
        results: List[Dict[str, Any]] = []
        succeeded = failed = skipped_duplicates = 0

        for filename, content_type, data in files:
            entry: Dict[str, Any] = {"filename": filename}
            try:
                ext = self._validate_image(content_type, data)
                image_url, digest = self._store_image(user_id, data, ext)

                existing = self.wardrobe_repo.get_item_by_image_hash(user_id, digest)
                if existing:
                    self._delete_owned_image(image_url)
                    entry.update({
                        "status": "duplicate",
                        "detail": "This exact image is already in your wardrobe.",
                        "item": self._to_dict(existing),
                    })
                    skipped_duplicates += 1
                    results.append(entry)
                    continue

                item = self.wardrobe_repo.add_item(
                    user_id=user_id,
                    title=os.path.splitext(filename or "Wardrobe Item")[0][:255] or "Wardrobe Item",
                    category="Tops",  # placeholder bucket until AI analysis lands
                    subcategory=None,
                    color_name="Black",
                    color_hex="#1B1B1B",
                    pattern="Solid",
                    brand_name="Own Collection",
                    image_url=image_url,
                    ai_tags=[],
                    occasions=[],
                    processing_status="processing",
                    image_hash=digest,
                )
                analyzed = await self._run_ai_analysis(item)
                entry.update({"status": "created", "item": self._to_dict(analyzed)})
                succeeded += 1
            except (ValidationDomainError,) as exc:
                entry.update({"status": "failed", "detail": str(exc)})
                failed += 1
            except Exception as exc:  # never let one file kill the batch
                logger.error("Wardrobe upload failed", filename=filename, error=str(exc))
                entry.update({"status": "failed", "detail": "Upload processing failed."})
                failed += 1
            results.append(entry)

        return {
            "results": results,
            "summary": {
                "total": len(files),
                "succeeded": succeeded,
                "failed": failed,
                "duplicates_skipped": skipped_duplicates,
            },
        }

    # ─────────────────── AI analysis (real provider) ───────────
    async def _run_ai_analysis(self, item: WardrobeItem) -> WardrobeItem:
        """Run the configured vision provider against the stored image and
        persist the normalized result — or mark the item failed/retryable.

        The image bytes are loaded from our own storage (no outbound fetch of
        user-supplied URLs), converted to a data URL the provider already
        accepts, and the raw model output passes through the taxonomy
        normalizer before touching controlled columns.
        """
        from backend.app.providers.tryon_provider import VisualSearchAIProvider

        item.processing_status = "processing"
        item.processing_error = None
        self.wardrobe_repo.update_item(item)

        try:
            data_url = self._image_ref_for_analysis(item.image_url)
            provider = VisualSearchAIProvider()
            raw = await provider.analyze_wardrobe_image(data_url)

            if not raw.get("analysis_available"):
                raise ProviderIntegrationError(
                    "vision", "wardrobe analysis temporarily unavailable", retryable=True
                )
            if not raw.get("category"):
                raise ValidationDomainError(
                    "The image does not appear to show a clothing item."
                )

            normalized = taxonomy.normalize_wardrobe_analysis(raw)
            item.title = normalized["item_type"] or item.title
            item.category = normalized["category"]
            item.subcategory = normalized["item_type"]
            item.color_name = normalized["primary_color"]
            item.color_hex = normalized["primary_color_hex"]
            item.secondary_colors = json.dumps(normalized["secondary_colors"])
            item.pattern = normalized["pattern"]
            item.ai_tags = json.dumps(normalized["style_tags"])
            item.occasions = json.dumps(normalized["occasion_suitability"])
            item.seasonality = normalized["seasonality"]
            item.ai_confidence = normalized["confidence"]
            item.processing_status = "ready"
            item.processing_error = None
        except (ValidationDomainError, ProviderIntegrationError) as exc:
            # Honest failure (BRD §20): item stays safely uploaded, status
            # becomes failed/retryable, detail is recorded for the retry UX.
            item.processing_status = "failed"
            item.processing_error = str(exc)
            logger.warn("Wardrobe AI analysis failed", item_id=item.id, error=str(exc))
        except Exception as exc:
            item.processing_status = "failed"
            item.processing_error = "AI analysis failed unexpectedly."
            logger.error("Wardrobe AI analysis error", item_id=item.id, error=str(exc))

        return self.wardrobe_repo.update_item(item)

    def _image_ref_for_analysis(self, image_url: str) -> str:
        """Build a data URL from the stored image bytes for the provider."""
        if image_url.startswith("data:image"):
            return image_url
        uploads_root = os.path.abspath(settings.STORAGE_LOCAL_DIR)
        if image_url.startswith("/uploads/"):
            rel = image_url[len("/uploads/"):]
            candidate = os.path.abspath(os.path.join(uploads_root, rel))
            if candidate.startswith(uploads_root + os.sep) and os.path.isfile(candidate):
                ext = os.path.splitext(candidate)[1].lower()
                mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
                with open(candidate, "rb") as fh:
                    return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"
        # External URL (e.g. seeded/demo items): provider fetches it through
        # its own SSRF-guarded downloader.
        return image_url

    async def analyze_item(self, user_id: int, item_id: int) -> Dict[str, Any]:
        """(Re)run AI analysis for one owned item — the retry path."""
        item = self.get_item(user_id, item_id)  # ownership enforced here
        analyzed = await self._run_ai_analysis(item)
        return self._to_dict(analyzed)

    async def auto_tag_image(self, image_url: Optional[str], image_base64: Optional[str]) -> Dict[str, Any]:
        """Preview tagging for the upload form: runs the real vision provider
        and returns normalized suggestions. analysis_available=False is
        returned honestly when no vision model is configured — the UI then
        falls back to the manual form instead of showing fabricated tags."""
        if not image_url and not image_base64:
            raise ValidationDomainError("image_url or image_base64 is required.")
        image_ref = image_base64 or image_url

        from backend.app.providers.tryon_provider import VisualSearchAIProvider

        provider = VisualSearchAIProvider()
        raw = await provider.analyze_wardrobe_image(image_ref)
        if not raw.get("analysis_available"):
            return {
                "analysis_available": False,
                "detail": "AI auto-tagging is not configured (set GEMINI_API_KEY).",
            }
        if not raw.get("category"):
            return {"analysis_available": False, "detail": "No clothing item detected in the image."}

        n = taxonomy.normalize_wardrobe_analysis(raw)
        return {
            "analysis_available": True,
            "detected_title": n["item_type"] or f"{n['primary_color']} {n['category']}",
            "detected_category": n["category"],
            "detected_subcategory": n["item_type"] or "",
            "detected_color": n["primary_color"],
            "detected_color_hex": n["primary_color_hex"],
            "detected_pattern": n["pattern"],
            "ai_tags": n["style_tags"],
            "suggested_occasions": n["occasion_suitability"],
            "seasonality": n["seasonality"],
            "confidence": n["confidence"],
        }

    # ───────────────────── serialization ───────────────────────
    def _to_dict(self, item: WardrobeItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "title": item.title,
            "category": item.category,
            "subcategory": item.subcategory,
            "color_name": item.color_name,
            "color_hex": item.color_hex,
            "pattern": item.pattern,
            "brand_name": item.brand_name,
            "image_url": item.image_url,
            "ai_tags": json.loads(item.ai_tags) if item.ai_tags else [],
            "occasions": json.loads(item.occasions) if item.occasions else [],
            "secondary_colors": json.loads(item.secondary_colors) if getattr(item, "secondary_colors", None) else [],
            "seasonality": getattr(item, "seasonality", "All-Season") or "All-Season",
            "wear_frequency": item.wear_frequency,
            "wear_count": item.wear_count,
            "is_favorite": item.is_favorite,
            "processing_status": getattr(item, "processing_status", "ready") or "ready",
            "processing_error": getattr(item, "processing_error", None),
            "ai_confidence": getattr(item, "ai_confidence", None),
            "created_at": item.created_at,
        }
