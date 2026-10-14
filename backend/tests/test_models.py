from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import Activity, ActivityStream, MetricDefinition, MetricScope, User
from app.services.metric_catalog import CATALOG, seed_catalog


def test_seed_catalog_cuando_se_ejecuta_dos_veces_entonces_no_duplica(session: Session):
    seed_catalog(session)
    seed_catalog(session)
    rows = session.exec(select(MetricDefinition)).all()
    assert len(rows) == len(CATALOG)
    hrv = session.get(MetricDefinition, "hrv_last_night")
    assert hrv.scope == MetricScope.DAILY and hrv.higher_is_better is True


def _activity(session: Session, user: User, metrics: dict) -> Activity:
    act = Activity(
        user_id=user.id,
        sport="running",
        start_time=datetime(2026, 10, 14, 16, tzinfo=UTC),
        duration_s=1800,
        distance_m=6000,
        metrics=metrics,
    )
    session.add(act)
    session.commit()
    session.refresh(act)
    return act


def test_activity_cuando_reloj_trae_metrica_nueva_entonces_se_guarda_sin_migracion(session, user):
    old = _activity(session, user, {"avg_cadence": 172})
    new = _activity(session, user, {"avg_cadence": 175, "avg_power": 265, "respiration_avg": 38})

    with_power = session.exec(select(Activity).where(Activity.metrics.has_key("avg_power"))).all()
    assert [a.id for a in with_power] == [new.id]
    assert session.get(Activity, old.id).metrics == {"avg_cadence": 172}


def test_activity_stream_cuando_canal_desconocido_entonces_se_admite(session, user):
    act = _activity(session, user, {})
    session.add(ActivityStream(activity_id=act.id, channel="core_temperature", values=[37.1, None, 37.4]))
    session.commit()
    stream = session.exec(select(ActivityStream).where(ActivityStream.activity_id == act.id)).one()
    assert stream.values == [37.1, None, 37.4]
