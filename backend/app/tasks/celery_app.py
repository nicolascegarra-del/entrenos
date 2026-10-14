from celery import Celery

from app.core.config import get_settings
from app.services.sync_schedule import TICK_MIN

celery_app = Celery(
    "entrenos",
    broker=get_settings().redis_url,
    backend=get_settings().redis_url,
    include=["app.tasks.sync", "app.tasks.garmin_connect"],
)
celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Comprueba cada TICK_MIN minutos a quién le toca según el intervalo elegido en Ajustes.
        "garmin-sync-tick": {"task": "garmin.sync_all", "schedule": TICK_MIN * 60},
    },
)
