# ruff: noqa: E501 - el XML de ejemplo imita líneas reales del export
import zipfile
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, ActivityStream, AppleImport, DailyMetric, User
from app.services import apple_health, health_connect
from app.services.file_import import FileImportError, ImportedActivity, save_imported

START = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)  # 09:00 +0200


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _d(t: datetime) -> str:
    """Fecha en el formato del export: «2026-10-01 09:00:00 +0200»."""
    return t.astimezone(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S %z")


def _export_xml(with_route: bool = True) -> str:
    end = START + timedelta(minutes=30)
    hr = "".join(
        f'<Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch" unit="count/min" '
        f'startDate="{_d(START + timedelta(seconds=s))}" endDate="{_d(START + timedelta(seconds=s))}" value="{140 + s // 120}"/>'
        for s in range(0, 1801, 60)
    )  # fmt: skip
    route = (
        '<WorkoutRoute sourceName="Apple Watch"><FileReference path="/workout-routes/route_1.gpx"/></WorkoutRoute>'
        if with_route
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (ExportDate,Me,(Record|Workout)*)>
<!ATTLIST HealthData locale CDATA #REQUIRED>
]>
<HealthData locale="es_ES">
 <ExportDate value="2026-10-05 10:00:00 +0200"/>
 <Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"/>
 {hr}
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Apple Watch" unit="count/min" startDate="2026-10-01 00:00:00 +0200" endDate="2026-10-01 23:59:00 +0200" value="47"/>
 <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" sourceName="Apple Watch" unit="ms" startDate="2026-10-01 03:00:00 +0200" endDate="2026-10-01 03:01:00 +0200" value="60"/>
 <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" sourceName="Apple Watch" unit="ms" startDate="2026-10-01 05:00:00 +0200" endDate="2026-10-01 05:01:00 +0200" value="70"/>
 <Record type="HKQuantityTypeIdentifierVO2Max" sourceName="Apple Watch" unit="mL/min·kg" startDate="2026-09-29 18:00:00 +0200" endDate="2026-09-29 18:00:00 +0200" value="52.4"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count" startDate="2026-10-01 08:00:00 +0200" endDate="2026-10-01 08:30:00 +0200" value="4000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Apple Watch" unit="count" startDate="2026-10-01 08:00:00 +0200" endDate="2026-10-01 08:30:00 +0200" value="5200"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-09-30 23:30:00 +0200" endDate="2026-10-01 06:30:00 +0200" value="HKCategoryValueSleepAnalysisInBed"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-09-30 23:45:00 +0200" endDate="2026-10-01 03:45:00 +0200" value="HKCategoryValueSleepAnalysisAsleepCore"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-10-01 03:45:00 +0200" endDate="2026-10-01 06:15:00 +0200" value="HKCategoryValueSleepAnalysisAsleepDeep"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30" durationUnit="min" sourceName="Apple Watch de Ana" startDate="{_d(START)}" endDate="{_d(end)}">
  <MetadataEntry key="HKIndoorWorkout" value="0"/>
  <MetadataEntry key="HKElevationAscended" value="8500 cm"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="{_d(START)}" endDate="{_d(end)}" average="148" minimum="120" maximum="171" unit="count/min"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" startDate="{_d(START)}" endDate="{_d(end)}" sum="6.1" unit="km"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" startDate="{_d(START)}" endDate="{_d(end)}" sum="420" unit="kcal"/>
  {route}
 </Workout>
 <Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining" duration="45" durationUnit="min" sourceName="Apple Watch de Ana" startDate="2026-10-02 19:00:00 +0200" endDate="2026-10-02 19:45:00 +0200" totalEnergyBurned="250" totalEnergyBurnedUnit="kcal"/>
</HealthData>
"""


def _route_gpx() -> str:
    pts = "".join(
        f'<trkpt lat="{37.6 + i * 0.003}" lon="-0.98"><ele>{10 + i}</ele><time>{(START + timedelta(minutes=i)).isoformat()}</time></trkpt>'
        for i in range(31)
    )  # fmt: skip
    return (
        f'<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{pts}</trkseg></trk></gpx>'
    )


def _export_zip(tmp_path, xml: str | None = None):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("apple_health_export/export.xml", xml or _export_xml())
        zf.writestr("apple_health_export/export_cda.xml", "<x/>")
        zf.writestr("apple_health_export/workout-routes/route_1.gpx", _route_gpx())
    return path


def test_export_entrenos_series_y_metricas_diarias(session: Session, user: User, tmp_path):
    seen: list[int] = []
    counts = apple_health.import_export(session, user.id, _export_zip(tmp_path), seen.append)
    assert counts == {"workouts": 2, "duplicates": 0, "days": 1}
    assert seen and max(seen) <= 99

    run, strength = session.exec(
        select(Activity).where(Activity.user_id == user.id).order_by(Activity.start_time)
    ).all()
    assert run.source == "apple" and run.sport == "running"
    assert run.name == "Carrera · Apple Watch"
    assert run.duration_s == 1800 and run.distance_m == pytest.approx(6100)
    assert (run.avg_hr, run.max_hr, run.calories, run.elevation_gain_m) == (148, 171, 420, 85)
    assert run.timezone == "+02:00"
    assert run.metrics["vo2max"] == 52.4  # VO2max del 29/09, la última antes del entreno
    channels = {
        s.channel: s.values for s in session.exec(select(ActivityStream).where(ActivityStream.activity_id == run.id))
    }
    assert {"lat", "lon", "hr", "altitude", "distance"} <= set(channels)
    assert channels["hr"][0] == 140 and channels["hr"][-1] == 155  # pulso cruzado con cada punto GPS

    assert strength.sport == "strength_training" and strength.calories == 250
    assert strength.duration_s == 2700 and strength.avg_hr is None

    day = session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id)).one()
    assert day.day == date(2026, 10, 1)
    assert day.metrics["resting_hr"] == 47
    assert day.metrics["hrv_sdnn"] == 65  # media de la noche, en su propia clave (SDNN ≠ RMSSD)
    assert day.metrics["steps_daily"] == 5200  # iPhone y reloj no se suman: se queda la fuente mayor
    assert day.metrics["sleep_seconds"] == 6.5 * 3600  # «en cama» no cuenta como dormido


def test_export_sin_ruta_guarda_serie_de_pulso(session: Session, user: User, tmp_path):
    xml = tmp_path / "export.xml"
    xml.write_text(_export_xml(with_route=False), encoding="utf-8")
    apple_health.import_export(session, user.id, xml)
    run = session.exec(select(Activity).where(Activity.sport == "running")).one()
    channels = {s.channel for s in session.exec(select(ActivityStream).where(ActivityStream.activity_id == run.id))}
    assert channels == {"time", "hr"}


def test_export_no_pisa_garmin_ni_duplica(session: Session, user: User, tmp_path):
    garmin, _ = save_imported(
        session,
        user.id,
        ImportedActivity(sport="running", start_time=START + timedelta(seconds=40), duration_s=1810),
        "fit",
    )
    session.add(DailyMetric(user_id=user.id, day=date(2026, 10, 1), metrics={"resting_hr": 45}))
    session.commit()
    counts = apple_health.import_export(session, user.id, _export_zip(tmp_path))
    assert counts["workouts"] == 1 and counts["duplicates"] == 1
    day = session.exec(select(DailyMetric).where(DailyMetric.user_id == user.id)).one()
    assert day.metrics["resting_hr"] == 45 and day.metrics["steps_daily"] == 5200
    # Repetir la importación no crea nada nuevo.
    assert apple_health.import_export(session, user.id, _export_zip(tmp_path))["workouts"] == 0
    assert session.get(Activity, garmin.id).source == "fit"


@pytest.mark.parametrize(
    ("content", "msg"),
    [
        ('<?xml version="1.0"?><!DOCTYPE HealthData [<!ENTITY a "aaaa">]><HealthData>&a;</HealthData>', "ENTITY"),
        ('<?xml version="1.0"?><gpx></gpx>', "Apple Salud"),
    ],
)
def test_export_no_valido(session: Session, user: User, tmp_path, content, msg):
    path = tmp_path / "export.xml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(FileImportError, match=msg):
        apple_health.import_export(session, user.id, path)


def test_zip_sin_export(session: Session, user: User, tmp_path):
    path = tmp_path / "otra.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("foto.jpg", b"x")
    with pytest.raises(FileImportError, match="export.xml"):
        apple_health.import_export(session, user.id, path)


@pytest.mark.parametrize(
    ("raw", "sport"),
    [("Correr", "running"), ("Running", "running"), ("Carrera en cinta", "treadmill_running"),
     ("Ciclismo en interior", "indoor_cycling"), ("Natación", "lap_swimming"),
     ("Entrenamiento de fuerza tradicional", "strength_training"), ("HKWorkoutActivityTypeHiking", "hiking"),
     ("Tai chi", "other")],
)  # fmt: skip
def test_deporte_del_atajo(raw, sport):
    assert apple_health.shortcut_sport(raw) == sport


@pytest.mark.parametrize(("raw", "seconds"), [(2700, 2700), ("45:00", 2700), ("1:02:03", 3723), ("45 min", 2700)])
def test_duracion_del_atajo(raw, seconds):
    assert apple_health._seconds(raw) == seconds


def test_api_subida_por_trozos(client, user, session, tmp_path, monkeypatch):
    from app.api import apple as apple_api
    from app.tasks import sources as tasks

    monkeypatch.setattr(apple_api, "get_settings", lambda: type("S", (), {"storage_dir": str(tmp_path)})())
    queued: list = []
    monkeypatch.setattr(tasks.apple_import_task, "apply_async", lambda args: queued.append(args))
    data = _export_zip(tmp_path).read_bytes()
    h = auth(user)

    start = client.post(
        "/api/v1/imports/apple-health", json={"filename": "export.zip", "size_bytes": len(data)}, headers=h
    )
    assert start.status_code == 200, start.text
    up = start.json()
    assert up["status"] == "uploading" and up["chunk_bytes"] > 0
    url = f"/api/v1/imports/apple-health/{up['id']}"
    half = len(data) // 2
    assert client.put(f"{url}?offset=0", content=data[:half], headers=h).json()["received_bytes"] == half
    # Un trozo fuera de sitio se rechaza indicando desde dónde seguir.
    wrong = client.put(f"{url}?offset=0", content=data[half:], headers=h)
    assert wrong.status_code == 409 and str(half) in wrong.json()["error"]["message"]
    assert client.post(f"{url}/finish", headers=h).status_code == 409  # falta la mitad
    assert client.put(f"{url}?offset={half}", content=data[half:], headers=h).json()["received_bytes"] == len(data)
    assert client.post(f"{url}/finish", headers=h).json()["status"] == "queued"
    assert queued == [[up["id"]]]

    # El trabajo en segundo plano (aquí, directamente) importa y borra el fichero.
    monkeypatch.setattr(tasks, "engine", session.get_bind())
    result = tasks.apple_import_task(up["id"])
    assert result["workouts"] == 2
    assert not (tmp_path / "apple" / f"{up['id']}.upload").exists()
    latest = client.get("/api/v1/imports/apple-health", headers=h).json()
    assert latest["status"] == "done" and latest["progress"] == 100 and latest["result"]["workouts"] == 2
    assert client.get("/api/v1/sources", headers=h).json()["apple_last_at"] is not None


def test_api_subida_errores(client, user, session, tmp_path, monkeypatch):
    from app.api import apple as apple_api
    from app.tasks import sources as tasks

    monkeypatch.setattr(apple_api, "get_settings", lambda: type("S", (), {"storage_dir": str(tmp_path)})())
    h = auth(user)
    too_big = client.post(
        "/api/v1/imports/apple-health", json={"filename": "x.zip", "size_bytes": 5_000_000_000}, headers=h
    )
    assert too_big.status_code == 422
    up = client.post("/api/v1/imports/apple-health", json={"filename": "x.zip", "size_bytes": 10}, headers=h).json()
    assert (
        client.put(f"/api/v1/imports/apple-health/{up['id']}?offset=0", content=b"x" * 11, headers=h).status_code == 422
    )
    # Otra persona no puede tocar esta subida.
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert (
        client.put(f"/api/v1/imports/apple-health/{up['id']}?offset=0", content=b"x", headers=auth(other)).status_code
        == 404
    )
    # Un fichero que no es un export termina en error legible y sin fichero en disco.
    client.put(f"/api/v1/imports/apple-health/{up['id']}?offset=0", content=b"0123456789", headers=h)
    monkeypatch.setattr(tasks.apple_import_task, "apply_async", lambda args: None)
    client.post(f"/api/v1/imports/apple-health/{up['id']}/finish", headers=h)
    monkeypatch.setattr(tasks, "engine", session.get_bind())
    tasks.apple_import_task(up["id"])
    row = session.get(AppleImport, up["id"])
    session.refresh(row)
    assert row.status == "error" and "Apple Salud" in row.error
    assert client.delete(f"/api/v1/imports/apple-health/{up['id']}", headers=h).status_code == 204


def test_atajo_ios(client, user, session):
    token = health_connect.create_token(session, user.id)
    start = START.isoformat()
    payload = {
        "workouts": {
            "type": ["Correr", "Fuerza"],
            "start": [start, "2026-10-02 19:00:00 +0200"],
            "end": [(START + timedelta(minutes=30)).isoformat(), "2026-10-02 19:40:00 +0200"],
            "duration": [1800, "40:00"],
            "distance": ["6,1 km", None],
            "energy": [420, "250 kcal"],
        },
        "heart_rate": {
            "dates": [(START + timedelta(minutes=m)).isoformat() for m in range(31)],
            "values": [140 + m for m in range(31)],
        },
        "resting_hr": [{"date": "2026-10-01T08:00:00+02:00", "value": 48}],
    }
    assert (
        client.post("/api/v1/ingest/apple-shortcuts", json=payload, headers={"X-Api-Key": "hc_malo"}).status_code == 401
    )
    res = client.post("/api/v1/ingest/apple-shortcuts", json=payload, headers={"X-Api-Key": token}).json()
    assert res == {"workouts": 2, "duplicates": 0, "days": 1}
    run = session.exec(select(Activity).where(Activity.sport == "running")).one()
    assert run.source == "apple" and run.distance_m == pytest.approx(6100)
    assert (run.avg_hr, run.max_hr) == (155, 170)  # calculados del pulso del entreno
    strength = session.exec(select(Activity).where(Activity.sport == "strength_training")).one()
    assert strength.duration_s == 2400 and strength.calories == 250
    # Reenviar lo mismo (la automatización corre cada día) no duplica.
    again = client.post("/api/v1/ingest/apple-shortcuts", json=payload, headers={"X-Api-Key": token}).json()
    assert again["workouts"] == 0 and again["duplicates"] == 2
    assert (
        client.post("/api/v1/ingest/apple-shortcuts", content=b"[1]", headers={"X-Api-Key": token,
                    "Content-Type": "application/json"}).status_code == 422
    )  # fmt: skip


def test_atajo_lista_de_objetos(session: Session, user: User):
    counts = apple_health.ingest_shortcut(
        session,
        user.id,
        {
            "workouts": [
                {"tipo": "Ciclismo", "inicio": "2026-10-03 10:00:00 +0200", "duracion": "1:30:00", "distancia": 42}
            ]
        },
    )
    assert counts["workouts"] == 1
    ride = session.exec(select(Activity)).one()
    assert ride.sport == "cycling" and ride.distance_m == 42_000 and ride.duration_s == 5400
    assert ride.timezone == "+02:00"
