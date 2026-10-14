import pytest
from sqlmodel import Session, select

from app.core.security import create_token, hash_password
from app.models import Activity, PlannedSession, User
from app.services.plan_service import match_pending
from app.services.sync_service import sync_activities
from tests.fakes import FakeGarmin, MemoryStorage

# FakeGarmin crea carreras a las 17:58 hora local del 14/10/2026 hacia atrás, una por día.
RUN_DAY = "2026-10-14"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def plan_body(**overrides) -> dict:
    body = {
        "day": RUN_DAY,
        "sport": "running",
        "title": "Rodaje con ritmo",
        "blocks": [
            {"kind": "warmup", "duration_s": 600},
            {"kind": "steady", "distance_m": 3000, "target_metric": "pace", "target_min": 400, "target_max": 450},
            {"kind": "cooldown"},
        ],
    }
    return body | overrides


@pytest.fixture
def synced(session: Session, user: User) -> User:
    sync_activities(session, user.id, FakeGarmin(3), MemoryStorage())
    return user


def test_create_plan_cuando_hay_actividad_ese_dia_entonces_empareja_y_puntua(client, synced):
    res = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced))
    assert res.status_code == 201
    plan = res.json()
    assert plan["activity"]["start_time"].startswith(RUN_DAY)
    assert plan["match_mode"] == "auto"
    assert plan["compliance_detail"]["method"] == "streams"  # la actividad del fixture tiene 1 vuelta
    assert len(plan["compliance_detail"]["steps"]) == 3
    assert plan["compliance_score"] is not None
    assert plan["planned_distance_m"] == 3000
    assert [b["position"] for b in plan["blocks"]] == [0, 1, 2]


def test_create_plan_cuando_dia_sin_actividad_entonces_pendiente(client, synced):
    plan = client.post("/api/v1/plans", json=plan_body(day="2026-12-01"), headers=auth(synced)).json()
    assert plan["activity"] is None and plan["compliance_score"] is None


def test_create_plan_cuando_otro_deporte_entonces_no_empareja(client, synced):
    plan = client.post("/api/v1/plans", json=plan_body(sport="cycling"), headers=auth(synced)).json()
    assert plan["activity"] is None


def test_create_plan_cuando_dos_planes_mismo_dia_entonces_actividad_no_se_reutiliza(client, synced):
    first = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced)).json()
    second = client.post("/api/v1/plans", json=plan_body(title="Doble"), headers=auth(synced)).json()
    assert first["activity"] is not None
    assert second["activity"] is None


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ({"kind": "steady", "duration_s": 60, "distance_m": 100}, "no ambas"),
        ({"kind": "steady", "target_metric": "hr"}, "mínimo, un máximo"),
        ({"kind": "steady", "target_metric": "hr", "target_min": 160, "target_max": 150}, "mayor que el máximo"),
    ],
)
def test_create_plan_cuando_bloque_invalido_entonces_422_con_mensaje(client, user, block, message):
    res = client.post("/api/v1/plans", json=plan_body(blocks=[block]), headers=auth(user))
    assert res.status_code == 422
    assert message in res.json()["error"]["message"]


def test_list_plans_cuando_rango_entonces_solo_esos_dias(client, synced):
    for day in ("2026-10-12", "2026-10-14", "2026-10-20"):
        client.post("/api/v1/plans", json=plan_body(day=day), headers=auth(synced))
    res = client.get("/api/v1/plans?date_from=2026-10-12&date_to=2026-10-18", headers=auth(synced)).json()
    assert [p["day"] for p in res] == ["2026-10-12", "2026-10-14"]


def test_list_plans_cuando_rango_excesivo_entonces_400(client, user):
    res = client.get("/api/v1/plans?date_from=2026-01-01&date_to=2026-12-31", headers=auth(user))
    assert res.status_code == 400


def test_update_plan_cuando_cambia_dia_entonces_reempareja(client, synced):
    plan = client.post("/api/v1/plans", json=plan_body(day="2026-12-01"), headers=auth(synced)).json()
    updated = client.put(f"/api/v1/plans/{plan['id']}", json=plan_body(), headers=auth(synced)).json()
    assert updated["activity"] is not None
    assert len(updated["blocks"]) == 3


def test_set_match_cuando_manual_sin_actividad_entonces_desvincula_y_no_reempareja(client, session, synced):
    plan = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced)).json()
    res = client.put(f"/api/v1/plans/{plan['id']}/match", json={"mode": "manual"}, headers=auth(synced)).json()
    assert res["activity"] is None and res["match_mode"] == "manual"
    assert match_pending(session, synced.id) == 0  # el modo manual no se toca tras sincronizar


def test_set_match_cuando_manual_con_actividad_de_otro_dia_entonces_la_respeta(client, session, synced):
    other_day = session.exec(select(Activity).order_by(Activity.start_time)).first()
    plan = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced)).json()
    res = client.put(
        f"/api/v1/plans/{plan['id']}/match",
        json={"mode": "manual", "activity_id": other_day.id},
        headers=auth(synced),
    ).json()
    assert res["activity"]["id"] == other_day.id
    assert res["compliance_score"] is not None


def test_set_match_cuando_actividad_ajena_entonces_400(client, session, synced):
    stranger = User(email="otra@example.com", password_hash=hash_password("x" * 12))
    session.add(stranger)
    session.commit()
    plan = client.post("/api/v1/plans", json=plan_body(day="2026-12-01"), headers=auth(stranger)).json()
    activity = session.exec(select(Activity)).first()
    res = client.put(
        f"/api/v1/plans/{plan['id']}/match",
        json={"mode": "manual", "activity_id": activity.id},
        headers=auth(stranger),
    )
    assert res.status_code == 400


def test_candidates_cuando_dia_con_carrera_entonces_la_lista(client, synced):
    plan = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced)).json()
    candidates = client.get(f"/api/v1/plans/{plan['id']}/candidates", headers=auth(synced)).json()
    assert len(candidates) == 1 and candidates[0]["start_time"].startswith(RUN_DAY)


def test_plan_cuando_es_de_otro_usuario_entonces_404(client, session, synced):
    plan = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced)).json()
    stranger = User(email="otra@example.com", password_hash=hash_password("x" * 12))
    session.add(stranger)
    session.commit()
    for method, path in (("get", ""), ("delete", ""), ("get", "/candidates")):
        res = getattr(client, method)(f"/api/v1/plans/{plan['id']}{path}", headers=auth(stranger))
        assert res.status_code == 404


def test_delete_plan_cuando_existe_entonces_204_y_desaparece(client, session, synced):
    plan = client.post("/api/v1/plans", json=plan_body(), headers=auth(synced)).json()
    assert client.delete(f"/api/v1/plans/{plan['id']}", headers=auth(synced)).status_code == 204
    assert session.get(PlannedSession, plan["id"]) is None


def test_match_pending_cuando_llega_la_actividad_despues_entonces_empareja(client, session, user):
    plan = client.post("/api/v1/plans", json=plan_body(), headers=auth(user)).json()
    assert plan["activity"] is None
    sync_activities(session, user.id, FakeGarmin(1), MemoryStorage())
    assert match_pending(session, user.id) == 1
    assert client.get(f"/api/v1/plans/{plan['id']}", headers=auth(user)).json()["activity"] is not None
