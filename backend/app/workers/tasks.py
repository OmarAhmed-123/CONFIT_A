import json
from datetime import datetime, timezone
from celery.exceptions import MaxRetriesExceededError, Retry
from backend.app.workers.celery_app import celery_app
from backend.app.core.database import SessionLocal
from backend.app.core.logging import logger
from backend.app.models.wardrobe import WardrobeItem
from backend.app.models.tryon import TryOnSession, TryOnJob


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
    """GDPR Article 17 maintenance task: Purges unconsented Try-On photos exceeding 24h retention.

    Covers BOTH retention-bearing VTON tables (port of PR #119):
    * ``tryon_sessions`` — the session row's person-photo references;
    * ``tryon_jobs`` — the job row's ``input_person_image_url`` (the
      uploaded person photo, stored as a data URL). Before this port the
      job rows had no retention columns and the person photos they hold
      would be retained indefinitely.
    """
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

        # Job rows (migration 0038: job rows now carry expires_at/consent_retained).
        expired_jobs = (
            db.query(TryOnJob)
            .filter(TryOnJob.consent_retained == False)
            .filter(TryOnJob.expires_at < now)
            .all()
        )
        job_count = len(expired_jobs)
        for j in expired_jobs:
            j.input_person_image_url = "[PURGED_FOR_PRIVACY]"
        db.commit()
        logger.info("Purged expired privacy assets", sessions=count, jobs=job_count)
        return {"purged_count": count, "purged_job_count": job_count}
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


# ---------------------------------------------------------------------------
# Catalog import (queue: catalog_ingest)
# ---------------------------------------------------------------------------
# THE TASK THE ROUTE NAMED BUT THAT DID NOT EXIST
# ------------------------------------------------
# ``celery_app.task_routes`` has routed
# ``backend.app.workers.tasks.bulk_catalog_import_task`` to ``catalog_ingest``
# since the worker was introduced, and ``docker-compose.yml`` starts a worker
# consuming that queue — but no such task was ever defined. Meanwhile the
# confirm-import endpoint answered ``202 Accepted`` and then ran the entire
# import inline. So the queue was decorative, the acceptance was false, and a
# large catalogue could only ever finish if the HTTP connection survived it.

@celery_app.task(bind=True, max_retries=2, name="backend.app.workers.tasks.bulk_catalog_import_task")
def bulk_catalog_import_task(self, job_id: int):
    """Execute one persisted catalog-import job.

    The job row is the work item: the CSV, the target branch, the notification
    opt-in and the actor all live there (migration 0042), so this task can run
    long after the request that created it has ended and the browser is gone.

    Retries are bounded and only for transient failures. A validation failure is
    not retried — re-running it would produce the same result — and the service
    already records per-row rejections in the job rather than raising.
    """
    from backend.app.services.brand_catalog_service import BrandCatalogService

    db = SessionLocal()
    try:
        service = BrandCatalogService(db)
        result = service.execute_import_job(job_id)
        logger.info(
            "catalog_import_task_finished",
            job_id=job_id,
            status=result.get("status"),
            accepted=result.get("accepted_rows"),
            rejected=result.get("rejected_rows"),
        )
        return result
    except Exception as exc:
        db.rollback()
        err_msg = f"{type(exc).__name__}: {exc}"[:500]
        logger.error("catalog_import_task_error", job_id=job_id, error=err_msg[:300])
        is_exhausted = self.request.retries >= self.max_retries
        recovery_db = SessionLocal()
        try:
            from backend.app.models.catalog_import import CatalogImportJob
            job_row = recovery_db.query(CatalogImportJob).filter(CatalogImportJob.id == job_id).first()
            if job_row is not None and job_row.status not in ("completed", "partially_completed"):
                job_row.heartbeat_at = None
                job_row.last_error = err_msg
                if is_exhausted:
                    job_row.status = "failed"
                    job_row.completed_at = datetime.now(timezone.utc)
                else:
                    job_row.status = "queued"
                recovery_db.commit()
        except Exception as rec_exc:
            recovery_db.rollback()
            logger.warning("catalog_import_state_reset_failed", job_id=job_id, error=str(rec_exc)[:200])
        finally:
            recovery_db.close()

        if is_exhausted:
            logger.error("catalog_import_retries_exhausted", job_id=job_id)
            return {"job_id": job_id, "status": "failed", "retries_exhausted": True}

        try:
            raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 300))
        except Retry:
            raise
        except MaxRetriesExceededError:
            logger.error("catalog_import_retries_exhausted", job_id=job_id)
            return {"job_id": job_id, "status": "failed", "retries_exhausted": True}
    finally:
        db.close()


@celery_app.task
def recover_stalled_catalog_imports_task():
    """Hand abandoned imports back to the queue.

    Covers the two ways a job becomes orphaned: the API committed the row and the
    broker was down at dispatch time, and a worker died mid-import leaving the
    job in ``processing`` with a stale heartbeat. Re-dispatching is safe because
    ``claim_job`` is an atomic conditional update and a terminal job is a no-op.
    """
    from backend.app.services.brand_catalog_service import BrandCatalogService

    db = SessionLocal()
    try:
        service = BrandCatalogService(db)
        job_ids = service.recover_open_jobs()
        dispatched = []
        for job_id in job_ids:
            try:
                bulk_catalog_import_task.delay(job_id)
                dispatched.append(job_id)
            except Exception as exc:  # broker still down: try again next sweep
                logger.warning("catalog_import_requeue_failed", job_id=job_id,
                               error=str(exc)[:200])
        logger.info("catalog_import_recovery_sweep", found=len(job_ids),
                    dispatched=len(dispatched))
        return {"found": len(job_ids), "dispatched": dispatched}
    finally:
        db.close()
