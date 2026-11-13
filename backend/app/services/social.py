"""
Parte social: perfiles, seguir, bloqueos, feed con kudos y comentarios, clasificación y duelos.

La autorización está centralizada aquí y todo pasa por estas funciones:
- `is_blocked`: un bloqueo en cualquier sentido oculta a las dos personas entre sí (búsqueda, feed,
  clasificación, duelos y perfil).
- `follow_status`: solo un seguimiento aceptado da acceso.
- `can_view` / `visible_clause`: una actividad la ve su dueño o un seguidor aceptado si está en
  «followers»; «private» (Solo yo) no la ve nadie más.

Lo que sale hacia otras personas se construye campo a campo (`feed_items`, `person_out`): nunca FC,
zonas, salud, notas, análisis de la IA, sensaciones ni email.

Las fechas de clasificaciones y duelos se cuentan en días de Madrid.
"""

import logging
import math
import re
import unicodedata
from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Date, Float, and_, cast, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.models import (
    Achievement,
    Activity,
    ActivityComment,
    ActivityStream,
    Block,
    Duel,
    Follow,
    Kudos,
    SocialProfile,
    User,
    UserStatus,
)
from app.services import modules, notifications
from app.services.es_format import num
from app.services.plan_steps import family_members

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Madrid")
VISIBILITIES = ("followers", "private")
HANDLE_RE = re.compile(r"^[a-z0-9_.]{3,30}$")
TRACK_MAX_POINTS = 150
SEARCH_LIMIT = 20
PROFILE_RECENT = 10
GROUP_SECONDS = 600  # avisos de kudos y comentarios: como mucho uno cada 10 minutos por actividad
SUM_METRICS = ("km", "time", "elevation", "days")
BEST_METRICS = ("best_5k", "best_10k")
DUEL_METRICS = SUM_METRICS + BEST_METRICS
DUEL_DURATIONS = ("1w", "2w", "1m")


