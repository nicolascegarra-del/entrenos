"""
Métricas diarias de varias fuentes en la misma fila (`DailyMetric`), sin que una borre a otra.

Cada fuente (garmin, coros, health_connect, apple, oura) guarda SUS valores en `raw["_sources"][fuente]`
y `metrics` es siempre el resultado de combinarlas (`merge_daily`), con la fuente de cada clave en
`metric_sources`:

- Sueño y recuperación (`sleep_*`, `hrv_last_night`, `resting_hr`, `readiness_score`, temperatura, SpO2,
  respiración y los contribuidores `oura_readiness_*` / `oura_sleep_*`): según la preferencia de la persona
  (`UserSettings.recovery_source`): `oura`, `watch` (el reloj) o `auto` (Oura si está conectado). Si la
  fuente elegida no tiene ese dato, se usa la otra.
- Lo demás: el reloj (garmin > coros > health_connect > apple) y, si ninguno lo tiene, Oura.
- Claves escritas por otras partes de la app sin fuente (p. ej. el umbral de Garmin `lt_speed`) se respetan.

El raw de Garmin sigue en el nivel superior de `raw` (como siempre); el de otras fuentes, en `raw[fuente]`.
"""

from datetime import date, timedelta

from sqlmodel import Session, col, select

from app.models import DailyMetric, OuraConnection
from app.services.sync_schedule import get_user_settings

WATCH_SOURCES = ("garmin", "coros", "health_connect", "apple")
SOURCES = (*WATCH_SOURCES, "oura")
SOURCES_KEY = "_sources"
RECOVERY_KEYS = frozenset({
    "hrv_last_night", "resting_hr", "readiness_score", "temperature_deviation", "temperature_trend_deviation",
    "spo2_avg", "breath_rate", "breathing_disturbance_index", "avg_hr_sleep", "naps_s", "restless_periods",
    "time_in_bed_s",
})  # fmt: skip
RECOVERY_PREFIXES = ("sleep_", "oura_readiness_", "oura_sleep_")
RECOMPUTE_DAYS = 365

Prefs = tuple[str, bool]  # (recovery_source, oura_connected)


def is_recovery_key(key: str) -> bool:
    return key in RECOVERY_KEYS or key.startswith(RECOVERY_PREFIXES)


def preferences(session: Session, user_id: int) -> Prefs:
    """Preferencia de fuente de recuperación y si Oura está conectado."""
    return get_user_settings(session, user_id).recovery_source or "auto", session.get(
        OuraConnection, user_id
    ) is not None


def uses_oura(prefs: Prefs) -> bool:
    """¿El sueño y la recuperación salen de Oura? (auto = sí, si está conectado)."""
    source, connected = prefs
    return source == "oura" or (source == "auto" and connected)


def by_source(row: DailyMetric) -> dict[str, dict]:
    """Valores guardados de cada fuente para ese día."""
    stored = (row.raw or {}).get(SOURCES_KEY) or {}
    return {k: dict(v) for k, v in stored.items() if isinstance(v, dict)}


LEGACY = "_sin_fuente"


def _order(prefs: Prefs, recovery: bool, known: set[str]) -> list[str]:
    """
    Prioridad de fuentes para una clave. Lo escrito sin fuente (`LEGACY`: datos antiguos o escritos aparte)
    va como antes: Garmin, COROS y Health Connect lo sustituyen; Apple y Oura solo rellenan si falta.
    """
    watch = ["garmin", "coros", "health_connect", LEGACY, "apple"]
    order = ["oura", *watch] if recovery and uses_oura(prefs) else [*watch, "oura"]
    return order + sorted(known - set(order))  # fuentes nuevas, al final


