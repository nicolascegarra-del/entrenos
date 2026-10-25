import json
from datetime import date, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import PlannedSession, User
from app.services import ai_tools
from app.services import route_planner as rp

POINTS = [{"lat": 37.60, "lon": -0.98}, {"lat": 37.61, "lon": -0.97}]


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def ors_response(n: int = 101, climb: float = 50.0) -> dict:
    """Ruta recta de ~1,2 km que sube `climb` m en la primera mitad y baja la mitad en la segunda."""
    coords = []
    for i in range(n):
        alt = 100 + climb * min(i, n // 2) / (n // 2) - (climb / 2) * max(0, i - n // 2) / (n // 2)
        coords.append([-0.98 + i * 0.0001, 37.60 + i * 0.0001, alt])
    return {
        "features": [
            {
                "geometry": {"coordinates": coords},
                "properties": {
                    "summary": {"distance": 1400.0, "duration": 1000.0},
                    "ascent": climb,
                    "descent": climb / 2,
                    "extras": {
                        "surface": {"summary": [{"value": 3, "distance": 1000.0}, {"value": 11, "distance": 400.0}]},
                        "waytype": {"summary": [{"value": 3, "distance": 900.0}, {"value": 4, "distance": 500.0}]},
                    },
                },
            }
        ]
    }


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


@pytest.fixture
def ors(monkeypatch):
    """Motor openrouteservice (opcional, con clave) simulado."""
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, body: dict) -> dict:
        calls.append((path, body))
        return ors_response()

    monkeypatch.setattr(rp.get_settings(), "route_engine", "ors")
    monkeypatch.setattr(rp, "_ors_post", fake_post)
    cache = FakeRedis()
    monkeypatch.setattr(rp, "_redis", lambda: cache)
    return calls


def test_calcula_la_ruta_con_desnivel_superficies_y_tiempo(client, user, ors):
    res = client.post("/api/v1/planned-routes/plan", json={"mode": "trail", "points": POINTS}, headers=auth(user))
    assert res.status_code == 200
    data = res.json()
    assert ors[0][0] == "/v2/directions/foot-hiking/geojson"
    assert ors[0][1]["coordinates"] == [[-0.98, 37.60], [-0.97, 37.61]] and ors[0][1]["elevation"] is True
    assert (data["distance_m"], data["ascent_m"], data["descent_m"]) == (1400, 50, 25)
    assert data["geometry"][0] == [37.6, -0.98, 100.0] and len(data["profile"]) == 101
    assert data["surfaces"][0] == {"tipo": "Asfalto o pavimento", "distancia_m": 1000, "pct": 71}
    assert {w["tipo"] for w in data["waytypes"]} == {"Carretera o calle", "Sendero o camino"}
    # Sin entrenos: 6:00/km × 1,15 en sendero, más lento por la subida.
    assert data["estimated_s"] > 1.4 * 360 * 1.15 and data["estimate_basis"] == "un ritmo fácil de 6:00/km"
    # La misma ruta otra vez sale de la caché.
    client.post("/api/v1/planned-routes/plan", json={"mode": "trail", "points": POINTS}, headers=auth(user))
    assert len(ors) == 1


def test_bici_por_velocidad_y_modos_desconocidos(session: Session, user: User, ors):
    bike = rp.plan(session, user.id, [rp.Waypoint(**p) for p in POINTS], "bici")
    assert ors[0][0] == "/v2/directions/cycling-regular/geojson"
    assert bike["estimated_s"] == round(1400 / (22 / 3.6) + 50 * 6)
    with pytest.raises(rp.RouteError, match="Modo"):
        rp.plan(session, user.id, [rp.Waypoint(**p) for p in POINTS], "avion")
    with pytest.raises(rp.RouteError, match="inicio y el final"):
        rp.plan(session, user.id, [rp.Waypoint(**POINTS[0])], "asfalto")


def test_limite_de_puntos_y_errores(client, user, ors, monkeypatch):
    many = [{"lat": 37.6 + i / 1000, "lon": -0.98} for i in range(rp.MAX_POINTS + 1)]
    assert client.post("/api/v1/planned-routes/plan", json={"mode": "asfalto", "points": many},
                       headers=auth(user)).status_code == 422  # fmt: skip

    def no_route(path: str, body: dict) -> dict:
        raise rp.RouteError("Algún punto está lejos de cualquier camino: acércalo a una calle o sendero.")

    monkeypatch.setattr(rp, "_ors_post", no_route)
    body = {"mode": "asfalto", "points": [POINTS[0], {"lat": 1, "lon": 1}]}
    res = client.post("/api/v1/planned-routes/plan", json=body, headers=auth(user))
    assert res.status_code == 422 and "lejos de cualquier camino" in res.json()["error"]["message"]


def test_sin_clave_explica_que_falta(session: Session, user: User, monkeypatch):
    monkeypatch.setattr(rp, "_redis", lambda: None)
    monkeypatch.setattr(rp.get_settings(), "route_engine", "ors")
    monkeypatch.setattr(rp.get_settings(), "ors_api_key", "")
    with pytest.raises(rp.RouteError, match="falta la clave"):
        rp.plan(session, user.id, [rp.Waypoint(**p) for p in POINTS], "asfalto")


