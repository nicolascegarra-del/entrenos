import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import (
    CoachSettings,
    PerformanceTest,
    PlannedBlock,
    PlannedSession,
    PlanProposal,
    User,
    UserProfile,
    WeeklyCheckin,
    WeightLog,
)
from app.services import ai_tools, coach, weekly_review

TOMORROW = date.today() + timedelta(days=1)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _tool(session: Session, user: User, name: str, args: dict) -> dict:
    _, text = ai_tools.execute(session, user.id, name, args)
    return json.loads(text)


def test_la_ia_guarda_corrige_y_olvida(session: Session, user: User):
    saved = _tool(session, user, "guardar_en_memoria", {"categoria": "disponibilidad",
                                                        "dato": "Entrena de lunes a viernes a las 7:00"})  # fmt: skip
    effect = saved["efecto"]
    assert effect["tipo"] == "memoria" and effect["accion"] == "guardado" and effect["categoria"] == "disponibilidad"
    fixed = _tool(session, user, "guardar_en_memoria", {"categoria": "disponibilidad", "dato": "Entrena a las 6:30",
                                                        "reemplaza_id": effect["id"]})  # fmt: skip
    assert fixed["efecto"]["accion"] == "corregido"
    assert [m.content for m in coach.memories(session, user.id)] == ["Entrena a las 6:30"]
    ficha = _tool(session, user, "memoria_del_atleta", {})
    assert ficha["datos"][0]["id"] == effect["id"] and ficha["consentimiento_salud"] is False
    _tool(session, user, "olvidar_dato", {"id": effect["id"]})
    assert coach.memories(session, user.id) == []
    bad = _tool(session, user, "guardar_en_memoria", {"categoria": "inventada", "dato": "x"})
    assert "Categoría desconocida" in bad["error"]


def test_la_entrevista_completa_el_perfil_y_los_umbrales(session: Session, user: User):
    faltan = _tool(session, user, "memoria_del_atleta", {})["perfil"]["faltan"]
    assert {"fecha de nacimiento", "sexo", "peso", "altura"} <= set(faltan)
    saved = _tool(session, user, "actualizar_perfil", {"fecha_nacimiento": "1985-04-12", "sexo": "male",
                                                       "peso_kg": 71.5, "altura_cm": 178})  # fmt: skip
    assert saved["efecto"] == {"tipo": "perfil", "cambios": {"Nacimiento": "12/04/1985", "Sexo": "hombre",
                                                             "Peso": "71.5 kg", "Altura": "178 cm"}}  # fmt: skip
    profile = session.get(UserProfile, user.id)
    assert (profile.birth_date, profile.weight_kg, profile.source) == (date(1985, 4, 12), 71.5, "manual")
    assert session.exec(select(WeightLog).where(WeightLog.user_id == user.id)).first().weight_kg == 71.5

    tested = _tool(session, user, "guardar_umbrales", {"fc_max": 188, "ritmo_umbral": "4:35"})
    assert tested["efecto"]["tipo"] == "umbrales"
    assert tested["efecto"]["cambios"] == {"FC máx.": "188 ppm", "Ritmo umbral": "4:35 /km"}
    test = session.get(PerformanceTest, tested["efecto"]["id"])
    assert test.results == {"hr_max": 188, "threshold_pace_s_km": 275} and test.status == "confirmed"
    perfil = _tool(session, user, "memoria_del_atleta", {})["perfil"]
    assert perfil["faltan"] == [] and perfil["datos"]["fc_max"] == {"valor": 188, "origen": "test", "detalle": None}
    assert perfil["datos"]["ritmo_umbral"]["valor"] == "4:35 /km"


