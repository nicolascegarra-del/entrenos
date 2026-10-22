"""
Clima del día de carrera con Open-Meteo (gratis y sin clave):

- Carrera en los próximos 15 días → pronóstico horario.
- Carrera pasada → tiempo que hizo (archivo histórico).
- Más adelante → «climatología»: media de los últimos 5 años en esas fechas (±3 días) y a esa hora.

Se guarda en `RaceGoal.weather_cache` para no repetir llamadas (pronóstico 3 h, climatología 30 días).
"""

import logging
from datetime import UTC, date, datetime, timedelta
from statistics import fmean

import httpx

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_DAYS = 15
CLIMATE_YEARS = 5
CLIMATE_WINDOW_D = 3
TTL = {"forecast": timedelta(hours=3), "climate": timedelta(days=30), "history": timedelta(days=3650)}
HOURLY = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "wind_speed_10m"]


class WeatherError(RuntimeError):
    """Open-Meteo no respondió o devolvió algo inesperado."""


def _get(url: str, params: dict) -> dict:
    """Petición a Open-Meteo (aislada para simularla en los tests)."""
    try:
        res = httpx.get(url, params=params, timeout=10)
        res.raise_for_status()
        return res.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open-Meteo no disponible: %s", type(exc).__name__)
        raise WeatherError("No se pudo consultar el clima ahora mismo. Inténtalo más tarde.") from exc


def geocode(query: str) -> list[dict]:
    """Lugares que coinciden con el texto (en español)."""
    data = _get(GEOCODE_URL, {"name": query, "count": 6, "language": "es", "format": "json"})
    return [
        {"name": r["name"], "region": r.get("admin1") or "", "country": r.get("country") or "",
         "lat": round(r["latitude"], 5), "lon": round(r["longitude"], 5)}
        for r in data.get("results") or []
    ]  # fmt: skip


def _hours_window(hourly: dict, day: date, hour: int, hours: int) -> dict[str, list[float]]:
    """Valores de las horas de carrera [hour, hour + hours) del día `day`."""
    wanted = {f"{day.isoformat()}T{h:02d}:00" for h in range(hour, min(24, hour + hours))}
    idx = [i for i, t in enumerate(hourly.get("time", [])) if t in wanted]
    return {k: [hourly[k][i] for i in idx if hourly.get(k) and hourly[k][i] is not None] for k in hourly if k != "time"}


def _summary(values: dict[str, list[float]]) -> dict:
    def avg(key: str) -> float | None:
        v = values.get(key) or []
        return round(fmean(v), 1) if v else None

    rain = values.get("precipitation_probability") or []
    return {
        "temp_c": avg("temperature_2m"),
        "temp_max_c": round(max(values["temperature_2m"]), 1) if values.get("temperature_2m") else None,
        "dew_point_c": avg("dew_point_2m"),
        "humidity_pct": avg("relative_humidity_2m"),
        "wind_kmh": avg("wind_speed_10m"),
        "rain_prob_pct": round(max(rain)) if rain else None,
    }


def race_weather(lat: float, lon: float, day: date, hour: int, hours: int, today: date | None = None) -> dict:
    """
    Clima durante la carrera (media de las horas que dura).

    Returns:
        {"source": forecast|history|climate, "label": texto, temp_c, dew_point_c, humidity_pct, …}
    """
    today = today or date.today()
    hours = max(1, hours)
    base = {"latitude": lat, "longitude": lon, "timezone": "auto"}
    if day < today:
        data = _get(ARCHIVE_URL, {**base, "hourly": ",".join(HOURLY), "start_date": day, "end_date": day})
        out = _summary(_hours_window(data.get("hourly", {}), day, hour, hours))
        return {**out, "source": "history", "label": "Tiempo que hizo ese día"}
    if (day - today).days <= FORECAST_DAYS:
        hourly = ",".join([*HOURLY, "precipitation_probability"])
        data = _get(FORECAST_URL, {**base, "hourly": hourly, "start_date": day, "end_date": day})
        out = _summary(_hours_window(data.get("hourly", {}), day, hour, hours))
        return {**out, "source": "forecast", "label": "Pronóstico"}
    # Climatología: misma ventana de fechas en los últimos años.
    merged: dict[str, list[float]] = {}
    years = 0
    for back in range(1, CLIMATE_YEARS + 1):
        try:
            past = day.replace(year=day.year - back)
        except ValueError:  # 29 de febrero
            past = day.replace(year=day.year - back, day=28)
        if past >= today:
            continue
        start, end = past - timedelta(days=CLIMATE_WINDOW_D), past + timedelta(days=CLIMATE_WINDOW_D)
        data = _get(ARCHIVE_URL, {**base, "hourly": ",".join(HOURLY), "start_date": start, "end_date": end})
        for d in range((end - start).days + 1):
            for k, v in _hours_window(data.get("hourly", {}), start + timedelta(days=d), hour, hours).items():
                merged.setdefault(k, []).extend(v)
        years += 1
    out = _summary(merged)
    return {**out, "source": "climate", "label": f"Media de los últimos {years} años en esas fechas"}


def cached_weather(goal, hours: int, today: date | None = None) -> dict | None:
    """Clima del objetivo usando la caché si sigue vigente; None si no tiene lugar."""
    if goal.lat is None or goal.lon is None:
        return None
    hour = goal.start_time.hour if goal.start_time else 9
    key = f"{goal.lat:.3f},{goal.lon:.3f},{goal.race_date},{hour},{hours}"
    cache = goal.weather_cache or {}
    now = datetime.now(UTC)
    if cache.get("key") == key:
        fetched = datetime.fromisoformat(cache["fetched_at"])
        source = cache["data"].get("source", "forecast")
        # Al entrar en la ventana del pronóstico, la climatología deja de valer.
        in_forecast = 0 <= (goal.race_date - (today or date.today())).days <= FORECAST_DAYS
        if now - fetched < TTL.get(source, TTL["forecast"]) and not (source == "climate" and in_forecast):
            return cache["data"]
    data = race_weather(goal.lat, goal.lon, goal.race_date, hour, hours, today)
    goal.weather_cache = {"key": key, "fetched_at": now.isoformat(), "data": data}
    return data
