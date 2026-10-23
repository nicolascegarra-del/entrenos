import base64
import json as _json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlmodel import Session, select

from app.core.crypto import decrypt_secret
from app.core.security import create_token
from app.models import Activity, CorosOAuth, OAuthClient, OAuthState, PlannedBlock, PlannedSession, User
from app.services import coros_oauth, coros_official, coros_workouts
from app.services.workout_export import WorkoutExportError
from tests.test_other_sources import _fit

TOMORROW = date.today() + timedelta(days=1)
META = {
    "resource": "https://mcpeu.coros.com/mcp",
    "issuer": "https://mcpeu.coros.com",
    "authorization_endpoint": "https://mcpeu.coros.com/oauth2/authorize",
    "token_endpoint": "https://mcpeu.coros.com/oauth2/token",
    "registration_endpoint": "https://mcpeu.coros.com/connect/register",
    "revocation_endpoint": "https://mcpeu.coros.com/oauth2/revoke",
}


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _blocks() -> list[PlannedBlock]:
    return [
        PlannedBlock(
            session_id=0,
            position=0,
            kind="warmup",
            repeat=1,
            duration_s=900,
            target_metric="hr",
            target_min=125,
            target_max=140,
        ),  # fmt: skip
        PlannedBlock(
            session_id=0,
            position=1,
            kind="interval",
            repeat=6,
            distance_m=1000,
            target_metric="pace",
            target_min=235,
            target_max=245,
            recovery_duration_s=90,
        ),  # fmt: skip
        PlannedBlock(session_id=0, position=2, kind="cooldown", repeat=1),
    ]


def _planned(sport: str = "running", day: date = TOMORROW) -> PlannedSession:
    return PlannedSession(user_id=1, day=day, sport=sport, title="Series 6 × 1000", notes="")


def test_formato_de_coros():
    c = coros_workouts.coros_course(_planned(), _blocks())
    assert c["sportType"] == 1 and c["courseName"] == "Series 6 × 1000"
    assert c["courseDescription"].startswith("Series 6 × 1000.") and "APP ENTRENOS" in c["courseDescription"]
    warm, group, cool = c["sections"]
    assert warm == {"sectionType": 1, "targetType": 2, "targetValue": 900, "intensityType": 1,
                    "intensityValueStart": 125, "intensityValueEnd": 140}  # fmt: skip
    assert group["intervalGroup"] is True and group["repeats"] == 6
    assert "targetType" not in group and "intensityType" not in group  # el contenedor no lleva objetivos
    work, rest = group["sets"]
    assert work == {"sectionType": 2, "targetType": 1, "targetValue": 1000, "intensityType": 2,
                    "intensityValueStart": 235, "intensityValueEnd": 245}  # fmt: skip
    assert rest == {"sectionType": 3, "targetType": 2, "targetValue": 90}
    assert cool == {"sectionType": 4, "targetType": 4}  # libre: hasta pulsar vuelta


def test_bici_y_deportes_sin_soporte():
    blocks = [PlannedBlock(session_id=0, position=0, kind="steady", repeat=1, duration_s=3600,
                           target_metric="speed", target_min=28, target_max=32)]  # fmt: skip
    c = coros_workouts.coros_course(_planned("indoor_cycling"), blocks)
    assert c["sportType"] == 2 and "intensityType" not in c["sections"][0]  # COROS no admite velocidad en bici
    with pytest.raises(WorkoutExportError):
        coros_workouts.coros_course(_planned("strength_training"), blocks)


@pytest.mark.parametrize(
    ("result", "expected"),
    [("Created. idInPlan: 1234567890123456789", "1234567890123456789"),
     ({"idInPlan": 987654321}, "987654321"), ('"idInPlan":"55556666777"', "55556666777"), ("ok", "")],
)  # fmt: skip
def test_id_del_resultado(result, expected):
    assert coros_workouts.id_in_plan(result) == expected


class FakeMcp:
    def __init__(self, fail: str = "") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail

    def call(self, name: str, arguments: dict) -> object:
        self.calls.append((name, arguments))
        if self.fail:
            raise coros_oauth.CorosOAuthError(self.fail)
        return f"Workout saved on {arguments['date']}. idInPlan: {1000000 + len(self.calls)}"


def _save(session: Session, user: User, day: date = TOMORROW) -> PlannedSession:
    planned = PlannedSession(user_id=user.id, day=day, sport="running", title="Series")
    session.add(planned)
    session.flush()
    for b in _blocks():
        b.session_id = planned.id
        session.add(b)
    session.commit()
    return planned


