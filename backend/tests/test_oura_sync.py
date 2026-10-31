from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import select

from app.models import (
    Activity,
    ActivityStream,
    DailyMetric,
    DailySeries,
    HealthTag,
    OuraConnection,
    RestPeriod,
    WellnessSession,
)  # fmt: skip
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


def test_sincronizar_cuando_un_documento_tiene_formato_inesperado_entonces_se_salta_solo_ese_tipo(
    session, user, oura, monkeypatch
):
    from datetime import date

    from app.models import OuraConnection
    from app.services import oura_sync

    connect(session, user)
    oura.collections["tag"] = [{"id": "t1", "day": "2026-10-20", "tag_type_code": "tag_generic_alcohol"}]
    original = oura_sync.store

    def store(session_, user_id, data_type, docs, prefs, **kw):
        if data_type == "daily_stress":
            raise TypeError("campo con un tipo distinto en este modelo de anillo")
        return original(session_, user_id, data_type, docs, prefs, **kw)

    monkeypatch.setattr(oura_sync, "store", store)
    counts = oura_sync.sync_range(session, user.id, date(2026, 10, 19), date(2026, 10, 21))
    session.expire_all()
    row = session.get(OuraConnection, user.id)
    assert row.status == "ok" and "daily_stress" in row.last_error
    assert counts["daily_stress"] == 0 and "tag" in counts


def test_sincronizar_cuando_faltan_campos_o_tipos_raros_entonces_no_falla(session, user, oura):
    from datetime import date

    from app.services import oura_sync

    connect(session, user)
    oura.collections["daily_readiness"] = [{"id": "r1", "day": "2026-10-20"}, "no-es-un-dict", {"day": None}]
    oura.collections["sleep"] = [{"id": "s1", "day": "2026-10-20", "type": "long_sleep", "total_sleep_duration": None}]
    oura.collections["daily_activity"] = [{"id": "a1", "day": "2026-10-20", "steps": "muchos", "class_5_min": 12}]
    counts = oura_sync.sync_range(session, user.id, date(2026, 10, 19), date(2026, 10, 21))
    assert counts is not None


# ─── Entrenos completos: serie de FC, MET, zonas, intensidad ─────────────────


def _workout_hr(start: datetime, minutes: int = 45, every_s: int = 5) -> list[dict]:
    """FC de entreno cada 5 s que sube de 120 a 165 ppm (y una muestra suelta despierto fuera del entreno)."""
    n = minutes * 60 // every_s
    rows = [{"timestamp": (start + timedelta(seconds=i * every_s)).isoformat(), "bpm": 120 + round(45 * i / n),
             "source": "workout"} for i in range(n)]  # fmt: skip
    return [*rows, {"timestamp": (start - timedelta(hours=2)).isoformat(), "bpm": 60, "source": "awake"}]


def test_workout_activity_cuando_hay_fc_y_met_entonces_series_alineadas_y_metricas():
    start = START
    hr = [(int(start.timestamp()) + s, b) for s, b in ((0, 100.0), (30, 120.0), (65, 140.0), (130, 130.0))]
    met = [(int(start.timestamp()), 4.0), (int(start.timestamp()) + 60, 8.0)]
    act = oura_sync.workout_activity(workout_doc(start, minutes=3) | {"intensity": "hard"}, hr, met)
    assert act.streams["time"] == [0, 30, 65, 130] and act.streams["hr"] == [100, 120, 140, 130]
    # Cada muestra de FC lleva el MET de su minuto; pasados 2 min sin MET, nada.
    assert act.streams["met"] == [4.0, 4.0, 8.0, 8.0]
    assert (act.avg_hr, act.max_hr) == (122, 140)
    m = act.metrics
    assert m["min_hr"] == 100 and m["avg_met"] == 6.0 and m["max_met"] == 8.0
    assert m["oura_intensity"] == 3 and m["oura_origin"] == 2 and m["avg_speed"] == 50.0
    assert m["oura"]["intensity"] == "hard" and m["oura"]["source"] == "autodetected"
    assert act.timezone == "+00:00" and act.calories == 450


def test_workout_activity_cuando_no_hay_datos_entonces_sin_series():
    act = oura_sync.workout_activity(workout_doc(START) | {"distance": None, "intensity": None}, [], [])
    assert act.streams == {} and act.avg_hr is None and act.distance_m is None
    assert "oura_intensity" not in act.metrics and "avg_speed" not in act.metrics
    assert oura_sync.workout_activity(workout_doc(START) | {"end_datetime": START.isoformat()}, [], []) is None


def test_sync_range_cuando_entreno_con_fc_entonces_guarda_series_zonas_e_intensidad(session, user, oura):
    connect(session, user)
    # FC máx. conocida (de otro entreno): da las zonas de la app.
    save_imported(session, user.id, ImportedActivity(sport="running", start_time=START - timedelta(days=3),
                                                     duration_s=1800, max_hr=190), "fit")  # fmt: skip
    oura.collections["heartrate"] = _workout_hr(START)
    activity_doc = daily_docs()["daily_activity"][0]
    activity_doc["met"] = {"interval": 60.0, "items": [3.0] * 60 * 24, "timestamp": f"{DAY}T00:00:00+00:00"}
    oura.collections["daily_activity"] = [activity_doc]
    oura.collections["workout"] = [workout_doc(START)]
    oura_sync.sync_range(session, user.id, DAY, DAY)
    act = session.exec(select(Activity).where(Activity.source == "oura")).one()
    streams = {s.channel: s.values for s in session.exec(select(ActivityStream))}
    assert len(streams["time"]) == len(streams["hr"]) == len(streams["met"]) == 540
    assert streams["time"][:2] == [0, 5] and streams["hr"][0] == 120 and set(streams["met"]) == {3.0}
    assert act.metrics["min_hr"] == 120
    assert act.max_hr == 165 and act.metrics["avg_met"] == 3.0 and act.metrics["oura_intensity"] == 2
    zones = [act.metrics.get(f"hr_zone_{i}_s") for i in range(1, 6)]
    assert all(z is not None for z in zones) and sum(zones) == pytest.approx(2695, abs=5)


