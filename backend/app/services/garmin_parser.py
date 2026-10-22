"""
Traduce las respuestas JSON de Garmin Connect al modelo flexible.

Funciones puras (sin BD ni red) para poder testearlas con fixtures y reprocesar
la capa raw cuando el catálogo aprende métricas nuevas. Si cambias la lógica,
sube `PARSER_VERSION` para que `reprocess` sepa qué actividades rehacer.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.models import MetricScope
from app.services.metric_catalog import CATALOG

PARSER_VERSION = 4  # v4: tiempo en zonas de FC (distribución de intensidad)

# Valores centinela que Garmin usa para "sin dato" (ej. potencia sin sensor = 65535).
_SENTINELS = {65535.0}
# Canales de detalle que no aportan nada como serie (el tiempo se recalcula aparte).
_SKIP_DETAIL_KEYS = {"directTimestamp", "sumDuration", "sumElapsedDuration", "sumMovingDuration"}
TIME_CHANNEL = "time"


def get_path(obj: Any, path: str) -> Any:
    """
    Lee una ruta con puntos e índices numéricos, ej. "0.generic.vo2MaxPreciseValue".
    Admite alternativas separadas por "|": devuelve la primera que tenga valor.
    """
    if "|" in path:
        return next((v for alt in path.split("|") if (v := get_path(obj, alt)) is not None), None)
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            if not part.isdigit() or int(part) >= len(obj):
                return None
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _clean(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return None if value in _SENTINELS else float(value)


def _sources(scope: MetricScope, source: str) -> dict[str, str]:
    """Mapa {clave_catálogo: ruta} de las métricas del catálogo que se leen de `source`."""
    return {d.key: d.sources[source] for d in CATALOG if d.scope == scope and source in d.sources}


def _parse_gmt(value: str) -> datetime:
    # Garmin usa "2026-10-14 15:58:05" en resúmenes y "2026-10-14T15:58:05.0" en vueltas.
    return datetime.fromisoformat(value.replace(" ", "T")).replace(tzinfo=UTC)


@dataclass
class ParsedActivity:
    garmin_activity_id: int
    garmin_device_id: int | None
    sport: str
    name: str
    start_time: datetime
    timezone: str | None
    duration_s: float
    moving_duration_s: float | None
    distance_m: float | None
    avg_hr: float | None
    max_hr: float | None
    elevation_gain_m: float | None
    calories: float | None
    metrics: dict[str, float] = field(default_factory=dict)
    is_race: bool = False


def parse_summary(summary: dict) -> ParsedActivity:
    start = _parse_gmt(summary["startTimeGMT"])
    timezone = None
    if summary.get("startTimeLocal"):
        offset_min = round((_parse_gmt(summary["startTimeLocal"]) - start).total_seconds() / 60)
        sign = "+" if offset_min >= 0 else "-"
        timezone = f"{sign}{abs(offset_min) // 60:02d}:{abs(offset_min) % 60:02d}"

    metrics = {}
    for key, path in _sources(MetricScope.ACTIVITY, "garmin_summary").items():
        value = _clean(get_path(summary, path))
        if value is not None:
            metrics[key] = value

    return ParsedActivity(
        garmin_activity_id=int(summary["activityId"]),
        garmin_device_id=summary.get("deviceId"),
        sport=(summary.get("activityType") or {}).get("typeKey") or "other",
        name=summary.get("activityName") or "",
        start_time=start,
        timezone=timezone,
        duration_s=float(summary.get("duration") or 0),
        moving_duration_s=_clean(summary.get("movingDuration")),
        distance_m=_clean(summary.get("distance")),
        avg_hr=_clean(summary.get("averageHR")),
        max_hr=_clean(summary.get("maxHR")),
        elevation_gain_m=_clean(summary.get("elevationGain")),
        calories=_clean(summary.get("calories")),
        metrics=metrics,
        is_race=((summary.get("eventType") or {}).get("typeKey") == "race"),
    )


def parse_details(details: dict | None) -> dict[str, list[float | None]]:
    """
    Convierte las métricas de detalle en canales alineados por índice.

    Las claves conocidas se renombran a la clave del catálogo (directHeartRate → hr);
    las desconocidas se guardan con su nombre de Garmin, así un sensor nuevo no se pierde.
    Los canales sin ningún dato válido se descartan.
    """
    if not details or not details.get("activityDetailMetrics"):
        return {}
    index = {d["key"]: d["metricsIndex"] for d in details.get("metricDescriptors", [])}
    rows = [r.get("metrics") or [] for r in details["activityDetailMetrics"]]

    def column(i: int) -> list[float | None]:
        return [_clean(row[i]) if i < len(row) else None for row in rows]

    def has_data(garmin_key: str) -> bool:
        return garmin_key in index and any(v is not None for v in column(index[garmin_key]))

    # Para cada métrica del catálogo, la primera alternativa con datos recibe la clave del
    # catálogo; el resto de canales (incluidas las otras alternativas) conservan su nombre.
    to_catalog: dict[str, str] = {}
    for key, paths in _sources(MetricScope.STREAM, "garmin_details").items():
        chosen = next((p for p in paths.split("|") if has_data(p)), None)
        if chosen:
            to_catalog[chosen] = key

    channels: dict[str, list[float | None]] = {}
    if "directTimestamp" in index:
        stamps = column(index["directTimestamp"])
        first = next((t for t in stamps if t is not None), None)
        if first is not None:
            channels[TIME_CHANNEL] = [None if t is None else (t - first) / 1000 for t in stamps]
    elif "sumDuration" in index:
        channels[TIME_CHANNEL] = column(index["sumDuration"])

    for garmin_key, i in index.items():
        if garmin_key in _SKIP_DETAIL_KEYS:
            continue
        values = column(i)
        if any(v is not None for v in values):
            channels[to_catalog.get(garmin_key, garmin_key)] = values
    return channels


# Métricas de vuelta que no son columnas: clave → posibles campos de Garmin (primero que exista).
_LAP_METRICS = {
    "avg_cadence": ("averageRunCadence", "averageBikeCadence"),
    "avg_power": ("averagePower",),
    "normalized_power": ("normalizedPower",),
    "avg_stride_length": ("strideLength",),
    "elevation_gain_m": ("elevationGain",),
    "elevation_loss_m": ("elevationLoss",),
    "max_speed": ("maxSpeed",),
}


def parse_laps(splits: dict | None, activity_start: datetime) -> list[dict]:
    laps = []
    for position, lap in enumerate((splits or {}).get("lapDTOs") or []):
        start = _parse_gmt(lap["startTimeGMT"]) if lap.get("startTimeGMT") else activity_start
        metrics = {}
        for key, candidates in _LAP_METRICS.items():
            value = next((v for c in candidates if (v := _clean(lap.get(c))) is not None), None)
            if value is not None:
                metrics[key] = value
        laps.append(
            {
                "index": position,
                "start_offset_s": max((start - activity_start).total_seconds(), 0.0),
                "duration_s": float(lap.get("duration") or 0),
                "distance_m": _clean(lap.get("distance")),
                "avg_hr": _clean(lap.get("averageHR")),
                "max_hr": _clean(lap.get("maxHR")),
                "avg_speed": _clean(lap.get("averageSpeed")),
                "metrics": metrics,
            }
        )
    return laps


def parse_daily(raw: dict[str, Any]) -> dict[str, float]:
    """
    Extrae las métricas diarias del catálogo.

    Args:
        raw: Respuestas de Garmin por fuente, ej. {"stats": {...}, "hrv": {...}, "sleep": {...}}.
            Las fuentes del catálogo (`garmin_stats`...) se buscan sin el prefijo `garmin_`.
    """
    metrics = {}
    for definition in CATALOG:
        if definition.scope != MetricScope.DAILY:
            continue
        for source, path in definition.sources.items():
            value = _clean(get_path(raw.get(source.removeprefix("garmin_")), path))
            if value is not None:
                metrics[definition.key] = value
                break
    return metrics