def merge_daily(row: DailyMetric, recovery_source: str, oura_connected: bool) -> None:
    """Recalcula `metrics` y `metric_sources` a partir de los valores de cada fuente (función pura sobre la fila)."""
    prefs = (recovery_source, oura_connected)
    stored = by_source(row)
    previous = row.metric_sources or {}
    # Lo que se escribió sin fuente (umbral de Garmin, datos antiguos sin migrar…) cuenta como una fuente más.
    stored[LEGACY] = {k: v for k, v in (row.metrics or {}).items() if k not in previous}
    metrics: dict = {}
    sources: dict[str, str] = {}
    keys = {k for values in stored.values() for k in values}
    for key in sorted(keys):
        for src in _order(prefs, is_recovery_key(key), set(stored)):
            value = stored.get(src, {}).get(key)
            if value is not None:
                metrics[key] = value
                if src != LEGACY:
                    sources[key] = src
                break
    row.metrics, row.metric_sources = metrics, sources


def _row(session: Session, user_id: int, day: date) -> DailyMetric:
    return session.exec(
        select(DailyMetric).where(DailyMetric.user_id == user_id, DailyMetric.day == day)
    ).first() or DailyMetric(user_id=user_id, day=day)


def set_source_metrics(
    session: Session,
    user_id: int,
    day: date,
    source: str,
    metrics: dict,
    raw: dict | None = None,
    *,
    replace: bool = True,
    prefs: Prefs | None = None,
) -> DailyMetric:
    """
    Guarda los valores de una fuente para un día y recombina la fila (no hace commit).

    Args:
        metrics: Claves del catálogo → valor. Los `None` se ignoran.
        raw: Respuesta original de la fuente. La de Garmin sustituye al raw de nivel superior (como antes);
            la de las demás se guarda en `raw[source]`. `None` = no tocar el raw.
        replace: True = estos son TODOS los valores de la fuente ese día (lo que falte se quita);
            False = solo se actualizan las claves recibidas.
        prefs: (recovery_source, oura_connected) si ya se conocen (evita consultas en bucles).
    """
    row = _row(session, user_id, day)
    stored = by_source(row)
    clean = {k: v for k, v in metrics.items() if v is not None}
    values = clean if replace else {**stored.get(source, {}), **clean}
    if values:
        stored[source] = values
    else:
        stored.pop(source, None)
    new_raw = dict(row.raw or {})
    if raw is not None:
        if source == "garmin":
            keep = {k: v for k, v in new_raw.items() if k.startswith("_") or k in SOURCES}
            new_raw = {**raw, **keep}
        else:
            new_raw[source] = raw
    new_raw[SOURCES_KEY] = stored
    row.raw = new_raw
    merge_daily(row, *(prefs or preferences(session, user_id)))
    session.add(row)
    return row


def source_value(row: DailyMetric | None, source: str, key: str) -> float | None:
    """Valor de una fuente concreta (sin combinar)."""
    return by_source(row).get(source, {}).get(key) if row is not None else None


def recompute_user(session: Session, user_id: int, days: int = RECOMPUTE_DAYS, today: date | None = None) -> int:
    """Recombina los últimos `days` días (tras cambiar la preferencia o conectar/desconectar Oura)."""
    prefs = preferences(session, user_id)
    since = (today or date.today()) - timedelta(days=days)
    rows = session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id, col(DailyMetric.day) >= since)).all()
    for row in rows:
        merge_daily(row, *prefs)
        session.add(row)
    session.commit()
    return len(rows)


def remove_source(session: Session, user_id: int, source: str) -> int:
    """Quita todo lo de una fuente de las métricas diarias y recombina (borra las filas que quedan vacías)."""
    prefs = preferences(session, user_id)
    touched = 0
    for row in session.exec(select(DailyMetric).where(DailyMetric.user_id == user_id)).all():
        stored = by_source(row)
        if source not in stored and source not in (row.raw or {}):
            continue
        stored.pop(source, None)
        new_raw = {k: v for k, v in (row.raw or {}).items() if k != source}
        new_raw[SOURCES_KEY] = stored
        row.raw = new_raw
        merge_daily(row, *prefs)
        touched += 1
        only_bookkeeping = all(k == SOURCES_KEY for k in new_raw) and not stored
        if not row.metrics and only_bookkeeping:
            session.delete(row)
        else:
            session.add(row)
    session.commit()
    return touched
