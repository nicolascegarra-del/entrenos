import io
from datetime import date, timedelta

import pytest
from fitparse import FitFile
from sqlmodel import Session

from app.core.security import create_token
from app.models import GarminCredential, PlannedBlock, PlannedSession, User, UserSettings
from app.services import garmin_workouts
from app.services.workout_export import WorkoutExportError, fit_workout, garmin_workout

TOMORROW = date.today() + timedelta(days=1)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _blocks() -> list[PlannedBlock]:
    return [
        PlannedBlock(session_id=0, position=0, kind="warmup", repeat=1, duration_s=900),
        PlannedBlock(
            session_id=0,
            position=1,
            kind="interval",
            repeat=6,
            distance_m=1000,
            target_metric="pace",
            target_min=230,
            target_max=240,
            recovery_duration_s=90,
        ),  # fmt: skip
        PlannedBlock(
            session_id=0,
            position=2,
            kind="steady",
            repeat=1,
            duration_s=600,
            target_metric="hr",
            target_min=140,
            target_max=150,
        ),  # fmt: skip
        PlannedBlock(session_id=0, position=3, kind="cooldown", repeat=1),  # hasta pulsar vuelta
    ]


def _planned(sport: str = "running") -> PlannedSession:
    return PlannedSession(user_id=1, day=TOMORROW, sport=sport, title="Series 6 × 1000", notes="Por la pista")


