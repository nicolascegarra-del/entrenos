"""
Recepción de datos de Health Connect (Android) para relojes sin API web: Samsung Galaxy Watch,
Xiaomi/Amazfit/Zepp, Huawei, Wear OS…

La app de código abierto `health-connect-webhook` (externa, AGPL; no se incluye código suyo) envía un
JSON con `exercise`, `heart_rate`, `sleep`, `steps`… a nuestra URL con una cabecera `X-Api-Key` que es
el token personal (aquí solo se guarda su hash).
"""

import secrets
from datetime import UTC, date, datetime

from sqlmodel import Session, select

from app.models import DailyMetric, IngestToken
from app.services.accounts import token_hash
from app.services.file_import import ImportedActivity, after_import, save_imported, sport_name

MAX_ITEMS = 5000


def create_token(session: Session, user_id: int) -> str:
    """Nuevo token (sustituye al anterior). Se muestra una sola vez."""
    token = "hc_" + secrets.token_urlsafe(32)
    row = session.get(IngestToken, user_id) or IngestToken(user_id=user_id, token_hash="", hint="")
    row.token_hash, row.hint, row.last_used_at = token_hash(token), token[-4:], None
    session.add(row)
    session.commit()
    return token


def user_for_token(session: Session, token: str | None) -> int | None:
    if not token or not token.startswith("hc_"):
        return None
    row = session.exec(select(IngestToken).where(IngestToken.token_hash == token_hash(token))).first()
    if row is None:
        return None
    row.last_used_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return row.user_id


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _set_daily(session: Session, user_id: int, day: date, key: str, value: float, keep_max: bool = False) -> None:
    row = session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day == day)).first()
    row = row or DailyMetric(user_id=user_id, day=day)
    metrics = dict(row.metrics or {})
    metrics[key] = max(value, metrics.get(key) or 0) if keep_max else value
    row.metrics = metrics
    session.add(row)


def ingest(session: Session, user_id: int, payload: dict) -> dict:
    """
    Guarda entrenos (sin duplicar con Garmin u otros relojes), sueño y pasos diarios.

    Returns:
        Cuántos elementos de cada tipo se han procesado.
    """
    counts = {"exercise": 0, "duplicates": 0, "sleep": 0, "steps_days": 0}
    hr_samples = []
    for h in (payload.get("heart_rate") or [])[: MAX_ITEMS * 10]:
        t, bpm = _time(h.get("time")), h.get("avg", h.get("bpm"))
        if t and isinstance(bpm, int | float):
            hr_samples.append((t, float(bpm)))
    for e in (payload.get("exercise") or [])[:MAX_ITEMS]:
        start, end = _time(e.get("start_time")), _time(e.get("end_time"))
        duration = e.get("duration_seconds") or ((end - start).total_seconds() if start and end else None)
        if not start or not duration:
            continue
        hrs = [b for t, b in hr_samples if start <= t <= (end or start)]
        act = ImportedActivity(
            sport=sport_name(e.get("type")),
            start_time=start.astimezone(UTC),
            duration_s=float(duration),
            distance_m=e.get("distance_meters"),
            avg_hr=round(sum(hrs) / len(hrs)) if hrs else None,
            max_hr=max(hrs) if hrs else None,
        )
        activity, new = save_imported(session, user_id, act, "health_connect", f"{e.get('type')}:{start.isoformat()}")
        if new:
            metrics = {k: v for k in ("steps", "avg_cadence_spm") if isinstance(v := e.get(k), int | float)}
            if metrics:
                activity.metrics = {**activity.metrics, **metrics}
                session.add(activity)
            counts["exercise"] += 1
        else:
            counts["duplicates"] += 1
    for s in (payload.get("sleep") or [])[:MAX_ITEMS]:
        end = _time(s.get("session_end_time"))
        if end and isinstance(s.get("duration_seconds"), int | float):
            _set_daily(session, user_id, end.date(), "sleep_seconds", float(s["duration_seconds"]))
            counts["sleep"] += 1
    steps: dict[date, float] = {}
    for st in (payload.get("steps") or [])[:MAX_ITEMS]:
        t = _time(st.get("start_time"))
        if t and isinstance(st.get("count"), int | float):
            steps[t.date()] = steps.get(t.date(), 0) + st["count"]
    for day, total in steps.items():
        # Si llega el mismo día en varios envíos se queda el mayor (no se suman dos veces).
        _set_daily(session, user_id, day, "steps_daily", total, keep_max=True)
        counts["steps_days"] += 1
    session.commit()
    if counts["exercise"]:
        after_import(session, user_id)
    return counts