def test_guardar_listar_gpx_asociar_y_borrar(client, user, session: Session, ors):
    h = auth(user)
    created = client.post("/api/v1/planned-routes", json={"name": "Vuelta al Calvario", "mode": "trail",
                                                         "points": POINTS}, headers=h)  # fmt: skip
    assert created.status_code == 201
    route = created.json()
    assert route["waypoints"] == [[37.6, -0.98], [37.61, -0.97]] and route["distance_m"] == 1400
    page = client.get("/api/v1/planned-routes", headers=h).json()
    assert page["total"] == 1 and page["items"][0]["name"] == "Vuelta al Calvario"
    assert len(page["items"][0]["preview"]) <= 60

    gpx = client.get(f"/api/v1/planned-routes/{route['id']}/gpx", headers=h)
    assert gpx.status_code == 200 and gpx.headers["content-type"].startswith("application/gpx+xml")
    assert b'creator="KTrain"' in gpx.content and gpx.content.count(b"<trkpt") == 101 and b"<ele>" in gpx.content

    planned = PlannedSession(user_id=user.id, day=date.today() + timedelta(days=2), sport="running", title="Tirada")
    session.add(planned)
    session.commit()
    linked = client.put(f"/api/v1/plans/{planned.id}/route", json={"planned_route_id": route["id"]}, headers=h)
    assert linked.json()["route"]["desnivel_positivo_m"] == 50
    detail = client.get(f"/api/v1/plans/{planned.id}", headers=h).json()
    assert detail["planned_route_id"] == route["id"] and detail["route"]["nombre"] == "Vuelta al Calvario"
    assert client.get(f"/api/v1/planned-routes/{route['id']}", headers=h).json()["sessions"][0]["id"] == planned.id

    # La IA ve la ruta en la sesión y su perfil por km.
    session.expire_all()
    _, text = ai_tools.execute(session, user.id, "plan_y_objetivos", {})
    assert json.loads(text)["sesiones"][0]["ruta"]["distancia_km"] == 1.4
    _, text = ai_tools.execute(session, user.id, "ruta_planificada", {"id": route["id"]})
    tool = json.loads(text)
    assert tool["por_km"][0]["km"] == 1 and tool["superficies"][0]["tipo"] == "Asfalto o pavimento"

    assert client.delete(f"/api/v1/planned-routes/{route['id']}", headers=h).status_code == 204
    session.expire_all()
    assert session.get(PlannedSession, planned.id).planned_route_id is None


def test_las_rutas_son_de_cada_uno(client, user, session: Session, ors):
    route = client.post("/api/v1/planned-routes", json={"name": "Mía", "mode": "asfalto", "points": POINTS},
                        headers=auth(user)).json()  # fmt: skip
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    h = auth(other)
    assert client.get(f"/api/v1/planned-routes/{route['id']}", headers=h).status_code == 404
    assert client.get(f"/api/v1/planned-routes/{route['id']}/gpx", headers=h).status_code == 404
    assert client.delete(f"/api/v1/planned-routes/{route['id']}", headers=h).status_code == 404
    assert client.get("/api/v1/planned-routes", headers=h).json()["total"] == 0
    mine = PlannedSession(user_id=other.id, day=date.today(), sport="running", title="X")
    session.add(mine)
    session.commit()
    assert client.put(f"/api/v1/plans/{mine.id}/route", json={"planned_route_id": route["id"]},
                      headers=h).status_code == 404  # fmt: skip


def brouter_response() -> dict:
    """GeoJSON de BRouter: 3 puntos que suben 30 m y bajan 10, con las etiquetas OSM de cada tramo."""
    return {
        "features": [
            {
                "geometry": {"coordinates": [[-0.98, 37.60, 100.0], [-0.975, 37.605, 130.0], [-0.97, 37.61, 120.0]]},
                "properties": {
                    "track-length": "1500",
                    "filtered ascend": "30",
                    "messages": [
                        ["Longitude", "Latitude", "Elevation", "Distance", "WayTags"],
                        ["-980000", "37600000", "100", "700", "highway=residential surface=asphalt"],
                        ["-975000", "37605000", "130", "500", "highway=path surface=dirt"],
                        ["-970000", "37610000", "120", "300", "highway=track"],
                    ],
                },
            }
        ]
    }


def test_brouter_sin_clave_es_el_motor_por_defecto(session: Session, user: User, monkeypatch):
    calls: list[tuple] = []

    def fake_get(points, mode):
        calls.append((points, mode))
        return brouter_response()

    monkeypatch.setattr(rp.get_settings(), "route_engine", "brouter")
    monkeypatch.setattr(rp.get_settings(), "ors_api_key", "")
    monkeypatch.setattr(rp, "_redis", lambda: None)
    monkeypatch.setattr(rp, "_brouter_get", fake_get)
    r = rp.plan(session, user.id, [rp.Waypoint(**p) for p in POINTS], "trail")
    assert calls[0][1] == "trail" and rp.BROUTER_PROFILES["trail"] == "hiking-mountain"
    assert (r["distance_m"], r["ascent_m"], r["descent_m"]) == (1500, 30, 10)
    assert r["geometry"][1] == [37.605, -0.975, 130.0] and r["max_altitude_m"] == 130
    assert {x["tipo"]: x["distancia_m"] for x in r["surfaces"]} == {"Asfalto o pavimento": 700,
                                                                    "Tierra, grava o pista": 800}  # fmt: skip
    assert {x["tipo"] for x in r["waytypes"]} == {"Carretera o calle", "Sendero o camino", "Pista"}


@pytest.mark.parametrize(
    ("status", "text", "message"),
    [
        (400, "position not mapped in existing datafile", "lejos de cualquier camino"),
        (503, "busy", "saturado"),
        (500, "no track found", "No se ha encontrado un camino"),
    ],
)
def test_errores_de_brouter(monkeypatch, status: int, text: str, message: str):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["profile"] == "shortest" and "lonlats" in request.url.params
        return httpx.Response(status, text=text)

    real = httpx.Client
    monkeypatch.setattr(rp.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(rp.RouteError, match=message):
        rp._brouter_get([rp.Waypoint(**p) for p in POINTS], "asfalto")
