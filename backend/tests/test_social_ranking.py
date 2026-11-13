"""Parte social: clasificación semanal/mensual y resumen para Hoy."""

from datetime import UTC, date, datetime

import pytest

from app.services import social
from tests.social_fixtures import add_activity, auth, befriend, make_user

TODAY = date(2026, 11, 11)  # miércoles: semana del 9 al 15 de noviembre


def at(day: int, hour: int = 10, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(social, "today_local", lambda: TODAY)


@pytest.fixture
def people(session):
    me = make_user(session, "yo", "Yo")
    ana = make_user(session, "ana", "Ana")
    bea = make_user(session, "bea", "Bea")
    for other in (ana, bea):
        befriend(session, me, other)
    return me, ana, bea


def _board(client, user, **params) -> dict:
    res = client.get("/api/v1/social/leaderboard", params=params, headers=auth(user))
    assert res.status_code == 200
    return res.json()


def test_period_bounds_cuando_semana_y_mes_entonces_limites_correctos():
    assert social.period_bounds("week", TODAY) == (
        date(2026, 11, 9),
        date(2026, 11, 15),
        date(2026, 11, 2),
        date(2026, 11, 8),
    )
    assert social.period_bounds("month", date(2026, 3, 31)) == (
        date(2026, 3, 1),
        date(2026, 3, 31),
        date(2026, 2, 1),
        date(2026, 2, 28),
    )


def test_leaderboard_cuando_semana_km_entonces_totales_rangos_y_gap(session, client, people):
    me, ana, bea = people
    add_activity(session, me, start=at(9), distance_m=10_000)
    add_activity(session, me, start=at(10), distance_m=11_049)
    add_activity(session, ana, start=at(11), distance_m=23_400)
    add_activity(session, bea, start=at(12), distance_m=5_000)
    add_activity(session, ana, start=at(8), distance_m=99_000)  # semana anterior: no cuenta
    data = _board(client, me)
    assert data["period_start"] == "2026-11-09" and data["period_end"] == "2026-11-15" and data["metric"] == "km"
    assert [(r["handle"], r["value"], r["rank"]) for r in data["rows"]] == [
        ("ana", 23.4, 1),
        ("yo", 21.0, 2),
        ("bea", 5.0, 3),
    ]
    assert data["my_rank"] == 2 and data["gap_to_next"] == 2.4 and data["next_name"] == "Ana"
    assert [r["me"] for r in data["rows"]] == [False, True, False]


def test_leaderboard_cuando_semana_anterior_entonces_prev_rank(session, client, people):
    me, ana, bea = people
    add_activity(session, me, start=at(3), distance_m=30_000)
    add_activity(session, ana, start=at(4), distance_m=20_000)
    add_activity(session, ana, start=at(10), distance_m=8_000)
    add_activity(session, me, start=at(10), distance_m=4_000)
    rows = {r["handle"]: r for r in _board(client, me)["rows"]}
    assert rows["ana"]["rank"] == 1 and rows["ana"]["prev_rank"] == 2
    assert rows["yo"]["rank"] == 2 and rows["yo"]["prev_rank"] == 1
    assert rows["bea"]["prev_rank"] is None  # no hizo nada la semana pasada


def test_leaderboard_cuando_actividad_solo_yo_de_amigo_entonces_no_cuenta(session, client, people):
    me, ana, _ = people
    add_activity(session, ana, start=at(10), distance_m=10_000)
    add_activity(session, ana, start=at(10, 18), distance_m=50_000, visibility="private")
    add_activity(session, me, start=at(10), distance_m=3_000, visibility="private")  # las mías, todas
    rows = {r["handle"]: r["value"] for r in _board(client, me)["rows"]}
    assert rows == {"ana": 10.0, "yo": 3.0, "bea": 0.0}


def test_leaderboard_cuando_no_sigo_o_pendiente_o_sin_perfil_entonces_no_aparece(session, client, people):
    me, *_ = people
    pend = make_user(session, "pend")
    befriend(session, me, pend, status="pending")
    make_user(session, "otro")
    add_activity(session, pend, start=at(10))
    handles = [r["handle"] for r in _board(client, me)["rows"]]
    assert sorted(handles) == ["ana", "bea", "yo"]
    sin = make_user(session, "sin", profile=False)
    assert _board(client, sin)["rows"] == [] and _board(client, sin)["my_rank"] is None


@pytest.mark.parametrize(("metric", "expected"), [("time", 5400), ("elevation", 350), ("days", 2)])
def test_leaderboard_cuando_otras_metricas_entonces_unidades(session, client, people, metric, expected):
    me, *_ = people
    add_activity(session, me, start=at(9, 8), duration_s=1800, elevation_gain_m=100.4)
    add_activity(session, me, start=at(9, 19), duration_s=1800, elevation_gain_m=100)
    add_activity(session, me, start=at(10, 8), duration_s=1800, elevation_gain_m=149.6)
    rows = {r["handle"]: r["value"] for r in _board(client, me, metric=metric)["rows"]}
    assert rows["yo"] == expected


def test_leaderboard_cuando_dia_local_madrid_entonces_cuenta_ese_dia(session, client, people):
    me, *_ = people
    # Domingo 8 a las 23:30 UTC = lunes 9 a las 00:30 en Madrid: cuenta en esta semana.
    add_activity(session, me, start=datetime(2026, 11, 8, 23, 30, tzinfo=UTC), distance_m=1000)
    assert {r["handle"]: r["value"] for r in _board(client, me)["rows"]}["yo"] == 1.0


def test_leaderboard_cuando_deporte_y_mes_entonces_filtra(session, client, people):
    me, ana, _ = people
    add_activity(session, me, start=at(2), distance_m=40_000, sport="road_biking")
    add_activity(session, me, start=at(3), distance_m=10_000, sport="trail_running")
    add_activity(session, ana, start=at(20, month=10), distance_m=10_000)
    run = {r["handle"]: r["value"] for r in _board(client, me, period="month", sport="running")["rows"]}
    bike = {r["handle"]: r["value"] for r in _board(client, me, period="month", sport="cycling")["rows"]}
    assert run["yo"] == 10.0 and bike["yo"] == 40.0
    month = _board(client, me, period="month")
    assert month["period_start"] == "2026-11-01" and month["period_end"] == "2026-11-30"
    assert {r["handle"]: r["prev_rank"] for r in month["rows"]}["ana"] == 1


def test_leaderboard_cuando_parametro_invalido_entonces_422(client, people):
    me, *_ = people
    assert client.get("/api/v1/social/leaderboard?metric=pasos", headers=auth(me)).status_code == 422


def test_summary_cuando_hay_amigos_entonces_puesto_y_distancia(session, client, people):
    me, ana, _ = people
    add_activity(session, me, start=at(10), distance_m=5_000)
    add_activity(session, ana, start=at(10), distance_m=7_500)
    data = client.get("/api/v1/social/summary", headers=auth(me)).json()
    assert data == {
        "has_profile": True,
        "my_rank": 2,
        "friends": 2,
        "gap_to_next": 2.5,
        "next_name": "Ana",
        "metric": "km",
        "active_duel": None,
    }


def test_summary_cuando_sin_perfil_entonces_has_profile_false(session, client):
    u = make_user(session, "x", profile=False)
    data = client.get("/api/v1/social/summary", headers=auth(u)).json()
    assert data["has_profile"] is False and data["my_rank"] is None and data["active_duel"] is None
