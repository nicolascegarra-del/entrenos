"""Módulos activos de la app (los activa o desactiva el administrador para todos)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.services import modules

router = APIRouter(prefix="/app", tags=["app"])


class ModulesOut(BaseModel):
    entrenadores: bool
    ia: bool
    reloj: bool
    rutas: bool
    nutricion: bool


class ModulesIn(BaseModel):
    """Solo los módulos que se cambian; los no enviados se quedan como están."""

    entrenadores: bool | None = None
    ia: bool | None = None
    reloj: bool | None = None
    rutas: bool | None = None
    nutricion: bool | None = None


@router.get(
    "/modules",
    summary="Módulos activos para tu cuenta",
    description=(
        "Qué partes de la app tiene activadas tu cuenta (el valor general del administrador o el que haya "
        "fijado para ti): `entrenadores`, `ia` (entrenador IA), "
        "`reloj` (envío de sesiones a Garmin y COROS), `rutas` y `nutricion`. La interfaz oculta lo apagado "
        "y su API responde 404 con el código `MODULE_DISABLED`."
    ),
    responses={401: {"description": "No autenticado"}},
)
def get_modules(session: SessionDep, user: CurrentUser) -> ModulesOut:
    return ModulesOut(**modules.for_user(session, user))