def test_la_entrevista_propone_lo_detectado_en_reloj_y_entrenos(session: Session, user: User):
    from app.services.file_import import ImportedActivity, save_imported
    from app.services.profile import apply_garmin_profile

    empty = _tool(session, user, "memoria_del_atleta", {})["perfil"]
    assert empty["actividades"] == 0 and empty["detectados"] == [] and "FC máxima" in empty["faltan"]
    apply_garmin_profile(session, user.id, {"userData": {"birthDate": "1985-04-12", "gender": "MALE",
                                                         "weight": 71500, "height": 178}})  # fmt: skip
    n = 1200
    run = ImportedActivity(
        sport="running",
        start_time=datetime(2026, 5, 12, 8, tzinfo=UTC),
        duration_s=float(n),
        distance_m=n * 3.5,
        avg_hr=160,
        max_hr=188,
        name="Series 6x1000",
        metrics={"lthr": 171, "vo2max": 52.0},
        streams={"time": [float(i) for i in range(n)], "distance": [i * 3.5 for i in range(n)]},
    )
    save_imported(session, user.id, run, "fit")
    perfil = _tool(session, user, "memoria_del_atleta", {})["perfil"]
    datos = perfil["datos"]
    assert datos["sexo"] == {"valor": "male", "origen": "garmin", "detalle": None}
    assert datos["fc_max"]["origen"] == "actividades" and datos["fc_max"]["valor"] == 188
    assert "12/05/2026" in datos["fc_max"]["detalle"] and "Series 6x1000" in datos["fc_max"]["detalle"]
    assert datos["fc_umbral"] == {"valor": 171, "origen": "reloj", "detalle": "12/05/2026"}
    assert datos["vo2max"]["valor"] == 52.0
    assert {"sexo", "fc_max", "fc_umbral", "vo2max"} <= set(perfil["detectados"])
    assert perfil["faltan"] == [] and perfil["actividades"] == 1 and perfil["sincronizando"] is False


@pytest.mark.parametrize(
    ("name", "args", "error"),
    [
        ("actualizar_perfil", {}, "ningún dato"),
        ("actualizar_perfil", {"fecha_nacimiento": "2030-01-01"}, "no es válida"),
        ("actualizar_perfil", {"peso_kg": 900}, "fuera de rango"),
        ("guardar_umbrales", {"fc_max": 400}, "fuera de lo posible"),
        ("guardar_umbrales", {"ritmo_umbral": "rápido"}, "Formato"),
    ],
)
def test_perfil_y_umbrales_no_validos(session: Session, user: User, name: str, args: dict, error: str):
    assert error in _tool(session, user, name, args)["error"]


def test_salud_solo_con_consentimiento(client, user, session):
    no = _tool(session, user, "guardar_en_memoria", {"categoria": "lesiones", "dato": "Fascitis en 2025"})
    assert "consentimiento" in no["error"] and coach.memories(session, user.id) == []
    h = auth(user)
    assert client.put("/api/v1/coach/settings", json={"health_consent": True}, headers=h).json()["health_consent"]
    ok = _tool(session, user, "guardar_en_memoria", {"categoria": "lesiones", "dato": "Fascitis en 2025"})
    assert ok["ok"]
    _tool(session, user, "guardar_en_memoria", {"categoria": "preferencias", "dato": "Odia la cinta"})
    # Retirar el consentimiento borra lo de salud y deja lo demás.
    client.put("/api/v1/coach/settings", json={"health_consent": False}, headers=h)
    session.expire_all()
    assert [m.category for m in coach.memories(session, user.id)] == ["preferencias"]


def test_la_ficha_va_en_el_contexto(session: Session, user: User):
    coach.save_memory(session, user.id, "objetivos", "Quiere bajar de 45 min en 10K en primavera", "usuario")
    block = coach.context_block(session, user.id)
    assert "LO QUE SÉ DEL ATLETA" in block and "45 min en 10K" in block and "Entrevista inicial: pendiente" in block
    _tool(session, user, "terminar_entrevista", {})
    assert "Entrevista inicial: hecha" in coach.context_block(session, user.id)


def test_api_ficha(client, user, session):
    h = auth(user)
    m = client.post("/api/v1/coach/memories", json={"category": "vida", "content": "Trabaja a turnos"}, headers=h)
    assert m.status_code == 201 and m.json()["source"] == "usuario"
    mid = m.json()["id"]
    assert client.put(f"/api/v1/coach/memories/{mid}", json={"category": "vida", "content": "Turnos de noche"},
                      headers=h).json()["content"] == "Turnos de noche"  # fmt: skip
    assert client.get("/api/v1/coach/memories", headers=h).json()[0]["content"] == "Turnos de noche"
    assert client.post("/api/v1/coach/memories", json={"category": "salud", "content": "Asma"},
                       headers=h).status_code == 422  # sin consentimiento  # fmt: skip
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.delete(f"/api/v1/coach/memories/{mid}", headers=auth(other)).status_code == 404
    assert client.delete(f"/api/v1/coach/memories/{mid}", headers=h).status_code == 204


