from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import Activity, RaceGoal, User
from app.services import race_forecast as rf
from app.services import race_models as rm

TODAY = date(2026, 10, 14)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def data(**overrides) -> rf.TrainingData:
    base = {
        "efforts": {"best_5k": (5000.0, 1500.0, TODAY), "best_10k": (10000.0, 3150.0, TODAY)},
        "vo2max": 44.0,
        "km_per_week": 45.0,
        "avg_pace_s_km": 330.0,
        "longest_run_m": 25000.0,
    }
    return rf.TrainingData(**(base | overrides))


# ─── Modelos ────────────────────────────────────────────────────────────────


def test_personal_exponent_cuando_marcas_siguen_1_08_entonces_lo_recupera():
    efforts = [(d, 1200 * (d / 5000) ** 1.08) for d in (3000, 5000, 10000, 21097.5)]
    exponent, personal = rm.personal_exponent(efforts)
    assert personal is True
    assert exponent == pytest.approx(1.08, abs=0.001)


def test_personal_exponent_cuando_distancias_poco_separadas_entonces_1_06_por_defecto():
    assert rm.personal_exponent([(1000, 240), (1609, 400)]) == (1.06, False)
    assert rm.personal_exponent([(5000, 1200)]) == (1.06, False)


def test_personal_exponent_cuando_datos_extremos_entonces_acotado():
    exponent, _ = rm.personal_exponent([(1000, 200), (10000, 4000)])  # exponente real ≈ 1,30
    assert exponent == 1.15


def test_time_for_vdot_cuando_inversa_entonces_devuelve_la_marca():
    v = rm.vdot(10000, 2700)
    assert rm.time_for_vdot(10000, v) == pytest.approx(2700, abs=1)
    assert rm.time_for_vdot(42195, rm.vdot(5000, 1200)) > 3 * 3600  # 5k en 20' ≈ maratón de ~3h10


def test_daniels_paces_cuando_vdot_50_entonces_orden_de_intensidades():
    paces = rm.daniels_paces(50)
    assert paces["repetition"][0] < paces["interval"][0] < paces["threshold"][0] < paces["marathon"][0]
    assert paces["marathon"][0] < paces["easy"][0] < paces["easy"][1]
    assert paces["threshold"][0] == pytest.approx(253, abs=8)  # ≈ 4:15 /km en las tablas de Daniels


def test_tanda_cuando_60_km_semana_a_5_min_entonces_ritmo_del_articulo():
    # Pm = 17,1 + 140·e^(−0,0053·60) + 0,55·300 ≈ 284 s/km → ~3:19:50
    assert rm.tanda_marathon_s(60, 300) == pytest.approx(284.0 * 42.195, abs=15)


# ─── Combinación, rango y avisos ────────────────────────────────────────────


def test_forecast_cuando_10k_entonces_riegel_y_vdot_a_partes_iguales_y_rango():
    f = rf.forecast(10000, data())
    assert {m.key for m in f.models} == {"riegel", "vdot"}
    assert all(m.weight == 0.5 for m in f.models)
    assert f.optimistic_s < f.probable_s < f.conservative_s
    assert f.exponent_personal is False  # 5k y 10k están a menos de ×3
    assert any("entrenamiento" in w for w in f.warnings)


def test_forecast_cuando_maraton_entonces_incluye_tanda_con_mas_peso():
    f = rf.forecast(42195, data(longest_run_m=32000))
    weights = {m.key: m.weight for m in f.models}
    assert weights == {"riegel": 0.3, "vdot": 0.3, "tanda": 0.4}


def test_forecast_cuando_volumen_justo_para_tanda_entonces_incluye_con_aviso():
    f = rf.forecast(42195, data(km_per_week=35, longest_run_m=32000))
    assert "tanda" in {m.key for m in f.models}
    assert any("con cautela" in w for w in f.warnings)


def test_forecast_cuando_muy_poco_volumen_entonces_excluye_tanda():
    # Regresión con datos reales: con 15 km/semana Tanda prevé una maratón mucho más rápida que el resto.
    f = rf.forecast(42195, data(km_per_week=15, longest_run_m=32000))
    assert {m.key for m in f.models} == {"riegel", "vdot"}
    assert all(m.weight == 0.5 for m in f.models)
    assert any("no se aplica" in w for w in f.warnings)


