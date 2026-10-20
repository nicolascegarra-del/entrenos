from datetime import UTC, datetime

import redis

from app.core.config import get_settings
from app.tasks.celery_app import celery_app

HEARTBEAT_KEY = "system:heartbeat"


@celery_app.task(name="system.heartbeat")
def heartbeat_task() -> None:
    """Guarda la hora del último latido (lo programa beat cada minuto y lo ejecuta el worker)."""
    client = redis.Redis.from_url(get_settings().redis_url)
    client.set(HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=3600)
