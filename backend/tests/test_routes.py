import math
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.core.security import create_token
from app.models import Activity, ActivityStream, User
from app.services import routes as svc

START = (37.6, -0.98)
M_PER_DEG = 111_195


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _track(km: float, heading_deg: float = 0, offset_m: float = 0, reverse: bool = False, n: int = 400):
    """Recorrido en línea recta (o al revés), con desplazamiento lateral opcional (ruido de GPS)."""
    h = math.radians(heading_deg)
    pts = []
    for i in range(n):
        d = km * 1000 * i / (n - 1)
        north, east = d * math.cos(h) - offset_m * math.sin(h), d * math.sin(h) + offset_m * math.cos(h)
        pts.append((START[0] + north / M_PER_DEG, START[1] + east / (M_PER_DEG * math.cos(math.radians(START[0])))))
    return pts[::-1] if reverse else pts


def _activity(session: Session, user: User, days_ago: int, pts, pace_s_km: float = 300, sport: str = "running",
              stop_at_m: float | None = None) -> Activity:  # fmt: skip
    dist = [0.0]
    for p, q in zip(pts, pts[1:], strict=False):
        dist.append(dist[-1] + svc.haversine(p, q))
    time = [d / 1000 * pace_s_km + (60 if stop_at_m is not None and d > stop_at_m else 0) for d in dist]
    a = Activity(user_id=user.id, sport=sport, name="Carrera", start_time=datetime.now(UTC) - timedelta(days=days_ago),
                 duration_s=time[-1], distance_m=dist[-1], avg_hr=150)  # fmt: skip
    session.add(a)
    session.commit()
    session.refresh(a)
    channels = {"lat": [p[0] for p in pts], "lon": [p[1] for p in pts], "distance": dist, "time": time,
                "hr": [140 + i % 20 for i in range(len(pts))], "altitude": [10.0] * len(pts)}  # fmt: skip
    for name, values in channels.items():
        session.add(ActivityStream(activity_id=a.id, channel=name, values=values))
    session.commit()
    return a


def test_huella_y_coincidencia():
    pts = _track(5)
    sig = svc.resample(pts, [svc.haversine(pts[0], p) for p in pts])
    assert len(sig) == svc.SIG_POINTS and sig[0] == [round(START[0], 6), round(START[1], 6)]
    noisy = svc.resample(*(lambda p: (p, [svc.haversine(p[0], q) for q in p]))(_track(5, offset_m=30)))
    other = svc.resample(*(lambda p: (p, [svc.haversine(p[0], q) for q in p]))(_track(5, heading_deg=90)))
    assert svc.same_route(sig, 5000, noisy, 5000)  # 30 m de ruido lateral
    assert not svc.same_route(sig, 5000, other, 5000)  # otra dirección
    assert not svc.same_route(sig, 5000, noisy, 6000)  # distancia muy distinta
    assert svc.resample(pts[:2], [0, 500]) is None  # demasiado corto


def test_un_desvio_largo_no_se_esconde_en_la_media():
    """Misma salida y llegada, pero un 25 % del camino a 400 m (p. ej. salir del estadio a la calle)."""
    base = [[START[0] + i * 0.0008, START[1]] for i in range(64)]
    detour = [[p[0], p[1] + (0.0045 if 24 <= i < 40 else 0)] for i, p in enumerate(base)]
    assert svc.mean_deviation(base, detour) < svc.MATCH_MEAN_M  # la media sola lo daría por bueno
    assert not svc.same_route(base, 5600, detour, 5600)


def test_agrupa_recorridos_repetidos(session, user):
    a = _activity(session, user, 30, _track(6), pace_s_km=330)
    b = _activity(session, user, 20, _track(6, offset_m=25), pace_s_km=300)
    _activity(session, user, 15, _track(6, reverse=True))  # mismo camino al revés: otro recorrido
    _activity(session, user, 10, _track(6, heading_deg=120))  # otro sitio
    _activity(session, user, 5, _track(6), sport="cycling")  # otro deporte
    groups = svc.group_routes(session, user.id)
    assert len(groups) == 1 and [m.id for m in groups[0].members] == [a.id, b.id]
    out = svc.group_out(groups[0])
    assert out["count"] == 2 and out["best"]["activity_id"] == b.id and out["name"] == "Carrera · 6,0 km"
    session.refresh(a)
    assert a.metrics[svc.SIG_KEY]["v"] == svc.SIG_VERSION  # huella guardada


def test_sin_gps_se_cachea_vacio(session, user):
    a = Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC), duration_s=1800, distance_m=5000)
    session.add(a)
    session.commit()
    assert svc.signature(session, a) is None and a.metrics[svc.SIG_KEY] == {"v": 1, "pts": None}


def test_comparar_alinea_por_distancia(session, user):
    a = _activity(session, user, 10, _track(3), pace_s_km=300)
    b = _activity(session, user, 5, _track(3, offset_m=20), pace_s_km=280, stop_at_m=1500)
    c = svc.compare(session, a, b)
    assert 2990 < c["distance_m"] <= 3000 and len(c["splits"]) == 2
    s1, s2 = c["splits"]
    assert abs(s1["a"] - 300) < 1 and abs(s1["b"] - 280) < 1 and abs(s2["diff"] - 40) < 2  # −20 s +60 s parada
    mid = next(p for p in c["points"] if p["distance_m"] >= 1000)
    assert abs(mid["gap_s"] + 20) < 1.5 and abs(mid["pace_a"] - 300) < 2
    assert len(c["track_a"]) > 50 and c["a"]["activity_id"] == a.id


def test_api_recorridos(client, user, session):
    a = _activity(session, user, 30, _track(5), pace_s_km=330)
    b = _activity(session, user, 20, _track(5), pace_s_km=310)
    lone = _activity(session, user, 10, _track(5, heading_deg=200))
    routes = client.get("/api/v1/routes", headers=auth(user)).json()
    assert len(routes) == 1 and routes[0]["id"] == a.id and routes[0]["count"] == 2
    detail = client.get(f"/api/v1/routes/{a.id}", headers=auth(user)).json()
    assert len(detail["efforts"]) == 2 and len(detail["track"]) > svc.SIG_POINTS  # trazado real
    mine = client.get(f"/api/v1/routes/by-activity/{b.id}", headers=auth(user)).json()
    assert mine["id"] == a.id and mine["rank"] == 1
    assert client.get(f"/api/v1/routes/by-activity/{lone.id}", headers=auth(user)).json() is None
    assert client.get("/api/v1/routes/999", headers=auth(user)).status_code == 404
    res = client.get(f"/api/v1/routes/compare?a={a.id}&b={b.id}", headers=auth(user))
    assert res.status_code == 200 and res.json()["splits"][0]["diff"] < 0
    assert client.get(f"/api/v1/routes/compare?a={a.id}&b={a.id}", headers=auth(user)).status_code == 422


def test_comparar_actividad_ajena_404(client, user, session):
    a = _activity(session, user, 3, _track(2))
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    b = _activity(session, other, 3, _track(2))
    assert client.get(f"/api/v1/routes/compare?a={a.id}&b={b.id}", headers=auth(user)).status_code == 404
    assert client.get(f"/api/v1/routes/by-activity/{b.id}", headers=auth(user)).status_code == 404
