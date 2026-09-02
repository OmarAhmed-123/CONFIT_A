from celery import Celery
from backend.app.core.config import settings

# Celery Application Configuration
celery_app = Celery(
    "confit_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["backend.app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,        # 5 minutes max per task
    task_soft_time_limit=240,   # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    task_routes={
        "backend.app.workers.tasks.render_vton_task": {"queue": "vton_heavy"},
        "backend.app.workers.tasks.extract_visual_features_task": {"queue": "vision_heavy"},
        "backend.app.workers.tasks.auto_tag_wardrobe_task": {"queue": "wardrobe_jobs"},
        "backend.app.workers.tasks.bulk_catalog_import_task": {"queue": "catalog_ingest"},
        "backend.app.workers.tasks.aggregate_analytics_task": {"queue": "analytics_rollups"},
        "backend.app.workers.tasks.purge_expired_sessions_task": {"queue": "maintenance"},
        "backend.app.workers.tasks.release_expired_inventory_reservations_task": {"queue": "maintenance"},
    },
    beat_schedule={
        "purge-expired-tryon-photos-hourly": {
            "task": "backend.app.workers.tasks.purge_expired_sessions_task",
            "schedule": 3600.0, # Every hour
        },
        "aggregate-style-heatmaps-daily": {
            "task": "backend.app.workers.tasks.aggregate_analytics_task",
            "schedule": 86400.0, # Every 24 hours
        },
        "release-expired-inventory-reservations-every-15min": {
            "task": "backend.app.workers.tasks.release_expired_inventory_reservations_task",
            "schedule": 900.0, # Every 15 minutes - critical for stock leak prevention
        }
    }
)