def _session(session: Session, user: User, day: date = TOMORROW) -> PlannedSession:
    planned = PlannedSession(user_id=user.id, day=day, sport="running", title="Series 6×1000")
    session.add(planned)
    session.flush()
    session.add(PlannedBlock(session_id=planned.id, position=0, kind="interval", repeat=6, distance_m=1000))
    session.commit()
    return planned


def test_propuesta_de_cambio_y_aceptar(client, user, session, monkeypatch):
    monkeypatch.setattr("app.api.workouts.queue_send", lambda s, uid: None)
    planned = _session(session, user)
    res = _tool(session, user, "proponer_cambio_plan", {
        "sesion_id": planned.id, "motivo": "El miércoles entras de noche: mejor descansar antes de las series.",
        "nuevo_dia": (TOMORROW + timedelta(days=1)).isoformat(),
        "bloques": [{"kind": "warmup", "repeat": 1, "duration_s": 900},
                    {"kind": "interval", "repeat": 5, "distance_m": 1000, "recovery_duration_s": 90}],
    })  # fmt: skip
    assert res["efecto"]["tipo"] == "propuesta" and "Series 6×1000: del" in res["efecto"]["resumen"]
    session.refresh(planned)
    assert planned.day == TOMORROW  # nada cambia hasta que la persona acepte
    h = auth(user)
    pending = client.get("/api/v1/coach/proposals", headers=h).json()
    assert len(pending) == 1 and pending[0]["reason"].startswith("El miércoles")
    done = client.post(f"/api/v1/coach/proposals/{pending[0]['id']}/accept", headers=h).json()
    assert done["status"] == "accepted"
    session.refresh(planned)
    blocks = session.exec(select(PlannedBlock).where(PlannedBlock.session_id == planned.id)).all()
    assert planned.day == TOMORROW + timedelta(days=1) and len(blocks) == 2
    assert client.post(f"/api/v1/coach/proposals/{pending[0]['id']}/reject", headers=h).status_code == 409


def test_propuestas_no_validas(session: Session, user: User):
    past = _session(session, user, date.today() - timedelta(days=2))
    args = {"sesion_id": past.id, "motivo": "x", "nuevo_titulo": "y"}
    assert "hoy en adelante" in _tool(session, user, "proponer_cambio_plan", args)["error"]
    planned = _session(session, user)
    assert "no cambia nada" in _tool(session, user, "proponer_cambio_plan",
                                     {"sesion_id": planned.id, "motivo": "x"})["error"]  # fmt: skip
    # La nueva sustituye a la pendiente anterior.
    _tool(session, user, "proponer_cambio_plan", {"sesion_id": planned.id, "motivo": "a", "nuevo_titulo": "A"})
    _tool(session, user, "proponer_cambio_plan", {"sesion_id": planned.id, "motivo": "b", "nuevo_titulo": "B"})
    states = [p.status for p in session.exec(select(PlanProposal).order_by(PlanProposal.id)).all()]
    assert states == ["expired", "pending"]


def _ai(session: Session, user: User) -> None:
    from app.core.crypto import encrypt_secret
    from app.models import AiProviderConfig

    config = AiProviderConfig(user_id=user.id, provider="anthropic", key_enc=encrypt_secret("sk-test"),
                              key_last4="test", model="claude-haiku-4-5", enabled=True, is_default=True)  # fmt: skip
    session.add(config)
    session.commit()


def test_revision_del_domingo_se_abre_y_avisa(session: Session, user: User, monkeypatch):
    _ai(session, user)
    sent: list = []
    monkeypatch.setattr(weekly_review.notifications, "notify", lambda *a, **k: sent.append(a) or True)
    sunday_evening = datetime(2026, 10, 25, 17, 30, tzinfo=UTC)  # 18:30 en Madrid (horario de invierno: +1)
    saturday = datetime(2026, 10, 24, 17, 30, tzinfo=UTC)
    assert weekly_review.due_tick(session, saturday) == 0
    assert weekly_review.due_tick(session, sunday_evening) == 1
    assert weekly_review.due_tick(session, sunday_evening + timedelta(hours=1)) == 0  # una por semana
    row = session.exec(select(WeeklyCheckin)).one()
    assert row.week_start == date(2026, 10, 19) and sent[0][2] == "weekly_review"
    # Desactivada: no se abre.
    session.add(CoachSettings(user_id=user.id, weekly_review=False))
    session.delete(row)
    session.commit()
    assert weekly_review.due_tick(session, sunday_evening) == 0


