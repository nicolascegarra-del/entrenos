from celery import Celery

from app.core.config import get_settings

celery_app = Celery("entrenos", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # La tarea de sincronización con Garmin (cada 30 min) se añade en la fase 3.
    beat_schedule={},
)
