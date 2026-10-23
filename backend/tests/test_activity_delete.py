from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, ActivityStream, DeletedActivity, Lap, PlannedSession, User
from app.services.activity_delete import delete_activities
from app.services.file_import import ImportedActivity, save_imported
from app.services.sync_service import sync_activities
from tests.fakes import FakeGarmin, MemoryStorage

START = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _imported(session: Session, user: User, minutes: int = 0, source: str = "coros", ext: str = "L1") -> Activity:
    act = ImportedActivity(sport="running", start_time=START + timedelta(minutes=minutes), duration_s=1800,
                           streams={"time": [0.0, 1.0], "hr": [140.0, 141.0]},
                           laps=[{"index": 0, "start_offset_s": 0, "duration_s": 1800, "distance_m": 5000,
                                  "avg_hr": 140, "max_hr": 150, "avg_speed": 2.8, "metrics": {}}])  # fmt: skip
    activity, _ = save_imported(session, user.id, act, source, ext)
    return activity


def test_borrar_una_por_api(client, user, session):
    a = _imported(session, user)
    h = auth(user)
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.delete(f"/api/v1/activities/{a.id}", headers=auth(other)).status_code == 404
    assert client.delete(f"/api/v1/activities/{a.id}", headers=h).status_code == 204
    assert client.get(f"/api/v1/activities/{a.id}", headers=h).status_code == 404
    assert session.exec(select(Lap).where(Lap.activity_id == a.id)).all() == []
    assert session.exec(select(ActivityStream).where(ActivityStream.activity_id == a.id)).all() == []
    mark = session.exec(select(DeletedActivity)).one()
    assert (mark.source, mark.external_key, mark.start_time) == ("coros", "L1", START)


def test_borrar_varias_solo_las_propias(client, user, session):
    mine = [_imported(session, user, m, ext=f"L{m}") for m in (0, 60, 120)]
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    theirs, _ = save_imported(session, other.id, ImportedActivity(sport="running", start_time=START, duration_s=60),
                              "fit")  # fmt: skip
    res = client.post("/api/v1/activities/delete", json={"ids": [mine[0].id, mine[1].id, theirs.id, 999999]},
                      headers=auth(user))  # fmt: skip
    assert res.json() == {"deleted": 2}
    assert session.get(Activity, mine[2].id) is not None and session.get(Activity, theirs.id) is not None
    assert client.post("/api/v1/activities/delete", json={"ids": []}, headers=auth(user)).status_code == 422


def test_no_vuelve_con_la_importacion_salvo_subirla_a_mano(session: Session, user: User):
    a = _imported(session, user)
    delete_activities(session, user.id, [a.id])
    again = ImportedActivity(sport="running", start_time=START + timedelta(seconds=30), duration_s=1800)
    # Llega de otra fuente (p. ej. Health Connect) a la misma hora: tampoco se crea.
    assert save_imported(session, user.id, again, "health_connect", "x") == (None, False)
    assert save_imported(session, user.id, again, "coros", "L1") == (None, False)
    # Subir el fichero a mano es querer recuperarla: se crea y se quita la marca.
    restored, created = save_imported(session, user.id, again, "fit", respect_deleted=False)
    assert created and restored is not None
    assert session.exec(select(DeletedActivity)).all() == []


def test_garmin_no_la_vuelve_a_traer(session: Session, user: User):
    storage = MemoryStorage()
    assert sync_activities(session, user.id, FakeGarmin(3), storage) == 3
    first = session.exec(select(Activity).where(Activity.user_id == user.id).order_by(Activity.start_time)).first()
    delete_activities(session, user.id, [first.id])
    assert sync_activities(session, user.id, FakeGarmin(3), storage) == 0
    assert len(session.exec(select(Activity).where(Activity.user_id == user.id)).all()) == 2


def test_la_sesion_del_plan_se_queda_sin_actividad(session: Session, user: User):
    a = _imported(session, user)
    planned = PlannedSession(user_id=user.id, day=date(2026, 10, 20), sport="running", title="Rodaje",
                             activity_id=a.id, compliance_score=90)  # fmt: skip
    session.add(planned)
    session.commit()
    delete_activities(session, user.id, [a.id])
    session.refresh(planned)
    assert planned.activity_id is None and planned.compliance_score is None