def test_enviar_actualizar_y_cambiar_de_dia(session: Session, user: User):
    planned = _save(session, user)
    mcp = FakeMcp()
    assert coros_workouts.send(session, planned, mcp) == "sent"
    assert mcp.calls[0][0] == "createScheduledWorkout" and mcp.calls[0][1]["date"] == TOMORROW.strftime("%Y%m%d")
    assert (planned.coros_status, planned.coros_id_in_plan, planned.coros_day) == ("sent", "1000001", TOMORROW)
    assert coros_workouts.send(session, planned, mcp) == "unchanged"
    planned.title = "Series cambiadas"  # mismo día: se actualiza el mismo entreno
    session.add(planned)
    session.commit()
    assert coros_workouts.send(session, planned, mcp) == "sent"
    assert mcp.calls[1][0] == "updateScheduledWorkout" and mcp.calls[1][1]["idInPlan"] == "1000001"
    planned.day = TOMORROW + timedelta(days=2)  # otro día: COROS no deja moverlo, se crea otro y se avisa
    session.add(planned)
    session.commit()
    assert coros_workouts.send(session, planned, mcp) == "sent"
    assert mcp.calls[2][0] == "createScheduledWorkout" and "quita el entreno" in planned.coros_error


def test_errores_de_coros(session: Session, user: User):
    planned = _save(session, user)
    assert coros_workouts.send(session, planned, FakeMcp(fail="Date out of range")) == "error"
    assert planned.coros_status == "error" and planned.coros_error == "Date out of range"
    past = _save(session, user, date.today() - timedelta(days=1))
    assert coros_workouts.send(session, past, FakeMcp()) == "error" and "90 días" in past.coros_error


LISTING = (
    "Sport Records — 2026-10-20 to 2026-10-23 (1 records)\n1. Outdoor Run — 2026-10-22\n"
    "   Duration: 35:12 | Distance: 5.23 km\n   LabelId: 481245905597530213 | SportType: 100"
)


class FakeFitMcp:
    def __init__(self, files: list[bytes], listing: str = LISTING) -> None:
        self.files, self.listing, self.downloads = files, listing, []

    def call_raw(self, name: str, arguments: dict) -> dict:
        if name == "querySportRecords":
            return {"content": [{"type": "text", "text": _json.dumps(self.listing)}]}
        assert name == "downloadActivityFitFiles" and arguments["sportType"] == 100
        self.downloads.append(arguments["labelId"])
        return {"content": [{"type": "text", "text": "Returned raw FIT file(s)."}] + [
            {"type": "resource", "resource": {"uri": f"coros://fit/{i}", "mimeType": "application/octet-stream",
                                              "blob": base64.b64encode(f).decode()}}
            for i, f in enumerate(self.files)
        ]}  # fmt: skip


def test_lista_de_actividades():
    assert coros_official.records(LISTING) == [("481245905597530213", 100)]


def test_sincronizar_actividades_por_fit(session: Session, user: User):
    session.add(CorosOAuth(user_id=user.id, client_id="c", issuer="i", mcp_url="u", access_token_enc="x"))
    session.commit()
    mcp = FakeFitMcp([_fit()])
    assert coros_official.sync(session, user.id, mcp) == 1  # type: ignore[arg-type]
    act = session.exec(select(Activity).where(Activity.user_id == user.id)).one()
    assert act.source == "coros" and act.external_id == "481245905597530213" and act.sport == "running"
    # La segunda pasada ni siquiera descarga: ya la tiene (no gasta el cupo de 50 al día).
    assert coros_official.sync(session, user.id, mcp) == 0  # type: ignore[arg-type]
    assert mcp.downloads == ["481245905597530213"]
    assert session.get(CorosOAuth, user.id).last_sync_at is not None


class FakeResponse:
    def __init__(self, data: dict | None = None, status: int = 200, text: str = "", ctype: str = "application/json"):
        self._data, self.status_code = data, status
        self.text = text or _json.dumps(data or {})
        self.content = self.text.encode()
        self.headers = {"content-type": ctype}

    def json(self) -> dict:
        return self._data if self._data is not None else _json.loads(self.text)


