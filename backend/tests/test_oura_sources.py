import importlib.util
from datetime import date, timedelta
from pathlib import Path

from sqlmodel import select

from app.models import AppleImport, DailyMetric, IngestToken, UserSettings
from app.services import daily_sources, oura_sync
from app.services.sync_service import sync_daily
from tests.fakes import FakeGarmin
from tests.oura_fake import auth, connect, daily_docs, sleep_doc

TODAY = date.today()
MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "20261028_c4e1a7b9d2f5_oura_ring.py"


def _oura_day(session, user, day: date = TODAY) -> None:
    oura = {"sleep": [sleep_doc(day=day)], **{k: v[0] for k, v in daily_docs(day).items() if k != "vO2_max"}}
    prefs = daily_sources.preferences(session, user.id)
    daily_sources.set_source_metrics(session, user.id, day, "oura", oura_sync.day_metrics(oura), raw=oura, prefs=prefs)
    session.commit()


def _row(session, user, day: date = TODAY) -> DailyMetric:
    session.expire_all()
    return session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id, DailyMetric.day == day)).one()


def _pref(session, user, source: str) -> None:
    session.merge(UserSettings(user_id=user.id, recovery_source=source))
    session.commit()


def test_garmin_cuando_solo_hay_garmin_entonces_mismas_metricas_que_antes(session, user):
    from app.services.garmin_parser import parse_daily
    from tests.fakes import load

    sync_daily(session, user.id, FakeGarmin(), days=1)
    row = _row(session, user)
    assert row.metrics == parse_daily(load("daily"))
    assert set(row.metric_sources.values()) == {"garmin"} and "stats" in row.raw  # raw de Garmin donde siempre


def test_garmin_cuando_sincroniza_despues_de_oura_entonces_no_borra_lo_de_oura(session, user, oura):
    connect(session, user)
    _oura_day(session, user)
    sync_daily(session, user.id, FakeGarmin(), days=1)
    row = _row(session, user)
    assert row.metrics["readiness_score"] == 76 and row.metrics["sleep_seconds"] == 27000
    assert row.metric_sources["readiness_score"] == "oura" and "oura" in row.raw and "stats" in row.raw


def test_combinar_cuando_auto_y_oura_conectado_entonces_recuperacion_de_oura_y_resto_del_reloj(session, user, oura):
    connect(session, user)
    sync_daily(session, user.id, FakeGarmin(), days=1)
    _oura_day(session, user)
    row = _row(session, user)
    assert row.metrics["resting_hr"] == 46 and row.metric_sources["resting_hr"] == "oura"
    garmin = daily_sources.source_value(row, "garmin", "steps_daily")
    assert row.metrics["steps_daily"] == garmin and row.metric_sources["steps_daily"] == "garmin"
    assert row.metric_sources["vo2max_running"] == "garmin"


def test_combinar_cuando_watch_entonces_recuperacion_del_reloj_y_oura_solo_si_falta(session, user, oura):
    connect(session, user)
    _pref(session, user, "watch")
    sync_daily(session, user.id, FakeGarmin(), days=1)
    _oura_day(session, user)
    row = _row(session, user)
    assert row.metric_sources["resting_hr"] == "garmin"
    assert row.metric_sources["sleep_seconds"] == "oura"  # Garmin no midió el sueño ese día


def test_combinar_cuando_auto_sin_oura_conectado_entonces_reloj(session, user):
    sync_daily(session, user.id, FakeGarmin(), days=1)
    _oura_day(session, user)  # datos que quedaron de Oura, pero sin conexión
    assert _row(session, user).metric_sources["resting_hr"] == "garmin"


def test_cambiar_preferencia_cuando_api_entonces_recalcula_dias(client, session, user, oura):
    connect(session, user)
    sync_daily(session, user.id, FakeGarmin(), days=1)
    _oura_day(session, user)
    old = TODAY - timedelta(days=400)
    session.add(DailyMetric(user_id=user.id, day=old, metrics={"resting_hr": 50}, metric_sources={}))
    session.commit()
    res = client.put("/api/v1/settings/recovery-source", json={"source": "watch"}, headers=auth(user))
    assert res.status_code == 200 and res.json() == {"recovery_source": "watch"}
    assert _row(session, user).metric_sources["resting_hr"] == "garmin"
    assert client.put("/api/v1/settings/recovery-source", json={"source": "x"}, headers=auth(user)).status_code == 422
    client.put("/api/v1/settings/recovery-source", json={"source": "oura"}, headers=auth(user))
    assert _row(session, user).metric_sources["resting_hr"] == "oura"
    assert _row(session, user, old).metrics == {"resting_hr": 50}  # fuera de los 365 días: intacta