class SocialError(Exception):
    """Error de negocio con estado HTTP y código propio (la API lo convierte en HTTPException)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _not_found(message: str = "No encontrado.") -> SocialError:
    return SocialError(404, "NOT_FOUND", message)


# ─── Texto ───────────────────────────────────────────────────────────────────

_TAG = re.compile(r"<[^>]*>")
_BIDI = set("‪‫‬‭‮⁦⁧⁨⁩")


def clean_text(value: str | None, max_len: int, multiline: bool = False) -> str:
    """
    Sanea texto escrito por la persona: quita etiquetas HTML, caracteres de control y de dirección
    (bidi), compacta espacios y recorta a `max_len`. Con `multiline` conserva saltos de línea (máx. 2 seguidos).
    """
    text = _TAG.sub("", value or "")
    out = []
    for ch in text:
        if ch == "\n" and multiline:
            out.append(ch)
        elif ch in "\t\r\n":
            out.append(" ")
        elif unicodedata.category(ch) == "Cc" or ch in _BIDI:
            continue
        else:
            out.append(ch)
    text = "".join(out)
    if multiline:
        lines = [re.sub(r"[  ]+", " ", line).strip() for line in text.split("\n")]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_len].strip()


def normalize_handle(raw: str) -> str:
    return (raw or "").strip().lstrip("@").lower()


def _like_escape(term: str) -> str:
    return term.replace("\\", r"\\").replace("%", r"\%").replace("_", r"\_")


# ─── Permisos ────────────────────────────────────────────────────────────────


def is_blocked(session: Session, a: int, b: int) -> bool:
    """¿Hay un bloqueo entre `a` y `b` en cualquier sentido?"""
    row = session.exec(select(Block.id).where(or_(
        and_(Block.blocker_id == a, Block.blocked_id == b), and_(Block.blocker_id == b, Block.blocked_id == a)
    )).limit(1)).first()  # fmt: skip
    return row is not None


def follow_status(session: Session, follower_id: int, followee_id: int) -> str:
    """«none», «pending» o «accepted»."""
    row = session.exec(select(Follow.status).where(
        Follow.follower_id == follower_id, Follow.followee_id == followee_id
    )).first()  # fmt: skip
    return row or "none"


def can_view_person(session: Session, viewer_id: int, owner_id: int) -> bool:
    """Ver las actividades compartidas de alguien: ser esa persona o seguirla (aceptado) sin bloqueo."""
    if viewer_id == owner_id:
        return True
    return not is_blocked(session, viewer_id, owner_id) and follow_status(session, viewer_id, owner_id) == "accepted"


def can_view(session: Session, viewer_id: int, activity: Activity) -> bool:
    """Una actividad: su dueño siempre; los demás solo si está en «followers» y la siguen (aceptado)."""
    if activity.user_id == viewer_id:
        return True
    if activity.visibility != "followers":
        return False
    return can_view_person(session, viewer_id, activity.user_id)


def _blocked_with(viewer_id: int) -> tuple[Any, Any]:
    """Subconsultas de quien yo bloqueo y de quien me bloquea."""
    return (
        select(Block.blocked_id).where(Block.blocker_id == viewer_id),
        select(Block.blocker_id).where(Block.blocked_id == viewer_id),
    )


def _not_blocked(user_col: Any, viewer_id: int) -> Any:
    mine, theirs = _blocked_with(viewer_id)
    return and_(col(user_col).not_in(mine), col(user_col).not_in(theirs))


def _followees(viewer_id: int) -> Any:
    return select(Follow.followee_id).where(Follow.follower_id == viewer_id, Follow.status == "accepted")


def visible_clause(viewer_id: int) -> Any:
    """Condición SQL equivalente a `can_view` para filtrar actividades en una sola consulta."""
    return or_(
        Activity.user_id == viewer_id,
        and_(
            Activity.visibility == "followers",
            col(Activity.user_id).in_(_followees(viewer_id)),
            _not_blocked(Activity.user_id, viewer_id),
        ),
    )


def visible_activity(session: Session, viewer_id: int, activity_id: int) -> Activity:
    """La actividad si el usuario la puede ver; si no, 404 (no se distingue «no existe» de «no puedes»)."""
    activity = session.get(Activity, activity_id)
    if activity is None or not can_view(session, viewer_id, activity):
        raise _not_found("Actividad no encontrada.")
    return activity


# ─── Perfil ──────────────────────────────────────────────────────────────────


def get_profile(session: Session, user_id: int) -> SocialProfile | None:
    return session.get(SocialProfile, user_id)


def require_profile(session: Session, user_id: int) -> SocialProfile:
    profile = get_profile(session, user_id)
    if profile is None:
        raise SocialError(409, "PROFILE_REQUIRED", "Crea primero tu perfil social (nombre visible y @).")
    return profile


def profile_out(p: SocialProfile) -> dict:
    return {
        "user_id": p.user_id,
        "display_name": p.display_name,
        "handle": p.handle,
        "bio": p.bio,
        "visibility": p.visibility,
        "default_activity_visibility": p.default_activity_visibility,
        "hide_map_ends_m": p.hide_map_ends_m,
        "show_pace": p.show_pace,
        "show_maps": p.show_maps,
    }


def _accepted_count(session: Session, column: Any, user_id: int) -> int:
    other = Follow.follower_id if column is Follow.followee_id else Follow.followee_id
    mine, theirs = _blocked_with(user_id)
    return session.exec(select(func.count()).select_from(Follow).where(
        column == user_id, Follow.status == "accepted", col(other).not_in(mine), col(other).not_in(theirs)
    )).one()  # fmt: skip


def my_counts(session: Session, user_id: int) -> dict:
    pending = session.exec(select(func.count()).select_from(Follow).where(
        Follow.followee_id == user_id, Follow.status == "pending"
    )).one()  # fmt: skip
    return {
        "followers": _accepted_count(session, Follow.followee_id, user_id),
        "following": _accepted_count(session, Follow.follower_id, user_id),
        "pending_requests": pending,
    }


def save_profile(session: Session, user_id: int, data: dict) -> SocialProfile:
    """
    Crea o actualiza el perfil. `data` llega validado por la API (formato del @, longitudes, valores).
    Con `share_history`, todas las actividades de la persona pasan a su visibilidad por defecto.

    Raises:
        SocialError: 409 `HANDLE_TAKEN` si el @ ya es de otra persona.
    """
    handle = data["handle"]
    taken = session.exec(select(SocialProfile.user_id).where(
        SocialProfile.handle == handle, SocialProfile.user_id != user_id
    )).first()  # fmt: skip
    if taken is not None:
        raise SocialError(409, "HANDLE_TAKEN", "Ese @ ya está cogido. Prueba con otro.")
    profile = get_profile(session, user_id) or SocialProfile(user_id=user_id, display_name="", handle=handle)
    for key in ("display_name", "handle", "bio", "visibility", "default_activity_visibility", "hide_map_ends_m",
                "show_pace", "show_maps"):  # fmt: skip
        if data.get(key) is not None:
            setattr(profile, key, data[key])
    session.add(profile)
    try:
        session.flush()
    except IntegrityError as exc:  # carrera entre dos personas con el mismo @
        session.rollback()
        raise SocialError(409, "HANDLE_TAKEN", "Ese @ ya está cogido. Prueba con otro.") from exc
    if data.get("share_history"):
        session.exec(update(Activity).where(Activity.user_id == user_id)
                     .values(visibility=profile.default_activity_visibility))  # fmt: skip
    # Al hacerse público, las solicitudes pendientes se aceptan solas.
    if profile.visibility == "public":
        session.exec(update(Follow).where(Follow.followee_id == user_id, Follow.status == "pending")
                     .values(status="accepted", accepted_at=datetime.now(UTC)))  # fmt: skip
    session.commit()
    session.refresh(profile)
    return profile


def set_activity_visibility(session: Session, user_id: int, activity_id: int, visibility: str) -> str:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user_id:
        raise _not_found("Actividad no encontrada.")
    activity.visibility = visibility
    session.add(activity)
    session.commit()
    return visibility


# ─── Personas ────────────────────────────────────────────────────────────────


def _owner(p: SocialProfile) -> dict:
    return {"user_id": p.user_id, "display_name": p.display_name, "handle": p.handle}


def person_out(session: Session, viewer_id: int, profiles: list[SocialProfile]) -> list[dict]:
    """Personas tal como las ve `viewer_id` (estado de seguimiento y bloqueo en 3 consultas para toda la lista)."""
    ids = [p.user_id for p in profiles]
    if not ids:
        return []
    mine = dict(session.exec(select(Follow.followee_id, Follow.status).where(
        Follow.follower_id == viewer_id, col(Follow.followee_id).in_(ids)
    )).all())  # fmt: skip
    follows_me = set(session.exec(select(Follow.follower_id).where(
        Follow.followee_id == viewer_id, col(Follow.follower_id).in_(ids), Follow.status == "accepted"
    )).all())  # fmt: skip
    blocked = set(session.exec(select(Block.blocked_id).where(
        Block.blocker_id == viewer_id, col(Block.blocked_id).in_(ids)
    )).all())  # fmt: skip
    return [
        {
            **_owner(p),
            "bio": p.bio,
            "visibility": p.visibility,
            "follow_status": mine.get(p.user_id, "none"),
            "follows_me": p.user_id in follows_me,
            "blocked": p.user_id in blocked,
        }
        for p in profiles
    ]


def _active_profiles() -> Any:
    return (
        select(SocialProfile).join(User, col(User.id) == SocialProfile.user_id).where(User.status == UserStatus.ACTIVE)
    )


def search(session: Session, viewer_id: int, q: str) -> list[dict]:
    """Por nombre visible o por @ (con «@» delante, solo por @). Sin bloqueos ni la propia persona."""
    term = (q or "").strip()
    by_handle = term.startswith("@")
    term = term.lstrip("@").strip()
    if len(term) < 2:
        return []
    like = _like_escape(term.lower())
    query = _active_profiles().where(SocialProfile.user_id != viewer_id, _not_blocked(SocialProfile.user_id, viewer_id))
    if by_handle:
        query = query.where(col(SocialProfile.handle).like(f"{like}%", escape="\\"))
    else:
        query = query.where(or_(
            col(SocialProfile.display_name).ilike(f"%{like}%", escape="\\"),
            col(SocialProfile.handle).like(f"{like}%", escape="\\"),
        ))  # fmt: skip
    rows = session.exec(query.order_by(SocialProfile.handle).limit(SEARCH_LIMIT)).all()
    return person_out(session, viewer_id, list(rows))


def profile_page(session: Session, viewer_id: int, handle: str) -> dict:
    """Perfil de otra persona (o el propio). 404 si no existe o hay un bloqueo."""
    profile = session.exec(_active_profiles().where(SocialProfile.handle == normalize_handle(handle))).first()
    if profile is None or (profile.user_id != viewer_id and is_blocked(session, viewer_id, profile.user_id)):
        raise _not_found("Perfil no encontrado.")
    uid = profile.user_id
    allowed = can_view_person(session, viewer_id, uid)
    shared = select(func.count()).select_from(Activity).where(Activity.user_id == uid)
    if uid != viewer_id:
        shared = shared.where(Activity.visibility == "followers")
    recent: list[dict] = []
    if allowed:
        rows = session.exec(
            select(Activity, SocialProfile)
            .join(SocialProfile, col(SocialProfile.user_id) == Activity.user_id)
            .where(Activity.user_id == uid, visible_clause(viewer_id))
            .order_by(col(Activity.start_time).desc(), col(Activity.id).desc())
            .limit(PROFILE_RECENT)
        ).all()
        recent = feed_items(session, viewer_id, list(rows))
    return {
        "person": person_out(session, viewer_id, [profile])[0],
        "counts": {
            "followers": _accepted_count(session, Follow.followee_id, uid),
            "following": _accepted_count(session, Follow.follower_id, uid),
            "activities": session.exec(shared).one(),
        },
        "can_view": allowed,
        "recent": recent,
    }


def _notify(session: Session, user_id: int, key: str, title: str, body: str, url: str) -> bool:
    """Push de tipo «social» si la persona tiene el módulo activado (respeta sus preferencias y no repite `key`)."""
    if not modules.enabled(session, "social", user_id):
        return False
    try:
        return notifications.notify(session, user_id, "social", key, title, body, url)
    except Exception:  # noqa: BLE001 - un fallo de push nunca debe romper la acción social
        logger.warning("No se pudo enviar el aviso social", extra={"key": key.split(":")[0]})
        session.rollback()
        return False


def _target_profile(session: Session, me: int, target_id: int) -> SocialProfile:
    if target_id == me:
        raise SocialError(400, "SELF", "No puedes hacer eso contigo.")
    profile = session.exec(_active_profiles().where(SocialProfile.user_id == target_id)).first()
    if profile is None or is_blocked(session, me, target_id):
        raise _not_found("Persona no encontrada.")
    return profile


def follow(session: Session, me: int, target_id: int) -> str:
    """Seguir: perfil público → aceptado al momento; privado → solicitud pendiente. Avisa a la otra persona."""
    my_profile = require_profile(session, me)
    target = _target_profile(session, me, target_id)
    existing = session.exec(select(Follow).where(Follow.follower_id == me, Follow.followee_id == target_id)).first()
    if existing is not None:
        return existing.status
    public = target.visibility == "public"
    row = Follow(follower_id=me, followee_id=target_id, status="accepted" if public else "pending",
                 accepted_at=datetime.now(UTC) if public else None)  # fmt: skip
    session.add(row)
    try:
        session.commit()
    except IntegrityError:  # doble clic: ya existe
        session.rollback()
        return follow_status(session, me, target_id)
    if public:
        _notify(
            session,
            target_id,
            f"follow:{me}:{target_id}:accepted",
            "Tienes un nuevo seguidor",
            f"{my_profile.display_name} (@{my_profile.handle}) ha empezado a seguirte.",
            f"/u/{my_profile.handle}",
        )
    else:
        _notify(session, target_id, f"follow:{me}:{target_id}:pending", "Nueva solicitud para seguirte",
                f"{my_profile.display_name} (@{my_profile.handle}) quiere seguirte.", "/social/personas")  # fmt: skip
    return row.status


def unfollow(session: Session, me: int, target_id: int) -> None:
    """Deja de seguir o cancela la solicitud (si no había nada, no hace nada)."""
    row = session.exec(select(Follow).where(Follow.follower_id == me, Follow.followee_id == target_id)).first()
    if row is not None:
        session.delete(row)
        session.commit()


def remove_follower(session: Session, me: int, follower_id: int) -> None:
    unfollow(session, follower_id, me)


def _list_people(session: Session, viewer_id: int, ids_query: Any) -> list[dict]:
    rows = session.exec(
        _active_profiles()
        .where(col(SocialProfile.user_id).in_(ids_query), _not_blocked(SocialProfile.user_id, viewer_id))
        .order_by(SocialProfile.display_name)
    ).all()
    return person_out(session, viewer_id, list(rows))


def requests(session: Session, me: int) -> list[dict]:
    return _list_people(session, me, select(Follow.follower_id).where(
        Follow.followee_id == me, Follow.status == "pending"
    ))  # fmt: skip


def followers(session: Session, me: int) -> list[dict]:
    return _list_people(session, me, select(Follow.follower_id).where(
        Follow.followee_id == me, Follow.status == "accepted"
    ))  # fmt: skip


def following(session: Session, me: int) -> list[dict]:
    return _list_people(session, me, _followees(me))


def blocked_list(session: Session, me: int) -> list[dict]:
    rows = session.exec(
        select(SocialProfile)
        .where(col(SocialProfile.user_id).in_(select(Block.blocked_id).where(Block.blocker_id == me)))
        .order_by(SocialProfile.display_name)
    ).all()
    return person_out(session, me, list(rows))


def _pending_request(session: Session, me: int, follower_id: int) -> Follow:
    row = session.exec(select(Follow).where(
        Follow.follower_id == follower_id, Follow.followee_id == me, Follow.status == "pending"
    )).first()  # fmt: skip
    if row is None:
        raise _not_found("Solicitud no encontrada.")
    return row


def accept_request(session: Session, me: int, follower_id: int) -> None:
    row = _pending_request(session, me, follower_id)
    row.status = "accepted"
    row.accepted_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    profile = get_profile(session, me)
    if profile is not None:
        _notify(
            session,
            follower_id,
            f"follow:{follower_id}:{me}:approved",
            "Solicitud aceptada",
            f"{profile.display_name} (@{profile.handle}) ha aceptado tu solicitud.",
            f"/u/{profile.handle}",
        )


def reject_request(session: Session, me: int, follower_id: int) -> None:
    session.delete(_pending_request(session, me, follower_id))
    session.commit()


def block(session: Session, me: int, target_id: int) -> None:
    """Bloquea: corta el seguimiento en los dos sentidos y cancela los duelos pendientes o en curso."""
    if target_id == me:
        raise SocialError(400, "SELF", "No puedes bloquearte a ti mismo.")
    if session.get(User, target_id) is None:
        raise _not_found("Persona no encontrada.")
    if session.exec(select(Block).where(Block.blocker_id == me, Block.blocked_id == target_id)).first() is None:
        session.add(Block(blocker_id=me, blocked_id=target_id))
    for row in session.exec(select(Follow).where(or_(
        and_(Follow.follower_id == me, Follow.followee_id == target_id),
        and_(Follow.follower_id == target_id, Follow.followee_id == me),
    ))).all():  # fmt: skip
        session.delete(row)
    session.exec(update(Duel).where(
        or_(and_(Duel.challenger_id == me, Duel.opponent_id == target_id),
            and_(Duel.challenger_id == target_id, Duel.opponent_id == me)),
        col(Duel.status).in_(("pending", "active")),
    ).values(status="cancelled"))  # fmt: skip
    try:
        session.commit()
    except IntegrityError:  # doble clic
        session.rollback()


def unblock(session: Session, me: int, target_id: int) -> None:
    row = session.exec(select(Block).where(Block.blocker_id == me, Block.blocked_id == target_id)).first()
    if row is not None:
        session.delete(row)
        session.commit()


# ─── Mapa ────────────────────────────────────────────────────────────────────


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def trim_track(
    lats: list[float | None], lons: list[float | None], hide_m: int, max_points: int = TRACK_MAX_POINTS
) -> list[list[float]] | None:
    """
    Traza para compartir: quita los puntos a menos de `hide_m` metros (distancia acumulada) del principio y
    del final, para no revelar dónde vive o trabaja la persona, y la reduce a `max_points` puntos.

    Returns:
        [[lat, lon], …] o None si no hay GPS o no queda nada tras el recorte.
    """
    points = [(la, lo) for la, lo in zip(lats or [], lons or [], strict=False)
              if la is not None and lo is not None and not (la == 0 and lo == 0)]  # fmt: skip
    if len(points) < 2:
        return None
    cum = [0.0]
    for prev, cur in zip(points, points[1:], strict=False):
        cum.append(cum[-1] + _haversine_m(prev, cur))
    total = cum[-1]
    kept = [p for p, d in zip(points, cum, strict=True) if hide_m <= d <= total - hide_m]
    if len(kept) < 2:
        return None
    if len(kept) > max_points:
        step = (len(kept) - 1) / (max_points - 1)
        kept = [kept[round(i * step)] for i in range(max_points)]
    return [[round(la, 5), round(lo, 5)] for la, lo in kept]


# ─── Feed ────────────────────────────────────────────────────────────────────


def _avg_speed(a: Activity) -> float | None:
    seconds = a.moving_duration_s or a.duration_s
    if not a.distance_m or not seconds:
        return None
    return round(a.distance_m / seconds, 3)


def feed_items(session: Session, viewer_id: int, rows: list[tuple[Activity, SocialProfile]]) -> list[dict]:
    """
    Tarjetas del feed para actividades ya autorizadas. Kudos, comentarios, logros y trazas se cargan con una
    consulta cada uno para toda la página (sin N+1). Solo salen los campos permitidos.
    """
    if not rows:
        return []
    ids = [a.id for a, _ in rows]
    kudos = dict(session.exec(select(Kudos.activity_id, func.count()).where(
        col(Kudos.activity_id).in_(ids)).group_by(Kudos.activity_id)).all())  # fmt: skip
    kudoed = set(session.exec(select(Kudos.activity_id).where(
        col(Kudos.activity_id).in_(ids), Kudos.user_id == viewer_id)).all())  # fmt: skip
    comments = dict(session.exec(select(ActivityComment.activity_id, func.count()).where(
        col(ActivityComment.activity_id).in_(ids), col(ActivityComment.deleted_at).is_(None)
    ).group_by(ActivityComment.activity_id)).all())  # fmt: skip
    achievements: dict[int, list[dict]] = {}
    for aid, title, kind in session.exec(select(Achievement.activity_id, Achievement.title, Achievement.kind).where(
        col(Achievement.activity_id).in_(ids)).order_by(Achievement.id)).all():  # fmt: skip
        achievements.setdefault(aid, []).append({"title": title, "kind": kind})
    with_maps = [a.id for a, p in rows if p.show_maps]
    streams: dict[int, dict[str, list]] = {}
    if with_maps:
        for s in session.exec(select(ActivityStream).where(
            col(ActivityStream.activity_id).in_(with_maps), col(ActivityStream.channel).in_(("lat", "lon"))
        )).all():  # fmt: skip
            streams.setdefault(s.activity_id, {})[s.channel] = s.values
    items = []
    for a, p in rows:
        chans = streams.get(a.id, {})
        track = trim_track(chans.get("lat", []), chans.get("lon", []), p.hide_map_ends_m) if p.show_maps else None
        items.append({
            "activity_id": a.id,
            "owner": _owner(p),
            "sport": a.sport,
            "name": a.name,
            "start_time": a.start_time,
            "distance_m": a.distance_m,
            "duration_s": a.duration_s,
            "moving_duration_s": a.moving_duration_s,
            "avg_speed": _avg_speed(a) if p.show_pace else None,
            "elevation_gain_m": a.elevation_gain_m,
            "is_race": a.is_race,
            "track": track,
            "achievements": achievements.get(a.id, []),
            "kudos_count": kudos.get(a.id, 0),
            "kudoed_by_me": a.id in kudoed,
            "comments_count": comments.get(a.id, 0),
            "mine": a.user_id == viewer_id,
            "visibility": a.visibility,
        })  # fmt: skip
    return items


def feed(session: Session, viewer_id: int, before: datetime | None, limit: int) -> dict:
    """Las actividades propias y de quien sigues (aceptado) que puedes ver, de la más reciente hacia atrás."""
    if get_profile(session, viewer_id) is None:
        return {"items": [], "next_before": None}
    query = (
        select(Activity, SocialProfile)
        .join(SocialProfile, col(SocialProfile.user_id) == Activity.user_id)
        .join(User, col(User.id) == Activity.user_id)
        .where(visible_clause(viewer_id), User.status == UserStatus.ACTIVE)
    )
    if before is not None:
        query = query.where(Activity.start_time < before)
    rows = list(session.exec(
        query.order_by(col(Activity.start_time).desc(), col(Activity.id).desc()).limit(limit + 1)
    ).all())  # fmt: skip
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": feed_items(session, viewer_id, rows),
        "next_before": rows[-1][0].start_time.isoformat() if more and rows else None,
    }


# ─── Kudos y comentarios ─────────────────────────────────────────────────────


def _kudos_state(session: Session, viewer_id: int, activity_id: int) -> dict:
    count = session.exec(select(func.count()).select_from(Kudos).where(Kudos.activity_id == activity_id)).one()
    mine = session.exec(select(Kudos.id).where(Kudos.activity_id == activity_id, Kudos.user_id == viewer_id)).first()
    return {"kudos_count": count, "kudoed_by_me": mine is not None}


def _bucket() -> int:
    return int(datetime.now(UTC).timestamp()) // GROUP_SECONDS


def give_kudos(session: Session, me: int, activity_id: int) -> dict:
    """Kudos idempotente (dar dos veces cuenta uno). No a las propias. Aviso al dueño agrupado cada 10 min."""
    profile = require_profile(session, me)
    activity = visible_activity(session, me, activity_id)
    if activity.user_id == me:
        raise SocialError(400, "OWN_ACTIVITY", "No puedes darte kudos a ti mismo.")
    if session.exec(select(Kudos.id).where(Kudos.activity_id == activity_id, Kudos.user_id == me)).first() is None:
        session.add(Kudos(activity_id=activity_id, user_id=me))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            state = _kudos_state(session, me, activity_id)
            others = state["kudos_count"] - 1
            body = f"{profile.display_name} te ha dado kudos en «{activity.name or 'tu actividad'}»."
            if others > 0:
                body = (f"{profile.display_name} y {others} más te han dado kudos en "
                        f"«{activity.name or 'tu actividad'}».")  # fmt: skip
            _notify(session, activity.user_id, f"kudos:{activity_id}:{_bucket()}", "👏 Kudos", body,
                    f"/actividades/{activity_id}")  # fmt: skip
    return _kudos_state(session, me, activity_id)


def remove_kudos(session: Session, me: int, activity_id: int) -> dict:
    visible_activity(session, me, activity_id)
    row = session.exec(select(Kudos).where(Kudos.activity_id == activity_id, Kudos.user_id == me)).first()
    if row is not None:
        session.delete(row)
        session.commit()
    return _kudos_state(session, me, activity_id)


def kudos_list(session: Session, me: int, activity_id: int) -> list[dict]:
    visible_activity(session, me, activity_id)
    rows = session.exec(
        select(SocialProfile)
        .join(Kudos, col(Kudos.user_id) == SocialProfile.user_id)
        .where(Kudos.activity_id == activity_id, _not_blocked(SocialProfile.user_id, me))
        .order_by(col(Kudos.created_at).desc())
    ).all()
    return [_owner(p) for p in rows]


def _comment_out(c: ActivityComment, author: SocialProfile, me: int, owner_id: int) -> dict:
    return {
        "id": c.id,
        "author": _owner(author),
        "body": c.body,
        "created_at": c.created_at,
        "can_delete": me in (c.author_id, owner_id),
    }


def comments(session: Session, me: int, activity_id: int) -> list[dict]:
    activity = visible_activity(session, me, activity_id)
    rows = session.exec(
        select(ActivityComment, SocialProfile)
        .join(SocialProfile, col(SocialProfile.user_id) == ActivityComment.author_id)
        .where(ActivityComment.activity_id == activity_id, col(ActivityComment.deleted_at).is_(None),
               _not_blocked(ActivityComment.author_id, me))
        .order_by(ActivityComment.created_at, ActivityComment.id)
    ).all()  # fmt: skip
    return [_comment_out(c, p, me, activity.user_id) for c, p in rows]


def add_comment(session: Session, me: int, activity_id: int, body: str) -> dict:
    """Comentario saneado (≤ 500). Aviso al dueño como mucho uno cada 10 minutos por actividad."""
    profile = require_profile(session, me)
    activity = visible_activity(session, me, activity_id)
    text = clean_text(body, 500, multiline=True)
    if not text:
        raise SocialError(422, "VALIDATION_ERROR", "El comentario está vacío.")
    row = ActivityComment(activity_id=activity_id, author_id=me, body=text)
    session.add(row)
    session.commit()
    session.refresh(row)
    if activity.user_id != me:
        _notify(session, activity.user_id, f"comment:{activity_id}:{_bucket()}", "💬 Nuevo comentario",
                f"{profile.display_name}: {text[:100]}", f"/actividades/{activity_id}")  # fmt: skip
    return _comment_out(row, profile, me, activity.user_id)


def delete_comment(session: Session, me: int, comment_id: int) -> None:
    """Lo borra su autor o el dueño de la actividad (borrado lógico)."""
    row = session.get(ActivityComment, comment_id)
    if row is None or row.deleted_at is not None:
        raise _not_found("Comentario no encontrado.")
    activity = session.get(Activity, row.activity_id)
    if activity is None or not can_view(session, me, activity):
        raise _not_found("Comentario no encontrado.")
    if me not in (row.author_id, activity.user_id):
        raise SocialError(403, "FORBIDDEN", "Solo puede borrarlo quien lo escribió o el dueño de la actividad.")
    row.deleted_at = datetime.now(UTC)
    session.add(row)
    session.commit()


# ─── Periodos y métricas ─────────────────────────────────────────────────────


def today_local() -> date:
    return datetime.now(TZ).date()


def _add_month(day: date) -> date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def period_bounds(period: str, today: date) -> tuple[date, date, date, date]:
    """Periodo actual (inicio y fin incluidos) y el anterior, para semana (lunes a domingo) o mes natural."""
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6), start - timedelta(days=7), start - timedelta(days=1)
    start = today.replace(day=1)
    end = date(start.year, start.month, monthrange(start.year, start.month)[1])
    prev_end = start - timedelta(days=1)
    return start, end, prev_end.replace(day=1), prev_end


def _utc_range(start: date, end: date) -> tuple[datetime, datetime]:
    """Del inicio del día `start` al final del día `end` (Madrid), en UTC."""
    return (
        datetime.combine(start, time(), TZ).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time(), TZ).astimezone(UTC),
    )


def _metric_expr(metric: str) -> Any:
    if metric == "km":
        return func.coalesce(func.sum(Activity.distance_m), 0)
    if metric == "time":
        return func.coalesce(func.sum(func.coalesce(Activity.moving_duration_s, Activity.duration_s)), 0)
    if metric == "elevation":
        return func.coalesce(func.sum(Activity.elevation_gain_m), 0)
    if metric == "days":
        return func.count(func.distinct(cast(func.timezone("Europe/Madrid", Activity.start_time), Date)))
    value = cast(col(Activity.metrics)[metric].astext, Float)
    return func.min(func.nullif(value, 0))


def _format_value(metric: str, raw: float | None) -> float | None:
    if raw is None:
        return None
    if metric == "km":
        return round(float(raw) / 1000, 1)
    if metric in BEST_METRICS:
        return round(float(raw), 1)
    return int(round(float(raw)))


def _sport_filter(metric: str, sport: str) -> Any | None:
    if metric in BEST_METRICS:
        return col(Activity.sport).in_(family_members("running"))
    if sport in ("running", "cycling"):
        return col(Activity.sport).in_(family_members(sport))
    return None


def _totals(session: Session, user_ids: list[int], metric: str, sport: str, start: date, end: date,
            viewer_id: int | None) -> dict[int, float | None]:  # fmt: skip
    """
    Valor de la métrica por persona en una sola consulta agregada. Con `viewer_id`, cuenta todas las suyas
    y solo las «followers» de los demás; sin él (duelos), solo las «followers» de todos.
    """
    if not user_ids:
        return {}
    since, until = _utc_range(start, end)
    visible = Activity.visibility == "followers"
    if viewer_id is not None:
        visible = or_(Activity.user_id == viewer_id, visible)
    query = select(Activity.user_id, _metric_expr(metric)).where(
        col(Activity.user_id).in_(user_ids), Activity.start_time >= since, Activity.start_time < until, visible
    )
    sport_clause = _sport_filter(metric, sport)
    if sport_clause is not None:
        query = query.where(sport_clause)
    found = dict(session.exec(query.group_by(Activity.user_id)).all())
    empty = None if metric in BEST_METRICS else 0
    return {uid: _format_value(metric, found.get(uid, empty)) for uid in user_ids}


def _ranks(values: dict[int, float | None], names: dict[int, str]) -> list[tuple[int, int]]:
    """[(user_id, puesto)] de mayor a menor; empates comparten puesto (1, 1, 3)."""
    order = sorted(values, key=lambda uid: (-(values[uid] or 0), names.get(uid, "").lower(), uid))
    out: list[tuple[int, int]] = []
    for i, uid in enumerate(order):
        rank = out[-1][1] if i and (values[uid] or 0) == (values[order[i - 1]] or 0) else i + 1
        out.append((uid, rank))
    return out


# ─── Clasificación ───────────────────────────────────────────────────────────


def _participants(session: Session, me: int) -> dict[int, SocialProfile]:
    """Yo y a quien sigo (aceptado), con perfil, cuenta activa y sin bloqueo."""
    rows = session.exec(_active_profiles().where(or_(
        SocialProfile.user_id == me,
        and_(col(SocialProfile.user_id).in_(_followees(me)), _not_blocked(SocialProfile.user_id, me)),
    ))).all()  # fmt: skip
    return {p.user_id: p for p in rows}


def leaderboard(session: Session, me: int, period: str, metric: str, sport: str, today: date | None = None) -> dict:
    start, end, prev_start, prev_end = period_bounds(period, today or today_local())
    people = _participants(session, me)
    out = {"period_start": start, "period_end": end, "metric": metric, "rows": [], "my_rank": None,
           "gap_to_next": None, "next_name": None}  # fmt: skip
    if me not in people:
        return out
    ids = list(people)
    names = {uid: p.display_name for uid, p in people.items()}
    current = _totals(session, ids, metric, sport, start, end, me)
    previous = _totals(session, ids, metric, sport, prev_start, prev_end, me)
    prev_ranks = dict(_ranks(previous, names))
    for uid, rank in _ranks(current, names):
        p = people[uid]
        out["rows"].append({
            "user_id": uid, "display_name": p.display_name, "handle": p.handle, "value": current[uid],
            "rank": rank, "prev_rank": prev_ranks[uid] if previous[uid] else None, "me": uid == me,
        })  # fmt: skip
    mine = current[me] or 0
    out["my_rank"] = next(r["rank"] for r in out["rows"] if r["me"])
    above = [r for r in out["rows"] if (r["value"] or 0) > mine]
    if above:
        nxt = min(above, key=lambda r: r["value"])
        gap = nxt["value"] - mine
        out["gap_to_next"] = round(gap, 1) if metric == "km" else gap
        out["next_name"] = nxt["display_name"]
    return out


# ─── Duelos ──────────────────────────────────────────────────────────────────


def duel_end(start: date, duration: str) -> date:
    if duration == "1m":
        return _add_month(start) - timedelta(days=1)
    return start + timedelta(days=(14 if duration == "2w" else 7) - 1)


def duel_values(session: Session, duel: Duel) -> tuple[float | None, float | None]:
    """Marcador al vuelo: solo actividades «followers» de los dos en el periodo (la misma regla para ambos)."""
    if duel.status == "finished":
        return duel.challenger_value, duel.opponent_value
    if duel.status != "active":
        return None, None
    values = _totals(session, [duel.challenger_id, duel.opponent_id], duel.metric, duel.sport, duel.start_date,
                     duel.end_date, None)  # fmt: skip
    return values[duel.challenger_id], values[duel.opponent_id]


def leader(duel: Duel, challenger_value: float | None, opponent_value: float | None) -> int | None:
    """Quién va ganando (None si empate o sin datos). En mejores marcas gana el tiempo menor."""
    c, o = challenger_value, opponent_value
    if duel.metric in BEST_METRICS:
        if c is None and o is None:
            return None
        if o is None or (c is not None and c < o):
            return duel.challenger_id
        if c is None or o < c:
            return duel.opponent_id
        return None
    c, o = c or 0, o or 0
    if c == o:
        return None
    return duel.challenger_id if c > o else duel.opponent_id


def _profiles_map(session: Session, ids: set[int]) -> dict[int, SocialProfile]:
    if not ids:
        return {}
    return {p.user_id: p for p in session.exec(select(SocialProfile).where(col(SocialProfile.user_id).in_(ids)))}


def _person_ref(profiles: dict[int, SocialProfile], uid: int) -> dict:
    p = profiles.get(uid)
    return _owner(p) if p else {"user_id": uid, "display_name": "", "handle": ""}


def duel_out(session: Session, duel: Duel, me: int, profiles: dict[int, SocialProfile]) -> dict:
    cv, ov = duel_values(session, duel)
    i_am_challenger = duel.challenger_id == me
    return {
        "id": duel.id,
        "challenger": _person_ref(profiles, duel.challenger_id),
        "opponent": _person_ref(profiles, duel.opponent_id),
        "metric": duel.metric,
        "sport": duel.sport,
        "start_date": duel.start_date,
        "end_date": duel.end_date,
        "status": duel.status,
        "my_value": cv if i_am_challenger else ov,
        "their_value": ov if i_am_challenger else cv,
        "winner_id": duel.winner_id,
        "i_am_challenger": i_am_challenger,
    }


def _mine(me: int) -> Any:
    return or_(Duel.challenger_id == me, Duel.opponent_id == me)


def list_duels(session: Session, me: int) -> dict:
    open_rows = list(session.exec(select(Duel).where(_mine(me), col(Duel.status).in_(("pending", "active")))
                                  .order_by(Duel.end_date, Duel.id)).all())  # fmt: skip
    finished = list(
        session.exec(
            select(Duel)
            .where(_mine(me), Duel.status == "finished")
            .order_by(col(Duel.end_date).desc(), col(Duel.id).desc())
            .limit(20)
        ).all()
    )
    rows = open_rows + finished
    profiles = _profiles_map(session, {d.challenger_id for d in rows} | {d.opponent_id for d in rows})
    out: dict[str, list] = {"active": [], "pending_in": [], "pending_out": [], "finished": []}
    for d in rows:
        if d.status == "active":
            bucket = "active"
        elif d.status == "finished":
            bucket = "finished"
        else:
            bucket = "pending_out" if d.challenger_id == me else "pending_in"
        out[bucket].append(duel_out(session, d, me, profiles))
    return out


def _duel_label(duel: Duel) -> str:
    return {"km": "más km", "time": "más tiempo", "elevation": "más desnivel", "days": "más días activos",
            "best_5k": "mejor 5K", "best_10k": "mejor 10K"}[duel.metric]  # fmt: skip


def create_duel(session: Session, me: int, opponent_id: int, metric: str, sport: str, duration: str) -> dict:
    """
    Reta a alguien: hace falta seguirse mutuamente (aceptado) o que su perfil sea público. Las fechas son
    provisionales hasta que acepta.
    """
    my_profile = require_profile(session, me)
    target = _target_profile(session, me, opponent_id)
    mutual = (follow_status(session, me, opponent_id) == "accepted"
              and follow_status(session, opponent_id, me) == "accepted")  # fmt: skip
    if not mutual and target.visibility != "public":
        raise SocialError(403, "NOT_FRIENDS", "Solo puedes retar a quien te sigue y sigues, o a un perfil público.")
    exists = session.exec(select(Duel.id).where(
        or_(and_(Duel.challenger_id == me, Duel.opponent_id == opponent_id),
            and_(Duel.challenger_id == opponent_id, Duel.opponent_id == me)),
        col(Duel.status).in_(("pending", "active")),
    )).first()  # fmt: skip
    if exists is not None:
        raise SocialError(409, "DUEL_EXISTS", "Ya tenéis un duelo pendiente o en marcha.")
    start = today_local()
    duel = Duel(challenger_id=me, opponent_id=opponent_id, metric=metric, sport=sport, duration=duration,
                start_date=start, end_date=duel_end(start, duration))  # fmt: skip
    session.add(duel)
    session.commit()
    session.refresh(duel)
    span = {"1w": "1 semana", "2w": "2 semanas", "1m": "1 mes"}[duration]
    _notify(
        session,
        opponent_id,
        f"duel:{duel.id}:new",
        "⚔️ Te han retado",
        f"{my_profile.display_name} te reta a un duelo: {_duel_label(duel)} en {span}.",
        "/social/duelos",
    )
    return duel_out(session, duel, me, _profiles_map(session, {me, opponent_id}))


def _my_duel(session: Session, me: int, duel_id: int) -> Duel:
    duel = session.get(Duel, duel_id)
    if duel is None or me not in (duel.challenger_id, duel.opponent_id):
        raise _not_found("Duelo no encontrado.")
    return duel


def _state_error() -> SocialError:
    return SocialError(409, "DUEL_STATE", "El duelo ya no admite ese cambio.")


def duel_action(session: Session, me: int, duel_id: int, action: str) -> dict:
    """
    accept / decline: solo la persona retada y si está pendiente. Al aceptar empieza ese día.
    cancel: quien reta mientras está pendiente, o cualquiera de los dos si está en marcha.
    """
    duel = _my_duel(session, me, duel_id)
    if action in ("accept", "decline"):
        if duel.opponent_id != me or duel.status != "pending":
            raise _state_error()
        if action == "accept":
            if is_blocked(session, duel.challenger_id, duel.opponent_id):
                raise _state_error()
            duel.status = "active"
            duel.start_date = today_local()
            duel.end_date = duel_end(duel.start_date, duel.duration)
        else:
            duel.status = "declined"
    elif action == "cancel":
        allowed = (duel.status == "pending" and duel.challenger_id == me) or duel.status == "active"
        if not allowed:
            raise _state_error()
        duel.status = "cancelled"
    else:
        raise _not_found()
    session.add(duel)
    session.commit()
    session.refresh(duel)
    if action == "accept":
        profile = get_profile(session, me)
        name = profile.display_name if profile else "Tu rival"
        _notify(session, duel.challenger_id, f"duel:{duel.id}:accepted", "⚔️ Duelo aceptado",
                f"{name} ha aceptado tu reto. ¡Empieza hoy!", "/social/duelos")  # fmt: skip
    return duel_out(session, duel, me, _profiles_map(session, {duel.challenger_id, duel.opponent_id}))


def _fmt(metric: str, value: float | None) -> str:
    if value is None:
        return "sin marca"
    if metric == "km":
        return f"{num(value, 1)} km"
    if metric == "elevation":
        return f"{int(value)} m"
    if metric == "days":
        return f"{int(value)} días"
    seconds = int(round(value))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} min" if h else f"{m}:{s:02d}"


def _fmt_short(metric: str, value: float | None) -> str:
    """Segundo número de «23,4 km contra 21,0»: sin unidad."""
    text = _fmt(metric, value)
    return text.removesuffix(" km").removesuffix(" m").removesuffix(" días")


def close_duels(session: Session, today: date | None = None) -> int:
    """Cierra los duelos en marcha cuyo último día ya pasó: guarda el marcador, decide ganador (o empate) y avisa."""
    today = today or today_local()
    due = session.exec(select(Duel).where(Duel.status == "active", Duel.end_date < today)).all()
    for duel in due:
        cv, ov = duel_values(session, duel)
        duel.challenger_value, duel.opponent_value = cv, ov
        duel.winner_id = leader(duel, cv, ov)
        duel.status = "finished"
        session.add(duel)
        session.commit()
        profiles = _profiles_map(session, {duel.challenger_id, duel.opponent_id})
        for uid, mine, theirs in ((duel.challenger_id, cv, ov), (duel.opponent_id, ov, cv)):
            other = duel.opponent_id if uid == duel.challenger_id else duel.challenger_id
            name = _person_ref(profiles, other)["display_name"] or "tu rival"
            if duel.winner_id is None:
                title = "🤝 Duelo terminado en empate"
            elif duel.winner_id == uid:
                title = "🏆 ¡Has ganado el duelo!"
            else:
                title = "Duelo terminado"
            body = f"Contra {name}: {_fmt(duel.metric, mine)} frente a {_fmt(duel.metric, theirs)}."
            _notify(session, uid, f"duel:{duel.id}:end", title, body, "/social/duelos")
    return len(due)


def duel_overtakes(session: Session, now: datetime | None = None) -> int:
    """
    Avisa a quien acaban de adelantar en un duelo en marcha. Se compara con `last_leader_id`, así que cada
    adelantamiento avisa una sola vez aunque la tarea se ejecute muchas.
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H")
    sent = 0
    for duel in session.exec(select(Duel).where(Duel.status == "active")).all():
        cv, ov = duel_values(session, duel)
        current = leader(duel, cv, ov)
        if current is None or current == duel.last_leader_id:
            continue
        previous = duel.last_leader_id
        duel.last_leader_id = current
        session.add(duel)
        session.commit()
        if previous is None:
            continue  # primer líder: nadie ha sido adelantado
        passed = duel.opponent_id if current == duel.challenger_id else duel.challenger_id
        lead_value, passed_value = (cv, ov) if current == duel.challenger_id else (ov, cv)
        name = _person_ref(_profiles_map(session, {current}), current)["display_name"] or "Tu rival"
        body = f"{name} te ha pasado: {_fmt(duel.metric, lead_value)} contra {_fmt_short(duel.metric, passed_value)}"
        if _notify(session, passed, f"duel:{duel.id}:lead:{current}:{stamp}", "⚔️ Te han adelantado", body,
                   "/social/duelos"):  # fmt: skip
            sent += 1
    return sent


# ─── Resumen para Hoy ────────────────────────────────────────────────────────


def summary(session: Session, me: int) -> dict:
    has_profile = get_profile(session, me) is not None
    out = {"has_profile": has_profile, "my_rank": None, "friends": 0, "gap_to_next": None, "next_name": None,
           "metric": "km", "active_duel": None}  # fmt: skip
    if not has_profile:
        return out
    board = leaderboard(session, me, "week", "km", "all")
    out.update(my_rank=board["my_rank"], friends=max(len(board["rows"]) - 1, 0), gap_to_next=board["gap_to_next"],
               next_name=board["next_name"])  # fmt: skip
    duel = session.exec(select(Duel).where(_mine(me), Duel.status == "active").order_by(Duel.end_date)).first()
    if duel is not None:
        out["active_duel"] = duel_out(session, duel, me, _profiles_map(session, {duel.challenger_id, duel.opponent_id}))
    return out