def test_sync_range_cuando_el_entreno_cambia_en_oura_entonces_se_actualiza_sin_duplicar(session, user, oura):
    connect(session, user)
    oura.collections["workout"] = [workout_doc(START)]
    oura_sync.sync_range(session, user.id, DAY, DAY)
    act = session.exec(select(Activity)).one()
    assert act.avg_hr is None and act.metrics["oura_intensity"] == 2
    act.name = "Mi paseo"
    session.add(act)
    session.commit()
    oura.collections["heartrate"] = _workout_hr(START)
    oura.collections["workout"] = [workout_doc(START) | {"intensity": "easy", "calories": 300.0}]
    oura_sync.sync_range(session, user.id, DAY, DAY)
    session.expire_all()
    act = session.exec(select(Activity)).one()
    assert act.name == "Mi paseo" and act.calories == 300 and act.metrics["oura_intensity"] == 1
    assert act.avg_hr == 142 and len(session.exec(select(ActivityStream)).all()) == 2  # time y hr


def test_workout_sin_fc_de_entreno_entonces_usa_la_fc_de_ese_rato(session, user, oura):
    connect(session, user)
    oura.collections["heartrate"] = [
        {"timestamp": (START + timedelta(minutes=m)).isoformat(), "bpm": 90 + m, "source": "awake"} for m in (0, 5, 10)
    ]
    oura.collections["workout"] = [workout_doc(START, minutes=12)]
    oura_sync.sync_range(session, user.id, DAY, DAY)
    act = session.exec(select(Activity)).one()
    assert (act.avg_hr, act.max_hr, act.metrics["min_hr"]) == (95, 100, 90)


def test_reprocess_workouts_cuando_entreno_antiguo_entonces_lo_completa_con_lo_guardado(session, user, oura):
    connect(session, user)
    oura.collections["heartrate"] = _workout_hr(START)
    oura_sync.sync_range(session, user.id, DAY, DAY)  # FC continua guardada; aún sin entrenos
    old, _ = save_imported(session, user.id, ImportedActivity(
        sport="running", start_time=START, duration_s=2700, distance_m=9000, calories=450, name="Carrera · Oura",
        timezone="+02:00"), "oura", "w-old")  # fmt: skip
    assert oura_sync.reprocess_workouts(session) == 1
    session.expire_all()
    act = session.get(Activity, old.id)
    assert act.avg_hr == 142 and act.max_hr == 165 and act.metrics["min_hr"] == 120
    assert act.timezone == "+02:00" and act.start_time == START and act.name == "Carrera · Oura"
    assert {s.channel for s in session.exec(select(ActivityStream))} == {"time", "hr"}
    assert oura_sync.reprocess_workouts(session, user.id) == 1  # idempotente
    assert len(session.exec(select(ActivityStream)).all()) == 2


def test_analisis_de_entreno_oura_cuando_hay_fc_entonces_pulso_trimp_y_vo2max_de_oura(session, user, oura):
    from app.services import activity_analysis

    connect(session, user)
    oura.collections["heartrate"] = _workout_hr(START)
    oura.collections["vO2_max"] = daily_docs()["vO2_max"]
    oura.collections["workout"] = [workout_doc(START, activity="cycling") | {"distance": None}]
    oura_sync.sync_range(session, user.id, DAY, DAY)
    act = session.exec(select(Activity)).one()
    data = activity_analysis.analysis(session, act)
    hr = data["heart_rate"]
    assert (hr["min"], hr["avg"], hr["max"]) == (120, 142, 165)
    assert hr["drift"]["pct"] > 5 and hr["drift"]["first_hr"] < hr["drift"]["second_hr"]
    assert hr["trimp"] and hr["trimp"] > 0
    assert data["vo2max"]["current"] == 51 and data["vo2max"]["current_source"] == "oura"
    assert data["decoupling"] is None and data["splits"] == []


def test_despike_cuando_el_anillo_mete_un_valor_fijo_imposible_entonces_lo_quita():
    # Como en un entreno real: 208 ppm cada 5 s mezclado con la FC buena (~100) y luego minutos solo de 208.
    bad = [(t, 208.0) for t in range(3, 400, 5)]
    good = [(t, 100.0 + (t // 100)) for t in range(0, 200, 10)] + [(t, 105.0 + (t % 3)) for t in range(403, 1400, 5)]
    clean = oura_sync.despike(sorted(bad + good))
    assert max(b for _, b in clean) < 120 and len(clean) == len(good)
    # Subidas reales (de 100 a 170 en 2 min) y huecos largos se respetan.
    ramp = [(t, 100.0 + t * 0.6) for t in range(0, 120, 5)] + [(600, 90.0), (605, 91.0)]
    assert oura_sync.despike(ramp) == ramp
