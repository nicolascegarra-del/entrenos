from datetime import date, time, timedelta

import pytest

from app.core.security import create_token
from app.models import RaceGoal, User
from app.services import race_day as rd
from app.services import weather as wx

TODAY = date(2026, 10, 22)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _gpx(eles: list[float], step_deg: float = 0.001, extra: str = "") -> str:
    pts = "".join(f'<trkpt lat="{37.6 + i * step_deg}" lon="-0.98"><ele>{e}</ele></trkpt>' for i, e in enumerate(eles))
    return f'<?xml version="1.0"?>{extra}<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{pts}</trkseg></trk></gpx>'


def _hourly(day: date, temp: float, dew: float, hours=range(24), rain: int | None = None) -> dict:
    h = {"time": [f"{day.isoformat()}T{x:02d}:00" for x in hours], "temperature_2m": [temp] * len(hours),
         "dew_point_2m": [dew] * len(hours), "relative_humidity_2m": [70] * len(hours),
         "wind_speed_10m": [12] * len(hours)}  # fmt: skip
    if rain is not None:
        h["precipitation_probability"] = [rain] * len(hours)
    return {"hourly": h}


# ─── Desnivel ────────────────────────────────────────────────────────────────


def test_pendiente_regla_de_daniels():
    assert rd.grade_factor(0) == 1 and rd.grade_factor(0.04) == pytest.approx(1.12)
    assert rd.grade_factor(-0.04) == pytest.approx(1 - 0.12 * 0.55)  # se recupera el 55 %
    assert rd.grade_factor(-0.2) == rd.grade_factor(-0.1)  # más empinado ya no ayuda
    # 10 km con 200 m de D+ (subidas y bajadas iguales): ~+2,7 %, como en la práctica
    assert rd.gain_factor(10000, 0) == 1 and rd.gain_factor(10000, 200) == pytest.approx(1.027)


def test_factores_por_km_en_subida_y_bajada():
    points = [[0, 0], [1000, 50], [2000, 0]]  # sube 5 % y baja 5 %
    up, down = rd.km_factors(points, 2000)
    assert up == pytest.approx(1.15) and down == pytest.approx(1 - 0.15 * 0.55)
    assert rd.km_factors([], 3500) == [1.0] * 4


# ─── Calor ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("temp", "dew", "low", "high"), [(10, 5, 0, 0), (20, 15, 1, 2), (30, 24, 6, 6.5)])
def test_calor_temperatura_mas_rocio(temp, dew, low, high):
    assert low <= rd.heat_slowdown_pct(temp, dew) <= high


def test_niveles_de_calor():
    assert rd.heat_level(0, 90)[0] == "good"
    assert rd.heat_level(1.5, 125)[0] == "watch"
    assert rd.heat_level(4, 150)[0] == "alert" and rd.heat_level(12, 185)[1].startswith("Calor extremo")
    assert rd.heat_slowdown_pct(38, 30) == 12.0


# ─── Ritmos y avituallamiento ────────────────────────────────────────────────


def test_plan_de_ritmos_reparte_el_tiempo_exacto():
    plan = rd.pacing_plan(3000, 10500, [1.0] * 10 + [1.0])
    assert len(plan) == 11 and plan[-1]["distance_m"] == 500 and plan[-1]["cum_s"] == 3000
    assert plan[0]["pace_s_km"] == pytest.approx(285.7, abs=0.1)
    hilly = rd.pacing_plan(600, 2000, [1.2, 0.9])
    assert hilly[0]["pace_s_km"] > hilly[1]["pace_s_km"] and hilly[-1]["cum_s"] == 600


def test_avituallamiento_segun_duracion_y_calor():
    assert rd.fueling(45 * 60, 12)["gels"] == 0
    half = rd.fueling(95 * 60, 18)
    assert half["gels"] == 1 and half["gel_times_min"] == [40] and half["fluid_ml_h"] == [500, 700]
    full = rd.fueling(3.5 * 3600, 27)
    assert full["gels"] == 7 and full["gel_times_min"][0] == 30 and full["sodium"] and full["carbs_g_h"] == [60, 90]


