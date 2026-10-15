from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import Activity, DailyMetric, PlannedSession, User
from app.services.progress import (
    Thresholds,
    activity_load,
    efficiency,
    fitness_series,
    form_label,
    records,
    weekly_volume,
)

T = Thresholds(lthr=160, hr_rest=50, hr_max=190)


def run(
    day: date, duration_s: float = 3600, avg_hr: float | None = 160, distance_m: float = 10000, **metrics
) -> Activity:
    return Activity(
        id=hash((day, duration_s, avg_hr)) % 100000,
        user_id=1,
        sport="running",
        start_time=datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8),
        timezone="+02:00",
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
        metrics=metrics,
    )


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def test_activity_load_cuando_una_hora_en_umbral_entonces_100():
    assert activity_load(run(date(2026, 10, 1)), T) == 100


def test_activity_load_cuando_media_hora_suave_entonces_menor():
    # IF = (105-50)/(160-50) = 0,5 → 0,5 h × 0,25 × 100 = 12,5
    assert activity_load(run(date(2026, 10, 1), duration_s=1800, avg_hr=105), T) == 12.5


def test_activity_load_cuando_sin_fc_entonces_estimada_por_duracion():
    assert activity_load(run(date(2026, 10, 1), avg_hr=None), T) == 50
    strength = run(date(2026, 10, 1), avg_hr=None)
    strength.sport = "strength_training"
    assert activity_load(strength, T) == 30


def test_fitness_series_cuando_carga_constante_entonces_ctl_y_atl_convergen():
    start = date(2026, 1, 1)
    loads = {start + timedelta(days=i): 100.0 for i in range(200)}
    series = fitness_series(loads, start + timedelta(days=190), start + timedelta(days=199))
    assert len(series) == 10
    last = series[-1]
    assert last["atl"] == pytest.approx(100, abs=0.5)
    assert last["ctl"] == pytest.approx(100, abs=1.5)
    assert abs(last["tsb"]) < 2


def test_fitness_series_cuando_bloque_duro_entonces_forma_negativa_y_luego_recupera():
    start = date(2026, 1, 1)
    loads = {start + timedelta(days=i): 50.0 for i in range(60)}
    loads |= {start + timedelta(days=60 + i): 150.0 for i in range(7)}
    series = {p["day"]: p for p in fitness_series(loads, start, start + timedelta(days=80))}
    after_block = series[start + timedelta(days=67)]
    rested = series[start + timedelta(days=80)]
    assert after_block["tsb"] < -20
    assert rested["tsb"] > after_block["tsb"]


def test_fitness_series_cuando_sin_cargas_entonces_vacio():
    assert fitness_series({}, date(2026, 1, 1), date(2026, 1, 10)) == []


@pytest.mark.parametrize(
    ("tsb", "label"), [(20, "Muy descansado"), (8, "Fresco"), (0, "Equilibrado"), (-20, "Cargado"), (-40, "Sobrecarga")]
)
def test_form_label_cuando_tsb_entonces_etiqueta(tsb, label):
    assert form_label(tsb) == label


def test_weekly_volume_cuando_semanas_vacias_entonces_incluidas_con_cero():
    monday = date(2026, 10, 5)
    a, b = run(monday + timedelta(days=2)), run(monday + timedelta(days=16), distance_m=5000)
    weeks = weekly_volume([a, b], {a.id: 80, b.id: 40}, monday, monday + timedelta(days=14))
    assert [w["week"] for w in weeks] == [monday, monday + timedelta(days=7), monday + timedelta(days=14)]
    assert [w["distance_m"] for w in weeks] == [10000, 0, 5000]
    assert weeks[0]["load"] == 80 and weeks[1]["count"] == 0


def test_efficiency_cuando_carrera_entonces_m_min_por_pulsacion():
    assert efficiency(run(date(2026, 10, 1), avg_hr=150)) == pytest.approx(166.67 / 150, abs=0.001)
    assert efficiency(run(date(2026, 10, 1), duration_s=300)) is None  # demasiado corta
    bike = run(date(2026, 10, 1))
    bike.sport = "cycling"
    assert efficiency(bike) is None


