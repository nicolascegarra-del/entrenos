from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import AccountTier, Activity, PlannedSession, RaceGoal, TrainingPlan, TrainingPlanWeek, User
from app.services import plan_generator as gen
from app.services import training_plans as svc
from app.services.race_models import daniels_paces

PACES = daniels_paces(40)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _input(weeks: int = 12, distance: float = 10_000, days=(1, 3, 5, 6), km: float = 20, **kw) -> gen.PlanInput:
    start = date(2026, 1, 5)  # lunes
    race = start + timedelta(weeks=weeks - 1, days=6)  # domingo de la última semana
    return gen.PlanInput(race_date=race, distance_m=distance, start=start, weekdays=tuple(days), long_run_weekday=6,
                         current_km_week=km, paces=PACES, race_pace_s_km=300, **kw)  # fmt: skip


# ─── Generador ───────────────────────────────────────────────────────────────


def test_fases_en_orden_con_afinamiento_segun_distancia():
    assert gen.phases(12, 10_000)[-1] == "taper" and gen.phases(12, 10_000).count("taper") == 1
    assert gen.phases(16, 42_195).count("taper") == 2
    order = gen.phases(12, 10_000)
    ranks = {"base": 0, "build": 1, "peak": 2, "taper": 3}
    assert [ranks[p] for p in order] == sorted(ranks[p] for p in order)


def test_volumen_sube_como_mucho_10_por_ciento_con_descargas_y_afinamiento():
    weeks = gen.generate(_input(weeks=14, km=20))
    km = [w.target_km for w in weeks]
    normal = [w for w in weeks if not w.is_recovery and w.phase != "taper"]
    for a, b in zip(normal, normal[1:], strict=False):
        assert b.target_km <= a.target_km * 1.10 + 0.1
    assert any(w.is_recovery for w in weeks)
    assert weeks[-1].target_km < max(km) * 0.6  # semana de carrera muy suave


def test_semana_de_carrera_tiene_la_carrera_y_poco_mas():
    weeks = gen.generate(_input())
    last = weeks[-1].workouts
    assert last[-1].kind == "race" and last[-1].day == _input().race_date
    assert len(last) <= 3


def test_calidad_como_mucho_2_y_tirada_larga_en_su_dia():
    for w in gen.generate(_input(days=(0, 1, 2, 3, 4, 6))):
        quality = [x for x in w.workouts if x.kind in ("threshold", "intervals", "race_pace")]
        assert len(quality) <= 2
        longs = [x for x in w.workouts if x.kind == "long"]
        assert all(x.day.weekday() == 6 for x in longs)


def test_ritmos_de_daniels_en_los_bloques():
    week = next(w for w in gen.generate(_input()) if w.phase == "build")
    threshold = next(x for x in week.workouts if x.kind == "threshold")
    interval = next(b for b in threshold.blocks if b.kind == "interval")
    assert interval.pace == PACES["threshold"] and interval.repeat >= 2


def test_cuenta_basica_respeta_el_maximo_de_sesiones():
    for w in gen.generate(_input(days=(0, 1, 2, 3, 4, 5, 6), max_sessions_week=3)):
        assert len(w.workouts) <= 3


def test_menos_de_4_semanas_entonces_error():
    with pytest.raises(ValueError, match="semanas"):
        gen.generate(_input(weeks=2))


@pytest.mark.parametrize(
    ("done", "compliance", "tsb", "acwr", "action"),
    [
        (1.0, 92, 3, 1.0, "progress"),
        (1.0, 90, -15, 1.0, "hold"),
        (0.6, 90, 0, 1.0, "hold"),
        (1.0, 60, 0, 1.0, "hold"),
        (0.3, None, 0, 1.0, "reduce"),
        (1.0, 95, 0, 1.6, "reduce"),
        (None, None, None, None, "progress"),
    ],
)
def test_reglas_de_adaptacion(done, compliance, tsb, acwr, action):
    assert gen.adjustment(done, compliance, tsb, acwr).action == action


# ─── API ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def goal(session: Session, user: User) -> RaceGoal:
    g = RaceGoal(user_id=user.id, name="10K", race_date=date.today() + timedelta(weeks=10), distance_m=10_000,
                 target_time_s=3000)  # fmt: skip
    session.add(g)
    for d in range(1, 28, 3):  # historial: ~20 km/semana
        session.add(Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC) - timedelta(days=d),
                             duration_s=2400, distance_m=7000, avg_hr=150))  # fmt: skip
    session.commit()
    session.refresh(g)
    return g


BODY = {"weekdays": [1, 3, 6], "long_run_weekday": 6}


def test_preview_no_guarda_nada(client, user, goal, session):
    res = client.post("/api/v1/training-plans/preview", json={**BODY, "goal_id": goal.id}, headers=auth(user))
    data = res.json()
    assert res.status_code == 200 and len(data["weeks"]) >= 10 and data["start_km_week"] > 0
    assert session.exec(select(TrainingPlan)).first() is None