def test_apple_cuando_hay_garmin_entonces_solo_rellena_lo_que_falta(session, user):
    from app.services.apple_health import save_daily

    sync_daily(session, user.id, FakeGarmin(), days=1)
    garmin_rhr = _row(session, user).metrics["resting_hr"]
    assert save_daily(session, user.id, {TODAY: {"resting_hr": 99, "hrv_sdnn": 40}}) == 1
    row = _row(session, user)
    assert row.metrics["resting_hr"] == garmin_rhr and row.metrics["hrv_sdnn"] == 40
    assert row.metric_sources["hrv_sdnn"] == "apple"
    sync_daily(session, user.id, FakeGarmin(), days=1)  # Garmin ya no borra lo de Apple
    assert _row(session, user).metrics["hrv_sdnn"] == 40


def test_health_connect_cuando_pasos_repetidos_entonces_se_queda_el_mayor(session, user):
    from app.services.health_connect import _set_daily

    _set_daily(session, user.id, TODAY, "steps_daily", 5000, keep_max=True)
    _set_daily(session, user.id, TODAY, "steps_daily", 3000, keep_max=True)
    session.commit()
    row = _row(session, user)
    assert row.metrics["steps_daily"] == 5000 and row.metric_sources["steps_daily"] == "health_connect"


def test_valor_sin_fuente_cuando_se_recombina_entonces_se_conserva(session, user):
    session.add(DailyMetric(user_id=user.id, day=TODAY, metrics={"lt_speed": 3.9}))
    session.commit()
    sync_daily(session, user.id, FakeGarmin(), days=1)
    row = _row(session, user)
    assert row.metrics["lt_speed"] == 3.9 and "lt_speed" not in row.metric_sources


def test_quitar_fuente_cuando_purga_oura_entonces_vuelve_el_reloj(session, user, oura):
    connect(session, user)
    sync_daily(session, user.id, FakeGarmin(), days=1)
    _oura_day(session, user)
    _oura_day(session, user, TODAY - timedelta(days=1))  # día solo de Oura: desaparece
    daily_sources.remove_source(session, user.id, "oura")
    row = _row(session, user)
    assert "readiness_score" not in row.metrics and set(row.metric_sources.values()) == {"garmin"}
    assert "oura" not in row.raw
    assert session.exec(select(DailyMetric).where(DailyMetric.day == TODAY - timedelta(days=1))).first() is None


def _migration():
    spec = importlib.util.spec_from_file_location("oura_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migracion_cuando_filas_antiguas_entonces_marca_su_fuente(session, user):
    from app.models import User

    other = User(email="hc@example.com", password_hash="x")
    session.add(other)
    session.commit()
    session.add_all([
        DailyMetric(user_id=user.id, day=TODAY, metrics={"resting_hr": 50, "hrv_sdnn": 41, "lt_speed": 3.8},
                    raw={"stats": {"restingHeartRate": 50}}),
        DailyMetric(user_id=user.id, day=TODAY - timedelta(days=1), metrics={"resting_hr": 52, "steps_daily": 900}),
        DailyMetric(user_id=other.id, day=TODAY, metrics={"sleep_seconds": 25000}),
        IngestToken(user_id=other.id, token_hash="h" * 64, hint="abcd"),
        AppleImport(id="a1", user_id=user.id, filename="export.zip", size_bytes=1),
    ])  # fmt: skip
    session.commit()
    module = _migration()
    conn = session.connection()
    assert module.backfill(conn) == 3
    assert module.backfill(conn) == 0  # idempotente
    session.commit()
    garmin_row = _row(session, user)
    assert garmin_row.metric_sources == {"resting_hr": "garmin", "hrv_sdnn": "apple"}
    assert garmin_row.raw["_sources"] == {"garmin": {"resting_hr": 50}, "apple": {"hrv_sdnn": 41}}
    assert garmin_row.raw["stats"] == {"restingHeartRate": 50} and garmin_row.metrics["lt_speed"] == 3.8
    assert set(_row(session, user, TODAY - timedelta(days=1)).metric_sources.values()) == {"apple"}
    assert _row(session, other).metric_sources == {"sleep_seconds": "health_connect"}
    # Tras migrar, Garmin sustituye sus valores y conserva los de Apple.
    daily_sources.merge_daily(garmin_row, "auto", False)
    assert garmin_row.metrics == {"resting_hr": 50, "hrv_sdnn": 41, "lt_speed": 3.8}
