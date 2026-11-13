"""Parte social: duelos 1 contra 1 (crear, aceptar, marcador, cierre y avisos de adelantamiento)."""

from datetime import UTC, date, datetime

import pytest
from sqlmodel import select

from app.models import Duel
from app.services import social
from app.tasks import social as social_tasks
from tests.social_fixtures import add_activity, auth, befriend, make_user

TODAY = date(2026, 11, 11)


def at(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(social, "today_local", lambda: TODAY)


@pytest.fixture
def pair(session):
    ana = make_user(session, "ana", "Ana")
    bea = make_user(session, "bea", "Bea")
    befriend(session, ana, bea)
    befriend(session, bea, ana)
    return ana, bea


def _create(client, user, opponent, **body) -> dict:
    payload = {"opponent_id": opponent.id, "metric": "km", "sport": "all", "duration": "1w", **body}
    return client.post("/api/v1/social/duels", json=payload, headers=auth(user))


def _active_duel(client, pair, **body) -> dict:
    ana, bea = pair
    duel = _create(client, ana, bea, **body).json()
    return client.post(f"/api/v1/social/duels/{duel['id']}/accept", headers=auth(bea)).json()


# ─── Crear y responder ───────────────────────────────────────────────────────


def test_crear_duelo_cuando_amigos_mutuos_entonces_pendiente_y_aviso(session, client, pair, pushes):
    ana, bea = pair
    res = _create(client, ana, bea)
    assert res.status_code == 200
    duel = res.json()
    assert duel["status"] == "pending" and duel["i_am_challenger"] is True
    assert duel["my_value"] is None and duel["their_value"] is None
    assert duel["challenger"] == {"user_id": ana.id, "display_name": "Ana", "handle": "ana"}
    assert pushes[-1]["user_id"] == bea.id and "te reta" in pushes[-1]["body"]
    lists = client.get("/api/v1/social/duels", headers=auth(bea)).json()
    assert [d["id"] for d in lists["pending_in"]] == [duel["id"]] and lists["pending_out"] == []
    assert [d["id"] for d in client.get("/api/v1/social/duels", headers=auth(ana)).json()["pending_out"]] == [
        duel["id"]
    ]


def test_crear_duelo_cuando_solo_sigo_y_privado_entonces_403(session, client):
    ana = make_user(session, "ana")
    bea = make_user(session, "bea")
    befriend(session, ana, bea)  # Bea no sigue a Ana
    res = _create(client, ana, bea)
    assert res.status_code == 403 and res.json()["error"]["code"] == "NOT_FRIENDS"


def test_crear_duelo_cuando_perfil_publico_entonces_permitido(session, client):
    ana = make_user(session, "ana")
    pub = make_user(session, "pub", public=True)
    assert _create(client, ana, pub).status_code == 200


def test_crear_duelo_cuando_ya_hay_uno_o_bloqueo_o_datos_malos_entonces_error(session, client, pair):
    ana, bea = pair
    assert _create(client, ana, bea).status_code == 200
    res = _create(client, bea, ana)
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUEL_EXISTS"
    assert _create(client, ana, bea, metric="pasos").status_code == 422
    assert _create(client, ana, bea, duration="3d").status_code == 422
    assert _create(client, ana, ana).status_code == 400
    client.post(f"/api/v1/social/block/{ana.id}", headers=auth(bea))
    assert _create(client, ana, bea).status_code == 404


def test_aceptar_duelo_cuando_retado_entonces_activo_desde_hoy(session, client, pair, pushes):
    ana, bea = pair
    duel = _create(client, ana, bea, duration="1m").json()
    assert client.post(f"/api/v1/social/duels/{duel['id']}/accept", headers=auth(ana)).status_code == 409
    res = client.post(f"/api/v1/social/duels/{duel['id']}/accept", headers=auth(bea))
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active" and data["start_date"] == "2026-11-11" and data["end_date"] == "2026-12-10"
    assert data["i_am_challenger"] is False and data["my_value"] == 0
    assert pushes[-1]["user_id"] == ana.id and "aceptado" in pushes[-1]["body"]
    assert client.post(f"/api/v1/social/duels/{duel['id']}/decline", headers=auth(bea)).status_code == 409


def test_rechazar_y_cancelar_duelo_cuando_permitido_entonces_cambia_estado(session, client, pair):
    ana, bea = pair
    d1 = _create(client, ana, bea).json()
    assert client.post(f"/api/v1/social/duels/{d1['id']}/cancel", headers=auth(bea)).status_code == 409
    assert client.post(f"/api/v1/social/duels/{d1['id']}/decline", headers=auth(bea)).json()["status"] == "declined"
    d2 = _create(client, ana, bea).json()
    assert client.post(f"/api/v1/social/duels/{d2['id']}/cancel", headers=auth(ana)).json()["status"] == "cancelled"
    carla = make_user(session, "carla")
    assert client.post(f"/api/v1/social/duels/{d2['id']}/cancel", headers=auth(carla)).status_code == 404


# ─── Marcador ────────────────────────────────────────────────────────────────


def test_marcador_cuando_actividades_en_periodo_entonces_suma_solo_compartidas(session, client, pair):
    ana, bea = pair
    duel = _active_duel(client, pair)
    add_activity(session, ana, start=at(11), distance_m=23_400)
    add_activity(session, ana, start=at(12), distance_m=50_000, visibility="private")  # no cuenta
    add_activity(session, ana, start=at(10), distance_m=9_000)  # antes de empezar
    add_activity(session, bea, start=at(12), distance_m=21_000)
    add_activity(session, bea, start=at(13), distance_m=5_000, sport="road_biking")
    data = client.get("/api/v1/social/duels", headers=auth(bea)).json()["active"][0]
    assert data["id"] == duel["id"] and data["my_value"] == 26.0 and data["their_value"] == 23.4
    summary = client.get("/api/v1/social/summary", headers=auth(ana)).json()
    assert summary["active_duel"]["my_value"] == 23.4


def test_marcador_cuando_deporte_running_entonces_filtra(session, client, pair):
    ana, bea = pair
    _active_duel(client, pair, sport="running")
    add_activity(session, bea, start=at(12), distance_m=21_000, sport="trail_running")
    add_activity(session, bea, start=at(13), distance_m=50_000, sport="road_biking")
    assert client.get("/api/v1/social/duels", headers=auth(bea)).json()["active"][0]["my_value"] == 21.0


def test_marcador_cuando_mejor_5k_entonces_menor_gana_y_null_sin_marca(session, client, pair):
    ana, bea = pair
    duel = _active_duel(client, pair, metric="best_5k")
    row = session.get(Duel, duel["id"])
    assert social.duel_values(session, row) == (None, None)
    add_activity(session, ana, start=at(11), metrics={"best_5k": 1320.0})
    add_activity(session, ana, start=at(12), metrics={"best_5k": 1290.0})
    assert social.duel_values(session, row) == (1290.0, None)
    assert social.leader(row, 1290.0, None) == ana.id
    add_activity(session, bea, start=at(12), metrics={"best_5k": 1250.0})
    assert social.leader(row, *social.duel_values(session, row)) == bea.id


# ─── Cierre y avisos ─────────────────────────────────────────────────────────


def test_cerrar_duelos_cuando_vencido_entonces_ganador_y_aviso_a_los_dos(session, client, pair, pushes):
    ana, bea = pair
    duel = _active_duel(client, pair)  # 11 al 17 de noviembre
    add_activity(session, ana, start=at(12), distance_m=10_000)
    add_activity(session, bea, start=at(13), distance_m=8_000)
    assert social.close_duels(session, today=date(2026, 11, 17)) == 0  # aún no ha terminado
    pushes.clear()
    assert social.close_duels(session, today=date(2026, 11, 18)) == 1
    row = session.get(Duel, duel["id"])
    session.refresh(row)
    assert row.status == "finished" and row.winner_id == ana.id
    assert (row.challenger_value, row.opponent_value) == (10.0, 8.0)
    titles = {p["user_id"]: p["title"] for p in pushes}
    assert "ganado" in titles[ana.id] and titles[bea.id] == "Duelo terminado"
    # Una actividad posterior no cambia el marcador guardado.
    add_activity(session, bea, start=at(14), distance_m=30_000)
    finished = client.get("/api/v1/social/duels", headers=auth(bea)).json()["finished"][0]
    assert finished["my_value"] == 8.0 and finished["winner_id"] == ana.id
    assert social.close_duels(session, today=date(2026, 11, 19)) == 0


def test_cerrar_duelos_cuando_empate_entonces_sin_ganador(session, client, pair, pushes):
    ana, bea = pair
    duel = _active_duel(client, pair)
    add_activity(session, ana, start=at(12), distance_m=10_000)
    add_activity(session, bea, start=at(13), distance_m=10_000)
    social.close_duels(session, today=date(2026, 11, 18))
    row = session.get(Duel, duel["id"])
    session.refresh(row)
    assert row.status == "finished" and row.winner_id is None
    assert all("empate" in p["title"] for p in pushes[-2:])


def test_adelantamiento_cuando_cambia_lider_entonces_un_aviso_sin_duplicar(session, client, pair, pushes):
    ana, bea = pair
    _active_duel(client, pair)
    pushes.clear()
    add_activity(session, bea, start=at(11), distance_m=21_000)
    assert social.duel_overtakes(session) == 0  # primera líder: nadie ha sido adelantado
    add_activity(session, ana, start=at(12), distance_m=23_400)
    assert social.duel_overtakes(session) == 1
    assert pushes[-1]["user_id"] == bea.id
    assert pushes[-1]["body"] == "Ana te ha pasado: 23,4 km contra 21,0"
    assert social.duel_overtakes(session) == 0  # la tarea se repite: sin avisos de más
    assert len(pushes) == 1
    add_activity(session, bea, start=at(13), distance_m=5_000)
    assert social.duel_overtakes(session, now=datetime(2026, 11, 13, 20, tzinfo=UTC)) == 1
    assert pushes[-1]["user_id"] == ana.id


def test_tareas_celery_cuando_se_ejecutan_entonces_usan_el_servicio(session, client, pair, monkeypatch):
    calls = []
    monkeypatch.setattr(social, "close_duels", lambda s: calls.append("close") or 0)
    monkeypatch.setattr(social, "duel_overtakes", lambda s: calls.append("lead") or 0)
    assert social_tasks.close_duels_task() == 0 and social_tasks.duel_overtakes_task() == 0
    assert calls == ["close", "lead"]
    assert session.exec(select(Duel)).all() == []
