"""Parte social: feed paginado (sin N+1), kudos y comentarios."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.core.db import engine
from app.models import Achievement
from app.services import social
from tests.social_fixtures import add_activity, add_track, auth, befriend, make_user, straight_track


@pytest.fixture
def ana(session):
    return make_user(session, "ana", "Ana")


@pytest.fixture
def bea(session):
    return make_user(session, "bea", "Bea")


# ─── Feed ────────────────────────────────────────────────────────────────────


def test_feed_cuando_mias_y_de_seguidos_entonces_ordenado_y_paginado(session, client, ana, bea):
    befriend(session, bea, ana)
    now = datetime.now(UTC)
    mine = add_activity(session, bea, start=now - timedelta(hours=1))
    theirs = [add_activity(session, ana, start=now - timedelta(hours=h)) for h in (2, 3, 4)]
    res = client.get("/api/v1/social/feed?limit=2", headers=auth(bea)).json()
    assert [i["activity_id"] for i in res["items"]] == [mine.id, theirs[0].id]
    assert res["items"][0]["mine"] is True and res["items"][1]["mine"] is False
    assert res["next_before"] is not None
    res2 = client.get(
        "/api/v1/social/feed", params={"limit": 2, "before": res["next_before"]}, headers=auth(bea)
    ).json()
    assert [i["activity_id"] for i in res2["items"]] == [theirs[1].id, theirs[2].id]
    assert res2["next_before"] is None


def test_feed_cuando_item_entonces_campos_del_contrato(session, client, ana, bea):
    befriend(session, bea, ana)
    a = add_activity(
        session, ana, distance_m=10_000, duration_s=3_000, moving_duration_s=2_500, elevation_gain_m=120, is_race=True
    )
    session.add(
        Achievement(
            user_id=ana.id,
            key="pr10k",
            kind="record",
            title="Mejor 10K",
            achieved_on=a.start_time.date(),
            activity_id=a.id,
        )
    )
    session.commit()
    item = client.get("/api/v1/social/feed", headers=auth(bea)).json()["items"][0]
    assert item["avg_speed"] == 4.0 and item["is_race"] is True and item["elevation_gain_m"] == 120
    assert item["achievements"] == [{"title": "Mejor 10K", "kind": "record"}]
    assert item["owner"] == {"user_id": ana.id, "display_name": "Ana", "handle": "ana"}
    assert item["visibility"] == "followers" and item["track"] is None


def test_feed_cuando_sin_perfil_entonces_vacio(session, client):
    u = make_user(session, "x", profile=False)
    add_activity(session, u)
    assert client.get("/api/v1/social/feed", headers=auth(u)).json() == {"items": [], "next_before": None}


def _count_queries(fn) -> list[str]:
    statements: list[str] = []

    def before(_conn, _cursor, statement, *_args, **_kwargs):
        statements.append(" ".join(statement.split())[:150])

    event.listen(engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return statements


def test_feed_cuando_50_actividades_entonces_mismas_consultas_que_con_pocas(session, client, ana, bea):
    """Sin N+1: el número de consultas no depende de cuántas actividades haya en la página."""
    befriend(session, bea, ana)
    now = datetime.now(UTC)
    for h in range(2):
        a = add_activity(session, ana, start=now - timedelta(hours=h + 1))
        add_track(session, a, *straight_track(2000))
    headers = auth(bea)  # fuera del recuento: leer `bea` caducado también consulta la BD
    client.get("/api/v1/social/feed?limit=50", headers=headers)  # calienta cachés (módulos, claves)
    few = _count_queries(lambda: client.get("/api/v1/social/feed?limit=50", headers=headers))
    carla = make_user(session, "carla")
    befriend(session, bea, carla)
    for h in range(48):
        a = add_activity(session, carla if h % 2 else ana, start=now - timedelta(hours=h + 3))
        add_track(session, a, *straight_track(2000))
        social.give_kudos(session, bea.id, a.id)
        social.add_comment(session, bea.id, a.id, "¡Vamos!")
    res = None

    def call():
        nonlocal res
        res = client.get("/api/v1/social/feed?limit=50", headers=headers)

    many = _count_queries(call)
    assert len(res.json()["items"]) == 50
    assert len(many) == len(few), "\n".join([s[:70] for s in few] + ["---"] + [s[:70] for s in many])
    assert len(many) <= 15


# ─── Kudos ───────────────────────────────────────────────────────────────────


def test_kudos_cuando_doble_entonces_idempotente_y_quitar(session, client, ana, bea, pushes):
    a = add_activity(session, ana, name="Series")
    befriend(session, bea, ana)
    url = f"/api/v1/social/activities/{a.id}/kudos"
    assert client.post(url, headers=auth(bea)).json() == {"kudos_count": 1, "kudoed_by_me": True}
    assert client.post(url, headers=auth(bea)).json() == {"kudos_count": 1, "kudoed_by_me": True}
    assert [p["user_id"] for p in pushes] == [ana.id] and "«Series»" in pushes[0]["body"]
    assert client.get(url, headers=auth(ana)).json() == [{"user_id": bea.id, "display_name": "Bea", "handle": "bea"}]
    assert client.delete(url, headers=auth(bea)).json() == {"kudos_count": 0, "kudoed_by_me": False}
    assert client.delete(url, headers=auth(bea)).json() == {"kudos_count": 0, "kudoed_by_me": False}


def test_kudos_cuando_propia_entonces_400(session, client, ana):
    a = add_activity(session, ana)
    res = client.post(f"/api/v1/social/activities/{a.id}/kudos", headers=auth(ana))
    assert res.status_code == 400 and res.json()["error"]["code"] == "OWN_ACTIVITY"


def test_kudos_cuando_varios_en_10_min_entonces_un_solo_aviso(session, client, ana, bea, pushes, monkeypatch):
    monkeypatch.setattr(social, "_bucket", lambda: 1)  # mismo tramo de 10 minutos
    a = add_activity(session, ana)
    carla = make_user(session, "carla")
    befriend(session, bea, ana)
    befriend(session, carla, ana)
    client.post(f"/api/v1/social/activities/{a.id}/kudos", headers=auth(bea))
    client.post(f"/api/v1/social/activities/{a.id}/kudos", headers=auth(carla))
    assert len(pushes) == 1  # agrupado: mismo tramo de 10 minutos


# ─── Comentarios ─────────────────────────────────────────────────────────────


def test_comentario_cuando_html_y_control_entonces_saneado(session, client, ana, bea, pushes):
    a = add_activity(session, ana)
    befriend(session, bea, ana)
    body = {"body": "<script>alert(1)</script>¡Qué  <b>crack</b>!\u0000‮\n\n\n\nSigue así 💪"}
    res = client.post(f"/api/v1/social/activities/{a.id}/comments", json=body, headers=auth(bea))
    assert res.status_code == 200
    data = res.json()
    assert data["body"] == "alert(1)¡Qué crack!\n\nSigue así 💪"
    assert data["author"]["handle"] == "bea" and data["can_delete"] is True
    assert pushes[0]["user_id"] == ana.id
    listed = client.get(f"/api/v1/social/activities/{a.id}/comments", headers=auth(ana)).json()
    assert len(listed) == 1 and listed[0]["can_delete"] is True  # el dueño también puede borrar
    feed = client.get("/api/v1/social/feed", headers=auth(ana)).json()
    assert feed["items"][0]["comments_count"] == 1


def test_comentario_cuando_vacio_tras_sanear_o_largo_entonces_422(session, client, ana, bea):
    a = add_activity(session, ana)
    befriend(session, bea, ana)
    url = f"/api/v1/social/activities/{a.id}/comments"
    assert client.post(url, json={"body": "<b></b>  "}, headers=auth(bea)).status_code == 422
    res = client.post(url, json={"body": "x" * 600}, headers=auth(bea))
    assert res.status_code == 200 and len(res.json()["body"]) == 500


def test_comentario_cuando_varios_en_10_min_entonces_un_aviso(session, client, ana, bea, pushes, monkeypatch):
    monkeypatch.setattr(social, "_bucket", lambda: 1)
    a = add_activity(session, ana)
    befriend(session, bea, ana)
    for text in ("uno", "dos", "tres"):
        client.post(f"/api/v1/social/activities/{a.id}/comments", json={"body": text}, headers=auth(bea))
    assert len(pushes) == 1


def test_borrar_comentario_cuando_autor_o_dueno_entonces_si_y_tercero_no(session, client, ana, bea):
    a = add_activity(session, ana)
    carla = make_user(session, "carla")
    for u in (bea, carla):
        befriend(session, u, ana)
    url = f"/api/v1/social/activities/{a.id}/comments"
    c1 = client.post(url, json={"body": "de Bea"}, headers=auth(bea)).json()["id"]
    c2 = client.post(url, json={"body": "otro de Bea"}, headers=auth(bea)).json()["id"]
    listed = client.get(url, headers=auth(carla)).json()
    assert [c["can_delete"] for c in listed] == [False, False]
    assert client.delete(f"/api/v1/social/comments/{c1}", headers=auth(carla)).status_code == 403
    assert client.delete(f"/api/v1/social/comments/{c1}", headers=auth(bea)).status_code == 204  # autora
    assert client.delete(f"/api/v1/social/comments/{c2}", headers=auth(ana)).status_code == 204  # dueña
    assert client.get(url, headers=auth(ana)).json() == []
    assert client.delete(f"/api/v1/social/comments/{c1}", headers=auth(bea)).status_code == 404


def test_comentar_cuando_no_puede_ver_entonces_404(session, client, ana, bea):
    a = add_activity(session, ana)
    res = client.post(f"/api/v1/social/activities/{a.id}/comments", json={"body": "hola"}, headers=auth(bea))
    assert res.status_code == 404
