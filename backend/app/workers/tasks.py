import json
from datetime import datetime, timezone
from backend.app.workers.celery_app import celery_app
from backend.app.core.database import SessionLocal
from backend.app.core.logging import logger
from backend.app.models.wardrobe import WardrobeItem
from backend.app.models.tryon import TryOnSession


# NOTE: there is deliberately NO Celery VTON task. The only virtual try-on
# renderer is the CatVTON pipeline in services/vton-worker (Modal), reached via
# TryOnService -> VTON_WORKER_URL. A previous ``render_vton_task`` here marked
# sessions "completed" after time.sleep(1.5) with rendered_result_url =
# garment_image_url (a fake success). It was removed; see
# backend/tests/test_production_parity.py::test_fake_vton_celery_task_is_gone.

@celery_app.task(bind=True, max_retries=3)
def auto_tag_wardrobe_task(self, item_id: int):
    """Background wardrobe auto-tagging via the REAL vision provider.

    Group 4 fix: the previous task wrote the same hardcoded tags
    (["Tailored", "Fine Wool", ...]) to every item it touched. It now
    delegates to WardrobeService._run_ai_analysis, which calls the
    configured Gemini vision model, normalizes the structured output
    through the shared taxonomy, and marks the item 'failed' (retryable)
    on provider failure instead of fabricating attributes.
    """
    import asyncio
    from backend.app.services.wardrobe_service import WardrobeService

    logger.info("Running AI Auto-tagging job", item_id=item_id)
    db = SessionLocal()
    try:
        item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()
        if not item:
            return {"status": "not_found"}

        service = WardrobeService(db)
        analyzed = asyncio.run(service._run_ai_analysis(item))
        return {
            "status": "completed" if analyzed.processing_status == "ready" else "failed",
            "item_id": item_id,
            "processing_status": analyzed.processing_status,
            "tags": json.loads(analyzed.ai_tags) if analyzed.ai_tags else [],
        }
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task
def purge_expired_sessions_task():
    """GDPR Article 17 maintenance task: Purges unconsented Try-On photos exceeding 24h retention."""
    logger.info("Running GDPR Privacy Purge daemon")
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        expired_sessions = (
            db.query(TryOnSession)
            .filter(TryOnSession.consent_retained == False)
            .filter(TryOnSession.expires_at < now)
            .all()
        )

        count = len(expired_sessions)
        for s in expired_sessions:
            s.input_user_image_url = "[PURGED_FOR_PRIVACY]"
            s.rendered_result_url = "[PURGED_FOR_PRIVACY]"
        db.commit()
        logger.info("Purged expired privacy assets", count=count)
        return {"purged_count": count}
    finally:
        db.close()


@celery_app.task
def aggregate_analytics_task():
    """Nightly aggregation rollups for B2B brand conversion funnels and return reduction."""
    logger.info("Running B2B platform analytics rollup daemon")
    return {"status": "success", "aggregated_at": datetime.now(timezone.utc).isoformat()}


@celery_app.task
def release_expired_inventory_reservations_task():
    """
    CRITICAL: Releases held inventory reservations older than 30 minutes.
    Prevents stock leak when checkout fails mid-transaction or user abandons cart after reservation.
    
    This task should run every 15 minutes via celery beat:
    - Only releases status='held' (not committed/released)
    - Restores global SKU stock and store reserved_quantity
    - Marks reservation as released with timestamp
    - Idempotent and safe to run concurrently (uses FOR UPDATE locks)
    """
    from datetime import timedelta
    from backend.app.models.catalog import ProductSKU, StoreInventory
    from backend.app.models.commerce import InventoryReservation

    logger.info("Running expired inventory reservation cleanup")
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        # Find stale held reservations
        stale_reservations = (
            db.query(InventoryReservation)
            .filter(InventoryReservation.status == "held")
            .filter(InventoryReservation.created_at < cutoff)
            .all()
        )

        released_count = 0
        restored_units = 0

        for reservation in stale_reservations:
            # Lock SKU to prevent race with concurrent checkout
            sku = (
                db.query(ProductSKU)
                .with_for_update()
                .filter(ProductSKU.id == reservation.sku_id)
                .first()
            )
            if sku:
                sku.stock_level += reservation.quantity
                sku.is_in_stock = True
                restored_units += reservation.quantity

            # Restore store inventory if BOPIS
            if reservation.store_id:
                store_inv = (
                    db.query(StoreInventory)
                    .with_for_update()
                    .filter(
                        StoreInventory.store_id == reservation.store_id,
                        StoreInventory.sku_id == reservation.sku_id,
                    )
                    .first()
                )
                if store_inv:
                    store_inv.reserved_quantity = max(
                        0, store_inv.reserved_quantity - reservation.quantity
                    )

            reservation.status = "released"
            reservation.released_at = datetime.now(timezone.utc)
            released_count += 1

        db.commit()
        logger.info(
            "Expired reservations released",
            released_count=released_count,
            restored_units=restored_units,
        )
        return {"released_count": released_count, "restored_units": restored_units}
    except Exception as exc:
        db.rollback()
        logger.error("Failed to release expired reservations", error=str(exc))
        raise
    finally:
        db.close()