class FakeHttp:
    def __init__(self, posts: list) -> None:
        self.posts = posts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, data=None, headers=None):  # noqa: A002 - firma de httpx
        self.posts.append((url, json or data, headers))
        if url.endswith("/connect/register"):
            return FakeResponse({"client_id": "cliente-123"})
        if url.endswith("/oauth2/token"):
            return FakeResponse({"access_token": "acceso", "refresh_token": "refresco", "expires_in": 3600})
        if url.endswith("/mcp"):
            body = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": '"hola"'}]}}
            return FakeResponse(text=f"event: message\ndata: {_json.dumps(body)}\n\n", ctype="text/event-stream")
        return FakeResponse({})


def test_oauth_completo_y_llamada_mcp(client, user, session, monkeypatch):
    posts: list = []
    monkeypatch.setattr(coros_oauth, "discover", lambda *a: META)
    monkeypatch.setattr(coros_oauth, "_http", lambda: FakeHttp(posts))
    h = auth(user)
    assert client.post("/api/v1/sources/coros-official/connect", json={"origin": "https://malo.example"},
                       headers=h).status_code == 400  # fmt: skip
    res = client.post("/api/v1/sources/coros-official/connect", json={"origin": "http://localhost:3000"}, headers=h)
    assert res.status_code == 200, res.text
    q = parse_qs(urlparse(res.json()["url"]).query)
    assert q["client_id"] == ["cliente-123"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://localhost:3000/api/v1/sources/coros-official/callback"]
    assert q["resource"] == [META["resource"]] and "offline_access" in q["scope"][0]
    state = q["state"][0]
    assert session.get(OAuthState, state) is not None
    # Un segundo intento reutiliza el cliente registrado.
    client.post("/api/v1/sources/coros-official/connect", json={"origin": "http://localhost:3000"}, headers=h)
    assert len(session.exec(select(OAuthClient)).all()) == 1
    state = session.exec(select(OAuthState)).one().state

    from app.tasks import sources as tasks

    monkeypatch.setattr(tasks.coros_official_sync_task, "apply_async", lambda **kw: None)
    back = client.get(f"/api/v1/sources/coros-official/callback?state={state}&code=abc", follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"] == "http://localhost:3000/ajustes/conexiones?coros=ok"
    token_call = next(p for p in posts if p[0].endswith("/oauth2/token"))
    assert token_call[1]["code_verifier"] and token_call[1]["grant_type"] == "authorization_code"
    row = session.get(CorosOAuth, user.id)
    session.refresh(row)
    assert decrypt_secret(row.access_token_enc) == "acceso" and decrypt_secret(row.refresh_token_enc) == "refresco"
    assert client.get("/api/v1/sources", headers=h).json()["coros_official"]["status"] == "ok"
    # El state es de un solo uso.
    again = client.get(f"/api/v1/sources/coros-official/callback?state={state}&code=abc", follow_redirects=False)
    assert again.headers["location"].endswith("?coros=error")
    # Llamada a una herramienta (respuesta SSE) con el token guardado.
    assert coros_oauth.CorosMcp(session, user.id).call("queryUserInfo", {}) == "hola"
    assert posts[-1][2]["Authorization"] == "Bearer acceso"
    assert client.delete("/api/v1/sources/coros-official", headers=h).status_code == 204
    session.expire_all()
    assert session.get(CorosOAuth, user.id) is None


def test_cancelar_en_coros(client, user, session):
    session.add(OAuthState(state="s1", user_id=user.id, provider="coros", code_verifier="v",
                           redirect_uri="http://localhost:3000/api/v1/sources/coros-official/callback"))  # fmt: skip
    session.commit()
    back = client.get("/api/v1/sources/coros-official/callback?state=s1&error=access_denied", follow_redirects=False)
    assert back.headers["location"] == "http://localhost:3000/ajustes/conexiones?coros=cancelada"


def test_api_enviar_a_coros(client, user, session, monkeypatch):
    from app.api import workouts as api

    h = auth(user)
    planned = _save(session, user)
    assert client.post(f"/api/v1/plans/{planned.id}/coros", headers=h).status_code == 409
    fake = FakeMcp()
    monkeypatch.setattr(api, "CorosMcp", lambda s, uid: fake)
    monkeypatch.setattr(api, "_coros_connected", lambda s, uid: True)
    res = client.post(f"/api/v1/plans/{planned.id}/coros", headers=h).json()
    assert res["coros_status"] == "sent"
    detail = client.get(f"/api/v1/plans/{planned.id}", headers=h).json()
    assert detail["coros_status"] == "sent" and detail["coros_outdated"] is False
    total = client.post("/api/v1/workouts/send-upcoming", headers=h).json()
    assert total == {"sent": 0, "unchanged": 1, "error": 0}
    assert client.get("/api/v1/workouts/settings", headers=h).json()["coros_connected"] is True


def _activity_fit() -> bytes:
    """FIT de actividad de carrera (10 min, 2 vueltas) con cadencia, potencia y efecto de entrenamiento."""
    from datetime import UTC, datetime

    from app.services.workout_export import FIT_EPOCH, _FitWriter

    start = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)
    ts = int((start - FIT_EPOCH).total_seconds())
    w = _FitWriter()
    w.message(0, [(0, "enum", None), (1, "uint16", None), (4, "uint32", None)], [[4, 294, ts]])  # file_id: actividad
    rec = [(253, "uint32", None), (5, "uint32", None), (3, "uint8", None), (4, "uint8", None), (7, "uint16", None)]
    w.message(20, rec, [[ts + i, round(i * 3.2 * 100), 150 + i // 60, 85, 250] for i in range(600)])
    lap = [(253, "uint32", None), (2, "uint32", None), (7, "uint32", None), (8, "uint32", None),
           (9, "uint32", None), (15, "uint8", None), (16, "uint8", None), (17, "uint8", None),
           (19, "uint16", None), (21, "uint16", None)]  # fmt: skip
    w.message(19, lap, [[ts + 300 * (k + 1), ts + 300 * k, 300_000, 300_000, 96_000, 152 + 5 * k, 160 + 5 * k,
                         85, 248 + 4 * k, 3 + k] for k in range(2)])  # fmt: skip
    session = [(253, "uint32", None), (2, "uint32", None), (5, "enum", None), (7, "uint32", None),
               (8, "uint32", None), (9, "uint32", None), (16, "uint8", None), (17, "uint8", None),
               (18, "uint8", None), (20, "uint16", None), (34, "uint16", None), (24, "uint8", None),
               (137, "uint8", None)]  # fmt: skip
    w.message(18, session, [[ts + 600, ts, 1, 600_000, 600_000, 192_000, 155, 165, 86, 250, 262, 32, 11]])
    return w.bytes()


def test_actividad_de_coros_tan_completa_como_garmin(session: Session, user: User):
    from app.models import ActivityStream, Lap
    from app.services import ai_tools
    from app.services.file_import import parse_fit, save_imported

    act = parse_fit(_activity_fit())
    assert act.metrics["avg_cadence"] == 172  # 86 zancadas/min → 172 pasos/min, como Garmin
    assert (act.metrics["avg_power"], act.metrics["normalized_power"]) == (250, 262)
    assert (act.metrics["aerobic_te"], act.metrics["anaerobic_te"]) == (3.2, 1.1)
    assert len(act.laps) == 2 and act.laps[1]["start_offset_s"] == 300 and act.laps[0]["avg_hr"] == 152
    saved, _ = save_imported(session, user.id, act, "coros", "fit:1")
    laps = session.exec(select(Lap).where(Lap.activity_id == saved.id).order_by(Lap.index)).all()
    assert [lap.metrics["avg_power"] for lap in laps] == [248, 252]
    cad = session.exec(select(ActivityStream).where(ActivityStream.activity_id == saved.id,
                                                    ActivityStream.channel == "cadence")).one()  # fmt: skip
    assert cad.values[0] == 170
    # La IA ve vueltas, cadencia, potencia y efecto de entrenamiento, como con Garmin.
    _, detail = ai_tools.detalle_actividad(session, user.id, {"id": saved.id})
    assert len(detail["vueltas"]) == 2 and detail["vueltas"][0]["cadencia"] == 170
    assert any("otencia" in k for k in detail["metricas_del_reloj"])


def test_descarga_bloqueada_por_coros_se_avisa(session: Session, user: User):
    session.add(CorosOAuth(user_id=user.id, client_id="c", issuer="i", mcp_url="u", access_token_enc="x"))
    session.commit()

    class Blocked:
        def call_raw(self, name, arguments):
            if name == "querySportRecords":
                return {"content": [{"type": "text", "text": LISTING}]}
            return {"content": [{"type": "text", "text": "Tool call anomalies detected. High risk..."}]}

    assert coros_official.sync(session, user.id, Blocked()) == 0  # type: ignore[arg-type]
    row = session.get(CorosOAuth, user.id)
    assert row.last_error == coros_official.BLOCKED and row.last_sync_at is None
