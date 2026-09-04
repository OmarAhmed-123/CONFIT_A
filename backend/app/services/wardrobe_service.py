import base64
import hashlib
import json
import os
import uuid
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, ProviderIntegrationError, FeatureNotConfiguredError
from backend.app.core.logging import logger
from backend.app.services.storage_service import require_production_storage, get_storage
from backend.app.models.wardrobe import WardrobeItem
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.services import wardrobe_taxonomy as taxonomy

# Image contract shared by single + bulk upload paths.
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB, matches the vision provider limit

# Fields a client is permitted to change via update_item. The schema already
# whitelists these at the API boundary; this service-level allowlist is the
# second line of defense so lifecycle columns (processing_status, image_hash,
# user_id, ...) can never be mutated through the generic update path even if
# a future caller bypasses the controller schema.
_UPDATEABLE_FIELDS = {
    "title", "category", "subcategory", "color_name", "color_hex", "pattern",
    "occasions", "seasonality", "wear_frequency", "is_favorite", "wear_count",
    "brand_name", "purchase_price", "ai_tags", "secondary_colors",
}


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

    # ─────────── FLOW E: G5 completed purchase -> G4 wardrobe ───────────
    def sync_items_from_order(self, order) -> Dict[str, Any]:
        """Materialise a completed purchase into the buyer's wardrobe.

        Contract (BRD FLOW E)::

            Completed Purchase -> Persisted Order -> Persisted OrderItems
              -> Server-side catalog lookup -> WardrobeItem -> User-owned wardrobe

        Sources of truth are the **persisted order** and the **catalog** only.
        Nothing is read from the request: not the title, not the category, not
        the colour, not the brand, not the price and above all not the owner.
        ``order.user_id`` — written by the server from the authenticated
        identity or the checkout session — is the only ownership input, so a
        client can never place a purchase into somebody else's wardrobe or
        claim a price/category it invented.

        Semantics required by FLOW E and honoured here:

        * **Guest-safe** — an order with no ``user_id`` has no wardrobe to
          write to. That is a normal outcome, not an error: it is reported as
          ``skipped`` and logged at info level.
        * **Idempotent** — one wardrobe item per persisted ``OrderItem``,
          enforced twice: a lineage read before insert, and the database
          unique index ``uq_wardrobe_items_source_order_item`` (migration
          0015) so that concurrent retries, webhook re-deliveries or an
          operator backfill cannot duplicate a piece.
        * **Returned lines excluded** — an item already flagged
          ``is_returned`` is not the customer's to wear, so it is not added.
        * **Never corrupts the purchase** — every failure is contained,
          rolled back at line grain and logged loudly with the order number.
          The order and its payment stay financially authoritative; a
          wardrobe-sync problem must never surface to the shopper as a
          failed purchase.

        Returns an observable summary dict (never raises for per-line
        problems) so the caller can log/telemetry it.
        """
        summary: Dict[str, Any] = {
            "status": "skipped",
            "order_number": getattr(order, "order_number", None),
            "order_id": getattr(order, "id", None),
            "user_id": getattr(order, "user_id", None),
            "created": 0,
            "already_synced": 0,
            "skipped_returned": 0,
            "failed": 0,
            "errors": [],
        }

        if not order.user_id:
            # Guest purchase: no account, therefore no wardrobe. Not an error.
            summary["status"] = "skipped"
            summary["reason"] = "guest_order_no_wardrobe_owner"
            logger.info(
                "wardrobe_sync_skipped_guest_order",
                order_number=summary["order_number"],
            )
            return summary

        # Imported lazily: catalog models are a sibling domain and a module
        # level import would make wardrobe_service depend on catalog at
        # import time (the rest of this service is catalog-agnostic).
        from backend.app.models.catalog import Product, ProductSKU

        for order_item in list(order.items or []):
            if getattr(order_item, "is_returned", False):
                summary["skipped_returned"] += 1
                continue

            try:
                existing = self.wardrobe_repo.get_item_by_source_order_item(order_item.id)
                if existing is not None:
                    summary["already_synced"] += 1
                    continue

                product = (
                    self.db.query(Product).filter(Product.id == order_item.product_id).first()
                    if order_item.product_id else None
                )
                sku = (
                    self.db.query(ProductSKU).filter(ProductSKU.id == order_item.product_sku_id).first()
                    if order_item.product_sku_id else None
                )

                derived = self._derive_from_catalog(order_item, product, sku)
                if derived is None:
                    summary["failed"] += 1
                    summary["errors"].append(
                        f"order_item={order_item.id}: no catalog image_url; item not added"
                    )
                    logger.error(
                        "wardrobe_sync_line_skipped_no_catalog_image",
                        order_number=summary["order_number"],
                        order_item_id=order_item.id,
                        product_id=order_item.product_id,
                    )
                    continue

                self.wardrobe_repo.add_item(
                    user_id=order.user_id,
                    source_order_item_id=order_item.id,
                    **derived,
                )
                summary["created"] += 1
            except IntegrityError:
                # Lost a race against a concurrent sync of the same line: the
                # winner's row is the canonical one. Roll the failed insert
                # back so the session is usable for the remaining lines.
                self.db.rollback()
                summary["already_synced"] += 1
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                summary["failed"] += 1
                summary["errors"].append(f"order_item={order_item.id}: {type(exc).__name__}: {exc}"[:300])
                logger.error(
                    "wardrobe_sync_line_failed",
                    order_number=summary["order_number"],
                    order_item_id=getattr(order_item, "id", None),
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )

        if summary["failed"] and not summary["created"]:
            summary["status"] = "failed"
        elif summary["failed"]:
            summary["status"] = "partial"
        else:
            summary["status"] = "synced"

        logger.info(
            "wardrobe_sync_completed",
            order_number=summary["order_number"],
            user_id=summary["user_id"],
            status=summary["status"],
            created=summary["created"],
            already_synced=summary["already_synced"],
            skipped_returned=summary["skipped_returned"],
            failed=summary["failed"],
        )
        return summary

    def _derive_from_catalog(self, order_item, product, sku) -> Optional[Dict[str, Any]]:
        """Project a persisted OrderItem + its catalog rows onto wardrobe fields.

        Every value comes from the database. The OrderItem supplies the
        transaction truth (the price actually charged, the size/colour
        variant actually sold); the catalog supplies the taxonomy truth
        (category, style/occasion tags, imagery). Returns ``None`` when the
        piece cannot be represented (no image to show), which the caller
        records as an observable failure rather than inventing a placeholder.
        """
        image_url = getattr(product, "thumbnail_url", None) if product else None
        if not image_url:
            return None

        category_name = None
        if product is not None and getattr(product, "category", None) is not None:
            category_name = product.category.name

        # The variant actually purchased wins over the product-level colour.
        raw_color = (getattr(sku, "color", None) if sku else None) or (
            getattr(product, "color_family", None) if product else None
        ) or order_item.color
        color_name = taxonomy.normalize_color(raw_color)
        color_hex = taxonomy.color_hex_for_family(
            color_name,
            (getattr(sku, "color_hex", None) if sku else None)
            or (getattr(product, "dominant_hex", None) if product else None),
        )

        style_tags: Any = []
        occasion_tags: Any = []
        if product is not None:
            for attr, target in (("style_tags", "style"), ("occasion_tags", "occasion")):
                try:
                    parsed = json.loads(getattr(product, attr, None) or "[]")
                except (TypeError, ValueError):
                    parsed = []
                if target == "style":
                    style_tags = parsed
                else:
                    occasion_tags = parsed

        return {
            "title": (getattr(product, "title", None) if product else None) or order_item.product_title,
            "category": taxonomy.normalize_category(category_name, order_item.product_title),
            "subcategory": category_name,
            "color_name": color_name,
            "color_hex": color_hex,
            "pattern": taxonomy.normalize_pattern(None),
            # BrandProfile.brand_name is the catalog truth; the OrderItem copy
            # is only a fallback for a since-deleted catalog row.
            "brand_name": (
                getattr(getattr(product, "brand", None), "brand_name", None)
                if product is not None else None
            ) or order_item.brand_name,
            "image_url": image_url,
            "ai_tags": taxonomy.normalize_tags(style_tags),
            "occasions": taxonomy.normalize_occasions(occasion_tags),
            "wear_frequency": "regular",
            # Money truth = the persisted order line, never the live catalog
            # price (which may have moved since purchase) and never the client.
            # Passed through as the exact Decimal stored in NUMERIC(12,2).
            "purchase_price": order_item.unit_price,
            "is_favorite": False,
            "seasonality": taxonomy.normalize_season(None),
            "processing_status": "ready",
        }

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
            if key not in _UPDATEABLE_FIELDS or val is None:
                continue  # silently drop non-whitelisted / null fields
            if key == "wear_count" and isinstance(val, int) and val < 0:
                raise ValidationDomainError("wear_count cannot be negative.")
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
        is computed for duplicate-upload protection.
        C24 FIX: Uses pluggable storage backend (local or S3/R2)."""
        digest = hashlib.sha256(data).hexdigest()
        filename = f"{uuid.uuid4().hex}{ext}"
        relative_path = f"wardrobe/{user_id}/{filename}"

        # Production requires durable object storage; the local backend is an
        # explicit development convenience. On a read-only serverless filesystem
        # this raises FeatureNotConfiguredError (501) instead of PermissionError
        # (500) — and never returns a URL to a file that will not exist later.
        storage = require_production_storage("wardrobe_upload")
        public_url = storage.store(relative_path, data)
        return public_url, digest

    def _delete_owned_image(self, image_url: Optional[str]) -> None:
        """Best-effort removal of a wardrobe image WE stored (local or object
        storage). The configured backend decides whether it issued the URL, so
        seeded/external images are never touched and S3/R2 objects are not
        orphaned (the previous implementation only understood /uploads/)."""
        try:
            storage = get_storage()
        except Exception as exc:  # storage misconfigured: nothing to delete
            logger.warn("Wardrobe image cleanup skipped: storage unavailable", error=str(exc)[:120])
            return
        key = storage.key_for_url(image_url)
        if not key:
            return
        if not storage.delete(key):
            logger.warn("Wardrobe image cleanup did not remove the object", path=image_url)

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

                try:
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
                except IntegrityError:
                    # Lost a concurrent-insert race on uq_wardrobe_items_user_
                    # image_hash (same bytes uploaded twice simultaneously).
                    # Roll back and return the canonical item — idempotent.
                    self.db.rollback()
                    self._delete_owned_image(image_url)
                    canonical = self.wardrobe_repo.get_item_by_image_hash(user_id, digest)
                    entry.update({
                        "status": "duplicate",
                        "detail": "This exact image is already in your wardrobe.",
                        "item": self._to_dict(canonical) if canonical else None,
                    })
                    skipped_duplicates += 1
                    results.append(entry)
                    continue

                # C5 FIX: Async pipeline - enqueue Celery task for AI analysis instead of blocking
                # Item is returned immediately with processing status, analysis happens in background
                try:
                    from backend.app.workers.tasks import auto_tag_wardrobe_task
                    auto_tag_wardrobe_task.delay(item.id)
                    logger.info("Enqueued wardrobe auto-tag task", item_id=item.id)
                except Exception as enqueue_err:
                    # If Celery unavailable (dev mode), fallback to inline analysis
                    logger.warn(f"Celery enqueue failed, falling back to inline: {enqueue_err}")
                    try:
                        analyzed = await self._run_ai_analysis(item)
                        entry.update({"status": "created", "item": self._to_dict(analyzed)})
                        succeeded += 1
                        results.append(entry)
                        continue
                    except Exception:
                        pass

                entry.update({"status": "created", "item": self._to_dict(item)})
                succeeded += 1
            except FeatureNotConfiguredError:
                # Storage is not configured for this environment: that is a
                # deployment fact, identical for every file — surface it as 501
                # instead of N opaque "Upload processing failed." rows.
                raise
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
        """Build a data URL from the stored image bytes for the provider.

        Bytes we stored are read back through the configured storage backend
        (local disk or S3/R2) — never re-fetched over HTTP. External URLs
        (seeded/demo items) go to the provider, which fetches them through its
        own SSRF-guarded downloader.
        """
        if image_url.startswith("data:image"):
            return image_url
        try:
            storage = get_storage()
            key = storage.key_for_url(image_url)
        except Exception:
            key = None
        if key:
            data = storage.read(key)
            if data:
                ext = os.path.splitext(key)[1].lower()
                mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
                return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        return image_url

    async def analyze_item(self, user_id: int, item_id: int) -> Dict[str, Any]:
        """(Re)run AI analysis for one owned item — the retry path.

        Guard (§26 concurrency): re-analyzing an already-ready item is
        idempotent — it returns the current state without burning another
        vision call. Retry is meaningful only for failed/processing items.
        """
        item = self.get_item(user_id, item_id)  # ownership enforced here
        if item.processing_status == "ready":
            return self._to_dict(item)
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
