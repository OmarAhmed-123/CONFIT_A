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

    # Bound the PUBLISH path when the broker is unreachable.
    #
    # kombu's default ensure/retry policy is max_retries=20 with a 1s interval,
    # and .delay() is synchronous, so an unreachable Redis made every enqueue
    # block the calling request for ~20 seconds before raising. In the wardrobe
    # upload path that turned a fast "queued" response into a 20s stall per
    # item, and it was the direct cause of the ~120s local test timeout
    # (several upload tests x ~20s each).
    #
    # The caller already has an inline-analysis fallback for an unavailable
    # broker; it just needs to find out quickly. Fail after ~1.5s instead.
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 1,
        "socket_timeout": 2,
        "socket_connect_timeout": 2,
    },
    # NOTE: the redis RESULT BACKEND does not read max_retries from the top
    # level of this dict. celery.backends.redis.RedisBackend.retry_policy
    # merges only a NESTED "retry_policy" key over the base class default of
    # max_retries=20 / interval_step=1 (celery.backends.base.Backend). Putting
    # the keys at the top level silently has no effect - which is exactly why
    # the 20 x 1s "Connection to Redis lost: Retry (n/20)" storm survived an
    # earlier attempt to bound it.
    result_backend_transport_options={
        "socket_timeout": 2,
        "socket_connect_timeout": 2,
        "retry_policy": {
            "max_retries": 2,
            "interval_start": 0,
            "interval_step": 0.5,
            "interval_max": 1,
        },
    },
    task_publish_retry_policy={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 1,
    },
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
