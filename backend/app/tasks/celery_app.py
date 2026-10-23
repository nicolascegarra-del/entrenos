from celery import Celery
from celery.signals import setup_logging as celery_setup_logging

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.sync_schedule import TICK_MIN

celery_app = Celery(
    "entrenos",
    broker=get_settings().redis_url,
    backend=get_settings().redis_url,
    include=[
        "app.tasks.sync",
        "app.tasks.garmin_connect",
        "app.tasks.email",
        "app.tasks.heartbeat",
        "app.tasks.housekeeping",
        "app.tasks.plans",
        "app.tasks.notifications",
        "app.tasks.sources",
        "app.tasks.ai",
        "app.tasks.workouts",
        "app.tasks.coach",
    ],
)
celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Comprueba cada TICK_MIN minutos a quién le toca según el intervalo elegido en Ajustes.
        "garmin-sync-tick": {"task": "garmin.sync_all", "schedule": TICK_MIN * 60},
        # Latido para Admin → Sistema: demuestra que beat programa y el worker ejecuta.
        "heartbeat": {"task": "system.heartbeat", "schedule": 60},
        # Cuentas sin confirmar (48 h) y cuentas Básicas inactivas (aviso y borrado).
        "accounts-housekeeping": {"task": "accounts.housekeeping", "schedule": 24 * 3600},
        # Adaptación semanal de los planes de entrenamiento (actúa una vez por semana y plan).
        "plans-adapt": {"task": "plans.adapt_due", "schedule": 6 * 3600},
        # Notificación «hoy toca…» a la hora que elige cada persona.
        "notifications-daily": {"task": "notifications.daily", "schedule": 15 * 60},
        # Otros relojes: COROS cada hora (Health Connect llega solo por webhook).
        "coros-sync": {"task": "coros.sync_all", "schedule": 3600},
        # Sesiones de los próximos 7 días a Garmin (quien tenga el envío automático activado).
        "garmin-workouts": {"task": "garmin.send_workouts_all", "schedule": 6 * 3600},
        # COROS por la conexión oficial (límite de 50 .FIT al día): actividades de hoy y ayer.
        "coros-official-sync": {"task": "coros.official_sync_all", "schedule": 6 * 3600},
        # Revisión semanal con el entrenador IA (el domingo desde las 18:00 locales).
        "coach-weekly": {"task": "coach.weekly_tick", "schedule": 3600},
    },
)


@celery_setup_logging.connect
def _configure_logging(**_: object) -> None:
    """Sustituye el logging de Celery por el estructurado de la app (JSON en producción)."""
    setup_logging("worker")
