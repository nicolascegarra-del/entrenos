from fastapi import APIRouter, HTTPException, status
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.models import MetricDefinition, SyncRun
from app.schemas.activity import GarminStatus, MetricDefinitionRead, SyncRunRead
from app.services.garmin_client import has_tokens
from app.tasks.sync import sync_user_task

router = APIRouter(tags=["garmin"])


@router.get("/garmin/status", summary="Estado de la conexión y última sincronización")
def garmin_status(session: SessionDep, user: CurrentUser) -> GarminStatus:
    last = session.exec(
        select(SyncRun).where(SyncRun.user_id == user.id).order_by(col(SyncRun.started_at).desc())
    ).first()
    return GarminStatus(
        connected=has_tokens(user.id),
        last_run=SyncRunRead.model_validate(last, from_attributes=True) if last else None,
    )


@router.post(
    "/garmin/sync",
    summary="Sincronizar ahora",
    description="Encola una sincronización en segundo plano. Consulta `/garmin/status` para ver el resultado.",
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "Garmin no está conectado."}},
)
def garmin_sync(user: CurrentUser) -> dict:
    if not has_tokens(user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Garmin no está conectado.")
    sync_user_task.delay(user.id)
    return {"queued": True}


@router.get("/metrics/catalog", summary="Catálogo de métricas conocidas")
def metric_catalog(session: SessionDep, _: CurrentUser) -> list[MetricDefinitionRead]:
    rows = session.exec(select(MetricDefinition).order_by(MetricDefinition.key)).all()
    return [MetricDefinitionRead.model_validate(r, from_attributes=True) for r in rows]
