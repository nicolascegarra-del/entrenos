from celery import Celery

from app.core.config import get_settings

celery_app = Celery(
    "entrenos",
    broker=get_settings().redis_url,
    backend=get_settings().redis_url,
    include=["app.tasks.sync"],
)
celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "garmin-sync-cada-30-min": {"task": "garmin.sync_all", "schedule": 30 * 60},
    },
)
