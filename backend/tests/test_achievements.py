from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Achievement, Activity, User
from app.services import achievements as svc

TODAY = date(2026, 10, 22)  # jueves


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _act(session: Session, user: User, day: date, km: float = 5, sport: str = "running", elev: float = 0,
         metrics: dict | None = None) -> Activity:  # fmt: skip
    a = Activity(user_id=user.id, sport=sport, start_time=datetime(day.year, day.month, day.day, 8, tzinfo=UTC),
                 duration_s=km * 330, distance_m=km * 1000, elevation_gain_m=elev, metrics=metrics or {})  # fmt: skip
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# ─── Racha ───────────────────────────────────────────────────────────────────


def test_racha_la_semana_en_curso_no_la_rompe():
    monday = svc.week_start(TODAY)
    counts = {monday - timedelta(days=7 * k): 3 for k in range(1, 5)}  # 4 semanas cumplidas
    counts[monday] = 1  # esta semana aún no
    s = svc.streaks(counts, 3, TODAY)
    assert s["current"] == 4 and s["best"] == 4 and s["this_week"] == 1 and len(s["weeks"]) == 12
    counts[monday] = 3
    assert svc.streaks(counts, 3, TODAY)["current"] == 5


def test_racha_se_corta_con_una_semana_floja():
    monday = svc.week_start(TODAY)
    counts = {monday - timedelta(days=7 * k): 3 for k in (1, 2, 4, 5, 6)}
    s = svc.streaks(counts, 3, TODAY)
    assert s["current"] == 2 and s["best"] == 3
    assert svc.streaks({}, 3, TODAY)["best"] == 0


# ─── Retos del mes ───────────────────────────────────────────────────────────


def test_retos_personales_con_la_media_de_3_meses(session, user):
    for month in (7, 8, 9):
        for d in (3, 10, 17):
            _act(session, user, date(2026, month, d), km=10, elev=100)
    _act(session, user, date(2026, 10, 5), km=40, elev=400)
    ch = {c["key"]: c for c in svc.challenges(svc.prog.user_activities(session, user.id), TODAY)}
    assert ch["km"]["target"] == 40 and ch["km"]["current"] == 40 and ch["km"]["done"]  # 30 × 1,1 → 40
    assert ch["sessions"]["target"] == 8 and not ch["sessions"]["done"]  # mínimo 8
    assert ch["elevation"]["target"] == 400 and ch["km"]["ends"] == date(2026, 10, 31)


def test_sin_desnivel_no_hay_reto_de_desnivel():
    assert [c["key"] for c in svc.challenges([], TODAY)] == ["km", "sessions"]


# ─── Logros ──────────────────────────────────────────────────────────────────


def test_hitos_rachas_y_records(session, user):
    start = date(2026, 6, 1)
    for i in range(12):  # 12 carreras, 3 por semana durante 4 semanas
        _act(session, user, start + timedelta(days=(i // 3) * 7 + i % 3), km=6, elev=100,
             metrics={"best_5k": 1800 - i * 10})  # fmt: skip
    _act(session, user, date(2026, 7, 1), km=10.2)
    _act(session, user, date(2026, 7, 2), km=40, sport="cycling", elev=0)
    found = {c["key"]: c for c in svc.candidates(svc.prog.user_activities(session, user.id), 3, TODAY)}
    assert {"first_run", "first_5k", "first_10k", "count_10", "elev_1000", "streak_4"} <= found.keys()
    assert "first_half" not in found and "km_100" not in found  # 82 km de carrera
    assert found["first_5k"]["achieved_on"] == start
    assert found["streak_4"]["achieved_on"] == date(2026, 6, 28)  # domingo de la 4.ª semana
    records = [c for c in found.values() if c["kind"] == "record"]
    assert len(records) == 11 and records[-1]["title"] == "Récord en Mejor 5 km: 28:10"


def test_primera_vez_con_historial_no_avisa(session, user, monkeypatch):
    sent = []
    monkeypatch.setattr(svc.notifications, "notify", lambda *a, **k: sent.append(a[4]) or True)
    _act(session, user, TODAY - timedelta(days=60), km=6)
    new = svc.evaluate(session, user.id, TODAY)
    assert {a.key for a in new} >= {"first_run", "first_5k"} and sent == []
    _act(session, user, TODAY - timedelta(days=1), km=10.5)
    assert [a.key for a in svc.evaluate(session, user.id, TODAY) if a.kind == "milestone"] == ["first_10k"]
    assert sent == ["🏆 Primeros 10 km"]
    assert svc.evaluate(session, user.id, TODAY) == []  # no repite


def test_cuenta_nueva_recibe_sus_primeros_logros(session, user, monkeypatch):
    sent = []
    monkeypatch.setattr(svc.notifications, "notify", lambda *a, **k: sent.append(a[4]) or True)
    _act(session, user, TODAY - timedelta(days=1), km=5.2)
    svc.evaluate(session, user.id, TODAY)
    assert sent == ["🏆 2 logros nuevos"]


def test_logros_antiguos_importados_no_avisan(session, user, monkeypatch):
    sent = []
    monkeypatch.setattr(svc.notifications, "notify", lambda *a, **k: sent.append(a[4]) or True)
    _act(session, user, TODAY - timedelta(days=60), km=3)
    svc.evaluate(session, user.id, TODAY)
    _act(session, user, TODAY - timedelta(days=50), km=12)  # sync de histórico antiguo
    svc.evaluate(session, user.id, TODAY)
    assert sent == []


# ─── API ─────────────────────────────────────────────────────────────────────


def test_api_logros(client, user, session):
    _act(session, user, date.today() - timedelta(days=2), km=5.5)
    data = client.get("/api/v1/achievements", headers=auth(user)).json()
    assert data["streak"]["target"] == 3 and data["milestones"]["total"] == len(svc.MILESTONES)
    assert {a["key"] for a in data["achievements"]} == {"first_run", "first_5k"}
    upcoming = {u["group"]: u for u in data["upcoming"]}
    assert upcoming["single_run"]["key"] == "first_10k" and upcoming["single_run"]["pct"] == 55
    assert session.exec(select(Achievement)).all()  # se guardan al consultarlos


@pytest.mark.parametrize(("sessions", "code"), [(2, 200), (0, 422), (15, 422)])
def test_objetivo_semanal(client, user, sessions, code):
    res = client.put("/api/v1/achievements/weekly-goal", json={"sessions": sessions}, headers=auth(user))
    assert res.status_code == code
    if code == 200:
        assert res.json()["streak"]["target"] == 2
