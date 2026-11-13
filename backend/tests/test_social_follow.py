"""Parte social: perfil, búsqueda, seguir (público y privado), solicitudes y seguidores."""

import pytest
from sqlmodel import select

from app.models import Follow
from tests.social_fixtures import add_activity, auth, befriend, make_user


@pytest.fixture
def ana(session):
    return make_user(session, "ana", "Ana García")


@pytest.fixture
def bea(session):
    return make_user(session, "bea", "Bea")


# ─── Perfil ──────────────────────────────────────────────────────────────────


def test_me_cuando_sin_perfil_entonces_null_y_contadores_a_cero(session, client):
    u = make_user(session, "nadie", profile=False)
    res = client.get("/api/v1/social/me", headers=auth(u))
    assert res.status_code == 200
    assert res.json() == {"profile": None, "counts": {"followers": 0, "following": 0, "pending_requests": 0}}


def test_put_me_cuando_datos_validos_entonces_crea_con_valores_por_defecto(session, client):
    u = make_user(session, "x", profile=False)
    body = {"display_name": " <b>Marta</b>\u0007 ", "handle": "@Marta.Run_1", "bio": "Corro <script>x</script>"}
    res = client.put("/api/v1/social/me", json=body, headers=auth(u))
    assert res.status_code == 200
    assert res.json() == {
        "user_id": u.id,
        "display_name": "Marta",
        "handle": "marta.run_1",
        "bio": "Corro x",
        "visibility": "private",
        "default_activity_visibility": "followers",
        "hide_map_ends_m": 300,
        "show_pace": True,
        "show_maps": True,
    }
    res = client.put(
        "/api/v1/social/me",
        json={"display_name": "Marta", "handle": "marta.run_1", "hide_map_ends_m": 0, "visibility": "public"},
        headers=auth(u),
    )
    assert res.json()["hide_map_ends_m"] == 0 and res.json()["visibility"] == "public"
    assert res.json()["bio"] == "Corro x"  # lo no enviado se conserva


def test_put_me_cuando_handle_de_otra_persona_entonces_409(session, client, ana):
    u = make_user(session, "x", profile=False)
    res = client.put("/api/v1/social/me", json={"display_name": "Otra", "handle": "ANA"}, headers=auth(u))
    assert res.status_code == 409 and res.json()["error"]["code"] == "HANDLE_TAKEN"


@pytest.mark.parametrize("handle", ["ab", "a" * 31, "con espacio", "eñe", "guion-medio"])
def test_put_me_cuando_handle_mal_formado_entonces_422(session, client, handle):
    u = make_user(session, "x", profile=False)
    res = client.put("/api/v1/social/me", json={"display_name": "X", "handle": handle}, headers=auth(u))
    assert res.status_code == 422


def test_put_me_cuando_nombre_vacio_o_valores_fuera_de_rango_entonces_422(session, client):
    u = make_user(session, "x", profile=False)
    for body in (
        {"display_name": "<i></i>", "handle": "xxx"},
        {"display_name": "X", "handle": "xxx", "hide_map_ends_m": 1001},
        {"display_name": "X", "handle": "xxx", "visibility": "todos"},
    ):
        assert client.put("/api/v1/social/me", json=body, headers=auth(u)).status_code == 422


# ─── Búsqueda y perfil ajeno ─────────────────────────────────────────────────


def test_search_cuando_nombre_o_arroba_entonces_encuentra_sin_incluirme(session, client, ana, bea):
    make_user(session, "sinperfil", profile=False)
    res = client.get("/api/v1/social/users/search?q=garc", headers=auth(bea))
    assert [p["handle"] for p in res.json()] == ["ana"]
    person = res.json()[0]
    assert person == {
        "user_id": ana.id,
        "display_name": "Ana García",
        "handle": "ana",
        "bio": "",
        "visibility": "private",
        "follow_status": "none",
        "follows_me": False,
        "blocked": False,
    }
    assert [p["handle"] for p in client.get("/api/v1/social/users/search?q=@be", headers=auth(ana)).json()] == ["bea"]
    assert client.get("/api/v1/social/users/search?q=@bea", headers=auth(bea)).json() == []  # a mí no
    assert client.get("/api/v1/social/users/search?q=sinperfil", headers=auth(ana)).json() == []
    assert client.get("/api/v1/social/users/search?q=%25", headers=auth(ana)).json() == []  # comodines escapados


def test_perfil_cuando_no_sigue_entonces_sin_actividades(session, client, ana, bea):
    add_activity(session, ana)
    res = client.get("/api/v1/social/users/@ana", headers=auth(bea))
    assert res.status_code == 200
    data = res.json()
    assert data["can_view"] is False and data["recent"] == []
    assert data["counts"] == {"followers": 0, "following": 0, "activities": 1}
    assert client.get("/api/v1/social/users/nadie", headers=auth(bea)).status_code == 404


