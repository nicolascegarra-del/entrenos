"""
API de la parte social (módulo «social»): perfil, seguir, bloqueos, feed, kudos, comentarios,
clasificación y duelos. La lógica y los permisos viven en `services/social.py`.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import CurrentUser, SessionDep, require_module
from app.core.rate_limit import limiter
from app.services import social as svc

router = APIRouter(prefix="/social", tags=["social"], dependencies=[Depends(require_module("social"))])
activity_router = APIRouter(
    prefix="/activities", tags=["actividades"], dependencies=[Depends(require_module("social"))]
)

Visibility = Literal["followers", "private"]
Metric = Literal["km", "time", "elevation", "days"]
Sport = Literal["all", "running", "cycling"]


# ─── Esquemas ────────────────────────────────────────────────────────────────


class SocialProfileOut(BaseModel):
    user_id: int
    display_name: str
    handle: str
    bio: str
    visibility: Literal["private", "public"]
    default_activity_visibility: Visibility
    hide_map_ends_m: int
    show_pace: bool
    show_maps: bool


class CountsOut(BaseModel):
    followers: int
    following: int
    pending_requests: int


class MeOut(BaseModel):
    profile: SocialProfileOut | None
    counts: CountsOut


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    handle: str = Field(min_length=1, max_length=40)
    bio: str | None = Field(default=None, max_length=400)
    visibility: Literal["private", "public"] | None = None
    default_activity_visibility: Visibility | None = None
    hide_map_ends_m: int | None = Field(default=None, ge=0, le=1000)
    show_pace: bool | None = None
    show_maps: bool | None = None
    share_history: bool | None = Field(
        default=None, description="Aplica la visibilidad por defecto a todo el historial"
    )

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        clean = svc.clean_text(value, 60)
        if not clean:
            raise ValueError("Escribe un nombre visible.")
        return clean

    @field_validator("handle")
    @classmethod
    def _handle(cls, value: str) -> str:
        handle = svc.normalize_handle(value)
        if not svc.HANDLE_RE.match(handle):
            raise ValueError("El @ debe tener entre 3 y 30 caracteres: letras minúsculas, números, «_» o «.».")
        return handle

    @field_validator("bio")
    @classmethod
    def _bio(cls, value: str | None) -> str | None:
        return None if value is None else svc.clean_text(value, 200, multiline=True)


class PersonOut(BaseModel):
    user_id: int
    display_name: str
    handle: str
    bio: str
    visibility: Literal["private", "public"]
    follow_status: Literal["none", "pending", "accepted"]
    follows_me: bool
    blocked: bool


class OwnerOut(BaseModel):
    user_id: int
    display_name: str
    handle: str


class AchievementOut(BaseModel):
    title: str
    kind: str


class FeedItem(BaseModel):
    activity_id: int
    owner: OwnerOut
    sport: str
    name: str
    start_time: datetime
    distance_m: float | None
    duration_s: float
    moving_duration_s: float | None
    avg_speed: float | None = Field(description="m/s; null si el dueño oculta el ritmo")
    elevation_gain_m: float | None
    is_race: bool
    track: list[tuple[float, float]] | None = Field(description="[lat, lon] con los extremos recortados")
    achievements: list[AchievementOut]
    kudos_count: int
    kudoed_by_me: bool
    comments_count: int
    mine: bool
    visibility: Visibility


class FeedOut(BaseModel):
    items: list[FeedItem]
    next_before: str | None


class ProfileCountsOut(BaseModel):
    followers: int
    following: int
    activities: int


class ProfilePageOut(BaseModel):
    person: PersonOut
    counts: ProfileCountsOut
    can_view: bool
    recent: list[FeedItem]


class FollowOut(BaseModel):
    status: Literal["pending", "accepted"]


class KudosOut(BaseModel):
    kudos_count: int
    kudoed_by_me: bool


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    author: OwnerOut
    body: str
    created_at: datetime
    can_delete: bool


class VisibilityIn(BaseModel):
    visibility: Visibility


class VisibilityOut(BaseModel):
    visibility: Visibility


class LeaderRow(BaseModel):
    user_id: int
    display_name: str
    handle: str
    value: float
    rank: int
    prev_rank: int | None
    me: bool


class LeaderboardOut(BaseModel):
    period_start: date
    period_end: date
    metric: Metric
    rows: list[LeaderRow]
    my_rank: int | None
    gap_to_next: float | None
    next_name: str | None


class DuelOut(BaseModel):
    id: int
    challenger: OwnerOut
    opponent: OwnerOut
    metric: Literal["km", "time", "elevation", "days", "best_5k", "best_10k"]
    sport: Sport
    start_date: date
    end_date: date
    status: Literal["pending", "active", "finished", "declined", "cancelled"]
    my_value: float | None
    their_value: float | None
    winner_id: int | None
    i_am_challenger: bool


class DuelsOut(BaseModel):
    active: list[DuelOut]
    pending_in: list[DuelOut]
    pending_out: list[DuelOut]
    finished: list[DuelOut]


class DuelIn(BaseModel):
    opponent_id: int
    metric: Literal["km", "time", "elevation", "days", "best_5k", "best_10k"]
    sport: Sport = "all"
    duration: Literal["1w", "2w", "1m"]


class SummaryOut(BaseModel):
    has_profile: bool
    my_rank: int | None
    friends: int
    gap_to_next: float | None
    next_name: str | None
    metric: Literal["km"]
    active_duel: DuelOut | None


# ─── Utilidades ──────────────────────────────────────────────────────────────


def _run(fn: Callable[..., Any], *args: Any) -> Any:
    """Ejecuta un servicio y traduce `SocialError` a la respuesta de error estándar (con código propio)."""
    try:
        return fn(*args)
    except svc.SocialError as exc:
        raise HTTPException(exc.status, exc.message, headers={"X-Error-Code": exc.code}) from exc


def _no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_E404 = {404: {"description": "No existe, hay un bloqueo o no tienes acceso"}}
_E409P = {409: {"description": "`PROFILE_REQUIRED`: falta el perfil social"}}


# ─── Perfil ──────────────────────────────────────────────────────────────────


@router.get("/me", summary="Mi perfil social y contadores",
            description="`profile` es null hasta que la persona elige nombre visible y @.")  # fmt: skip
def get_me(session: SessionDep, user: CurrentUser) -> MeOut:
    profile = svc.get_profile(session, user.id)
    return MeOut(profile=svc.profile_out(profile) if profile else None, counts=svc.my_counts(session, user.id))


@router.put(
    "/me",
    summary="Crear o editar mi perfil social",
    description="Con `share_history`, todas tus actividades pasan a tu visibilidad por defecto.",
    responses={409: {"description": "`HANDLE_TAKEN`: el @ ya existe"}, 422: {"description": "Formato no válido"}},
)
def put_me(body: ProfileIn, session: SessionDep, user: CurrentUser) -> SocialProfileOut:
    profile = _run(svc.save_profile, session, user.id, body.model_dump())
    return SocialProfileOut(**svc.profile_out(profile))


# ─── Personas ────────────────────────────────────────────────────────────────


@router.get("/users/search", summary="Buscar personas por nombre o @",
            description="Hasta 20. Con «@» delante busca solo por @. Excluye bloqueos y a ti.")  # fmt: skip
@limiter.limit("60/minute")
def search_users(
    request: Request, session: SessionDep, user: CurrentUser, q: Annotated[str, Query(max_length=60)] = ""
) -> list[PersonOut]:
    return svc.search(session, user.id, q)


@router.get("/users/{handle}", summary="Perfil de una persona",
            description="`recent` va vacío si no puedes ver sus actividades.", responses=_E404)  # fmt: skip
def user_profile(handle: str, session: SessionDep, user: CurrentUser) -> ProfilePageOut:
    return _run(svc.profile_page, session, user.id, handle)


@router.post("/follow/{user_id}", summary="Seguir a alguien",
             description="Perfil público: aceptado al momento. Privado: solicitud pendiente. Avisa por push.",
             responses={**_E404, **_E409P})  # fmt: skip
@limiter.limit("60/minute")
def follow(request: Request, user_id: int, session: SessionDep, user: CurrentUser) -> FollowOut:
    return FollowOut(status=_run(svc.follow, session, user.id, user_id))


@router.delete("/follow/{user_id}", summary="Dejar de seguir o cancelar la solicitud", status_code=204)
def unfollow(user_id: int, session: SessionDep, user: CurrentUser) -> Response:
    svc.unfollow(session, user.id, user_id)
    return _no_content()


@router.get("/requests", summary="Solicitudes pendientes para seguirme")
def list_requests(session: SessionDep, user: CurrentUser) -> list[PersonOut]:
    return svc.requests(session, user.id)


@router.post("/requests/{user_id}/accept", summary="Aceptar una solicitud", status_code=204,
             description="Avisa por push a quien la envió.", responses=_E404)  # fmt: skip
def accept_request(user_id: int, session: SessionDep, user: CurrentUser) -> Response:
    _run(svc.accept_request, session, user.id, user_id)
    return _no_content()


@router.post("/requests/{user_id}/reject", summary="Rechazar una solicitud", status_code=204, responses=_E404)
def reject_request(user_id: int, session: SessionDep, user: CurrentUser) -> Response:
    _run(svc.reject_request, session, user.id, user_id)
    return _no_content()


@router.get("/followers", summary="Mis seguidores")
def list_followers(session: SessionDep, user: CurrentUser) -> list[PersonOut]:
    return svc.followers(session, user.id)


@router.get("/following", summary="A quién sigo")
def list_following(session: SessionDep, user: CurrentUser) -> list[PersonOut]:
    return svc.following(session, user.id)


@router.delete("/followers/{user_id}", summary="Quitar a un seguidor", status_code=204)
def remove_follower(user_id: int, session: SessionDep, user: CurrentUser) -> Response:
    svc.remove_follower(session, user.id, user_id)
    return _no_content()


@router.post("/block/{user_id}", summary="Bloquear a alguien", status_code=204,
             description="Corta el seguimiento en los dos sentidos, cancela duelos y os oculta en todo.",
             responses=_E404)  # fmt: skip
def block(user_id: int, session: SessionDep, user: CurrentUser) -> Response:
    _run(svc.block, session, user.id, user_id)
    return _no_content()


@router.delete("/block/{user_id}", summary="Desbloquear", status_code=204)
def unblock(user_id: int, session: SessionDep, user: CurrentUser) -> Response:
    svc.unblock(session, user.id, user_id)
    return _no_content()


@router.get("/blocked", summary="Personas bloqueadas")
def list_blocked(session: SessionDep, user: CurrentUser) -> list[PersonOut]:
    return svc.blocked_list(session, user.id)


# ─── Feed, kudos y comentarios ───────────────────────────────────────────────


@router.get("/feed", summary="Feed de actividades",
            description="Tuyas y de quien sigues (aceptado) que puedes ver. Paginado con `before` (ISO).")  # fmt: skip
def get_feed(
    session: SessionDep,
    user: CurrentUser,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FeedOut:
    return svc.feed(session, user.id, before, limit)


@router.post("/activities/{activity_id}/kudos", summary="Dar kudos", responses={**_E404, **_E409P,
             400: {"description": "`OWN_ACTIVITY`: no a tus propias actividades"}})  # fmt: skip
@limiter.limit("120/minute")
def give_kudos(request: Request, activity_id: int, session: SessionDep, user: CurrentUser) -> KudosOut:
    return _run(svc.give_kudos, session, user.id, activity_id)


@router.delete("/activities/{activity_id}/kudos", summary="Quitar mi kudos", responses=_E404)
def remove_kudos(activity_id: int, session: SessionDep, user: CurrentUser) -> KudosOut:
    return _run(svc.remove_kudos, session, user.id, activity_id)


@router.get("/activities/{activity_id}/kudos", summary="Quién ha dado kudos", responses=_E404)
def list_kudos(activity_id: int, session: SessionDep, user: CurrentUser) -> list[OwnerOut]:
    return _run(svc.kudos_list, session, user.id, activity_id)


@router.get("/activities/{activity_id}/comments", summary="Comentarios de una actividad", responses=_E404)
def list_comments(activity_id: int, session: SessionDep, user: CurrentUser) -> list[CommentOut]:
    return _run(svc.comments, session, user.id, activity_id)


@router.post("/activities/{activity_id}/comments", summary="Comentar una actividad",
             description="Texto saneado (sin HTML), hasta 500 caracteres. Aviso al dueño cada 10 min como mucho.",
             responses={**_E404, **_E409P})  # fmt: skip
@limiter.limit("20/minute")
def add_comment(
    request: Request, activity_id: int, body: CommentIn, session: SessionDep, user: CurrentUser
) -> CommentOut:
    return _run(svc.add_comment, session, user.id, activity_id, body.body)


@router.delete("/comments/{comment_id}", summary="Borrar un comentario", status_code=204,
               description="Puede su autor o el dueño de la actividad.",
               responses={**_E404, 403: {"description": "No es tuyo ni de tu actividad"}})  # fmt: skip
def delete_comment(comment_id: int, session: SessionDep, user: CurrentUser) -> Response:
    _run(svc.delete_comment, session, user.id, comment_id)
    return _no_content()


@activity_router.put("/{activity_id}/visibility", summary="Visible para seguidores o Solo yo",
                     responses={404: {"description": "No existe o no es tuya"}})  # fmt: skip
def set_visibility(activity_id: int, body: VisibilityIn, session: SessionDep, user: CurrentUser) -> VisibilityOut:
    return VisibilityOut(visibility=_run(svc.set_activity_visibility, session, user.id, activity_id, body.visibility))


# ─── Clasificación, duelos y resumen ─────────────────────────────────────────


@router.get("/leaderboard", summary="Clasificación entre amigos",
            description="Tú y a quien sigues (aceptado), con las actividades que puedes ver. km con 1 decimal, "
                        "time en segundos, elevation en m y days = días distintos con actividad.")  # fmt: skip
def get_leaderboard(
    session: SessionDep,
    user: CurrentUser,
    period: Literal["week", "month"] = "week",
    metric: Metric = "km",
    sport: Sport = "all",
) -> LeaderboardOut:
    return svc.leaderboard(session, user.id, period, metric, sport)


@router.get("/duels", summary="Mis duelos", description="En marcha, pendientes y los 20 últimos terminados.")
def list_duels(session: SessionDep, user: CurrentUser) -> DuelsOut:
    return svc.list_duels(session, user.id)


@router.post("/duels", summary="Retar a alguien",
             description="Hace falta seguiros mutuamente (aceptado) o que su perfil sea público. Empieza al aceptar.",
             responses={**_E404, **_E409P, 403: {"description": "`NOT_FRIENDS`"},
                        409: {"description": "`DUEL_EXISTS` o `PROFILE_REQUIRED`"}})  # fmt: skip
@limiter.limit("30/minute")
def create_duel(request: Request, body: DuelIn, session: SessionDep, user: CurrentUser) -> DuelOut:
    return _run(svc.create_duel, session, user.id, body.opponent_id, body.metric, body.sport, body.duration)


@router.post("/duels/{duel_id}/{action}", summary="Aceptar, rechazar o cancelar un duelo",
             responses={**_E404, 409: {"description": "`DUEL_STATE`: no admite ese cambio"}})  # fmt: skip
def duel_action(
    duel_id: int, action: Literal["accept", "decline", "cancel"], session: SessionDep, user: CurrentUser
) -> DuelOut:
    return _run(svc.duel_action, session, user.id, duel_id, action)


@router.get("/summary", summary="Resumen para Hoy", description="Tu semana entre amigos (km) y el duelo en marcha.")
def get_summary(session: SessionDep, user: CurrentUser) -> SummaryOut:
    return svc.summary(session, user.id)
