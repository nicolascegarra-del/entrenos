from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token, hash_password
from app.models import Activity, DailyMetric, PlannedSession, StrengthSet, User
from app.services.progress import Thresholds, activity_load
from app.services.strength import clean_exercise, estimated_1rm, exercise_key, summarize_sets


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def manual_body(day: str = "2026-10-14", **overrides) -> dict:
    return {
        "sport": "strength_training",
        "name": "Pierna",
        "start_time": f"{day}T19:30:00+02:00",
        "duration_s": 3600,
    } | overrides


@pytest.mark.parametrize(
    ("weight", "reps", "expected"),
    [(100, 1, 100), (100, 5, 116.7), (80, 10, 106.7), (60, 15, None), (None, 5, None), (100, 0, None)],
)
def test_estimated_1rm_cuando_peso_y_reps_entonces_epley(weight, reps, expected):
    assert estimated_1rm(weight, reps) == expected


def test_exercise_key_cuando_tildes_y_mayusculas_entonces_misma_clave():
    assert exercise_key("  Press   Banca ") == exercise_key("press banca") == "press banca"
    assert exercise_key("Remo con barra") == exercise_key("remo con BARRA")
    assert exercise_key("Elevación lateral") == "elevacion lateral"
    assert clean_exercise("  sentadilla   trasera ") == "Sentadilla trasera"


def test_summarize_sets_cuando_varias_series_entonces_volumen_mejor_peso_y_1rm():
    sets = [
        StrengthSet(activity_id=1, position=0, exercise="Sentadilla", reps=8, weight_kg=80),
        StrengthSet(activity_id=1, position=1, exercise="sentadilla", reps=5, weight_kg=100),
        StrengthSet(activity_id=1, position=2, exercise="Plancha", duration_s=60),
    ]
    by_key = {s["key"]: s for s in summarize_sets(sets)}
    squat = by_key["sentadilla"]
    assert squat["sets"] == 2 and squat["reps"] == 13
    assert squat["volume_kg"] == 8 * 80 + 5 * 100
    assert squat["top_weight_kg"] == 100 and squat["best_e1rm_kg"] == 116.7
    assert by_key["plancha"]["best_e1rm_kg"] is None


def test_activity_load_cuando_sin_fc_con_rpe_entonces_usa_rpe():
    gym = Activity(user_id=1, sport="strength_training", start_time=datetime.now(UTC), duration_s=3600)
    t = Thresholds(lthr=160, hr_rest=50, hr_max=190)
    assert activity_load(gym, t) == 30  # sin RPE: estimación por deporte
    assert activity_load(gym, t, rpe=7) == pytest.approx(87.1, abs=0.1)  # (7/7,5)² × 100
    assert activity_load(gym, t, rpe=10) == pytest.approx(177.8, abs=0.1)


def test_create_manual_activity_cuando_zona_horaria_entonces_utc_y_offset(client, session, user):
    res = client.post("/api/v1/activities", json=manual_body(), headers=auth(user))
    assert res.status_code == 201
    data = res.json()
    assert data["start_time"].startswith("2026-10-14T17:30:00") and data["timezone"] == "+02:00"
    detail = client.get(f"/api/v1/activities/{data['id']}", headers=auth(user)).json()
    assert detail["manual"] is True


def test_create_manual_activity_cuando_sin_zona_horaria_entonces_422(client, user):
    res = client.post("/api/v1/activities", json=manual_body() | {"start_time": "2026-10-14T19:30:00"},
                      headers=auth(user))  # fmt: skip
    assert res.status_code == 422
    assert "zona horaria" in res.json()["error"]["message"]


def test_create_manual_activity_cuando_hay_plan_ese_dia_entonces_lo_empareja(client, session, user):
    session.add(PlannedSession(user_id=user.id, day=date(2026, 10, 14), sport="strength_training", title="Gym"))
    session.commit()
    activity = client.post("/api/v1/activities", json=manual_body(), headers=auth(user)).json()
    plans = client.get("/api/v1/plans?date_from=2026-10-14&date_to=2026-10-14", headers=auth(user)).json()
    assert plans[0]["activity_id"] == activity["id"]


def test_delete_activity_cuando_manual_entonces_204_y_de_garmin_409(client, session, user):
    manual = client.post("/api/v1/activities", json=manual_body(), headers=auth(user)).json()
    garmin = Activity(user_id=user.id, garmin_activity_id=123, sport="running", start_time=datetime.now(UTC),
                      duration_s=600)  # fmt: skip
    session.add(garmin)
    session.commit()
    assert client.delete(f"/api/v1/activities/{manual['id']}", headers=auth(user)).status_code == 204
    res = client.delete(f"/api/v1/activities/{garmin.id}", headers=auth(user))
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONFLICT"


