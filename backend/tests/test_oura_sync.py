from datetime import UTC, date, datetime, timedelta

from sqlmodel import select

from app.models import Activity, DailyMetric, DailySeries, HealthTag, OuraConnection, RestPeriod, WellnessSession
from app.services import oura_sync
from app.services.file_import import ImportedActivity, save_imported
from app.tasks import oura as tasks
from tests.oura_fake import DAY, connect, daily_docs, sleep_doc, workout_doc

START = datetime(2026, 10, 20, 18, 0, tzinfo=UTC)


def _load_all(oura) -> None:
    oura.collections.update(daily_docs())
    oura.collections["sleep"] = [
        sleep_doc(),
        sleep_doc(kind="sleep", total=1800, doc_id="nap-1", start="2026-10-20T15:00:00+02:00"),
        sleep_doc(kind="deleted", total=9999, doc_id="del-1"),
    ]
    oura.collections["heartrate"] = [
        {"timestamp": "2026-10-20T18:05:00+00:00", "bpm": 150, "source": "workout"},
        {"timestamp": "2026-10-20T18:20:00+00:00", "bpm": 170, "source": "workout"},
        {"timestamp": "2026-10-20T12:00:00+00:00", "bpm": 70, "source": "awake"},
    ]
    oura.collections["session"] = [{
        "id": "se-1", "day": "2026-10-20", "type": "meditation", "mood": "good",
        "start_datetime": "2026-10-20T13:00:00+02:00", "end_datetime": "2026-10-20T13:10:00+02:00",
        "heart_rate": {"interval": 5.0, "items": [60, 58, None, 56], "timestamp": "2026-10-20T13:00:00+02:00"},
        "heart_rate_variability": {"interval": 5.0, "items": [50, 70], "timestamp": "2026-10-20T13:00:00+02:00"},
        "motion_count": {"interval": 5.0, "items": [0, 1], "timestamp": "2026-10-20T13:00:00+02:00"},
    }]  # fmt: skip
    oura.collections["tag"] = [{"id": "tg-1", "day": "2026-10-20", "text": "cena fuerte",
                                "timestamp": "2026-10-20T21:00:00+02:00",
                                "tags": ["tag_generic_late_meal"]}]  # fmt: skip
    oura.collections["enhanced_tag"] = [{
        "id": "et-1", "tag_type_code": "tag_generic_alcohol", "start_time": "2026-10-20T20:00:00+02:00",
        "end_time": None, "start_day": "2026-10-20", "end_day": None, "comment": "dos copas", "custom_name": None,
    }]  # fmt: skip
    oura.collections["rest_mode_period"] = [{"id": "rm-1", "start_day": "2026-10-18", "start_time": None,
                                             "end_day": None, "end_time": None, "episodes": []}]  # fmt: skip
    oura.collections["workout"] = [workout_doc(START)]
    oura.collections["ring_configuration"] = [
        {"id": "r-0", "color": "black", "design": "heritage", "firmware_version": "1.0", "hardware_type": "gen2",
         "set_up_at": "2021-01-01T00:00:00+00:00", "size": 8},
        {"id": "r-1", "color": "silver", "design": "horizon", "firmware_version": "2.9.1", "hardware_type": "gen3",
         "set_up_at": "2024-05-01T00:00:00+00:00", "size": 9},
    ]  # fmt: skip
    oura.collections["ring_battery_level"] = [
        {"timestamp": "2026-10-20T08:00:00+00:00", "level": 12, "charging": False, "in_charger": False}
    ]


def test_day_metrics_cuando_todos_los_tipos_entonces_claves_del_catalogo():
    oura = {k: v[0] for k, v in daily_docs().items()}
    oura["vo2_max"] = oura.pop("vO2_max")
    oura["sleep"] = [sleep_doc(), sleep_doc(kind="late_nap", total=1200, doc_id="n")]
    m = oura_sync.day_metrics(oura)
    assert m["sleep_seconds"] == 27000 and m["naps_s"] == 1200 and m["resting_hr"] == 46
    assert m["hrv_last_night"] == 58 and m["sleep_deep_s"] == 5400 and m["breath_rate"] == 14.5
    assert m["sleep_score"] == 82 and m["oura_sleep_restfulness"] == 60
    assert m["readiness_score"] == 76 and m["temperature_deviation"] == -0.21 and m["oura_readiness_hrv_balance"] == 70
    assert m["activity_score"] == 88 and m["steps_daily"] == 11200 and m["high_activity_met_min"] == 60
    assert m["oura_activity_move_every_hour"] == 100 and m["non_wear_s"] == 600 and m["inactivity_alerts"] == 2
    assert m["spo2_avg"] == 96.8 and m["breathing_disturbance_index"] == 4
    assert m["stress_high_s"] == 3600 and m["recovery_high_s"] == 5400
    assert m["resilience_level"] == 3 and m["oura_resilience_daytime_recovery"] == 55
    assert m["vo2max_oura"] == 51 and m["cardio_age"] == 35 and m["pulse_wave_velocity"] == 6.9