# ─── GPX ─────────────────────────────────────────────────────────────────────


def test_gpx_perfil_y_desnivel():
    c = rd.parse_gpx(_gpx([10, 20, 30, 40, 30, 20, 10] * 3), "maraton.gpx")
    assert 2000 < c["distance_m"] < 2400 and c["gain_m"] > 20 and c["name"] == "maraton.gpx"
    assert c["points"][0][0] == 0 and c["start"] == [37.6, -0.98] and len(c["track"]) == 21


@pytest.mark.parametrize(("text", "msg"), [
    ("no soy xml", "válido"),
    (_gpx([1, 2], extra='<!DOCTYPE x [<!ENTITY a "b">]>'), "DOCTYPE"),
    ('<gpx><trk><trkseg><trkpt lat="1" lon="1"/><trkpt lat="1.1" lon="1"/></trkseg></trk></gpx>', "altitudes"),
    ("<gpx></gpx>", "puntos"),
])  # fmt: skip
def test_gpx_no_valido(text, msg):
    with pytest.raises(rd.GpxError, match=msg):
        rd.parse_gpx(text)


# ─── Clima ───────────────────────────────────────────────────────────────────


def test_pronostico_dentro_de_15_dias(monkeypatch):
    calls = []
    day = TODAY + timedelta(days=3)

    def fake(url, params):
        calls.append(url)
        return _hourly(day, 18, 12, rain=40)

    monkeypatch.setattr(wx, "_get", fake)
    w = wx.race_weather(37.6, -0.98, day, 9, 2, TODAY)
    assert calls == [wx.FORECAST_URL] and w["source"] == "forecast" and w["temp_c"] == 18 and w["rain_prob_pct"] == 40


def test_climatologia_media_de_5_anos(monkeypatch):
    calls = []
    day = TODAY + timedelta(days=60)

    def fake(url, params):
        calls.append(params["start_date"])
        start = params["start_date"]
        return {"hourly": {k: v for d in range(7) for k, v in []} or _merge(start)}

    def _merge(start):
        out = {"time": [], "temperature_2m": [], "dew_point_2m": [], "relative_humidity_2m": [], "wind_speed_10m": []}
        for d in range(7):
            h = _hourly(start + timedelta(days=d), 10 + d, 5)["hourly"]
            for k in out:
                out[k] += h[k]
        return out

    monkeypatch.setattr(wx, "_get", fake)
    w = wx.race_weather(37.6, -0.98, day, 9, 3, TODAY)
    assert len(calls) == 5 and w["source"] == "climate" and w["temp_c"] == 13 and "5 años" in w["label"]


def test_carrera_pasada_usa_el_historico(monkeypatch):
    day = TODAY - timedelta(days=10)
    monkeypatch.setattr(wx, "_get", lambda url, params: _hourly(day, 22, 15) if url == wx.ARCHIVE_URL else {})
    assert wx.race_weather(37.6, -0.98, day, 9, 1, TODAY)["source"] == "history"


def test_cache_del_clima(monkeypatch, user):
    calls = []
    goal = RaceGoal(user_id=user.id, name="X", race_date=TODAY + timedelta(days=2), distance_m=10000,
                    lat=37.6, lon=-0.98, start_time=time(9, 0))  # fmt: skip
    monkeypatch.setattr(wx, "_get", lambda url, params: calls.append(1) or _hourly(goal.race_date, 15, 8))
    wx.cached_weather(goal, 1, TODAY)
    wx.cached_weather(goal, 1, TODAY)
    assert len(calls) == 1
    goal.start_time = time(18, 0)  # cambia la clave → nueva consulta
    wx.cached_weather(goal, 1, TODAY)
    assert len(calls) == 2
    assert wx.cached_weather(RaceGoal(user_id=1, name="Y", race_date=TODAY, distance_m=1), 1) is None


