from sqlmodel import Session, select

from app.models import Activity, ActivityRaw, ActivityStream, DailyMetric, Device, Lap, SyncStatus
from app.services import garmin_parser
from app.services.sync_service import reprocess_activities, run_sync, sync_activities
from tests.fakes import FakeGarmin, MemoryStorage


def test_sync_activities_cuando_bd_vacia_entonces_importa_todo_con_raw_streams_y_vueltas(session, user):
    storage = MemoryStorage()
    assert sync_activities(session, user.id, FakeGarmin(3), storage) == 3

    activities = session.exec(select(Activity).order_by(Activity.start_time.desc())).all()
    assert [a.garmin_activity_id for a in activities] == [9000000100, 9000000099, 9000000098]
    first = activities[0]
    assert first.sport == "running" and first.distance_m > 6000
    assert "avg_cadence" in first.metrics

    channels = session.exec(select(ActivityStream.channel).where(ActivityStream.activity_id == first.id)).all()
    assert {"time", "hr", "speed", "lat", "lon"} <= set(channels)
    assert session.exec(select(Lap).where(Lap.activity_id == first.id)).first() is not None

    raw = session.get(ActivityRaw, first.id)
    assert raw.parser_version == garmin_parser.PARSER_VERSION
    assert storage.files[raw.fit_object_key] == b"PK-fake-fit"

    device = session.exec(select(Device)).one()
    assert device.name == "Forerunner 735XT"
    assert first.device_id == device.id


def test_sync_activities_cuando_ya_importadas_entonces_solo_trae_las_nuevas(session, user):
    garmin = FakeGarmin(3)
    sync_activities(session, user.id, garmin, MemoryStorage())
    newer = dict(garmin.activities[0]) | {"activityId": 9000000200}
    garmin.activities.insert(0, newer)
    garmin.detail_calls = 0

    assert sync_activities(session, user.id, garmin, MemoryStorage()) == 1
    assert garmin.detail_calls == 1


def test_sync_activities_cuando_max_new_entonces_respeta_el_limite(session, user):
    assert sync_activities(session, user.id, FakeGarmin(30), MemoryStorage(), max_new=5) == 5
    assert len(session.exec(select(Activity)).all()) == 5


def test_sync_activities_cuando_historico_completo_entonces_pagina_hasta_el_final(session, user):
    assert sync_activities(session, user.id, FakeGarmin(25), MemoryStorage(), max_new=None) == 25


def test_run_sync_cuando_todo_ok_entonces_registra_exito_y_metricas_diarias(session, user):
    run = run_sync(session, user.id, FakeGarmin(2), MemoryStorage(), days=3)
    assert run.status == SyncStatus.SUCCESS
    assert run.new_activities == 2 and run.daily_days == 3
    assert run.finished_at is not None
    daily = session.exec(select(DailyMetric)).all()
    assert len(daily) == 3
    assert daily[0].metrics["vo2max_running"] == 44.0


def test_run_sync_cuando_garmin_falla_entonces_registra_error_sin_romper(session, user):
    class Broken(FakeGarmin):
        def get_activities(self, start: int, limit: int) -> list[dict]:
            raise ConnectionError("Garmin caído")

    run = run_sync(session, user.id, Broken(), MemoryStorage())
    assert run.status == SyncStatus.ERROR
    assert "Garmin caído" in run.error


def test_reprocess_cuando_parser_nuevo_entonces_rehace_desde_raw(session: Session, user, monkeypatch):
    sync_activities(session, user.id, FakeGarmin(1), MemoryStorage())
    activity = session.exec(select(Activity)).one()
    raw = session.get(ActivityRaw, activity.id)
    # Simula que el reloj enviaba potencia y que el parser antiguo no la conocía.
    raw.summary = raw.summary | {"avgPower": 250.0}
    activity.metrics = {k: v for k, v in activity.metrics.items() if k != "avg_power"}
    session.commit()

    monkeypatch.setattr(garmin_parser, "PARSER_VERSION", garmin_parser.PARSER_VERSION + 1)
    assert reprocess_activities(session, user.id) == 1
    session.refresh(activity)
    assert activity.metrics["avg_power"] == 250.0
    assert reprocess_activities(session, user.id) == 0
