"""Material (zapatillas): alta, kilómetros, predeterminada, retirar y asignar a actividades."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity, Gear
from app.services import gear as svc

router = APIRouter(tags=["material"])
_NOT_FOUND = {404: {"description": "No encontrado"}}


class GearIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=80)
    start_km: float = Field(default=0, ge=0, le=5000, description="Km que ya tenían al darlas de alta")
    alert_km: float = Field(default=700, ge=100, le=3000)
    first_use: date | None = Field(default=None, description="Desde cuándo se le asignan las carreras (por defecto)")
    is_default: bool = False
    retired: bool = False


class ActivityGearIn(BaseModel):
    gear_id: int | None


def _owned(session: SessionDep, user_id: int, gear_id: int) -> Gear:
    gear = session.get(Gear, gear_id)
    if gear is None or gear.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material no encontrado.")
    return gear


def _apply(session: SessionDep, user_id: int, gear: Gear, body: GearIn) -> None:
    for key in ("name", "brand", "model", "start_km", "alert_km", "first_use"):
        setattr(gear, key, getattr(body, key))
    if body.retired != gear.retired:
        gear.retired = body.retired
        gear.retired_at = datetime.now(UTC) if body.retired else None
    session.add(gear)
    session.flush()
    if body.is_default and not gear.retired:
        svc.set_default(session, user_id, gear)
    elif gear.is_default and (not body.is_default or gear.retired):
        gear.is_default = False
        session.add(gear)
    session.commit()
    if gear.is_default:
        svc.assign_default(session, user_id)


@router.get("/gear", summary="Mis zapatillas con sus kilómetros y estado")
def list_gear(session: SessionDep, user: CurrentUser) -> list[dict]:
    return svc.list_gear(session, user.id)


@router.post("/gear", summary="Dar de alta unas zapatillas", status_code=status.HTTP_201_CREATED)
def create_gear(body: GearIn, session: SessionDep, user: CurrentUser) -> list[dict]:
    _apply(session, user.id, Gear(user_id=user.id, name=body.name), body)
    return svc.list_gear(session, user.id)


@router.put("/gear/{gear_id}", summary="Editar, marcar por defecto o retirar", responses=_NOT_FOUND)
def update_gear(gear_id: int, body: GearIn, session: SessionDep, user: CurrentUser) -> list[dict]:
    _apply(session, user.id, _owned(session, user.id, gear_id), body)
    return svc.list_gear(session, user.id)


@router.delete("/gear/{gear_id}", summary="Borrar (las actividades quedan sin zapatilla)", status_code=204,
               responses=_NOT_FOUND)  # fmt: skip
def delete_gear(gear_id: int, session: SessionDep, user: CurrentUser) -> Response:
    session.delete(_owned(session, user.id, gear_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/activities/{activity_id}/gear", summary="Cambiar las zapatillas de una actividad",
            responses=_NOT_FOUND)  # fmt: skip
def set_activity_gear(activity_id: int, body: ActivityGearIn, session: SessionDep, user: CurrentUser) -> dict:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    if body.gear_id is not None:
        _owned(session, user.id, body.gear_id)
    activity.gear_id = body.gear_id
    session.add(activity)
    session.commit()
    return {"activity_id": activity.id, "gear_id": activity.gear_id}