def test_records_cuando_varias_carreras_entonces_mejor_marca_e_historial():
    acts = [
        run(date(2026, 1, 1), best_5k=1500.0),
        run(date(2026, 2, 1), duration_s=3000, best_5k=1450.0, best_1k=270.0),
        run(date(2026, 3, 1), duration_s=3100, best_5k=1480.0),
    ]
    by_key = {r["key"]: r for r in records(acts)}
    five = by_key["best_5k"]
    assert five["best"]["time_s"] == 1450 and five["distance_m"] == 5000
    assert [h["time_s"] for h in five["history"]] == [1500, 1450]
    assert by_key["best_10k"]["best"] is None


# ─── API ────────────────────────────────────────────────────────────────────


@pytest.fixture
def history(session: Session, user: User) -> User:
    today = date.today()
    for i in range(0, 28, 2):
        day = today - timedelta(days=i)
        a = run(day, duration_s=3000 + i, avg_hr=150, vo2max=44.0 + (i == 0), best_5k=1500.0 - i)
        a.id, a.user_id = None, user.id
        session.add(a)
    session.add(DailyMetric(user_id=user.id, day=today, metrics={"resting_hr": 52}))
    session.add(PlannedSession(user_id=user.id, day=today, sport="running", title="Hoy", compliance_score=88))
    session.commit()
    return user


def test_api_fitness_cuando_historial_entonces_puntos_hasta_hoy(client, history):
    res = client.get("/api/v1/progress/fitness?days=30", headers=auth(history)).json()
    assert res["hr_rest"] == 52
    assert res["points"][-1]["day"] == date.today().isoformat()
    assert res["points"][-1]["ctl"] > 0


def test_api_weekly_cuando_4_semanas_entonces_4_puntos(client, history):
    res = client.get("/api/v1/progress/weekly?weeks=4", headers=auth(history)).json()
    assert len(res) == 4
    assert sum(w["count"] for w in res) > 0


def test_api_metric_cuando_vo2max_entonces_serie_y_desconocida_404(client, history):
    res = client.get("/api/v1/progress/metric/vo2max?days=30", headers=auth(history)).json()
    assert res[-1]["value"] == 45
    assert client.get("/api/v1/progress/metric/inventada", headers=auth(history)).status_code == 404


def test_api_records_y_efficiency(client, history):
    recs = {r["key"]: r for r in client.get("/api/v1/progress/records", headers=auth(history)).json()}
    assert recs["best_5k"]["best"]["time_s"] == 1474  # 1500 − 26 (la más antigua de la serie)
    eff = client.get("/api/v1/progress/efficiency?days=30", headers=auth(history)).json()
    assert len(eff) == 14 and all(p["value"] > 0 for p in eff)


def test_api_summary_cuando_semana_con_plan_entonces_resumen_completo(client, history):
    res = client.get("/api/v1/summary", headers=auth(history)).json()
    assert res["this_week"]["count"] >= 1
    assert res["resting_hr"] == 52 and res["vo2max"] == 45
    assert res["compliance_avg"] == 88
    assert res["form_label"] in {"Muy descansado", "Fresco", "Equilibrado", "Cargado", "Sobrecarga"}
    assert len(res["recent"]) == 5
    assert res["readiness"]["status"] in {"good", "watch", "alert"} and res["readiness"]["message"]


def test_api_summary_cuando_usuario_sin_datos_entonces_vacio_sin_error(client, user):
    res = client.get("/api/v1/summary", headers=auth(user)).json()
    assert res["fitness"] is None and res["this_week"]["count"] == 0 and res["recent"] == []
    assert res["readiness"]["status"] == "nodata" and res["readiness"]["acwr"] is None


def test_api_progress_cuando_sin_auth_entonces_401(client):
    assert client.get("/api/v1/progress/fitness").status_code == 401