def test_perfil_cuando_sigue_aceptado_entonces_ve_recientes(session, client, ana, bea):
    a = add_activity(session, ana)
    add_activity(session, ana, visibility="private")
    befriend(session, bea, ana)
    data = client.get("/api/v1/social/users/ana", headers=auth(bea)).json()
    assert data["can_view"] is True and [i["activity_id"] for i in data["recent"]] == [a.id]
    assert data["person"]["follow_status"] == "accepted"
    assert data["counts"]["followers"] == 1 and data["counts"]["activities"] == 1


# ─── Seguir ──────────────────────────────────────────────────────────────────


def test_follow_cuando_perfil_publico_entonces_aceptado_y_aviso(session, client, bea, pushes):
    pub = make_user(session, "pub", "Pública", public=True)
    res = client.post(f"/api/v1/social/follow/{pub.id}", headers=auth(bea))
    assert res.status_code == 200 and res.json() == {"status": "accepted"}
    assert pushes[0]["user_id"] == pub.id and "ha empezado a seguirte" in pushes[0]["body"]
    # Repetir no duplica.
    assert client.post(f"/api/v1/social/follow/{pub.id}", headers=auth(bea)).json() == {"status": "accepted"}
    assert len(session.exec(select(Follow)).all()) == 1


def test_follow_cuando_perfil_privado_entonces_pendiente_y_solicitud(session, client, ana, bea, pushes):
    res = client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea))
    assert res.json() == {"status": "pending"}
    assert pushes[0]["user_id"] == ana.id and "quiere seguirte" in pushes[0]["body"]
    reqs = client.get("/api/v1/social/requests", headers=auth(ana)).json()
    assert [p["handle"] for p in reqs] == ["bea"]
    assert client.get("/api/v1/social/me", headers=auth(ana)).json()["counts"]["pending_requests"] == 1


def test_follow_cuando_sin_perfil_propio_o_a_mi_mismo_entonces_error(session, client, ana):
    u = make_user(session, "x", profile=False)
    res = client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(u))
    assert res.status_code == 409 and res.json()["error"]["code"] == "PROFILE_REQUIRED"
    assert client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(ana)).status_code == 400
    assert client.post("/api/v1/social/follow/999999", headers=auth(ana)).status_code == 404


def test_aceptar_cuando_solicitud_pendiente_entonces_sigue_y_aviso(session, client, ana, bea, pushes):
    client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea))
    assert client.post(f"/api/v1/social/requests/{bea.id}/accept", headers=auth(ana)).status_code == 204
    assert pushes[-1]["user_id"] == bea.id and "ha aceptado" in pushes[-1]["body"]
    following = client.get("/api/v1/social/following", headers=auth(bea)).json()
    assert [p["handle"] for p in following] == ["ana"] and following[0]["follow_status"] == "accepted"
    followers = client.get("/api/v1/social/followers", headers=auth(ana)).json()
    assert [p["handle"] for p in followers] == ["bea"] and followers[0]["follows_me"] is True
    assert client.post(f"/api/v1/social/requests/{bea.id}/accept", headers=auth(ana)).status_code == 404


def test_rechazar_cuando_solicitud_pendiente_entonces_desaparece(session, client, ana, bea):
    client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea))
    assert client.post(f"/api/v1/social/requests/{bea.id}/reject", headers=auth(ana)).status_code == 204
    assert session.exec(select(Follow)).all() == []
    assert client.post(f"/api/v1/social/requests/{bea.id}/reject", headers=auth(ana)).status_code == 404


def test_dejar_de_seguir_cuando_aceptado_o_pendiente_entonces_borra(session, client, ana, bea):
    befriend(session, bea, ana)
    assert client.delete(f"/api/v1/social/follow/{ana.id}", headers=auth(bea)).status_code == 204
    assert session.exec(select(Follow)).all() == []
    client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea))  # solicitud
    assert client.delete(f"/api/v1/social/follow/{ana.id}", headers=auth(bea)).status_code == 204  # cancelar
    assert session.exec(select(Follow)).all() == []


def test_quitar_seguidor_cuando_me_sigue_entonces_deja_de_ver(session, client, ana, bea):
    a = add_activity(session, ana)
    befriend(session, bea, ana)
    assert client.delete(f"/api/v1/social/followers/{bea.id}", headers=auth(ana)).status_code == 204
    assert client.get(f"/api/v1/social/activities/{a.id}/kudos", headers=auth(bea)).status_code == 404


def test_hacerse_publico_cuando_hay_pendientes_entonces_se_aceptan(session, client, ana, bea):
    client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea))
    client.put(
        "/api/v1/social/me", json={"display_name": "Ana", "handle": "ana", "visibility": "public"}, headers=auth(ana)
    )
    session.expire_all()
    assert session.exec(select(Follow.status)).all() == ["accepted"]