def test_put_sets_cuando_series_entonces_reemplaza_y_resume(client, user):
    activity = client.post("/api/v1/activities", json=manual_body(), headers=auth(user)).json()
    url = f"/api/v1/activities/{activity['id']}/sets"
    client.put(url, json=[{"exercise": "Curl", "reps": 10, "weight_kg": 12}], headers=auth(user))
    res = client.put(
        url,
        json=[
            {"exercise": "  press banca ", "reps": 5, "weight_kg": 80},
            {"exercise": "Press banca", "reps": 3, "weight_kg": 90},
        ],
        headers=auth(user),
    ).json()
    assert [s["exercise"] for s in res["sets"]] == ["Press banca", "Press banca"]
    assert res["sets"][0]["e1rm_kg"] == pytest.approx(93.3, abs=0.1)
    assert len(res["summary"]) == 1 and res["summary"][0]["volume_kg"] == 670
    assert client.get(url, headers=auth(user)).json()["sets"][1]["weight_kg"] == 90


def test_put_sets_cuando_actividad_ajena_entonces_404(client, session, user):
    activity = client.post("/api/v1/activities", json=manual_body(), headers=auth(user)).json()
    other = User(email="otra@example.com", password_hash=hash_password("x" * 12))
    session.add(other)
    session.commit()
    res = client.put(f"/api/v1/activities/{activity['id']}/sets", json=[], headers=auth(other))
    assert res.status_code == 404
    assert client.get(f"/api/v1/activities/{activity['id']}/feedback", headers=auth(other)).status_code == 404


def test_feedback_cuando_se_guarda_entonces_devuelve_con_contexto_del_dia(client, session, user):
    session.add(
        DailyMetric(user_id=user.id, day=date(2026, 10, 14), metrics={"sleep_seconds": 25200, "resting_hr": 53})
    )
    session.commit()
    activity = client.post("/api/v1/activities", json=manual_body(), headers=auth(user)).json()
    url = f"/api/v1/activities/{activity['id']}/feedback"
    empty = client.get(url, headers=auth(user)).json()
    assert empty["rpe"] is None and empty["context"] == {"sleep_seconds": 25200, "resting_hr": 53}
    saved = client.put(url, json={"rpe": 8, "feeling": 4, "notes": "  Buenas piernas "}, headers=auth(user)).json()
    assert saved["rpe"] == 8 and saved["feeling"] == 4 and saved["notes"] == "Buenas piernas"


def test_feedback_cuando_rpe_fuera_de_rango_entonces_422(client, user):
    activity = client.post("/api/v1/activities", json=manual_body(), headers=auth(user)).json()
    res = client.put(f"/api/v1/activities/{activity['id']}/feedback", json={"rpe": 11}, headers=auth(user))
    assert res.status_code == 422


def test_strength_exercises_cuando_varias_sesiones_entonces_historial_y_mejora(client, user):
    for i, weight in enumerate((80, 85, 90)):
        day = (date(2026, 9, 1) + timedelta(days=7 * i)).isoformat()
        activity = client.post("/api/v1/activities", json=manual_body(day=day), headers=auth(user)).json()
        client.put(f"/api/v1/activities/{activity['id']}/sets",
                   json=[{"exercise": "Sentadilla", "reps": 5, "weight_kg": weight}], headers=auth(user))  # fmt: skip
    overview = client.get("/api/v1/strength/exercises", headers=auth(user)).json()
    assert overview[0]["exercise"] == "Sentadilla" and overview[0]["sessions"] == 3
    assert overview[0]["e1rm_change_kg"] == pytest.approx(11.7, abs=0.1)
    history = client.get("/api/v1/strength/exercises/SENTADILLA", headers=auth(user)).json()
    assert [h["top_weight_kg"] for h in history] == [80, 85, 90]
    assert client.get("/api/v1/strength/exercises/inexistente", headers=auth(user)).status_code == 404


def test_rpe_cuando_registrado_entonces_cuenta_en_la_carga(client, session: Session, user):
    activity = client.post(
        "/api/v1/activities", json=manual_body(day=date.today().isoformat()), headers=auth(user)
    ).json()
    before = client.get("/api/v1/progress/fitness?days=7", headers=auth(user)).json()["points"][-1]
    client.put(f"/api/v1/activities/{activity['id']}/feedback", json={"rpe": 9}, headers=auth(user))
    after = client.get("/api/v1/progress/fitness?days=7", headers=auth(user)).json()["points"][-1]
    assert after["load"] > before["load"]