def test_crear_plan_guarda_semanas_y_sesiones_futuras(client, user, goal, session):
    res = client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(user))
    plan = res.json()
    assert res.status_code == 201 and plan["goal_name"] == "10K" and plan["current_week"] == 1
    sessions = session.exec(select(PlannedSession).where(PlannedSession.plan_id == plan["id"])).all()
    assert sessions and all(s.day >= date.today() for s in sessions)
    assert {s.session_kind for s in sessions} >= {"long", "race"}
    listed = client.get(f"/api/v1/plans?date_from={date.today()}&date_to={date.today() + timedelta(days=30)}",
                        headers=auth(user))  # fmt: skip
    assert any(s["plan_id"] == plan["id"] for s in listed.json())
    assert client.get("/api/v1/training-plans/active", headers=auth(user)).json()["id"] == plan["id"]


def test_crear_otro_plan_cancela_el_anterior(client, user, goal, session):
    first = client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(user)).json()
    second = client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(user)).json()
    assert session.get(TrainingPlan, first["id"]).status == "cancelled"
    assert not session.exec(select(PlannedSession).where(PlannedSession.plan_id == first["id"])).all()
    assert second["status"] == "active"


def test_objetivo_demasiado_cercano_422(client, user, session):
    g = RaceGoal(user_id=user.id, name="Pronto", race_date=date.today() + timedelta(days=10), distance_m=5000)
    session.add(g)
    session.commit()
    res = client.post("/api/v1/training-plans/preview", json={**BODY, "goal_id": g.id}, headers=auth(user))
    assert res.status_code == 422 and "semanas" in res.json()["error"]["message"]


def test_objetivo_de_otro_usuario_404(client, goal, session):
    other = User(email="otro@example.com", password_hash="x")
    session.add(other)
    session.commit()
    res = client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(other))
    assert res.status_code == 404


def test_adaptar_reduce_si_se_hizo_poco(client, user, goal, session, monkeypatch):
    plan = client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(user)).json()
    monkeypatch.setattr(svc, "_week_status", lambda s, p, start: (0.2, None))
    res = client.post(f"/api/v1/training-plans/{plan['id']}/adapt", headers=auth(user)).json()
    assert res["adjustment"]["action"] == "reduce" and "menos de la mitad" in res["adjustment"]["reason"]
    week = session.exec(select(TrainingPlanWeek).where(TrainingPlanWeek.plan_id == plan["id"],
                                                       TrainingPlanWeek.index == 1)).one()  # fmt: skip
    assert week.adjustment["action"] == "reduce"
    current = next(w for w in res["plan"]["weeks"] if w["is_current"])
    assert current["adjustment"]["reason"]


def test_adapt_due_solo_una_vez_por_semana_y_cierra_planes_pasados(session, user, goal, client):
    client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(user))
    assert svc.adapt_due(session) == 1
    assert svc.adapt_due(session) == 0
    plan = session.exec(select(TrainingPlan)).one()
    assert svc.adapt_due(session, today=plan.race_date + timedelta(days=1)) == 0
    session.refresh(plan)
    assert plan.status == "done"


def test_cancelar_plan(client, user, goal, session):
    plan = client.post("/api/v1/training-plans", json={**BODY, "goal_id": goal.id}, headers=auth(user)).json()
    assert client.delete(f"/api/v1/training-plans/{plan['id']}", headers=auth(user)).status_code == 204
    assert client.get("/api/v1/training-plans/active", headers=auth(user)).json() is None


def test_cuenta_basica_plan_con_su_maximo(client, session, goal, user):
    user.tier = AccountTier.BASIC
    session.add(user)
    session.commit()
    body = {"goal_id": goal.id, "weekdays": [0, 1, 2, 3, 4, 5, 6], "long_run_weekday": 6}
    weeks = client.post("/api/v1/training-plans/preview", json=body, headers=auth(user)).json()["weeks"]
    assert max(len(w["sessions"]) for w in weeks) <= 14


def test_tirada_larga_siempre_la_mas_larga_y_calidad_a_escala():
    for km in (12, 16, 30, 50):
        for w in gen.generate(_input(km=km, days=(1, 3, 6))):
            longs = [x for x in w.workouts if x.kind == "long"]
            others = [x for x in w.workouts if x.kind not in ("long", "race")]
            if longs and others:
                assert longs[0].km >= max(o.km for o in others), (km, w.index, w.workouts)
    low = gen.generate(_input(km=12, days=(1, 3, 6)))
    rp = [x for w in low for x in w.workouts if x.kind == "race_pace"]
    assert all(x.km <= 8 for x in rp)  # con poco volumen, el ritmo de carrera no es de 10 km


def test_primera_semana_mensaje_propio():
    assert "Primera semana" in gen.adjustment(None, None, 2, 1.0).reason
    assert "cumplida" in gen.adjustment(1.0, 95, 2, 1.0).reason