def test_main_and_naps_cuando_no_hay_long_sleep_entonces_el_mas_largo_y_sin_descartados():
    main, naps = oura_sync.main_and_naps([
        sleep_doc(kind="sleep", total=3000, doc_id="a"), sleep_doc(kind="sleep", total=9000, doc_id="b"),
        sleep_doc(kind="rest", total=20000, doc_id="c"),
    ])  # fmt: skip
    assert main["id"] == "b" and [n["id"] for n in naps] == ["a"]
    assert oura_sync.main_and_naps([sleep_doc(kind="deleted")]) == (None, [])


def test_sync_range_cuando_todos_los_datos_entonces_guarda_cada_tipo(session, user, oura, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.notifications.notify", lambda *a, **k: sent.append(a[3]) or True)
    connect(session, user)
    _load_all(oura)
    counts = oura_sync.sync_range(session, user.id, DAY, DAY)
    assert counts["sleep"] == 3 and counts["workout"] == 1 and counts["heartrate"] == 3
    row = session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id, DailyMetric.day == DAY)).one()
    assert row.metrics["sleep_seconds"] == 27000 and row.metrics["naps_s"] == 1800
    assert row.metric_sources["sleep_seconds"] == "oura" and row.metric_sources["steps_daily"] == "oura"
    raw_sleep = row.raw["oura"]["sleep"]
    assert len(raw_sleep) == 3 and all("heart_rate" not in p and "sleep_phase_5_min" not in p for p in raw_sleep)
    assert "met" not in row.raw["oura"]["daily_activity"]
    series = {s.kind: s.data for s in session.exec(select(DailySeries).where(DailySeries.user_id == user.id))}
    assert series["hypnogram_5min"] == {"start": "2026-10-19T23:30:00+02:00", "phases": "4221133214"}
    assert series["sleep_hr"]["items"] == [55, None, 50, 48, 47, 49] and series["sleep_hrv"]["interval"] == 300
    assert series["movement_30s"]["values"] == "1112111" and series["hypnogram_30s"]["phases"] == "42211"
    assert series["activity_class_5min"]["classes"] == "0011223344" and series["met"]["items"] == [0.9, 1.2, 3.5]
    assert [p[1:] for p in series["heartrate"]["points"]] == [[70, "awake"], [150, "workout"], [170, "workout"]]
    ws = session.exec(select(WellnessSession)).one()
    assert (ws.type, ws.mood, ws.hr_avg, ws.hrv_avg) == ("meditation", "good", 58.0, 60.0)
    tags = {t.external_id: t for t in session.exec(select(HealthTag))}
    assert tags["et-1"].label == "Alcohol" and tags["et-1"].comment == "dos copas"
    assert tags["tg-1"].label == "Cena tarde" and tags["tg-1"].day == DAY
    rest = session.exec(select(RestPeriod)).one()
    assert rest.start_date == date(2026, 10, 18) and rest.end_date is None
    act = session.exec(select(Activity).where(Activity.source == "oura")).one()
    assert act.sport == "running" and act.duration_s == 2700 and act.distance_m == 9000
    assert act.avg_hr == 160 and act.max_hr == 170 and act.external_id == "w-1"
    conn = session.get(OuraConnection, user.id)
    assert conn.ring["model"] == "gen3" and conn.ring["firmware"] == "2.9.1" and conn.ring["battery_level"] == 12
    assert conn.last_sync_at is not None and conn.status == "ok"
    assert [k for k in sent if k.startswith("oura-")] == [
        f"oura-battery:{date.today().isoformat()}"
    ]  # batería baja: un aviso con clave del día


def test_sync_range_cuando_se_repite_entonces_no_duplica_nada(session, user, oura):
    connect(session, user)
    _load_all(oura)
    oura_sync.sync_range(session, user.id, DAY, DAY)
    oura_sync.sync_range(session, user.id, DAY, DAY)
    assert len(session.exec(select(Activity)).all()) == 1
    assert len(session.exec(select(HealthTag)).all()) == 2
    hr = session.exec(select(DailySeries).where(DailySeries.kind == "heartrate")).one()
    assert len(hr.data["points"]) == 3


def test_workout_de_oura_cuando_garmin_tiene_el_mismo_entreno_entonces_no_duplica(session, user, oura):
    save_imported(session, user.id, ImportedActivity(sport="running", start_time=START + timedelta(seconds=50),
                                                     duration_s=2720), "garmin_fit")  # fmt: skip
    connect(session, user)
    oura.collections["workout"] = [workout_doc(START)]
    counts = oura_sync.sync_range(session, user.id, DAY, DAY)
    assert counts["workout"] == 0
    assert [a.source for a in session.exec(select(Activity)).all()] == ["garmin_fit"]