def test_responder_revision_y_resumen(client, user, session, monkeypatch):
    from app.services import llm
    from app.tasks import coach as tasks

    _ai(session, user)
    session.add(CoachSettings(user_id=user.id, health_consent=True))
    session.commit()
    h = auth(user)
    opened = client.post("/api/v1/coach/checkin", headers=h).json()
    assert opened["status"] == "pending"

    def fake_stream(provider, key, model, system, history, tools=None, executor=None):
        assert "Revisión de la semana" in history[0]["content"] and "molestias: gemelo derecho" in history[0]["content"]
        assert "LO QUE SÉ DEL ATLETA" in system
        dato = "Molestia en el gemelo derecho (oct 2026)"
        executor(llm.ToolCall(id="1", name="guardar_en_memoria", args={"categoria": "lesiones", "dato": dato}))
        yield llm.Chunk(text="**Tu semana** Bien. **Cómo llegas** Algo cargado. **Lo que toca** Suave.")

    monkeypatch.setattr(weekly_review, "stream_chat", fake_stream)
    monkeypatch.setattr(tasks.weekly_summary_task, "apply_async", lambda args: tasks.weekly_summary_task(*args))
    answers = {"energia": 3, "sueno": 4, "molestias": "gemelo derecho", "comentario": ""}
    res = client.post(f"/api/v1/coach/checkin/{opened['id']}/answers", json=answers, headers=h)
    assert res.status_code == 200, res.text
    row = client.get("/api/v1/coach/checkin", headers=h).json()
    assert row["status"] == "done" and row["summary"].startswith("**Tu semana**")
    assert row["answers"] == {"energia": 3, "sueno": 4, "molestias": "gemelo derecho"}
    assert row["effects"][0]["tipo"] == "memoria"
    assert client.post(f"/api/v1/coach/checkin/{opened['id']}/answers", json={}, headers=h).status_code == 422


def test_chat_con_efectos_y_entrevista(client, user, session, monkeypatch):
    from app.api import ai as ai_api
    from app.services import llm

    _ai(session, user)
    seen: dict = {}

    def fake_stream(provider, key, model, system, history, tools=None, executor=None):
        seen["system"] = system
        seen["tools"] = [t.name for t in tools]
        executor(llm.ToolCall(id="1", name="guardar_en_memoria",
                              args={"categoria": "historial", "dato": "Corre desde 2019"}))  # fmt: skip
        yield llm.Chunk(tool="Guardado en tu ficha: Corre desde 2019")
        yield llm.Chunk(text="Apuntado. ¿Has tenido lesiones?")

    monkeypatch.setattr(ai_api, "stream_chat", fake_stream)
    res = client.post("/api/v1/chat", json={"message": "Empecemos", "mode": "interview"}, headers=auth(user))
    body = res.text
    assert "event: effect" in body and "Corre desde 2019" in body
    assert "MODO ENTREVISTA INICIAL" in seen["system"] and "guardar_en_memoria" in seen["tools"]
    conv = client.get("/api/v1/chat/conversations", headers=auth(user)).json()[0]
    msgs = client.get(f"/api/v1/chat/conversations/{conv['id']}", headers=auth(user)).json()["messages"]
    assert msgs[-1]["effects"][0]["dato"] == "Corre desde 2019"


@pytest.mark.parametrize("bad", [{"energia": 9}, {"molestias": "x" * 600}])
def test_respuestas_no_validas(client, user, session, bad):
    _ai(session, user)
    opened = client.post("/api/v1/coach/checkin", headers=auth(user)).json()
    assert client.post(f"/api/v1/coach/checkin/{opened['id']}/answers", json=bad,
                       headers=auth(user)).status_code == 422  # fmt: skip
