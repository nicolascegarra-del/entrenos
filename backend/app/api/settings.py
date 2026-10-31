from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app.api.deps import CurrentUser, SessionDep
from app.models import SYNC_INTERVALS, SyncMode
from app.services.sync_schedule import get_user_settings, last_run_start, next_sync_at

router = APIRouter(prefix="/settings", tags=["ajustes"])


class SyncSettingsIn(BaseModel):
    mode: SyncMode
    interval_min: int

    @field_validator("interval_min")
    @classmethod
    def allowed_interval(cls, value: int) -> int:
        if value not in SYNC_INTERVALS:
            raise ValueError(f"El intervalo debe ser uno de: {', '.join(map(str, SYNC_INTERVALS))} minutos.")
        return value


class SyncSettingsOut(SyncSettingsIn):
    intervals: list[int]
    next_sync_at: datetime | None


def _out(session: SessionDep, user_id: int) -> SyncSettingsOut:
    settings = get_user_settings(session, user_id)
    return SyncSettingsOut(
        mode=settings.sync_mode,
        interval_min=settings.sync_interval_min,
        intervals=list(SYNC_INTERVALS),
        next_sync_at=next_sync_at(settings, last_run_start(session, user_id), datetime.now(UTC)),
    )


@router.get("/sync", summary="Preferencias de sincronización (todas las conexiones)")
def get_sync_settings(session: SessionDep, user: CurrentUser) -> SyncSettingsOut:
    return _out(session, user.id)


@router.put(
    "/sync",
    summary="Cambiar modo e intervalo de sincronización",
    description=(
        "General para todas las conexiones (Garmin, COROS, Oura, Suunto, Amazfit, Xiaomi, Samsung). `auto`: se "
        "sincroniza cada `interval_min` (60, 240, 480, 960 o 1440). `manual`: solo con «Sincronizar ahora»."
    ),
    responses={422: {"description": "Intervalo no permitido."}},
)
def update_sync_settings(body: SyncSettingsIn, session: SessionDep, user: CurrentUser) -> SyncSettingsOut:
    settings = get_user_settings(session, user.id)
    settings.sync_mode, settings.sync_interval_min = body.mode, body.interval_min
    session.add(settings)
    session.commit()
    return _out(session, user.id)