def test_forecast_cuando_distancia_mayor_que_tirada_larga_entonces_rango_mas_amplio():
    normal = rf.forecast(21097.5, data(longest_run_m=22000))
    corto = rf.forecast(21097.5, data(longest_run_m=12000))
    assert (corto.conservative_s - corto.probable_s) > (normal.conservative_s - normal.probable_s)
    assert any("tirada más larga" in w for w in corto.warnings)


def test_forecast_cuando_ultra_entonces_aviso_de_extrapolacion():
    f = rf.forecast(50000, data(longest_run_m=50000))
    assert any("mayor que maratón" in w for w in f.warnings)


def test_forecast_cuando_solo_vo2max_entonces_aviso_poco_fiable():
    f = rf.forecast(10000, data(efforts={}))
    assert f.vdot_source == "vo2max" and len(f.models) == 1
    assert any("VO2max del reloj" in w for w in f.warnings)


def test_forecast_cuando_sin_datos_entonces_sin_prevision():
    f = rf.forecast(10000, data(efforts={}, vo2max=None))
    assert f.probable_s is None and f.warnings


def test_forecast_cuando_calibrado_entonces_aplica_factor():
    base = rf.forecast(10000, data())
    calibrated = rf.forecast(10000, data(), calibration=0.97)
    assert calibrated.probable_s == pytest.approx(base.probable_s * 0.97, abs=1)
    assert calibrated.calibration_factor == 0.97


@pytest.mark.parametrize(
    ("results", "expected"),
    [([], None), ([(2900, 3000)], pytest.approx(0.9667, abs=0.001)), ([(2000, 3000)], 0.9), ([(4000, 3000)], 1.1)],
)
def test_calibration_factor_cuando_carreras_entonces_mediana_acotada(results, expected):
    assert rf.calibration_factor(results) == expected


def test_projected_tsb_cuando_afinamiento_entonces_llega_mas_fresco():
    loads = {TODAY - timedelta(days=i): 60.0 for i in range(90)}
    tsb = rf.projected_tsb(loads, TODAY, TODAY + timedelta(days=21))
    assert tsb is not None and tsb > 0  # la carga baja al 50 % los últimos 10 días
    assert rf.projected_tsb(loads, TODAY, TODAY) is None


def test_checklist_cuando_preparacion_incompleta_entonces_pendientes():
    items = {i["key"]: i for i in rf.checklist(42195, data(longest_run_m=21000, km_per_week=30), -12, 10, 50, 45)}
    assert items["long_run"]["status"] == "pending" and items["weekly_volume"]["status"] == "pending"
    assert items["taper"]["status"] == "warn"
    assert items["vdot_gap"]["status"] == "warn"  # 5 puntos de VDOT en 10 semanas es mucho
    ok = {i["key"]: i["status"] for i in rf.checklist(10000, data(), 10, 6, 40, 45)}
    assert ok == {"long_run": "ok", "weekly_volume": "ok", "taper": "ok", "vdot_gap": "ok"}


# ─── API ────────────────────────────────────────────────────────────────────


def _run(user_id: int, day: date, distance: float, seconds: float, **metrics) -> Activity:
    return Activity(
        user_id=user_id, sport="running", timezone="+02:00", distance_m=distance, duration_s=seconds,
        moving_duration_s=seconds, avg_hr=150,
        start_time=datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8), metrics=metrics,
    )  # fmt: skip


@pytest.fixture
def runner(session: Session, user: User) -> User:
    today = date.today()
    for i in range(0, 70, 3):
        session.add(_run(user.id, today - timedelta(days=i), 10000, 3300, best_5k=1560.0, best_10k=3300.0))
    session.commit()
    return user


def goal_body(**overrides) -> dict:
    return {"name": "10K de la ciudad", "race_date": (date.today() + timedelta(days=42)).isoformat(),
            "distance_m": 10000, "target_time_s": 3000} | overrides  # fmt: skip