def test_sync_range_cuando_falta_un_scope_entonces_lo_salta_y_lo_anota(session, user, oura):
    connect(session, user)
    oura.fail["/v2/usercollection/daily_spo2"] = [403]
    oura.collections.update(daily_docs())
    oura_sync.sync_range(session, user.id, DAY, DAY)
    conn = session.get(OuraConnection, user.id)
    assert "daily_spo2" in conn.last_error and conn.status == "ok"
    row = session.exec(select(DailyMetric)).one()
    assert "readiness_score" in row.metrics and "spo2_avg" not in row.metrics


def test_fetch_object_cuando_siesta_nueva_entonces_se_suma_sin_perder_la_noche(session, user, oura):
    connect(session, user)
    oura.collections["sleep"] = [sleep_doc()]
    oura_sync.sync_range(session, user.id, DAY, DAY)
    oura.documents[("sleep", "nap-2")] = sleep_doc(kind="sleep", total=1500, doc_id="nap-2")
    assert oura_sync.fetch_object(session, user.id, "sleep", "nap-2", "create") == 1
    row = session.exec(select(DailyMetric)).one()
    assert row.metrics["sleep_seconds"] == 27000 and row.metrics["naps_s"] == 1500
    assert session.exec(select(DailySeries).where(DailySeries.kind == "hypnogram_5min")).one().data["phases"]


def test_fetch_object_cuando_vo2max_entonces_usa_la_coleccion_vO2_max(session, user, oura):
    connect(session, user)
    oura.documents[("vO2_max", "v-9")] = {"id": "v-9", "day": DAY.isoformat(), "vo2_max": 49.5}
    oura_sync.fetch_object(session, user.id, "vo2_max", "v-9", "update")
    assert session.exec(select(DailyMetric)).one().metrics["vo2max_oura"] == 49.5


def test_fetch_object_cuando_delete_entonces_borra_lo_importado_de_oura(session, user, oura):
    connect(session, user)
    _load_all(oura)
    oura_sync.sync_range(session, user.id, DAY, DAY)
    pairs = [("workout", "w-1"), ("session", "se-1"), ("enhanced_tag", "et-1"), ("rest_mode_period", "rm-1"),
             ("daily_readiness", "dr-1"), ("sleep", "s-1")]  # fmt: skip
    for data_type, object_id in pairs:
        assert oura_sync.fetch_object(session, user.id, data_type, object_id, "delete") == 1, data_type
    session.expire_all()
    assert session.exec(select(Activity)).all() == [] and session.exec(select(WellnessSession)).all() == []
    assert [t.external_id for t in session.exec(select(HealthTag))] == ["tg-1"]
    assert session.exec(select(RestPeriod)).all() == []
    row = session.exec(select(DailyMetric)).one()
    assert "readiness_score" not in row.metrics and "daily_readiness" not in row.raw["oura"]
    assert row.metrics["sleep_seconds"] == 1800  # la siesta pasa a ser el periodo principal
    assert session.exec(select(DailySeries).where(DailySeries.kind == "hypnogram_5min")).all() == []


def test_import_history_cuando_cuenta_basica_entonces_limita_dias_en_bloques(session, user, oura):
    from app.models import AccountTier

    user.tier = AccountTier.BASIC
    session.add(user)
    session.commit()
    from app.services.accounts import set_setting

    set_setting(session, "basic_history_days", "45")
    session.commit()
    connect(session, user)
    tasks.import_history(session, user.id, today=DAY)
    conn = session.get(OuraConnection, user.id)
    assert conn.history_status == "done"
    assert (conn.history_from, conn.history_to) == (DAY - timedelta(days=44), DAY)
    sleep_calls = [r.url.params for r in oura.requests if r.url.path.endswith("/sleep")]
    assert [(p["start_date"], p["end_date"]) for p in sleep_calls] == [
        ("2026-09-21", "2026-10-21"), ("2026-09-06", "2026-09-21")]  # fmt: skip
    hr_calls = [r for r in oura.requests if r.url.path.endswith("/heartrate")]
    assert len(hr_calls) == 8  # 30 días (5 trozos de hasta 7) + 15 días (3 trozos)


def test_import_history_cuando_oura_falla_entonces_estado_error(session, user, oura):
    connect(session, user)
    oura.fail["/v2/usercollection/heartrate"] = [500] * 10
    tasks.import_history(session, user.id, today=DAY)
    conn = session.get(OuraConnection, user.id)
    assert conn.history_status == "error" and conn.status == "error"


def test_sync_recent_cuando_modulo_apagado_entonces_no_sincroniza(session, user, oura):
    from app.services import modules

    connect(session, user)
    modules.set_user_modules(session, user, {"oura": False}, None)
    assert tasks.sync_recent(session) == 0
    modules.set_user_modules(session, user, {"oura": None}, None)
    assert tasks.sync_recent(session) == 1
