import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import create_token, hash_password
from app.models import SyncRun, SyncStatus, User
from app.services.metric_catalog import seed_catalog
from app.services.streams import downsample
from app.services.sync_service import sync_activities
from tests.fakes import FakeGarmin, MemoryStorage


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


@pytest.fixture
def synced(session: Session, user: User) -> User:
    sync_activities(session, user.id, FakeGarmin(5), MemoryStorage())
    return user


def test_downsample_cuando_menos_puntos_que_el_limite_entonces_igual():
    data = {"hr": [1.0, 2.0, 3.0]}
    assert downsample(data, 10) == data


def test_downsample_cuando_muchos_puntos_entonces_promedia_y_conserva_coordenadas():
    data = {
        "hr": [100.0, 110.0, None, 130.0],
        "lat": [40.0, 40.1, 40.2, 40.3],
        "speed": [None, None, 3.0, 3.0],
    }
    assert downsample(data, 2) == {"hr": [105.0, 130.0], "lat": [40.0, 40.2], "speed": [None, 3.0]}


def test_list_activities_cuando_hay_mas_que_el_limite_entonces_pagina_por_cursor(client: TestClient, synced):
    first = client.get("/api/v1/activities?limit=2", headers=auth(synced)).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = client.get(f"/api/v1/activities?limit=2&cursor={first['next_cursor']}", headers=auth(synced)).json()
    third = client.get(f"/api/v1/activities?limit=2&cursor={second['next_cursor']}", headers=auth(synced)).json()
    ids = [a["id"] for page in (first, second, third) for a in page["items"]]
    assert len(ids) == 5 == len(set(ids))
    assert third["next_cursor"] is None
    starts = [a["start_time"] for page in (first, second, third) for a in page["items"]]
    assert starts == sorted(starts, reverse=True)


def test_list_activities_cuando_filtro_deporte_y_fecha_entonces_filtra(client, synced):
    res = client.get("/api/v1/activities?sport=cycling", headers=auth(synced)).json()
    assert res["items"] == []
    res = client.get("/api/v1/activities?date_from=2026-10-13T00:00:00Z", headers=auth(synced)).json()
    assert len(res["items"]) == 2


def test_list_activities_cuando_cursor_invalido_entonces_400(client, synced):
    res = client.get("/api/v1/activities?cursor=basura", headers=auth(synced))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"


def test_list_sports_cuando_hay_carreras_entonces_running(client, synced):
    assert client.get("/api/v1/activities/sports", headers=auth(synced)).json() == ["running"]


def test_get_activity_cuando_existe_entonces_detalle_con_vueltas_canales_y_reloj(client, synced):
    activity_id = client.get("/api/v1/activities?limit=1", headers=auth(synced)).json()["items"][0]["id"]
    detail = client.get(f"/api/v1/activities/{activity_id}", headers=auth(synced)).json()
    assert detail["device"]["name"] == "Forerunner 735XT"
    assert detail["laps"] and detail["laps"][0]["avg_hr"] == 133
    assert {"time", "hr", "speed", "lat", "lon"} <= set(detail["channels"])
    assert detail["metrics"]["avg_cadence"] > 150


def test_get_activity_cuando_es_de_otro_usuario_entonces_404(client, session, synced):
    other = User(email="otro@example.com", password_hash=hash_password("x" * 12))
    session.add(other)
    session.commit()
    activity_id = client.get("/api/v1/activities?limit=1", headers=auth(synced)).json()["items"][0]["id"]
    assert client.get(f"/api/v1/activities/{activity_id}", headers=auth(other)).status_code == 404
    assert client.get(f"/api/v1/activities/{activity_id}/streams", headers=auth(other)).status_code == 404
    assert client.get("/api/v1/activities", headers=auth(other)).json()["items"] == []


def test_get_streams_cuando_canales_y_max_points_entonces_reducido(client, synced):
    activity_id = client.get("/api/v1/activities?limit=1", headers=auth(synced)).json()["items"][0]["id"]
    res = client.get(
        f"/api/v1/activities/{activity_id}/streams?channels=time,hr&max_points=50", headers=auth(synced)
    ).json()
    assert set(res["channels"]) == {"time", "hr"}
    assert res["points"] == 30  # 60 muestras en tramos de 2
    assert all(len(v) == 30 for v in res["channels"].values())


def test_get_streams_cuando_sin_auth_entonces_401(client):
    assert client.get("/api/v1/activities/1/streams").status_code == 401


def test_garmin_status_cuando_sin_tokens_entonces_desconectado(client, user, monkeypatch):
    monkeypatch.setattr("app.api.garmin.has_tokens", lambda _uid: False)
    res = client.get("/api/v1/garmin/status", headers=auth(user)).json()
    assert res["connected"] is False and res["last_run"] is None
    assert res["connection"]["status"] == "none"


def test_garmin_status_cuando_hay_sync_entonces_devuelve_la_ultima(client, session, user, monkeypatch):
    monkeypatch.setattr("app.api.garmin.has_tokens", lambda _uid: True)
    session.add(SyncRun(user_id=user.id, status=SyncStatus.SUCCESS, new_activities=4))
    session.commit()
    res = client.get("/api/v1/garmin/status", headers=auth(user)).json()
    assert res["connected"] is True
    assert res["last_run"]["status"] == "success" and res["last_run"]["new_activities"] == 4


def test_garmin_sync_cuando_no_conectado_entonces_409(client, user, monkeypatch):
    monkeypatch.setattr("app.api.garmin.has_tokens", lambda _uid: False)
    res = client.post("/api/v1/garmin/sync", headers=auth(user))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"


def test_garmin_sync_cuando_conectado_entonces_encola_tarea(client, user, monkeypatch):
    queued = []
    monkeypatch.setattr("app.api.garmin.has_tokens", lambda _uid: True)
    monkeypatch.setattr("app.api.garmin.sync_user_task.delay", lambda uid: queued.append(uid))
    res = client.post("/api/v1/garmin/sync", headers=auth(user))
    assert res.status_code == 202
    assert queued == [user.id]


def test_metric_catalog_cuando_sembrado_entonces_lista_metricas(client, session, user):
    seed_catalog(session)
    keys = {m["key"] for m in client.get("/api/v1/metrics/catalog", headers=auth(user)).json()}
    assert {"hr", "avg_power", "hrv_last_night", "distance"} <= keys