def test_api_goal_cuando_se_crea_entonces_lista_con_prevision(client, runner):
    created = client.post("/api/v1/goals", json=goal_body(), headers=auth(runner))
    assert created.status_code == 201
    goals = client.get("/api/v1/goals", headers=auth(runner)).json()
    assert goals[0]["name"] == "10K de la ciudad" and goals[0]["days_left"] == 42
    assert 2800 < goals[0]["probable_s"] < 3600


def test_api_report_cuando_objetivo_entonces_prevision_evolucion_checklist_y_ritmos(client, runner):
    goal = client.post("/api/v1/goals", json=goal_body(), headers=auth(runner)).json()
    report = client.get(f"/api/v1/goals/{goal['id']}/report", headers=auth(runner)).json()
    f = report["forecast"]
    assert f["optimistic_s"] < f["probable_s"] < f["conservative_s"]
    assert report["gap_s"] == f["probable_s"] - 3000
    assert report["vdot_needed"] > f["vdot_current"]
    assert len(report["evolution"]) >= 8
    assert {i["key"] for i in report["checklist"]} >= {"long_run", "weekly_volume", "taper", "vdot_gap"}
    assert set(report["paces"]) == {"easy", "marathon", "threshold", "interval", "repetition"}


def test_api_result_cuando_se_marca_carrera_entonces_calibra_el_siguiente_objetivo(client, session, runner):
    race_day = date.today() - timedelta(days=1)
    race = _run(runner.id, race_day, 10050, 3000)  # carrera real más rápida de lo que predecían los entrenos
    session.add(race)
    session.commit()
    past = client.post("/api/v1/goals", json=goal_body(name="Pasada", race_date=race_day.isoformat()),
                       headers=auth(runner)).json()  # fmt: skip
    candidates = client.get(f"/api/v1/goals/{past['id']}/candidates", headers=auth(runner)).json()
    assert [c["id"] for c in candidates] == [race.id]
    result = client.put(f"/api/v1/goals/{past['id']}/result", json={"activity_id": race.id},
                        headers=auth(runner)).json()  # fmt: skip
    assert result["result_time_s"] == pytest.approx(3000 * (10000 / 10050) ** 1.06, abs=1)
    assert result["predicted_time_s"] > result["result_time_s"]

    future = client.post("/api/v1/goals", json=goal_body(), headers=auth(runner)).json()
    report = client.get(f"/api/v1/goals/{future['id']}/report", headers=auth(runner)).json()
    assert report["forecast"]["calibration_factor"] < 1


def test_api_result_cuando_actividad_ajena_entonces_400(client, session, runner):
    goal = client.post("/api/v1/goals", json=goal_body(), headers=auth(runner)).json()
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    foreign = _run(other.id, date.today(), 10000, 3000)
    session.add(foreign)
    session.commit()
    res = client.put(f"/api/v1/goals/{goal['id']}/result", json={"activity_id": foreign.id}, headers=auth(runner))
    assert res.status_code == 400


def test_api_goal_cuando_es_de_otro_usuario_entonces_404(client, session, runner):
    goal = client.post("/api/v1/goals", json=goal_body(), headers=auth(runner)).json()
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    for method, path in (("get", "/report"), ("delete", ""), ("get", "/candidates")):
        assert getattr(client, method)(f"/api/v1/goals/{goal['id']}{path}", headers=auth(other)).status_code == 404


def test_api_update_y_delete_goal(client, session, runner):
    goal = client.post("/api/v1/goals", json=goal_body(), headers=auth(runner)).json()
    updated = client.put(f"/api/v1/goals/{goal['id']}", json=goal_body(distance_m=21097.5, target_time_s=None),
                         headers=auth(runner)).json()  # fmt: skip
    assert updated["distance_m"] == 21097.5 and updated["target_time_s"] is None
    assert client.delete(f"/api/v1/goals/{goal['id']}", headers=auth(runner)).status_code == 204
    assert session.get(RaceGoal, goal["id"]) is None


def test_api_training_paces_cuando_hay_marcas_entonces_ritmos_daniels(client, runner, user):
    res = client.get("/api/v1/training-paces", headers=auth(runner)).json()
    assert res["source"] == "marca" and res["vdot"] > 25
    assert res["paces"]["easy"][0] < res["paces"]["easy"][1]