def test_formato_de_garmin():
    w = garmin_workout(_planned(), _blocks())
    assert w["sportType"]["sportTypeKey"] == "running" and w["workoutName"] == "Series 6 × 1000"
    assert "Por la pista" in w["description"] and w["estimatedDurationInSecs"] > 2400
    warm, group, steady, cool = w["workoutSegments"][0]["workoutSteps"]
    assert warm["stepType"]["stepTypeKey"] == "warmup" and warm["endConditionValue"] == 900
    assert group["type"] == "RepeatGroupDTO" and group["numberOfIterations"] == 6 and group["skipLastRestStep"]
    run, rest = group["workoutSteps"]
    assert run["endCondition"]["conditionTypeKey"] == "distance" and run["endConditionValue"] == 1000
    assert run["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    # Ritmo 3:50-4:00 /km → velocidad (m/s) de la más lenta a la más rápida.
    assert (run["targetValueOne"], run["targetValueTwo"]) == (round(1000 / 240, 3), round(1000 / 230, 3))
    assert rest["stepType"]["stepTypeKey"] == "recovery" and rest["endConditionValue"] == 90
    assert run["childStepId"] == rest["childStepId"] == group["childStepId"] == 1
    assert steady["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone" and steady["targetValueTwo"] == 150
    assert cool["endCondition"]["conditionTypeKey"] == "lap.button"
    orders = [warm["stepOrder"], group["stepOrder"], run["stepOrder"], rest["stepOrder"], steady["stepOrder"],
              cool["stepOrder"]]  # fmt: skip
    assert orders == sorted(set(orders))


def test_deporte_sin_soporte_o_sin_bloques():
    with pytest.raises(WorkoutExportError, match="carrera y de bici"):
        garmin_workout(_planned("strength_training"), _blocks())
    with pytest.raises(WorkoutExportError, match="bloques"):
        fit_workout(_planned(), [])


def test_fichero_fit_de_entreno():
    data = fit_workout(_planned(), _blocks())
    fit = FitFile(io.BytesIO(data))
    fit.parse()  # valida cabecera y CRC
    file_id = next(iter(fit.get_messages("file_id"))).get_values()
    assert file_id["type"] == "workout"
    workout = next(iter(fit.get_messages("workout"))).get_values()
    assert workout["sport"] == "running" and workout["wkt_name"] == "Series 6 × 1000"
    steps = [m.get_values() for m in fit.get_messages("workout_step")]
    assert workout["num_valid_steps"] == len(steps) == 6  # calent., serie, recup., repetir, bloque, calma
    serie, recup, repetir = steps[1], steps[2], steps[3]
    assert serie["duration_type"] == "distance" and serie["intensity"] == "active"
    assert recup["intensity"] == "rest"
    assert repetir["duration_type"] == "repeat_until_steps_cmplt"
    assert steps[0]["wkt_step_name"] == "Calentamiento" and steps[-1]["duration_type"] == "open"


class FakeGarmin:
    def __init__(self, fail: bool = False) -> None:
        self.uploaded: list[dict] = []
        self.scheduled: list[tuple[int, str]] = []
        self.deleted: list[int] = []
        self.fail = fail

    def upload_workout(self, workout: dict) -> dict:
        if self.fail:
            raise RuntimeError("500")
        self.uploaded.append(workout)
        return {"workoutId": 100 + len(self.uploaded)}

    def schedule_workout(self, workout_id: int, day: str) -> dict:
        self.scheduled.append((workout_id, day))
        return {"workoutScheduleId": 900 + len(self.scheduled)}

    def delete_workout(self, workout_id: int) -> None:
        self.deleted.append(workout_id)


def _save(session: Session, user: User, day: date = TOMORROW, sport: str = "running") -> PlannedSession:
    planned = PlannedSession(user_id=user.id, day=day, sport=sport, title="Rodaje")
    session.add(planned)
    session.flush()
    for b in _blocks():
        b.session_id = planned.id
        session.add(b)
    session.commit()
    return planned


def test_enviar_no_repite_y_reenvia_si_cambia(session: Session, user: User):
    planned = _save(session, user)
    garmin = FakeGarmin()
    assert garmin_workouts.send(session, planned, garmin) == "sent"
    assert (planned.garmin_workout_id, planned.garmin_schedule_id, planned.garmin_status) == (101, 901, "sent")
    assert garmin.scheduled == [(101, TOMORROW.isoformat())]
    assert garmin_workouts.send(session, planned, garmin) == "unchanged"
    planned.day = TOMORROW + timedelta(days=1)  # cambio de día: se borra la anterior y se sube otra
    session.add(planned)
    session.commit()
    assert garmin_workouts.send(session, planned, garmin) == "sent"
    assert garmin.deleted == [101] and planned.garmin_workout_id == 102
    garmin_workouts.remove(session, planned, garmin)
    assert garmin.deleted == [101, 102] and planned.garmin_status == "" and planned.garmin_workout_id is None


def test_error_de_garmin_queda_en_la_sesion(session: Session, user: User):
    planned = _save(session, user)
    assert garmin_workouts.send(session, planned, FakeGarmin(fail=True)) == "error"
    assert planned.garmin_status == "error" and "Garmin no aceptó" in planned.garmin_error
    strength = _save(session, user, sport="strength_training")
    assert garmin_workouts.send(session, strength, FakeGarmin()) == "error"
    assert "carrera y de bici" in strength.garmin_error


def test_proximos_7_dias(session: Session, user: User):
    today = date.today()
    inside = [_save(session, user, today), _save(session, user, today + timedelta(days=6))]
    _save(session, user, today + timedelta(days=7))  # fuera
    _save(session, user, today - timedelta(days=1))  # pasada
    _save(session, user, today + timedelta(days=2), sport="strength_training")  # no se envía
    garmin = FakeGarmin()
    assert garmin_workouts.send_upcoming(session, user.id, garmin) == {"sent": 2, "unchanged": 0, "error": 0}
    assert {d for _, d in garmin.scheduled} == {p.day.isoformat() for p in inside}
    assert garmin_workouts.send_upcoming(session, user.id, garmin)["unchanged"] == 2


def _plan_body(day: date = TOMORROW) -> dict:
    return {"day": day.isoformat(), "sport": "running", "title": "Series",
            "blocks": [{"kind": "warmup", "repeat": 1, "duration_s": 600},
                       {"kind": "interval", "repeat": 4, "distance_m": 1000, "target_metric": "pace",
                        "target_min": 235, "target_max": 245, "recovery_duration_s": 120}]}  # fmt: skip


def test_api_enviar_estado_y_cambios(client, user, session, monkeypatch):
    from app.api import workouts as api

    h = auth(user)
    plan = client.post("/api/v1/plans", json=_plan_body(), headers=h).json()
    # Sin Garmin conectado: 409 con un mensaje claro.
    no = client.post(f"/api/v1/plans/{plan['id']}/garmin", headers=h)
    assert no.status_code == 409 and "Conecta Garmin" in no.json()["error"]["message"]
    fake = FakeGarmin()
    fake.persist = lambda: None
    monkeypatch.setattr(api, "_client", lambda user_id: fake)
    res = client.post(f"/api/v1/plans/{plan['id']}/garmin", headers=h).json()
    assert res["garmin_status"] == "sent" and res["garmin_sent_at"]
    detail = client.get(f"/api/v1/plans/{plan['id']}", headers=h).json()
    assert detail["garmin_status"] == "sent" and detail["garmin_outdated"] is False
    edited = client.put(f"/api/v1/plans/{plan['id']}", json={**_plan_body(), "title": "Series cambiadas"}, headers=h)
    assert edited.json()["garmin_outdated"] is True
    assert client.post("/api/v1/workouts/send-upcoming", headers=h).json() == {"sent": 1, "unchanged": 0, "error": 0}
    assert client.delete(f"/api/v1/plans/{plan['id']}/garmin", headers=h).json()["garmin_status"] == ""


def test_api_borrar_sesion_la_quita_de_garmin(client, user, session, monkeypatch):
    from app.api import workouts as api

    queued: list = []
    monkeypatch.setattr(api, "queue_delete", lambda uid, wid: queued.append((uid, wid)))
    monkeypatch.setattr("app.api.plans.queue_delete", lambda uid, wid: queued.append((uid, wid)))
    planned = _save(session, user)
    planned.garmin_workout_id, planned.garmin_status = 555, "sent"
    session.add(planned)
    session.commit()
    assert client.delete(f"/api/v1/plans/{planned.id}", headers=auth(user)).status_code == 204
    assert queued == [(user.id, 555)]


def test_api_envio_automatico(client, user, session, monkeypatch):
    from app.tasks import workouts as tasks

    sent: list = []
    monkeypatch.setattr(tasks.send_workouts_task, "apply_async", lambda **kw: sent.append(kw["args"]))
    h = auth(user)
    assert client.get("/api/v1/workouts/settings", headers=h).json() == {
        "auto": False, "garmin_connected": False, "days": 7}  # fmt: skip
    session.add(GarminCredential(user_id=user.id, tokens_enc="x"))
    session.commit()
    on = client.put("/api/v1/workouts/settings", json={"auto": True}, headers=h).json()
    assert on["auto"] and on["garmin_connected"] and sent == [[user.id]]
    client.post("/api/v1/plans", json=_plan_body(), headers=h)  # guardar una sesión también lo lanza
    assert len(sent) == 2
    assert session.get(UserSettings, user.id).garmin_workouts_auto
    # La pasada cada 6 h solo coge a quien lo tiene activado y Garmin conectado.
    assert tasks.send_workouts_all_task() == 1


def test_api_descargar_fit(client, user, session):
    h = auth(user)
    plan = client.post("/api/v1/plans", json=_plan_body(), headers=h).json()
    res = client.get(f"/api/v1/plans/{plan['id']}/workout.fit", headers=h)
    assert res.status_code == 200 and res.headers["content-type"] == "application/vnd.ant.fit"
    assert res.headers["content-disposition"].endswith('-series.fit"') and res.content[8:12] == b".FIT"
    strength = client.post("/api/v1/plans", json={**_plan_body(), "sport": "strength_training"}, headers=h).json()
    assert client.get(f"/api/v1/plans/{strength['id']}/workout.fit", headers=h).status_code == 422
