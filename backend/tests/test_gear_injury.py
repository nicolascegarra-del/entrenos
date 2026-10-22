from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, Gear, User
from app.services import gear as gear_svc
from app.services import injury


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _run(session: Session, user: User, days_ago: int, km: float, sport: str = "running") -> Activity:
    a = Activity(user_id=user.id, sport=sport, start_time=datetime.now(UTC) - timedelta(days=days_ago),
                 duration_s=km * 360, distance_m=km * 1000, avg_hr=150)  # fmt: skip
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# ─── Zapatillas ──────────────────────────────────────────────────────────────


def test_alta_por_defecto_asigna_carreras_desde_su_primer_uso(client, user, session):
    old = _run(session, user, 30, 10)
    recent = _run(session, user, 3, 8)
    bike = _run(session, user, 2, 30, sport="cycling")
    body = {"name": "Pegasus", "start_km": 120, "alert_km": 700, "is_default": True,
            "first_use": (date.today() - timedelta(days=10)).isoformat()}  # fmt: skip
    rows = client.post("/api/v1/gear", json=body, headers=auth(user)).json()
    assert rows[0]["total_km"] == 128 and rows[0]["status"] == "ok" and rows[0]["is_default"]
    session.expire_all()
    assert session.get(Activity, recent.id).gear_id == rows[0]["id"]
    assert session.get(Activity, old.id).gear_id is None and session.get(Activity, bike.id).gear_id is None


def test_estado_de_las_zapatillas():
    assert gear_svc.gear_status(600, 700) == "ok"
    assert gear_svc.gear_status(660, 700) == "soon"
    assert gear_svc.gear_status(705, 700) == "replace"


def test_solo_una_por_defecto_y_retirar(client, user):
    a = client.post("/api/v1/gear", json={"name": "A", "is_default": True}, headers=auth(user)).json()
    gid_a = a[0]["id"]
    rows = client.post("/api/v1/gear", json={"name": "B", "is_default": True}, headers=auth(user)).json()
    defaults = [r for r in rows if r["is_default"]]
    assert len(defaults) == 1 and defaults[0]["name"] == "B"
    rows = client.put(f"/api/v1/gear/{gid_a}", json={"name": "A", "retired": True}, headers=auth(user)).json()
    retired = next(r for r in rows if r["id"] == gid_a)
    assert retired["status"] == "retired"


def test_cambiar_zapatillas_de_una_actividad_y_permisos(client, user, session):
    act = _run(session, user, 1, 5)
    gid = client.post("/api/v1/gear", json={"name": "A"}, headers=auth(user)).json()[0]["id"]
    res = client.put(f"/api/v1/activities/{act.id}/gear", json={"gear_id": gid}, headers=auth(user))
    assert res.json() == {"activity_id": act.id, "gear_id": gid}
    other = User(email="otro@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.put(f"/api/v1/activities/{act.id}/gear", json={"gear_id": None},
                      headers=auth(other)).status_code == 404  # fmt: skip
    assert client.put(f"/api/v1/gear/{gid}", json={"name": "x"}, headers=auth(other)).status_code == 404


def test_importar_material_de_garmin(session, user):
    act = _run(session, user, 2, 10)
    act.garmin_activity_id = 555
    session.add(act)
    session.commit()

    class Api:
        def get_gear(self, profile):
            return [{"uuid": "u1", "gearTypeName": "Shoes", "displayName": "Novablast", "maximumMeters": 800000,
                     "gearStatusName": "active"}, {"uuid": "u2", "gearTypeName": "Bike"}]  # fmt: skip

        def get_gear_activities(self, uuid):
            return [{"activityId": 555}]

    assert gear_svc.import_garmin_gear(session, user.id, Api(), "1") == 1
    shoe = session.exec(select(Gear)).one()
    assert shoe.name == "Novablast" and shoe.alert_km == 800
    session.refresh(act)
    assert act.gear_id == shoe.id
    assert gear_svc.import_garmin_gear(session, user.id, Api(), "1") == 0  # no duplica


def test_importar_material_cuando_garmin_falla_no_rompe(session, user):
    class Api:
        def get_gear(self, profile):
            raise RuntimeError("Garmin caído")

    assert gear_svc.import_garmin_gear(session, user.id, Api(), "1") == 0


# ─── Avisos de lesión ────────────────────────────────────────────────────────


VOLUME_CASES = [(22, [20, 20, 20], "good"), (24, [20, 20, 20], "watch"), (30, [20, 20, 20], "alert"),
                (10, [0, 0, 0], "good"), (12, [20, 20, 20], "good")]  # fmt: skip


@pytest.mark.parametrize(("last7", "prev", "status"), VOLUME_CASES)
def test_subida_de_volumen(last7, prev, status):
    assert injury.volume_jump(last7, prev).status == status


def test_monotonia_de_foster():
    assert injury.monotony([50, 52, 48, 51, 50, 49, 50]).status == "watch"  # todos los días igual
    assert injury.monotony([90, 0, 40, 0, 100, 0, 30]).status == "good"


def test_tirada_larga_y_acwr():
    assert injury.long_run_share(12, 20).status == "watch"
    assert injury.long_run_share(6, 20).status == "good"
    assert injury.acwr_check(1.6).status == "alert" and injury.acwr_check(None).status == "good"


def test_zapatillas_en_el_informe(client, user, session):
    session.add(Gear(user_id=user.id, name="Vieja", start_km=750, alert_km=700))
    session.commit()
    data = client.get("/api/v1/progress/injury-risk", headers=auth(user)).json()
    shoes = next(c for c in data["checks"] if c["key"] == "shoes")
    assert shoes["status"] == "alert" and "Vieja" in shoes["message"] and data["status"] == "alert"
    assert "," in shoes["message"] or "750" in shoes["message"]


def test_informe_sin_datos(client, user):
    data = client.get("/api/v1/progress/injury-risk", headers=auth(user)).json()
    assert data["status"] == "good" and len(data["checks"]) == 5
