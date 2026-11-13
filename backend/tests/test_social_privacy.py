"""Parte social: permisos, recorte del mapa, datos que nunca salen, módulo, migración y RGPD."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import select

from app.models import Activity, ActivityComment, Block, Duel, Follow, Kudos, SocialProfile, User
from app.services import accounts, modules, social
from tests.social_fixtures import (
    add_activity,
    add_track,
    auth,
    befriend,
    distance_from_start,
    make_user,
    straight_track,
)


@pytest.fixture
def ana(session):
    return make_user(session, "ana", "Ana")


@pytest.fixture
def bea(session):
    return make_user(session, "bea", "Bea")


def _feed_ids(client, user) -> list[int]:
    res = client.get("/api/v1/social/feed", headers=auth(user))
    assert res.status_code == 200
    return [i["activity_id"] for i in res.json()["items"]]


# ─── Quién ve qué ────────────────────────────────────────────────────────────


def test_can_view_cuando_no_sigue_entonces_no_ve(session, client, ana, bea):
    a = add_activity(session, ana)
    assert not social.can_view(session, bea.id, a)
    assert _feed_ids(client, bea) == []
    assert client.get(f"/api/v1/social/activities/{a.id}/comments", headers=auth(bea)).status_code == 404


def test_can_view_cuando_solicitud_pendiente_entonces_no_ve(session, client, ana, bea):
    a = add_activity(session, ana)
    befriend(session, bea, ana, status="pending")
    assert not social.can_view(session, bea.id, a)
    assert _feed_ids(client, bea) == []


def test_can_view_cuando_seguidor_aceptado_entonces_ve_followers(session, client, ana, bea):
    a = add_activity(session, ana)
    befriend(session, bea, ana)
    assert a.visibility == "followers"  # la del perfil de Ana
    assert social.can_view(session, bea.id, a)
    assert _feed_ids(client, bea) == [a.id]


def test_can_view_cuando_solo_yo_entonces_oculta_a_seguidores(session, client, ana, bea):
    a = add_activity(session, ana, visibility="private")
    befriend(session, bea, ana)
    assert not social.can_view(session, bea.id, a)
    assert _feed_ids(client, bea) == []
    assert _feed_ids(client, ana) == [a.id]  # el dueño sí la ve
    assert client.post(f"/api/v1/social/activities/{a.id}/kudos", headers=auth(bea)).status_code == 404


def test_bloqueo_cuando_cualquier_sentido_entonces_corta_todo(session, client, ana, bea):
    a = add_activity(session, ana)
    befriend(session, bea, ana)
    befriend(session, ana, bea)
    assert client.post(f"/api/v1/social/block/{bea.id}", headers=auth(ana)).status_code == 204
    # Se cortan los seguimientos en los dos sentidos y nadie ve a nadie.
    assert session.exec(select(Follow)).all() == []
    assert not social.can_view(session, bea.id, a)
    assert _feed_ids(client, bea) == []
    assert client.get("/api/v1/social/users/search?q=ana", headers=auth(bea)).json() == []
    assert client.get("/api/v1/social/users/search?q=bea", headers=auth(ana)).json() == []
    assert client.get("/api/v1/social/users/ana", headers=auth(bea)).status_code == 404
    assert client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea)).status_code == 404
    board = client.get("/api/v1/social/leaderboard", headers=auth(bea)).json()
    assert [r["user_id"] for r in board["rows"]] == [bea.id]
    blocked = client.get("/api/v1/social/blocked", headers=auth(ana)).json()
    assert [p["handle"] for p in blocked] == ["bea"] and blocked[0]["blocked"] is True
    # Desbloquear no devuelve el seguimiento.
    assert client.delete(f"/api/v1/social/block/{bea.id}", headers=auth(ana)).status_code == 204
    assert client.get("/api/v1/social/users/ana", headers=auth(bea)).status_code == 200
    assert _feed_ids(client, bea) == []


def test_bloqueo_cuando_hay_duelo_entonces_se_cancela(session, client, ana, bea):
    duel = Duel(
        challenger_id=ana.id,
        opponent_id=bea.id,
        metric="km",
        start_date=datetime.now(UTC).date(),
        end_date=datetime.now(UTC).date() + timedelta(days=6),
        status="active",
    )
    session.add(duel)
    session.commit()
    client.post(f"/api/v1/social/block/{ana.id}", headers=auth(bea))
    session.refresh(duel)
    assert duel.status == "cancelled"


def test_feed_y_perfil_cuando_otra_persona_entonces_nunca_fc_salud_ni_email(session, client, ana, bea):
    a = add_activity(
        session, ana, avg_hr=151.25, max_hr=183.75, calories=4321.5, metrics={"trimp": 90, "best_5k": 1300}
    )
    lats, lons = straight_track(3000)
    add_track(session, a, lats, lons)
    befriend(session, bea, ana)
    feed = client.get("/api/v1/social/feed", headers=auth(bea)).text
    page = client.get("/api/v1/social/users/ana", headers=auth(bea)).text
    people = client.get("/api/v1/social/users/search?q=an", headers=auth(bea)).text
    for body in (feed, page, people):
        for forbidden in (
            "avg_hr",
            "max_hr",
            "151.25",
            "183.75",
            "4321.5",
            "calories",
            "trimp",
            "metrics",
            "email",
            "@example.com",
            "hr_zones",
            "notes",
            "feedback",
            "review",
        ):
            assert forbidden not in body, forbidden
    item = json.loads(feed)["items"][0]
    assert set(item) == {
        "activity_id",
        "owner",
        "sport",
        "name",
        "start_time",
        "distance_m",
        "duration_s",
        "moving_duration_s",
        "avg_speed",
        "elevation_gain_m",
        "is_race",
        "track",
        "achievements",
        "kudos_count",
        "kudoed_by_me",
        "comments_count",
        "mine",
        "visibility",
    }
    assert set(item["owner"]) == {"user_id", "display_name", "handle"}


def test_feed_cuando_dueno_oculta_ritmo_y_mapas_entonces_null(session, client, bea):
    ana = make_user(session, "ana", show_pace=False, show_maps=False)
    a = add_activity(session, ana)
    add_track(session, a, *straight_track(3000))
    befriend(session, bea, ana)
    item = client.get("/api/v1/social/feed", headers=auth(bea)).json()["items"][0]
    assert item["avg_speed"] is None and item["track"] is None
    assert item["distance_m"] == 10_000


# ─── Mapa ────────────────────────────────────────────────────────────────────


def test_trim_track_cuando_300_m_entonces_quita_extremos_y_maximo_150_puntos():
    lats, lons = straight_track(5000, step_m=5)  # 1001 puntos
    track = social.trim_track(lats, lons, 300)
    assert track is not None and 2 <= len(track) <= 150
    first, last = distance_from_start(track[0][0]), distance_from_start(track[-1][0])
    assert first >= 299 and last <= 5000 - 299
    assert first < 320 and last > 5000 - 320  # no recorta de más


def test_trim_track_cuando_ruta_corta_o_sin_gps_entonces_none():
    assert social.trim_track(*straight_track(500), 300) is None  # todo cae en la zona oculta
    assert social.trim_track([], [], 300) is None
    assert social.trim_track([None, None], [None, None], 0) is None


def test_trim_track_cuando_cero_entonces_traza_entera_simplificada():
    lats, lons = straight_track(1000)
    track = social.trim_track(lats, lons, 0)
    assert track[0] == [round(lats[0], 5), -3.0] and track[-1] == [round(lats[-1], 5), -3.0]


def test_feed_cuando_hay_gps_entonces_traza_recortada(session, client, ana, bea):
    a = add_activity(session, ana)
    add_track(session, a, *straight_track(3000))
    befriend(session, bea, ana)
    track = client.get("/api/v1/social/feed", headers=auth(bea)).json()["items"][0]["track"]
    assert distance_from_start(track[0][0]) >= 299 and distance_from_start(track[-1][0]) <= 2701


# ─── Visibilidad de actividades ──────────────────────────────────────────────


def test_visibilidad_cuando_sin_perfil_entonces_nueva_actividad_privada(session):
    u = make_user(session, "solo", profile=False)
    assert add_activity(session, u).visibility == "private"


def test_visibilidad_cuando_perfil_entonces_toma_la_de_por_defecto(session):
    u = make_user(session, "rosa", default_visibility="private")
    assert add_activity(session, u).visibility == "private"
    v = make_user(session, "vera", default_visibility="followers")
    assert add_activity(session, v).visibility == "followers"


def test_put_visibility_cuando_dueno_entonces_cambia_y_otro_404(session, client, ana, bea):
    a = add_activity(session, ana)
    res = client.put(f"/api/v1/activities/{a.id}/visibility", json={"visibility": "private"}, headers=auth(ana))
    assert res.status_code == 200 and res.json() == {"visibility": "private"}
    res = client.put(f"/api/v1/activities/{a.id}/visibility", json={"visibility": "followers"}, headers=auth(bea))
    assert res.status_code == 404
    res = client.put(f"/api/v1/activities/{a.id}/visibility", json={"visibility": "todos"}, headers=auth(ana))
    assert res.status_code == 422
    assert client.get(f"/api/v1/activities/{a.id}", headers=auth(ana)).json()["visibility"] == "private"


def test_share_history_cuando_activa_entonces_historial_pasa_a_por_defecto(session, client):
    u = make_user(session, "luis", profile=False)
    old = [add_activity(session, u, start=datetime.now(UTC) - timedelta(days=d)) for d in (3, 40)]
    assert all(a.visibility == "private" for a in old)
    body = {"display_name": "Luis", "handle": "luis"}
    assert client.put("/api/v1/social/me", json=body, headers=auth(u)).status_code == 200
    for a in old:
        session.refresh(a)
        assert a.visibility == "private"  # sin share_history no cambia
    res = client.put("/api/v1/social/me", json={**body, "share_history": True}, headers=auth(u))
    assert res.status_code == 200
    for a in old:
        session.refresh(a)
        assert a.visibility == "followers"


# ─── Módulo ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/social/me"),
        ("get", "/api/v1/social/feed"),
        ("get", "/api/v1/social/leaderboard"),
        ("get", "/api/v1/social/duels"),
        ("get", "/api/v1/social/summary"),
        ("post", "/api/v1/social/follow/1"),
        ("put", "/api/v1/activities/1/visibility"),
    ],
)
def test_social_cuando_modulo_apagado_entonces_404(session, client, ana, method, path):
    modules.set_modules(session, {"social": False}, None)
    res = getattr(client, method)(
        path, headers=auth(ana), **({"json": {"visibility": "private"}} if method == "put" else {})
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "MODULE_DISABLED"


def test_social_cuando_sin_sesion_entonces_401(client):
    assert client.get("/api/v1/social/feed").status_code == 401


def test_aviso_cuando_modulo_apagado_para_la_persona_entonces_no_se_envia(session, client, ana, bea, pushes):
    ana.module_overrides = {"social": False}
    session.add(ana)
    session.commit()
    client.post(f"/api/v1/social/follow/{ana.id}", headers=auth(bea))
    assert pushes == []


# ─── RGPD ────────────────────────────────────────────────────────────────────


def _social_world(session, ana, bea) -> Activity:
    a = add_activity(session, ana)
    b = add_activity(session, bea)
    befriend(session, bea, ana)
    befriend(session, ana, bea)
    session.add(Kudos(activity_id=b.id, user_id=ana.id))
    session.add(Kudos(activity_id=a.id, user_id=bea.id))
    session.add(ActivityComment(activity_id=b.id, author_id=ana.id, body="¡Bien!"))
    session.add(ActivityComment(activity_id=a.id, author_id=bea.id, body="Gracias"))
    session.add(Block(blocker_id=ana.id, blocked_id=make_user(session, "troll").id))
    session.add(
        Duel(
            challenger_id=ana.id,
            opponent_id=bea.id,
            metric="km",
            start_date=datetime.now(UTC).date(),
            end_date=datetime.now(UTC).date(),
            status="active",
            last_leader_id=ana.id,
        )
    )
    session.commit()
    return b


def test_exportacion_cuando_tiene_datos_sociales_entonces_los_incluye(session, ana, bea):
    _social_world(session, ana, bea)
    data = accounts.export_user_data(session, ana)
    assert data["social_profile"][0]["handle"] == "ana"
    assert len(data["follows"]) == 2 and len(data["blocks"]) == 1 and len(data["duels"]) == 1
    assert [k["user_id"] for k in data["kudos_given"]] == [ana.id]
    assert [c["body"] for c in data["comments_written"]] == ["¡Bien!"]
    assert "bea@example.com" not in json.dumps(data)


def test_borrado_cuando_borra_cuenta_entonces_desaparece_lo_social(session, ana, bea):
    b = _social_world(session, ana, bea)
    accounts.delete_user(session, ana)
    session.expire_all()
    assert session.get(SocialProfile, ana.id) is None
    assert session.exec(select(Follow)).all() == []
    assert session.exec(select(Duel)).all() == []
    assert session.exec(select(Block)).all() == []
    # Lo de Ana en la actividad de Bea se va; la actividad de Bea sigue.
    assert session.exec(select(Kudos)).all() == []
    assert session.exec(select(ActivityComment)).all() == []
    assert session.get(Activity, b.id) is not None and session.get(User, bea.id) is not None


# ─── Migración ───────────────────────────────────────────────────────────────

REVISION = "a1c5e9d3b7f2"
PREVIOUS = "a9d4f6b2c8e1"


def test_migracion_cuando_hay_actividades_antiguas_entonces_quedan_privadas(monkeypatch):
    """Base de datos aparte: se migra hasta la revisión anterior, se crean datos y se aplica la nueva."""
    import app.core.db as db

    url = make_url(str(db.engine.url.render_as_string(hide_password=False)))
    mig_url = url.set(database=f"{url.database}_mig")
    with create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT").connect() as admin:
        admin.execute(text(f'DROP DATABASE IF EXISTS "{mig_url.database}"'))
        admin.execute(text(f'CREATE DATABASE "{mig_url.database}"'))
    engine = create_engine(mig_url)
    monkeypatch.setattr(db, "engine", engine)  # alembic/env.py usa app.core.db.engine
    cfg = Config()
    cfg.set_main_option("script_location", "alembic")
    try:
        command.upgrade(cfg, PREVIOUS)
        with engine.begin() as conn:
            uid = conn.execute(
                text("INSERT INTO \"user\" (email, password_hash) VALUES ('m@example.com', 'x') RETURNING id")
            ).scalar()
            conn.execute(
                text(
                    "INSERT INTO activity (user_id, sport, name, start_time, duration_s, metrics, updated_at) "
                    "VALUES (:u, 'running', 'Antigua', now(), 60, '{}', now())"
                ),
                {"u": uid},
            )
        command.upgrade(cfg, REVISION)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT visibility FROM activity")).scalars().all() == ["private"]
            assert conn.execute(text("SELECT social FROM notification_prefs")).all() == []
        command.downgrade(cfg, PREVIOUS)
        with engine.connect() as conn:
            cols = (
                conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'activity'"))
                .scalars()
                .all()
            )
            assert "visibility" not in cols
            assert conn.execute(text("SELECT to_regclass('duel')")).scalar() is None
        command.upgrade(cfg, REVISION)
    finally:
        engine.dispose()
        with create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT").connect() as admin:
            admin.execute(text(f'DROP DATABASE IF EXISTS "{mig_url.database}"'))