def test_geocode(monkeypatch):
    monkeypatch.setattr(wx, "_get", lambda url, params: {"results": [
        {"name": "Cartagena", "admin1": "Región de Murcia", "country": "España", "latitude": 37.60197,
         "longitude": -0.98397}]})  # fmt: skip
    assert wx.geocode("Cartag") == [{"name": "Cartagena", "region": "Región de Murcia", "country": "España",
                                     "lat": 37.60197, "lon": -0.98397}]  # fmt: skip


# ─── API ─────────────────────────────────────────────────────────────────────


def test_api_dia_de_carrera(client, user, monkeypatch):
    race = date.today() + timedelta(days=5)
    monkeypatch.setattr(wx, "_get", lambda url, params: _hourly(race, 24, 18))
    body = {"name": "10K", "race_date": race.isoformat(), "distance_m": 10000, "target_time_s": 3000,
            "start_time": "09:00", "location_name": "Cartagena", "lat": 37.6, "lon": -0.98}  # fmt: skip
    goal = client.post("/api/v1/goals", json=body, headers=auth(user)).json()
    assert goal["start_time"] == "09:00:00" and goal["has_course"] is False
    gpx = {"gpx": _gpx([0, 10, 20, 30, 40, 50, 40, 30, 20, 10, 0] * 8, step_deg=0.001), "name": "10k.gpx"}
    res = client.put(f"/api/v1/goals/{goal['id']}/course", json=gpx, headers=auth(user))
    assert res.status_code == 200 and res.json()["has_course"] is True
    plan = client.get(f"/api/v1/goals/{goal['id']}/race-day", headers=auth(user)).json()
    assert plan["available"] and plan["base_source"] == "target" and plan["weather"]["source"] == "forecast"
    assert plan["heat"]["pct"] > 1 and plan["elevation_pct"] > 0 and plan["adjusted_s"] > 3000
    assert len(plan["pacing"]) == 10 and plan["pacing_target"][-1]["cum_s"] == 3000
    assert plan["course"]["source"] == "gpx" and plan["fueling"]["gels"] == 0
    assert client.delete(f"/api/v1/goals/{goal['id']}/course", headers=auth(user)).status_code == 204


def test_api_sin_lugar_ni_previsión(client, user):
    body = {"name": "Sin datos", "race_date": (date.today() + timedelta(days=40)).isoformat(), "distance_m": 5000}
    goal = client.post("/api/v1/goals", json=body, headers=auth(user)).json()
    plan = client.get(f"/api/v1/goals/{goal['id']}/race-day", headers=auth(user)).json()
    assert plan == {"available": False, "reason": "Necesitamos una previsión o un tiempo objetivo para planificar."}


def test_api_clima_caido_no_rompe(client, user, monkeypatch):
    def down(url, params):
        raise wx.WeatherError("No se pudo consultar el clima ahora mismo. Inténtalo más tarde.")

    monkeypatch.setattr(wx, "_get", down)
    body = {"name": "D+", "race_date": (date.today() + timedelta(days=3)).isoformat(), "distance_m": 21097,
            "target_time_s": 6000, "lat": 37.6, "lon": -0.98, "elevation_gain_m": 300}  # fmt: skip
    goal = client.post("/api/v1/goals", json=body, headers=auth(user)).json()
    plan = client.get(f"/api/v1/goals/{goal['id']}/race-day", headers=auth(user)).json()
    assert plan["weather"] is None and "clima" in plan["weather_error"] and plan["course"]["source"] == "gain"
    assert client.get("/api/v1/goals/geocode?q=Murcia", headers=auth(user)).status_code == 503


def test_api_gpx_malo(client, user):
    body = {"name": "G", "race_date": (date.today() + timedelta(days=3)).isoformat(), "distance_m": 5000}
    goal = client.post("/api/v1/goals", json=body, headers=auth(user)).json()
    res = client.put(f"/api/v1/goals/{goal['id']}/course", json={"gpx": "x" * 30}, headers=auth(user))
    assert res.status_code == 422
